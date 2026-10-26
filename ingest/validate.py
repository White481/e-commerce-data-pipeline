"""Data quality rules สำหรับข้อมูลก่อนเข้า raw.online_retail

แถวที่ผิดกฎจะถูกแยกออกพร้อมเหตุผล ไม่ได้ถูกทิ้งเงียบ ๆ
CustomerID ว่างไม่ถือว่าผิด (guest checkout ~25%) ไปกรองทีหลังตอนทำ fact
"""

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

MAX_REJECT_RATE = 0.05


class CircuitBreakerError(Exception):
    """แถวเสียเกินเพดาน: ข้อมูลทั้ง batch น่าจะมีปัญหา ไม่ควรโหลด"""


SCHEMA = pa.DataFrameSchema(
    {
        "line_id": pa.Column(str, unique=True, report_duplicates="all"),
        "invoice_no": pa.Column(str),
        "stock_code": pa.Column(str),
        "quantity": pa.Column(nullable=False),
        "invoice_date": pa.Column(nullable=False),
        "unit_price": pa.Column(checks=pa.Check.gt(0, error="unit_price <= 0")),
    },
    checks=[
        pa.Check(
            lambda df: ~(df["invoice_no"].str.startswith("C") & (df["quantity"] > 0)),
            error="cancelled invoice (C...) with positive quantity",
        ),
    ],
    coerce=False,
)


def _reason(row: pd.Series) -> str:
    check = str(row["check"])
    column = row["column"]
    if check == "not_nullable":
        return f"{column} is null"
    if check == "field_uniqueness":
        return f"duplicate {column}"
    return check


def validate(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """คืน (แถวดี, แถวเสีย) โดยแถวเสียมีคอลัมน์ reason เพิ่ม"""
    try:
        SCHEMA.validate(df, lazy=True)
        return df, df.iloc[0:0].assign(reason=pd.Series(dtype=str))
    except SchemaErrors as exc:
        cases = exc.failure_cases

    # failure ที่ไม่ผูกกับแถวไหน (เช่น check พังเพราะ dtype ผิด) แปลว่าทั้ง batch ผิดรูป
    if cases["index"].isna().any():
        broken = cases[cases["index"].isna()][["column", "check"]].to_dict("records")
        raise ValueError(f"batch failed schema checks: {broken}")

    reasons = (
        cases.assign(reason=cases.apply(_reason, axis=1))
        .drop_duplicates(subset=["index", "reason"])
        .groupby("index")["reason"]
        .agg("; ".join)
    )
    bad_mask = df.index.isin(reasons.index)
    bad = df[bad_mask].assign(reason=reasons)
    return df[~bad_mask], bad


def check_reject_rate(
    rows_read: int, rows_rejected: int, max_rate: float = MAX_REJECT_RATE
) -> None:
    if rows_read and rows_rejected / rows_read > max_rate:
        raise CircuitBreakerError(
            f"rejected {rows_rejected}/{rows_read} rows "
            f"({rows_rejected / rows_read:.1%}) > {max_rate:.0%}"
        )
