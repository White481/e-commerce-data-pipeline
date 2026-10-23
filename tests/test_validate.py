import pandas as pd
import pytest

from ingest.validate import CircuitBreakerError, check_reject_rate, validate


def _rows(**overrides):
    df = pd.DataFrame({
        "line_id": ["536365-1", "536365-2", "C536379-1"],
        "invoice_no": ["536365", "536365", "C536379"],
        "stock_code": ["85123A", "71053", "D"],
        "quantity": [6, 6, -1],
        "invoice_date": pd.to_datetime(["2010-12-01 08:26", "2010-12-01 08:26", "2010-12-01 09:41"]),
        "unit_price": [2.55, 3.39, 27.5],
    })
    for column, (idx, value) in overrides.items():
        if column == "invoice_date":
            df[column] = df[column].astype(object)
        df.loc[idx, column] = value
    return df


def test_clean_rows_pass():
    good, bad = validate(_rows())
    assert len(good) == 3 and bad.empty


@pytest.mark.parametrize("price", [0, -11062.06])
def test_price_not_positive_is_rejected(price):
    good, bad = validate(_rows(unit_price=(1, price)))
    assert bad["line_id"].tolist() == ["536365-2"]
    assert bad["reason"].iloc[0] == "unit_price <= 0"
    assert len(good) == 2


def test_cancelled_invoice_with_positive_quantity_is_rejected():
    _, bad = validate(_rows(quantity=(2, 1)))
    assert bad["line_id"].tolist() == ["C536379-1"]
    assert "cancelled invoice" in bad["reason"].iloc[0]


def test_missing_invoice_date_is_rejected():
    _, bad = validate(_rows(invoice_date=(0, None)))
    assert bad["line_id"].tolist() == ["536365-1"]
    assert bad["reason"].iloc[0] == "invoice_date is null"


def test_duplicate_line_id_rejects_every_copy():
    good, bad = validate(_rows(line_id=(1, "536365-1")))
    assert sorted(bad["line_id"]) == ["536365-1", "536365-1"]
    assert set(bad["reason"]) == {"duplicate line_id"}
    assert good["line_id"].tolist() == ["C536379-1"]


def test_multiple_reasons_are_joined():
    df = _rows(unit_price=(2, 0), quantity=(2, 1))
    _, bad = validate(df)
    assert len(bad) == 1
    assert set(bad["reason"].iloc[0].split("; ")) == {
        "unit_price <= 0", "cancelled invoice (C...) with positive quantity",
    }


def test_malformed_batch_raises():
    df = _rows()
    df["quantity"] = pd.Series([6, "oops", -1], dtype=object)
    with pytest.raises(ValueError, match="batch failed schema checks"):
        validate(df)


def test_circuit_breaker():
    check_reject_rate(100, 5)  # 5% พอดี ยังผ่าน
    with pytest.raises(CircuitBreakerError):
        check_reject_rate(100, 6)
