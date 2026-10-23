"""สร้าง database 'airflow' ใน Postgres ตัวเดียวกันถ้ายังไม่มี (รันก่อน airflow standalone)"""

import os

import psycopg2

conn = psycopg2.connect(
    host="postgres",
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
    dbname=os.environ["POSTGRES_DB"],
)
conn.autocommit = True
with conn.cursor() as cur:
    cur.execute("SELECT 1 FROM pg_database WHERE datname = 'airflow'")
    if cur.fetchone() is None:
        cur.execute("CREATE DATABASE airflow")
        print("created database airflow")
conn.close()
