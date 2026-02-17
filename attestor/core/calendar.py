"""Business day calendar and date adjustment infrastructure.

Phase 3: day count fraction computations.
Phase A: adjust_date(), expanded DayCountConvention (8 conventions).

Type definitions live in core/types.py. This module provides functions.
"""

from __future__ import annotations

import calendar as _cal
from datetime import date, timedelta
from decimal import Decimal
from typing import assert_never

from attestor.core.types import BusinessDayConvention, DayCountConvention

# ---------------------------------------------------------------------------
# Business day helpers (weekends only — holiday calendars deferred)
# ---------------------------------------------------------------------------


def _is_business_day(d: date) -> bool:
    """Check if date is a weekday (Mon-Fri). Holiday calendars deferred."""
    return d.weekday() < 5


def adjust_date(d: date, convention: BusinessDayConvention) -> date:
    """Adjust a date according to a business day convention.

    MOD_FOLLOWING: move to next business day, unless that crosses a month
                   boundary, in which case move to previous business day.
    FOLLOWING: move to next business day.
    PRECEDING: move to previous business day.
    NONE: no adjustment.
    """
    match convention:
        case "NONE":
            return d
        case "FOLLOWING":
            result = d
            while not _is_business_day(result):
                result += timedelta(days=1)
            return result
        case "PRECEDING":
            result = d
            while not _is_business_day(result):
                result -= timedelta(days=1)
            return result
        case "MOD_FOLLOWING":
            result = d
            while not _is_business_day(result):
                result += timedelta(days=1)
            # If crossed month boundary, go back instead
            if result.month != d.month:
                result = d
                while not _is_business_day(result):
                    result -= timedelta(days=1)
            return result
        case _never:
            assert_never(_never)


def add_business_days(start: date, days: int) -> date:
    """Add business days (skip weekends only — Phase 1/2 simplification)."""
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon=0 .. Fri=4
            added += 1
    return current


# ---------------------------------------------------------------------------
# Day count fraction computation
# ---------------------------------------------------------------------------


def _is_leap_year(y: int) -> bool:
    return _cal.isleap(y)


def _days_in_year(y: int) -> int:
    return 366 if _is_leap_year(y) else 365


def _act_act_isda(start: date, end: date) -> Decimal:
    """ACT/ACT.ISDA: actual days / actual days in year, split across year boundaries.

    Precondition: start <= end (enforced by caller day_count_fraction).
    """
    total = Decimal("0")
    current = start
    while current.year < end.year:
        year_end = date(current.year + 1, 1, 1)
        days_in_period = (year_end - current).days
        total += Decimal(str(days_in_period)) / Decimal(str(_days_in_year(current.year)))
        current = year_end
    # Remaining days in the final year
    days_in_period = (end - current).days
    if days_in_period > 0:
        total += Decimal(str(days_in_period)) / Decimal(str(_days_in_year(current.year)))
    return total


def _thirty_e_360(start: date, end: date) -> Decimal:
    """30E/360 (Eurobond basis): both d1 and d2 capped at 30."""
    d1 = min(start.day, 30)
    d2 = min(end.day, 30)
    m1, y1 = start.month, start.year
    m2, y2 = end.month, end.year
    days = Decimal(str(360 * (y2 - y1) + 30 * (m2 - m1) + (d2 - d1)))
    return days / Decimal("360")


def day_count_fraction(
    start: date, end: date, convention: DayCountConvention,
) -> Decimal:
    """Compute year fraction for the accrual period [start, end).

    Precondition: start <= end. Raises TypeError otherwise to prevent
    silent sign inconsistencies across conventions (Formalis Finding 2).
    """
    if start > end:
        raise TypeError(
            f"day_count_fraction: start ({start}) must be <= end ({end})"
        )
    match convention:
        case DayCountConvention.ACT_360:
            return Decimal(str((end - start).days)) / Decimal("360")
        case DayCountConvention.ACT_365:
            return Decimal(str((end - start).days)) / Decimal("365")
        case DayCountConvention.THIRTY_360:
            # ISDA 2006 Section 4.16(f) "30/360" (Bond Basis):
            # D1 = min(start.day, 30)
            # D2 = 30 if (end.day == 31 AND D1 >= 30) else end.day
            d1 = min(start.day, 30)
            d2 = 30 if (end.day == 31 and d1 >= 30) else end.day
            m1, y1 = start.month, start.year
            m2, y2 = end.month, end.year
            days = Decimal(str(360 * (y2 - y1) + 30 * (m2 - m1) + (d2 - d1)))
            return days / Decimal("360")
        case DayCountConvention.ACT_ACT_ISDA:
            return _act_act_isda(start, end)
        case DayCountConvention.ACT_ACT_ICMA:
            # Simplified: uses ACT/ACT.ISDA as approximation.
            # Full ICMA requires coupon period context (deferred to Phase C).
            return _act_act_isda(start, end)
        case DayCountConvention.THIRTY_E_360:
            return _thirty_e_360(start, end)
        case DayCountConvention.ACT_365L:
            # ACT/365L: actual days / 365 (or 366 if period contains Feb 29)
            divisor = 365
            y_start, y_end = start.year, end.year
            for y in range(y_start, y_end + 1):
                if _is_leap_year(y):
                    feb29 = date(y, 2, 29)
                    if start < feb29 <= end:
                        divisor = 366
                        break
            return Decimal(str((end - start).days)) / Decimal(str(divisor))
        case DayCountConvention.BUS_252:
            # BUS/252: count business days between dates / 252
            count = 0
            current = start
            while current < end:
                current += timedelta(days=1)
                if _is_business_day(current):
                    count += 1
            return Decimal(str(count)) / Decimal("252")
        case _never:
            assert_never(_never)
