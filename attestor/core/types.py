"""Core types: UtcDatetime, FrozenMap, BitemporalEnvelope, IdempotencyKey, EventTime.

Phase A additions: PeriodUnit, Period, Frequency, DatedValue, Schedule,
                   AdjustableDate, RelativeDateOffset.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, ClassVar, Literal, final

from attestor.core.result import Err, Ok

# ---------------------------------------------------------------------------
# Day count conventions (moved from fx_types.py for import ordering)
# ---------------------------------------------------------------------------


class DayCountConvention(Enum):
    """Day count conventions for accrual period calculation.

    ISDA 2006 Section 4.16.
    """

    ACT_360 = "ACT/360"
    ACT_365 = "ACT/365"
    THIRTY_360 = "30/360"
    ACT_ACT_ISDA = "ACT/ACT.ISDA"
    ACT_ACT_ICMA = "ACT/ACT.ICMA"
    THIRTY_E_360 = "30E/360"
    ACT_365L = "ACT/365L"
    BUS_252 = "BUS/252"


@final
@dataclass(frozen=True, slots=True)
class UtcDatetime:
    """Timezone-aware UTC datetime. Naive datetimes are rejected."""

    value: datetime

    def __post_init__(self) -> None:
        if self.value.tzinfo is None:
            raise TypeError("UtcDatetime requires timezone-aware datetime, got naive")

    @staticmethod
    def parse(raw: datetime) -> Ok[UtcDatetime] | Err[str]:
        """Parse a datetime, rejecting naive (no tzinfo) datetimes."""
        if raw.tzinfo is None:
            return Err("UtcDatetime requires timezone-aware datetime, got naive")
        return Ok(UtcDatetime(value=raw.astimezone(UTC)))

    @staticmethod
    def now() -> UtcDatetime:
        """Current UTC time."""
        return UtcDatetime(value=datetime.now(tz=UTC))


@final
@dataclass(frozen=True, slots=True)
class FrozenMap[K, V]:
    """Immutable sorted mapping for deterministic hashing and serialization.

    Entries are stored as a sorted tuple of (key, value) pairs.
    This guarantees: (a) immutability, (b) deterministic iteration order,
    (c) canonical serialization for content-addressing.
    """

    _entries: tuple[tuple[K, V], ...]

    EMPTY: ClassVar[FrozenMap[Any, Any]]  # Assigned after class definition

    @staticmethod
    def create(items: dict[K, V] | Iterable[tuple[K, V]]) -> Ok[FrozenMap[K, V]] | Err[str]:
        """Create a FrozenMap from a dict or iterable of (key, value) pairs.

        Duplicate keys: last value wins (like dict constructor). GAP-10.
        Non-comparable keys: returns Err. GAP-08.
        """
        if isinstance(items, dict):  # noqa: SIM108
            d = items
        else:
            d = dict(items)  # deduplicates: last value wins (GAP-10)
        try:
            entries = tuple(sorted(d.items(), key=lambda kv: kv[0]))
        except TypeError as e:
            return Err(f"FrozenMap keys must be comparable: {e}")
        return Ok(FrozenMap(_entries=entries))

    def get(self, key: K, default: V | None = None) -> V | None:
        """Return value for key, or default if not found."""
        for k, v in self._entries:
            if k == key:
                return v
        return default

    def __getitem__(self, key: K) -> V:
        for k, v in self._entries:
            if k == key:
                return v
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        return any(k == key for k, _ in self._entries)

    def __iter__(self) -> Iterator[K]:
        return (k for k, _ in self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def items(self) -> tuple[tuple[K, V], ...]:
        """Return the sorted (key, value) entries."""
        return self._entries

    def to_dict(self) -> dict[K, V]:
        """Convert to a regular dict (for serialization boundaries)."""
        return dict(self._entries)


FrozenMap.EMPTY = FrozenMap(_entries=())


@final
@dataclass(frozen=True, slots=True)
class BitemporalEnvelope[T]:
    """Wraps payload with event-time and knowledge-time."""

    payload: T
    event_time: UtcDatetime
    knowledge_time: UtcDatetime


@final
@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    """Non-empty string key for idempotent operations."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise TypeError("IdempotencyKey requires non-empty string")

    @staticmethod
    def create(raw: str) -> Ok[IdempotencyKey] | Err[str]:
        """Create an IdempotencyKey, rejecting empty strings."""
        if not raw:
            return Err("IdempotencyKey requires non-empty string")
        return Ok(IdempotencyKey(value=raw))


@final
@dataclass(frozen=True, slots=True)
class EventTime:
    """Temporal ordering wrapper using UtcDatetime."""

    value: UtcDatetime


# ---------------------------------------------------------------------------
# Phase A: Date and Schedule Foundation
# ---------------------------------------------------------------------------

type PeriodUnit = Literal["D", "W", "M", "Y"]


@final
@dataclass(frozen=True, slots=True)
class Period:
    """A time period: multiplier x unit (e.g., 3M, 1Y, 5D).

    CDM: Period = periodMultiplier + period.
    """

    multiplier: int
    unit: PeriodUnit

    def __post_init__(self) -> None:
        if self.multiplier <= 0:
            raise TypeError(f"Period.multiplier must be > 0, got {self.multiplier}")


class RollConventionEnum(Enum):
    """How to determine period end dates when generating schedules.

    Subset of CDM's 30+ values. Covers the most common conventions.
    """

    EOM = "EOM"      # End of month
    IMM = "IMM"      # 3rd Wednesday of month (IMM dates)
    DOM_1 = "1"      # 1st of month
    DOM_15 = "15"    # 15th of month
    DOM_20 = "20"    # 20th of month
    DOM_28 = "28"    # 28th of month
    DOM_30 = "30"    # 30th of month
    NONE = "NONE"    # No roll adjustment


@final
@dataclass(frozen=True, slots=True)
class Frequency:
    """Coupled period + roll convention for schedule generation.

    CDM: Frequency = period + rollConvention.
    """

    period: Period
    roll_convention: RollConventionEnum


@final
@dataclass(frozen=True, slots=True)
class DatedValue:
    """A single (date, value) pair for step schedules.

    CDM: DatedValue = date + value.
    """

    date: date
    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise TypeError(f"DatedValue.value must be finite Decimal, got {self.value!r}")


@final
@dataclass(frozen=True, slots=True)
class Schedule:
    """A step schedule: ordered sequence of (date, value) pairs.

    CDM: Schedule = initialValue + step[*].
    Invariants:
    - At least one entry (len >= 1)
    - Strict date monotonicity: dates[i] < dates[i+1]
    """

    entries: tuple[DatedValue, ...]

    def __post_init__(self) -> None:
        if not self.entries:
            raise TypeError("Schedule must contain at least one entry")
        for i in range(len(self.entries) - 1):
            if self.entries[i].date >= self.entries[i + 1].date:
                raise TypeError(
                    f"Schedule: dates must be strictly monotonic, "
                    f"but entries[{i}].date={self.entries[i].date} >= "
                    f"entries[{i + 1}].date={self.entries[i + 1].date}"
                )


type BusinessDayConvention = Literal[
    "MOD_FOLLOWING", "FOLLOWING", "PRECEDING", "NONE",
]


@final
@dataclass(frozen=True, slots=True)
class BusinessDayAdjustments:
    """Convention + business centers for adjusting dates to good business days.

    CDM: BusinessDayAdjustments = businessDayConvention + businessCenters.
    """

    convention: BusinessDayConvention
    business_centers: frozenset[str]  # e.g. frozenset({"GBLO", "USNY"})

    def __post_init__(self) -> None:
        if self.convention != "NONE" and not self.business_centers:
            raise TypeError(
                "BusinessDayAdjustments: business_centers required "
                f"when convention is {self.convention!r}"
            )


@final
@dataclass(frozen=True, slots=True)
class AdjustableDate:
    """A date that carries its own adjustment rule.

    CDM: AdjustableDate = unadjustedDate + dateAdjustments.
    """

    unadjusted_date: date
    adjustments: BusinessDayAdjustments | None  # None = no adjustment needed


@final
@dataclass(frozen=True, slots=True)
class RelativeDateOffset:
    """A date offset relative to some reference date.

    CDM: RelativeDateOffset = period + dayType + businessDayConvention + businessCenters.
    """

    period: Period
    day_type: Literal["Business", "Calendar"]
    business_day_convention: BusinessDayConvention
    business_centers: frozenset[str]

    def __post_init__(self) -> None:
        if self.business_day_convention != "NONE" and not self.business_centers:
            raise TypeError(
                "RelativeDateOffset: business_centers required "
                f"when business_day_convention is {self.business_day_convention!r}"
            )


# ---------------------------------------------------------------------------
# Phase A: Counterparty direction
# ---------------------------------------------------------------------------

type CounterpartyRole = Literal["PARTY1", "PARTY2"]


@final
@dataclass(frozen=True, slots=True)
class PayerReceiver:
    """Who pays and who receives for a given payout.

    CDM: PayerReceiver = payer + receiver (CounterpartyRoleEnum).
    Invariant: payer != receiver (a party cannot pay itself).
    """

    payer: CounterpartyRole
    receiver: CounterpartyRole

    def __post_init__(self) -> None:
        if self.payer == self.receiver:
            raise TypeError(
                f"PayerReceiver: payer must differ from receiver, both are {self.payer!r}"
            )


# ---------------------------------------------------------------------------
# Phase A: Schedule types (moved from instrument/types.py for import ordering)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class CalculationPeriodDates:
    """Effective/termination dates with schedule generation parameters.

    CDM: CalculationPeriodDates = effectiveDate + terminationDate + frequency
         + rollConvention + firstPeriodStartDate + lastRegularPeriodEndDate + BDA.
    """

    effective_date: AdjustableDate
    termination_date: AdjustableDate
    frequency: Frequency
    business_day_adjustments: BusinessDayAdjustments
    first_period_start_date: date | None = None  # Stub at start
    last_regular_period_end_date: date | None = None  # Stub at end

    def __post_init__(self) -> None:
        eff = self.effective_date.unadjusted_date
        term = self.termination_date.unadjusted_date
        if eff >= term:
            raise TypeError(
                f"CalculationPeriodDates: effective_date ({eff}) "
                f"must be < termination_date ({term})"
            )
        fpsd = self.first_period_start_date
        lrped = self.last_regular_period_end_date
        # Stub start must be <= effective and < termination
        if fpsd is not None:
            if fpsd > eff:
                raise TypeError(
                    "CalculationPeriodDates: "
                    "first_period_start_date must be <= effective_date"
                )
            if fpsd >= term:
                raise TypeError(
                    "CalculationPeriodDates: "
                    "first_period_start_date must be < termination_date"
                )
        # Last regular end must be > effective and <= termination
        if lrped is not None:
            if lrped <= eff:
                raise TypeError(
                    "CalculationPeriodDates: "
                    "last_regular_period_end_date must be > effective_date"
                )
            if lrped > term:
                raise TypeError(
                    "CalculationPeriodDates: "
                    "last_regular_period_end_date must be <= termination_date"
                )
        # Cross-validate: stub start < last regular end
        if fpsd is not None and lrped is not None and fpsd >= lrped:
            raise TypeError(
                "CalculationPeriodDates: first_period_start_date "
                "must be < last_regular_period_end_date"
            )


@final
@dataclass(frozen=True, slots=True)
class PaymentDates:
    """Payment schedule parameters for a payout leg.

    CDM: PaymentDates = paymentFrequency + payRelativeTo + paymentDaysOffset + BDA.
    """

    payment_frequency: Frequency
    pay_relative_to: Literal[
        "CalculationPeriodStartDate", "CalculationPeriodEndDate",
    ]
    payment_day_offset: int  # Number of business days offset (can be 0)
    business_day_adjustments: BusinessDayAdjustments

    def __post_init__(self) -> None:
        if self.payment_day_offset < 0:
            raise TypeError(
                f"PaymentDates: payment_day_offset must be >= 0, "
                f"got {self.payment_day_offset}"
            )
