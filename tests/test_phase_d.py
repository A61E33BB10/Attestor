"""Phase D: Event and Lifecycle Alignment — comprehensive tests.

Covers all new and enriched types:
- ClosedStateEnum, TransferStatusEnum, EventIntentEnum,
  CorporateActionTypeEnum, ActionEnum
- QuantityChangePI, PartyChangePI, SplitPI, TermsChangePI, IndexTransitionPI
- ClosedState, Trade, TradeState
- Enriched BusinessEvent (before/after, event_intent, action, event_ref)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import get_args

import pytest

from attestor.core.money import NonEmptyStr
from attestor.core.party import CounterpartyRoleEnum
from attestor.core.result import Ok
from attestor.core.types import (
    FrozenMap,
    PayerReceiver,
    Period,
    UtcDatetime,
)
from attestor.instrument.lifecycle import (
    ActionEnum,
    BusinessEvent,
    ClosedState,
    ClosedStateEnum,
    CorporateActionTypeEnum,
    EventIntentEnum,
    IndexTransitionPI,
    PartyChangePI,
    PrimitiveInstruction,
    QuantityChangePI,
    SplitPI,
    TermsChangePI,
    Trade,
    TradeState,
    TransferStatusEnum,
)
from attestor.instrument.types import PositionStatusEnum
from attestor.oracle.observable import FloatingRateIndex, FloatingRateIndexEnum

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PR = PayerReceiver(payer=CounterpartyRoleEnum.PARTY1, receiver=CounterpartyRoleEnum.PARTY2)


def _nes(s: str) -> NonEmptyStr:
    r = NonEmptyStr.parse(s)
    assert isinstance(r, Ok)
    return r.value


_USD = _nes("USD")
_ACME = _nes("ACME")
_BIGCO = _nes("BigCo")
_TRADE1 = _nes("TRADE-001")
_TRADE2 = _nes("TRADE-002")
_TRADE3 = _nes("TRADE-003")
_PROD1 = _nes("IRS-5Y-USD")

_SOFR = FloatingRateIndex(
    index=FloatingRateIndexEnum.SOFR,
    designated_maturity=Period(1, "D"),
)
_EURIBOR = FloatingRateIndex(
    index=FloatingRateIndexEnum.EURIBOR,
    designated_maturity=Period(3, "M"),
)


# ---------------------------------------------------------------------------
# ClosedStateEnum
# ---------------------------------------------------------------------------


class TestClosedStateEnum:
    def test_count(self) -> None:
        assert len(ClosedStateEnum) == 7

    def test_members(self) -> None:
        expected = {
            "ALLOCATED", "CANCELLED", "EXERCISED",
            "EXPIRED", "MATURED", "NOVATED", "TERMINATED",
        }
        actual = {e.name for e in ClosedStateEnum}
        assert actual == expected


# ---------------------------------------------------------------------------
# TransferStatusEnum
# ---------------------------------------------------------------------------


class TestTransferStatusEnum:
    def test_count(self) -> None:
        assert len(TransferStatusEnum) == 5

    def test_members(self) -> None:
        expected = {
            "PENDING", "INSTRUCTED", "SETTLED", "NETTED", "DISPUTED",
        }
        actual = {e.name for e in TransferStatusEnum}
        assert actual == expected


# ---------------------------------------------------------------------------
# EventIntentEnum
# ---------------------------------------------------------------------------


class TestEventIntentEnum:
    def test_count(self) -> None:
        assert len(EventIntentEnum) == 23

    def test_key_members(self) -> None:
        assert EventIntentEnum.NOVATION.value == "Novation"
        assert EventIntentEnum.OPTION_EXERCISE.value == "OptionExercise"
        assert EventIntentEnum.INDEX_TRANSITION.value == "IndexTransition"


# ---------------------------------------------------------------------------
# CorporateActionTypeEnum
# ---------------------------------------------------------------------------


class TestCorporateActionTypeEnum:
    def test_count(self) -> None:
        assert len(CorporateActionTypeEnum) == 20

    def test_members(self) -> None:
        expected = {
            "BANKRUPTCY_OR_INSOLVENCY", "BESPOKE_EVENT", "BONUS_ISSUE",
            "CASH_DIVIDEND", "CLASS_ACTION", "DELISTING",
            "EARLY_REDEMPTION", "ISSUER_NATIONALIZATION", "LIQUIDATION",
            "MERGER", "RELISTING", "REVERSE_STOCK_SPLIT",
            "RIGHTS_ISSUE", "SPIN_OFF", "STOCK_DIVIDEND",
            "STOCK_IDENTIFIER_CHANGE", "STOCK_NAME_CHANGE",
            "STOCK_RECLASSIFICATION", "STOCK_SPLIT", "TAKEOVER",
        }
        actual = {e.name for e in CorporateActionTypeEnum}
        assert actual == expected


# ---------------------------------------------------------------------------
# ActionEnum
# ---------------------------------------------------------------------------


class TestActionEnum:
    def test_count(self) -> None:
        assert len(ActionEnum) == 3

    def test_members(self) -> None:
        expected = {"NEW", "CORRECT", "CANCEL"}
        actual = {e.name for e in ActionEnum}
        assert actual == expected


# ---------------------------------------------------------------------------
# QuantityChangePI
# ---------------------------------------------------------------------------


class TestQuantityChangePI:
    def test_valid_decrease(self) -> None:
        pi = QuantityChangePI(
            instrument_id=_TRADE1,
            quantity_change=Decimal("-5000000"),
            effective_date=date(2025, 6, 15),
        )
        assert pi.quantity_change == Decimal("-5000000")

    def test_valid_increase(self) -> None:
        pi = QuantityChangePI(
            instrument_id=_TRADE1,
            quantity_change=Decimal("1000000"),
            effective_date=date(2025, 6, 15),
        )
        assert pi.quantity_change == Decimal("1000000")

    def test_zero_rejected(self) -> None:
        with pytest.raises(TypeError, match="must be non-zero"):
            QuantityChangePI(
                instrument_id=_TRADE1,
                quantity_change=Decimal("0"),
                effective_date=date(2025, 6, 15),
            )

    def test_nan_rejected(self) -> None:
        with pytest.raises(TypeError, match="finite Decimal"):
            QuantityChangePI(
                instrument_id=_TRADE1,
                quantity_change=Decimal("NaN"),
                effective_date=date(2025, 6, 15),
            )

    def test_infinity_rejected(self) -> None:
        with pytest.raises(TypeError, match="finite Decimal"):
            QuantityChangePI(
                instrument_id=_TRADE1,
                quantity_change=Decimal("Infinity"),
                effective_date=date(2025, 6, 15),
            )

    def test_frozen(self) -> None:
        pi = QuantityChangePI(
            instrument_id=_TRADE1,
            quantity_change=Decimal("-1000"),
            effective_date=date(2025, 6, 15),
        )
        with pytest.raises(AttributeError):
            pi.quantity_change = Decimal("0")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PartyChangePI
# ---------------------------------------------------------------------------


class TestPartyChangePI:
    def test_valid(self) -> None:
        pi = PartyChangePI(
            instrument_id=_TRADE1,
            old_party=_ACME,
            new_party=_BIGCO,
            effective_date=date(2025, 6, 15),
        )
        assert pi.old_party == _ACME
        assert pi.new_party == _BIGCO

    def test_same_party_rejected(self) -> None:
        with pytest.raises(TypeError, match="must differ"):
            PartyChangePI(
                instrument_id=_TRADE1,
                old_party=_ACME,
                new_party=_ACME,
                effective_date=date(2025, 6, 15),
            )


# ---------------------------------------------------------------------------
# SplitPI
# ---------------------------------------------------------------------------


class TestSplitPI:
    def test_valid(self) -> None:
        pi = SplitPI(
            instrument_id=_TRADE1,
            split_into=(_TRADE2, _TRADE3),
            effective_date=date(2025, 6, 15),
        )
        assert len(pi.split_into) == 2

    def test_single_rejected(self) -> None:
        with pytest.raises(TypeError, match="at least 2"):
            SplitPI(
                instrument_id=_TRADE1,
                split_into=(_TRADE2,),
                effective_date=date(2025, 6, 15),
            )

    def test_empty_rejected(self) -> None:
        with pytest.raises(TypeError, match="at least 2"):
            SplitPI(
                instrument_id=_TRADE1,
                split_into=(),
                effective_date=date(2025, 6, 15),
            )

    def test_duplicate_ids_rejected(self) -> None:
        with pytest.raises(TypeError, match="distinct trade IDs"):
            SplitPI(
                instrument_id=_TRADE1,
                split_into=(_TRADE2, _TRADE2),
                effective_date=date(2025, 6, 15),
            )


# ---------------------------------------------------------------------------
# TermsChangePI
# ---------------------------------------------------------------------------


class TestTermsChangePI:
    def test_valid(self) -> None:
        fm_r = FrozenMap.create({"fixed_rate": "0.035"})
        assert isinstance(fm_r, Ok)
        pi = TermsChangePI(
            instrument_id=_TRADE1,
            changed_fields=fm_r.value,
            effective_date=date(2025, 6, 15),
        )
        assert pi.changed_fields["fixed_rate"] == "0.035"

    def test_empty_rejected(self) -> None:
        fm_r = FrozenMap.create({})
        assert isinstance(fm_r, Ok)
        with pytest.raises(TypeError, match="at least one entry"):
            TermsChangePI(
                instrument_id=_TRADE1,
                changed_fields=fm_r.value,
                effective_date=date(2025, 6, 15),
            )


# ---------------------------------------------------------------------------
# IndexTransitionPI
# ---------------------------------------------------------------------------


class TestIndexTransitionPI:
    def test_valid(self) -> None:
        pi = IndexTransitionPI(
            instrument_id=_TRADE1,
            old_index=_EURIBOR,
            new_index=_SOFR,
            spread_adjustment=Decimal("0.0026161"),
            effective_date=date(2025, 1, 1),
        )
        assert pi.old_index.index == FloatingRateIndexEnum.EURIBOR
        assert pi.new_index.index == FloatingRateIndexEnum.SOFR
        assert pi.spread_adjustment == Decimal("0.0026161")

    def test_same_index_rejected(self) -> None:
        with pytest.raises(TypeError, match="must differ"):
            IndexTransitionPI(
                instrument_id=_TRADE1,
                old_index=_SOFR,
                new_index=_SOFR,
                spread_adjustment=Decimal("0"),
                effective_date=date(2025, 1, 1),
            )

    def test_nan_spread_rejected(self) -> None:
        with pytest.raises(TypeError, match="finite Decimal"):
            IndexTransitionPI(
                instrument_id=_TRADE1,
                old_index=_EURIBOR,
                new_index=_SOFR,
                spread_adjustment=Decimal("NaN"),
                effective_date=date(2025, 1, 1),
            )


# ---------------------------------------------------------------------------
# PrimitiveInstruction union updated
# ---------------------------------------------------------------------------


class TestPrimitiveInstructionUnionPhaseD:
    def test_has_18_variants(self) -> None:
        args = get_args(PrimitiveInstruction)
        assert len(args) == 18

    def test_new_variants_present(self) -> None:
        args = get_args(PrimitiveInstruction)
        names = {t.__name__ for t in args}
        assert "QuantityChangePI" in names
        assert "PartyChangePI" in names
        assert "SplitPI" in names
        assert "TermsChangePI" in names
        assert "IndexTransitionPI" in names


# ---------------------------------------------------------------------------
# ClosedState
# ---------------------------------------------------------------------------


class TestClosedState:
    def test_valid(self) -> None:
        cs = ClosedState(
            state=ClosedStateEnum.MATURED,
            effective_date=date(2030, 1, 15),
        )
        assert cs.state == ClosedStateEnum.MATURED

    def test_frozen(self) -> None:
        cs = ClosedState(
            state=ClosedStateEnum.MATURED,
            effective_date=date(2030, 1, 15),
        )
        with pytest.raises(AttributeError):
            cs.state = ClosedStateEnum.TERMINATED  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Trade
# ---------------------------------------------------------------------------


class TestTrade:
    def test_valid_with_agreement(self) -> None:
        t = Trade(
            trade_id=_TRADE1,
            trade_date=date(2025, 1, 15),
            payer_receiver=_PR,
            product_id=_PROD1,
            currency=_USD,
            legal_agreement_id=_nes("ISDA-2002-001"),
        )
        assert t.trade_id == _TRADE1
        assert t.legal_agreement_id is not None

    def test_valid_without_agreement(self) -> None:
        t = Trade(
            trade_id=_TRADE1,
            trade_date=date(2025, 1, 15),
            payer_receiver=_PR,
            product_id=_PROD1,
            currency=_USD,
        )
        assert t.legal_agreement_id is None

    def test_frozen(self) -> None:
        t = Trade(
            trade_id=_TRADE1,
            trade_date=date(2025, 1, 15),
            payer_receiver=_PR,
            product_id=_PROD1,
            currency=_USD,
        )
        with pytest.raises(AttributeError):
            t.trade_date = date(2025, 2, 1)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TradeState
# ---------------------------------------------------------------------------


class TestTradeState:
    def _make_trade(self) -> Trade:
        return Trade(
            trade_id=_TRADE1,
            trade_date=date(2025, 1, 15),
            payer_receiver=_PR,
            product_id=_PROD1,
            currency=_USD,
        )

    def test_valid_open(self) -> None:
        ts = TradeState(
            trade=self._make_trade(),
            status=PositionStatusEnum.FORMED,
        )
        assert ts.closed_state is None
        assert ts.reset_history == ()
        assert ts.transfer_history == ()

    def test_valid_closed(self) -> None:
        cs = ClosedState(
            state=ClosedStateEnum.MATURED,
            effective_date=date(2030, 1, 15),
        )
        ts = TradeState(
            trade=self._make_trade(),
            status=PositionStatusEnum.CLOSED,
            closed_state=cs,
        )
        assert ts.closed_state is not None
        assert ts.closed_state.state == ClosedStateEnum.MATURED

    def test_closed_without_state_rejected(self) -> None:
        with pytest.raises(TypeError, match="closed_state is required"):
            TradeState(
                trade=self._make_trade(),
                status=PositionStatusEnum.CLOSED,
            )

    def test_open_with_closed_state_rejected(self) -> None:
        cs = ClosedState(
            state=ClosedStateEnum.TERMINATED,
            effective_date=date(2025, 6, 15),
        )
        with pytest.raises(TypeError, match="closed_state must be None"):
            TradeState(
                trade=self._make_trade(),
                status=PositionStatusEnum.FORMED,
                closed_state=cs,
            )

    def test_with_histories(self) -> None:
        t1 = UtcDatetime.now()
        t2 = UtcDatetime.now()
        ts = TradeState(
            trade=self._make_trade(),
            status=PositionStatusEnum.SETTLED,
            reset_history=(t1,),
            transfer_history=(t1, t2),
        )
        assert len(ts.reset_history) == 1
        assert len(ts.transfer_history) == 2

    def test_frozen(self) -> None:
        ts = TradeState(
            trade=self._make_trade(),
            status=PositionStatusEnum.FORMED,
        )
        with pytest.raises(AttributeError):
            ts.status = PositionStatusEnum.SETTLED  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Enriched BusinessEvent
# ---------------------------------------------------------------------------


class TestBusinessEventEnrichment:
    def _make_trade_state(
        self, status: PositionStatusEnum = PositionStatusEnum.FORMED,
    ) -> TradeState:
        trade = Trade(
            trade_id=_TRADE1,
            trade_date=date(2025, 1, 15),
            payer_receiver=_PR,
            product_id=_PROD1,
            currency=_USD,
        )
        cs = None
        if status == PositionStatusEnum.CLOSED:
            cs = ClosedState(
                state=ClosedStateEnum.MATURED,
                effective_date=date(2030, 1, 15),
            )
        return TradeState(trade=trade, status=status, closed_state=cs)

    def test_backward_compatible(self) -> None:
        """Existing code without Phase D fields still works."""
        pi = QuantityChangePI(
            instrument_id=_TRADE1,
            quantity_change=Decimal("-1000000"),
            effective_date=date(2025, 6, 15),
        )
        ev = BusinessEvent(
            instruction=pi,
            timestamp=UtcDatetime.now(),
        )
        assert ev.before is None
        assert ev.after is None
        assert ev.event_intent is None
        assert ev.action == ActionEnum.NEW
        assert ev.event_ref is None

    def test_with_state_snapshots(self) -> None:
        before = self._make_trade_state(PositionStatusEnum.FORMED)
        after = self._make_trade_state(PositionStatusEnum.SETTLED)
        pi = QuantityChangePI(
            instrument_id=_TRADE1,
            quantity_change=Decimal("-5000000"),
            effective_date=date(2025, 6, 15),
        )
        ev = BusinessEvent(
            instruction=pi,
            timestamp=UtcDatetime.now(),
            before=before,
            after=after,
            event_intent=EventIntentEnum.DECREASE,
            action=ActionEnum.NEW,
            event_ref=_nes("TX-12345"),
        )
        assert ev.before is not None
        assert ev.after is not None
        assert ev.event_intent == EventIntentEnum.DECREASE
        assert ev.event_ref is not None

    def test_action_default_is_new(self) -> None:
        pi = QuantityChangePI(
            instrument_id=_TRADE1,
            quantity_change=Decimal("-1000"),
            effective_date=date(2025, 6, 15),
        )
        ev = BusinessEvent(
            instruction=pi,
            timestamp=UtcDatetime.now(),
        )
        assert ev.action == ActionEnum.NEW

    def test_correction_action(self) -> None:
        pi = QuantityChangePI(
            instrument_id=_TRADE1,
            quantity_change=Decimal("-1000"),
            effective_date=date(2025, 6, 15),
        )
        ev = BusinessEvent(
            instruction=pi,
            timestamp=UtcDatetime.now(),
            action=ActionEnum.CORRECT,
        )
        assert ev.action == ActionEnum.CORRECT

    def test_old_execute_pi_still_works(self) -> None:
        """Ensure pre-Phase D ExecutePI still works in BusinessEvent."""
        # ExecutePI requires a CanonicalOrder; just verify it's in the union
        args = get_args(PrimitiveInstruction)
        names = {t.__name__ for t in args}
        assert "ExecutePI" in names


# ---------------------------------------------------------------------------
# Conservation property: TradeState status-closed_state coupling
# ---------------------------------------------------------------------------


class TestTradeStateConservation:
    def test_all_closed_reasons_constructable(self) -> None:
        """Every ClosedStateEnum value can be used in a closed TradeState."""
        trade = Trade(
            trade_id=_TRADE1,
            trade_date=date(2025, 1, 15),
            payer_receiver=_PR,
            product_id=_PROD1,
            currency=_USD,
        )
        for reason in ClosedStateEnum:
            cs = ClosedState(state=reason, effective_date=date(2030, 1, 15))
            ts = TradeState(
                trade=trade,
                status=PositionStatusEnum.CLOSED,
                closed_state=cs,
            )
            assert ts.closed_state.state == reason

    def test_non_closed_statuses_reject_closed_state(self) -> None:
        """Every non-CLOSED status rejects a closed_state."""
        trade = Trade(
            trade_id=_TRADE1,
            trade_date=date(2025, 1, 15),
            payer_receiver=_PR,
            product_id=_PROD1,
            currency=_USD,
        )
        cs = ClosedState(
            state=ClosedStateEnum.MATURED,
            effective_date=date(2030, 1, 15),
        )
        for status in PositionStatusEnum:
            if status == PositionStatusEnum.CLOSED:
                continue
            with pytest.raises(TypeError, match="closed_state must be None"):
                TradeState(trade=trade, status=status, closed_state=cs)
