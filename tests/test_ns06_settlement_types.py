"""NS6b tests — settlement type enrichment aligned to CDM Rosetta.

Tests cover: CashSettlementTerms (enriched with CDM optional fields),
PhysicalSettlementPeriod (new CDM one-of type),
PhysicalSettlementTerms (enriched with CDM optional fields).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from attestor.core.money import NonEmptyStr, NonNegativeDecimal
from attestor.core.result import unwrap
from attestor.instrument.derivative_types import (
    CashSettlementMethodEnum,
    CashSettlementTerms,
    PhysicalSettlementPeriod,
    PhysicalSettlementTerms,
)

# ---------------------------------------------------------------------------
# CashSettlementTerms
# ---------------------------------------------------------------------------


class TestCashSettlementTerms:
    def test_basic_unchanged(self) -> None:
        """Existing constructor still works with no new fields."""
        cst = CashSettlementTerms(
            settlement_method=NonEmptyStr(value="MidMarket"),
            valuation_date=date(2025, 7, 1),
            currency=NonEmptyStr(value="USD"),
        )
        assert cst.settlement_method.value == "MidMarket"
        assert cst.cash_settlement_method is None
        assert cst.cash_settlement_amount is None
        assert cst.recovery_factor is None
        assert cst.fixed_settlement is None
        assert cst.accrued_interest is None

    def test_with_cash_settlement_method(self) -> None:
        cst = CashSettlementTerms(
            settlement_method=NonEmptyStr(value="ParYieldCurve"),
            valuation_date=date(2025, 7, 1),
            currency=NonEmptyStr(value="USD"),
            cash_settlement_method=CashSettlementMethodEnum.PAR_YIELD_CURVE_ADJUSTED_METHOD,
        )
        expected = CashSettlementMethodEnum.PAR_YIELD_CURVE_ADJUSTED_METHOD
        assert cst.cash_settlement_method is expected

    def test_with_cash_settlement_amount(self) -> None:
        amt = unwrap(NonNegativeDecimal.parse(Decimal("1000000")))
        cst = CashSettlementTerms(
            settlement_method=NonEmptyStr(value="CashPrice"),
            valuation_date=date(2025, 7, 1),
            currency=NonEmptyStr(value="USD"),
            cash_settlement_amount=amt,
        )
        assert cst.cash_settlement_amount is not None
        assert cst.cash_settlement_amount.value == Decimal("1000000")

    def test_recovery_factor_valid(self) -> None:
        cst = CashSettlementTerms(
            settlement_method=NonEmptyStr(value="RecoveryLock"),
            valuation_date=date(2025, 7, 1),
            currency=NonEmptyStr(value="USD"),
            recovery_factor=Decimal("0.40"),
        )
        assert cst.recovery_factor == Decimal("0.40")

    def test_recovery_factor_zero_valid(self) -> None:
        cst = CashSettlementTerms(
            settlement_method=NonEmptyStr(value="RecoveryLock"),
            valuation_date=date(2025, 7, 1),
            currency=NonEmptyStr(value="USD"),
            recovery_factor=Decimal("0"),
        )
        assert cst.recovery_factor == Decimal("0")

    def test_recovery_factor_one_valid(self) -> None:
        cst = CashSettlementTerms(
            settlement_method=NonEmptyStr(value="RecoveryLock"),
            valuation_date=date(2025, 7, 1),
            currency=NonEmptyStr(value="USD"),
            recovery_factor=Decimal("1"),
        )
        assert cst.recovery_factor == Decimal("1")

    def test_recovery_factor_out_of_range_rejected(self) -> None:
        with pytest.raises(TypeError, match="recovery_factor must be in"):
            CashSettlementTerms(
                settlement_method=NonEmptyStr(value="RecoveryLock"),
                valuation_date=date(2025, 7, 1),
                currency=NonEmptyStr(value="USD"),
                recovery_factor=Decimal("1.5"),
            )

    def test_recovery_factor_negative_rejected(self) -> None:
        with pytest.raises(TypeError, match="recovery_factor must be in"):
            CashSettlementTerms(
                settlement_method=NonEmptyStr(value="RecoveryLock"),
                valuation_date=date(2025, 7, 1),
                currency=NonEmptyStr(value="USD"),
                recovery_factor=Decimal("-0.1"),
            )

    def test_recovery_factor_non_decimal_rejected(self) -> None:
        with pytest.raises(TypeError, match="recovery_factor must be Decimal"):
            CashSettlementTerms(
                settlement_method=NonEmptyStr(value="RecoveryLock"),
                valuation_date=date(2025, 7, 1),
                currency=NonEmptyStr(value="USD"),
                recovery_factor=0.4,  # type: ignore[arg-type]
            )

    def test_fixed_settlement_valid(self) -> None:
        cst = CashSettlementTerms(
            settlement_method=NonEmptyStr(value="CashPrice"),
            valuation_date=date(2025, 7, 1),
            currency=NonEmptyStr(value="USD"),
            fixed_settlement=True,
        )
        assert cst.fixed_settlement is True

    def test_fixed_settlement_non_bool_rejected(self) -> None:
        with pytest.raises(TypeError, match="fixed_settlement must be bool"):
            CashSettlementTerms(
                settlement_method=NonEmptyStr(value="CashPrice"),
                valuation_date=date(2025, 7, 1),
                currency=NonEmptyStr(value="USD"),
                fixed_settlement=1,  # type: ignore[arg-type]
            )

    def test_accrued_interest_valid(self) -> None:
        cst = CashSettlementTerms(
            settlement_method=NonEmptyStr(value="CashPrice"),
            valuation_date=date(2025, 7, 1),
            currency=NonEmptyStr(value="USD"),
            accrued_interest=False,
        )
        assert cst.accrued_interest is False

    def test_accrued_interest_non_bool_rejected(self) -> None:
        with pytest.raises(TypeError, match="accrued_interest must be bool"):
            CashSettlementTerms(
                settlement_method=NonEmptyStr(value="CashPrice"),
                valuation_date=date(2025, 7, 1),
                currency=NonEmptyStr(value="USD"),
                accrued_interest="yes",  # type: ignore[arg-type]
            )

    def test_all_new_fields(self) -> None:
        cst = CashSettlementTerms(
            settlement_method=NonEmptyStr(value="CashPrice"),
            valuation_date=date(2025, 7, 1),
            currency=NonEmptyStr(value="USD"),
            cash_settlement_method=CashSettlementMethodEnum.CASH_PRICE_METHOD,
            cash_settlement_amount=unwrap(NonNegativeDecimal.parse(Decimal("50000"))),
            recovery_factor=Decimal("0.40"),
            fixed_settlement=True,
            accrued_interest=False,
        )
        assert cst.cash_settlement_method is not None
        assert cst.cash_settlement_amount is not None
        assert cst.recovery_factor is not None
        assert cst.fixed_settlement is True
        assert cst.accrued_interest is False

    def test_frozen(self) -> None:
        cst = CashSettlementTerms(
            settlement_method=NonEmptyStr(value="MidMarket"),
            valuation_date=date(2025, 7, 1),
            currency=NonEmptyStr(value="USD"),
        )
        with pytest.raises(AttributeError):
            cst.recovery_factor = Decimal("0.5")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PhysicalSettlementPeriod
# ---------------------------------------------------------------------------


class TestPhysicalSettlementPeriod:
    def test_business_days_not_specified(self) -> None:
        psp = PhysicalSettlementPeriod(business_days_not_specified=True)
        assert psp.business_days_not_specified is True
        assert psp.business_days is None
        assert psp.maximum_business_days is None

    def test_business_days(self) -> None:
        psp = PhysicalSettlementPeriod(business_days=5)
        assert psp.business_days == 5

    def test_business_days_zero(self) -> None:
        psp = PhysicalSettlementPeriod(business_days=0)
        assert psp.business_days == 0

    def test_maximum_business_days(self) -> None:
        psp = PhysicalSettlementPeriod(maximum_business_days=30)
        assert psp.maximum_business_days == 30

    def test_no_choice_rejected(self) -> None:
        with pytest.raises(TypeError, match="exactly one"):
            PhysicalSettlementPeriod()

    def test_two_choices_rejected(self) -> None:
        with pytest.raises(TypeError, match="exactly one"):
            PhysicalSettlementPeriod(
                business_days_not_specified=True,
                business_days=5,
            )

    def test_all_three_choices_rejected(self) -> None:
        with pytest.raises(TypeError, match="exactly one"):
            PhysicalSettlementPeriod(
                business_days_not_specified=True,
                business_days=5,
                maximum_business_days=30,
            )

    def test_negative_business_days_rejected(self) -> None:
        with pytest.raises(TypeError, match="must be >= 0"):
            PhysicalSettlementPeriod(business_days=-1)

    def test_negative_maximum_business_days_rejected(self) -> None:
        with pytest.raises(TypeError, match="must be >= 0"):
            PhysicalSettlementPeriod(maximum_business_days=-1)

    def test_business_days_bool_rejected(self) -> None:
        with pytest.raises(TypeError, match="must be int"):
            PhysicalSettlementPeriod(business_days=True)  # type: ignore[arg-type]

    def test_frozen(self) -> None:
        psp = PhysicalSettlementPeriod(business_days=5)
        with pytest.raises(AttributeError):
            psp.business_days = 10  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PhysicalSettlementTerms
# ---------------------------------------------------------------------------


class TestPhysicalSettlementTerms:
    def test_basic_unchanged(self) -> None:
        """Existing constructor still works with no new fields."""
        pst = PhysicalSettlementTerms(
            delivery_period_days=3,
            settlement_currency=NonEmptyStr(value="USD"),
        )
        assert pst.delivery_period_days == 3
        assert pst.cleared_physical_settlement is None
        assert pst.physical_settlement_period is None
        assert pst.escrow is None
        assert pst.sixty_business_day_settlement_cap is None

    def test_with_settlement_period(self) -> None:
        period = PhysicalSettlementPeriod(business_days=5)
        pst = PhysicalSettlementTerms(
            delivery_period_days=5,
            settlement_currency=NonEmptyStr(value="USD"),
            physical_settlement_period=period,
        )
        assert pst.physical_settlement_period is period

    def test_with_cleared_settlement(self) -> None:
        pst = PhysicalSettlementTerms(
            delivery_period_days=3,
            settlement_currency=NonEmptyStr(value="USD"),
            cleared_physical_settlement=True,
        )
        assert pst.cleared_physical_settlement is True

    def test_with_escrow(self) -> None:
        pst = PhysicalSettlementTerms(
            delivery_period_days=3,
            settlement_currency=NonEmptyStr(value="USD"),
            escrow=True,
        )
        assert pst.escrow is True

    def test_with_sixty_day_cap(self) -> None:
        pst = PhysicalSettlementTerms(
            delivery_period_days=3,
            settlement_currency=NonEmptyStr(value="USD"),
            sixty_business_day_settlement_cap=True,
        )
        assert pst.sixty_business_day_settlement_cap is True

    def test_all_new_fields(self) -> None:
        pst = PhysicalSettlementTerms(
            delivery_period_days=3,
            settlement_currency=NonEmptyStr(value="USD"),
            cleared_physical_settlement=True,
            physical_settlement_period=PhysicalSettlementPeriod(business_days=5),
            escrow=False,
            sixty_business_day_settlement_cap=True,
        )
        assert pst.cleared_physical_settlement is True
        assert pst.physical_settlement_period is not None
        assert pst.escrow is False
        assert pst.sixty_business_day_settlement_cap is True

    def test_zero_delivery_days_rejected(self) -> None:
        with pytest.raises(TypeError, match="must be > 0"):
            PhysicalSettlementTerms(
                delivery_period_days=0,
                settlement_currency=NonEmptyStr(value="USD"),
            )

    def test_bool_delivery_days_rejected(self) -> None:
        with pytest.raises(TypeError, match="must be int"):
            PhysicalSettlementTerms(
                delivery_period_days=True,  # type: ignore[arg-type]
                settlement_currency=NonEmptyStr(value="USD"),
            )

    def test_invalid_settlement_period_rejected(self) -> None:
        with pytest.raises(TypeError, match="PhysicalSettlementPeriod"):
            PhysicalSettlementTerms(
                delivery_period_days=3,
                settlement_currency=NonEmptyStr(value="USD"),
                physical_settlement_period="invalid",  # type: ignore[arg-type]
            )

    def test_non_bool_escrow_rejected(self) -> None:
        with pytest.raises(TypeError, match="bool or None"):
            PhysicalSettlementTerms(
                delivery_period_days=3,
                settlement_currency=NonEmptyStr(value="USD"),
                escrow=1,  # type: ignore[arg-type]
            )

    def test_frozen(self) -> None:
        pst = PhysicalSettlementTerms(
            delivery_period_days=3,
            settlement_currency=NonEmptyStr(value="USD"),
        )
        with pytest.raises(AttributeError):
            pst.escrow = True  # type: ignore[misc]
