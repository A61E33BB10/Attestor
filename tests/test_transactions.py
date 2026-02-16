"""Tests for attestor.ledger.transactions — ledger domain types."""

from __future__ import annotations

import dataclasses
from datetime import date, datetime
from decimal import Decimal

import pytest

from attestor.core.money import NonEmptyStr, PositiveDecimal
from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import UtcDatetime
from attestor.ledger.transactions import (
    Account,
    AccountType,
    DeltaBool,
    DeltaDate,
    DeltaDatetime,
    DeltaDecimal,
    DeltaNull,
    DeltaStr,
    DistinctAccountPair,
    ExecuteResult,
    LedgerEntry,
    Move,
    Position,
    StateDelta,
    Transaction,
)

# ---------------------------------------------------------------------------
# DeltaValue
# ---------------------------------------------------------------------------


class TestDeltaValue:
    def test_delta_decimal(self) -> None:
        assert DeltaDecimal(Decimal("1.5")).value == Decimal("1.5")

    def test_delta_str(self) -> None:
        assert DeltaStr("hello").value == "hello"

    def test_delta_bool(self) -> None:
        assert DeltaBool(True).value is True

    def test_delta_date(self) -> None:
        d = date(2024, 1, 15)
        assert DeltaDate(d).value == d

    def test_delta_datetime(self) -> None:
        dt = datetime(2024, 1, 15, 12, 0)  # noqa: DTZ001
        assert DeltaDatetime(dt).value == dt

    def test_delta_null(self) -> None:
        DeltaNull()  # constructs successfully

    def test_pattern_match(self) -> None:
        values: list[object] = [
            DeltaDecimal(Decimal("1")),
            DeltaStr("s"),
            DeltaBool(False),
            DeltaDate(date.today()),
            DeltaDatetime(datetime.now()),  # noqa: DTZ005
            DeltaNull(),
        ]
        for v in values:
            match v:
                case DeltaDecimal():
                    pass
                case DeltaStr():
                    pass
                case DeltaBool():
                    pass
                case DeltaDate():
                    pass
                case DeltaDatetime():
                    pass
                case DeltaNull():
                    pass
                case _:
                    pytest.fail(f"Unmatched: {v}")


# ---------------------------------------------------------------------------
# AccountType, Account, Position (GAP-33)
# ---------------------------------------------------------------------------


class TestAccountType:
    def test_has_8_variants(self) -> None:
        assert len(AccountType) == 8

    def test_cash_exists(self) -> None:
        assert AccountType.CASH.value == "CASH"


class TestAccount:
    def test_creation(self) -> None:
        acc = Account(
            account_id=unwrap(NonEmptyStr.parse("ACC-001")),
            account_type=AccountType.CASH,
        )
        assert acc.account_id.value == "ACC-001"
        assert acc.account_type == AccountType.CASH

    def test_frozen(self) -> None:
        acc = Account(
            account_id=unwrap(NonEmptyStr.parse("ACC-001")),
            account_type=AccountType.CASH,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            acc.account_type = AccountType.PNL  # type: ignore[misc]


class TestPosition:
    def test_has_fields(self) -> None:
        pos = Position(
            account=unwrap(NonEmptyStr.parse("ACC-001")),
            instrument=unwrap(NonEmptyStr.parse("AAPL")),
            quantity=Decimal("100"),
        )
        assert pos.quantity == Decimal("100")

    def test_frozen(self) -> None:
        pos = Position(
            account=unwrap(NonEmptyStr.parse("ACC-001")),
            instrument=unwrap(NonEmptyStr.parse("AAPL")),
            quantity=Decimal("100"),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            pos.quantity = Decimal("200")  # type: ignore[misc]


class TestExecuteResult:
    def test_has_3_values(self) -> None:
        assert len(ExecuteResult) == 3


# ---------------------------------------------------------------------------
# DistinctAccountPair
# ---------------------------------------------------------------------------


class TestDistinctAccountPair:
    def test_create_valid(self) -> None:
        result = DistinctAccountPair.create("ACC-A", "ACC-B")
        assert isinstance(result, Ok)
        pair = unwrap(result)
        assert pair.debit == "ACC-A"
        assert pair.credit == "ACC-B"

    def test_create_same_account_err(self) -> None:
        result = DistinctAccountPair.create("ACC-A", "ACC-A")
        assert isinstance(result, Err)

    def test_create_empty_debit_err(self) -> None:
        assert isinstance(DistinctAccountPair.create("", "ACC-B"), Err)

    def test_create_empty_credit_err(self) -> None:
        assert isinstance(DistinctAccountPair.create("ACC-A", ""), Err)

    def test_frozen(self) -> None:
        pair = unwrap(DistinctAccountPair.create("A", "B"))
        with pytest.raises(dataclasses.FrozenInstanceError):
            pair.debit = "C"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# StateDelta, Move, Transaction
# ---------------------------------------------------------------------------


class TestStateDelta:
    def test_construction(self) -> None:
        sd = StateDelta(
            unit="AAPL", field="quantity",
            old_value=DeltaDecimal(Decimal("0")),
            new_value=DeltaDecimal(Decimal("100")),
        )
        assert sd.field == "quantity"

    def test_frozen(self) -> None:
        sd = StateDelta("u", "f", DeltaNull(), DeltaStr("x"))
        with pytest.raises(dataclasses.FrozenInstanceError):
            sd.field = "other"  # type: ignore[misc]


class TestMove:
    def test_has_fields(self) -> None:
        qty = unwrap(PositiveDecimal.parse(Decimal("100")))
        m = Move(source="A", destination="B", unit="USD", quantity=qty, contract_id="C-1")
        assert m.source == "A"
        assert m.quantity.value == Decimal("100")

    def test_frozen(self) -> None:
        qty = unwrap(PositiveDecimal.parse(Decimal("1")))
        m = Move("A", "B", "USD", qty, "C")
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.source = "Z"  # type: ignore[misc]

    def test_create_valid(self) -> None:
        qty = unwrap(PositiveDecimal.parse(Decimal("100")))
        result = Move.create("A", "B", "USD", qty, "C-1")
        assert isinstance(result, Ok)
        m = unwrap(result)
        assert m.source == "A"
        assert m.destination == "B"

    def test_create_self_transfer_err(self) -> None:
        """F-HIGH-01: source == destination must be rejected."""
        qty = unwrap(PositiveDecimal.parse(Decimal("100")))
        result = Move.create("A", "A", "USD", qty, "C-1")
        assert isinstance(result, Err)
        assert "differ" in result.error

    def test_create_empty_source_err(self) -> None:
        qty = unwrap(PositiveDecimal.parse(Decimal("100")))
        assert isinstance(Move.create("", "B", "USD", qty, "C"), Err)

    def test_create_empty_destination_err(self) -> None:
        qty = unwrap(PositiveDecimal.parse(Decimal("100")))
        assert isinstance(Move.create("A", "", "USD", qty, "C"), Err)

    def test_create_empty_unit_err(self) -> None:
        qty = unwrap(PositiveDecimal.parse(Decimal("100")))
        assert isinstance(Move.create("A", "B", "", qty, "C"), Err)

    def test_create_empty_contract_id_err(self) -> None:
        qty = unwrap(PositiveDecimal.parse(Decimal("100")))
        assert isinstance(Move.create("A", "B", "USD", qty, ""), Err)


class TestTransaction:
    def test_has_moves_and_timestamp(self) -> None:
        qty = unwrap(PositiveDecimal.parse(Decimal("50")))
        m = Move("A", "B", "USD", qty, "C")
        ts = UtcDatetime.now()
        tx = Transaction(tx_id="TX-1", moves=(m,), timestamp=ts)
        assert len(tx.moves) == 1
        assert tx.timestamp == ts

    def test_state_deltas_default_empty(self) -> None:
        qty = unwrap(PositiveDecimal.parse(Decimal("50")))
        m = Move("A", "B", "USD", qty, "C")
        ts = UtcDatetime.now()
        tx = Transaction(tx_id="TX-1", moves=(m,), timestamp=ts)
        assert tx.state_deltas == ()

    def test_frozen(self) -> None:
        qty = unwrap(PositiveDecimal.parse(Decimal("50")))
        m = Move("A", "B", "USD", qty, "C")
        tx = Transaction(tx_id="TX-1", moves=(m,), timestamp=UtcDatetime.now())
        with pytest.raises(dataclasses.FrozenInstanceError):
            tx.tx_id = "TX-2"  # type: ignore[misc]

    def test_create_valid(self) -> None:
        qty = unwrap(PositiveDecimal.parse(Decimal("50")))
        m = Move("A", "B", "USD", qty, "C")
        ts = UtcDatetime.now()
        result = Transaction.create("TX-1", (m,), ts)
        assert isinstance(result, Ok)
        tx = unwrap(result)
        assert tx.tx_id == "TX-1"
        assert len(tx.moves) == 1

    def test_create_empty_tx_id_err(self) -> None:
        qty = unwrap(PositiveDecimal.parse(Decimal("50")))
        m = Move("A", "B", "USD", qty, "C")
        result = Transaction.create("", (m,), UtcDatetime.now())
        assert isinstance(result, Err)
        assert "tx_id" in result.error

    def test_create_empty_moves_err(self) -> None:
        """F-HIGH-02: empty moves must be rejected."""
        result = Transaction.create("TX-1", (), UtcDatetime.now())
        assert isinstance(result, Err)
        assert "at least one" in result.error


# ---------------------------------------------------------------------------
# LedgerEntry
# ---------------------------------------------------------------------------


class TestLedgerEntry:
    def test_with_valid_distinct_pair(self) -> None:
        pair = unwrap(DistinctAccountPair.create("CASH", "REVENUE"))
        amt = unwrap(PositiveDecimal.parse(Decimal("1000")))
        entry = LedgerEntry(
            accounts=pair, instrument="USD", amount=amt,
            timestamp=UtcDatetime.now(),
        )
        assert entry.instrument == "USD"

    def test_debit_account_property(self) -> None:
        pair = unwrap(DistinctAccountPair.create("CASH", "REVENUE"))
        amt = unwrap(PositiveDecimal.parse(Decimal("1")))
        entry = LedgerEntry(accounts=pair, instrument="USD", amount=amt,
                            timestamp=UtcDatetime.now())
        assert entry.debit_account == "CASH"

    def test_credit_account_property(self) -> None:
        pair = unwrap(DistinctAccountPair.create("CASH", "REVENUE"))
        amt = unwrap(PositiveDecimal.parse(Decimal("1")))
        entry = LedgerEntry(accounts=pair, instrument="USD", amount=amt,
                            timestamp=UtcDatetime.now())
        assert entry.credit_account == "REVENUE"

    def test_frozen(self) -> None:
        pair = unwrap(DistinctAccountPair.create("A", "B"))
        amt = unwrap(PositiveDecimal.parse(Decimal("1")))
        entry = LedgerEntry(accounts=pair, instrument="X", amount=amt,
                            timestamp=UtcDatetime.now())
        with pytest.raises(dataclasses.FrozenInstanceError):
            entry.instrument = "Y"  # type: ignore[misc]

    def test_amount_is_positive_decimal(self) -> None:
        pair = unwrap(DistinctAccountPair.create("A", "B"))
        amt = unwrap(PositiveDecimal.parse(Decimal("42")))
        entry = LedgerEntry(accounts=pair, instrument="X", amount=amt,
                            timestamp=UtcDatetime.now())
        assert entry.amount.value > 0

    def test_optional_attestation(self) -> None:
        pair = unwrap(DistinctAccountPair.create("A", "B"))
        amt = unwrap(PositiveDecimal.parse(Decimal("1")))
        entry = LedgerEntry(accounts=pair, instrument="X", amount=amt,
                            timestamp=UtcDatetime.now())
        assert entry.attestation is None
