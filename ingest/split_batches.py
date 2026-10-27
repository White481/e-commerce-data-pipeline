"""แบ่งไฟล์ต้นฉบับเป็น Parquet รายวันใน landing zone เพื่อจำลองข้อมูลที่มาส่งทีละวัน

    python -m ingest.split_batches      (ปลายทางจาก LANDING_URI: data/landing หรือ s3://...)

ไฟล์รายวันเก็บคอลัมน์และลำดับแถวเหมือนต้นฉบับ (line_id ขึ้นกับลำดับแถว)
"""

import pandas as pd

from ingest.landing import landing_uri, write_day

SOURCE_FILE = "data/Online Retail.xlsx"


def split(df: pd.DataFrame, uri: str | None = None) -> list[str]:
    return [
        write_day(rows, day, uri)
        for day, rows in df.groupby(df["InvoiceDate"].dt.date, sort=True)
    ]


def main() -> None:
    # ข้อความทุกคอลัมน์ต้องเป็น str: Parquet เก็บชนิดเดียวต่อคอลัมน์ (Description บางแถวเป็นตัวเลข)
    text = {c: str for c in ("InvoiceNo", "StockCode", "Description", "Country")}
    df = pd.read_excel(SOURCE_FILE, dtype=text)
    written = split(df)
    print(f"เขียน {len(written)} partition ลง {landing_uri()}/ ({written[0]} ... {written[-1]})")


if __name__ == "__main__":
    main()
