
**Stack:** Python, pandas, PostgreSQL 16, Docker, SQLAlchemy, SQL

## Data Model (Star Schema)

- `fact_sales` — central table storing every transaction
- `dim_customer` — customer info + country
- `dim_product` — product details
- `dim_date` — calendar table, broken down by year/month/day/weekday

A star schema was chosen because it's the standard data warehouse pattern 
that makes business analysis queries (revenue, top products) fast and easy to read.

## Data Quality Decisions

While cleansing the data, I found two issues that required a deliberate decision on how to handle them:

1. **CustomerID missing in ~25% of rows** — decided to drop these rows, since per-customer 
   analysis isn't possible without knowing who made the purchase. Hypothesis: the point-of-sale 
   system may allow guest checkout without requiring login.
2. **Negative Quantity values (~10,600 rows)** — not an error, but **product returns**. 
   Kept these rows and added an `is_return` flag column instead of discarding them, 
   so return volume can still be analyzed separately.

## Validation Rules (Phase 2)

`ingest/validate.py` (pandera) runs before every load. Failing rows are **not** loaded;
they go to `audit.rejected_rows` with a reason, and each run prints how many rows were
read / rejected / loaded.

| Rule | Rows rejected (full file) |
|---|---|
| `unit_price <= 0` | 2,517 (0.46%) |
| cancelled invoice (`C…`) with positive quantity | 0 |
| `invoice_date` is null | 0 |
| duplicate `line_id` | 0 |

**Circuit breaker:** if more than 5% of a batch is rejected, the whole batch is stopped
(nothing is loaded, the run is marked `failed`). That much bad data usually means a broken
export, not a few bad rows.

**Why missing `CustomerID` is not a validation rule:** it affects 24.9% of rows, so it would
trip the circuit breaker on every batch. More importantly, it isn't invalid data — those are
real sales (likely guest checkout) and they still count toward revenue and product totals.
The raw layer keeps them; the per-customer filter stays in `clean_data.py` (and will move to
the fact model in dbt), where it's a modelling choice rather than a data-quality failure.

## Setup

Requires Python 3.11+ (pandas 3.x) and Docker.

```bash
# 0. Configure credentials (never commit .env)
cp .env.example .env          # then edit the values
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 1. Start Postgres
make up

# 2. Create tables
make create-tables

# 3. Clean the raw data
make clean-data

# 4. Load into Postgres
make load

# Raw layer with validation + audit (Phase 1–2)
make init-db
make load-raw

# 5. Business analysis queries: see analyses/analysis_queries.sql
```

Run the unit tests and linter with `make test` and `make lint`.

> `make load` appends, so re-running it on a populated database fails on primary keys.
> To start fresh: `docker compose down -v && make up && make create-tables && make load`.

## Business Insights

Full queries available in `analyses/analysis_queries.sql`, covering:
- Monthly revenue trend
- Top 10 best-selling products
- Top 10 customers by spend
- Monthly return volume

## Lessons Learned

- A Docker volume only sets the password at first creation — editing `docker-compose.yml` 
  afterward has no effect if the volume already exists. Requires `docker compose down -v` to recreate.
- `pandas.to_sql(if_exists="append")` will auto-create a table if it doesn't exist yet — 
  this is risky because the table won't have the intended constraints (PK/FK). Schema management 
  (SQL DDL) should be kept clearly separate from data loading (Python).