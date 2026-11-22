"""
Sends valid orders from the staging database to Odoo.
Each order is handled in its own transaction. The result is saved in the
staging table and in the event log, so we always know what happened.
"""

import os

import psycopg2
import requests
from dotenv import load_dotenv
from psycopg2.extras import Json

from odoo_client import OdooError, create_order

load_dotenv()

# Orders that failed because of a network problem get this many attempts in total.
MAX_RETRIES = 3

"""
Takes one order that is ready to send. Orders that failed only because of a
network problem are picked up again, until they run out of attempts. Rows that
another worker is already handling are skipped, and orders we have already
tried during this run are left out so we do not loop forever.
"""
PICK_ORDER = """
SELECT id, external_order_id, payload
FROM orders_staging
WHERE (status = 'VALID'
       OR (status = 'FAILED' AND last_error_type = 'NETWORK' AND retry_count < %s))
  AND id <> ALL(%s::int[])
ORDER BY id
LIMIT 1
FOR UPDATE SKIP LOCKED
"""

MARK_SENT = """
UPDATE orders_staging
SET status = 'SENT', odoo_order_id = %s, error_message = NULL,
    last_error_type = NULL, updated_at = CURRENT_TIMESTAMP
WHERE id = %s
"""

MARK_FAILED = """
UPDATE orders_staging
SET status = 'FAILED', retry_count = retry_count + 1, last_error_type = %s,
    error_message = %s, updated_at = CURRENT_TIMESTAMP
WHERE id = %s
"""


def connect():
    return psycopg2.connect(
        host="localhost",
        port=5433,
        dbname="staging",
        user="staging",
        password=os.environ["STAGING_DB_PASSWORD"],
    )


def log_event(cur, order_id, event, details=None):
    cur.execute(
        "INSERT INTO sync_log (order_id, event, details) VALUES (%s, %s, %s)",
        (order_id, event, Json(details) if details else None),
    )


def classify(exc):
    # Only NETWORK errors are worth trying again. The rest need a human or new data.
    if isinstance(exc, OdooError):
        if exc.status in (401, 403):
            return "AUTH"
        if exc.status == 404:
            return "ODOO_MISSING_REFERENCE"
        if exc.status >= 500:
            return "NETWORK"
        return "ODOO_REJECTED"
    if isinstance(exc, requests.exceptions.RequestException):
        return "NETWORK"
    if isinstance(exc, ValueError):
        return "VALIDATION"
    return "UNKNOWN"


def describe(exc):
    # Short text for the error column.
    if isinstance(exc, OdooError) and isinstance(exc.payload, dict):
        text = exc.payload.get("message") or str(exc)
    else:
        text = str(exc)
    return text[:500]


def record_failure(cur, order_id, external_id, exc):
    error_type = classify(exc)
    message = describe(exc)

    if error_type == "AUTH":
        # The order itself is fine, so we leave it as it is and stop the run.
        log_event(cur, order_id, "STOPPED_AUTH", {"message": message})
        return "auth"

    cur.execute(MARK_FAILED, (error_type, message, order_id))
    log_event(cur, order_id, "FAILED", {"type": error_type, "message": message})
    print(f"{external_id}: failed ({error_type}) {message}")
    return "failed"


def process_next(conn, done_ids):
    # Returns what happened to the order, or None when there is nothing left.
    with conn:
        with conn.cursor() as cur:
            cur.execute(PICK_ORDER, (MAX_RETRIES, done_ids))
            row = cur.fetchone()
            if row is None:
                return None
            order_id, external_id, payload = row
            done_ids.append(order_id)

            try:
                odoo_order_id, created = create_order(payload)
            except Exception as exc:
                return record_failure(cur, order_id, external_id, exc)

            cur.execute(MARK_SENT, (odoo_order_id, order_id))
            event = "SENT" if created else "ALREADY_IN_ODOO"
            log_event(cur, order_id, event, {"odoo_order_id": odoo_order_id})
            print(f"{external_id}: {event.lower()} (Odoo id {odoo_order_id})")
            return "sent" if created else "already_in_odoo"


def main():
    counts = {"sent": 0, "already_in_odoo": 0, "failed": 0}
    done_ids = []
    conn = connect()
    try:
        while True:
            result = process_next(conn, done_ids)
            if result is None:
                break
            if result == "auth":
                print("Stopped: Odoo refused the API key. Check the key in .env.")
                break
            counts[result] += 1
    finally:
        conn.close()

    print(f"Created in Odoo: {counts['sent']}")
    print(f"Already in Odoo: {counts['already_in_odoo']}")
    print(f"Failed: {counts['failed']}")


if __name__ == "__main__":
    main()
