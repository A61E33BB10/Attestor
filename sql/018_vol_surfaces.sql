-- Volatility surfaces store (append-only, bitemporal)
CREATE TABLE IF NOT EXISTS attestor.vol_surfaces (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    attestation_id  TEXT NOT NULL UNIQUE,
    underlying      TEXT NOT NULL,
    as_of           DATE NOT NULL,
    model_config_ref TEXT NOT NULL,
    slices_json     JSONB NOT NULL,
    valid_time      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    system_time     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER prevent_mutation_vol_surfaces
    BEFORE UPDATE OR DELETE ON attestor.vol_surfaces
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();
