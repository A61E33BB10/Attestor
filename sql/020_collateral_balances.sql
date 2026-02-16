-- Collateral balances ledger (mutable for balance updates)
CREATE TABLE IF NOT EXISTS attestor.collateral_balances (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    agreement_id    TEXT NOT NULL,
    party           TEXT NOT NULL,
    collateral_type TEXT NOT NULL CHECK (collateral_type IN ('CASH', 'GOVERNMENT_BOND', 'CORPORATE_BOND', 'EQUITY')),
    quantity        NUMERIC(28,10) NOT NULL,
    currency        TEXT NOT NULL,
    valid_time      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    system_time     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (agreement_id, party, collateral_type)
);

CREATE TRIGGER prevent_mutation_collateral_balances
    BEFORE UPDATE OR DELETE ON attestor.collateral_balances
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();
