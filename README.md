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
