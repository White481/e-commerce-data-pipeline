"""โหลดข้อมูลดิบเข้า raw.online_retail แบบ idempotent

- รันซ้ำกี่รอบก็ได้ผลเหมือนเดิม (upsert ด้วย line_id)
- แถวที่ไม่ผ่าน validate เขียนลง audit.rejected_rows พร้อมเหตุผล
- ทุกการรันเขียน 1 แถวลง audit.pipeline_runs
"""

import io
import json
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ingest.db import get_engine
from ingest.validate import check_reject_rate, validate

PIPELINE = "load_raw"
SOURCE_FILE = "data/Online Retail.xlsx"
INIT_SQL = Path(__file__).resolve().parent.parent / "sql" / "init.sql"

COLUMNS = [
    "line_id", "invoice_no", "line_no", "stock_code", "description",
    "quantity", "invoice_date", "unit_price", "customer_id", "country", "source_file",
]
# คอลัมน์ที่ใช้เช็กว่าแถวเปลี่ยนจริงไหม ก่อนจะ UPDATE
DATA_COLUMNS = COLUMNS[1:]

UPSERT_SQL = f"""
WITH upserted AS (
    INSERT INTO raw.online_retail ({", ".join(COLUMNS)}, run_id)
    SELECT {", ".join(COLUMNS)}, :run_id FROM stg_online_retail
    ON CONFLICT (line_id) DO UPDATE SET
        {", ".join(f"{c} = EXCLUDED.{c}" for c in DATA_COLUMNS)},
        run_id = EXCLUDED.run_id,
        loaded_at = now()
    WHERE ({", ".join(f"raw.online_retail.{c}" for c in DATA_COLUMNS)})
          IS DISTINCT FROM ({", ".join(f"EXCLUDED.{c}" for c in DATA_COLUMNS)})
    RETURNING (xmax = 0) AS inserted
)
SELECT count(*) FILTER (WHERE inserted)     AS inserted,
       count(*) FILTER (WHERE NOT inserted) AS updated
FROM upserted
"""


def init_db(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(INIT_SQL.read_text())


def prepare(df: pd.DataFrame, source_file: str) -> pd.DataFrame:
    """แปลงคอลัมน์ต้นฉบับให้ตรงกับ raw.online_retail และสร้าง line_id"""
    out = pd.DataFrame({
        "invoice_no": df["InvoiceNo"].astype(str),
        "stock_code": df["StockCode"].astype(str),
        "description": df["Description"],
        "quantity": df["Quantity"],
        "invoice_date": pd.to_datetime(df["InvoiceDate"]),
        "unit_price": df["UnitPrice"],
        "customer_id": df["CustomerID"].astype("Int64"),
        "country": df["Country"],
    })
    # ลำดับบรรทัดภายใน invoice ตามลำดับในไฟล์ต้นฉบับ (เริ่มที่ 1)
    out["line_no"] = out.groupby("invoice_no").cumcount() + 1
    out["line_id"] = out["invoice_no"] + "-" + out["line_no"].astype(str)
    out["source_file"] = source_file
    return out[COLUMNS]


def _start_run(engine: Engine, source_file: str) -> int:
    with engine.begin() as conn:
        return conn.execute(
            text("""
                INSERT INTO audit.pipeline_runs (pipeline, source_file, status)
                VALUES (:pipeline, :source_file, 'running')
                RETURNING run_id
            """),
            {"pipeline": PIPELINE, "source_file": source_file},
        ).scalar_one()


def _finish_run(engine: Engine, run_id: int, **fields) -> None:
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    with engine.begin() as conn:
        conn.execute(
            text(f"UPDATE audit.pipeline_runs SET {sets}, finished_at = now() WHERE run_id = :run_id"),
            {"run_id": run_id, **fields},
        )


def _write_rejected(engine: Engine, run_id: int, bad: pd.DataFrame) -> None:
    if bad.empty:
        return
    records = json.loads(bad.drop(columns="reason").to_json(orient="records", date_format="iso"))
    params = [
        {"run_id": run_id, "line_id": line_id, "reason": reason, "record": json.dumps(record)}
        for line_id, reason, record in zip(bad["line_id"], bad["reason"], records)
    ]
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO audit.rejected_rows (run_id, line_id, reason, record)
                VALUES (:run_id, :line_id, :reason, CAST(:record AS JSONB))
            """),
            params,
        )


def load_raw(df: pd.DataFrame, engine: Engine, source_file: str) -> dict:
    # audit row แยก transaction: ถ้าโหลดล้ม rollback แล้ว ยังมีบันทึกว่ารันแล้วล้ม
    run_id = _start_run(engine, source_file)
    rows_read, rows_rejected = len(df), 0
    try:
        good, bad = validate(prepare(df, source_file))
        rows_rejected = len(bad)
        # เขียนแถวเสียก่อนเช็ก circuit breaker เพื่อให้ดูได้ว่าทำไม batch ถูกตัด
        _write_rejected(engine, run_id, bad)
        check_reject_rate(rows_read, rows_rejected)

        buf = io.StringIO()
        good.to_csv(buf, index=False, header=False)
        buf.seek(0)

        # ทุกอย่างด้านล่างอยู่ใน transaction เดียว: สำเร็จทั้งหมดหรือไม่มีอะไรเปลี่ยนเลย
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE TEMP TABLE stg_online_retail "
                "(LIKE raw.online_retail INCLUDING DEFAULTS) ON COMMIT DROP"
            )
            cursor = conn.connection.cursor()
            cursor.copy_expert(
                f"COPY stg_online_retail ({', '.join(COLUMNS)}) FROM STDIN WITH (FORMAT csv)",
                buf,
            )
            inserted, updated = conn.execute(text(UPSERT_SQL), {"run_id": run_id}).one()
            # แถวที่ตอนนี้ไม่ผ่านกฎ แต่เคยโหลดเข้าไปแล้วในรอบก่อน ต้องเอาออก
            if not bad.empty:
                conn.execute(
                    text("DELETE FROM raw.online_retail WHERE line_id = ANY(:ids)"),
                    {"ids": bad["line_id"].tolist()},
                )
    except Exception as exc:
        _finish_run(
            engine, run_id, status="failed", rows_read=rows_read,
            rows_rejected=rows_rejected, error_message=str(exc)[:2000],
        )
        raise

    summary = {
        "rows_read": rows_read,
        "rows_rejected": rows_rejected,
        "rows_loaded": len(good),
        "rows_inserted": inserted,
        "rows_updated": updated,
    }
    _finish_run(
        engine, run_id, status="success",
        **{k: v for k, v in summary.items() if k != "rows_loaded"},
    )
    return {"run_id": run_id, **summary}


def main() -> None:
    engine = get_engine()
    init_db(engine)
    df = pd.read_excel(SOURCE_FILE, dtype={"InvoiceNo": str, "StockCode": str})
    summary = load_raw(df, engine, SOURCE_FILE)
    print(
        f"run_id={summary['run_id']}: อ่าน {summary['rows_read']} แถว, "
        f"ปฏิเสธ {summary['rows_rejected']}, โหลด {summary['rows_loaded']} "
        f"(insert {summary['rows_inserted']}, update {summary['rows_updated']})"
    )


if __name__ == "__main__":
    main()
