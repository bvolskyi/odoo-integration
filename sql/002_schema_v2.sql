/*
Second version of the staging schema.
Adds status checking, a retry counter, an error type and an event log.
Safe to run more than once.
*/

ALTER TABLE orders_staging
    ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_error_type VARCHAR(50);

-- Only these statuses are allowed.
ALTER TABLE orders_staging DROP CONSTRAINT IF EXISTS orders_staging_status_check;
ALTER TABLE orders_staging ADD CONSTRAINT orders_staging_status_check
    CHECK (status IN ('PENDING', 'VALID', 'INVALID', 'SENT', 'FAILED'));

-- One row for every important thing that happens to an order.
CREATE TABLE IF NOT EXISTS sync_log (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders_staging(id),
    event VARCHAR(50) NOT NULL,
    details JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS sync_log_order_id_idx ON sync_log (order_id);
