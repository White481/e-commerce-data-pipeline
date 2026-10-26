"""Integration test: ต้องมี Postgres รันอยู่ (make up) ไม่งั้นจะ skip

ใช้ database แยก <POSTGRES_DB>_test เพื่อไม่ให้แตะข้อมูลจริง
"""

import os

import pandas as pd
import psycopg2
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from ingest.db import get_engine
from ingest.load_raw import init_db, load_raw

SOURCE = "test.xlsx"


@pytest.fixture(scope="module")
def engine():
    test_db = f"{os.getenv('POSTGRES_DB', 'ecommerce')}_test"
    admin = get_engine(database="postgres").execution_options(isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": test_db}
            ).scalar()
            if not exists:
                conn.exec_driver_sql(f'CREATE DATABASE "{test_db}"')
    except OperationalError:
        pytest.skip("Postgres is not running (make up)")
    finally:
        admin.dispose()

    eng = get_engine(database=test_db)
    init_db(eng)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def clean_tables(engine):
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "TRUNCATE raw.online_retail, audit.rejected_rows, audit.pipeline_runs RESTART IDENTITY"
        )


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
    bad["Quantity"] = bad["Quantity"].astype(object)
    bad.loc[4, "Quantity"] = "not-a-number"  # COPY จะล้มเพราะ quantity เป็น INT
    with pytest.raises(psycopg2.DataError):
        load_raw(bad, engine, SOURCE)

    assert _count(engine) == 0  # ไม่มีแถวไหนเข้าไปครึ่ง ๆ กลาง ๆ
    with engine.connect() as conn:
        status, err = conn.execute(text(
            "SELECT status, error_message FROM audit.pipeline_runs"
        )).one()
    assert status == "failed" and err
