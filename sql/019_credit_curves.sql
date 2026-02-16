-- Credit curves store (append-only, bitemporal)
CREATE TABLE IF NOT EXISTS attestor.credit_curves (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    attestation_id  TEXT NOT NULL UNIQUE,
    reference_entity TEXT NOT NULL,
    as_of           DATE NOT NULL,
    tenors_json     JSONB NOT NULL,
    survival_probs_json JSONB NOT NULL,
    hazard_rates_json JSONB NOT NULL,
    recovery_rate   NUMERIC(10,6) NOT NULL CHECK (recovery_rate >= 0 AND recovery_rate < 1),
    model_config_ref TEXT NOT NULL,
    valid_time      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    system_time     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER prevent_mutation_credit_curves
    BEFORE UPDATE OR DELETE ON attestor.credit_curves
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();
