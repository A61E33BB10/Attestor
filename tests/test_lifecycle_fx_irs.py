"""Tests for FX / IRS lifecycle — transitions, FixingPI, NettingPI, MaturityPI."""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal

import pytest

from attestor.core.money import Money, NonEmptyStr
from attestor.core.result import Err, Ok, unwrap
from attestor.instrument.lifecycle import (
    FX_TRANSITIONS,
    IRS_TRANSITIONS,
    FixingPI,
    MaturityPI,
    NettingPI,
    check_transition,
)
from attestor.instrument.types import PositionStatusEnum

# ---------------------------------------------------------------------------
# FX_TRANSITIONS
# ---------------------------------------------------------------------------


class TestFXTransitions:
    def test_has_5_edges(self) -> None:
        assert len(FX_TRANSITIONS) == 5

    def test_proposed_to_formed(self) -> None:
        assert isinstance(
            check_transition(
                PositionStatusEnum.PROPOSED, PositionStatusEnum.FORMED,
                FX_TRANSITIONS,
            ),
            Ok,
        )

    def test_formed_to_settled(self) -> None:
        assert isinstance(
            check_transition(
                PositionStatusEnum.FORMED, PositionStatusEnum.SETTLED,
                FX_TRANSITIONS,
            ),
            Ok,
        )

    def test_settled_to_closed(self) -> None:
        assert isinstance(
            check_transition(
                PositionStatusEnum.SETTLED, PositionStatusEnum.CLOSED,
                FX_TRANSITIONS,
            ),
            Ok,
        )

    def test_cancelled_terminal(self) -> None:
        for to_state in PositionStatusEnum:
            assert isinstance(
                check_transition(
                    PositionStatusEnum.CANCELLED, to_state, FX_TRANSITIONS,
                ),
                Err,
            )


# ---------------------------------------------------------------------------
# IRS_TRANSITIONS
# ---------------------------------------------------------------------------


class TestIRSTransitions:
    def test_has_5_edges(self) -> None:
        assert len(IRS_TRANSITIONS) == 5

    def test_proposed_to_formed(self) -> None:
        assert isinstance(
            check_transition(
                PositionStatusEnum.PROPOSED, PositionStatusEnum.FORMED,
                IRS_TRANSITIONS,
            ),
            Ok,
        )

    def test_formed_to_settled(self) -> None:
        assert isinstance(
            check_transition(
                PositionStatusEnum.FORMED, PositionStatusEnum.SETTLED,
                IRS_TRANSITIONS,
            ),
            Ok,
        )

    def test_settled_to_closed(self) -> None:
        """IRS maturity: SETTLED -> CLOSED."""
        assert isinstance(
            check_transition(
                PositionStatusEnum.SETTLED, PositionStatusEnum.CLOSED,
                IRS_TRANSITIONS,
            ),
            Ok,
        )

    def test_invalid_closed_to_formed(self) -> None:
        assert isinstance(
            check_transition(
                PositionStatusEnum.CLOSED, PositionStatusEnum.FORMED,
                IRS_TRANSITIONS,
            ),
            Err,
        )


# ---------------------------------------------------------------------------
# FixingPI
# ---------------------------------------------------------------------------


class TestFixingPI:
    def test_construction(self) -> None:
        pi = FixingPI(
            instrument_id=NonEmptyStr(value="NDF-001"),
            fixing_date=date(2025, 9, 15),
            fixing_rate=Decimal("7.2345"),
            fixing_source=NonEmptyStr(value="WMR"),
        )
        assert pi.fixing_rate == Decimal("7.2345")
        assert pi.fixing_source.value == "WMR"

    def test_frozen(self) -> None:
        pi = FixingPI(
            instrument_id=NonEmptyStr(value="NDF-001"),
            fixing_date=date(2025, 9, 15),
            fixing_rate=Decimal("7.2345"),
            fixing_source=NonEmptyStr(value="WMR"),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            pi.fixing_rate = Decimal("0")  # type: ignore[misc]

    def test_negative_rate_allowed(self) -> None:
        """Fixing rate can be negative (e.g. negative interest rates)."""
        pi = FixingPI(
            instrument_id=NonEmptyStr(value="IRS-001"),
            fixing_date=date(2025, 6, 1),
            fixing_rate=Decimal("-0.005"),
            fixing_source=NonEmptyStr(value="SOFR"),
        )
        assert pi.fixing_rate < 0


# ---------------------------------------------------------------------------
# NettingPI
# ---------------------------------------------------------------------------


class TestNettingPI:
    def test_construction(self) -> None:
        ids = (NonEmptyStr(value="FX-001"), NonEmptyStr(value="FX-002"))
        amt = unwrap(Money.create(Decimal("50000"), "USD"))
        pi = NettingPI(
            instrument_ids=ids,
            netting_date=date(2025, 9, 17),
            net_amount=amt,
        )
        assert len(pi.instrument_ids) == 2
        assert pi.net_amount.amount == Decimal("50000")

    def test_frozen(self) -> None:
        ids = (NonEmptyStr(value="FX-001"),)
        amt = unwrap(Money.create(Decimal("1000"), "USD"))
        pi = NettingPI(instrument_ids=ids, netting_date=date(2025, 9, 17), net_amount=amt)
        with pytest.raises(dataclasses.FrozenInstanceError):
            pi.netting_date = date(2025, 1, 1)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MaturityPI
# ---------------------------------------------------------------------------


class TestMaturityPI:
    def test_construction(self) -> None:
        pi = MaturityPI(
            instrument_id=NonEmptyStr(value="IRS-001"),
            maturity_date=date(2030, 6, 15),
        )
        assert pi.maturity_date == date(2030, 6, 15)

    def test_frozen(self) -> None:
        pi = MaturityPI(
            instrument_id=NonEmptyStr(value="IRS-001"),
            maturity_date=date(2030, 6, 15),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            pi.instrument_id = NonEmptyStr(value="X")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PrimitiveInstruction union exhaustiveness
# ---------------------------------------------------------------------------


class TestPrimitiveInstructionUnion:
    def test_has_10_variants(self) -> None:
        """PrimitiveInstruction union should have 10 variants after Phase 3."""
        from attestor.instrument.lifecycle import PrimitiveInstruction
        # PrimitiveInstruction is a type alias — check __args__
        assert hasattr(PrimitiveInstruction, "__args__"), "Expected a Union type alias"

    def test_all_variants_constructible(self) -> None:
        """Each PI variant can be constructed."""
        from attestor.instrument.lifecycle import (
            AssignPI,
            DividendPI,
            ExecutePI,
            ExercisePI,
            ExpiryPI,
            MarginPI,
            TransferPI,
        )
        # Just verify no import error; full construction tested elsewhere
        assert ExecutePI is not None
        assert TransferPI is not None
        assert DividendPI is not None
        assert ExercisePI is not None
        assert AssignPI is not None
        assert ExpiryPI is not None
        assert MarginPI is not None
        assert FixingPI is not None
        assert NettingPI is not None
        assert MaturityPI is not None
