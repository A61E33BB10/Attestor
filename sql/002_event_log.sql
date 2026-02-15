-- =============================================================================
-- 002_event_log.sql
-- Append-only ordered event log. Every state change is recorded here as an
-- immutable event. This is the Postgres projection of the Kafka event stream.
-- =============================================================================

CREATE TABLE attestor.event_log (
    -- Monotonically increasing sequence number.
    sequence_id         BIGSERIAL       NOT NULL,

    -- Event type discriminator.
    event_type          TEXT            NOT NULL
                        CHECK (length(event_type) > 0),

    -- Full event payload as JSONB.
    payload             JSONB           NOT NULL,

    -- Source-assigned idempotency key. UNIQUE constraint ensures that
    -- reprocessing the same Kafka message does not create duplicate events.
    idempotency_key     TEXT            NOT NULL,

    -- Kafka provenance: "topic:partition:offset"
    kafka_ref           TEXT,

    -- BITEMPORAL COLUMNS --
    valid_time          TIMESTAMPTZ     NOT NULL,
    system_time         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- CONSTRAINTS --
    CONSTRAINT pk_event_log
        PRIMARY KEY (sequence_id),

    CONSTRAINT uq_event_log_idempotency_key
        UNIQUE (idempotency_key)
);

-- Immutability trigger
CREATE TRIGGER trg_event_log_immutable
    BEFORE UPDATE OR DELETE ON attestor.event_log
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();

COMMENT ON TABLE attestor.event_log IS
    'Append-only event log. Idempotency enforced by UNIQUE on idempotency_key. '
    'Insert pattern: INSERT ... ON CONFLICT (idempotency_key) DO NOTHING;';

-- INDEXES --
CREATE INDEX idx_event_log_valid_time
    ON attestor.event_log (valid_time);

CREATE INDEX idx_event_log_system_time
    ON attestor.event_log (system_time);

CREATE INDEX idx_event_log_event_type
    ON attestor.event_log (event_type);

CREATE INDEX idx_event_log_type_valid_time
    ON attestor.event_log (event_type, valid_time);
