"""Tests for derivative lifecycle — ExercisePI, AssignPI, ExpiryPI, MarginPI."""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from attestor.core.money import Money, NonEmptyStr
from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import UtcDatetime
from attestor.gateway.types import CanonicalOrder, OrderSide, OrderType
from attestor.instrument.derivative_types import (
    MarginType,
    OptionDetail,
    OptionExerciseStyleEnum,
    OptionTypeEnum,
    SettlementType,
)
from attestor.instrument.lifecycle import (
    DERIVATIVE_TRANSITIONS,
    AssignPI,
    BusinessEvent,
    ExercisePI,
    ExpiryPI,
    MarginPI,
    check_transition,
)
from attestor.instrument.types import PositionStatusEnum

_TS = UtcDatetime(value=datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC))
_LEI_A = "529900HNOAA1KXQJUQ27"
_LEI_B = "529900ODI3JL1O4COU11"


def _option_order() -> CanonicalOrder:
    detail = unwrap(OptionDetail.create(
        strike=Decimal("150"), expiry_date=date(2025, 12, 19),
        option_type=OptionTypeEnum.CALL, option_style=OptionExerciseStyleEnum.AMERICAN,
        settlement_type=SettlementType.PHYSICAL, underlying_id="AAPL",
    ))
    return unwrap(CanonicalOrder.create(
        order_id="OPT-001", instrument_id="AAPL251219C00150000",
        isin=None, side=OrderSide.BUY, quantity=Decimal("10"),
        price=Decimal("5.50"), currency="USD", order_type=OrderType.LIMIT,
        counterparty_lei=_LEI_A, executing_party_lei=_LEI_B,
        trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 16),
        venue="CBOE", timestamp=_TS, instrument_detail=detail,
    ))


# ---------------------------------------------------------------------------
# ExercisePI
# ---------------------------------------------------------------------------


class TestExercisePI:
    def test_construction(self) -> None:
        order = _option_order()
        pi = ExercisePI(order=order)
        assert pi.order.order_id.value == "OPT-001"

    def test_frozen(self) -> None:
        pi = ExercisePI(order=_option_order())
        with pytest.raises(dataclasses.FrozenInstanceError):
            pi.order = _option_order()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AssignPI
# ---------------------------------------------------------------------------


class TestAssignPI:
    def test_construction(self) -> None:
        order = _option_order()
        pi = AssignPI(order=order)
        assert pi.order.instrument_id.value == "AAPL251219C00150000"

    def test_frozen(self) -> None:
        pi = AssignPI(order=_option_order())
        with pytest.raises(dataclasses.FrozenInstanceError):
            pi.order = _option_order()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ExpiryPI
# ---------------------------------------------------------------------------


class TestExpiryPI:
    def test_construction(self) -> None:
        iid = unwrap(NonEmptyStr.parse("AAPL251219C00150000"))
        pi = ExpiryPI(instrument_id=iid, expiry_date=date(2025, 12, 19))
        assert pi.expiry_date == date(2025, 12, 19)

    def test_frozen(self) -> None:
        iid = unwrap(NonEmptyStr.parse("AAPL251219C00150000"))
        pi = ExpiryPI(instrument_id=iid, expiry_date=date(2025, 12, 19))
        with pytest.raises(dataclasses.FrozenInstanceError):
            pi.expiry_date = date(2026, 1, 1)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MarginPI
# ---------------------------------------------------------------------------


class TestMarginPI:
    def test_variation_margin(self) -> None:
        iid = unwrap(NonEmptyStr.parse("ESZ5"))
        amount = unwrap(Money.create(Decimal("5000"), "USD"))
        pi = MarginPI(
            instrument_id=iid, margin_amount=amount,
            margin_type=MarginType.VARIATION,
        )
        assert pi.margin_type == MarginType.VARIATION
        assert pi.margin_amount.amount == Decimal("5000")

    def test_initial_margin(self) -> None:
        iid = unwrap(NonEmptyStr.parse("ESZ5"))
        amount = unwrap(Money.create(Decimal("15000"), "USD"))
        pi = MarginPI(
            instrument_id=iid, margin_amount=amount,
            margin_type=MarginType.INITIAL,
        )
        assert pi.margin_type == MarginType.INITIAL

    def test_frozen(self) -> None:
        iid = unwrap(NonEmptyStr.parse("ESZ5"))
        amount = unwrap(Money.create(Decimal("5000"), "USD"))
        pi = MarginPI(instrument_id=iid, margin_amount=amount,
                      margin_type=MarginType.VARIATION)
        with pytest.raises(dataclasses.FrozenInstanceError):
            pi.margin_type = MarginType.INITIAL  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Derivative transitions (parameterized check_transition)
# ---------------------------------------------------------------------------


class TestDerivativeTransitions:
    def test_proposed_to_formed(self) -> None:
        result = check_transition(
            PositionStatusEnum.PROPOSED, PositionStatusEnum.FORMED,
            transitions=DERIVATIVE_TRANSITIONS,
        )
        assert isinstance(result, Ok)

    def test_formed_to_settled(self) -> None:
        result = check_transition(
            PositionStatusEnum.FORMED, PositionStatusEnum.SETTLED,
            transitions=DERIVATIVE_TRANSITIONS,
        )
        assert isinstance(result, Ok)

    def test_invalid_transition(self) -> None:
        result = check_transition(
            PositionStatusEnum.SETTLED, PositionStatusEnum.PROPOSED,
            transitions=DERIVATIVE_TRANSITIONS,
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Pattern matching
# ---------------------------------------------------------------------------


class TestPatternMatch:
    def test_exhaustive_match_on_derivative_pis(self) -> None:
        from attestor.instrument.lifecycle import DividendPI, ExecutePI, TransferPI

        order = _option_order()
        iid = unwrap(NonEmptyStr.parse("ESZ5"))
        amount = unwrap(Money.create(Decimal("5000"), "USD"))
        pis: list[object] = [
            ExercisePI(order=order),
            AssignPI(order=order),
            ExpiryPI(instrument_id=iid, expiry_date=date(2025, 12, 19)),
            MarginPI(instrument_id=iid, margin_amount=amount,
                     margin_type=MarginType.VARIATION),
        ]
        for pi in pis:
            match pi:
                case ExecutePI():
                    pytest.fail("Should not match ExecutePI")
                case TransferPI():
                    pytest.fail("Should not match TransferPI")
                case DividendPI():
                    pytest.fail("Should not match DividendPI")
                case ExercisePI():
                    pass
                case AssignPI():
                    pass
                case ExpiryPI():
                    pass
                case MarginPI():
                    pass
                case _:
                    pytest.fail(f"Unmatched: {pi}")


# ---------------------------------------------------------------------------
# BusinessEvent with derivative PI
# ---------------------------------------------------------------------------


class TestBusinessEventDerivative:
    def test_wraps_exercise_pi(self) -> None:
        pi = ExercisePI(order=_option_order())
        event = BusinessEvent(instruction=pi, timestamp=_TS)
        assert isinstance(event.instruction, ExercisePI)

    def test_wraps_margin_pi(self) -> None:
        iid = unwrap(NonEmptyStr.parse("ESZ5"))
        amount = unwrap(Money.create(Decimal("5000"), "USD"))
        pi = MarginPI(instrument_id=iid, margin_amount=amount,
                      margin_type=MarginType.INITIAL)
        event = BusinessEvent(instruction=pi, timestamp=_TS)
        assert isinstance(event.instruction, MarginPI)
