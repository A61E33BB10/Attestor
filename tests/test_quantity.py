"""Tests for attestor.core.quantity -- CDM base-math alignment.

Covers FinancialUnitEnum, RoundingDirectionEnum, UnitType, Quantity,
NonNegativeQuantity, Rounding.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from attestor.core.money import NonEmptyStr
from attestor.core.quantity import (
    FinancialUnitEnum,
    NonNegativeQuantity,
    Quantity,
    Rounding,
    RoundingDirectionEnum,
    UnitType,
)
from attestor.core.result import Err, Ok

# ---------------------------------------------------------------------------
# FinancialUnitEnum
# ---------------------------------------------------------------------------


class TestFinancialUnitEnum:
    def test_member_count(self) -> None:
        assert len(FinancialUnitEnum) == 8

    def test_exact_members(self) -> None:
        names = {m.name for m in FinancialUnitEnum}
        assert names == {
            "CONTRACT",
            "CONTRACTUAL_PRODUCT",
            "INDEX_UNIT",
            "LOG_NORMAL_VOLATILITY",
            "SHARE",
            "VALUE_PER_DAY",
            "VALUE_PER_PERCENT",
            "WEIGHT",
        }

    def test_share_value(self) -> None:
        assert FinancialUnitEnum.SHARE.value == "Share"


# ---------------------------------------------------------------------------
# RoundingDirectionEnum
# ---------------------------------------------------------------------------


class TestRoundingDirectionEnum:
    def test_member_count(self) -> None:
        assert len(RoundingDirectionEnum) == 3

    def test_exact_members(self) -> None:
        names = {m.name for m in RoundingDirectionEnum}
        assert names == {"UP", "DOWN", "NEAREST"}


# ---------------------------------------------------------------------------
# UnitType
# ---------------------------------------------------------------------------


class TestUnitType:
    def test_of_financial(self) -> None:
        ut = UnitType.of_financial(FinancialUnitEnum.SHARE)
        assert ut.financial_unit == FinancialUnitEnum.SHARE
        assert ut.currency is None

    def test_of_currency_valid(self) -> None:
        result = UnitType.of_currency("USD")
        assert isinstance(result, Ok)
        ut = result.value
        assert ut.currency is not None
        assert ut.currency.value == "USD"
        assert ut.financial_unit is None

    def test_of_currency_invalid(self) -> None:
        result = UnitType.of_currency("INVALID")
        assert isinstance(result, Err)

    def test_no_fields_set_rejected(self) -> None:
        with pytest.raises(TypeError, match="exactly one"):
            UnitType()

    def test_both_fields_set_rejected(self) -> None:
        with pytest.raises(TypeError, match="exactly one"):
            UnitType(
                financial_unit=FinancialUnitEnum.SHARE,
                currency=NonEmptyStr(value="USD"),
            )

    def test_frozen(self) -> None:
        ut = UnitType.of_financial(FinancialUnitEnum.CONTRACT)
        with pytest.raises(AttributeError):
            ut.financial_unit = FinancialUnitEnum.SHARE  # type: ignore[misc]

    def test_all_financial_units(self) -> None:
        for fu in FinancialUnitEnum:
            ut = UnitType.of_financial(fu)
            assert ut.financial_unit == fu

    def test_raw_string_financial_unit_rejected(self) -> None:
        """F-1: raw string bypassing enum type is rejected."""
        with pytest.raises(TypeError, match="FinancialUnitEnum"):
            UnitType(financial_unit="SHARE")  # type: ignore[arg-type]

    def test_raw_string_currency_rejected(self) -> None:
        """F-1: raw string bypassing NonEmptyStr type is rejected."""
        with pytest.raises(TypeError, match="NonEmptyStr"):
            UnitType(currency="USD")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Quantity
# ---------------------------------------------------------------------------


class TestQuantity:
    def test_valid(self) -> None:
        ut = UnitType.of_financial(FinancialUnitEnum.SHARE)
        q = Quantity(value=Decimal("1000"), unit=ut)
        assert q.value == Decimal("1000")
        assert q.unit.financial_unit == FinancialUnitEnum.SHARE

    def test_negative_allowed(self) -> None:
        """Quantity allows negative values (unlike NonNegativeQuantity)."""
        ut = UnitType.of_financial(FinancialUnitEnum.SHARE)
        q = Quantity(value=Decimal("-10"), unit=ut)
        assert q.value == Decimal("-10")

    def test_zero_allowed(self) -> None:
        ut = UnitType.of_financial(FinancialUnitEnum.SHARE)
        q = Quantity(value=Decimal("0"), unit=ut)
        assert q.value == Decimal("0")

    def test_non_finite_rejected(self) -> None:
        ut = UnitType.of_financial(FinancialUnitEnum.SHARE)
        with pytest.raises(TypeError, match="finite Decimal"):
            Quantity(value=Decimal("NaN"), unit=ut)

    def test_infinity_rejected(self) -> None:
        ut = UnitType.of_financial(FinancialUnitEnum.SHARE)
        with pytest.raises(TypeError, match="finite Decimal"):
            Quantity(value=Decimal("Inf"), unit=ut)

    def test_of_shares(self) -> None:
        result = Quantity.of_shares(Decimal("500"))
        assert isinstance(result, Ok)
        q = result.value
        assert q.value == Decimal("500")
        assert q.unit.financial_unit == FinancialUnitEnum.SHARE

    def test_of_contracts(self) -> None:
        result = Quantity.of_contracts(Decimal("10"))
        assert isinstance(result, Ok)
        q = result.value
        assert q.value == Decimal("10")
        assert q.unit.financial_unit == FinancialUnitEnum.CONTRACT

    def test_of_shares_non_finite_err(self) -> None:
        result = Quantity.of_shares(Decimal("NaN"))
        assert isinstance(result, Err)

    def test_frozen(self) -> None:
        ut = UnitType.of_financial(FinancialUnitEnum.SHARE)
        q = Quantity(value=Decimal("1"), unit=ut)
        with pytest.raises(AttributeError):
            q.value = Decimal("2")  # type: ignore[misc]

    def test_non_unittype_unit_rejected(self) -> None:
        """F-2: non-UnitType object as unit is rejected."""
        with pytest.raises(TypeError, match="UnitType"):
            Quantity(value=Decimal("1"), unit="notaunit")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# NonNegativeQuantity
# ---------------------------------------------------------------------------


class TestNonNegativeQuantity:
    def test_valid(self) -> None:
        ut = UnitType.of_financial(FinancialUnitEnum.SHARE)
        q = NonNegativeQuantity(value=Decimal("1000"), unit=ut)
        assert q.value == Decimal("1000")

    def test_zero_allowed(self) -> None:
        ut = UnitType.of_financial(FinancialUnitEnum.SHARE)
        q = NonNegativeQuantity(value=Decimal("0"), unit=ut)
        assert q.value == Decimal("0")

    def test_negative_rejected(self) -> None:
        ut = UnitType.of_financial(FinancialUnitEnum.SHARE)
        with pytest.raises(TypeError, match=">= 0"):
            NonNegativeQuantity(value=Decimal("-1"), unit=ut)

    def test_non_finite_rejected(self) -> None:
        ut = UnitType.of_financial(FinancialUnitEnum.SHARE)
        with pytest.raises(TypeError, match="finite Decimal"):
            NonNegativeQuantity(value=Decimal("NaN"), unit=ut)

    def test_create_valid(self) -> None:
        ut = UnitType.of_financial(FinancialUnitEnum.SHARE)
        result = NonNegativeQuantity.create(Decimal("100"), ut)
        assert isinstance(result, Ok)
        assert result.value.value == Decimal("100")

    def test_create_negative_err(self) -> None:
        ut = UnitType.of_financial(FinancialUnitEnum.SHARE)
        result = NonNegativeQuantity.create(Decimal("-1"), ut)
        assert isinstance(result, Err)

    def test_create_non_finite_err(self) -> None:
        ut = UnitType.of_financial(FinancialUnitEnum.SHARE)
        result = NonNegativeQuantity.create(Decimal("Inf"), ut)
        assert isinstance(result, Err)

    def test_of_shares(self) -> None:
        result = NonNegativeQuantity.of_shares(Decimal("1000"))
        assert isinstance(result, Ok)
        q = result.value
        assert q.value == Decimal("1000")
        assert q.unit.financial_unit == FinancialUnitEnum.SHARE

    def test_of_shares_negative_err(self) -> None:
        result = NonNegativeQuantity.of_shares(Decimal("-1"))
        assert isinstance(result, Err)

    def test_of_contracts(self) -> None:
        result = NonNegativeQuantity.of_contracts(Decimal("5"))
        assert isinstance(result, Ok)
        assert result.value.unit.financial_unit == FinancialUnitEnum.CONTRACT

    def test_frozen(self) -> None:
        ut = UnitType.of_financial(FinancialUnitEnum.SHARE)
        q = NonNegativeQuantity(value=Decimal("1"), unit=ut)
        with pytest.raises(AttributeError):
            q.value = Decimal("2")  # type: ignore[misc]

    def test_nvda_1000_shares(self) -> None:
        """Golden test: 1000 NVDA shares as CDM NonNegativeQuantity."""
        result = NonNegativeQuantity.of_shares(Decimal("1000"))
        assert isinstance(result, Ok)
        q = result.value
        assert q.value == Decimal("1000")
        assert q.unit.financial_unit == FinancialUnitEnum.SHARE
        assert q.unit.currency is None

    def test_currency_quantity(self) -> None:
        """Quantity with currency unit (e.g. 1M USD notional)."""
        result = UnitType.of_currency("USD")
        assert isinstance(result, Ok)
        ut = result.value
        result2 = NonNegativeQuantity.create(Decimal("1000000"), ut)
        assert isinstance(result2, Ok)
        assert result2.value.unit.currency is not None
        assert result2.value.unit.currency.value == "USD"

    def test_non_unittype_unit_rejected(self) -> None:
        """F-2: non-UnitType object as unit is rejected."""
        with pytest.raises(TypeError, match="UnitType"):
            NonNegativeQuantity(value=Decimal("1"), unit="bad")  # type: ignore[arg-type]

    def test_create_non_unittype_unit_err(self) -> None:
        """F-2: smart constructor rejects non-UnitType unit."""
        result = NonNegativeQuantity.create(Decimal("1"), "bad")  # type: ignore[arg-type]
        assert isinstance(result, Err)

    def test_negative_zero_canonicalized(self) -> None:
        """F-4: Decimal('-0') is canonicalized to Decimal('0')."""
        ut = UnitType.of_financial(FinancialUnitEnum.SHARE)
        q = NonNegativeQuantity(value=Decimal("-0"), unit=ut)
        assert q.value == Decimal("0")
        assert not q.value.is_signed()


# ---------------------------------------------------------------------------
# Rounding
# ---------------------------------------------------------------------------


class TestRounding:
    def test_valid(self) -> None:
        r = Rounding(
            rounding_direction=RoundingDirectionEnum.NEAREST,
            precision=2,
        )
        assert r.rounding_direction == RoundingDirectionEnum.NEAREST
        assert r.precision == 2

    def test_no_precision(self) -> None:
        r = Rounding(rounding_direction=RoundingDirectionEnum.UP)
        assert r.precision is None

    def test_negative_precision_rejected(self) -> None:
        with pytest.raises(TypeError, match="precision must be >= 0"):
            Rounding(rounding_direction=RoundingDirectionEnum.DOWN, precision=-1)

    def test_zero_precision(self) -> None:
        r = Rounding(rounding_direction=RoundingDirectionEnum.DOWN, precision=0)
        assert r.precision == 0

    def test_bool_precision_rejected(self) -> None:
        """F-3: bool is rejected even though bool is subclass of int."""
        with pytest.raises(TypeError, match="must be int"):
            Rounding(rounding_direction=RoundingDirectionEnum.NEAREST, precision=True)  # type: ignore[arg-type]

    def test_float_precision_rejected(self) -> None:
        """F-3: float is rejected for precision."""
        with pytest.raises(TypeError, match="must be int"):
            Rounding(rounding_direction=RoundingDirectionEnum.NEAREST, precision=2.5)  # type: ignore[arg-type]

    def test_frozen(self) -> None:
        r = Rounding(rounding_direction=RoundingDirectionEnum.NEAREST)
        with pytest.raises(AttributeError):
            r.precision = 5  # type: ignore[misc]
