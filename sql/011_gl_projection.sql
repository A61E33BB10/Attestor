-- =============================================================================
-- 011_gl_projection.sql
-- GL projection snapshot table: sub-ledger aggregated to GL accounts.
-- =============================================================================

CREATE TABLE attestor.gl_projection (
    gl_account      TEXT            NOT NULL
                    CHECK (length(gl_account) > 0),
    gl_account_type TEXT            NOT NULL
                    CHECK (gl_account_type IN (
                        'ASSET', 'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE'
                    )),
    instrument_id   TEXT            NOT NULL
                    CHECK (length(instrument_id) > 0),
    debit_total     DECIMAL         NOT NULL DEFAULT 0,
    credit_total    DECIMAL         NOT NULL DEFAULT 0,
    valid_time      TIMESTAMPTZ     NOT NULL,
    system_time     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    PRIMARY KEY (gl_account, instrument_id, valid_time)
);

CREATE INDEX idx_gl_projection_type
    ON attestor.gl_projection (gl_account_type, valid_time);

CREATE TRIGGER prevent_gl_projection_mutation
    BEFORE UPDATE OR DELETE ON attestor.gl_projection
    FOR EACH ROW EXECUTE FUNCTION prevent_mutation();

COMMENT ON TABLE attestor.gl_projection IS
    'Snapshot of GL entries projected from the sub-ledger. '
    'Append-only: each valid_time represents a projection snapshot.';
