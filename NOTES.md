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
