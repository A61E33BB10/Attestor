"""Tests for Phase 4 arbitrage gates: vol surface (AF-VS) and credit curve (AF-CR)."""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal

from attestor.core.result import unwrap
from attestor.oracle.arbitrage_gates import (
    ArbitrageCheckType,
    CheckSeverity,
    check_credit_curve_arbitrage_freedom,
    check_vol_surface_arbitrage_freedom,
)
from attestor.oracle.credit_curve import CreditCurve
from attestor.oracle.vol_surface import SVIParameters, VolSurface

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AS_OF = date(2025, 6, 15)


def _make_slice(
    expiry: Decimal,
    a: Decimal = Decimal("0.04"),
    b: Decimal = Decimal("0.4"),
    rho: Decimal = Decimal("-0.4"),
    m: Decimal = Decimal("0"),
    sigma: Decimal = Decimal("0.2"),
) -> SVIParameters:
    """Create a valid SVI slice via the smart constructor."""
    return unwrap(SVIParameters.create(
        a=a, b=b, rho=rho, m=m, sigma=sigma, expiry=expiry,
    ))


def _make_surface(
    slices: tuple[SVIParameters, ...],
) -> VolSurface:
    """Create a VolSurface from the given slices, inferring expiries."""
    expiries = tuple(sl.expiry for sl in slices)
    return unwrap(VolSurface.create(
        underlying="SPX",
        as_of=_AS_OF,
        expiries=expiries,
        slices=slices,
        model_config_ref="SVI-CFG-001",
    ))


def _valid_two_slice_surface() -> VolSurface:
    """Two slices with identical SVI params at T=0.25 and T=1.0.

    Since both slices have the same (a,b,rho,m,sigma), w(k) is
    identical for both.  Calendar spread and ATM monotonicity hold
    trivially (w2(k) = w1(k) for all k).
    """
    s1 = _make_slice(Decimal("0.25"))
    s2 = _make_slice(Decimal("1"))
    return _make_surface((s1, s2))


def _valid_credit_curve() -> CreditCurve:
    """A valid credit curve with 3 tenor points."""
    return unwrap(CreditCurve.create(
        reference_entity="ACME",
        as_of=_AS_OF,
        tenors=(Decimal("1"), Decimal("3"), Decimal("5")),
        survival_probs=(Decimal("0.98"), Decimal("0.94"), Decimal("0.90")),
        hazard_rates=(Decimal("0.0202"), Decimal("0.0209"), Decimal("0.0218")),
        recovery_rate=Decimal("0.4"),
        discount_curve_ref="USD-CURVE",
        model_config_ref="CDS-CFG-001",
    ))


# ---------------------------------------------------------------------------
# General enum / dataclass tests
# ---------------------------------------------------------------------------


class TestArbitrageCheckTypeEnum:
    def test_enum_has_five_values(self) -> None:
        """ArbitrageCheckType should now have 5 members."""
        assert len(ArbitrageCheckType) == 5

    def test_vol_surface_member(self) -> None:
        assert ArbitrageCheckType.VOL_SURFACE.value == "VOL_SURFACE"

    def test_credit_curve_member(self) -> None:
        assert ArbitrageCheckType.CREDIT_CURVE.value == "CREDIT_CURVE"


class TestArbitrageCheckResultFrozen:
    def test_result_is_frozen(self) -> None:
        results = unwrap(check_vol_surface_arbitrage_freedom(_valid_two_slice_surface()))
        with __import__("pytest").raises(dataclasses.FrozenInstanceError):
            results[0].passed = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Vol Surface: AF-VS-01 Calendar Spread Freedom
# ---------------------------------------------------------------------------


class TestCalendarSpreadFreedom:
    def test_identical_slices_pass(self) -> None:
        """Two slices with identical w(k) satisfy calendar spread trivially."""
        results = unwrap(check_vol_surface_arbitrage_freedom(_valid_two_slice_surface()))
        vs01 = [r for r in results if r.check_id == "AF-VS-01"]
        assert len(vs01) == 1
        assert vs01[0].passed is True

    def test_increasing_variance_passes(self) -> None:
        """Later slice with higher 'a' has w2(k) > w1(k) everywhere."""
        s1 = _make_slice(Decimal("0.25"), a=Decimal("0.04"))
        s2 = _make_slice(Decimal("1"), a=Decimal("0.08"))
        surface = _make_surface((s1, s2))
        results = unwrap(check_vol_surface_arbitrage_freedom(surface))
        vs01 = [r for r in results if r.check_id == "AF-VS-01"][0]
        assert vs01.passed is True

    def test_calendar_spread_violation(self) -> None:
        """Later slice with much lower 'a' violates calendar spread."""
        # Slice 1 at T=0.25: a=0.10 gives w(0) = 0.10 + 0.4*0.2 = 0.18
        # Slice 2 at T=1.0:  a=0.01 gives w(0) = 0.01 + 0.4*0.2 = 0.09
        # w2(0) = 0.09 < w1(0) = 0.18 => violation
        s1 = _make_slice(Decimal("0.25"), a=Decimal("0.10"))
        s2 = _make_slice(Decimal("1"), a=Decimal("0.01"))
        surface = _make_surface((s1, s2))
        results = unwrap(check_vol_surface_arbitrage_freedom(surface))
        vs01 = [r for r in results if r.check_id == "AF-VS-01"][0]
        assert vs01.passed is False


# ---------------------------------------------------------------------------
# Vol Surface: AF-VS-02 Durrleman Butterfly Condition
# ---------------------------------------------------------------------------


class TestDurrlemanButterfly:
    def test_well_behaved_svi_passes(self) -> None:
        """Moderate parameters (b=0.4, rho=-0.4, sigma=0.2) pass Durrleman."""
        surface = _make_surface((_make_slice(Decimal("1")),))
        results = unwrap(check_vol_surface_arbitrage_freedom(surface))
        vs02 = [r for r in results if r.check_id == "AF-VS-02"][0]
        assert vs02.passed is True

    def test_low_rho_low_b_passes(self) -> None:
        """Nearly symmetric smile with small b easily passes butterfly."""
        sl = _make_slice(
            Decimal("1"), a=Decimal("0.04"), b=Decimal("0.1"),
            rho=Decimal("0"), m=Decimal("0"), sigma=Decimal("0.3"),
        )
        surface = _make_surface((sl,))
        results = unwrap(check_vol_surface_arbitrage_freedom(surface))
        vs02 = [r for r in results if r.check_id == "AF-VS-02"][0]
        assert vs02.passed is True

    def test_two_slice_passes(self) -> None:
        """Both slices of a well-behaved surface pass butterfly."""
        surface = _valid_two_slice_surface()
        results = unwrap(check_vol_surface_arbitrage_freedom(surface))
        vs02 = [r for r in results if r.check_id == "AF-VS-02"][0]
        assert vs02.passed is True


# ---------------------------------------------------------------------------
# Vol Surface: AF-VS-03 / AF-VS-04 Roger Lee Wing Bounds
# ---------------------------------------------------------------------------


class TestRogerLeeWings:
    def test_right_wing_passes_for_valid(self) -> None:
        """b*(1+rho) = 0.4*(1+(-0.4)) = 0.4*0.6 = 0.24 <= 2."""
        surface = _make_surface((_make_slice(Decimal("1")),))
        results = unwrap(check_vol_surface_arbitrage_freedom(surface))
        vs03 = [r for r in results if r.check_id == "AF-VS-03"][0]
        assert vs03.passed is True

    def test_left_wing_passes_for_valid(self) -> None:
        """b*(1-rho) = 0.4*(1-(-0.4)) = 0.4*1.4 = 0.56 <= 2."""
        surface = _make_surface((_make_slice(Decimal("1")),))
        results = unwrap(check_vol_surface_arbitrage_freedom(surface))
        vs04 = [r for r in results if r.check_id == "AF-VS-04"][0]
        assert vs04.passed is True

    def test_boundary_b_rho_passes(self) -> None:
        """b=1.0, rho=0.0 => b*(1+|rho|) = 1.0 <= 2 for both wings."""
        sl = _make_slice(
            Decimal("1"), a=Decimal("0.04"), b=Decimal("1"),
            rho=Decimal("0"), sigma=Decimal("0.2"),
        )
        surface = _make_surface((sl,))
        results = unwrap(check_vol_surface_arbitrage_freedom(surface))
        vs03 = [r for r in results if r.check_id == "AF-VS-03"][0]
        vs04 = [r for r in results if r.check_id == "AF-VS-04"][0]
        assert vs03.passed is True
        assert vs04.passed is True

    def test_roger_lee_at_exact_bound(self) -> None:
        """b*(1+|rho|) = exactly 2 is allowed (<=)."""
        # b=1, rho=0.5: b*(1+rho)=1.5, b*(1-rho)=0.5, b*(1+|rho|)=1.5 <= 2
        # b=2, rho=0: b*(1+|rho|)=2 exactly
        sl = _make_slice(
            Decimal("1"), a=Decimal("0.04"), b=Decimal("2"),
            rho=Decimal("0"), sigma=Decimal("0.2"),
        )
        surface = _make_surface((sl,))
        results = unwrap(check_vol_surface_arbitrage_freedom(surface))
        vs03 = [r for r in results if r.check_id == "AF-VS-03"][0]
        vs04 = [r for r in results if r.check_id == "AF-VS-04"][0]
        assert vs03.passed is True
        assert vs04.passed is True


# ---------------------------------------------------------------------------
# Vol Surface: AF-VS-05 Positive Implied Variance
# ---------------------------------------------------------------------------


class TestPositiveVariance:
    def test_valid_surface_passes(self) -> None:
        """Well-parameterized SVI has w(k) >= 0 for all grid points."""
        surface = _make_surface((_make_slice(Decimal("1")),))
        results = unwrap(check_vol_surface_arbitrage_freedom(surface))
        vs05 = [r for r in results if r.check_id == "AF-VS-05"][0]
        assert vs05.passed is True

    def test_two_slice_surface_passes(self) -> None:
        surface = _valid_two_slice_surface()
        results = unwrap(check_vol_surface_arbitrage_freedom(surface))
        vs05 = [r for r in results if r.check_id == "AF-VS-05"][0]
        assert vs05.passed is True


# ---------------------------------------------------------------------------
# Vol Surface: AF-VS-06 ATM Variance Monotonicity
# ---------------------------------------------------------------------------


class TestATMVarianceMonotonicity:
    def test_identical_slices_pass(self) -> None:
        """Equal ATM variance is non-decreasing (trivially)."""
        surface = _valid_two_slice_surface()
        results = unwrap(check_vol_surface_arbitrage_freedom(surface))
        vs06 = [r for r in results if r.check_id == "AF-VS-06"][0]
        assert vs06.passed is True

    def test_increasing_atm_passes(self) -> None:
        """Higher 'a' in later slice means larger w(0, T2)."""
        s1 = _make_slice(Decimal("0.25"), a=Decimal("0.04"))
        s2 = _make_slice(Decimal("1"), a=Decimal("0.08"))
        surface = _make_surface((s1, s2))
        results = unwrap(check_vol_surface_arbitrage_freedom(surface))
        vs06 = [r for r in results if r.check_id == "AF-VS-06"][0]
        assert vs06.passed is True

    def test_atm_non_monotone_fails(self) -> None:
        """Decreasing ATM variance violates AF-VS-06."""
        s1 = _make_slice(Decimal("0.25"), a=Decimal("0.10"))
        s2 = _make_slice(Decimal("1"), a=Decimal("0.01"))
        surface = _make_surface((s1, s2))
        results = unwrap(check_vol_surface_arbitrage_freedom(surface))
        vs06 = [r for r in results if r.check_id == "AF-VS-06"][0]
        assert vs06.passed is False


# ---------------------------------------------------------------------------
# Vol Surface: Integration / naming / type tests
# ---------------------------------------------------------------------------


class TestVolSurfaceIntegration:
    def test_valid_surface_passes_all(self) -> None:
        """A well-behaved 2-slice surface passes all 6 gates."""
        surface = _valid_two_slice_surface()
        results = unwrap(check_vol_surface_arbitrage_freedom(surface))
        assert len(results) == 6
        for r in results:
            assert r.passed is True, f"{r.check_id} failed unexpectedly"

    def test_all_check_types_are_vol_surface(self) -> None:
        results = unwrap(check_vol_surface_arbitrage_freedom(_valid_two_slice_surface()))
        for r in results:
            assert r.check_type == ArbitrageCheckType.VOL_SURFACE

    def test_check_ids_follow_af_vs_naming(self) -> None:
        results = unwrap(check_vol_surface_arbitrage_freedom(_valid_two_slice_surface()))
        ids = [r.check_id for r in results]
        assert ids == [
            "AF-VS-01", "AF-VS-02", "AF-VS-03",
            "AF-VS-04", "AF-VS-05", "AF-VS-06",
        ]

    def test_severities(self) -> None:
        results = unwrap(check_vol_surface_arbitrage_freedom(_valid_two_slice_surface()))
        assert results[0].severity == CheckSeverity.CRITICAL  # AF-VS-01
        assert results[1].severity == CheckSeverity.CRITICAL  # AF-VS-02
        assert results[2].severity == CheckSeverity.HIGH      # AF-VS-03
        assert results[3].severity == CheckSeverity.HIGH      # AF-VS-04
        assert results[4].severity == CheckSeverity.CRITICAL  # AF-VS-05
        assert results[5].severity == CheckSeverity.HIGH      # AF-VS-06

    def test_single_slice_surface_passes_all(self) -> None:
        """Single-slice surface has no adjacent pairs; calendar/ATM checks pass trivially."""
        surface = _make_surface((_make_slice(Decimal("1")),))
        results = unwrap(check_vol_surface_arbitrage_freedom(surface))
        assert len(results) == 6
        for r in results:
            assert r.passed is True, f"{r.check_id} failed unexpectedly"

    def test_details_present(self) -> None:
        results = unwrap(check_vol_surface_arbitrage_freedom(_valid_two_slice_surface()))
        for r in results:
            assert len(r.details) > 0


# ---------------------------------------------------------------------------
# Credit Curve: AF-CR-01 Survival Probability Bounds
# ---------------------------------------------------------------------------


class TestCreditCurveSurvivalBounds:
    def test_valid_curve_passes(self) -> None:
        """All survival probs in (0, 1] => AF-CR-01 passes."""
        curve = _valid_credit_curve()
        results = unwrap(check_credit_curve_arbitrage_freedom(curve))
        cr01 = [r for r in results if r.check_id == "AF-CR-01"][0]
        assert cr01.passed is True

    def test_survival_at_one_passes(self) -> None:
        """Q(t) = 1.0 exactly is valid (boundary of (0, 1])."""
        curve = unwrap(CreditCurve.create(
            reference_entity="SAFE_CO",
            as_of=_AS_OF,
            tenors=(Decimal("1"),),
            survival_probs=(Decimal("1"),),
            hazard_rates=(Decimal("0"),),
            recovery_rate=Decimal("0.4"),
            discount_curve_ref="USD",
            model_config_ref="CFG",
        ))
        results = unwrap(check_credit_curve_arbitrage_freedom(curve))
        cr01 = [r for r in results if r.check_id == "AF-CR-01"][0]
        assert cr01.passed is True


# ---------------------------------------------------------------------------
# Credit Curve: AF-CR-02 Q(0)=1 Convention
# ---------------------------------------------------------------------------


class TestCreditCurveQ0:
    def test_q0_always_passes(self) -> None:
        """Q(0)=1 is enforced by construction; gate always passes."""
        curve = _valid_credit_curve()
        results = unwrap(check_credit_curve_arbitrage_freedom(curve))
        cr02 = [r for r in results if r.check_id == "AF-CR-02"][0]
        assert cr02.passed is True


# ---------------------------------------------------------------------------
# Credit Curve: AF-CR-03 Monotone Non-Increasing
# ---------------------------------------------------------------------------


class TestCreditCurveMonotone:
    def test_valid_curve_passes(self) -> None:
        """Decreasing survival probs pass monotonicity."""
        curve = _valid_credit_curve()
        results = unwrap(check_credit_curve_arbitrage_freedom(curve))
        cr03 = [r for r in results if r.check_id == "AF-CR-03"][0]
        assert cr03.passed is True

    def test_single_point_passes(self) -> None:
        """A single-point curve trivially passes monotonicity."""
        curve = unwrap(CreditCurve.create(
            reference_entity="SOLO",
            as_of=_AS_OF,
            tenors=(Decimal("5"),),
            survival_probs=(Decimal("0.85"),),
            hazard_rates=(Decimal("0.0325"),),
            recovery_rate=Decimal("0.4"),
            discount_curve_ref="USD",
            model_config_ref="CFG",
        ))
        results = unwrap(check_credit_curve_arbitrage_freedom(curve))
        cr03 = [r for r in results if r.check_id == "AF-CR-03"][0]
        assert cr03.passed is True


# ---------------------------------------------------------------------------
# Credit Curve: AF-CR-04 Non-Negative Hazard Rates
# ---------------------------------------------------------------------------


class TestCreditCurveHazard:
    def test_valid_curve_passes(self) -> None:
        curve = _valid_credit_curve()
        results = unwrap(check_credit_curve_arbitrage_freedom(curve))
        cr04 = [r for r in results if r.check_id == "AF-CR-04"][0]
        assert cr04.passed is True

    def test_zero_hazard_passes(self) -> None:
        """Zero hazard rate (risk-free entity) is valid."""
        curve = unwrap(CreditCurve.create(
            reference_entity="TREASURY",
            as_of=_AS_OF,
            tenors=(Decimal("1"),),
            survival_probs=(Decimal("1"),),
            hazard_rates=(Decimal("0"),),
            recovery_rate=Decimal("0.4"),
            discount_curve_ref="USD",
            model_config_ref="CFG",
        ))
        results = unwrap(check_credit_curve_arbitrage_freedom(curve))
        cr04 = [r for r in results if r.check_id == "AF-CR-04"][0]
        assert cr04.passed is True


# ---------------------------------------------------------------------------
# Credit Curve: Integration / naming / type tests
# ---------------------------------------------------------------------------


class TestCreditCurveIntegration:
    def test_all_four_checks_returned(self) -> None:
        results = unwrap(check_credit_curve_arbitrage_freedom(_valid_credit_curve()))
        assert len(results) == 4

    def test_all_check_types_are_credit_curve(self) -> None:
        results = unwrap(check_credit_curve_arbitrage_freedom(_valid_credit_curve()))
        for r in results:
            assert r.check_type == ArbitrageCheckType.CREDIT_CURVE

    def test_check_ids_follow_af_cr_naming(self) -> None:
        results = unwrap(check_credit_curve_arbitrage_freedom(_valid_credit_curve()))
        ids = [r.check_id for r in results]
        assert ids == ["AF-CR-01", "AF-CR-02", "AF-CR-03", "AF-CR-04"]

    def test_all_pass_for_valid_curve(self) -> None:
        results = unwrap(check_credit_curve_arbitrage_freedom(_valid_credit_curve()))
        for r in results:
            assert r.passed is True, f"{r.check_id} failed unexpectedly"

    def test_details_present(self) -> None:
        results = unwrap(check_credit_curve_arbitrage_freedom(_valid_credit_curve()))
        for r in results:
            assert len(r.details) > 0
