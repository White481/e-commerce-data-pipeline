"""Integration test: ต้องมี Postgres รันอยู่ (make up) ไม่งั้นจะ skip"""

import pandas as pd
import psycopg2
import pytest
from sqlalchemy import text

from ingest.load_raw import load_raw
from ingest.validate import CircuitBreakerError
from tests.conftest import truncate

SOURCE = "test.xlsx"


@pytest.fixture(autouse=True)
def clean_tables(engine):
    truncate(engine)


def _sample():
    return pd.DataFrame({
        "InvoiceNo": ["536365", "536365", "536365", "C536379", "536380"],
        "StockCode": ["85123A", "71053", "85123A", "D", "22961"],
        "Description": ["HEART T-LIGHT", "LANTERN", "HEART T-LIGHT", "Discount", None],
        "Quantity": [6, 6, 6, -1, 24],
        "InvoiceDate": pd.to_datetime(["2010-12-01 08:26"] * 3 + ["2010-12-01 09:41", "2010-12-01 09:45"]),
        "UnitPrice": [2.55, 3.39, 2.55, 27.5, 1.45],
        "CustomerID": [17850.0, 17850.0, 17850.0, 14527.0, None],
        "Country": ["United Kingdom"] * 5,
    })


def _count(engine, table="raw.online_retail"):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()


def test_rerun_keeps_same_count(engine):
    first = load_raw(_sample(), engine, SOURCE)
    second = load_raw(_sample(), engine, SOURCE)

    assert _count(engine) == 5
    assert first["rows_inserted"] == 5
    assert second["rows_inserted"] == 0 and second["rows_updated"] == 0


def test_duplicate_invoice_stock_lines_are_kept(engine):
    # 536365 + 85123A ปรากฏ 2 บรรทัด ต้องไม่ถูกรวมเป็นแถวเดียว
    load_raw(_sample(), engine, SOURCE)
    with engine.connect() as conn:
        ids = conn.execute(text(
            "SELECT line_id FROM raw.online_retail WHERE stock_code = '85123A' ORDER BY line_no"
        )).scalars().all()
    assert ids == ["536365-1", "536365-3"]


def test_deleted_rows_come_back(engine):
    load_raw(_sample(), engine, SOURCE)
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM raw.online_retail WHERE invoice_no = '536365'")
    assert _count(engine) == 2

    result = load_raw(_sample(), engine, SOURCE)
    assert _count(engine) == 5
    assert result["rows_inserted"] == 3


def test_changed_row_is_updated(engine):
    load_raw(_sample(), engine, SOURCE)
    changed = _sample()
    changed.loc[1, "Quantity"] = 12
    result = load_raw(changed, engine, SOURCE)
    assert result["rows_updated"] == 1 and result["rows_inserted"] == 0


def test_each_run_writes_audit_row(engine):
    load_raw(_sample(), engine, SOURCE)
    load_raw(_sample(), engine, SOURCE)
    with engine.connect() as conn:
        runs = conn.execute(text(
            "SELECT status, rows_read FROM audit.pipeline_runs ORDER BY run_id"
        )).all()
    assert runs == [("success", 5), ("success", 5)]


def test_failed_run_rolls_back_and_is_audited(engine):
    bad = _sample()
    bad.loc[4, "StockCode"] = "X" * 30  # ผ่าน validate แต่ COPY ล้ม (VARCHAR(20))
    with pytest.raises(psycopg2.DataError):
        load_raw(bad, engine, SOURCE)

    assert _count(engine) == 0  # ไม่มีแถวไหนเข้าไปครึ่ง ๆ กลาง ๆ
    with engine.connect() as conn:
        status, err = conn.execute(text(
            "SELECT status, error_message FROM audit.pipeline_runs"
        )).one()
    assert status == "failed" and err


def test_rejected_rows_are_audited_not_loaded(engine):
    df = pd.concat([_sample()] * 5, ignore_index=True)  # 25 แถว
    df["InvoiceNo"] = [f"{i // 5}{v}" for i, v in enumerate(df["InvoiceNo"])]
    df.loc[0, "UnitPrice"] = 0  # 1/25 = 4% < 5%

    result = load_raw(df, engine, SOURCE)

    assert result["rows_rejected"] == 1 and result["rows_loaded"] == 24
    assert _count(engine) == 24
    with engine.connect() as conn:
        reason, rejected_in_run = conn.execute(text("""
            SELECT r.reason, p.rows_rejected
            FROM audit.rejected_rows r JOIN audit.pipeline_runs p USING (run_id)
        """)).one()
    assert reason == "unit_price <= 0" and rejected_in_run == 1


def test_circuit_breaker_blocks_whole_batch(engine):
    df = _sample()
    df.loc[[0, 1], "UnitPrice"] = 0  # 2/5 = 40%

    with pytest.raises(CircuitBreakerError):
        load_raw(df, engine, SOURCE)

    assert _count(engine) == 0
    assert _count(engine, "audit.rejected_rows") == 2
    with engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM audit.pipeline_runs")).scalar_one()
    assert status == "failed"


def test_row_that_becomes_invalid_is_removed(engine):
    load_raw(_sample(), engine, SOURCE)

    # รอบสอง: แถว 536380-1 ที่เคยโหลดแล้วกลายเป็นราคา 0 (1 ใน 25 แถว = 4%)
    df = pd.concat([_sample()] + [_sample().assign(InvoiceNo=f"9{i}") for i in range(4)],
                   ignore_index=True)
    df.loc[4, "UnitPrice"] = 0
    load_raw(df, engine, SOURCE)

    with engine.connect() as conn:
        remaining = conn.execute(text(
            "SELECT count(*) FROM raw.online_retail WHERE line_id = '536380-1'"
        )).scalar()
    assert remaining == 0
