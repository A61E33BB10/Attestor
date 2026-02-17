"""Tests for Phase A: Date and Schedule Foundation.

Covers all new types, invariants, and functions introduced in Phase A:
- PeriodUnit, Period, RollConventionEnum, Frequency, DatedValue, Schedule
- BusinessDayConvention, BusinessDayAdjustments, AdjustableDate, RelativeDateOffset
- CounterpartyRole, PayerReceiver
- CalculationPeriodDates, PaymentDates
- adjust_date() (all 4 conventions)
- day_count_fraction() (5 new conventions: ACT/ACT.ISDA, ACT/ACT.ICMA, 30E/360, ACT/365L, BUS/252)
- DayCountConvention expansion to 8 members
- ISO 4217 currency expansion
- PayerReceiver integration on FixedLeg/FloatLeg/CDSPayoutSpec/SwaptionPayoutSpec
- IRSwapPayoutSpec consistency invariant
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from attestor.core.calendar import adjust_date, day_count_fraction
from attestor.core.money import VALID_CURRENCIES
from attestor.core.result import Ok
from attestor.core.types import (
    AdjustableDate,
    BusinessDayAdjustments,
    DatedValue,
    Frequency,
    PayerReceiver,
    Period,
    RelativeDateOffset,
    RollConventionEnum,
    Schedule,
)
from attestor.instrument.fx_types import (
    DayCountConvention,
    FixedLeg,
    FloatLeg,
    IRSwapPayoutSpec,
    PaymentFrequency,
)
from attestor.instrument.types import (
    CalculationPeriodDates,
    PaymentDates,
)

_PR = PayerReceiver(payer="PARTY1", receiver="PARTY2")
_PR_INV = PayerReceiver(payer="PARTY2", receiver="PARTY1")
_BDA = BusinessDayAdjustments(convention="MOD_FOLLOWING", business_centers=frozenset({"GBLO"}))


# ===========================================================================
# Period
# ===========================================================================


class TestPeriod:
    def test_valid_periods(self) -> None:
        for unit in ("D", "W", "M", "Y"):
            p = Period(multiplier=1, unit=unit)
            assert p.multiplier == 1
            assert p.unit == unit

    def test_large_multiplier(self) -> None:
        p = Period(multiplier=360, unit="D")
        assert p.multiplier == 360

    def test_zero_multiplier_rejected(self) -> None:
        with pytest.raises(TypeError, match="must be > 0"):
            Period(multiplier=0, unit="M")

    def test_negative_multiplier_rejected(self) -> None:
        with pytest.raises(TypeError, match="must be > 0"):
            Period(multiplier=-1, unit="Y")

    def test_frozen(self) -> None:
        p = Period(multiplier=3, unit="M")
        with pytest.raises(AttributeError):
            p.multiplier = 6  # type: ignore[misc]


# ===========================================================================
# RollConventionEnum
# ===========================================================================


class TestRollConventionEnum:
    def test_member_count(self) -> None:
        assert len(RollConventionEnum) == 8

    def test_expected_members(self) -> None:
        names = {m.name for m in RollConventionEnum}
        expected = {"EOM", "IMM", "DOM_1", "DOM_15", "DOM_20", "DOM_28", "DOM_30", "NONE"}
        assert names == expected

    def test_values_unique(self) -> None:
        vals = [m.value for m in RollConventionEnum]
        assert len(vals) == len(set(vals))


# ===========================================================================
# Frequency
# ===========================================================================


class TestFrequency:
    def test_valid(self) -> None:
        f = Frequency(period=Period(multiplier=3, unit="M"), roll_convention=RollConventionEnum.EOM)
        assert f.period.multiplier == 3
        assert f.roll_convention == RollConventionEnum.EOM

    def test_frozen(self) -> None:
        p = Period(multiplier=1, unit="Y")
        f = Frequency(period=p, roll_convention=RollConventionEnum.NONE)
        with pytest.raises(AttributeError):
            f.period = Period(multiplier=2, unit="Y")  # type: ignore[misc]


# ===========================================================================
# DatedValue
# ===========================================================================


class TestDatedValue:
    def test_valid(self) -> None:
        dv = DatedValue(date=date(2024, 1, 15), value=Decimal("0.025"))
        assert dv.date == date(2024, 1, 15)
        assert dv.value == Decimal("0.025")

    def test_non_decimal_rejected(self) -> None:
        with pytest.raises(TypeError, match="finite Decimal"):
            DatedValue(date=date(2024, 1, 1), value=0.5)  # type: ignore[arg-type]

    def test_nan_rejected(self) -> None:
        with pytest.raises(TypeError, match="finite Decimal"):
            DatedValue(date=date(2024, 1, 1), value=Decimal("NaN"))

    def test_infinity_rejected(self) -> None:
        with pytest.raises(TypeError, match="finite Decimal"):
            DatedValue(date=date(2024, 1, 1), value=Decimal("Inf"))

    def test_negative_value_allowed(self) -> None:
        dv = DatedValue(date=date(2024, 1, 1), value=Decimal("-0.01"))
        assert dv.value == Decimal("-0.01")

    def test_zero_value_allowed(self) -> None:
        dv = DatedValue(date=date(2024, 1, 1), value=Decimal("0"))
        assert dv.value == Decimal("0")


# ===========================================================================
# Schedule
# ===========================================================================


class TestSchedule:
    def test_single_entry(self) -> None:
        s = Schedule(entries=(DatedValue(date=date(2024, 1, 1), value=Decimal("0.05")),))
        assert len(s.entries) == 1

    def test_monotonic_dates(self) -> None:
        s = Schedule(entries=(
            DatedValue(date=date(2024, 1, 1), value=Decimal("0.04")),
            DatedValue(date=date(2024, 4, 1), value=Decimal("0.05")),
            DatedValue(date=date(2024, 7, 1), value=Decimal("0.06")),
        ))
        assert len(s.entries) == 3

    def test_empty_rejected(self) -> None:
        with pytest.raises(TypeError, match="at least one entry"):
            Schedule(entries=())

    def test_duplicate_dates_rejected(self) -> None:
        with pytest.raises(TypeError, match="strictly monotonic"):
            Schedule(entries=(
                DatedValue(date=date(2024, 1, 1), value=Decimal("0.04")),
                DatedValue(date=date(2024, 1, 1), value=Decimal("0.05")),
            ))

    def test_non_monotonic_dates_rejected(self) -> None:
        with pytest.raises(TypeError, match="strictly monotonic"):
            Schedule(entries=(
                DatedValue(date=date(2024, 4, 1), value=Decimal("0.05")),
                DatedValue(date=date(2024, 1, 1), value=Decimal("0.04")),
            ))

    def test_frozen(self) -> None:
        s = Schedule(entries=(DatedValue(date=date(2024, 1, 1), value=Decimal("0.05")),))
        with pytest.raises(AttributeError):
            s.entries = ()  # type: ignore[misc]


# ===========================================================================
# BusinessDayAdjustments
# ===========================================================================


class TestBusinessDayAdjustments:
    def test_none_convention_no_centers(self) -> None:
        bda = BusinessDayAdjustments(convention="NONE", business_centers=frozenset())
        assert bda.convention == "NONE"

    def test_following_with_centers(self) -> None:
        bda = BusinessDayAdjustments(
            convention="FOLLOWING", business_centers=frozenset({"USNY", "GBLO"}),
        )
        assert "USNY" in bda.business_centers

    def test_mod_following_no_centers_rejected(self) -> None:
        with pytest.raises(TypeError, match="business_centers required"):
            BusinessDayAdjustments(convention="MOD_FOLLOWING", business_centers=frozenset())

    def test_following_no_centers_rejected(self) -> None:
        with pytest.raises(TypeError, match="business_centers required"):
            BusinessDayAdjustments(convention="FOLLOWING", business_centers=frozenset())

    def test_preceding_no_centers_rejected(self) -> None:
        with pytest.raises(TypeError, match="business_centers required"):
            BusinessDayAdjustments(convention="PRECEDING", business_centers=frozenset())


# ===========================================================================
# AdjustableDate
# ===========================================================================


class TestAdjustableDate:
    def test_with_adjustments(self) -> None:
        ad = AdjustableDate(unadjusted_date=date(2024, 3, 30), adjustments=_BDA)
        assert ad.unadjusted_date == date(2024, 3, 30)
        assert ad.adjustments is not None

    def test_no_adjustments(self) -> None:
        ad = AdjustableDate(unadjusted_date=date(2024, 1, 15), adjustments=None)
        assert ad.adjustments is None


# ===========================================================================
# RelativeDateOffset
# ===========================================================================


class TestRelativeDateOffset:
    def test_valid(self) -> None:
        rdo = RelativeDateOffset(
            period=Period(multiplier=2, unit="D"),
            day_type="Business",
            business_day_convention="FOLLOWING",
            business_centers=frozenset({"USNY"}),
        )
        assert rdo.period.multiplier == 2
        assert rdo.day_type == "Business"

    def test_calendar_day_type(self) -> None:
        rdo = RelativeDateOffset(
            period=Period(multiplier=5, unit="D"),
            day_type="Calendar",
            business_day_convention="NONE",
            business_centers=frozenset(),
        )
        assert rdo.day_type == "Calendar"

    def test_non_none_convention_no_centers_rejected(self) -> None:
        with pytest.raises(TypeError, match="business_centers required"):
            RelativeDateOffset(
                period=Period(multiplier=2, unit="D"),
                day_type="Business",
                business_day_convention="FOLLOWING",
                business_centers=frozenset(),
            )


# ===========================================================================
# PayerReceiver
# ===========================================================================


class TestPayerReceiver:
    def test_valid_party1_pays(self) -> None:
        pr = PayerReceiver(payer="PARTY1", receiver="PARTY2")
        assert pr.payer == "PARTY1"
        assert pr.receiver == "PARTY2"

    def test_valid_party2_pays(self) -> None:
        pr = PayerReceiver(payer="PARTY2", receiver="PARTY1")
        assert pr.payer == "PARTY2"
        assert pr.receiver == "PARTY1"

    def test_same_party_rejected(self) -> None:
        with pytest.raises(TypeError, match="payer must differ from receiver"):
            PayerReceiver(payer="PARTY1", receiver="PARTY1")

    def test_same_party2_rejected(self) -> None:
        with pytest.raises(TypeError, match="payer must differ from receiver"):
            PayerReceiver(payer="PARTY2", receiver="PARTY2")

    def test_frozen(self) -> None:
        pr = PayerReceiver(payer="PARTY1", receiver="PARTY2")
        with pytest.raises(AttributeError):
            pr.payer = "PARTY2"  # type: ignore[misc]


# ===========================================================================
# adjust_date (4 conventions)
# ===========================================================================


class TestAdjustDate:
    def test_none_no_change(self) -> None:
        """NONE: weekend dates returned as-is."""
        saturday = date(2024, 1, 6)  # Saturday
        assert adjust_date(saturday, "NONE") == saturday

    def test_following_weekday_unchanged(self) -> None:
        """FOLLOWING: already a business day → no change."""
        monday = date(2024, 1, 8)
        assert adjust_date(monday, "FOLLOWING") == monday

    def test_following_saturday_to_monday(self) -> None:
        """FOLLOWING: Saturday → next Monday."""
        saturday = date(2024, 1, 6)
        assert adjust_date(saturday, "FOLLOWING") == date(2024, 1, 8)

    def test_following_sunday_to_monday(self) -> None:
        """FOLLOWING: Sunday → next Monday."""
        sunday = date(2024, 1, 7)
        assert adjust_date(sunday, "FOLLOWING") == date(2024, 1, 8)

    def test_preceding_saturday_to_friday(self) -> None:
        """PRECEDING: Saturday → previous Friday."""
        saturday = date(2024, 1, 6)
        assert adjust_date(saturday, "PRECEDING") == date(2024, 1, 5)

    def test_preceding_sunday_to_friday(self) -> None:
        """PRECEDING: Sunday → previous Friday."""
        sunday = date(2024, 1, 7)
        assert adjust_date(sunday, "PRECEDING") == date(2024, 1, 5)

    def test_preceding_weekday_unchanged(self) -> None:
        friday = date(2024, 1, 5)
        assert adjust_date(friday, "PRECEDING") == friday

    def test_mod_following_normal(self) -> None:
        """MOD_FOLLOWING: weekend → next Monday when same month."""
        saturday = date(2024, 1, 6)
        assert adjust_date(saturday, "MOD_FOLLOWING") == date(2024, 1, 8)

    def test_mod_following_month_boundary(self) -> None:
        """MOD_FOLLOWING: if next business day crosses month, go backwards."""
        # March 30, 2024 is Saturday. Following → April 1 (crosses month).
        # So MOD_FOLLOWING → March 29 (Friday).
        saturday_eom = date(2024, 3, 30)
        assert adjust_date(saturday_eom, "MOD_FOLLOWING") == date(2024, 3, 29)

    def test_mod_following_sunday_eom(self) -> None:
        """March 31, 2024 is Sunday. Following → April 1. MOD → March 29 (Fri)."""
        sunday_eom = date(2024, 3, 31)
        assert adjust_date(sunday_eom, "MOD_FOLLOWING") == date(2024, 3, 29)


# ===========================================================================
# day_count_fraction (new conventions)
# ===========================================================================


class TestDayCountFractionNewConventions:
    """Test the 5 new day count conventions added in Phase A."""

    def test_act_act_isda_same_year(self) -> None:
        # 2024 is leap year (366 days). Jan 1 to Jul 1 = 182 days.
        start, end = date(2024, 1, 1), date(2024, 7, 1)
        dcf = day_count_fraction(start, end, DayCountConvention.ACT_ACT_ISDA)
        expected = Decimal("182") / Decimal("366")
        assert dcf == expected

    def test_act_act_isda_cross_year(self) -> None:
        # Dec 1, 2023 to Mar 1, 2024.
        # 2023 (non-leap, 365): Dec 1 to Jan 1 = 31 days → 31/365
        # 2024 (leap, 366): Jan 1 to Mar 1 = 60 days → 60/366
        start, end = date(2023, 12, 1), date(2024, 3, 1)
        dcf = day_count_fraction(start, end, DayCountConvention.ACT_ACT_ISDA)
        expected = Decimal("31") / Decimal("365") + Decimal("60") / Decimal("366")
        assert dcf == expected

    def test_act_act_isda_same_date(self) -> None:
        d = date(2024, 6, 15)
        assert day_count_fraction(d, d, DayCountConvention.ACT_ACT_ISDA) == Decimal("0")

    def test_act_act_icma_delegates_to_isda(self) -> None:
        """Phase A ICMA implementation delegates to ISDA (full ICMA deferred to Phase C)."""
        start, end = date(2024, 1, 1), date(2024, 7, 1)
        isda = day_count_fraction(start, end, DayCountConvention.ACT_ACT_ISDA)
        icma = day_count_fraction(start, end, DayCountConvention.ACT_ACT_ICMA)
        assert icma == isda

    def test_thirty_e_360(self) -> None:
        # 30E/360: d1=min(31,30)=30, d2=min(15,30)=15.
        # 360*(2024-2024) + 30*(7-1) + (15-30) = 0 + 180 - 15 = 165
        # 165/360 = 0.458333...
        start, end = date(2024, 1, 31), date(2024, 7, 15)
        dcf = day_count_fraction(start, end, DayCountConvention.THIRTY_E_360)
        expected = Decimal("165") / Decimal("360")
        assert dcf == expected

    def test_thirty_e_360_vs_thirty_360_both_31st(self) -> None:
        """When both dates are 31st and D1>=30: 30/360 caps D2 → same as 30E/360."""
        start, end = date(2024, 1, 31), date(2024, 7, 31)
        e360 = day_count_fraction(start, end, DayCountConvention.THIRTY_E_360)
        t360 = day_count_fraction(start, end, DayCountConvention.THIRTY_360)
        assert e360 == t360 == Decimal("180") / Decimal("360")

    def test_thirty_360_vs_thirty_e_360_diverge(self) -> None:
        """ISDA 30/360: D2 not capped when D1 < 30. 30E/360 always caps D2."""
        # Jan 15 to Jul 31: D1=15 (<30), so ISDA 30/360 keeps D2=31.
        # 30E/360 caps D2 to 30.
        start, end = date(2024, 1, 15), date(2024, 7, 31)
        t360 = day_count_fraction(start, end, DayCountConvention.THIRTY_360)
        e360 = day_count_fraction(start, end, DayCountConvention.THIRTY_E_360)
        # 30/360: 360*0 + 30*6 + (31-15) = 196 → 196/360
        assert t360 == Decimal("196") / Decimal("360")
        # 30E/360: 360*0 + 30*6 + (30-15) = 195 → 195/360
        assert e360 == Decimal("195") / Decimal("360")
        assert t360 != e360

    def test_act_365l_no_leap(self) -> None:
        # 2023 non-leap year. Jan 1 to Jul 1 = 181 days. Divisor = 365.
        start, end = date(2023, 1, 1), date(2023, 7, 1)
        dcf = day_count_fraction(start, end, DayCountConvention.ACT_365L)
        assert dcf == Decimal("181") / Decimal("365")

    def test_act_365l_with_leap(self) -> None:
        # 2024 is leap. Period contains Feb 29 → divisor = 366.
        start, end = date(2024, 1, 1), date(2024, 7, 1)
        dcf = day_count_fraction(start, end, DayCountConvention.ACT_365L)
        assert dcf == Decimal("182") / Decimal("366")

    def test_act_365l_leap_year_but_outside_feb29(self) -> None:
        # 2024 is leap, but Mar 1 to Jul 1 doesn't contain Feb 29 → divisor = 365.
        start, end = date(2024, 3, 1), date(2024, 7, 1)
        dcf = day_count_fraction(start, end, DayCountConvention.ACT_365L)
        assert dcf == Decimal("122") / Decimal("365")

    def test_bus_252(self) -> None:
        # Mon Jan 1 to Mon Jan 8, 2024: 5 business days (Tue-Sat... no:
        # Jan 1 (Mon) to Jan 8 (Mon): Jan 2(Tue), 3(Wed), 4(Thu), 5(Fri), 8(Mon) = 5 biz days
        start, end = date(2024, 1, 1), date(2024, 1, 8)
        dcf = day_count_fraction(start, end, DayCountConvention.BUS_252)
        assert dcf == Decimal("5") / Decimal("252")

    def test_bus_252_same_date(self) -> None:
        d = date(2024, 6, 15)
        assert day_count_fraction(d, d, DayCountConvention.BUS_252) == Decimal("0") / Decimal("252")

    def test_start_after_end_rejected(self) -> None:
        """day_count_fraction rejects start > end (Formalis Finding 2)."""
        with pytest.raises(TypeError, match="start.*must be <= end"):
            day_count_fraction(date(2024, 7, 1), date(2024, 1, 1), DayCountConvention.ACT_360)


# ===========================================================================
# DayCountConvention enum expansion
# ===========================================================================


class TestDayCountConventionEnum:
    def test_member_count(self) -> None:
        assert len(DayCountConvention) == 8

    def test_all_members_present(self) -> None:
        expected = {
            "ACT_360", "ACT_365", "THIRTY_360",
            "ACT_ACT_ISDA", "ACT_ACT_ICMA", "THIRTY_E_360", "ACT_365L", "BUS_252",
        }
        assert {m.name for m in DayCountConvention} == expected


# ===========================================================================
# ISO 4217 currency expansion
# ===========================================================================


class TestCurrencyExpansion:
    def test_major_currencies_present(self) -> None:
        for ccy in ("USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"):
            assert ccy in VALID_CURRENCIES

    def test_emerging_market_currencies(self) -> None:
        for ccy in ("CNY", "INR", "BRL", "ZAR", "MXN", "KRW", "TRY", "THB"):
            assert ccy in VALID_CURRENCIES

    def test_zero_decimal_currencies(self) -> None:
        for ccy in ("JPY", "KRW", "VND", "CLP"):
            assert ccy in VALID_CURRENCIES

    def test_three_decimal_currencies(self) -> None:
        for ccy in ("BHD", "KWD", "OMR"):
            assert ccy in VALID_CURRENCIES

    def test_crypto_present(self) -> None:
        assert "BTC" in VALID_CURRENCIES
        assert "ETH" in VALID_CURRENCIES

    def test_minimum_count(self) -> None:
        """ISO 4217 has ~160 active codes. We should have at least 150."""
        assert len(VALID_CURRENCIES) >= 150


# ===========================================================================
# CalculationPeriodDates
# ===========================================================================


_FREQ = Frequency(
    period=Period(multiplier=3, unit="M"),
    roll_convention=RollConventionEnum.NONE,
)
_AD_EFF = AdjustableDate(unadjusted_date=date(2024, 1, 15), adjustments=None)
_AD_TERM = AdjustableDate(unadjusted_date=date(2029, 1, 15), adjustments=None)


class TestCalculationPeriodDates:
    def test_valid_minimal(self) -> None:
        cpd = CalculationPeriodDates(
            effective_date=_AD_EFF,
            termination_date=_AD_TERM,
            frequency=_FREQ,
            business_day_adjustments=_BDA,
        )
        assert cpd.effective_date.unadjusted_date == date(2024, 1, 15)
        assert cpd.first_period_start_date is None
        assert cpd.last_regular_period_end_date is None

    def test_with_stubs(self) -> None:
        cpd = CalculationPeriodDates(
            effective_date=_AD_EFF,
            termination_date=_AD_TERM,
            frequency=_FREQ,
            business_day_adjustments=_BDA,
            first_period_start_date=date(2024, 1, 1),
            last_regular_period_end_date=date(2028, 10, 15),
        )
        assert cpd.first_period_start_date == date(2024, 1, 1)
        assert cpd.last_regular_period_end_date == date(2028, 10, 15)

    def test_eff_gte_term_rejected(self) -> None:
        with pytest.raises(TypeError, match="must be < termination_date"):
            CalculationPeriodDates(
                effective_date=_AD_TERM,
                termination_date=_AD_EFF,
                frequency=_FREQ,
                business_day_adjustments=_BDA,
            )

    def test_equal_dates_rejected(self) -> None:
        with pytest.raises(TypeError, match="must be < termination_date"):
            CalculationPeriodDates(
                effective_date=_AD_EFF,
                termination_date=_AD_EFF,
                frequency=_FREQ,
                business_day_adjustments=_BDA,
            )

    def test_first_period_after_eff_rejected(self) -> None:
        """first_period_start_date must be <= effective_date."""
        msg = "first_period_start_date must be <= effective"
        with pytest.raises(TypeError, match=msg):
            CalculationPeriodDates(
                effective_date=_AD_EFF,
                termination_date=_AD_TERM,
                frequency=_FREQ,
                business_day_adjustments=_BDA,
                first_period_start_date=date(2025, 1, 1),
            )

    def test_last_regular_after_term_rejected(self) -> None:
        """last_regular_period_end_date must be <= termination_date."""
        msg = "last_regular_period_end_date must be <= termination"
        with pytest.raises(TypeError, match=msg):
            CalculationPeriodDates(
                effective_date=_AD_EFF,
                termination_date=_AD_TERM,
                frequency=_FREQ,
                business_day_adjustments=_BDA,
                last_regular_period_end_date=date(2030, 1, 1),
            )

    def test_last_regular_lte_eff_rejected(self) -> None:
        msg = "last_regular_period_end_date must be > effective"
        with pytest.raises(TypeError, match=msg):
            CalculationPeriodDates(
                effective_date=_AD_EFF,
                termination_date=_AD_TERM,
                frequency=_FREQ,
                business_day_adjustments=_BDA,
                last_regular_period_end_date=date(2024, 1, 15),
            )

    def test_stubs_order_is_implied(self) -> None:
        """fpsd <= eff < lrped is guaranteed by individual checks.

        The cross-validation (fpsd < lrped) in __post_init__ is
        defense-in-depth; it cannot fire when individual checks pass
        because fpsd <= eff and lrped > eff imply fpsd < lrped.
        """
        cpd = CalculationPeriodDates(
            effective_date=_AD_EFF,
            termination_date=_AD_TERM,
            frequency=_FREQ,
            business_day_adjustments=_BDA,
            first_period_start_date=date(2024, 1, 10),
            last_regular_period_end_date=date(2028, 10, 15),
        )
        assert cpd.first_period_start_date is not None
        assert cpd.last_regular_period_end_date is not None
        assert cpd.first_period_start_date < cpd.last_regular_period_end_date


# ===========================================================================
# PaymentDates
# ===========================================================================


class TestPaymentDates:
    def test_valid_zero_offset(self) -> None:
        pd = PaymentDates(
            payment_frequency=_FREQ,
            pay_relative_to="CalculationPeriodEndDate",
            payment_day_offset=0,
            business_day_adjustments=_BDA,
        )
        assert pd.payment_day_offset == 0

    def test_valid_positive_offset(self) -> None:
        pd = PaymentDates(
            payment_frequency=_FREQ,
            pay_relative_to="CalculationPeriodStartDate",
            payment_day_offset=2,
            business_day_adjustments=_BDA,
        )
        assert pd.pay_relative_to == "CalculationPeriodStartDate"

    def test_negative_offset_rejected(self) -> None:
        with pytest.raises(TypeError, match="must be >= 0"):
            PaymentDates(
                payment_frequency=_FREQ,
                pay_relative_to="CalculationPeriodEndDate",
                payment_day_offset=-1,
                business_day_adjustments=_BDA,
            )


# ===========================================================================
# PayerReceiver on FixedLeg / FloatLeg
# ===========================================================================


class TestPayerReceiverOnLegs:
    def test_fixed_leg_carries_payer_receiver(self) -> None:
        from attestor.core.money import NonEmptyStr, PositiveDecimal

        leg = FixedLeg(
            payer_receiver=_PR,
            fixed_rate=Decimal("0.03"),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency=NonEmptyStr(value="USD"),
            notional=PositiveDecimal(value=Decimal("1000000")),
        )
        assert leg.payer_receiver.payer == "PARTY1"
        assert leg.payer_receiver.receiver == "PARTY2"

    def test_float_leg_carries_payer_receiver(self) -> None:
        from attestor.core.money import NonEmptyStr, PositiveDecimal

        leg = FloatLeg(
            payer_receiver=_PR_INV,
            float_index=NonEmptyStr(value="SOFR"),
            spread=Decimal("0"),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency=NonEmptyStr(value="USD"),
            notional=PositiveDecimal(value=Decimal("1000000")),
        )
        assert leg.payer_receiver.payer == "PARTY2"
        assert leg.payer_receiver.receiver == "PARTY1"

    def test_float_leg_nan_spread_rejected(self) -> None:
        """FloatLeg rejects NaN spread (Formalis Finding 7)."""
        from attestor.core.money import NonEmptyStr, PositiveDecimal

        with pytest.raises(TypeError, match="FloatLeg.spread must be finite"):
            FloatLeg(
                payer_receiver=_PR_INV,
                float_index=NonEmptyStr(value="SOFR"),
                spread=Decimal("NaN"),
                day_count=DayCountConvention.ACT_360,
                payment_frequency=PaymentFrequency.QUARTERLY,
                currency=NonEmptyStr(value="USD"),
                notional=PositiveDecimal(value=Decimal("1000000")),
            )


# ===========================================================================
# IRSwapPayoutSpec consistency invariant
# ===========================================================================


class TestIRSwapConsistencyInvariant:
    def test_create_sets_inverse_direction(self) -> None:
        """create() auto-generates inverse PayerReceiver for float leg."""
        result = IRSwapPayoutSpec.create(
            fixed_rate=Decimal("0.03"),
            float_index="SOFR",
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            notional=Decimal("1000000"),
            currency="USD",
            start_date=date(2024, 1, 15),
            end_date=date(2029, 1, 15),
            payer_receiver=_PR,
        )
        assert isinstance(result, Ok)
        irs = result.value
        # Fixed payer = PARTY1, Float payer = PARTY2 (inverse)
        assert irs.fixed_leg.payer_receiver.payer == "PARTY1"
        assert irs.float_leg.payer_receiver.payer == "PARTY2"
        # Consistency: fixed_payer == float_receiver
        assert irs.fixed_leg.payer_receiver.payer == irs.float_leg.payer_receiver.receiver

    def test_inconsistent_direction_rejected(self) -> None:
        """Direct construction with non-inverse PayerReceivers is rejected."""
        from attestor.core.money import NonEmptyStr, PositiveDecimal

        same_pr = _PR
        fixed = FixedLeg(
            payer_receiver=same_pr,
            fixed_rate=Decimal("0.03"),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency=NonEmptyStr(value="USD"),
            notional=PositiveDecimal(value=Decimal("1000000")),
        )
        # Both legs have same direction → violates invariant
        floating = FloatLeg(
            payer_receiver=same_pr,
            float_index=NonEmptyStr(value="SOFR"),
            spread=Decimal("0"),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency=NonEmptyStr(value="USD"),
            notional=PositiveDecimal(value=Decimal("1000000")),
        )
        with pytest.raises(TypeError, match="fixed_leg payer must equal float_leg receiver"):
            IRSwapPayoutSpec(
                fixed_leg=fixed, float_leg=floating,
                start_date=date(2024, 1, 15), end_date=date(2029, 1, 15),
                currency=NonEmptyStr(value="USD"),
            )


# ===========================================================================
# PayerReceiver on CDS/Swaption
# ===========================================================================


class TestPayerReceiverOnCredit:
    def test_cds_create_with_payer_receiver(self) -> None:
        from attestor.instrument.credit_types import CDSPayoutSpec

        result = CDSPayoutSpec.create(
            reference_entity="ACME Corp",
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            currency="USD",
            effective_date=date(2024, 3, 20),
            maturity_date=date(2029, 3, 20),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("0.40"),
            payer_receiver=_PR,
        )
        assert isinstance(result, Ok)
        assert result.value.payer_receiver.payer == "PARTY1"

    def test_swaption_create_with_payer_receiver(self) -> None:
        from attestor.instrument.credit_types import SwaptionPayoutSpec
        from attestor.instrument.derivative_types import SettlementType

        underlying = IRSwapPayoutSpec.create(
            fixed_rate=Decimal("0.03"),
            float_index="SOFR",
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            notional=Decimal("1000000"),
            currency="USD",
            start_date=date(2024, 1, 15),
            end_date=date(2029, 1, 15),
            payer_receiver=_PR,
        )
        assert isinstance(underlying, Ok)

        result = SwaptionPayoutSpec.create(
            swaption_type="PAYER",
            strike=Decimal("0.03"),
            exercise_date=date(2024, 1, 10),
            underlying_swap=underlying.value,
            settlement_type=SettlementType.PHYSICAL,
            currency="USD",
            notional=Decimal("1000000"),
            payer_receiver=_PR,
        )
        assert isinstance(result, Ok)
        assert result.value.payer_receiver.payer == "PARTY1"
