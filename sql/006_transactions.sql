-- =============================================================================
-- 006_transactions.sql
-- Transaction log: append-only ledger of all executed transactions.
-- Each transaction contains one or more moves (JSONB).
-- =============================================================================

CREATE TABLE attestor.transactions (
    tx_id           TEXT            NOT NULL,
    moves           JSONB           NOT NULL,
    state_deltas    JSONB           NOT NULL DEFAULT '[]'::jsonb,
    executed_at     TIMESTAMPTZ     NOT NULL,
    system_time     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_transactions PRIMARY KEY (tx_id),
    CONSTRAINT chk_tx_id_nonempty CHECK (length(tx_id) > 0)
);

-- Immutability trigger: reject UPDATE and DELETE
CREATE TRIGGER trg_transactions_immutable
    BEFORE UPDATE OR DELETE ON attestor.transactions
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();

CREATE INDEX idx_transactions_executed_at
    ON attestor.transactions (executed_at);

COMMENT ON TABLE attestor.transactions IS
    'Append-only transaction log. Each row is an atomic batch of moves.';
