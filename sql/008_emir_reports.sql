-- =============================================================================
-- 008_emir_reports.sql
-- EMIR trade report projections: append-only regulatory reports.
-- =============================================================================

CREATE TABLE attestor.emir_reports (
    uti                         TEXT            NOT NULL,
    reporting_counterparty_lei  TEXT            NOT NULL
                                CHECK (length(reporting_counterparty_lei) = 20),
    other_counterparty_lei      TEXT            NOT NULL
                                CHECK (length(other_counterparty_lei) = 20),
    instrument_id               TEXT            NOT NULL
                                CHECK (length(instrument_id) > 0),
    isin                        TEXT,
    direction                   TEXT            NOT NULL
                                CHECK (direction IN ('BUY', 'SELL')),
    quantity                    DECIMAL         NOT NULL
                                CHECK (quantity > 0),
    price                       DECIMAL         NOT NULL,
    currency                    TEXT            NOT NULL
                                CHECK (length(currency) > 0),
    trade_date                  DATE            NOT NULL,
    settlement_date             DATE            NOT NULL,
    venue                       TEXT            NOT NULL
                                CHECK (length(venue) > 0),
    report_timestamp            TIMESTAMPTZ     NOT NULL,
    attestation_refs            TEXT[]          NOT NULL DEFAULT '{}',
    attestation_id              TEXT,
    system_time                 TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_emir_reports PRIMARY KEY (uti),
    CONSTRAINT chk_uti_nonempty CHECK (length(uti) > 0)
);

-- Immutability trigger
CREATE TRIGGER trg_emir_reports_immutable
    BEFORE UPDATE OR DELETE ON attestor.emir_reports
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();

CREATE INDEX idx_emir_reports_trade_date
    ON attestor.emir_reports (trade_date);

CREATE INDEX idx_emir_reports_instrument
    ON attestor.emir_reports (instrument_id);

COMMENT ON TABLE attestor.emir_reports IS
    'Append-only EMIR trade report projections. Each row is a pure projection '
    'from a canonical order (INV-R01).';
