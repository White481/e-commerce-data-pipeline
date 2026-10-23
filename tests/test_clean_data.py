import pandas as pd

from ingest.clean_data import clean


def _raw():
    return pd.DataFrame(
        {
            "InvoiceNo": ["1", "2", "3", "4"],
            "Description": ["A", "B", None, "D"],
            "Quantity": [2, -1, 5, 3],
            "UnitPrice": [1.5, 2.0, 1.0, 4.0],
            "CustomerID": [17850.0, 13047.0, 12583.0, None],
        }
    )


def test_drops_missing_customer_and_description():
    df = clean(_raw())
    assert df["InvoiceNo"].tolist() == ["1", "2"]


def test_customer_id_is_int():
    df = clean(_raw())
    assert pd.api.types.is_integer_dtype(df["CustomerID"])
    assert df["CustomerID"].tolist() == [17850, 13047]


def test_is_return_and_total_amount():
    df = clean(_raw())
    assert df["is_return"].tolist() == [False, True]
    assert df["total_amount"].tolist() == [3.0, -2.0]
