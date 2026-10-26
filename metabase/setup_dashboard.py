"""ตั้งค่า Metabase ผ่าน API: admin → เชื่อม DB ด้วย metabase_ro → 5 กราฟ → 1 dashboard

    python -m metabase.setup_dashboard      (ค่าทั้งหมดจาก .env, Metabase ที่ localhost:3000)

รันซ้ำได้: ครั้งแรกทำ setup ครั้งถัดไป login แล้วแทนที่กราฟ/dashboard เดิมด้วยชุดใหม่
"""

import json
import os
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

load_dotenv()

URL = os.getenv("METABASE_URL", "http://localhost:3000")
DATABASE_NAME = "E-commerce marts"
DASHBOARD_NAME = "E-commerce overview"

# (ชื่อ, ชนิดกราฟ, SQL, visualization_settings) — อ่านจาก schema marts เท่านั้น
CARDS = [
    (
        "Monthly revenue",
        "line",
        """
        SELECT date_trunc('month', date_key)::date AS month,
               round(sum(total_amount), 2)         AS revenue
        FROM marts.fact_sales
        GROUP BY 1
        ORDER BY 1
        """,
        {"graph.dimensions": ["month"], "graph.metrics": ["revenue"]},
    ),
    (
        "Repeat customer rate (%)",
        "scalar",
        """
        WITH orders AS (
            SELECT customer_id, count(DISTINCT invoice_no) AS order_count
            FROM marts.fact_sales
            WHERE NOT is_return
            GROUP BY 1
        )
        SELECT round(100.0 * count(*) FILTER (WHERE order_count > 1) / count(*), 1)
               AS repeat_customer_pct
        FROM orders
        """,
        {},
    ),
    (
        "Top 10 products by revenue",
        "row",
        """
        SELECT p.description               AS product,
               round(sum(f.total_amount), 2) AS revenue
        FROM marts.fact_sales f
        JOIN marts.dim_product p USING (product_key)
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT 10
        """,
        {"graph.dimensions": ["product"], "graph.metrics": ["revenue"]},
    ),
    (
        "Top 10 countries by revenue",
        "row",
        """
        SELECT c.country,
               round(sum(f.total_amount), 2) AS revenue
        FROM marts.fact_sales f
        JOIN marts.dim_customer c USING (customer_id)
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT 10
        """,
        {"graph.dimensions": ["country"], "graph.metrics": ["revenue"]},
    ),
    (
        "Monthly return rate (% of sales value)",
        "line",
        """
        SELECT date_trunc('month', date_key)::date AS month,
               round(100.0 * -sum(total_amount) FILTER (WHERE is_return)
                     / sum(total_amount) FILTER (WHERE NOT is_return), 2) AS return_rate_pct
        FROM marts.fact_sales
        GROUP BY 1
        ORDER BY 1
        """,
        {"graph.dimensions": ["month"], "graph.metrics": ["return_rate_pct"]},
    ),
]

# ตำแหน่งบน dashboard (grid กว้าง 24): row, col, size_x, size_y ตามลำดับ CARDS
LAYOUT = [(0, 0, 16, 6), (0, 16, 8, 6), (6, 0, 12, 8), (6, 12, 12, 8), (14, 0, 24, 6)]


def call(method: str, path: str, body: dict | None = None, session: str | None = None):
    request = urllib.request.Request(
        URL + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"X-Metabase-Session": session} if session else {})},
    )
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{method} {path} → {exc.code}: {exc.read().decode()[:500]}") from exc
    return json.loads(raw) if raw else None


def login() -> str:
    email, password = os.environ["METABASE_ADMIN_EMAIL"], os.environ["METABASE_ADMIN_PASSWORD"]
    properties = call("GET", "/api/session/properties")
    if not properties.get("has-user-setup"):
        call("POST", "/api/setup", {
            "token": properties["setup-token"],
            "user": {"email": email, "password": password,
                     "first_name": "Admin", "last_name": "Local"},
            "prefs": {"site_name": "E-commerce pipeline", "allow_tracking": False},
        })
        print("setup: created admin")
    return call("POST", "/api/session", {"username": email, "password": password})["id"]


def ensure_database(session: str) -> int:
    details = {
        "host": os.getenv("METABASE_DB_HOST", "postgres"),
        "port": 5432,
        "dbname": os.environ["POSTGRES_DB"],
        "user": "metabase_ro",
        "password": os.environ["METABASE_RO_PASSWORD"],
        "ssl": False,
        "schema-filters-type": "inclusion",
        "schema-filters-patterns": "marts",
    }
    existing = call("GET", "/api/database", session=session)
    existing = existing.get("data", existing)
    for database in existing:
        if database["name"] == DATABASE_NAME:
            call("PUT", f"/api/database/{database['id']}", {"details": details}, session)
            return database["id"]
    database = call("POST", "/api/database",
                    {"engine": "postgres", "name": DATABASE_NAME, "details": details}, session)
    print(f"database: connected as metabase_ro (id={database['id']})")
    return database["id"]


def archive_previous(session: str) -> None:
    names = {name for name, *_ in CARDS}
    for card in call("GET", "/api/card?f=all", session=session):
        if card["name"] in names and not card.get("archived"):
            call("PUT", f"/api/card/{card['id']}", {"archived": True}, session)
    for dashboard in call("GET", "/api/dashboard", session=session):
        if dashboard["name"] == DASHBOARD_NAME and not dashboard.get("archived"):
            call("PUT", f"/api/dashboard/{dashboard['id']}", {"archived": True}, session)


def main() -> None:
    session = login()
    database_id = ensure_database(session)
    archive_previous(session)

    card_ids = []
    for name, display, query, settings in CARDS:
        card = call("POST", "/api/card", {
            "name": name,
            "display": display,
            "dataset_query": {"type": "native", "database": database_id,
                              "native": {"query": " ".join(query.split())}},
            "visualization_settings": settings,
        }, session)
        card_ids.append(card["id"])

    dashboard = call("POST", "/api/dashboard", {
        "name": DASHBOARD_NAME,
        "description": "Online Retail 2010-12-01 → 2011-12-09 (December 2011 is a partial month). "
                       "Source: marts schema built by dbt, read through the metabase_ro role.",
    }, session)
    call("PUT", f"/api/dashboard/{dashboard['id']}", {"dashcards": [
        {"id": -(i + 1), "card_id": card_id, "row": row, "col": col, "size_x": w, "size_y": h}
        for i, (card_id, (row, col, w, h)) in enumerate(zip(card_ids, LAYOUT))
    ]}, session)

    # รันทุกกราฟหนึ่งครั้งเพื่อยืนยันว่า query ทำงานผ่าน role อ่านอย่างเดียวได้จริง
    for card_id, (name, *_) in zip(card_ids, CARDS):
        for _ in range(3):
            result = call("POST", f"/api/card/{card_id}/query", {}, session)
            if result.get("status") == "completed":
                break
            time.sleep(2)
        rows = result.get("data", {}).get("rows", [])
        print(f"card {name!r}: {result.get('status')}, {len(rows)} rows, first={rows[:1]}")

    print(f"dashboard: {URL}/dashboard/{dashboard['id']}")


if __name__ == "__main__":
    main()
