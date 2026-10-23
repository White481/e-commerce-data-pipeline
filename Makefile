.PHONY: up down psql init-db create-tables clean-data load load-raw split load-day load-since-last airflow-up backfill test lint

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

test:
	pytest -q

lint:
	ruff check .
