"""Landing zone: Parquet partition รายวัน ใช้โค้ดชุดเดียวทั้ง path ในเครื่องและ S3"""

import os
import uuid
from datetime import date

import pandas as pd
import pytest

from ingest.landing import day_uri, list_days, read_day, write_day

DAY = date(2010, 12, 1)


def _rows():
    return pd.DataFrame({
        "InvoiceNo": ["536365", "C536379"],
        "StockCode": ["85123A", "D"],
        "Description": ["HEART T-LIGHT", None],
        "Quantity": [6, -1],
        "InvoiceDate": pd.to_datetime(["2010-12-01 08:26", "2010-12-01 09:41"]),
        "UnitPrice": [2.55, 27.5],
        "CustomerID": [17850.0, None],
        "Country": ["United Kingdom", "United Kingdom"],
    })


def _roundtrip(uri):
    write_day(_rows(), DAY, uri)
    back = read_day(DAY, uri)
    pd.testing.assert_frame_equal(back, _rows(), check_dtype=False)
    # ชนิดข้อมูลที่ CSV เคยทำหาย ต้องรอดมาครบ
    assert pd.api.types.is_datetime64_any_dtype(back["InvoiceDate"])
    assert back["InvoiceNo"].tolist() == ["536365", "C536379"]
    assert list_days(uri) == [DAY]


def test_local_roundtrip_keeps_types(tmp_path):
    _roundtrip(str(tmp_path))
    assert (tmp_path / "date=2010-12-01" / "part-0.parquet").exists()


def test_missing_day_and_empty_landing(tmp_path):
    assert read_day(DAY, str(tmp_path)) is None
    assert list_days(str(tmp_path / "nothing-here")) == []


def test_read_only_needed_columns(tmp_path):
    write_day(_rows(), DAY, str(tmp_path))
    df = read_day(DAY, str(tmp_path), columns=["InvoiceNo", "UnitPrice"])
    assert list(df.columns) == ["InvoiceNo", "UnitPrice"]


def test_day_uri_is_hive_style_partition():
    assert day_uri(DAY, "s3://lake/landing") == "s3://lake/landing/date=2010-12-01/part-0.parquet"


@pytest.mark.skipif(not os.getenv("S3_ENDPOINT_URL"), reason="S3 endpoint not configured (make lake-up)")
def test_s3_roundtrip():
    bucket = os.getenv("S3_TEST_BUCKET", "ecommerce-lake")
    _roundtrip(f"s3://{bucket}/test-{uuid.uuid4().hex[:8]}/landing")
