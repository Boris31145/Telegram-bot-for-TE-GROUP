-- T.E. Group Bot — Initial schema
CREATE TABLE IF NOT EXISTS leads (
    id          SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    username    VARCHAR(255) DEFAULT '',
    full_name   VARCHAR(255) DEFAULT '',
    country     VARCHAR(100) DEFAULT '',
    city_from   VARCHAR(255) DEFAULT '',
    cargo_type  VARCHAR(100) DEFAULT '',
    weight_kg   NUMERIC(10,2) DEFAULT 0,
    volume_m3   NUMERIC(10,3) DEFAULT 0,
    urgency     VARCHAR(50)  DEFAULT '',
    incoterms   VARCHAR(50)  DEFAULT '',
    phone       VARCHAR(50)  DEFAULT '',
    comment     TEXT         DEFAULT '',
    status      VARCHAR(20)  DEFAULT 'NEW',
    created_at  TIMESTAMPTZ  DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_leads_status    ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_created   ON leads(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_leads_tg_id     ON leads(telegram_id);
