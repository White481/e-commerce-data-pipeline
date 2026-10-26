# Notes — what I ran into

## Phase 0

- **Database password leaked in git history.** It was hard-coded in `docker-compose.yml` and
  `load_to_postgres.py` and pushed to GitHub. Moving it to `.env` does not remove old commits,
  so I rotated the password (`docker compose down -v` to recreate the volume) instead of
  rewriting history.
- **`venv/` was committed** (4,823 files) before `.gitignore` existed. `git rm -r --cached`
  untracked it, but pulling that commit into a branch that still tracked those files deleted
  them from disk — the venv had to be rebuilt.
- **requirements didn't match the venv.** The venv was Python 3.9, but `pandas==3.0.5` needs 3.11+.
  `psycopg2-binary==2.9.10` also had no Python 3.14 wheel → bumped to 2.9.12.
- **`make test` failed while `python -m pytest` passed** — `python -m` adds the cwd to
  `sys.path`, bare `pytest` does not. Fixed with `pythonpath = ["."]` in `pyproject.toml`.

## Phase 1 — grain check

Raw file: 541,909 rows, 25,900 invoices.

| Check | Result |
|---|---|
| `(invoice_no, stock_code)` pairs that repeat | 9,694 pairs / 20,378 rows (max 20× in one invoice) |
| Fully identical rows | 5,268 extra rows |
| Same check on the old `fact_sales` (after dropping missing CustomerID) | 9,197 pairs / 19,345 rows |

→ `(invoice_no, stock_code)` is **not** a key. Grain = one invoice line.
`line_id = '<invoice_no>-<line_no>'`, where `line_no` is the row's position inside the invoice
in source-file order.

Caveat: `line_id` depends on the source file's row order. If the source were re-exported in a
different order, ids would shift. Fine for a static file; a real source system should provide a line id.

## Phase 1 — idempotency proof (real data)

| Run | Action | inserted | updated | rows in table |
|---|---|---|---|---|
| 1 | first load | 541,909 | 0 | 541,909 |
| 2 | re-run | 0 | 0 | 541,909 |
| — | delete 3 invoices + 10,000 random lines | | | 531,811 |
| 3 | re-run | 10,098 | 0 | 541,909 |

Revenue total (`sum(quantity * unit_price)`) was 9,747,747.93 before and after.

## Phase 2 — data quality

- Profiled every candidate rule on the full file before choosing thresholds. Missing
  `CustomerID` = 24.9% → would trip a 5% circuit breaker on every batch, so it stayed out of
  validation (reasoning in README).
- `unit_price <= 0` (2,517 rows) also covers every row with a missing `Description` (1,454)
  and every non-`C` invoice with negative quantity (1,336) — they all have price 0.
  2 rows are `A56318x` "Adjust bad debt" with price −11,062.06.
- Rows rejected now had already been loaded in Phase 1. Upsert alone never deletes, so the
  load now also deletes rejected `line_id`s inside the same transaction.
- pandera reports a check that *crashes* (e.g. `quantity` is a string) as a failure case with
  no row index. Dropping those silently would let a malformed batch pass, so `validate()`
  raises instead.
- Revenue in raw went from 9,747,747.93 to 9,769,872.05 after validation — the two
  bad-debt adjustment rows (−22,124.12) were removed.

## Phase 3 — incremental loading

- Checked before splitting: no invoice spans two days, and `line_id`s built per daily file are
  identical to the full-file ones — so daily loads and the one-shot load agree.
- **Per-day circuit breaker trips on real data.** 2 of 305 days exceed 5% rejected
  (2010-12-22: 64/291 = 22.0%, 2011-01-28: 51/1008 = 5.1%), all zero-price rows with no
  customer — stock adjustments, not a broken export. Kept the 5% rule and added a reviewed
  override (`--max-reject-rate`), recorded in audit.
- **Bug: approved override wasn't remembered.** `--since-last` re-loads the watermark day; when
  that day needed an override, the breaker tripped again on every run and the pipeline was stuck.
  Fix: reuse the highest rate that already succeeded for that `batch_date`.
- **Bug: data-based watermark skipped 22 days.** After `--since-last` stopped at 2010-12-22, I
  loaded 2011-01-28 directly; the watermark jumped to 01-28 and 2010-12-23 → 2011-01-27 were never
  loaded (506,611 rows instead of 539,392). Fix: start from the first landing day that has no
  rows in raw if it's earlier than the watermark. Reconciled afterwards: 539,392 rows,
  9,769,872.05 — same as the full-file load.
- A file moving to a different path made every row count as "updated" (`source_file` was part of
  the change check). Excluded it from the comparison.

| Check (real data) | Result |
|---|---|
| Load 5 days, then the same 5 again | 13,963 → 13,963 rows, 2nd round 0 inserted / 0 updated |
| Missing day (2010-12-04) | `skipped`, exit 0 |
| Delete last 3 days → `--since-last` | 5,205 → 13,963 rows |

## Phase 5 — Airflow

- Pinned `apache/airflow:3.3.2-python3.12`. Verified the imports inside the image instead of
  trusting memory: `airflow.sdk.DAG`, `airflow.providers.standard.operators.bash.BashOperator`,
  `airflow.timetables.interval.CronDataIntervalTimetable`. Backfill in 3.x is
  `airflow backfill create --from-date --to-date`, not `airflow dags backfill`.
- Airflow 3 defaults `@daily` to a trigger timetable (logical date = run time, zero-length
  interval). Used `CronDataIntervalTimetable` so `{{ ds }}` is the day being processed.
- Image build failed: `/opt` isn't writable by the `airflow` user → create the venv dir as root
  and `chown` it.
- **Backfill runs sat in `queued` forever.** The scheduler only picks up runs of *unpaused* DAGs
  — backfill runs included (`DagModel.is_paused == false()` in
  `DagRun.get_queued_dag_runs_to_set_running`). Unpausing also starts `catchup`, so catchup runs
  ran alongside the backfill. Harmless only because every task is idempotent.
- Docker was stopped mid-run (by me). Re-paused the DAG with a one-off
  `docker compose run --rm airflow airflow dags pause` *before* starting the scheduler again.
- The fail-injection flag was global at first — it would have failed every concurrent catchup
  run too. Made it per day: `data/.fail_transform_YYYY-MM-DD`.
- `airflow tasks clear -s/-e` matched nothing for a backfill run; clearing through the REST API
  (`POST /api/v2/dags/{dag_id}/clearTaskInstances` with `dag_run_id`, `dry_run` first) worked.
- **A second backfill from the UI reset 28 green runs.** The UI backfill dialog was submitted with
  reprocess behavior `completed`, which re-queued the already-successful January runs (tasks back
  to "no status"); stopping it with ■ marked every not-yet-run run `failed`. No task had run, so
  data was untouched (verified: raw 539,392 rows, mart matches raw on all 121 days, 0 duplicate
  `line_id`). Fixed with `airflow backfill create ... --reprocess-behavior failed` → 31/31 green.
  Lesson: in Airflow 3 the backfill banner's ■ *cancels* the backfill, and "reprocess completed"
  re-runs days that already succeeded.

## Phase 4 — dbt

- `pip install dbt-postgres` pulled a **beta** `dbt-core` (1.13.0b1). Pinned `dbt-core==1.12.6`
  + `dbt-postgres==1.11.0`.
- dbt doesn't read `.env`; `profiles.yml` uses `env_var()` and the Makefile sources `.env` first.
  In Airflow the same vars come from docker-compose (`POSTGRES_HOST=postgres`).
- Default schema naming would give `analytics_staging` / `analytics_marts`; a
  `generate_schema_name` macro keeps them as `staging` / `marts`.
- `fact_sales` incremental with `unique_key='date_key'` + `delete+insert` = replace the whole day,
  same semantics as the Phase 5 SQL transform, so retries and backfills stay idempotent.
- `dim_product.product_key = md5(stock_code)` instead of SERIAL: stable across full rebuilds.
- Reconciliation vs Phase 0: 406,829 → 406,789 fact rows (40 zero-price rows rejected), revenue
  identical at 8,300,065.81. The old table's "44 zero-price rows" included 4 rows of 0.001 that
  `NUMERIC(10,2)` had rounded to 0.00.
- The first `dbt build` died mid-test: Docker was stopped while it ran. Not a dbt problem.
- Removed the Phase 5 SQL transform (`sql/mart.sql`, `sql/transform_daily.sql`) so only dbt builds
  the marts. The old `mart` schema is still in the local database until dropped.
