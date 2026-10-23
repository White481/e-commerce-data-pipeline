from datetime import date

import pandas as pd
import pytest
from sqlalchemy import text

from ingest import run
from ingest.run import load_day, notify, transform_day
from ingest.split_batches import split
from tests.conftest import truncate

DAY = date(2010, 12, 1)


@pytest.fixture(autouse=True)
def clean_tables(engine):
    truncate(engine)


@pytest.fixture
def loaded(engine, tmp_path):
    df = pd.DataFrame({
        "InvoiceNo": ["536365", "536365", "536366", "C536379"],
        "StockCode": ["85123A", "71053", "85123A", "D"],
        "Description": ["HEART T-LIGHT", "LANTERN", "HEART T-LIGHT", "Discount"],
        "Quantity": [6, 6, 2, -1],
        "InvoiceDate": pd.to_datetime(["2010-12-01 08:26"] * 2 + ["2010-12-01 09:00", "2010-12-01 09:41"]),
        "UnitPrice": [2.55, 3.39, 2.55, 27.5],
        "CustomerID": [17850.0, 17850.0, None, 14527.0],  # 536366 ไม่มีลูกค้า
        "Country": ["United Kingdom"] * 4,
    })
    split(df, tmp_path)
    load_day(engine, DAY, tmp_path)
    return engine


def _counts(engine):
    with engine.connect() as conn:
        return conn.execute(text("""
            SELECT (SELECT count(*) FROM mart.fact_sales),
                   (SELECT count(*) FROM mart.dim_product),
                   (SELECT count(*) FROM mart.dim_customer),
                   (SELECT count(*) FROM mart.dim_date)
        """)).one()


def test_transform_twice_keeps_counts(loaded):
    transform_day(loaded, DAY)
    first = _counts(loaded)
    transform_day(loaded, DAY)
    assert _counts(loaded) == first == (3, 3, 2, 1)


def test_fact_excludes_rows_without_customer_and_flags_returns(loaded):
    transform_day(loaded, DAY)
    with loaded.connect() as conn:
        rows = dict(conn.execute(text("SELECT line_id, is_return FROM mart.fact_sales")).all())
    assert rows == {"536365-1": False, "536365-2": False, "C536379-1": True}


def test_injected_failure_rolls_back(loaded, tmp_path, monkeypatch):
    transform_day(loaded, DAY)
    monkeypatch.setattr(run, "FAIL_FLAG_DIR", tmp_path)
    flag = run.fail_flag(DAY)
    flag.touch()

    with pytest.raises(RuntimeError, match="injected failure"):
        transform_day(loaded, DAY)
    assert _counts(loaded)[0] == 3  # DELETE ของวันนั้นถูก rollback ไม่หาย

    flag.unlink()
    transform_day(loaded, DAY)
    assert _counts(loaded)[0] == 3


def test_notify_summarises_day(loaded):
    transform_day(loaded, DAY)
    message = notify(loaded, DAY)
    assert "load=success" in message and "fact 3 แถว" in message
