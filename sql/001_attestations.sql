-- =============================================================================
-- 001_attestations.sql
-- Attestation store: content-addressed, append-only, bitemporal.
--
-- Design decisions:
--   PK = attestation_id (hash of full attestation identity, per V-01/GAP-01)
--   content_hash = hash of value only (indexed, non-unique)
--   Kafka is source of truth; this table is a derived, queryable projection.
--   No UPDATE. No DELETE. Enforced by trigger.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS attestor;

-- ---------------------------------------------------------------------------
-- Immutability enforcement function (shared by all attestor tables)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION attestor.prevent_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'Table attestor.% is append-only: % operations are forbidden. '
        'Financial ledgers use pens, not pencils.',
        TG_TABLE_NAME, TG_OP;
    RETURN NULL;  -- never reached, but required by plpgsql
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ---------------------------------------------------------------------------
-- attestor.attestations
-- ---------------------------------------------------------------------------
CREATE TABLE attestor.attestations (
    -- Primary identity: SHA-256 of canonical_bytes(source, timestamp,
    -- confidence, value, provenance). Two observations of the same value
    -- from different sources produce different attestation_ids.
    attestation_id      TEXT            NOT NULL,

    -- Value identity: SHA-256 of canonical_bytes(value) only. Multiple
    -- attestations may share the same content_hash if they attest the
    -- same value from different sources. Used for dedup-by-value queries.
    content_hash        TEXT            NOT NULL,

    -- Fully qualified Python type name of the attested value.
    value_type          TEXT            NOT NULL
                        CHECK (length(value_type) > 0),

    -- Canonical JSON serialization of the attested value.
    value_json          JSONB           NOT NULL,

    -- Epistemic confidence classification.
    confidence_type     TEXT            NOT NULL
                        CHECK (confidence_type IN ('FIRM', 'QUOTED', 'DERIVED')),

    -- Full confidence payload as JSONB.
    confidence_json     JSONB           NOT NULL,

    -- Attestation source identifier.
    source              TEXT            NOT NULL
                        CHECK (length(source) > 0),

    -- Ordered array of input attestation_ids. Empty for Firm attestations.
    provenance_refs     TEXT[]          NOT NULL DEFAULT '{}',

    -- BITEMPORAL COLUMNS --

    -- valid_time: when the attested event occurred in the real world.
    valid_time          TIMESTAMPTZ     NOT NULL,

    -- system_time: when this row was inserted into the database.
    system_time         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- CONSTRAINTS --
    CONSTRAINT pk_attestations
        PRIMARY KEY (attestation_id),

    CONSTRAINT chk_attestation_id_length
        CHECK (length(attestation_id) = 64),

    CONSTRAINT chk_content_hash_length
        CHECK (length(content_hash) = 64)
);

-- Immutability trigger: reject UPDATE and DELETE
CREATE TRIGGER trg_attestations_immutable
    BEFORE UPDATE OR DELETE ON attestor.attestations
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();

COMMENT ON TABLE attestor.attestations IS
    'Content-addressed attestation store. PK is attestation_id (hash of full '
    'identity). Append-only: UPDATE and DELETE are rejected by trigger. '
    'Insert pattern: INSERT INTO attestor.attestations (...) VALUES (...) '
    'ON CONFLICT (attestation_id) DO NOTHING;';

-- INDEXES --

CREATE INDEX idx_attestations_content_hash
    ON attestor.attestations (content_hash);

CREATE INDEX idx_attestations_valid_time
    ON attestor.attestations (valid_time);

CREATE INDEX idx_attestations_system_time
    ON attestor.attestations (system_time);

CREATE INDEX idx_attestations_confidence_type
    ON attestor.attestations (confidence_type);

CREATE INDEX idx_attestations_source
    ON attestor.attestations (source);

CREATE INDEX idx_attestations_provenance_refs
    ON attestor.attestations USING GIN (provenance_refs);
