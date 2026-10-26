"""สร้าง role metabase_ro สำหรับ BI (Metabase): อ่านได้เฉพาะ schema marts เท่านั้น

    python -m ingest.roles      (รหัสผ่านจาก METABASE_RO_PASSWORD ใน .env)

รันซ้ำได้: สร้าง role ถ้ายังไม่มี และตั้งสิทธิ์ใหม่ทุกครั้ง
ไม่ใช้ชื่อ analyst_ro เพราะชื่อนั้นเป็นของ Text-to-SQL agent อยู่แล้ว (role ใช้ร่วมกันทั้ง server)
"""

from psycopg2 import sql
from sqlalchemy.engine import Engine

from ingest.db import _require, get_engine

ROLE = "metabase_ro"
SCHEMA = "marts"


def setup_readonly_role(engine: Engine, password: str, role_name: str = ROLE) -> None:
    role, schema = sql.Identifier(role_name), sql.Identifier(SCHEMA)
    with engine.begin() as conn:
        cursor = conn.connection.cursor()
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role_name,))
        if cursor.fetchone() is None:
            cursor.execute(sql.SQL("CREATE ROLE {} LOGIN").format(role))
        cursor.execute(
            sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(role, sql.Literal(password))
        )
        cursor.execute("SELECT current_database(), current_user")
        database, owner = cursor.fetchone()
        statements = [
            "GRANT CONNECT ON DATABASE {db} TO {role}",
            "CREATE SCHEMA IF NOT EXISTS {schema}",
            "GRANT USAGE ON SCHEMA {schema} TO {role}",
            "GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {role}",
            # dbt สร้างตารางใหม่ทุกครั้งที่ build: ตารางใหม่ของ owner ต้องได้ SELECT อัตโนมัติด้วย
            "ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA {schema} GRANT SELECT ON TABLES TO {role}",
        ]
        for statement in statements:
            cursor.execute(sql.SQL(statement).format(
                db=sql.Identifier(database), role=role, schema=schema, owner=sql.Identifier(owner),
            ))
        # schema อื่นที่มีข้อมูลดิบ / audit / staging: ไม่ให้สิทธิ์ใด ๆ
        cursor.execute(
            "SELECT nspname FROM pg_namespace WHERE nspname IN ('raw', 'audit', 'staging')"
        )
        for (other,) in cursor.fetchall():
            cursor.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM {}").format(
                sql.Identifier(other), role,
            ))


def main() -> None:
    setup_readonly_role(get_engine(), _require("METABASE_RO_PASSWORD"))
    print(f"role {ROLE}: SELECT on schema {SCHEMA} only")


if __name__ == "__main__":
    main()
