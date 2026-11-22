# Odoo 20 Order Integration

Integration layer that loads external JSON orders into a PostgreSQL staging
database and synchronizes them with Odoo 20 Community via the JSON-2 API.
Engineering project.

**Status:** in progress. Environment, staging schema and API read access are
verified. Staging ingestion and `sale.order` creation are in development.

## Data flow

```text
JSON orders (data/sample_order.json)
        |
        v
Python ingestion (validation, deduplication)
        |
        v
PostgreSQL staging (orders_staging, UNIQUE external_order_id)
        |
        v
Python sync (Odoo JSON-2 API)
        |
        v
Odoo 20 (res.partner, sale.order)
```

## Quick start

1. `cp .env.example .env` and set local passwords.
2. `docker compose up -d` (tested with `odoo:20.0` pulled on 2026-11-21 and `postgres:16`).
3. Open http://localhost:8069, create the database `odoo_erp`, install Sales,
   generate an API key (My Profile > Account Security) and put it in `.env`.
4. Verify the connection:

```bash
python3 -m venv venv && source venv/bin/activate
pip install requests python-dotenv psycopg2-binary
python src/test_odoo_connection.py
```

## Usage

Run the scripts in this order from the project folder, with the virtual
environment active and the containers running.

1. Copy the product list from Odoo into the staging database.
2. Load orders from a JSON file, check them and store them.
3. Send the valid orders to Odoo.

```bash
python src/sync_products.py
python src/ingest.py data/sample_order.json
python src/sync.py
```

Running any step twice is safe. The same order is never created twice in
Odoo, because every order carries its external number into Odoo and the
script checks for it first.

## How orders move through the staging table

- VALID: the order passed all checks and waits to be sent.
- INVALID: the order failed a check. The reason is saved with the order. If a
  corrected version is loaded later, it replaces the invalid one.
- SENT: the order exists in Odoo.
- FAILED: sending did not work. Network problems are tried again, up to three
  times in total. Other problems are not retried because they need new data.

An order with a problem in any line is rejected as a whole. We do not send
half an order.

Every important step is written to the sync_log table.
