-- Model configuration attestation store (append-only)
CREATE TABLE IF NOT EXISTS attestor.model_configs (
    config_id             TEXT        NOT NULL,
    model_class           TEXT        NOT NULL,
    parameters            JSONB       NOT NULL,
    code_version          TEXT        NOT NULL,
    calibration_timestamp TIMESTAMPTZ NOT NULL,
    fit_quality           JSONB       NOT NULL DEFAULT '{}',
    attestation_ref       TEXT,
    valid_time            TIMESTAMPTZ NOT NULL,
    system_time           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (config_id, code_version, calibration_timestamp)
);

CREATE TRIGGER prevent_mutation_model_configs
    BEFORE UPDATE OR DELETE ON attestor.model_configs
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();
