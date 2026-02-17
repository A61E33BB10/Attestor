"""Phase C: Product Enrichment — comprehensive tests.

Covers all new and enriched types:
- CompoundingMethodEnum, StubPeriod
- FixedRateSpecification, FloatingRateSpecification, RateSpecification
- CashSettlementTerms, PhysicalSettlementTerms, SettlementTerms
- AmericanExercise, EuropeanExercise, BermudaExercise, ExerciseTerms
- PerformancePayoutSpec
- GeneralTerms, ProtectionTerms
- Enriched FixedLeg (+ schedule fields), FloatLeg (+ schedule/reset fields)
- Enriched CDSPayoutSpec (+ general/protection terms)
- Enriched OptionPayoutSpec (+ exercise_terms)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from attestor.core.money import NonEmptyStr, PositiveDecimal
from attestor.core.result import Ok
from attestor.core.types import (
    AdjustableDate,
    BusinessDayAdjustments,
    CalculationPeriodDates,
    DayCountConvention,
    Frequency,
    PayerReceiver,
    PaymentDates,
    Period,
    RelativeDateOffset,
    RollConventionEnum,
)
from attestor.instrument.credit_types import (
    CDSPayoutSpec,
    GeneralTerms,
    ProtectionTerms,
)
from attestor.instrument.derivative_types import (
    AmericanExercise,
    BermudaExercise,
    CashSettlementTerms,
    CreditEventType,
    EuropeanExercise,
    OptionPayoutSpec,
    OptionStyle,
    OptionType,
    PerformancePayoutSpec,
    PhysicalSettlementTerms,
    SeniorityLevel,
    SettlementType,
)
from attestor.instrument.fx_types import (
    FixedLeg,
    FloatLeg,
    IRSwapPayoutSpec,
    PaymentFrequency,
)
from attestor.instrument.rate_spec import (
    CompoundingMethodEnum,
    FixedRateSpecification,
    FloatingRateSpecification,
    StubPeriod,
)
from attestor.oracle.observable import (
    FloatingRateIndex,
    FloatingRateIndexEnum,
    ResetDates,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SOFR = FloatingRateIndex(
    index=FloatingRateIndexEnum.SOFR,
    designated_maturity=Period(1, "D"),
)
_PR = PayerReceiver(payer="PARTY1", receiver="PARTY2")
_PR_INV = PayerReceiver(payer="PARTY2", receiver="PARTY1")
_USD_r = NonEmptyStr.parse("USD")
assert isinstance(_USD_r, Ok)
_USD: NonEmptyStr = _USD_r.value

_ACME_r = NonEmptyStr.parse("ACME Corp")
assert isinstance(_ACME_r, Ok)
_ACME: NonEmptyStr = _ACME_r.value

_BBG_r = NonEmptyStr.parse("Bloomberg")
assert isinstance(_BBG_r, Ok)
_BBG: NonEmptyStr = _BBG_r.value

_BM_r = NonEmptyStr.parse("BorrowedMoney")
assert isinstance(_BM_r, Ok)
_BM: NonEmptyStr = _BM_r.value


def _pos(s: str) -> PositiveDecimal:
    r = PositiveDecimal.parse(Decimal(s))
    assert isinstance(r, Ok)
    return r.value


# ---------------------------------------------------------------------------
# CompoundingMethodEnum
# ---------------------------------------------------------------------------


class TestCompoundingMethodEnum:
    def test_count(self) -> None:
        assert len(CompoundingMethodEnum) == 4

    def test_members(self) -> None:
        expected = {"FLAT", "STRAIGHT", "SPREAD_EXCLUSIVE", "NONE"}
        actual = {e.name for e in CompoundingMethodEnum}
        assert actual == expected


# ---------------------------------------------------------------------------
# StubPeriod
# ---------------------------------------------------------------------------


class TestStubPeriod:
    def test_no_stubs(self) -> None:
        sp = StubPeriod()
        assert sp.initial_stub_rate is None
        assert sp.final_stub_rate is None

    def test_initial_stub_only(self) -> None:
        sp = StubPeriod(initial_stub_rate=Decimal("0.025"))
        assert sp.initial_stub_rate == Decimal("0.025")
        assert sp.final_stub_rate is None

    def test_both_stubs(self) -> None:
        sp = StubPeriod(
            initial_stub_rate=Decimal("0.025"),
            final_stub_rate=Decimal("0.03"),
        )
        assert sp.initial_stub_rate == Decimal("0.025")
        assert sp.final_stub_rate == Decimal("0.03")

    def test_frozen(self) -> None:
        sp = StubPeriod()
        with pytest.raises(AttributeError):
            sp.initial_stub_rate = Decimal("0.01")  # type: ignore[misc]

    def test_nan_initial_rejected(self) -> None:
        with pytest.raises(TypeError, match="initial_stub_rate must be finite"):
            StubPeriod(initial_stub_rate=Decimal("NaN"))

    def test_inf_final_rejected(self) -> None:
        with pytest.raises(TypeError, match="final_stub_rate must be finite"):
            StubPeriod(final_stub_rate=Decimal("Infinity"))


# ---------------------------------------------------------------------------
# FixedRateSpecification
# ---------------------------------------------------------------------------


class TestFixedRateSpecification:
    def test_valid(self) -> None:
        frs = FixedRateSpecification(
            rate=Decimal("0.03"), day_count=DayCountConvention.ACT_360,
        )
        assert frs.rate == Decimal("0.03")
        assert frs.step_schedule == ()

    def test_with_step_schedule(self) -> None:
        from attestor.core.types import DatedValue

        steps = (
            DatedValue(date=date(2026, 1, 15), value=Decimal("0.035")),
            DatedValue(date=date(2027, 1, 15), value=Decimal("0.04")),
        )
        frs = FixedRateSpecification(
            rate=Decimal("0.03"),
            day_count=DayCountConvention.THIRTY_360,
            step_schedule=steps,
        )
        assert len(frs.step_schedule) == 2

    def test_nan_rejected(self) -> None:
        with pytest.raises(TypeError, match="finite Decimal"):
            FixedRateSpecification(
                rate=Decimal("NaN"),
                day_count=DayCountConvention.ACT_360,
            )

    def test_negative_rate_allowed(self) -> None:
        frs = FixedRateSpecification(
            rate=Decimal("-0.005"),
            day_count=DayCountConvention.ACT_360,
        )
        assert frs.rate == Decimal("-0.005")

    def test_step_schedule_out_of_order_rejected(self) -> None:
        from attestor.core.types import DatedValue

        with pytest.raises(TypeError, match="strictly ascending"):
            FixedRateSpecification(
                rate=Decimal("0.03"),
                day_count=DayCountConvention.ACT_360,
                step_schedule=(
                    DatedValue(date=date(2027, 1, 15), value=Decimal("0.04")),
                    DatedValue(date=date(2026, 1, 15), value=Decimal("0.035")),
                ),
            )

    def test_step_schedule_duplicate_dates_rejected(self) -> None:
        from attestor.core.types import DatedValue

        with pytest.raises(TypeError, match="strictly ascending"):
            FixedRateSpecification(
                rate=Decimal("0.03"),
                day_count=DayCountConvention.ACT_360,
                step_schedule=(
                    DatedValue(date=date(2026, 1, 15), value=Decimal("0.035")),
                    DatedValue(date=date(2026, 1, 15), value=Decimal("0.04")),
                ),
            )


# ---------------------------------------------------------------------------
# FloatingRateSpecification
# ---------------------------------------------------------------------------


class TestFloatingRateSpecification:
    def test_valid_minimal(self) -> None:
        frs = FloatingRateSpecification(
            float_rate_index=_SOFR,
            spread=Decimal("0.005"),
            day_count=DayCountConvention.ACT_360,
        )
        assert frs.spread == Decimal("0.005")
        assert frs.cap is None
        assert frs.floor is None
        assert frs.multiplier == Decimal("1")

    def test_with_cap_and_floor(self) -> None:
        frs = FloatingRateSpecification(
            float_rate_index=_SOFR,
            spread=Decimal("0"),
            day_count=DayCountConvention.ACT_360,
            cap=Decimal("0.05"),
            floor=Decimal("0.01"),
        )
        assert frs.cap == Decimal("0.05")
        assert frs.floor == Decimal("0.01")

    def test_cap_less_than_floor_rejected(self) -> None:
        with pytest.raises(TypeError, match="cap.*must be >= floor"):
            FloatingRateSpecification(
                float_rate_index=_SOFR,
                spread=Decimal("0"),
                day_count=DayCountConvention.ACT_360,
                cap=Decimal("0.01"),
                floor=Decimal("0.05"),
            )

    def test_nan_spread_rejected(self) -> None:
        with pytest.raises(TypeError, match="spread must be finite"):
            FloatingRateSpecification(
                float_rate_index=_SOFR,
                spread=Decimal("NaN"),
                day_count=DayCountConvention.ACT_360,
            )

    def test_inf_cap_rejected(self) -> None:
        with pytest.raises(TypeError, match="cap must be finite"):
            FloatingRateSpecification(
                float_rate_index=_SOFR,
                spread=Decimal("0"),
                day_count=DayCountConvention.ACT_360,
                cap=Decimal("Infinity"),
            )

    def test_negative_treatment_default(self) -> None:
        frs = FloatingRateSpecification(
            float_rate_index=_SOFR,
            spread=Decimal("0"),
            day_count=DayCountConvention.ACT_360,
        )
        assert frs.negative_treatment == "NegativeInterestRateMethod"


# ---------------------------------------------------------------------------
# CashSettlementTerms
# ---------------------------------------------------------------------------


class TestCashSettlementTerms:
    def test_valid(self) -> None:
        mm = NonEmptyStr.parse("MidMarket")
        assert isinstance(mm, Ok)
        cst = CashSettlementTerms(
            settlement_method=mm.value,
            valuation_date=date(2025, 7, 1),
            currency=_USD,
        )
        assert cst.valuation_date == date(2025, 7, 1)

    def test_frozen(self) -> None:
        mm = NonEmptyStr.parse("MidMarket")
        assert isinstance(mm, Ok)
        cst = CashSettlementTerms(
            settlement_method=mm.value,
            valuation_date=date(2025, 7, 1),
            currency=_USD,
        )
        with pytest.raises(AttributeError):
            cst.currency = _BBG  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PhysicalSettlementTerms
# ---------------------------------------------------------------------------


class TestPhysicalSettlementTerms:
    def test_valid(self) -> None:
        pst = PhysicalSettlementTerms(
            delivery_period_days=30, settlement_currency=_USD,
        )
        assert pst.delivery_period_days == 30

    def test_zero_rejected(self) -> None:
        with pytest.raises(TypeError, match="delivery_period_days must be > 0"):
            PhysicalSettlementTerms(
                delivery_period_days=0, settlement_currency=_USD,
            )

    def test_negative_rejected(self) -> None:
        with pytest.raises(TypeError, match="delivery_period_days must be > 0"):
            PhysicalSettlementTerms(
                delivery_period_days=-1, settlement_currency=_USD,
            )

    def test_bool_rejected(self) -> None:
        with pytest.raises(TypeError, match="delivery_period_days must be int"):
            PhysicalSettlementTerms(
                delivery_period_days=True,
                settlement_currency=_USD,
            )


# ---------------------------------------------------------------------------
# AmericanExercise
# ---------------------------------------------------------------------------


class TestAmericanExercise:
    def test_valid(self) -> None:
        ae = AmericanExercise(
            earliest_exercise_date=date(2025, 1, 1),
            latest_exercise_date=date(2025, 12, 31),
        )
        assert ae.earliest_exercise_date == date(2025, 1, 1)

    def test_same_date_allowed(self) -> None:
        ae = AmericanExercise(
            earliest_exercise_date=date(2025, 6, 15),
            latest_exercise_date=date(2025, 6, 15),
        )
        assert ae.earliest_exercise_date == ae.latest_exercise_date

    def test_earliest_after_latest_rejected(self) -> None:
        with pytest.raises(TypeError, match="earliest_exercise_date"):
            AmericanExercise(
                earliest_exercise_date=date(2025, 12, 31),
                latest_exercise_date=date(2025, 1, 1),
            )


# ---------------------------------------------------------------------------
# EuropeanExercise
# ---------------------------------------------------------------------------


class TestEuropeanExercise:
    def test_valid(self) -> None:
        ee = EuropeanExercise(expiration_date=date(2025, 6, 15))
        assert ee.expiration_date == date(2025, 6, 15)

    def test_frozen(self) -> None:
        ee = EuropeanExercise(expiration_date=date(2025, 6, 15))
        with pytest.raises(AttributeError):
            ee.expiration_date = date(2025, 7, 1)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# BermudaExercise
# ---------------------------------------------------------------------------


class TestBermudaExercise:
    def test_valid(self) -> None:
        be = BermudaExercise(
            exercise_dates=(date(2025, 3, 15), date(2025, 6, 15)),
        )
        assert len(be.exercise_dates) == 2

    def test_empty_rejected(self) -> None:
        with pytest.raises(TypeError, match="must be non-empty"):
            BermudaExercise(exercise_dates=())

    def test_non_ascending_rejected(self) -> None:
        with pytest.raises(TypeError, match="strictly ascending"):
            BermudaExercise(
                exercise_dates=(date(2025, 6, 15), date(2025, 3, 15)),
            )

    def test_duplicate_dates_rejected(self) -> None:
        with pytest.raises(TypeError, match="strictly ascending"):
            BermudaExercise(
                exercise_dates=(date(2025, 6, 15), date(2025, 6, 15)),
            )


# ---------------------------------------------------------------------------
# PerformancePayoutSpec
# ---------------------------------------------------------------------------


class TestPerformancePayoutSpec:
    def test_valid(self) -> None:
        uid = NonEmptyStr.parse("SPX")
        assert isinstance(uid, Ok)
        pps = PerformancePayoutSpec(
            underlier_id=uid.value,
            initial_observation_date=date(2025, 1, 1),
            final_observation_date=date(2025, 12, 31),
            currency=_USD,
            notional=_pos("1000000"),
        )
        assert pps.initial_observation_date == date(2025, 1, 1)

    def test_dates_equal_rejected(self) -> None:
        uid = NonEmptyStr.parse("SPX")
        assert isinstance(uid, Ok)
        with pytest.raises(TypeError, match="initial_observation_date"):
            PerformancePayoutSpec(
                underlier_id=uid.value,
                initial_observation_date=date(2025, 6, 15),
                final_observation_date=date(2025, 6, 15),
                currency=_USD,
                notional=_pos("1000000"),
            )


# ---------------------------------------------------------------------------
# GeneralTerms
# ---------------------------------------------------------------------------


class TestGeneralTerms:
    def test_valid_with_obligation(self) -> None:
        isin = NonEmptyStr.parse("US000000AA00")
        assert isinstance(isin, Ok)
        gt = GeneralTerms(
            reference_entity=_ACME,
            reference_obligation=isin.value,
            seniority=SeniorityLevel.SENIOR_UNSECURED,
        )
        assert gt.reference_entity == _ACME
        assert gt.seniority == SeniorityLevel.SENIOR_UNSECURED

    def test_valid_without_obligation(self) -> None:
        gt = GeneralTerms(
            reference_entity=_ACME,
            reference_obligation=None,
            seniority=SeniorityLevel.SUBORDINATED,
        )
        assert gt.reference_obligation is None

    def test_frozen(self) -> None:
        gt = GeneralTerms(
            reference_entity=_ACME,
            reference_obligation=None,
            seniority=SeniorityLevel.SENIOR_UNSECURED,
        )
        with pytest.raises(AttributeError):
            gt.seniority = SeniorityLevel.SUBORDINATED  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ProtectionTerms
# ---------------------------------------------------------------------------


class TestProtectionTerms:
    def test_valid(self) -> None:
        pt = ProtectionTerms(
            credit_events=frozenset({
                CreditEventType.BANKRUPTCY,
                CreditEventType.FAILURE_TO_PAY,
            }),
            obligations_category=_BM,
        )
        assert CreditEventType.BANKRUPTCY in pt.credit_events

    def test_empty_credit_events_rejected(self) -> None:
        with pytest.raises(TypeError, match="credit_events must be non-empty"):
            ProtectionTerms(
                credit_events=frozenset(),
                obligations_category=_BM,
            )


# ---------------------------------------------------------------------------
# Enriched FixedLeg
# ---------------------------------------------------------------------------


class TestFixedLegEnrichment:
    def test_backward_compatible(self) -> None:
        """Existing code without schedule fields still works."""
        fl = FixedLeg(
            payer_receiver=_PR,
            fixed_rate=Decimal("0.03"),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency=_USD,
            notional=_pos("10000000"),
        )
        assert fl.calculation_period_dates is None
        assert fl.payment_dates is None
        assert fl.stub is None

    def test_with_schedule_fields(self) -> None:
        bda = BusinessDayAdjustments(
            convention="MOD_FOLLOWING",
            business_centers=frozenset({"USNY"}),
        )
        cpd = CalculationPeriodDates(
            effective_date=AdjustableDate(
                unadjusted_date=date(2025, 1, 15),
                adjustments=bda,
            ),
            termination_date=AdjustableDate(
                unadjusted_date=date(2030, 1, 15),
                adjustments=bda,
            ),
            frequency=Frequency(
                period=Period(3, "M"),
                roll_convention=RollConventionEnum.DOM_15,
            ),
            business_day_adjustments=bda,
        )
        pd = PaymentDates(
            payment_frequency=Frequency(
                period=Period(3, "M"),
                roll_convention=RollConventionEnum.DOM_15,
            ),
            pay_relative_to="CalculationPeriodEndDate",
            payment_day_offset=2,
            business_day_adjustments=bda,
        )
        fl = FixedLeg(
            payer_receiver=_PR,
            fixed_rate=Decimal("0.03"),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency=_USD,
            notional=_pos("10000000"),
            calculation_period_dates=cpd,
            payment_dates=pd,
            stub=StubPeriod(initial_stub_rate=Decimal("0.025")),
        )
        assert fl.calculation_period_dates is not None
        assert fl.payment_dates is not None
        assert fl.stub is not None
        assert fl.stub.initial_stub_rate == Decimal("0.025")

    def test_no_reset_dates_field(self) -> None:
        """FixedLeg structurally cannot have reset_dates."""
        assert not hasattr(FixedLeg, "reset_dates") or "reset_dates" not in {
            f.name for f in FixedLeg.__dataclass_fields__.values()
        }


# ---------------------------------------------------------------------------
# Enriched FloatLeg
# ---------------------------------------------------------------------------


class TestFloatLegEnrichment:
    def test_backward_compatible(self) -> None:
        fl = FloatLeg(
            payer_receiver=_PR_INV,
            float_index=_SOFR,
            spread=Decimal("0"),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency=_USD,
            notional=_pos("10000000"),
        )
        assert fl.calculation_period_dates is None
        assert fl.payment_dates is None
        assert fl.reset_dates is None
        assert fl.floating_rate_calc_params is None
        assert fl.stub is None

    def test_has_reset_dates_field(self) -> None:
        """FloatLeg CAN have reset_dates (unlike FixedLeg)."""
        field_names = {
            f.name for f in FloatLeg.__dataclass_fields__.values()
        }
        assert "reset_dates" in field_names

    def test_with_reset_dates(self) -> None:
        bda = BusinessDayAdjustments(
            convention="MOD_FOLLOWING",
            business_centers=frozenset({"USNY"}),
        )
        rd = ResetDates(
            reset_frequency=Frequency(
                period=Period(3, "M"),
                roll_convention=RollConventionEnum.EOM,
            ),
            fixing_dates_offset=RelativeDateOffset(
                period=Period(2, "D"),
                day_type="Business",
                business_day_convention="PRECEDING",
                business_centers=frozenset({"USNY"}),
            ),
            reset_relative_to="CalculationPeriodStartDate",
            calculation_parameters=None,
            business_day_adjustments=bda,
        )
        fl = FloatLeg(
            payer_receiver=_PR_INV,
            float_index=_SOFR,
            spread=Decimal("0.005"),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency=_USD,
            notional=_pos("10000000"),
            reset_dates=rd,
        )
        assert fl.reset_dates is not None
        assert fl.reset_dates.reset_relative_to == "CalculationPeriodStartDate"


# ---------------------------------------------------------------------------
# Enriched CDSPayoutSpec
# ---------------------------------------------------------------------------


class TestCDSPayoutSpecEnrichment:
    def test_backward_compatible(self) -> None:
        result = CDSPayoutSpec.create(
            reference_entity="ACME Corp",
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            currency="USD",
            effective_date=date(2025, 1, 15),
            maturity_date=date(2030, 1, 15),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("0.4"),
            payer_receiver=_PR,
        )
        assert isinstance(result, Ok)
        assert result.value.general_terms is None
        assert result.value.protection_terms is None

    def test_with_enrichment(self) -> None:
        gt = GeneralTerms(
            reference_entity=_ACME,
            reference_obligation=None,
            seniority=SeniorityLevel.SENIOR_UNSECURED,
        )
        pt = ProtectionTerms(
            credit_events=frozenset({
                CreditEventType.BANKRUPTCY,
                CreditEventType.FAILURE_TO_PAY,
            }),
            obligations_category=_BM,
        )
        cds = CDSPayoutSpec(
            payer_receiver=_PR,
            reference_entity=_ACME,
            notional=_pos("10000000"),
            spread=Decimal("0.01"),
            currency=_USD,
            effective_date=date(2025, 1, 15),
            maturity_date=date(2030, 1, 15),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("0.4"),
            general_terms=gt,
            protection_terms=pt,
        )
        assert cds.general_terms is not None
        assert cds.protection_terms is not None
        assert CreditEventType.BANKRUPTCY in cds.protection_terms.credit_events


# ---------------------------------------------------------------------------
# Enriched OptionPayoutSpec
# ---------------------------------------------------------------------------


class TestOptionPayoutSpecEnrichment:
    def test_backward_compatible(self) -> None:
        result = OptionPayoutSpec.create(
            underlying_id="AAPL",
            strike=Decimal("150"),
            expiry_date=date(2025, 6, 20),
            option_type=OptionType.CALL,
            option_style=OptionStyle.EUROPEAN,
            settlement_type=SettlementType.CASH,
            currency="USD",
            exchange="CBOE",
        )
        assert isinstance(result, Ok)
        assert result.value.exercise_terms is None

    def test_with_european_exercise(self) -> None:
        result = OptionPayoutSpec.create(
            underlying_id="AAPL",
            strike=Decimal("150"),
            expiry_date=date(2025, 6, 20),
            option_type=OptionType.CALL,
            option_style=OptionStyle.EUROPEAN,
            settlement_type=SettlementType.CASH,
            currency="USD",
            exchange="CBOE",
        )
        assert isinstance(result, Ok)
        # Construct enriched version directly
        spec = result.value
        enriched = OptionPayoutSpec(
            underlying_id=spec.underlying_id,
            strike=spec.strike,
            expiry_date=spec.expiry_date,
            option_type=spec.option_type,
            option_style=spec.option_style,
            settlement_type=spec.settlement_type,
            currency=spec.currency,
            exchange=spec.exchange,
            multiplier=spec.multiplier,
            exercise_terms=EuropeanExercise(
                expiration_date=date(2025, 6, 20),
            ),
        )
        assert isinstance(enriched.exercise_terms, EuropeanExercise)

    def test_with_bermuda_exercise(self) -> None:
        result = OptionPayoutSpec.create(
            underlying_id="AAPL",
            strike=Decimal("150"),
            expiry_date=date(2025, 6, 20),
            option_type=OptionType.CALL,
            option_style=OptionStyle.AMERICAN,
            settlement_type=SettlementType.CASH,
            currency="USD",
            exchange="CBOE",
        )
        assert isinstance(result, Ok)
        spec = result.value
        enriched = OptionPayoutSpec(
            underlying_id=spec.underlying_id,
            strike=spec.strike,
            expiry_date=spec.expiry_date,
            option_type=spec.option_type,
            option_style=spec.option_style,
            settlement_type=spec.settlement_type,
            currency=spec.currency,
            exchange=spec.exchange,
            multiplier=spec.multiplier,
            exercise_terms=BermudaExercise(
                exercise_dates=(date(2025, 3, 15), date(2025, 6, 15)),
            ),
        )
        assert isinstance(enriched.exercise_terms, BermudaExercise)
        assert len(enriched.exercise_terms.exercise_dates) == 2


# ---------------------------------------------------------------------------
# Integration: IRS with enriched legs
# ---------------------------------------------------------------------------


class TestIRSIntegrationEnriched:
    def test_create_still_works(self) -> None:
        """IRSwapPayoutSpec.create() still works without schedule fields."""
        result = IRSwapPayoutSpec.create(
            fixed_rate=Decimal("0.03"),
            float_index=_SOFR,
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            notional=Decimal("10000000"),
            currency="USD",
            start_date=date(2025, 1, 15),
            end_date=date(2030, 1, 15),
            payer_receiver=_PR,
        )
        assert isinstance(result, Ok)
        spec = result.value
        assert spec.fixed_leg.calculation_period_dates is None
        assert spec.float_leg.reset_dates is None
