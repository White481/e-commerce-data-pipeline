.PHONY: up down psql create-tables clean-data load test lint

up:
	docker compose up -d

down:
	docker compose down

psql:
	docker compose exec postgres sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB'

create-tables:
	docker compose exec -T postgres sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB' < models/create_tables.sql

clean-data:
	python -m ingest.clean_data

load:
	python -m ingest.load_to_postgres

test:
	pytest -q

lint:
	ruff check .
