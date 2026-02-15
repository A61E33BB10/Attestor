-- Scheduled and realised cashflows for IRS and FX (append-only, bitemporal)
CREATE TABLE IF NOT EXISTS attestor.cashflows (
    cashflow_id  TEXT        PRIMARY KEY,
    instrument_id TEXT       NOT NULL,
    direction    TEXT        NOT NULL CHECK (direction IN ('PAY', 'RECEIVE')),
    amount       DECIMAL     NOT NULL,
    currency     TEXT        NOT NULL,
    payment_date DATE        NOT NULL,
    leg_type     TEXT        NOT NULL CHECK (leg_type IN ('FIXED', 'FLOAT')),
    period_start DATE        NOT NULL,
    period_end   DATE        NOT NULL,
    status       TEXT        NOT NULL CHECK (status IN ('SCHEDULED', 'FIXED', 'SETTLED')),
    valid_time   TIMESTAMPTZ NOT NULL,
    system_time  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER prevent_mutation_cashflows
    BEFORE UPDATE OR DELETE ON attestor.cashflows
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();
