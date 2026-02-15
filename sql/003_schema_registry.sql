-- =============================================================================
-- 003_schema_registry.sql
-- Type version tracking for canonical serialization schemas.
-- =============================================================================

CREATE TABLE attestor.schema_registry (
    -- Fully qualified Python type name.
    type_name           TEXT            NOT NULL
                        CHECK (length(type_name) > 0),

    -- Monotonically increasing version number per type_name.
    version             INTEGER         NOT NULL
                        CHECK (version > 0),

    -- SHA-256 hash of the canonical JSON Schema definition.
    schema_hash         TEXT            NOT NULL
                        CHECK (length(schema_hash) = 64),

    -- JSON Schema document for this type at this version.
    schema_json         JSONB           NOT NULL,

    -- BITEMPORAL COLUMNS --
    valid_time          TIMESTAMPTZ     NOT NULL,
    registered_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- CONSTRAINTS --
    CONSTRAINT pk_schema_registry
        PRIMARY KEY (type_name, version),

    CONSTRAINT uq_schema_registry_hash
        UNIQUE (type_name, schema_hash)
);

-- Immutability trigger
CREATE TRIGGER trg_schema_registry_immutable
    BEFORE UPDATE OR DELETE ON attestor.schema_registry
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();

COMMENT ON TABLE attestor.schema_registry IS
    'Type version tracking for canonical serialization schemas. Append-only. '
    'A new version creates a new row. Existing versions are never modified.';

-- INDEXES --
CREATE INDEX idx_schema_registry_type_name
    ON attestor.schema_registry (type_name);

CREATE INDEX idx_schema_registry_registered_at
    ON attestor.schema_registry (registered_at);
