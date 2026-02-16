"""Tests for attestor.oracle.credit_curve — credit curve bootstrapping.

Covers CDSQuote, CreditCurve (with smart constructor), survival_probability,
hazard_rate, and bootstrap_credit_curve.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from attestor.core.decimal_math import exp_d, ln_d
from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, Ok, unwrap
from attestor.oracle.attestation import DerivedConfidence
from attestor.oracle.calibration import ModelConfig, YieldCurve
from attestor.oracle.credit_curve import (
    CDSQuote,
    CreditCurve,
    bootstrap_credit_curve,
    hazard_rate,
    survival_probability,
)

_TS = datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_config() -> ModelConfig:
    return unwrap(ModelConfig.create(
        config_id="CFG-CDS-001",
        model_class="CDS_BOOTSTRAP",
        code_version="1.0.0",
    ))


def _sample_discount_curve() -> YieldCurve:
    return unwrap(YieldCurve.create(
        currency="USD",
        as_of=date(2025, 6, 15),
        tenors=(Decimal("1"), Decimal("3"), Decimal("5")),
        discount_factors=(Decimal("0.96"), Decimal("0.90"), Decimal("0.85")),
        model_config_ref="CFG-YC-001",
    ))


def _sample_3pt_curve() -> CreditCurve:
    """Build a valid 3-tenor credit curve directly for use in tests."""
    # Q(1)=0.98, Q(3)=0.94, Q(5)=0.88  -- monotone, within (0,1]
    tenors = (Decimal("1"), Decimal("3"), Decimal("5"))
    sprobs = (Decimal("0.98"), Decimal("0.94"), Decimal("0.88"))
    # Derive hazard rates: lambda_j = -ln(Q_j/Q_{j-1}) / (T_j - T_{j-1})
    h1 = -ln_d(sprobs[0]) / tenors[0]
    h2 = -ln_d(sprobs[1] / sprobs[0]) / (tenors[1] - tenors[0])
    h3 = -ln_d(sprobs[2] / sprobs[1]) / (tenors[2] - tenors[1])
    hazards = (h1, h2, h3)
    return unwrap(CreditCurve.create(
        reference_entity="ACME Corp",
        as_of=date(2025, 6, 15),
        tenors=tenors,
        survival_probs=sprobs,
        hazard_rates=hazards,
        recovery_rate=Decimal("0.4"),
        discount_curve_ref="CFG-YC-001",
        model_config_ref="CFG-CDS-001",
    ))


def _sample_quotes() -> tuple[CDSQuote, ...]:
    """3-point CDS quote strip: 1Y, 3Y, 5Y."""
    return (
        CDSQuote(
            reference_entity=NonEmptyStr(value="ACME Corp"),
            tenor=Decimal("1"),
            spread=Decimal("0.01"),  # 100bps
            recovery_rate=Decimal("0.4"),
            currency=NonEmptyStr(value="USD"),
        ),
        CDSQuote(
            reference_entity=NonEmptyStr(value="ACME Corp"),
            tenor=Decimal("3"),
            spread=Decimal("0.012"),  # 120bps
            recovery_rate=Decimal("0.4"),
            currency=NonEmptyStr(value="USD"),
        ),
        CDSQuote(
            reference_entity=NonEmptyStr(value="ACME Corp"),
            tenor=Decimal("5"),
            spread=Decimal("0.015"),  # 150bps
            recovery_rate=Decimal("0.4"),
            currency=NonEmptyStr(value="USD"),
        ),
    )


# ---------------------------------------------------------------------------
# CreditCurve.create — valid construction
# ---------------------------------------------------------------------------


class TestCreditCurveCreateValid:
    def test_valid_3_tenors(self) -> None:
        curve = _sample_3pt_curve()
        assert len(curve.tenors) == 3
        assert curve.reference_entity.value == "ACME Corp"
        assert curve.recovery_rate == Decimal("0.4")

    def test_survival_probs_monotone_decreasing(self) -> None:
        curve = _sample_3pt_curve()
        for i in range(1, len(curve.survival_probs)):
            assert curve.survival_probs[i] <= curve.survival_probs[i - 1]

    def test_hazard_rates_non_negative(self) -> None:
        curve = _sample_3pt_curve()
        for h in curve.hazard_rates:
            assert h >= Decimal("0")

    def test_frozen(self) -> None:
        curve = _sample_3pt_curve()
        with pytest.raises(dataclasses.FrozenInstanceError):
            curve.recovery_rate = Decimal("0.5")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CreditCurve.create — rejection
# ---------------------------------------------------------------------------


class TestCreditCurveCreateReject:
    def test_reject_survival_gt_one(self) -> None:
        result = CreditCurve.create(
            reference_entity="ACME Corp",
            as_of=date(2025, 6, 15),
            tenors=(Decimal("1"),),
            survival_probs=(Decimal("1.01"),),
            hazard_rates=(Decimal("0.01"),),
            recovery_rate=Decimal("0.4"),
            discount_curve_ref="YC", model_config_ref="CFG",
        )
        assert isinstance(result, Err)
        assert "survival_probs" in result.error

    def test_reject_survival_zero(self) -> None:
        result = CreditCurve.create(
            reference_entity="ACME Corp",
            as_of=date(2025, 6, 15),
            tenors=(Decimal("1"),),
            survival_probs=(Decimal("0"),),
            hazard_rates=(Decimal("0.01"),),
            recovery_rate=Decimal("0.4"),
            discount_curve_ref="YC", model_config_ref="CFG",
        )
        assert isinstance(result, Err)
        assert "survival_probs" in result.error

    def test_reject_survival_negative(self) -> None:
        result = CreditCurve.create(
            reference_entity="ACME Corp",
            as_of=date(2025, 6, 15),
            tenors=(Decimal("1"),),
            survival_probs=(Decimal("-0.5"),),
            hazard_rates=(Decimal("0.01"),),
            recovery_rate=Decimal("0.4"),
            discount_curve_ref="YC", model_config_ref="CFG",
        )
        assert isinstance(result, Err)
        assert "survival_probs" in result.error

    def test_reject_non_monotone_survival(self) -> None:
        result = CreditCurve.create(
            reference_entity="ACME Corp",
            as_of=date(2025, 6, 15),
            tenors=(Decimal("1"), Decimal("3")),
            survival_probs=(Decimal("0.9"), Decimal("0.95")),  # increasing!
            hazard_rates=(Decimal("0.01"), Decimal("0.01")),
            recovery_rate=Decimal("0.4"),
            discount_curve_ref="YC", model_config_ref="CFG",
        )
        assert isinstance(result, Err)
        assert "monotone" in result.error

    def test_reject_unsorted_tenors(self) -> None:
        result = CreditCurve.create(
            reference_entity="ACME Corp",
            as_of=date(2025, 6, 15),
            tenors=(Decimal("3"), Decimal("1")),
            survival_probs=(Decimal("0.95"), Decimal("0.90")),
            hazard_rates=(Decimal("0.01"), Decimal("0.01")),
            recovery_rate=Decimal("0.4"),
            discount_curve_ref="YC", model_config_ref="CFG",
        )
        assert isinstance(result, Err)
        assert "ascending" in result.error

    def test_reject_mismatched_lengths(self) -> None:
        result = CreditCurve.create(
            reference_entity="ACME Corp",
            as_of=date(2025, 6, 15),
            tenors=(Decimal("1"), Decimal("3")),
            survival_probs=(Decimal("0.98"),),  # length mismatch
            hazard_rates=(Decimal("0.01"), Decimal("0.01")),
            recovery_rate=Decimal("0.4"),
            discount_curve_ref="YC", model_config_ref="CFG",
        )
        assert isinstance(result, Err)
        assert "same length" in result.error

    def test_reject_negative_hazard_rate(self) -> None:
        result = CreditCurve.create(
            reference_entity="ACME Corp",
            as_of=date(2025, 6, 15),
            tenors=(Decimal("1"),),
            survival_probs=(Decimal("0.98"),),
            hazard_rates=(Decimal("-0.01"),),
            recovery_rate=Decimal("0.4"),
            discount_curve_ref="YC", model_config_ref="CFG",
        )
        assert isinstance(result, Err)
        assert "hazard_rates" in result.error

    def test_reject_recovery_rate_gte_one(self) -> None:
        result = CreditCurve.create(
            reference_entity="ACME Corp",
            as_of=date(2025, 6, 15),
            tenors=(Decimal("1"),),
            survival_probs=(Decimal("0.98"),),
            hazard_rates=(Decimal("0.01"),),
            recovery_rate=Decimal("1"),
            discount_curve_ref="YC", model_config_ref="CFG",
        )
        assert isinstance(result, Err)
        assert "recovery_rate" in result.error

    def test_reject_recovery_rate_negative(self) -> None:
        result = CreditCurve.create(
            reference_entity="ACME Corp",
            as_of=date(2025, 6, 15),
            tenors=(Decimal("1"),),
            survival_probs=(Decimal("0.98"),),
            hazard_rates=(Decimal("0.01"),),
            recovery_rate=Decimal("-0.1"),
            discount_curve_ref="YC", model_config_ref="CFG",
        )
        assert isinstance(result, Err)
        assert "recovery_rate" in result.error

    def test_reject_empty_tenors(self) -> None:
        result = CreditCurve.create(
            reference_entity="ACME Corp",
            as_of=date(2025, 6, 15),
            tenors=(),
            survival_probs=(),
            hazard_rates=(),
            recovery_rate=Decimal("0.4"),
            discount_curve_ref="YC", model_config_ref="CFG",
        )
        assert isinstance(result, Err)
        assert "non-empty" in result.error


# ---------------------------------------------------------------------------
# survival_probability
# ---------------------------------------------------------------------------


class TestSurvivalProbability:
    def test_q_zero_is_one(self) -> None:
        """Q(0) = 1 by convention."""
        curve = _sample_3pt_curve()
        q = unwrap(survival_probability(curve, Decimal("0")))
        assert q == Decimal("1")

    def test_q_negative_tenor_is_one(self) -> None:
        """Q(t) = 1 for t <= 0."""
        curve = _sample_3pt_curve()
        q = unwrap(survival_probability(curve, Decimal("-1")))
        assert q == Decimal("1")

    def test_exact_at_tenor_points(self) -> None:
        """Interpolation at exact tenor points should recover stored values."""
        curve = _sample_3pt_curve()
        for i, tenor in enumerate(curve.tenors):
            q = unwrap(survival_probability(curve, tenor))
            # Should be very close to stored value (within Decimal precision)
            diff = abs(q - curve.survival_probs[i])
            assert diff < Decimal("1E-20"), (
                f"At tenor={tenor}: got Q={q}, expected {curve.survival_probs[i]}"
            )

    def test_between_tenors_exponential_interpolation(self) -> None:
        """Between tenor points, uses piecewise constant hazard."""
        curve = _sample_3pt_curve()
        # t = 2.0 is between T_1=1 and T_2=3
        q_at_2 = unwrap(survival_probability(curve, Decimal("2")))
        # Must be between Q(1) and Q(3)
        assert curve.survival_probs[1] < q_at_2 < curve.survival_probs[0]
        # Verify exponential form: Q(2) = Q(1) * exp(-lambda_2 * (2-1))
        expected = curve.survival_probs[0] * exp_d(
            -curve.hazard_rates[1] * Decimal("1")
        )
        diff = abs(q_at_2 - expected)
        assert diff < Decimal("1E-20")

    def test_beyond_last_tenor_flat_extrapolation(self) -> None:
        """Beyond last tenor uses flat hazard extrapolation."""
        curve = _sample_3pt_curve()
        # t = 7.0 is beyond T_3=5
        q_at_7 = unwrap(survival_probability(curve, Decimal("7")))
        # Must be less than Q(5)
        assert q_at_7 < curve.survival_probs[-1]
        # Verify: Q(7) = Q(5) * exp(-lambda_3 * (7 - 5))
        expected = curve.survival_probs[-1] * exp_d(
            -curve.hazard_rates[-1] * Decimal("2")
        )
        diff = abs(q_at_7 - expected)
        assert diff < Decimal("1E-20")

    def test_before_first_tenor(self) -> None:
        """Between 0 and first tenor uses first hazard rate."""
        curve = _sample_3pt_curve()
        # t = 0.5 is before T_1=1
        q_at_half = unwrap(survival_probability(curve, Decimal("0.5")))
        assert Decimal("0") < q_at_half <= Decimal("1")
        # Verify: Q(0.5) = exp(-lambda_1 * 0.5)
        expected = exp_d(-curve.hazard_rates[0] * Decimal("0.5"))
        diff = abs(q_at_half - expected)
        assert diff < Decimal("1E-20")


# ---------------------------------------------------------------------------
# hazard_rate
# ---------------------------------------------------------------------------


class TestHazardRate:
    def test_correct_computation(self) -> None:
        """hazard_rate(t1, t2) = -ln(Q(t2)/Q(t1)) / (t2-t1)."""
        curve = _sample_3pt_curve()
        lam = unwrap(hazard_rate(curve, Decimal("0"), Decimal("1")))
        assert lam >= Decimal("0")
        # For t1=0, Q(0)=1, so lambda = -ln(Q(1)) / 1
        expected = -ln_d(curve.survival_probs[0]) / Decimal("1")
        diff = abs(lam - expected)
        assert diff < Decimal("1E-20")

    def test_t2_le_t1_err(self) -> None:
        curve = _sample_3pt_curve()
        result = hazard_rate(curve, Decimal("2"), Decimal("1"))
        assert isinstance(result, Err)

    def test_t2_eq_t1_err(self) -> None:
        curve = _sample_3pt_curve()
        result = hazard_rate(curve, Decimal("1"), Decimal("1"))
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# CDSQuote
# ---------------------------------------------------------------------------


class TestCDSQuote:
    def test_construction(self) -> None:
        q = CDSQuote(
            reference_entity=NonEmptyStr(value="ACME Corp"),
            tenor=Decimal("5"),
            spread=Decimal("0.01"),
            recovery_rate=Decimal("0.4"),
            currency=NonEmptyStr(value="USD"),
        )
        assert q.tenor == Decimal("5")
        assert q.spread == Decimal("0.01")
        assert q.recovery_rate == Decimal("0.4")
        assert q.reference_entity.value == "ACME Corp"
        assert q.currency.value == "USD"

    def test_frozen(self) -> None:
        q = CDSQuote(
            reference_entity=NonEmptyStr(value="ACME Corp"),
            tenor=Decimal("5"),
            spread=Decimal("0.01"),
            recovery_rate=Decimal("0.4"),
            currency=NonEmptyStr(value="USD"),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            q.spread = Decimal("0.02")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# bootstrap_credit_curve
# ---------------------------------------------------------------------------


class TestBootstrapCreditCurve:
    def test_3pt_bootstrap(self) -> None:
        """Bootstrap from 3 CDS quotes produces valid CreditCurve."""
        result = bootstrap_credit_curve(
            quotes=_sample_quotes(),
            discount_curve=_sample_discount_curve(),
            config=_sample_config(),
            as_of=date(2025, 6, 15),
            reference_entity="ACME Corp",
        )
        assert isinstance(result, Ok)
        att = result.value
        curve = att.value
        assert len(curve.tenors) == 3
        assert curve.tenors == (Decimal("1"), Decimal("3"), Decimal("5"))
        # Survival probs must be monotone decreasing
        for i in range(1, len(curve.survival_probs)):
            assert curve.survival_probs[i] <= curve.survival_probs[i - 1]
        # All hazard rates non-negative
        for h in curve.hazard_rates:
            assert h >= Decimal("0")

    def test_bootstrap_survival_probs_formula(self) -> None:
        """Verify Q(t) = 1 / (1 + spread * t / (1 - R))."""
        quotes = _sample_quotes()
        result = bootstrap_credit_curve(
            quotes=quotes,
            discount_curve=_sample_discount_curve(),
            config=_sample_config(),
            as_of=date(2025, 6, 15),
            reference_entity="ACME Corp",
        )
        att = unwrap(result)
        curve = att.value
        for i, q in enumerate(quotes):
            lgd = Decimal("1") - q.recovery_rate
            expected_q = Decimal("1") / (
                Decimal("1") + q.spread * q.tenor / lgd
            )
            diff = abs(curve.survival_probs[i] - expected_q)
            assert diff < Decimal("1E-20"), (
                f"Q(T_{i})={curve.survival_probs[i]} != {expected_q}"
            )

    def test_derived_confidence_populated(self) -> None:
        """Attestation should have DerivedConfidence."""
        result = bootstrap_credit_curve(
            quotes=_sample_quotes(),
            discount_curve=_sample_discount_curve(),
            config=_sample_config(),
            as_of=date(2025, 6, 15),
            reference_entity="ACME Corp",
        )
        att = unwrap(result)
        assert isinstance(att.confidence, DerivedConfidence)
        assert att.confidence.method.value == "CDS_BOOTSTRAP"
        assert att.confidence.config_ref.value == "CFG-CDS-001"

    def test_provenance_chain(self) -> None:
        """Attestation should reference the config."""
        result = bootstrap_credit_curve(
            quotes=_sample_quotes(),
            discount_curve=_sample_discount_curve(),
            config=_sample_config(),
            as_of=date(2025, 6, 15),
            reference_entity="ACME Corp",
        )
        att = unwrap(result)
        # model_config_ref in curve should match config_id
        assert att.value.model_config_ref == "CFG-CDS-001"
        # discount_curve_ref in curve should match discount curve's config ref
        assert att.value.discount_curve_ref == "CFG-YC-001"
        # Source should be the model class
        assert att.source.value == "CDS_BOOTSTRAP"

    def test_empty_quotes_err(self) -> None:
        result = bootstrap_credit_curve(
            quotes=(),
            discount_curve=_sample_discount_curve(),
            config=_sample_config(),
            as_of=date(2025, 6, 15),
            reference_entity="ACME Corp",
        )
        assert isinstance(result, Err)
        assert "At least one" in result.error

    def test_single_quote_valid(self) -> None:
        """Single CDS quote should produce a valid 1-point curve."""
        single = (CDSQuote(
            reference_entity=NonEmptyStr(value="ACME Corp"),
            tenor=Decimal("5"),
            spread=Decimal("0.01"),
            recovery_rate=Decimal("0.4"),
            currency=NonEmptyStr(value="USD"),
        ),)
        result = bootstrap_credit_curve(
            quotes=single,
            discount_curve=_sample_discount_curve(),
            config=_sample_config(),
            as_of=date(2025, 6, 15),
            reference_entity="ACME Corp",
        )
        assert isinstance(result, Ok)
        curve = result.value.value
        assert len(curve.tenors) == 1
        assert len(curve.survival_probs) == 1
        assert len(curve.hazard_rates) == 1
        assert curve.hazard_rates[0] >= Decimal("0")

    def test_content_hash_populated(self) -> None:
        """Attestation should have non-empty content_hash."""
        result = bootstrap_credit_curve(
            quotes=_sample_quotes(),
            discount_curve=_sample_discount_curve(),
            config=_sample_config(),
            as_of=date(2025, 6, 15),
            reference_entity="ACME Corp",
        )
        att = unwrap(result)
        assert att.content_hash != ""
        assert att.attestation_id != ""


# ---------------------------------------------------------------------------
# No float in domain code
# ---------------------------------------------------------------------------


class TestDecimalOnly:
    def test_survival_prob_type_is_decimal(self) -> None:
        """All survival_probability outputs must be Decimal, not float."""
        curve = _sample_3pt_curve()
        q = unwrap(survival_probability(curve, Decimal("2")))
        assert isinstance(q, Decimal)

    def test_hazard_rate_type_is_decimal(self) -> None:
        """All hazard_rate outputs must be Decimal, not float."""
        curve = _sample_3pt_curve()
        lam = unwrap(hazard_rate(curve, Decimal("0"), Decimal("1")))
        assert isinstance(lam, Decimal)

    def test_bootstrapped_curve_all_decimal(self) -> None:
        """All fields in a bootstrapped curve must be Decimal."""
        result = bootstrap_credit_curve(
            quotes=_sample_quotes(),
            discount_curve=_sample_discount_curve(),
            config=_sample_config(),
            as_of=date(2025, 6, 15),
            reference_entity="ACME Corp",
        )
        curve = unwrap(result).value
        for t in curve.tenors:
            assert isinstance(t, Decimal)
        for q in curve.survival_probs:
            assert isinstance(q, Decimal)
        for h in curve.hazard_rates:
            assert isinstance(h, Decimal)
        assert isinstance(curve.recovery_rate, Decimal)
