.PHONY: up down psql init-db create-tables clean-data load load-raw test lint

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

test:
	pytest -q

lint:
	ruff check .
