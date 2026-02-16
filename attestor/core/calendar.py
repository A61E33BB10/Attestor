"""Business day calendar — weekends only for now.

Phase 3 adds day count fraction computations.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import assert_never

from attestor.instrument.fx_types import DayCountConvention


def add_business_days(start: date, days: int) -> date:
    """Add business days (skip weekends only — Phase 1/2 simplification)."""
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon=0 .. Fri=4
            added += 1
    return current


def day_count_fraction(
    start: date, end: date, convention: DayCountConvention,
) -> Decimal:
    """Compute year fraction between two dates under a day count convention."""
    match convention:
        case DayCountConvention.ACT_360:
            return Decimal(str((end - start).days)) / Decimal("360")
        case DayCountConvention.ACT_365:
            return Decimal(str((end - start).days)) / Decimal("365")
        case DayCountConvention.THIRTY_360:
            d1, m1, y1 = min(start.day, 30), start.month, start.year
            d2, m2, y2 = min(end.day, 30), end.month, end.year
            days = Decimal(str(360 * (y2 - y1) + 30 * (m2 - m1) + (d2 - d1)))
            return days / Decimal("360")
        case _never:
            assert_never(_never)
