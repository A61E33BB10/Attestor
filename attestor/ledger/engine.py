"""Double-entry bookkeeping engine with conservation law enforcement.

Core invariant (INV-L01): For every unit U,
    sigma(U) = sum_W beta(W, U) is unchanged by every execute().

LedgerEngine is @final but NOT a dataclass — it holds mutable internal state.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import final

from attestor.core.errors import ConservationViolationError
from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, Ok
from attestor.ledger.transactions import (
    Account,
    ExecuteResult,
    Position,
    Transaction,
)


@final
class LedgerEngine:
    """Double-entry bookkeeping engine with conservation law enforcement.

    Core invariant (INV-L01): For every unit U,
        sigma(U) = sum_W beta(W, U) is unchanged by every execute().

    Position index: O(1) lookup by (account, instrument).
    """

    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}
        self._balances: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
        self._transactions: list[Transaction] = []
        self._applied_tx_ids: set[str] = set()

    def register_account(self, account: Account) -> Ok[None] | Err[str]:
        """Register an account in the chart of accounts (INV-L06)."""
        aid = account.account_id.value
        if aid in self._accounts:
            return Err(f"Account already registered: {aid}")
        self._accounts[aid] = account
        return Ok(None)

    def execute(
        self, tx: Transaction,
    ) -> Ok[ExecuteResult] | Err[ConservationViolationError]:
        """Execute a transaction atomically (INV-L05).

        1. Check idempotency (INV-X03): already applied -> Ok(ALREADY_APPLIED)
        2. Verify all accounts exist (INV-L06)
        3. Pre-compute sigma(U) for affected units
        4. Apply all moves: source balance -= qty, dest balance += qty
        5. Post-verify sigma(U) unchanged (INV-L01)
        6. Record transaction
        7. Return Ok(APPLIED)

        On any failure: revert ALL balance changes (INV-L05 atomicity).
        """
        # 1. Idempotency
        if tx.tx_id in self._applied_tx_ids:
            return Ok(ExecuteResult.ALREADY_APPLIED)

        # 2. Account existence
        for move in tx.moves:
            if move.source not in self._accounts:
                return Err(ConservationViolationError(
                    message=f"Source account not registered: {move.source}",
                    code="UNREGISTERED_ACCOUNT",
                    timestamp=tx.timestamp,
                    source="ledger.engine.LedgerEngine.execute",
                    law_name="INV-L06",
                    expected="registered",
                    actual=move.source,
                ))
            if move.destination not in self._accounts:
                return Err(ConservationViolationError(
                    message=f"Destination account not registered: {move.destination}",
                    code="UNREGISTERED_ACCOUNT",
                    timestamp=tx.timestamp,
                    source="ledger.engine.LedgerEngine.execute",
                    law_name="INV-L06",
                    expected="registered",
                    actual=move.destination,
                ))

        # 3. Identify affected units and pre-compute sigma
        affected_units = {m.unit for m in tx.moves}
        pre_sigma = {u: self.total_supply(u) for u in affected_units}

        # 4. Apply moves — save old values for rollback
        old_balances: dict[tuple[str, str], Decimal] = {}
        for move in tx.moves:
            src_key = (move.source, move.unit)
            dst_key = (move.destination, move.unit)
            if src_key not in old_balances:
                old_balances[src_key] = self._balances[src_key]
            if dst_key not in old_balances:
                old_balances[dst_key] = self._balances[dst_key]
            self._balances[src_key] -= move.quantity.value
            self._balances[dst_key] += move.quantity.value

        # 5. Post-verify sigma(U) unchanged (INV-L01)
        for u in affected_units:
            post = self.total_supply(u)
            if pre_sigma[u] != post:
                # REVERT (INV-L05 atomicity)
                for key, val in old_balances.items():
                    self._balances[key] = val
                return Err(ConservationViolationError(
                    message=f"Conservation violated for unit {u}",
                    code="CONSERVATION_VIOLATION",
                    timestamp=tx.timestamp,
                    source="ledger.engine.LedgerEngine.execute",
                    law_name="INV-L01",
                    expected=str(pre_sigma[u]),
                    actual=str(post),
                ))

        # 6. Record transaction
        self._transactions.append(tx)
        self._applied_tx_ids.add(tx.tx_id)

        # 7. Return success
        return Ok(ExecuteResult.APPLIED)

    def get_balance(self, account_id: str, instrument: str) -> Decimal:
        """O(1) balance lookup."""
        return self._balances.get((account_id, instrument), Decimal(0))

    def get_position(self, account_id: str, instrument: str) -> Position:
        """Return Position for (account, instrument)."""
        return Position(
            account=NonEmptyStr(value=account_id),
            instrument=NonEmptyStr(value=instrument),
            quantity=self.get_balance(account_id, instrument),
        )

    def positions(self) -> tuple[Position, ...]:
        """All non-zero positions."""
        return tuple(
            Position(
                account=NonEmptyStr(value=acct),
                instrument=NonEmptyStr(value=inst),
                quantity=qty,
            )
            for (acct, inst), qty in sorted(self._balances.items())
            if qty != 0
        )

    def total_supply(self, instrument: str) -> Decimal:
        """sigma(U) — sum of all balances for instrument across all accounts."""
        total = Decimal(0)
        for (_, inst), qty in self._balances.items():
            if inst == instrument:
                total += qty
        return total

    def clone(self) -> LedgerEngine:
        """Deep copy for time-travel (INV-L09)."""
        new = LedgerEngine()
        new._accounts = dict(self._accounts)
        new._balances = defaultdict(Decimal, self._balances)
        new._transactions = list(self._transactions)
        new._applied_tx_ids = set(self._applied_tx_ids)
        return new

    def transaction_count(self) -> int:
        """Number of applied transactions."""
        return len(self._transactions)
