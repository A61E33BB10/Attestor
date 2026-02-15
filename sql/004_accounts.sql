-- =============================================================================
-- 004_accounts.sql
-- Chart of accounts: account registry for double-entry bookkeeping.
-- Append-only: no UPDATE/DELETE. Enforced by trigger.
-- =============================================================================

CREATE TABLE attestor.accounts (
    account_id      TEXT            NOT NULL,
    account_type    TEXT            NOT NULL
                    CHECK (account_type IN (
                        'CASH', 'SECURITIES', 'DERIVATIVES',
                        'COLLATERAL', 'MARGIN', 'ACCRUALS', 'PNL'
                    )),
    owner_party_id  TEXT            NOT NULL
                    CHECK (length(owner_party_id) > 0),
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_accounts PRIMARY KEY (account_id),
    CONSTRAINT chk_account_id_nonempty CHECK (length(account_id) > 0)
);

-- Immutability trigger: reject UPDATE and DELETE
CREATE TRIGGER trg_accounts_immutable
    BEFORE UPDATE OR DELETE ON attestor.accounts
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();

COMMENT ON TABLE attestor.accounts IS
    'Chart of accounts for double-entry bookkeeping. Append-only.';
