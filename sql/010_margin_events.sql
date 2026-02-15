-- =============================================================================
-- 010_margin_events.sql
-- Append-only margin event log for options and futures.
-- =============================================================================

CREATE TABLE attestor.margin_events (
    event_id        TEXT            PRIMARY KEY,
    account_id      TEXT            NOT NULL
                    REFERENCES attestor.accounts(account_id),
    margin_type     TEXT            NOT NULL
                    CHECK (margin_type IN ('INITIAL', 'VARIATION')),
    margin_flow     DECIMAL         NOT NULL,
    instrument_id   TEXT            NOT NULL
                    CHECK (length(instrument_id) > 0),
    valid_time      TIMESTAMPTZ     NOT NULL,
    system_time     TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_margin_events_account
    ON attestor.margin_events (account_id, valid_time);

CREATE INDEX idx_margin_events_instrument
    ON attestor.margin_events (instrument_id, valid_time);

CREATE TRIGGER prevent_margin_events_mutation
    BEFORE UPDATE OR DELETE ON attestor.margin_events
    FOR EACH ROW EXECUTE FUNCTION prevent_mutation();

COMMENT ON TABLE attestor.margin_events IS
    'Append-only margin event log. Each row records a single margin flow '
    '(initial or variation) for an account/instrument pair.';
