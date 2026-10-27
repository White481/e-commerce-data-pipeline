.PHONY: up down psql init-db create-tables clean-data load load-raw split load-day load-since-last airflow-up backfill dbt-build dbt-docs roles metabase-up metabase-setup lake-up test lint

up:
	docker compose up -d

down:
	docker compose down

psql:
	docker compose exec postgres sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB'

init-db:
	docker compose exec -T postgres sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB -v ON_ERROR_STOP=1' < sql/init.sql

create-tables:
	docker compose exec -T postgres sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB' < models/create_tables.sql

clean-data:
	python -m ingest.clean_data

load:
	python -m ingest.load_to_postgres

load-raw:
	python -m ingest.load_raw

split:
	python -m ingest.split_batches

load-day:  # make load-day DATE=2011-01-05
	python -m ingest.run load --date $(DATE)

load-since-last:
	python -m ingest.run load --since-last

airflow-up:  # UI: http://localhost:8080
	docker compose up -d --build airflow

backfill:  # make backfill FROM=2011-01-01 TO=2011-01-31 (DAG ต้อง unpause ก่อน run ถึงจะเริ่ม)
	docker compose exec airflow airflow backfill create --dag-id ecommerce_daily \
		--from-date $(FROM) --to-date $(TO) --max-active-runs 1

# dbt ไม่อ่าน .env เอง จึงโหลดเข้า env ก่อน
DBT = set -a && . ./.env && set +a && dbt

dbt-build:
	$(DBT) build --project-dir dbt_project --profiles-dir dbt_project

dbt-docs:  # http://localhost:8081
	$(DBT) docs generate --project-dir dbt_project --profiles-dir dbt_project
	$(DBT) docs serve --project-dir dbt_project --profiles-dir dbt_project --port 8081

roles:  # metabase_ro: SELECT on marts only
	python -m ingest.roles

metabase-up:  # http://localhost:3000
	docker compose up -d metabase

metabase-setup:  # admin + database + 5 charts + dashboard (re-runnable)
	python -m metabase.setup_dashboard

lake-up:  # S3 API http://localhost:9000, console http://localhost:9001/rustfs/console/
	docker compose up -d lake

test:
	pytest -q

lint:
	ruff check .
