"""CDM base-math -- Quantity, UnitType, and financial unit enums.

Aligned with ISDA CDM Rosetta (base-math-*):
  UnitType = one-of(capacityUnit | weatherUnit | financialUnit | currency)
  Quantity = value (Decimal) + unit (UnitType)
  NonNegativeQuantity = Quantity with value >= 0

Attestor flattens CDM's 6-level MeasureBase hierarchy
(MeasureBase -> Measure -> MeasureSchedule -> QuantitySchedule
-> Quantity -> NonNegativeQuantity) into two flat dataclasses
with smart constructors.  The Rosetta inheritance chain is a
DSL artifact; Python frozen dataclasses are more idiomatic.

RoundingDirectionEnum and Rounding are included for CDM
completeness (base-math Rounding type).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import final

from attestor.core.money import NonEmptyStr, validate_currency
from attestor.core.result import Err, Ok

# ---------------------------------------------------------------------------
# Enums  (CDM Rosetta: base-math-enum.rosetta)
# ---------------------------------------------------------------------------


class FinancialUnitEnum(Enum):
    """Financial quantity units for securities.

    CDM: FinancialUnitEnum (exact 8 members).
    """

    CONTRACT = "Contract"
    CONTRACTUAL_PRODUCT = "ContractualProduct"
    INDEX_UNIT = "IndexUnit"
    LOG_NORMAL_VOLATILITY = "LogNormalVolatility"
    SHARE = "Share"
    VALUE_PER_DAY = "ValuePerDay"
    VALUE_PER_PERCENT = "ValuePerPercent"
    WEIGHT = "Weight"


class RoundingDirectionEnum(Enum):
    """Rounding rule for precision-based rounding.

    CDM: RoundingDirectionEnum (exact 3 members).
    """

    UP = "Up"
    DOWN = "Down"
    NEAREST = "Nearest"


# ---------------------------------------------------------------------------
# UnitType  (CDM Rosetta: base-math-type.rosetta, one-of condition)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class UnitType:
    """Discriminated unit for price, quantity, or other purposes.

    CDM: UnitType with one-of condition -- exactly one of
    capacityUnit | weatherUnit | financialUnit | currency must be set.

    Attestor omits capacityUnit and weatherUnit (commodity/weather
    out of scope) but preserves the one-of invariant over the
    fields that are modeled.
    """

    financial_unit: FinancialUnitEnum | None = None
    currency: NonEmptyStr | None = None

    def __post_init__(self) -> None:
        if self.financial_unit is not None and not isinstance(
            self.financial_unit, FinancialUnitEnum
        ):
            raise TypeError(
                f"UnitType.financial_unit must be FinancialUnitEnum, "
                f"got {type(self.financial_unit).__name__}"
            )
        if self.currency is not None and not isinstance(self.currency, NonEmptyStr):
            raise TypeError(
                f"UnitType.currency must be NonEmptyStr, "
                f"got {type(self.currency).__name__}"
            )
        count = sum(1 for f in (self.financial_unit, self.currency) if f is not None)
        if count != 1:
            raise TypeError(
                f"UnitType requires exactly one field set, got {count}"
            )

    @staticmethod
    def of_financial(unit: FinancialUnitEnum) -> UnitType:
        """Create a UnitType for a financial unit (Share, Contract, etc.)."""
        return UnitType(financial_unit=unit)

    @staticmethod
    def of_currency(code: str) -> Ok[UnitType] | Err[str]:
        """Create a UnitType for a currency code (ISO 4217)."""
        if not validate_currency(code):
            return Err(f"UnitType.currency: invalid ISO 4217 code '{code}'")
        return Ok(UnitType(currency=NonEmptyStr(value=code)))


# ---------------------------------------------------------------------------
# Quantity  (CDM: Quantity extends QuantitySchedule -- flattened)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class Quantity:
    """A numeric value with an explicit unit.

    CDM: Quantity extends QuantitySchedule (single value, no steps).
    Conditions: value exists, unit exists, datedValue is absent.

    Attestor flattens the 4-level chain into a single dataclass.
    """

    value: Decimal
    unit: UnitType

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise TypeError(
                f"Quantity.value must be finite Decimal, got {self.value!r}"
            )
        if not isinstance(self.unit, UnitType):
            raise TypeError(
                f"Quantity.unit must be UnitType, "
                f"got {type(self.unit).__name__}"
            )

    @staticmethod
    def of_shares(n: Decimal) -> Ok[Quantity] | Err[str]:
        """Create a share quantity."""
        if not isinstance(n, Decimal) or not n.is_finite():
            return Err(f"Quantity.of_shares: need finite Decimal, got {n!r}")
        return Ok(Quantity(
            value=n,
            unit=UnitType.of_financial(FinancialUnitEnum.SHARE),
        ))

    @staticmethod
    def of_contracts(n: Decimal) -> Ok[Quantity] | Err[str]:
        """Create a contract quantity."""
        if not isinstance(n, Decimal) or not n.is_finite():
            return Err(f"Quantity.of_contracts: need finite Decimal, got {n!r}")
        return Ok(Quantity(
            value=n,
            unit=UnitType.of_financial(FinancialUnitEnum.CONTRACT),
        ))


# ---------------------------------------------------------------------------
# NonNegativeQuantity  (CDM: NonNegativeQuantity extends Quantity)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class NonNegativeQuantity:
    """Quantity constrained to value >= 0.

    CDM: NonNegativeQuantity extends Quantity.
    Condition: value >= 0.
    """

    value: Decimal
    unit: UnitType

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise TypeError(
                f"NonNegativeQuantity.value must be finite Decimal, "
                f"got {self.value!r}"
            )
        if self.value < 0:
            raise TypeError(
                f"NonNegativeQuantity.value must be >= 0, got {self.value}"
            )
        if not isinstance(self.unit, UnitType):
            raise TypeError(
                f"NonNegativeQuantity.unit must be UnitType, "
                f"got {type(self.unit).__name__}"
            )
        # Canonicalize Decimal('-0') to Decimal('0') for deterministic
        # serialization in attestation comparisons.
        if self.value == 0 and self.value.is_signed():
            object.__setattr__(self, "value", Decimal("0"))

    @staticmethod
    def create(
        value: Decimal, unit: UnitType,
    ) -> Ok[NonNegativeQuantity] | Err[str]:
        """Smart constructor returning Ok | Err."""
        if not isinstance(value, Decimal) or not value.is_finite():
            return Err(
                f"NonNegativeQuantity.value must be finite Decimal, "
                f"got {value!r}"
            )
        if value < 0:
            return Err(f"NonNegativeQuantity.value must be >= 0, got {value}")
        if not isinstance(unit, UnitType):
            return Err(
                f"NonNegativeQuantity.unit must be UnitType, "
                f"got {type(unit).__name__}"
            )
        return Ok(NonNegativeQuantity(value=value, unit=unit))

    @staticmethod
    def of_shares(n: Decimal) -> Ok[NonNegativeQuantity] | Err[str]:
        """Create a non-negative share quantity."""
        return NonNegativeQuantity.create(
            n, UnitType.of_financial(FinancialUnitEnum.SHARE),
        )

    @staticmethod
    def of_contracts(n: Decimal) -> Ok[NonNegativeQuantity] | Err[str]:
        """Create a non-negative contract quantity."""
        return NonNegativeQuantity.create(
            n, UnitType.of_financial(FinancialUnitEnum.CONTRACT),
        )


# ---------------------------------------------------------------------------
# Type alias for code accepting either Quantity variant
# ---------------------------------------------------------------------------

type AnyQuantity = Quantity | NonNegativeQuantity


# ---------------------------------------------------------------------------
# Rounding  (CDM Rosetta: base-math-type.rosetta)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class Rounding:
    """Rules for rounding a number.

    CDM: Rounding = roundingDirection + precision (optional).
    """

    rounding_direction: RoundingDirectionEnum
    precision: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.rounding_direction, RoundingDirectionEnum):
            raise TypeError(
                f"Rounding.rounding_direction must be RoundingDirectionEnum, "
                f"got {type(self.rounding_direction).__name__}"
            )
        if self.precision is not None:
            if not isinstance(self.precision, int) or isinstance(
                self.precision, bool
            ):
                raise TypeError(
                    f"Rounding.precision must be int, "
                    f"got {type(self.precision).__name__}"
                )
            if self.precision < 0:
                raise TypeError(
                    f"Rounding.precision must be >= 0, got {self.precision}"
                )
