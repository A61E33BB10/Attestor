"""Rate specification types for IRS product enrichment.

Phase C: FixedRateSpecification, FloatingRateSpecification, RateSpecification
union, StubPeriod, CompoundingMethodEnum, NegativeTreatmentEnum.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Literal, final

from attestor.core.types import DatedValue, DayCountConvention
from attestor.oracle.observable import FloatingRateIndex

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CompoundingMethodEnum(Enum):
    """How interim amounts compound within a calculation period.

    CDM: CompoundingMethodEnum.
    """

    FLAT = "FLAT"
    STRAIGHT = "STRAIGHT"
    SPREAD_EXCLUSIVE = "SPREAD_EXCLUSIVE"
    NONE = "NONE"


type NegativeTreatmentEnum = Literal[
    "NegativeInterestRateMethod",
    "ZeroInterestRateMethod",
]


# ---------------------------------------------------------------------------
# Stub period
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class StubPeriod:
    """Initial and/or final stub rate overrides.

    CDM: StubPeriod = initialStub + finalStub. Each stub can specify a
    fixed rate or a floating rate index to use for the stub period.
    We simplify to optional fixed rates (most common case).
    """

    initial_stub_rate: Decimal | None = None
    final_stub_rate: Decimal | None = None

    def __post_init__(self) -> None:
        if self.initial_stub_rate is not None:
            if not isinstance(self.initial_stub_rate, Decimal):
                raise TypeError(
                    "StubPeriod.initial_stub_rate must be Decimal, "
                    f"got {type(self.initial_stub_rate).__name__}"
                )
            if not self.initial_stub_rate.is_finite():
                raise TypeError(
                    "StubPeriod.initial_stub_rate must be finite, "
                    f"got {self.initial_stub_rate!r}"
                )
        if self.final_stub_rate is not None:
            if not isinstance(self.final_stub_rate, Decimal):
                raise TypeError(
                    "StubPeriod.final_stub_rate must be Decimal, "
                    f"got {type(self.final_stub_rate).__name__}"
                )
            if not self.final_stub_rate.is_finite():
                raise TypeError(
                    "StubPeriod.final_stub_rate must be finite, "
                    f"got {self.final_stub_rate!r}"
                )


# ---------------------------------------------------------------------------
# Rate specifications
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class FixedRateSpecification:
    """Fixed rate with optional step schedule and day count.

    CDM: FixedRateSpecification = rateSchedule + dayCountFraction.
    step_schedule allows rate changes over time (step-up/step-down bonds).
    """

    rate: Decimal
    day_count: DayCountConvention
    step_schedule: tuple[DatedValue, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.rate, Decimal) or not self.rate.is_finite():
            raise TypeError(
                f"FixedRateSpecification.rate must be finite Decimal, "
                f"got {self.rate!r}"
            )
        for i in range(1, len(self.step_schedule)):
            if self.step_schedule[i].date <= self.step_schedule[i - 1].date:
                raise TypeError(
                    "FixedRateSpecification.step_schedule: dates must be "
                    "strictly ascending, but "
                    f"step_schedule[{i - 1}].date="
                    f"{self.step_schedule[i - 1].date} >= "
                    f"step_schedule[{i}].date={self.step_schedule[i].date}"
                )


@final
@dataclass(frozen=True, slots=True)
class FloatingRateSpecification:
    """Floating rate index with spread, cap, floor, and multiplier.

    CDM: FloatingRateSpecification = floatingRateIndex + spreadSchedule
         + capRateSchedule + floorRateSchedule + floatingRateMultiplierSchedule
         + negativeInterestRateTreatment.
    """

    float_rate_index: FloatingRateIndex
    spread: Decimal
    day_count: DayCountConvention
    cap: Decimal | None = None
    floor: Decimal | None = None
    multiplier: Decimal = Decimal("1")
    negative_treatment: NegativeTreatmentEnum = "NegativeInterestRateMethod"

    def __post_init__(self) -> None:
        if not isinstance(self.spread, Decimal) or not self.spread.is_finite():
            raise TypeError(
                f"FloatingRateSpecification.spread must be finite Decimal, "
                f"got {self.spread!r}"
            )
        if self.cap is not None and (
            not isinstance(self.cap, Decimal) or not self.cap.is_finite()
        ):
            raise TypeError(
                "FloatingRateSpecification.cap must be finite Decimal, "
                f"got {self.cap!r}"
            )
        if self.floor is not None and (
            not isinstance(self.floor, Decimal) or not self.floor.is_finite()
        ):
            raise TypeError(
                "FloatingRateSpecification.floor must be finite Decimal, "
                f"got {self.floor!r}"
            )
        if (
            self.cap is not None
            and self.floor is not None
            and self.cap < self.floor
        ):
            raise TypeError(
                f"FloatingRateSpecification: cap ({self.cap}) "
                f"must be >= floor ({self.floor})"
            )
        if not isinstance(self.multiplier, Decimal) or not self.multiplier.is_finite():
            raise TypeError(
                "FloatingRateSpecification.multiplier must be finite Decimal, "
                f"got {self.multiplier!r}"
            )


type RateSpecification = FixedRateSpecification | FloatingRateSpecification
