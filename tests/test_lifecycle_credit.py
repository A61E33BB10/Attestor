"""Tests for CDS / Swaption / Collateral lifecycle -- transitions and PI variants."""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
from typing import get_args

import pytest

from attestor.core.money import Money, NonEmptyStr
from attestor.core.result import Err, Ok, unwrap
from attestor.instrument.derivative_types import CreditEventType
from attestor.instrument.lifecycle import (
    CDS_TRANSITIONS,
    SWAPTION_TRANSITIONS,
    CollateralCallPI,
    CreditEventPI,
    PrimitiveInstruction,
    SwaptionCashSettlement,
    SwaptionExercisePI,
    SwaptionPhysicalSettlement,
    check_transition,
)
from attestor.instrument.types import PositionStatusEnum

# ---------------------------------------------------------------------------
# CDS_TRANSITIONS
# ---------------------------------------------------------------------------


class TestCDSTransitions:
    def test_has_5_edges(self) -> None:
        assert len(CDS_TRANSITIONS) == 5

    def test_proposed_to_formed(self) -> None:
        assert isinstance(
            check_transition(
                PositionStatusEnum.PROPOSED, PositionStatusEnum.FORMED,
                CDS_TRANSITIONS,
            ),
            Ok,
        )

    def test_proposed_to_cancelled(self) -> None:
        assert isinstance(
            check_transition(
                PositionStatusEnum.PROPOSED, PositionStatusEnum.CANCELLED,
                CDS_TRANSITIONS,
            ),
            Ok,
        )

    def test_formed_to_settled(self) -> None:
        assert isinstance(
            check_transition(
                PositionStatusEnum.FORMED, PositionStatusEnum.SETTLED,
                CDS_TRANSITIONS,
            ),
            Ok,
        )

    def test_formed_to_cancelled(self) -> None:
        assert isinstance(
            check_transition(
                PositionStatusEnum.FORMED, PositionStatusEnum.CANCELLED,
                CDS_TRANSITIONS,
            ),
            Ok,
        )

    def test_settled_to_closed(self) -> None:
        assert isinstance(
            check_transition(
                PositionStatusEnum.SETTLED, PositionStatusEnum.CLOSED,
                CDS_TRANSITIONS,
            ),
            Ok,
        )

    def test_invalid_settled_to_formed(self) -> None:
        assert isinstance(
            check_transition(
                PositionStatusEnum.SETTLED, PositionStatusEnum.FORMED,
                CDS_TRANSITIONS,
            ),
            Err,
        )

    def test_cancelled_terminal(self) -> None:
        for to_state in PositionStatusEnum:
            assert isinstance(
                check_transition(
                    PositionStatusEnum.CANCELLED, to_state, CDS_TRANSITIONS,
                ),
                Err,
            )


# ---------------------------------------------------------------------------
# SWAPTION_TRANSITIONS
# ---------------------------------------------------------------------------


class TestSwaptionTransitions:
    def test_has_5_edges(self) -> None:
        assert len(SWAPTION_TRANSITIONS) == 5

    def test_proposed_to_formed(self) -> None:
        assert isinstance(
            check_transition(
                PositionStatusEnum.PROPOSED, PositionStatusEnum.FORMED,
                SWAPTION_TRANSITIONS,
            ),
            Ok,
        )

    def test_proposed_to_cancelled(self) -> None:
        assert isinstance(
            check_transition(
                PositionStatusEnum.PROPOSED, PositionStatusEnum.CANCELLED,
                SWAPTION_TRANSITIONS,
            ),
            Ok,
        )

    def test_formed_to_settled(self) -> None:
        assert isinstance(
            check_transition(
                PositionStatusEnum.FORMED, PositionStatusEnum.SETTLED,
                SWAPTION_TRANSITIONS,
            ),
            Ok,
        )

    def test_formed_to_cancelled(self) -> None:
        assert isinstance(
            check_transition(
                PositionStatusEnum.FORMED, PositionStatusEnum.CANCELLED,
                SWAPTION_TRANSITIONS,
            ),
            Ok,
        )

    def test_settled_to_closed(self) -> None:
        assert isinstance(
            check_transition(
                PositionStatusEnum.SETTLED, PositionStatusEnum.CLOSED,
                SWAPTION_TRANSITIONS,
            ),
            Ok,
        )

    def test_invalid_closed_to_proposed(self) -> None:
        assert isinstance(
            check_transition(
                PositionStatusEnum.CLOSED, PositionStatusEnum.PROPOSED,
                SWAPTION_TRANSITIONS,
            ),
            Err,
        )

    def test_cancelled_terminal(self) -> None:
        for to_state in PositionStatusEnum:
            assert isinstance(
                check_transition(
                    PositionStatusEnum.CANCELLED, to_state, SWAPTION_TRANSITIONS,
                ),
                Err,
            )


# ---------------------------------------------------------------------------
# CreditEventPI
# ---------------------------------------------------------------------------


class TestCreditEventPI:
    def test_construction_without_auction_price(self) -> None:
        pi = CreditEventPI(
            instrument_id=NonEmptyStr(value="CDS-001"),
            event_type=CreditEventType.BANKRUPTCY,
            determination_date=date(2026, 3, 15),
            auction_price=None,
        )
        assert pi.instrument_id.value == "CDS-001"
        assert pi.event_type is CreditEventType.BANKRUPTCY
        assert pi.determination_date == date(2026, 3, 15)
        assert pi.auction_price is None

    def test_construction_with_auction_price(self) -> None:
        pi = CreditEventPI(
            instrument_id=NonEmptyStr(value="CDS-002"),
            event_type=CreditEventType.FAILURE_TO_PAY,
            determination_date=date(2026, 4, 1),
            auction_price=Decimal("0.35"),
        )
        assert pi.auction_price == Decimal("0.35")

    def test_frozen(self) -> None:
        pi = CreditEventPI(
            instrument_id=NonEmptyStr(value="CDS-001"),
            event_type=CreditEventType.RESTRUCTURING,
            determination_date=date(2026, 3, 15),
            auction_price=None,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            pi.auction_price = Decimal("0.50")  # type: ignore[misc]

    def test_replace(self) -> None:
        pi = CreditEventPI(
            instrument_id=NonEmptyStr(value="CDS-001"),
            event_type=CreditEventType.BANKRUPTCY,
            determination_date=date(2026, 3, 15),
            auction_price=None,
        )
        updated = dataclasses.replace(pi, auction_price=Decimal("0.40"))
        assert updated.auction_price == Decimal("0.40")
        assert pi.auction_price is None  # original unchanged


# ---------------------------------------------------------------------------
# SwaptionExercisePI
# ---------------------------------------------------------------------------


class TestSwaptionExercisePI:
    def test_physical_settlement(self) -> None:
        """Physical settlement: SwaptionPhysicalSettlement variant."""
        pi = SwaptionExercisePI(
            instrument_id=NonEmptyStr(value="SWPTN-001"),
            exercise_date=date(2026, 6, 15),
            settlement=SwaptionPhysicalSettlement(
                underlying_irs_id=NonEmptyStr(value="IRS-099"),
            ),
        )
        assert isinstance(pi.settlement, SwaptionPhysicalSettlement)
        assert pi.settlement.underlying_irs_id.value == "IRS-099"

    def test_cash_settlement(self) -> None:
        """Cash settlement: SwaptionCashSettlement variant."""
        amt = unwrap(Money.create(Decimal("150000"), "USD"))
        pi = SwaptionExercisePI(
            instrument_id=NonEmptyStr(value="SWPTN-002"),
            exercise_date=date(2026, 6, 15),
            settlement=SwaptionCashSettlement(settlement_amount=amt),
        )
        assert isinstance(pi.settlement, SwaptionCashSettlement)
        assert pi.settlement.settlement_amount.amount == Decimal("150000")

    def test_frozen(self) -> None:
        pi = SwaptionExercisePI(
            instrument_id=NonEmptyStr(value="SWPTN-001"),
            exercise_date=date(2026, 6, 15),
            settlement=SwaptionPhysicalSettlement(
                underlying_irs_id=NonEmptyStr(value="IRS-099"),
            ),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            pi.exercise_date = date(2026, 1, 1)  # type: ignore[misc]

    def test_replace(self) -> None:
        pi = SwaptionExercisePI(
            instrument_id=NonEmptyStr(value="SWPTN-001"),
            exercise_date=date(2026, 6, 15),
            settlement=SwaptionPhysicalSettlement(
                underlying_irs_id=NonEmptyStr(value="IRS-099"),
            ),
        )
        updated = dataclasses.replace(pi, exercise_date=date(2027, 1, 1))
        assert updated.exercise_date == date(2027, 1, 1)
        assert pi.exercise_date == date(2026, 6, 15)

    def test_illegal_states_impossible(self) -> None:
        """Sum type prevents the 2 illegal states that the old design admitted."""
        # Cannot construct with both None/both set -- the type system enforces
        # exactly one of CashSettlement or PhysicalSettlement
        amt = unwrap(Money.create(Decimal("100000"), "USD"))
        cash = SwaptionCashSettlement(settlement_amount=amt)
        phys = SwaptionPhysicalSettlement(
            underlying_irs_id=NonEmptyStr(value="IRS-001"),
        )
        # Both variants work individually
        pi_cash = SwaptionExercisePI(
            instrument_id=NonEmptyStr(value="SWPTN-001"),
            exercise_date=date(2026, 6, 15),
            settlement=cash,
        )
        pi_phys = SwaptionExercisePI(
            instrument_id=NonEmptyStr(value="SWPTN-001"),
            exercise_date=date(2026, 6, 15),
            settlement=phys,
        )
        assert isinstance(pi_cash.settlement, SwaptionCashSettlement)
        assert isinstance(pi_phys.settlement, SwaptionPhysicalSettlement)


# ---------------------------------------------------------------------------
# CollateralCallPI
# ---------------------------------------------------------------------------


class TestCollateralCallPI:
    def test_cash_collateral(self) -> None:
        amt = unwrap(Money.create(Decimal("5000000"), "USD"))
        pi = CollateralCallPI(
            agreement_id=NonEmptyStr(value="CSA-001"),
            call_amount=amt,
            call_date=date(2026, 7, 1),
            collateral_type=NonEmptyStr(value="CASH"),
        )
        assert pi.agreement_id.value == "CSA-001"
        assert pi.call_amount.amount == Decimal("5000000")
        assert pi.collateral_type.value == "CASH"

    def test_frozen(self) -> None:
        amt = unwrap(Money.create(Decimal("1000000"), "EUR"))
        pi = CollateralCallPI(
            agreement_id=NonEmptyStr(value="CSA-002"),
            call_amount=amt,
            call_date=date(2026, 7, 1),
            collateral_type=NonEmptyStr(value="CASH"),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            pi.call_date = date(2026, 8, 1)  # type: ignore[misc]

    def test_replace(self) -> None:
        amt = unwrap(Money.create(Decimal("1000000"), "EUR"))
        pi = CollateralCallPI(
            agreement_id=NonEmptyStr(value="CSA-002"),
            call_amount=amt,
            call_date=date(2026, 7, 1),
            collateral_type=NonEmptyStr(value="CASH"),
        )
        updated = dataclasses.replace(pi, collateral_type=NonEmptyStr(value="UST-10Y"))
        assert updated.collateral_type.value == "UST-10Y"
        assert pi.collateral_type.value == "CASH"


# ---------------------------------------------------------------------------
# PrimitiveInstruction union exhaustiveness
# ---------------------------------------------------------------------------


class TestPrimitiveInstructionUnion:
    def test_has_18_variants(self) -> None:
        """PrimitiveInstruction union should have 18 variants after Phase D."""
        args = get_args(PrimitiveInstruction)
        assert len(args) == 18

    def test_new_variants_present(self) -> None:
        """CreditEventPI, SwaptionExercisePI, CollateralCallPI in union."""
        args = get_args(PrimitiveInstruction)
        assert CreditEventPI in args
        assert SwaptionExercisePI in args
        assert CollateralCallPI in args
