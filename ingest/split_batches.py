"""แบ่งไฟล์ต้นฉบับเป็นไฟล์รายวันใน data/landing/ เพื่อจำลองข้อมูลที่มาส่งทีละวัน

ไฟล์รายวันเก็บคอลัมน์และลำดับแถวเหมือนต้นฉบับ (line_id ขึ้นกับลำดับแถว)
"""

from pathlib import Path

import pandas as pd

SOURCE_FILE = "data/Online Retail.xlsx"
LANDING_DIR = Path("data/landing")


def split(df: pd.DataFrame, landing_dir: Path = LANDING_DIR) -> list[Path]:
    landing_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for day, rows in df.groupby(df["InvoiceDate"].dt.date, sort=True):
        path = landing_dir / f"{day:%Y-%m-%d}.csv"
        rows.to_csv(path, index=False)
        paths.append(path)
    return paths


def main() -> None:
    df = pd.read_excel(SOURCE_FILE, dtype={"InvoiceNo": str, "StockCode": str})
    paths = split(df)
    print(f"เขียน {len(paths)} ไฟล์ลง {LANDING_DIR}/ ({paths[0].stem} ถึง {paths[-1].stem})")


if __name__ == "__main__":
    main()
