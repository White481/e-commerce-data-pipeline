"""CLI สำหรับรัน pipeline รายวัน

    python -m ingest.run init
    python -m ingest.run load --date 2011-01-05
    python -m ingest.run load --since-last
    python -m ingest.run notify --date 2011-01-05

transform ทำด้วย dbt (dbt_project/) ไม่ได้อยู่ในไฟล์นี้
"""

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ingest.db import get_engine
from ingest.load_raw import init_db, load_raw, record_skipped
from ingest.validate import MAX_REJECT_RATE, CircuitBreakerError

LANDING_DIR = Path(os.getenv("LANDING_DIR", "data/landing"))
def landing_file(day: date, landing_dir: Path = LANDING_DIR) -> Path:
    return landing_dir / f"{day:%Y-%m-%d}.csv"


def read_landing(path: Path) -> pd.DataFrame:
    return pd.read_csv(
        path, dtype={"InvoiceNo": str, "StockCode": str}, parse_dates=["InvoiceDate"]
    )


def load_day(
    engine: Engine, day: date, landing_dir: Path = LANDING_DIR,
    max_reject_rate: float = MAX_REJECT_RATE,
) -> dict:
    path = landing_file(day, landing_dir)
    if not path.exists():
        run_id = record_skipped(engine, str(path), day)
        print(f"{day}: ไม่มีไฟล์ {path} → skipped (run_id={run_id})")
        return {"run_id": run_id, "status": "skipped"}

    rate = max(max_reject_rate, approved_reject_rate(engine, day))
    summary = load_raw(read_landing(path), engine, str(path), day, rate)
    print(
        f"{day}: อ่าน {summary['rows_read']} แถว, ปฏิเสธ {summary['rows_rejected']}, "
        f"โหลด {summary['rows_loaded']} (insert {summary['rows_inserted']}, "
        f"update {summary['rows_updated']})"
    )
    return {"status": "success", **summary}


def approved_reject_rate(engine: Engine, day: date) -> float:
    """เพดานที่เคยอนุมัติให้วันนี้ (override ที่โหลดสำเร็จแล้ว) เพื่อไม่ให้ breaker ตัดวันเดิมซ้ำ"""
    with engine.connect() as conn:
        rate = conn.execute(
            text("""
                SELECT max(max_reject_rate) FROM audit.pipeline_runs
                WHERE pipeline = 'load_raw' AND batch_date = :day AND status = 'success'
            """),
            {"day": day},
        ).scalar()
    return float(rate) if rate is not None else MAX_REJECT_RATE


def loaded_days(engine: Engine) -> set[date]:
    with engine.connect() as conn:
        return set(conn.execute(text(
            "SELECT DISTINCT invoice_date::date FROM raw.online_retail"
        )).scalars())


def watermark(engine: Engine) -> date | None:
    """วันล่าสุดที่มีข้อมูลอยู่ใน raw จริง (ไม่ใช่วันที่ audit บอกว่ารันแล้ว)"""
    with engine.connect() as conn:
        latest = conn.execute(text("SELECT max(invoice_date) FROM raw.online_retail")).scalar()
    return latest.date() if latest else None


def load_since_last(
    engine: Engine, landing_dir: Path = LANDING_DIR,
    max_reject_rate: float = MAX_REJECT_RATE,
) -> list[dict]:
    available = sorted(date.fromisoformat(p.stem) for p in landing_dir.glob("*.csv"))
    if not available:
        print(f"ไม่มีไฟล์ใน {landing_dir}")
        return []

    # โหลดวัน watermark ซ้ำด้วย เผื่อรอบก่อนได้ข้อมูลของวันนั้นไม่ครบ
    # และถ้ามีวันก่อนหน้าที่มีไฟล์แต่ยังไม่มีข้อมูล (เช่นเคยโหลดข้ามวัน) ให้เริ่มจากวันนั้น
    mark = watermark(engine)
    loaded = loaded_days(engine)
    gaps = [d for d in available if d not in loaded]
    candidates = [d for d in (mark, gaps[0] if gaps else None) if d is not None]
    start, end = min(candidates, default=available[0]), available[-1]
    print(f"watermark={mark}, วันแรกที่ขาด={gaps[0] if gaps else None} → โหลด {start} ถึง {end}")

    results = []
    day = start
    while day <= end:
        # วันที่ล้มจะหยุดทั้ง loop: ไม่ข้ามไปโหลดวันถัดไป รอบหน้าจะเริ่มใหม่จากตรงนี้
        results.append(load_day(engine, day, landing_dir, max_reject_rate))
        day += timedelta(days=1)
    return results


def notify(engine: Engine, day: date) -> str:
    """สรุปผลของวันจาก audit + marts.fact_sales ของ dbt (ตอนนี้แค่ print ให้ไปอยู่ใน task log)"""
    with engine.connect() as conn:
        run = conn.execute(text("""
            SELECT status, rows_read, rows_rejected, rows_inserted, rows_updated
            FROM audit.pipeline_runs
            WHERE pipeline = 'load_raw' AND batch_date = :day
            ORDER BY run_id DESC LIMIT 1
        """), {"day": day}).one_or_none()
        fact_rows, revenue = 0, 0
        if conn.execute(text("SELECT to_regclass('marts.fact_sales')")).scalar():
            fact_rows, revenue = conn.execute(text("""
                SELECT count(*), coalesce(sum(total_amount), 0)
                FROM marts.fact_sales WHERE date_key = :day
            """), {"day": day}).one()
    if run is None:
        message = f"{day}: ไม่มีบันทึกการโหลด"
    else:
        status, read, rejected, inserted, updated = run
        message = (
            f"{day}: load={status} อ่าน {read} ปฏิเสธ {rejected} insert {inserted} "
            f"update {updated} | fact {fact_rows} แถว รายได้ {revenue:,.2f}"
        )
    print(message)
    return message


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ingest.run")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="สร้าง schema raw/audit (รันซ้ำได้)")

    load = sub.add_parser("load", help="โหลดไฟล์รายวันจาก landing")
    which = load.add_mutually_exclusive_group(required=True)
    which.add_argument("--date", type=date.fromisoformat, help="YYYY-MM-DD")
    which.add_argument("--since-last", action="store_true")
    load.add_argument(
        "--max-reject-rate", type=float, default=MAX_REJECT_RATE,
        help="เพดานแถวเสีย (default 0.05) ใช้ override เฉพาะวันที่ตรวจแล้ว",
    )
    notify_cmd = sub.add_parser("notify")
    notify_cmd.add_argument("--date", type=date.fromisoformat, required=True)
    args = parser.parse_args(argv)

    engine = get_engine()
    init_db(engine)
    if args.command == "init":
        print("init เสร็จ")
        return 0

    if args.command == "notify":
        notify(engine, args.date)
        return 0

    try:
        if args.date:
            load_day(engine, args.date, max_reject_rate=args.max_reject_rate)
        else:
            load_since_last(engine, max_reject_rate=args.max_reject_rate)
    except CircuitBreakerError as exc:
        print(f"circuit breaker: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
