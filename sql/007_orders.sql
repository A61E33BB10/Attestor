-- =============================================================================
-- 007_orders.sql
-- Canonical order store: normalized trade orders from gateway.
-- Append-only: no UPDATE/DELETE.
-- =============================================================================

CREATE TABLE attestor.orders (
    order_id            TEXT            NOT NULL,
    instrument_id       TEXT            NOT NULL
                        CHECK (length(instrument_id) > 0),
    isin                TEXT,
    side                TEXT            NOT NULL
                        CHECK (side IN ('BUY', 'SELL')),
    quantity            DECIMAL         NOT NULL
                        CHECK (quantity > 0),
    price               DECIMAL         NOT NULL,
    currency            TEXT            NOT NULL
                        CHECK (length(currency) > 0),
    order_type          TEXT            NOT NULL
                        CHECK (order_type IN ('MARKET', 'LIMIT')),
    counterparty_lei    TEXT            NOT NULL
                        CHECK (length(counterparty_lei) = 20),
    executing_party_lei TEXT            NOT NULL
                        CHECK (length(executing_party_lei) = 20),
    trade_date          DATE            NOT NULL,
    settlement_date     DATE            NOT NULL,
    venue               TEXT            NOT NULL
                        CHECK (length(venue) > 0),
    order_timestamp     TIMESTAMPTZ     NOT NULL,
    attestation_id      TEXT,
    system_time         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_orders PRIMARY KEY (order_id),
    CONSTRAINT chk_order_id_nonempty CHECK (length(order_id) > 0),
    CONSTRAINT chk_settlement_after_trade CHECK (settlement_date >= trade_date)
);

-- Immutability trigger
CREATE TRIGGER trg_orders_immutable
    BEFORE UPDATE OR DELETE ON attestor.orders
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();

CREATE INDEX idx_orders_instrument
    ON attestor.orders (instrument_id, trade_date);

CREATE INDEX idx_orders_trade_date
    ON attestor.orders (trade_date);

COMMENT ON TABLE attestor.orders IS
    'Append-only canonical order store. Each order is normalized by the gateway.';
