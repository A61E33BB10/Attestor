-- =============================================================================
-- 009_market_data.sql
-- Market data observations: attested price points from oracle ingest.
-- =============================================================================

CREATE TABLE attestor.market_data (
    instrument_id       TEXT            NOT NULL
                        CHECK (length(instrument_id) > 0),
    price               DECIMAL         NOT NULL,
    currency            TEXT            NOT NULL
                        CHECK (length(currency) > 0),
    observation_time    TIMESTAMPTZ     NOT NULL,
    confidence_type     TEXT            NOT NULL
                        CHECK (confidence_type IN ('FIRM', 'QUOTED', 'DERIVED')),
    attestation_id      TEXT            NOT NULL
                        CHECK (length(attestation_id) = 64),
    source              TEXT            NOT NULL
                        CHECK (length(source) > 0),
    system_time         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_market_data
        PRIMARY KEY (attestation_id)
);

-- Immutability trigger
CREATE TRIGGER trg_market_data_immutable
    BEFORE UPDATE OR DELETE ON attestor.market_data
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();

CREATE INDEX idx_market_data_instrument_time
    ON attestor.market_data (instrument_id, observation_time);

CREATE INDEX idx_market_data_source
    ON attestor.market_data (source);

COMMENT ON TABLE attestor.market_data IS
    'Attested market data observations. Each row is a price point from '
    'the oracle ingestion pipeline with content-addressed identity.';
