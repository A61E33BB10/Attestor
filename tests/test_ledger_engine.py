"""Tests for attestor.ledger.engine — LedgerEngine conservation, atomicity, idempotency."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from attestor.core.money import NonEmptyStr, PositiveDecimal
from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import UtcDatetime
from attestor.ledger.engine import LedgerEngine
from attestor.ledger.transactions import (
    Account,
    AccountType,
    ExecuteResult,
    Move,
    Position,
    Transaction,
)

_TS = UtcDatetime(value=datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC))


def _acct(aid: str, atype: AccountType = AccountType.CASH) -> Account:
    return Account(account_id=NonEmptyStr(value=aid), account_type=atype)


def _move(src: str, dst: str, unit: str, qty: str, contract: str = "C1") -> Move:
    return Move(
        source=src, destination=dst, unit=unit,
        quantity=unwrap(PositiveDecimal.parse(Decimal(qty))),
        contract_id=contract,
    )


def _tx(tx_id: str, moves: tuple[Move, ...], ts: UtcDatetime = _TS) -> Transaction:
    return Transaction(tx_id=tx_id, moves=moves, timestamp=ts)


# ---------------------------------------------------------------------------
# Account registration
# ---------------------------------------------------------------------------


class TestAccountRegistration:
    def test_register_account(self) -> None:
        engine = LedgerEngine()
        result = engine.register_account(_acct("A"))
        assert isinstance(result, Ok)

    def test_duplicate_account(self) -> None:
        engine = LedgerEngine()
        engine.register_account(_acct("A"))
        result = engine.register_account(_acct("A"))
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Simple execute
# ---------------------------------------------------------------------------


class TestSimpleExecute:
    def test_single_move(self) -> None:
        engine = LedgerEngine()
        engine.register_account(_acct("A"))
        engine.register_account(_acct("B"))
        tx = _tx("TX1", (_move("A", "B", "USD", "100"),))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert result.value is ExecuteResult.APPLIED
        assert engine.get_balance("A", "USD") == Decimal("-100")
        assert engine.get_balance("B", "USD") == Decimal("100")

    def test_multi_move_transaction(self) -> None:
        """Settlement pattern: cash + securities in one tx."""
        engine = LedgerEngine()
        for a in ("BUYER_CASH", "SELLER_CASH", "BUYER_SEC", "SELLER_SEC"):
            engine.register_account(_acct(a))
        tx = _tx("TX1", (
            _move("BUYER_CASH", "SELLER_CASH", "USD", "17550"),
            _move("SELLER_SEC", "BUYER_SEC", "AAPL", "100"),
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert engine.get_balance("BUYER_CASH", "USD") == Decimal("-17550")
        assert engine.get_balance("SELLER_CASH", "USD") == Decimal("17550")
        assert engine.get_balance("SELLER_SEC", "AAPL") == Decimal("-100")
        assert engine.get_balance("BUYER_SEC", "AAPL") == Decimal("100")

    def test_transaction_count(self) -> None:
        engine = LedgerEngine()
        engine.register_account(_acct("A"))
        engine.register_account(_acct("B"))
        assert engine.transaction_count() == 0
        engine.execute(_tx("TX1", (_move("A", "B", "USD", "50"),)))
        assert engine.transaction_count() == 1
        engine.execute(_tx("TX2", (_move("B", "A", "USD", "25"),)))
        assert engine.transaction_count() == 2


# ---------------------------------------------------------------------------
# Conservation law (INV-L01)
# ---------------------------------------------------------------------------


class TestConservation:
    def test_sigma_preserved_single_move(self) -> None:
        engine = LedgerEngine()
        engine.register_account(_acct("A"))
        engine.register_account(_acct("B"))
        pre = engine.total_supply("USD")
        engine.execute(_tx("TX1", (_move("A", "B", "USD", "100"),)))
        post = engine.total_supply("USD")
        assert pre == post == Decimal(0)

    def test_sigma_preserved_multi_move(self) -> None:
        engine = LedgerEngine()
        for a in ("A", "B", "C"):
            engine.register_account(_acct(a))
        engine.execute(_tx("TX1", (
            _move("A", "B", "USD", "100"),
            _move("B", "C", "USD", "50"),
        )))
        assert engine.total_supply("USD") == Decimal(0)

    @given(
        amounts=st.lists(
            st.decimals(min_value=Decimal("0.01"), max_value=Decimal("1000000"),
                        places=2, allow_nan=False, allow_infinity=False),
            min_size=1, max_size=10,
        ),
    )
    @settings(max_examples=200)
    def test_sigma_preserved_hypothesis(self, amounts: list[Decimal]) -> None:
        """INV-L01: sigma(U) == 0 after arbitrary moves between 2 accounts."""
        engine = LedgerEngine()
        engine.register_account(_acct("A"))
        engine.register_account(_acct("B"))
        for i, amt in enumerate(amounts):
            move = _move("A", "B", "USD", str(amt))
            engine.execute(_tx(f"TX-{i}", (move,)))
        assert engine.total_supply("USD") == Decimal(0)


# ---------------------------------------------------------------------------
# Atomicity (INV-L05)
# ---------------------------------------------------------------------------


class TestAtomicity:
    def test_unregistered_source_reverts(self) -> None:
        engine = LedgerEngine()
        engine.register_account(_acct("A"))
        # "B" not registered — tx should fail
        tx = _tx("TX1", (_move("A", "B", "USD", "100"),))
        result = engine.execute(tx)
        assert isinstance(result, Err)
        assert engine.get_balance("A", "USD") == Decimal(0)
        assert engine.transaction_count() == 0

    def test_unregistered_destination_reverts(self) -> None:
        engine = LedgerEngine()
        engine.register_account(_acct("A"))
        tx = _tx("TX1", (_move("B", "A", "USD", "100"),))
        result = engine.execute(tx)
        assert isinstance(result, Err)
        assert engine.get_balance("A", "USD") == Decimal(0)


# ---------------------------------------------------------------------------
# Idempotency (INV-X03)
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_same_tx_id_twice(self) -> None:
        engine = LedgerEngine()
        engine.register_account(_acct("A"))
        engine.register_account(_acct("B"))
        tx = _tx("TX1", (_move("A", "B", "USD", "100"),))
        r1 = engine.execute(tx)
        r2 = engine.execute(tx)
        assert isinstance(r1, Ok) and r1.value is ExecuteResult.APPLIED
        assert isinstance(r2, Ok) and r2.value is ExecuteResult.ALREADY_APPLIED
        assert engine.get_balance("B", "USD") == Decimal("100")
        assert engine.transaction_count() == 1


# ---------------------------------------------------------------------------
# Chart of accounts (INV-L06)
# ---------------------------------------------------------------------------


class TestChartOfAccounts:
    def test_move_to_unregistered_account(self) -> None:
        engine = LedgerEngine()
        engine.register_account(_acct("A"))
        tx = _tx("TX1", (_move("A", "UNKNOWN", "USD", "100"),))
        result = engine.execute(tx)
        assert isinstance(result, Err)
        assert "UNKNOWN" in result.error.actual

    def test_move_from_unregistered_account(self) -> None:
        engine = LedgerEngine()
        engine.register_account(_acct("B"))
        tx = _tx("TX1", (_move("GHOST", "B", "USD", "100"),))
        result = engine.execute(tx)
        assert isinstance(result, Err)
        assert "GHOST" in result.error.actual


# ---------------------------------------------------------------------------
# Clone independence (INV-L09)
# ---------------------------------------------------------------------------


class TestClone:
    def test_clone_independence(self) -> None:
        engine = LedgerEngine()
        engine.register_account(_acct("A"))
        engine.register_account(_acct("B"))
        engine.execute(_tx("TX1", (_move("A", "B", "USD", "100"),)))

        clone = engine.clone()
        # Clone has same state
        assert clone.get_balance("A", "USD") == Decimal("-100")
        assert clone.get_balance("B", "USD") == Decimal("100")
        assert clone.transaction_count() == 1

        # Mutate clone
        clone.execute(_tx("TX2", (_move("B", "A", "USD", "50"),)))
        assert clone.get_balance("A", "USD") == Decimal("-50")

        # Original unaffected
        assert engine.get_balance("A", "USD") == Decimal("-100")
        assert engine.transaction_count() == 1

    def test_clone_idempotency_independence(self) -> None:
        """Clone's applied_tx_ids are independent."""
        engine = LedgerEngine()
        engine.register_account(_acct("A"))
        engine.register_account(_acct("B"))
        engine.execute(_tx("TX1", (_move("A", "B", "USD", "100"),)))

        clone = engine.clone()
        # TX1 already applied in clone
        r = clone.execute(_tx("TX1", (_move("A", "B", "USD", "100"),)))
        assert isinstance(r, Ok) and r.value is ExecuteResult.ALREADY_APPLIED

        # New TX in clone doesn't affect original
        clone.execute(_tx("TX2", (_move("B", "A", "USD", "50"),)))
        assert engine.transaction_count() == 1


# ---------------------------------------------------------------------------
# Position tracking
# ---------------------------------------------------------------------------


class TestPositionTracking:
    def test_get_balance_default_zero(self) -> None:
        engine = LedgerEngine()
        assert engine.get_balance("NONEXISTENT", "USD") == Decimal(0)

    def test_get_position(self) -> None:
        engine = LedgerEngine()
        engine.register_account(_acct("A"))
        engine.register_account(_acct("B"))
        engine.execute(_tx("TX1", (_move("A", "B", "USD", "200"),)))
        pos = engine.get_position("B", "USD")
        assert pos.account.value == "B"
        assert pos.instrument.value == "USD"
        assert pos.quantity == Decimal("200")

    def test_positions_excludes_zero(self) -> None:
        engine = LedgerEngine()
        engine.register_account(_acct("A"))
        engine.register_account(_acct("B"))
        engine.execute(_tx("TX1", (_move("A", "B", "USD", "100"),)))
        engine.execute(_tx("TX2", (_move("B", "A", "USD", "100"),)))
        # Both balances back to zero
        positions = engine.positions()
        assert len(positions) == 0

    def test_positions_non_zero_only(self) -> None:
        engine = LedgerEngine()
        engine.register_account(_acct("A"))
        engine.register_account(_acct("B"))
        engine.register_account(_acct("C"))
        engine.execute(_tx("TX1", (_move("A", "B", "USD", "100"),)))
        engine.execute(_tx("TX2", (_move("A", "C", "EUR", "50"),)))
        positions = engine.positions()
        # A has -100 USD and -50 EUR, B has 100 USD, C has 50 EUR = 4 non-zero
        assert len(positions) == 4

    def test_total_supply(self) -> None:
        engine = LedgerEngine()
        engine.register_account(_acct("A"))
        engine.register_account(_acct("B"))
        engine.register_account(_acct("C"))
        engine.execute(_tx("TX1", (_move("A", "B", "USD", "100"),)))
        engine.execute(_tx("TX2", (_move("B", "C", "USD", "30"),)))
        # sigma(USD) should still be 0 — all started at 0
        assert engine.total_supply("USD") == Decimal(0)

    def test_total_supply_distinct_instruments(self) -> None:
        engine = LedgerEngine()
        engine.register_account(_acct("A"))
        engine.register_account(_acct("B"))
        engine.execute(_tx("TX1", (_move("A", "B", "USD", "100"),)))
        engine.execute(_tx("TX2", (_move("A", "B", "EUR", "200"),)))
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply("EUR") == Decimal(0)
        assert engine.total_supply("GBP") == Decimal(0)


# ---------------------------------------------------------------------------
# Error messages
# ---------------------------------------------------------------------------


class TestErrorMessages:
    def test_conservation_error_has_law_name(self) -> None:
        """Unregistered account error carries INV-L06."""
        engine = LedgerEngine()
        engine.register_account(_acct("A"))
        tx = _tx("TX1", (_move("A", "MISSING", "USD", "100"),))
        result = engine.execute(tx)
        assert isinstance(result, Err)
        assert result.error.law_name == "INV-L06"
        assert result.error.code == "UNREGISTERED_ACCOUNT"
