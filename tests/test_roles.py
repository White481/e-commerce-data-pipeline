"""role อ่านอย่างเดียวอ่าน marts ได้ แต่อ่าน raw ไม่ได้ และเขียนอะไรไม่ได้เลย

role อยู่ระดับ server (ใช้ร่วมทุก database) จึงใช้ชื่อเฉพาะของเทสต์แล้วลบทิ้งหลังจบ
ห้ามใช้ชื่อ role จริง ไม่งั้นเทสต์จะไปเปลี่ยนรหัสผ่านของ role ที่ระบบอื่นใช้อยู่
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

from ingest.roles import setup_readonly_role

TEST_ROLE = "test_marts_ro"
PASSWORD = "test-ro-password"


@pytest.fixture
def ro_engine(engine):
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS marts")
        conn.exec_driver_sql("DROP TABLE IF EXISTS marts.before_setup, marts.after_setup")
        conn.exec_driver_sql("CREATE TABLE marts.before_setup AS SELECT 1 AS x")
    setup_readonly_role(engine, PASSWORD, TEST_ROLE)
    with engine.begin() as conn:
        # ตารางที่สร้างหลังตั้งสิทธิ์ (เหมือน dbt build รอบถัดไป) ต้องอ่านได้ด้วย
        conn.exec_driver_sql("CREATE TABLE marts.after_setup AS SELECT 2 AS x")
    ro = create_engine(engine.url.set(username=TEST_ROLE, password=PASSWORD))
    yield ro
    ro.dispose()
    with engine.begin() as conn:
        conn.exec_driver_sql(f"DROP OWNED BY {TEST_ROLE}")
        conn.exec_driver_sql(f"DROP ROLE {TEST_ROLE}")


def test_can_select_marts_including_new_tables(ro_engine):
    with ro_engine.connect() as conn:
        assert conn.execute(text("SELECT x FROM marts.before_setup")).scalar() == 1
        assert conn.execute(text("SELECT x FROM marts.after_setup")).scalar() == 2


def test_cannot_read_raw(ro_engine):
    with ro_engine.connect() as conn, pytest.raises(ProgrammingError, match="permission denied"):
        conn.execute(text("SELECT count(*) FROM raw.online_retail"))


def test_cannot_write_marts(ro_engine):
    with ro_engine.connect() as conn, pytest.raises(ProgrammingError, match="permission denied"):
        conn.execute(text("INSERT INTO marts.before_setup VALUES (3)"))


def test_setup_is_rerunnable(engine, ro_engine):
    setup_readonly_role(engine, PASSWORD, TEST_ROLE)
    with ro_engine.connect() as conn:
        assert conn.execute(text("SELECT x FROM marts.before_setup")).scalar() == 1
