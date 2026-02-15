-- =============================================================================
-- 012_reports_mifid2.sql
-- MiFID II transaction reports — append-only regulatory reporting.
-- =============================================================================

CREATE TABLE attestor.reports_mifid2 (
    report_id       TEXT            PRIMARY KEY,
    trade_ref       TEXT            NOT NULL
                    CHECK (length(trade_ref) > 0),
    instrument_type TEXT            NOT NULL
                    CHECK (instrument_type IN ('EQUITY', 'OPTION', 'FUTURE')),
    report_payload  JSONB           NOT NULL,
    content_hash    TEXT            NOT NULL
                    CHECK (length(content_hash) > 0),
    valid_time      TIMESTAMPTZ     NOT NULL,
    system_time     TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_reports_mifid2_trade_ref
    ON attestor.reports_mifid2 (trade_ref);

CREATE INDEX idx_reports_mifid2_instrument_type
    ON attestor.reports_mifid2 (instrument_type, valid_time);

CREATE TRIGGER prevent_mifid2_mutation
    BEFORE UPDATE OR DELETE ON attestor.reports_mifid2
    FOR EACH ROW EXECUTE FUNCTION prevent_mutation();

COMMENT ON TABLE attestor.reports_mifid2 IS
    'Append-only MiFID II transaction reports. Each row is an immutable '
    'regulatory report linked to a trade attestation.';
