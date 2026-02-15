-- =============================================================================
-- 005_positions.sql
-- Bitemporal position tracking: (account, instrument, valid_time).
-- Supports point-in-time queries for both business time and system time.
-- =============================================================================

CREATE TABLE attestor.positions (
    account_id      TEXT            NOT NULL
                    REFERENCES attestor.accounts(account_id),
    instrument_id   TEXT            NOT NULL
                    CHECK (length(instrument_id) > 0),
    quantity        DECIMAL         NOT NULL,
    valid_time      TIMESTAMPTZ     NOT NULL,
    system_time     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_positions
        PRIMARY KEY (account_id, instrument_id, valid_time)
);

CREATE INDEX idx_positions_instrument
    ON attestor.positions (instrument_id, valid_time);

CREATE INDEX idx_positions_system_time
    ON attestor.positions (system_time);

CREATE TRIGGER prevent_positions_mutation
    BEFORE UPDATE OR DELETE ON attestor.positions
    FOR EACH ROW EXECUTE FUNCTION prevent_mutation();

COMMENT ON TABLE attestor.positions IS
    'Bitemporal position store. Each row is a snapshot of a position at a '
    'specific valid_time. Query with valid_time <= ? AND system_time <= ? '
    'for point-in-time reconstructions.';
