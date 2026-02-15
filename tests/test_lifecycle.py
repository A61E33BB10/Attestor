"""Tests for attestor.instrument.lifecycle — transitions, PrimitiveInstruction, BusinessEvent."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from attestor.core.money import Money, NonEmptyStr, PositiveDecimal
from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import UtcDatetime
from attestor.gateway.types import CanonicalOrder, OrderSide, OrderType
from attestor.instrument.lifecycle import (
    EQUITY_TRANSITIONS,
    BusinessEvent,
    DividendPI,
    ExecutePI,
    PrimitiveInstruction,
    TransferPI,
    check_transition,
)
from attestor.instrument.types import PositionStatusEnum

_TS = UtcDatetime(value=datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC))


# ---------------------------------------------------------------------------
# Valid transitions
# ---------------------------------------------------------------------------


class TestValidTransitions:
    def test_proposed_to_formed(self) -> None:
        result = check_transition(PositionStatusEnum.PROPOSED, PositionStatusEnum.FORMED)
        assert isinstance(result, Ok)

    def test_proposed_to_cancelled(self) -> None:
        result = check_transition(PositionStatusEnum.PROPOSED, PositionStatusEnum.CANCELLED)
        assert isinstance(result, Ok)

    def test_formed_to_settled(self) -> None:
        result = check_transition(PositionStatusEnum.FORMED, PositionStatusEnum.SETTLED)
        assert isinstance(result, Ok)

    def test_formed_to_cancelled(self) -> None:
        result = check_transition(PositionStatusEnum.FORMED, PositionStatusEnum.CANCELLED)
        assert isinstance(result, Ok)

    def test_settled_to_closed(self) -> None:
        result = check_transition(PositionStatusEnum.SETTLED, PositionStatusEnum.CLOSED)
        assert isinstance(result, Ok)

    def test_all_five_transitions_exist(self) -> None:
        assert len(EQUITY_TRANSITIONS) == 5


# ---------------------------------------------------------------------------
# Invalid transitions
# ---------------------------------------------------------------------------


class TestInvalidTransitions:
    def test_proposed_to_settled(self) -> None:
        result = check_transition(PositionStatusEnum.PROPOSED, PositionStatusEnum.SETTLED)
        assert isinstance(result, Err)
        assert result.error.from_state == "Proposed"
        assert result.error.to_state == "Settled"

    def test_formed_to_proposed(self) -> None:
        result = check_transition(PositionStatusEnum.FORMED, PositionStatusEnum.PROPOSED)
        assert isinstance(result, Err)

    def test_settled_to_formed(self) -> None:
        result = check_transition(PositionStatusEnum.SETTLED, PositionStatusEnum.FORMED)
        assert isinstance(result, Err)

    def test_cancelled_to_anything(self) -> None:
        for to_state in PositionStatusEnum:
            result = check_transition(PositionStatusEnum.CANCELLED, to_state)
            assert isinstance(result, Err)

    def test_closed_to_anything(self) -> None:
        for to_state in PositionStatusEnum:
            result = check_transition(PositionStatusEnum.CLOSED, to_state)
            assert isinstance(result, Err)

    def test_same_state(self) -> None:
        for state in PositionStatusEnum:
            result = check_transition(state, state)
            assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# PrimitiveInstruction
# ---------------------------------------------------------------------------


class TestPrimitiveInstruction:
    def test_execute_pi(self) -> None:
        order = unwrap(CanonicalOrder.create(
            order_id="ORD-001", instrument_id="AAPL", isin=None,
            side=OrderSide.BUY, quantity=Decimal("100"), price=Decimal("175.50"),
            currency="USD", order_type=OrderType.LIMIT,
            counterparty_lei="529900HNOAA1KXQJUQ27",
            executing_party_lei="529900ODI3JL1O4COU11",
            trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 17),
            venue="XNYS", timestamp=_TS,
        ))
        pi = ExecutePI(order=order)
        assert isinstance(pi.order, CanonicalOrder)

    def test_transfer_pi(self) -> None:
        pi = TransferPI(
            instrument_id=unwrap(NonEmptyStr.parse("AAPL")),
            quantity=unwrap(PositiveDecimal.parse(Decimal("100"))),
            cash_amount=unwrap(Money.create(Decimal("17550"), "USD")),
            from_account=unwrap(NonEmptyStr.parse("BUYER_CASH")),
            to_account=unwrap(NonEmptyStr.parse("SELLER_CASH")),
        )
        assert pi.instrument_id.value == "AAPL"

    def test_dividend_pi(self) -> None:
        pi = DividendPI(
            instrument_id=unwrap(NonEmptyStr.parse("AAPL")),
            amount_per_share=unwrap(PositiveDecimal.parse(Decimal("0.82"))),
            ex_date=date(2025, 8, 11),
            payment_date=date(2025, 8, 14),
            currency=unwrap(NonEmptyStr.parse("USD")),
        )
        assert pi.amount_per_share.value == Decimal("0.82")

    def test_pattern_match_exhaustive(self) -> None:
        """Pattern matching on PrimitiveInstruction covers all variants."""
        order = unwrap(CanonicalOrder.create(
            order_id="ORD-001", instrument_id="AAPL", isin=None,
            side=OrderSide.BUY, quantity=Decimal("100"), price=Decimal("175.50"),
            currency="USD", order_type=OrderType.LIMIT,
            counterparty_lei="529900HNOAA1KXQJUQ27",
            executing_party_lei="529900ODI3JL1O4COU11",
            trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 17),
            venue="XNYS", timestamp=_TS,
        ))
        instructions: list[PrimitiveInstruction] = [
            ExecutePI(order=order),
            TransferPI(
                instrument_id=unwrap(NonEmptyStr.parse("AAPL")),
                quantity=unwrap(PositiveDecimal.parse(Decimal("100"))),
                cash_amount=unwrap(Money.create(Decimal("17550"), "USD")),
                from_account=unwrap(NonEmptyStr.parse("A")),
                to_account=unwrap(NonEmptyStr.parse("B")),
            ),
            DividendPI(
                instrument_id=unwrap(NonEmptyStr.parse("AAPL")),
                amount_per_share=unwrap(PositiveDecimal.parse(Decimal("0.82"))),
                ex_date=date(2025, 8, 11), payment_date=date(2025, 8, 14),
                currency=unwrap(NonEmptyStr.parse("USD")),
            ),
        ]
        matched = 0
        for pi in instructions:
            match pi:
                case ExecutePI():
                    matched += 1
                case TransferPI():
                    matched += 1
                case DividendPI():
                    matched += 1
        assert matched == 3


# ---------------------------------------------------------------------------
# BusinessEvent
# ---------------------------------------------------------------------------


class TestBusinessEvent:
    def test_creation(self) -> None:
        order = unwrap(CanonicalOrder.create(
            order_id="ORD-001", instrument_id="AAPL", isin=None,
            side=OrderSide.BUY, quantity=Decimal("100"), price=Decimal("175.50"),
            currency="USD", order_type=OrderType.LIMIT,
            counterparty_lei="529900HNOAA1KXQJUQ27",
            executing_party_lei="529900ODI3JL1O4COU11",
            trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 17),
            venue="XNYS", timestamp=_TS,
        ))
        event = BusinessEvent(instruction=ExecutePI(order=order), timestamp=_TS)
        assert event.attestation_id is None

    def test_with_attestation_id(self) -> None:
        order = unwrap(CanonicalOrder.create(
            order_id="ORD-001", instrument_id="AAPL", isin=None,
            side=OrderSide.BUY, quantity=Decimal("100"), price=Decimal("175.50"),
            currency="USD", order_type=OrderType.LIMIT,
            counterparty_lei="529900HNOAA1KXQJUQ27",
            executing_party_lei="529900ODI3JL1O4COU11",
            trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 17),
            venue="XNYS", timestamp=_TS,
        ))
        event = BusinessEvent(
            instruction=ExecutePI(order=order), timestamp=_TS,
            attestation_id="abc123",
        )
        assert event.attestation_id == "abc123"
