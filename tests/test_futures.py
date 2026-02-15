"""Tests for attestor.ledger.futures — position open, variation margin, expiry."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import UtcDatetime
from attestor.ledger.engine import LedgerEngine
from attestor.ledger.futures import (
    create_futures_expiry_transaction,
    create_futures_open_transaction,
    create_variation_margin_transaction,
)
from attestor.ledger.transactions import Account, AccountType

_TS = UtcDatetime(value=datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC))
_CONTRACT = "FUT-ES-2025-12-19"
_SIZE = Decimal("50")  # ES point value


def _setup_engine() -> LedgerEngine:
    engine = LedgerEngine()
    for name, atype in [
        ("LONG-POS", AccountType.DERIVATIVES),
        ("SHORT-POS", AccountType.DERIVATIVES),
        ("LONG-MARGIN", AccountType.MARGIN),
        ("SHORT-MARGIN", AccountType.MARGIN),
        ("LONG-CASH", AccountType.CASH),
        ("SHORT-CASH", AccountType.CASH),
    ]:
        engine.register_account(Account(
            account_id=unwrap(NonEmptyStr.parse(name)),
            account_type=atype,
        ))
    return engine


# ---------------------------------------------------------------------------
# Futures open
# ---------------------------------------------------------------------------


class TestFuturesOpen:
    def test_creates_one_move(self) -> None:
        tx = unwrap(create_futures_open_transaction(
            "ESZ5", "LONG-POS", "SHORT-POS",
            Decimal("5"), _CONTRACT, "TX-FO1", _TS,
        ))
        assert len(tx.moves) == 1
        assert tx.moves[0].unit == _CONTRACT

    def test_direction(self) -> None:
        tx = unwrap(create_futures_open_transaction(
            "ESZ5", "LONG-POS", "SHORT-POS",
            Decimal("5"), _CONTRACT, "TX-FO2", _TS,
        ))
        # short -> long
        assert tx.moves[0].source == "SHORT-POS"
        assert tx.moves[0].destination == "LONG-POS"

    def test_conservation(self) -> None:
        engine = _setup_engine()
        tx = unwrap(create_futures_open_transaction(
            "ESZ5", "LONG-POS", "SHORT-POS",
            Decimal("5"), _CONTRACT, "TX-FO3", _TS,
        ))
        unwrap(engine.execute(tx))
        assert engine.total_supply(_CONTRACT) == Decimal(0)
        assert engine.get_balance("LONG-POS", _CONTRACT) == Decimal("5")
        assert engine.get_balance("SHORT-POS", _CONTRACT) == Decimal("-5")

    def test_zero_quantity_err(self) -> None:
        result = create_futures_open_transaction(
            "ESZ5", "LONG-POS", "SHORT-POS",
            Decimal("0"), _CONTRACT, "TX-FAIL", _TS,
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Variation margin
# ---------------------------------------------------------------------------


class TestVariationMargin:
    def test_price_up_short_pays_long(self) -> None:
        # settlement=5200, prev=5100, size=50, qty=5
        # margin = 100*50*5 = 25000
        tx = unwrap(create_variation_margin_transaction(
            "ESZ5", "LONG-MARGIN", "SHORT-MARGIN",
            Decimal("5200"), Decimal("5100"), _SIZE, Decimal("5"),
            "TX-VM1", _TS,
        ))
        move = tx.moves[0]
        assert move.source == "SHORT-MARGIN"
        assert move.destination == "LONG-MARGIN"
        assert move.quantity.value == Decimal("25000")

    def test_price_down_long_pays_short(self) -> None:
        tx = unwrap(create_variation_margin_transaction(
            "ESZ5", "LONG-MARGIN", "SHORT-MARGIN",
            Decimal("5000"), Decimal("5100"), _SIZE, Decimal("5"),
            "TX-VM2", _TS,
        ))
        move = tx.moves[0]
        assert move.source == "LONG-MARGIN"
        assert move.destination == "SHORT-MARGIN"
        assert move.quantity.value == Decimal("25000")

    def test_price_unchanged_err(self) -> None:
        result = create_variation_margin_transaction(
            "ESZ5", "LONG-MARGIN", "SHORT-MARGIN",
            Decimal("5100"), Decimal("5100"), _SIZE, Decimal("5"),
            "TX-FAIL", _TS,
        )
        assert isinstance(result, Err)
        assert "unchanged" in result.error

    def test_conservation(self) -> None:
        engine = _setup_engine()
        tx = unwrap(create_variation_margin_transaction(
            "ESZ5", "LONG-MARGIN", "SHORT-MARGIN",
            Decimal("5200"), Decimal("5100"), _SIZE, Decimal("5"),
            "TX-VM3", _TS,
        ))
        unwrap(engine.execute(tx))
        assert engine.total_supply("USD") == Decimal(0)


# ---------------------------------------------------------------------------
# Futures expiry
# ---------------------------------------------------------------------------


class TestFuturesExpiry:
    def test_with_final_margin_2_moves(self) -> None:
        tx = unwrap(create_futures_expiry_transaction(
            "ESZ5", "LONG-CASH", "SHORT-CASH",
            "LONG-POS", "SHORT-POS",
            Decimal("5300"), Decimal("5200"), _SIZE, Decimal("5"),
            _CONTRACT, "TX-FE1", _TS,
        ))
        assert len(tx.moves) == 2  # margin + position close

    def test_zero_final_margin_1_move(self) -> None:
        tx = unwrap(create_futures_expiry_transaction(
            "ESZ5", "LONG-CASH", "SHORT-CASH",
            "LONG-POS", "SHORT-POS",
            Decimal("5200"), Decimal("5200"), _SIZE, Decimal("5"),
            _CONTRACT, "TX-FE2", _TS,
        ))
        assert len(tx.moves) == 1  # only position close

    def test_conservation(self) -> None:
        engine = _setup_engine()
        tx = unwrap(create_futures_expiry_transaction(
            "ESZ5", "LONG-CASH", "SHORT-CASH",
            "LONG-POS", "SHORT-POS",
            Decimal("5300"), Decimal("5200"), _SIZE, Decimal("5"),
            _CONTRACT, "TX-FE3", _TS,
        ))
        unwrap(engine.execute(tx))
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply(_CONTRACT) == Decimal(0)


# ---------------------------------------------------------------------------
# Multi-day lifecycle
# ---------------------------------------------------------------------------


class TestMultiDayLifecycle:
    def test_open_3_margins_expiry(self) -> None:
        engine = _setup_engine()
        qty = Decimal("5")

        # Open position
        unwrap(engine.execute(unwrap(create_futures_open_transaction(
            "ESZ5", "LONG-POS", "SHORT-POS",
            qty, _CONTRACT, "TX-OPEN", _TS,
        ))))

        # Day 1: 5100 -> 5200 (+100)
        unwrap(engine.execute(unwrap(create_variation_margin_transaction(
            "ESZ5", "LONG-MARGIN", "SHORT-MARGIN",
            Decimal("5200"), Decimal("5100"), _SIZE, qty,
            "TX-D1", _TS,
        ))))

        # Day 2: 5200 -> 5150 (-50)
        unwrap(engine.execute(unwrap(create_variation_margin_transaction(
            "ESZ5", "LONG-MARGIN", "SHORT-MARGIN",
            Decimal("5150"), Decimal("5200"), _SIZE, qty,
            "TX-D2", _TS,
        ))))

        # Day 3: 5150 -> 5250 (+100)
        unwrap(engine.execute(unwrap(create_variation_margin_transaction(
            "ESZ5", "LONG-MARGIN", "SHORT-MARGIN",
            Decimal("5250"), Decimal("5150"), _SIZE, qty,
            "TX-D3", _TS,
        ))))

        # Expiry: final settlement at 5300, last margin at 5250
        unwrap(engine.execute(unwrap(create_futures_expiry_transaction(
            "ESZ5", "LONG-CASH", "SHORT-CASH",
            "LONG-POS", "SHORT-POS",
            Decimal("5300"), Decimal("5250"), _SIZE, qty,
            _CONTRACT, "TX-EXP", _TS,
        ))))

        # Conservation holds
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply(_CONTRACT) == Decimal(0)

        # Cumulative: (5300 - 5100) * 50 * 5 = 50000 long wins
        long_total = (
            engine.get_balance("LONG-MARGIN", "USD")
            + engine.get_balance("LONG-CASH", "USD")
        )
        assert long_total == Decimal("50000")


# ---------------------------------------------------------------------------
# Property-based
# ---------------------------------------------------------------------------


class TestMarginConservation:
    @given(
        settlement=st.decimals(
            min_value=Decimal("1"), max_value=Decimal("99999"),
            allow_nan=False, allow_infinity=False, places=2,
        ),
        previous=st.decimals(
            min_value=Decimal("1"), max_value=Decimal("99999"),
            allow_nan=False, allow_infinity=False, places=2,
        ),
    )
    def test_conservation_property(
        self, settlement: Decimal, previous: Decimal,
    ) -> None:
        if settlement == previous:
            return  # skip — would return Err
        engine = _setup_engine()
        result = create_variation_margin_transaction(
            "ESZ5", "LONG-MARGIN", "SHORT-MARGIN",
            settlement, previous, _SIZE, Decimal("1"),
            "TX-PBT", _TS,
        )
        assert isinstance(result, Ok)
        unwrap(engine.execute(unwrap(result)))
        assert engine.total_supply("USD") == Decimal(0)
