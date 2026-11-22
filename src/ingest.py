"""
Reads orders from a JSON file, checks them, and saves them in the staging
database. Good orders get the status VALID, bad ones get INVALID with a short
reason. Running it again never creates duplicates.
"""

import json
import os
import sys

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import Json

load_dotenv()

INPUT_FILE = sys.argv[1] if len(sys.argv) > 1 else "data/sample_order.json"

"""
A new order is inserted. An existing order is only updated when it was
INVALID, so a corrected version can be loaded again. Anything else is
left alone and no row comes back. The xmax trick tells us whether the row
was just inserted or updated.
"""
SAVE_ORDER = """
INSERT INTO orders_staging
    (external_order_id, payload, status, error_message, last_error_type)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (external_order_id) DO UPDATE
SET payload = EXCLUDED.payload,
    status = EXCLUDED.status,
    error_message = EXCLUDED.error_message,
    last_error_type = EXCLUDED.last_error_type,
    updated_at = CURRENT_TIMESTAMP
WHERE orders_staging.status = 'INVALID'
RETURNING id, (xmax = 0) AS was_inserted
"""


def connect():
    return psycopg2.connect(
        host="localhost",
        port=5433,
        dbname="staging",
        user="staging",
        password=os.environ["STAGING_DB_PASSWORD"],
    )


def check_order(order):
    # Returns a list of problems. An empty list means the order is fine.
    problems = []

    if not str(order.get("customer_name") or "").strip():
        problems.append("customer name is empty")

    items = order.get("items")
    if not isinstance(items, list) or not items:
        problems.append("order has no items")
        return problems

    for number, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            problems.append(f"item {number} is not an object")
            continue
        if not str(item.get("sku") or "").strip():
            problems.append(f"item {number} has no product code")
        quantity = item.get("quantity")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            problems.append(f"item {number} has an invalid quantity")

    return problems


def log_event(cur, order_id, event, details=None):
    cur.execute(
        "INSERT INTO sync_log (order_id, event, details) VALUES (%s, %s, %s)",
        (order_id, event, Json(details) if details else None),
    )


def save_order(cur, external_id, order):
    # Returns inserted, reprocessed or duplicate.
    problems = check_order(order)
    status = "INVALID" if problems else "VALID"
    message = "; ".join(problems) if problems else None
    error_type = "VALIDATION" if problems else None

    cur.execute(SAVE_ORDER, (external_id, Json(order), status, message, error_type))
    row = cur.fetchone()

    if row is None:
        # The order exists and is not INVALID, so we skip it.
        cur.execute(
            "SELECT id FROM orders_staging WHERE external_order_id = %s",
            (external_id,),
        )
        log_event(cur, cur.fetchone()[0], "DUPLICATE_SKIPPED")
        return "duplicate"

    order_id, was_inserted = row
    prefix = "INGESTED_" if was_inserted else "REPROCESSED_"
    log_event(cur, order_id, prefix + status, {"problems": problems})
    return "inserted" if was_inserted else "reprocessed"


def main():
    with open(INPUT_FILE, encoding="utf-8") as f:
        orders = json.load(f)

    counts = {"inserted": 0, "reprocessed": 0, "duplicate": 0, "skipped": 0}
    conn = connect()
    try:
        for order in orders:
            external_id = str(order.get("external_order_id") or "").strip()
            if not external_id:
                print("Skipping an order that has no order id")
                counts["skipped"] += 1
                continue
            with conn.cursor() as cur:
                counts[save_order(cur, external_id, order)] += 1
            conn.commit()
    finally:
        conn.close()

    print(f"Read {len(orders)} orders from {INPUT_FILE}")
    print(f"New: {counts['inserted']}")
    print(f"Loaded again after being invalid: {counts['reprocessed']}")
    print(f"Duplicates skipped: {counts['duplicate']}")
    print(f"Skipped without an id: {counts['skipped']}")


if __name__ == "__main__":
    main()
