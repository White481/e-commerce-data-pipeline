"""Daily e-commerce pipeline: setup → ingest → transform → notify

ทุก task เรียกคำสั่งเดียวกับที่ใช้รันมือ ผ่าน venv แยกของ pipeline:
ingest = python -m ingest.run, transform = dbt build (fact_sales แทนที่เฉพาะวันนั้น)
แต่ละ task idempotent จึง retry / clear / backfill ซ้ำได้โดยข้อมูลไม่ซ้ำ

Airflow 3.3: DAG มาจาก airflow.sdk, BashOperator ย้ายไป providers.standard
"""

from datetime import datetime, timedelta, timezone

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, Param
from airflow.timetables.interval import CronDataIntervalTimetable

PYTHON = "/opt/pipeline-venv/bin/python -m ingest.run"
DBT = "/opt/pipeline-venv/bin/dbt"
PROJECT_DIR = "/opt/project"

with DAG(
    dag_id="ecommerce_daily",
    description="Load one day of Online Retail data into raw, then build the mart",
    # data interval แบบเดิม: run ของ logical date 2011-01-05 = ข้อมูลวันที่ 2011-01-05
    schedule=CronDataIntervalTimetable("@daily", timezone="UTC"),
    start_date=datetime(2010, 12, 1, tzinfo=timezone.utc),
    end_date=datetime(2011, 12, 9, tzinfo=timezone.utc),
    catchup=True,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(seconds=30),
        "cwd": PROJECT_DIR,
    },
    params={
        # override เฉพาะวันที่คนตรวจแล้ว: trigger พร้อม conf {"max_reject_rate": 0.25}
        "max_reject_rate": Param(0.05, type="number", minimum=0, maximum=1),
    },
    tags=["ecommerce"],
) as dag:
    setup = BashOperator(task_id="setup", bash_command=f"{PYTHON} init")

    ingest = BashOperator(
        task_id="ingest",
        # วันที่ไม่มีไฟล์ CLI บันทึก skipped แล้ว exit 0 → DAG ไม่แดง
        bash_command=(
            f"{PYTHON} load --date {{{{ ds }}}} "
            "--max-reject-rate {{ params.max_reject_rate }}"
        ),
    )

    transform = BashOperator(
        task_id="transform",
        bash_command=(
            f"{DBT} build --project-dir dbt_project --profiles-dir dbt_project "
            """--vars '{"run_date": "{{ ds }}"}'"""
        ),
    )

    notify = BashOperator(task_id="notify", bash_command=f"{PYTHON} notify --date {{{{ ds }}}}")

    setup >> ingest >> transform >> notify
