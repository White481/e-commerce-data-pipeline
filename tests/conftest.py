"""Fixture สำหรับ integration test: ใช้ database แยก <POSTGRES_DB>_test เพื่อไม่แตะข้อมูลจริง"""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from ingest.db import get_engine
from ingest.load_raw import init_db


def truncate(engine):
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "TRUNCATE raw.online_retail, audit.rejected_rows, audit.pipeline_runs RESTART IDENTITY"
        )


@pytest.fixture(scope="session")
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
        # ในเครื่องยอมให้ skip ได้ แต่ใน CI (GitHub ตั้ง CI=true) ต้องล้ม ไม่งั้นเทสต์ DB จะหายเงียบ
        if os.getenv("CI"):
            pytest.fail("Postgres is not reachable in CI")
        pytest.skip("Postgres is not running (make up)")
    finally:
        admin.dispose()

    eng = get_engine(database=test_db)
    init_db(eng)
    yield eng
    eng.dispose()
