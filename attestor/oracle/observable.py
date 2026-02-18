"""Observable and Index taxonomy — CDM-aligned market data identifiers.

Phase B: FloatingRateIndex, Index union, Observable union, Price types,
PriceQuantity, ObservationIdentifier, FloatingRateCalculationParameters,
ResetDates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Literal, final

from attestor.core.money import NonEmptyStr
from attestor.core.quantity import NonNegativeQuantity
from attestor.core.types import (
    BusinessDayAdjustments,
    Frequency,
    Period,
    RelativeDateOffset,
)

# ---------------------------------------------------------------------------
# Floating rate indices
# ---------------------------------------------------------------------------


class FloatingRateIndexEnum(Enum):
    """Major floating rate indices.

    CDM: FloatingRateIndexEnum (~200 values). We model the ~20 most
    commonly traded indices. Expand as needed.
    """

    # Overnight rates (RFR)
    SOFR = "USD-SOFR"
    ESTR = "EUR-ESTR"
    SONIA = "GBP-SONIA"
    TONA = "JPY-TONA"
    SARON = "CHF-SARON"
    AONIA = "AUD-AONIA"
    CORRA = "CAD-CORRA"
    # IBOR rates
    EURIBOR = "EUR-EURIBOR"
    TIBOR = "JPY-TIBOR"
    BBSW = "AUD-BBSW"
    CDOR = "CAD-CDOR"
    HIBOR = "HKD-HIBOR"
    SIBOR = "SGD-SIBOR"
    KLIBOR = "MYR-KLIBOR"
    JIBAR = "ZAR-JIBAR"
    # Legacy (still used in outstanding contracts)
    USD_LIBOR = "USD-LIBOR"
    GBP_LIBOR = "GBP-LIBOR"
    CHF_LIBOR = "CHF-LIBOR"
    JPY_LIBOR = "JPY-LIBOR"
    EUR_LIBOR = "EUR-LIBOR"


@final
@dataclass(frozen=True, slots=True)
class FloatingRateIndex:
    """A specific floating rate index with its designated maturity.

    CDM: FloatingRateIndex = floatingRateIndex + indexTenor.
    For overnight rates (SOFR, SONIA, etc.), designated_maturity
    is 1D by convention.
    """

    index: FloatingRateIndexEnum
    designated_maturity: Period  # e.g. Period(3, "M") for 3M EURIBOR

    def __post_init__(self) -> None:
        if not isinstance(self.index, FloatingRateIndexEnum):
            raise TypeError(
                "FloatingRateIndex.index must be FloatingRateIndexEnum, "
                f"got {type(self.index).__name__}"
            )
        if not isinstance(self.designated_maturity, Period):
            raise TypeError(
                "FloatingRateIndex.designated_maturity must be Period, "
                f"got {type(self.designated_maturity).__name__}"
            )


# ---------------------------------------------------------------------------
# Other index types (minimal stubs for union completeness)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class CreditIndex:
    """Credit default swap index (e.g. CDX.NA.IG, iTraxx Europe).

    CDM: CreditIndex = indexName + indexSeries + indexAnnexVersion.
    """

    index_name: NonEmptyStr
    index_series: int
    index_annex_version: int

    def __post_init__(self) -> None:
        if not isinstance(self.index_series, int) or isinstance(
            self.index_series, bool
        ):
            raise TypeError(
                "CreditIndex.index_series must be int, "
                f"got {type(self.index_series).__name__}"
            )
        if self.index_series <= 0:
            raise TypeError(
                f"CreditIndex.index_series must be > 0, got {self.index_series}"
            )
        if not isinstance(self.index_annex_version, int) or isinstance(
            self.index_annex_version, bool
        ):
            raise TypeError(
                "CreditIndex.index_annex_version must be int, "
                f"got {type(self.index_annex_version).__name__}"
            )
        if self.index_annex_version <= 0:
            raise TypeError(
                f"CreditIndex.index_annex_version must be > 0, "
                f"got {self.index_annex_version}"
            )


@final
@dataclass(frozen=True, slots=True)
class EquityIndex:
    """Equity index reference (e.g. S&P 500, EURO STOXX 50).

    CDM: EquityIndex = name + asset_class.
    """

    index_name: NonEmptyStr


@final
@dataclass(frozen=True, slots=True)
class FXRateIndex:
    """FX rate source for fixings (e.g. WM/Reuters, ECB).

    CDM: FxRateSourceFixing = fixingSource + fixingTime.
    """

    fixing_source: NonEmptyStr
    currency: NonEmptyStr


# ---------------------------------------------------------------------------
# Index and Observable unions
# ---------------------------------------------------------------------------

type Index = FloatingRateIndex | CreditIndex | EquityIndex | FXRateIndex

type Asset = NonEmptyStr  # Simplified: asset identifier (e.g. ISIN, ticker)

type Observable = Asset | Index


# ---------------------------------------------------------------------------
# Price types
# ---------------------------------------------------------------------------


class PriceTypeEnum(Enum):
    """What kind of price is being quoted.

    CDM: PriceTypeEnum.
    """

    INTEREST_RATE = "INTEREST_RATE"
    EXCHANGE_RATE = "EXCHANGE_RATE"
    ASSET_PRICE = "ASSET_PRICE"
    CASH_PRICE = "CASH_PRICE"
    NET_PRICE = "NET_PRICE"


class PriceExpressionEnum(Enum):
    """How the price value is expressed.

    CDM: PriceExpressionEnum.
    """

    ABSOLUTE = "ABSOLUTE"
    PERCENTAGE_OF_NOTIONAL = "PERCENTAGE_OF_NOTIONAL"
    PER_UNIT = "PER_UNIT"


@final
@dataclass(frozen=True, slots=True)
class Price:
    """A price observation with type and expression context.

    CDM: Price = value + unit + priceType + priceExpression.
    """

    value: Decimal
    currency: NonEmptyStr
    price_type: PriceTypeEnum
    price_expression: PriceExpressionEnum

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise TypeError(
                f"Price.value must be finite Decimal, got {self.value!r}"
            )


@final
@dataclass(frozen=True, slots=True)
class PriceQuantity:
    """Coupling of price, quantity, and the observable being priced.

    CDM: PriceQuantity = price (0..*) + quantity (0..*) + observable (0..1).
    Attestor simplifies to single price + quantity + observable for
    the common equity/derivatives case.

    quantity is a NonNegativeQuantity (value + UnitType) per CDM
    base-math alignment.
    """

    price: Price
    quantity: NonNegativeQuantity
    observable: Observable


@final
@dataclass(frozen=True, slots=True)
class ObservationIdentifier:
    """Identifies a specific observation: what, when, from where.

    CDM: ObservationIdentifier = observable + observationDate + source.
    """

    observable: Observable
    observation_date: date
    source: NonEmptyStr


# ---------------------------------------------------------------------------
# Floating rate calculation parameters
# ---------------------------------------------------------------------------


class CalculationMethodEnum(Enum):
    """How floating rate resets are combined over a period.

    CDM: CalculationMethodEnum.
    """

    COMPOUNDING = "COMPOUNDING"
    AVERAGING = "AVERAGING"


@final
@dataclass(frozen=True, slots=True)
class FloatingRateCalculationParameters:
    """Parameters for overnight rate compounding/averaging.

    CDM: FloatingRateCalculationParameters = calculationMethod
         + applicableBusinessDays + lookbackDays + lockoutDays + shiftDays.
    """

    calculation_method: CalculationMethodEnum
    applicable_business_days: frozenset[str]
    lookback_days: int
    lockout_days: int
    shift_days: int

    def __post_init__(self) -> None:
        if self.lookback_days < 0:
            raise TypeError(
                f"FloatingRateCalculationParameters.lookback_days "
                f"must be >= 0, got {self.lookback_days}"
            )
        if self.lockout_days < 0:
            raise TypeError(
                f"FloatingRateCalculationParameters.lockout_days "
                f"must be >= 0, got {self.lockout_days}"
            )
        if self.shift_days < 0:
            raise TypeError(
                f"FloatingRateCalculationParameters.shift_days "
                f"must be >= 0, got {self.shift_days}"
            )


# ---------------------------------------------------------------------------
# Reset dates
# ---------------------------------------------------------------------------


type ResetRelativeTo = Literal[
    "CalculationPeriodStartDate", "CalculationPeriodEndDate",
]


@final
@dataclass(frozen=True, slots=True)
class ResetDates:
    """Floating rate reset schedule parameters.

    CDM: ResetDates = resetFrequency + fixingDatesOffset
         + resetRelativeTo + calculationParameters.
    """

    reset_frequency: Frequency
    fixing_dates_offset: RelativeDateOffset
    reset_relative_to: ResetRelativeTo
    calculation_parameters: FloatingRateCalculationParameters | None
    business_day_adjustments: BusinessDayAdjustments
