-- FX rate history (append-only, bitemporal)
CREATE TABLE IF NOT EXISTS attestor.fx_rates (
    rate_id      TEXT        PRIMARY KEY,
    pair         TEXT        NOT NULL,
    rate         DECIMAL     NOT NULL,
    confidence   TEXT        NOT NULL CHECK (confidence IN ('firm', 'quoted')),
    valid_time   TIMESTAMPTZ NOT NULL,
    system_time  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER prevent_mutation_fx_rates
    BEFORE UPDATE OR DELETE ON attestor.fx_rates
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();
