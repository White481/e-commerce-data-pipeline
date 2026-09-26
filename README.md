
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

## Setup

```bash
# 1. Start the Postgres container
docker compose up -d

# 2. Create tables
# Run models/create_tables.sql via a SQL client (SQLTools/psql)

# 3. Clean the data
python ingest/clean_data.py

# 4. Load data into Postgres
python ingest/load_to_postgres.py

# 5. Run business analysis queries
# See models/analysis_queries.sql
```

## Business Insights

Full queries available in `models/analysis_queries.sql`, covering:
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