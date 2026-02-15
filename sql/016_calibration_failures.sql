-- Failed calibration log (append-only)
CREATE TABLE IF NOT EXISTS attestor.calibration_failures (
    failure_id          TEXT        PRIMARY KEY,
    model_class         TEXT        NOT NULL,
    reason              TEXT        NOT NULL,
    failed_checks       JSONB       NOT NULL DEFAULT '[]',
    fallback_config_ref TEXT,
    valid_time          TIMESTAMPTZ NOT NULL,
    system_time         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER prevent_mutation_calibration_failures
    BEFORE UPDATE OR DELETE ON attestor.calibration_failures
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();
