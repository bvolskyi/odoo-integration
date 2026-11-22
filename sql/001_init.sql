CREATE TABLE IF NOT EXISTS orders_staging (
    id SERIAL PRIMARY KEY,
    external_order_id VARCHAR(100) UNIQUE NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    odoo_order_id INTEGER,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
