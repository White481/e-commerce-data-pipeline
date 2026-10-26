"""Incremental loading: ไฟล์รายวันใน landing dir ชั่วคราว + DB test"""

from datetime import date

import pandas as pd
import pytest
from sqlalchemy import text

from ingest.run import load_day, load_since_last, notify, watermark
from ingest.split_batches import split
from ingest.validate import CircuitBreakerError
from tests.conftest import truncate

DAYS = [date(2010, 12, d) for d in (1, 2, 3, 5, 6)]  # ไม่มีวันที่ 4 (วันหยุด)


@pytest.fixture(autouse=True)
def clean_tables(engine):
    truncate(engine)


@pytest.fixture
def landing(tmp_path):
    rows = []
    for i, day in enumerate(DAYS):
        for line in range(3):
            rows.append({
                "InvoiceNo": f"5{i:05d}", "StockCode": f"S{line}", "Description": "ITEM",
                "Quantity": 2, "InvoiceDate": pd.Timestamp(day) + pd.Timedelta(hours=9 + line),
                "UnitPrice": 1.5, "CustomerID": 17850.0, "Country": "United Kingdom",
            })
    split(pd.DataFrame(rows), tmp_path)
    return tmp_path


def _count(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM raw.online_retail")).scalar()


def _statuses(engine):
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT batch_date, status FROM audit.pipeline_runs ORDER BY run_id"
        )).all()


def test_split_writes_one_file_per_day(landing):
    assert sorted(p.stem for p in landing.glob("*.csv")) == [f"{d:%Y-%m-%d}" for d in DAYS]


def test_load_five_days_twice_keeps_count(engine, landing):
    for _ in range(2):
        for day in DAYS:
            load_day(engine, day, landing)
    assert _count(engine) == 15


def test_missing_day_is_skipped_not_error(engine, landing):
    result = load_day(engine, date(2010, 12, 4), landing)
    assert result["status"] == "skipped"
    assert _statuses(engine) == [(date(2010, 12, 4), "skipped")]


def test_since_last_catches_up_after_deleting_last_three_days(engine, landing):
    load_since_last(engine, landing)
    assert _count(engine) == 15 and watermark(engine) == date(2010, 12, 6)

    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM raw.online_retail WHERE invoice_date >= '2010-12-03'")
    assert _count(engine) == 6 and watermark(engine) == date(2010, 12, 2)

    results = load_since_last(engine, landing)
    assert _count(engine) == 15
    # เริ่มที่วัน watermark (2 ธ.ค.) ซ้ำอีกรอบ แล้วไล่ไปถึงวันล่าสุด วันที่ 4 ไม่มีไฟล์
    assert [r["status"] for r in results] == ["success", "success", "skipped", "success", "success"]
    assert results[0]["rows_inserted"] == 0


def test_since_last_on_empty_db_starts_at_first_file(engine, landing):
    results = load_since_last(engine, landing)
    assert len(results) == 6  # 1–6 ธ.ค. รวมวันที่ 4 ที่ skipped
    assert _count(engine) == 15


def test_day_file_replaces_that_day(engine, landing):
    load_day(engine, DAYS[0], landing)
    path = landing / "2010-12-01.csv"
    df = pd.read_csv(path)
    df.iloc[:2].to_csv(path, index=False)  # ต้นทางแก้ไฟล์ เหลือ 2 บรรทัด

    load_day(engine, DAYS[0], landing)
    assert _count(engine) == 2


def test_reviewed_override_lets_high_reject_day_through(engine, landing):
    path = landing / "2010-12-01.csv"
    df = pd.read_csv(path)
    df.loc[0, "UnitPrice"] = 0  # 1/3 = 33%
    df.to_csv(path, index=False)

    with pytest.raises(CircuitBreakerError):
        load_day(engine, DAYS[0], landing)

    load_day(engine, DAYS[0], landing, max_reject_rate=0.5)
    assert _count(engine) == 2
    with engine.connect() as conn:
        runs = conn.execute(text(
            "SELECT status, max_reject_rate FROM audit.pipeline_runs ORDER BY run_id"
        )).all()
    assert [(s, float(r)) for s, r in runs] == [("failed", 0.05), ("success", 0.5)]


def test_approved_override_is_remembered_on_reload(engine, landing):
    path = landing / "2010-12-06.csv"
    df = pd.read_csv(path)
    df.loc[0, "UnitPrice"] = 0
    df.to_csv(path, index=False)

    with pytest.raises(CircuitBreakerError):
        load_since_last(engine, landing)  # breaker ตัดที่ 6 ธ.ค.
    load_day(engine, DAYS[-1], landing, max_reject_rate=0.5)  # คนตรวจแล้ว อนุมัติ

    # since-last โหลดวัน watermark (6 ธ.ค.) ซ้ำ ต้องไม่ติด breaker อีก
    results = load_since_last(engine, landing)
    assert [r["status"] for r in results] == ["success"]


def test_since_last_fills_gap_left_by_out_of_order_load(engine, landing):
    load_day(engine, DAYS[0], landing)
    load_day(engine, DAYS[-1], landing)  # ข้ามไปโหลดวันสุดท้ายก่อน watermark จึงกระโดด
    assert watermark(engine) == DAYS[-1]

    load_since_last(engine, landing)
    assert _count(engine) == 15


def test_notify_summarises_day(engine, landing):
    load_day(engine, DAYS[0], landing)
    message = notify(engine, DAYS[0])
    assert "load=success" in message and "อ่าน 3" in message
