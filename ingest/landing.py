"""Landing zone (bronze): ไฟล์ Parquet แบ่ง partition ตามวัน

    <LANDING_URI>/date=YYYY-MM-DD/part-0.parquet

LANDING_URI เป็นได้ทั้ง path ในเครื่อง (data/landing) หรือ s3://bucket/landing
fsspec ทำให้โค้ดชุดเดียวใช้ได้ทั้งสองแบบ: ย้ายไป AWS S3 จริงแค่เปลี่ยน env
S3_ENDPOINT_URL ใช้เมื่อเป็น S3-compatible ในเครื่อง (RustFS); บน AWS ไม่ต้องตั้ง
credential อ่านจาก AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY ตามมาตรฐาน AWS
"""

import os
import re
from datetime import date

import fsspec
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DEFAULT_URI = "data/landing"
PART = "part-0.parquet"
PARTITION = re.compile(r"date=(\d{4}-\d{2}-\d{2})")


def landing_uri() -> str:
    return os.getenv("LANDING_URI", DEFAULT_URI)


def _fs(uri: str | None):
    uri = uri or landing_uri()
    options = {}
    if uri.startswith("s3://") and os.getenv("S3_ENDPOINT_URL"):
        options["client_kwargs"] = {"endpoint_url": os.environ["S3_ENDPOINT_URL"]}
    fs, root = fsspec.core.url_to_fs(uri, **options)
    return fs, root.rstrip("/")


def _part(root: str, day: date) -> str:
    return f"{root}/date={day:%Y-%m-%d}/{PART}"


def day_uri(day: date, uri: str | None = None) -> str:
    """ที่อยู่เต็มของไฟล์วันนั้น ใช้บันทึกเป็น source_file"""
    return _part((uri or landing_uri()).rstrip("/"), day)


def write_day(df: pd.DataFrame, day: date, uri: str | None = None) -> str:
    fs, root = _fs(uri)
    path = _part(root, day)
    fs.makedirs(path.rsplit("/", 1)[0], exist_ok=True)
    with fs.open(path, "wb") as f:
        df.to_parquet(f, index=False)
    return day_uri(day, uri)


def read_day(day: date, uri: str | None = None, columns: list[str] | None = None):
    """คืน DataFrame ของวันนั้น หรือ None ถ้าวันนั้นไม่มีไฟล์

    columns: อ่านเฉพาะบางคอลัมน์ได้ (Parquet เป็น columnar จึงไม่ต้องอ่านทั้งไฟล์)
    """
    fs, root = _fs(uri)
    path = _part(root, day)
    if not fs.exists(path):
        return None
    with fs.open(path, "rb") as f:
        return pd.read_parquet(f, columns=columns)


def list_days(uri: str | None = None) -> list[date]:
    fs, root = _fs(uri)
    if not fs.exists(root):
        return []
    days = (PARTITION.search(p) for p in fs.glob(f"{root}/date=*/{PART}"))
    return sorted(date.fromisoformat(m.group(1)) for m in days if m)
