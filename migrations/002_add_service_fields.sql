-- TE Group Bot — add service type and customs fields (idempotent)
ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS service_type       VARCHAR(50)   DEFAULT 'delivery',
    ADD COLUMN IF NOT EXISTS customs_direction  VARCHAR(100)  DEFAULT '',
    ADD COLUMN IF NOT EXISTS invoice_value      NUMERIC(12,2) DEFAULT 0;
