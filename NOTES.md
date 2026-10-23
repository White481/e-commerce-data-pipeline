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
