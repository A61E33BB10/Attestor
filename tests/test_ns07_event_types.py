"""NS7b tests — event-common type enrichment to CDM Rosetta.

Tests cover:
- ClosedState: activity_date (renamed), effective_date, last_payment_date
- Trade: execution_type, execution_venue, cleared_date
- TradeState: observation_history, valuation_history
- BusinessEvent: after as tuple, event_date, effective_date,
  event_qualifier, corporate_action_intent
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from attestor.core.money import NonEmptyStr
from attestor.core.party import CounterpartyRoleEnum
from attestor.core.result import Ok
from attestor.core.types import PayerReceiver, UtcDatetime
from attestor.instrument.lifecycle import (
    ActionEnum,
    BusinessEvent,
    ClosedState,
    ClosedStateEnum,
    CorporateActionTypeEnum,
    EventIntentEnum,
    ExecutionTypeEnum,
    QuantityChangePI,
    Trade,
    TradeState,
)
from attestor.instrument.types import PositionStatusEnum

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PR = PayerReceiver(
    payer=CounterpartyRoleEnum.PARTY1,
    receiver=CounterpartyRoleEnum.PARTY2,
)


def _nes(s: str) -> NonEmptyStr:
    r = NonEmptyStr.parse(s)
    assert isinstance(r, Ok)
    return r.value


_USD = _nes("USD")
_TRADE1 = _nes("TRADE-001")
_PROD1 = _nes("IRS-5Y-USD")


def _make_trade(**kwargs: object) -> Trade:
    defaults: dict[str, object] = {
        "trade_id": _TRADE1,
        "trade_date": date(2025, 1, 15),
        "payer_receiver": _PR,
        "product_id": _PROD1,
        "currency": _USD,
    }
    defaults.update(kwargs)
    return Trade(**defaults)  # type: ignore[arg-type]


def _make_trade_state(
    status: PositionStatusEnum = PositionStatusEnum.FORMED,
) -> TradeState:
    cs = None
    if status == PositionStatusEnum.CLOSED:
        cs = ClosedState(
            state=ClosedStateEnum.MATURED,
            activity_date=date(2030, 1, 15),
        )
    return TradeState(trade=_make_trade(), status=status, closed_state=cs)


# ---------------------------------------------------------------------------
# ClosedState enrichment
# ---------------------------------------------------------------------------


class TestClosedStateEnrichment:
    def test_activity_date_field(self) -> None:
        cs = ClosedState(
            state=ClosedStateEnum.MATURED,
            activity_date=date(2030, 1, 15),
        )
        assert cs.activity_date == date(2030, 1, 15)

    def test_effective_date_optional(self) -> None:
        cs = ClosedState(
            state=ClosedStateEnum.TERMINATED,
            activity_date=date(2030, 6, 1),
        )
        assert cs.effective_date is None

    def test_effective_date_set(self) -> None:
        cs = ClosedState(
            state=ClosedStateEnum.TERMINATED,
            activity_date=date(2030, 6, 1),
            effective_date=date(2030, 6, 15),
        )
        assert cs.effective_date == date(2030, 6, 15)

    def test_last_payment_date_optional(self) -> None:
        cs = ClosedState(
            state=ClosedStateEnum.NOVATED,
            activity_date=date(2030, 3, 1),
        )
        assert cs.last_payment_date is None

    def test_last_payment_date_set(self) -> None:
        cs = ClosedState(
            state=ClosedStateEnum.NOVATED,
            activity_date=date(2030, 3, 1),
            last_payment_date=date(2030, 2, 28),
        )
        assert cs.last_payment_date == date(2030, 2, 28)

    def test_all_fields_set(self) -> None:
        cs = ClosedState(
            state=ClosedStateEnum.EXERCISED,
            activity_date=date(2030, 5, 1),
            effective_date=date(2030, 5, 3),
            last_payment_date=date(2030, 4, 30),
        )
        assert cs.state == ClosedStateEnum.EXERCISED
        assert cs.activity_date == date(2030, 5, 1)
        assert cs.effective_date == date(2030, 5, 3)
        assert cs.last_payment_date == date(2030, 4, 30)

    def test_frozen(self) -> None:
        cs = ClosedState(
            state=ClosedStateEnum.CANCELLED,
            activity_date=date(2030, 1, 1),
        )
        with pytest.raises(AttributeError):
            cs.activity_date = date(2031, 1, 1)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Trade enrichment
# ---------------------------------------------------------------------------


class TestTradeEnrichment:
    def test_execution_type_default_none(self) -> None:
        t = _make_trade()
        assert t.execution_type is None

    def test_execution_type_set(self) -> None:
        t = _make_trade(execution_type=ExecutionTypeEnum.OFF_FACILITY)
        assert t.execution_type == ExecutionTypeEnum.OFF_FACILITY

    def test_execution_venue_default_none(self) -> None:
        t = _make_trade()
        assert t.execution_venue is None

    def test_execution_venue_set(self) -> None:
        t = _make_trade(
            execution_type=ExecutionTypeEnum.ELECTRONIC,
            execution_venue=_nes("XNAS"),
        )
        assert t.execution_venue is not None
        assert t.execution_venue.value == "XNAS"

    def test_cleared_date_default_none(self) -> None:
        t = _make_trade()
        assert t.cleared_date is None

    def test_cleared_date_set(self) -> None:
        t = _make_trade(cleared_date=date(2025, 1, 16))
        assert t.cleared_date == date(2025, 1, 16)

    def test_all_new_fields(self) -> None:
        t = _make_trade(
            execution_type=ExecutionTypeEnum.ON_VENUE,
            execution_venue=_nes("XLON"),
            cleared_date=date(2025, 1, 17),
        )
        assert t.execution_type == ExecutionTypeEnum.ON_VENUE
        assert t.execution_venue is not None
        assert t.execution_venue.value == "XLON"
        assert t.cleared_date == date(2025, 1, 17)

    def test_frozen(self) -> None:
        t = _make_trade(
            execution_type=ExecutionTypeEnum.ELECTRONIC,
            execution_venue=_nes("XNAS"),
        )
        with pytest.raises(AttributeError):
            t.execution_type = None  # type: ignore[misc]

    def test_venue_without_type_rejected(self) -> None:
        with pytest.raises(TypeError, match="execution_venue requires execution_type"):
            _make_trade(execution_venue=_nes("XNAS"))

    def test_electronic_without_venue_rejected(self) -> None:
        with pytest.raises(TypeError, match="ELECTRONIC.*requires execution_venue"):
            _make_trade(execution_type=ExecutionTypeEnum.ELECTRONIC)

    def test_off_facility_without_venue_ok(self) -> None:
        t = _make_trade(execution_type=ExecutionTypeEnum.OFF_FACILITY)
        assert t.execution_type == ExecutionTypeEnum.OFF_FACILITY
        assert t.execution_venue is None


# ---------------------------------------------------------------------------
# TradeState enrichment
# ---------------------------------------------------------------------------


class TestTradeStateEnrichment:
    def test_observation_history_default_empty(self) -> None:
        ts = _make_trade_state()
        assert ts.observation_history == ()

    def test_valuation_history_default_empty(self) -> None:
        ts = _make_trade_state()
        assert ts.valuation_history == ()

    def test_observation_history_set(self) -> None:
        t1 = UtcDatetime.now()
        t2 = UtcDatetime.now()
        ts = TradeState(
            trade=_make_trade(),
            status=PositionStatusEnum.SETTLED,
            observation_history=(t1, t2),
        )
        assert len(ts.observation_history) == 2

    def test_valuation_history_set(self) -> None:
        t1 = UtcDatetime.now()
        ts = TradeState(
            trade=_make_trade(),
            status=PositionStatusEnum.FORMED,
            valuation_history=(t1,),
        )
        assert len(ts.valuation_history) == 1


# ---------------------------------------------------------------------------
# BusinessEvent enrichment
# ---------------------------------------------------------------------------


class TestBusinessEventEnrichment:
    def _make_pi(self) -> QuantityChangePI:
        return QuantityChangePI(
            instrument_id=_TRADE1,
            quantity_change=Decimal("-1000"),
            effective_date=date(2025, 6, 15),
        )

    def test_after_default_empty_tuple(self) -> None:
        ev = BusinessEvent(
            instruction=self._make_pi(),
            timestamp=UtcDatetime.now(),
        )
        assert ev.after == ()

    def test_after_single_trade_state(self) -> None:
        after = _make_trade_state(PositionStatusEnum.SETTLED)
        ev = BusinessEvent(
            instruction=self._make_pi(),
            timestamp=UtcDatetime.now(),
            after=(after,),
        )
        assert len(ev.after) == 1
        assert ev.after[0].status == PositionStatusEnum.SETTLED

    def test_after_multiple_trade_states(self) -> None:
        """Split events produce multiple output trades."""
        a1 = _make_trade_state(PositionStatusEnum.FORMED)
        a2 = _make_trade_state(PositionStatusEnum.FORMED)
        ev = BusinessEvent(
            instruction=self._make_pi(),
            timestamp=UtcDatetime.now(),
            after=(a1, a2),
        )
        assert len(ev.after) == 2

    def test_event_date_default_none(self) -> None:
        ev = BusinessEvent(
            instruction=self._make_pi(),
            timestamp=UtcDatetime.now(),
        )
        assert ev.event_date is None

    def test_event_date_set(self) -> None:
        ev = BusinessEvent(
            instruction=self._make_pi(),
            timestamp=UtcDatetime.now(),
            event_date=date(2025, 6, 15),
        )
        assert ev.event_date == date(2025, 6, 15)

    def test_effective_date_default_none(self) -> None:
        ev = BusinessEvent(
            instruction=self._make_pi(),
            timestamp=UtcDatetime.now(),
        )
        assert ev.effective_date is None

    def test_effective_date_set(self) -> None:
        ev = BusinessEvent(
            instruction=self._make_pi(),
            timestamp=UtcDatetime.now(),
            effective_date=date(2025, 6, 17),
        )
        assert ev.effective_date == date(2025, 6, 17)

    def test_event_qualifier_default_none(self) -> None:
        ev = BusinessEvent(
            instruction=self._make_pi(),
            timestamp=UtcDatetime.now(),
        )
        assert ev.event_qualifier is None

    def test_event_qualifier_set(self) -> None:
        ev = BusinessEvent(
            instruction=self._make_pi(),
            timestamp=UtcDatetime.now(),
            event_qualifier=_nes("PartialTermination"),
        )
        assert ev.event_qualifier is not None
        assert ev.event_qualifier.value == "PartialTermination"

    def test_corporate_action_intent_default_none(self) -> None:
        ev = BusinessEvent(
            instruction=self._make_pi(),
            timestamp=UtcDatetime.now(),
        )
        assert ev.corporate_action_intent is None

    def test_corporate_action_intent_set(self) -> None:
        ev = BusinessEvent(
            instruction=self._make_pi(),
            timestamp=UtcDatetime.now(),
            event_intent=EventIntentEnum.CORPORATE_ACTION_ADJUSTMENT,
            corporate_action_intent=CorporateActionTypeEnum.STOCK_SPLIT,
        )
        assert ev.corporate_action_intent == CorporateActionTypeEnum.STOCK_SPLIT

    def test_corporate_action_intent_wrong_intent_rejected(self) -> None:
        with pytest.raises(TypeError, match="CORPORATE_ACTION_ADJUSTMENT"):
            BusinessEvent(
                instruction=self._make_pi(),
                timestamp=UtcDatetime.now(),
                event_intent=EventIntentEnum.NOVATION,
                corporate_action_intent=CorporateActionTypeEnum.STOCK_SPLIT,
            )

    def test_all_new_fields(self) -> None:
        before = _make_trade_state(PositionStatusEnum.SETTLED)
        after = _make_trade_state(PositionStatusEnum.CLOSED)
        ev = BusinessEvent(
            instruction=self._make_pi(),
            timestamp=UtcDatetime.now(),
            before=before,
            after=(after,),
            event_intent=EventIntentEnum.CORPORATE_ACTION_ADJUSTMENT,
            action=ActionEnum.NEW,
            event_date=date(2025, 6, 15),
            effective_date=date(2025, 6, 17),
            event_qualifier=_nes("CorporateActionAdjustment"),
            corporate_action_intent=CorporateActionTypeEnum.CASH_DIVIDEND,
        )
        assert ev.event_date == date(2025, 6, 15)
        assert ev.effective_date == date(2025, 6, 17)
        assert ev.event_qualifier is not None
        assert ev.event_qualifier.value == "CorporateActionAdjustment"
        assert ev.corporate_action_intent == CorporateActionTypeEnum.CASH_DIVIDEND
        assert len(ev.after) == 1

    def test_frozen(self) -> None:
        ev = BusinessEvent(
            instruction=self._make_pi(),
            timestamp=UtcDatetime.now(),
            event_date=date(2025, 6, 15),
        )
        with pytest.raises(AttributeError):
            ev.event_date = date(2026, 1, 1)  # type: ignore[misc]
