-- Yield curve store (append-only, bitemporal)
CREATE TABLE IF NOT EXISTS attestor.yield_curves (
    curve_id         TEXT        PRIMARY KEY,
    currency         TEXT        NOT NULL,
    as_of            DATE        NOT NULL,
    tenors           DECIMAL[]   NOT NULL,
    discount_factors DECIMAL[]   NOT NULL,
    confidence_payload JSONB     NOT NULL DEFAULT '{}',
    model_config_ref TEXT        NOT NULL,
    valid_time       TIMESTAMPTZ NOT NULL,
    system_time      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER prevent_mutation_yield_curves
    BEFORE UPDATE OR DELETE ON attestor.yield_curves
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();
