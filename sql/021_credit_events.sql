-- Credit events register (append-only)
CREATE TABLE IF NOT EXISTS attestor.credit_events (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    attestation_id  TEXT NOT NULL UNIQUE,
    reference_entity TEXT NOT NULL,
    event_type      TEXT NOT NULL CHECK (event_type IN ('BANKRUPTCY', 'FAILURE_TO_PAY', 'RESTRUCTURING')),
    determination_date DATE NOT NULL,
    auction_price   NUMERIC(10,6) CHECK (auction_price >= 0 AND auction_price <= 1),
    settlement_date DATE,
    recovery_rate   NUMERIC(10,6) CHECK (recovery_rate >= 0 AND recovery_rate < 1),
    valid_time      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    system_time     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER prevent_mutation_credit_events
    BEFORE UPDATE OR DELETE ON attestor.credit_events
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();
