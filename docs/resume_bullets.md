# Resume bullets

Pick 3–4. Every number below comes from a real run of this project (see README and NOTES.md).

**Project line**

E-commerce Data Pipeline — Python, PostgreSQL, dbt, Airflow, Docker, GitHub Actions, Metabase · github.com/White481/e-commerce-data-pipeline

**Bullets**

- Built an idempotent batch pipeline that validates and loads 541,909 retail transactions into PostgreSQL; re-running any day inserts 0 duplicate rows, and loading 305 daily files reconciles exactly with a one-shot load (539,392 rows).
- Added pandera data-quality checks with a 5% circuit breaker and an audit trail that records every run and each of the 2,517 rejected rows (0.46%) with its reason.
- Modeled a star schema in dbt (incremental fact, 3 dimensions) with 24 tests plus a reconciliation test; revenue matched the legacy model to the cent (8,300,065.81) and every row difference was explained.
- Orchestrated daily runs in Airflow 3 with retries and backfills; backfilled a month (31/31 runs) and proved that a forced mid-run failure followed by a retry left no duplicate data.
- Set up CI in GitHub Actions that runs 37 tests against a live Postgres service, loads real data, runs dbt build and checks idempotency on every pull request.
- Served a 5-chart Metabase dashboard built through its API on a least-privilege, SELECT-only role, verified in tests and CI.

**Short version (one line)**

Built a daily batch pipeline (Python, Postgres, dbt, Airflow, CI) for 541K retail transactions, with idempotent loads, data-quality checks rejecting 0.46% of rows with an audit trail, and a reconciled star schema served in Metabase.
