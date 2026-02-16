"""Tests for attestor.oracle.vol_surface -- SVI parameterization and vol surface."""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from attestor.core.decimal_math import sqrt_d
from attestor.core.result import Err, Ok, unwrap
from attestor.oracle.attestation import Attestation, DerivedConfidence
from attestor.oracle.calibration import ModelConfig
from attestor.oracle.vol_surface import (
    SVIParameters,
    VolSurface,
    calibrate_vol_surface,
    implied_vol,
    svi_first_derivative,
    svi_second_derivative,
    svi_total_variance,
)

# ---------------------------------------------------------------------------
# Fixtures: well-known SVI parameters
# ---------------------------------------------------------------------------

# A "textbook" SVI parameter set:
#   a=0.04, b=0.4, rho=-0.4, m=0.0, sigma=0.2, expiry=1.0
#
# Constraint checks:
#   C-SVI-02: b=0.4 >= 0                        OK
#   C-SVI-03: |rho|=0.4 < 1                     OK
#   C-SVI-04: sigma=0.2 > 0                     OK
#   C-SVI-05: b*(1+|rho|) = 0.4*1.4 = 0.56 <= 2 OK
#   C-SVI-01: a + b*sigma*sqrt(1-rho^2)
#           = 0.04 + 0.4*0.2*sqrt(1-0.16)
#           = 0.04 + 0.08*sqrt(0.84)
#           = 0.04 + 0.08*0.9165... = 0.04 + 0.0733... = 0.1133... >= 0  OK


def _sample_params() -> SVIParameters:
    """Construct known-good SVI parameters directly (test-only shortcut)."""
    return SVIParameters(
        a=Decimal("0.04"),
        b=Decimal("0.4"),
        rho=Decimal("-0.4"),
        m=Decimal("0"),
        sigma=Decimal("0.2"),
        expiry=Decimal("1"),
    )


def _sample_params_via_create() -> SVIParameters:
    """Construct via smart constructor and unwrap."""
    return unwrap(SVIParameters.create(
        a=Decimal("0.04"),
        b=Decimal("0.4"),
        rho=Decimal("-0.4"),
        m=Decimal("0"),
        sigma=Decimal("0.2"),
        expiry=Decimal("1"),
    ))


def _make_slice(expiry: Decimal) -> SVIParameters:
    """Make a valid SVI slice with the given expiry."""
    return unwrap(SVIParameters.create(
        a=Decimal("0.04"),
        b=Decimal("0.4"),
        rho=Decimal("-0.4"),
        m=Decimal("0"),
        sigma=Decimal("0.2"),
        expiry=expiry,
    ))


# ---------------------------------------------------------------------------
# SVIParameters.create -- constraint validation
# ---------------------------------------------------------------------------


class TestSVIParametersCreate:
    def test_valid_parameters(self) -> None:
        result = SVIParameters.create(
            a=Decimal("0.04"), b=Decimal("0.4"), rho=Decimal("-0.4"),
            m=Decimal("0"), sigma=Decimal("0.2"), expiry=Decimal("1"),
        )
        assert isinstance(result, Ok)
        params = unwrap(result)
        assert params.a == Decimal("0.04")
        assert params.b == Decimal("0.4")

    def test_reject_negative_b(self) -> None:
        """C-SVI-02: b >= 0."""
        result = SVIParameters.create(
            a=Decimal("0.04"), b=Decimal("-0.1"), rho=Decimal("0"),
            m=Decimal("0"), sigma=Decimal("0.2"), expiry=Decimal("1"),
        )
        assert isinstance(result, Err)
        assert "C-SVI-02" in result.error

    def test_reject_rho_equals_one(self) -> None:
        """C-SVI-03: |rho| < 1."""
        result = SVIParameters.create(
            a=Decimal("0.04"), b=Decimal("0.4"), rho=Decimal("1"),
            m=Decimal("0"), sigma=Decimal("0.2"), expiry=Decimal("1"),
        )
        assert isinstance(result, Err)
        assert "C-SVI-03" in result.error

    def test_reject_rho_equals_neg_one(self) -> None:
        """C-SVI-03: |rho| < 1 (negative boundary)."""
        result = SVIParameters.create(
            a=Decimal("0.04"), b=Decimal("0.4"), rho=Decimal("-1"),
            m=Decimal("0"), sigma=Decimal("0.2"), expiry=Decimal("1"),
        )
        assert isinstance(result, Err)
        assert "C-SVI-03" in result.error

    def test_reject_rho_above_one(self) -> None:
        """C-SVI-03: |rho| < 1 (beyond boundary)."""
        result = SVIParameters.create(
            a=Decimal("0.04"), b=Decimal("0.4"), rho=Decimal("1.5"),
            m=Decimal("0"), sigma=Decimal("0.2"), expiry=Decimal("1"),
        )
        assert isinstance(result, Err)
        assert "C-SVI-03" in result.error

    def test_reject_sigma_zero(self) -> None:
        """C-SVI-04: sigma > 0."""
        result = SVIParameters.create(
            a=Decimal("0.04"), b=Decimal("0.4"), rho=Decimal("0"),
            m=Decimal("0"), sigma=Decimal("0"), expiry=Decimal("1"),
        )
        assert isinstance(result, Err)
        assert "C-SVI-04" in result.error

    def test_reject_sigma_negative(self) -> None:
        """C-SVI-04: sigma > 0."""
        result = SVIParameters.create(
            a=Decimal("0.04"), b=Decimal("0.4"), rho=Decimal("0"),
            m=Decimal("0"), sigma=Decimal("-0.1"), expiry=Decimal("1"),
        )
        assert isinstance(result, Err)
        assert "C-SVI-04" in result.error

    def test_reject_roger_lee_violation(self) -> None:
        """C-SVI-05: b*(1+|rho|) <= 2.

        b=1.5, rho=0.5 => 1.5 * 1.5 = 2.25 > 2.
        """
        result = SVIParameters.create(
            a=Decimal("0.04"), b=Decimal("1.5"), rho=Decimal("0.5"),
            m=Decimal("0"), sigma=Decimal("0.2"), expiry=Decimal("1"),
        )
        assert isinstance(result, Err)
        assert "C-SVI-05" in result.error

    def test_reject_vertex_negativity(self) -> None:
        """C-SVI-01: a + b*sigma*sqrt(1-rho^2) >= 0.

        a=-0.5, b=0.1, sigma=0.2, rho=0 => -0.5 + 0.1*0.2*1 = -0.48 < 0.
        """
        result = SVIParameters.create(
            a=Decimal("-0.5"), b=Decimal("0.1"), rho=Decimal("0"),
            m=Decimal("0"), sigma=Decimal("0.2"), expiry=Decimal("1"),
        )
        assert isinstance(result, Err)
        assert "C-SVI-01" in result.error

    def test_reject_expiry_zero(self) -> None:
        result = SVIParameters.create(
            a=Decimal("0.04"), b=Decimal("0.4"), rho=Decimal("0"),
            m=Decimal("0"), sigma=Decimal("0.2"), expiry=Decimal("0"),
        )
        assert isinstance(result, Err)
        assert "expiry" in result.error

    def test_reject_expiry_negative(self) -> None:
        result = SVIParameters.create(
            a=Decimal("0.04"), b=Decimal("0.4"), rho=Decimal("0"),
            m=Decimal("0"), sigma=Decimal("0.2"), expiry=Decimal("-1"),
        )
        assert isinstance(result, Err)
        assert "expiry" in result.error

    def test_frozen(self) -> None:
        params = _sample_params()
        with pytest.raises(dataclasses.FrozenInstanceError):
            params.a = Decimal("999")  # type: ignore[misc]

    def test_b_zero_allowed(self) -> None:
        """b=0 is the degenerate flat-vol case; constraints are satisfied."""
        result = SVIParameters.create(
            a=Decimal("0.04"), b=Decimal("0"), rho=Decimal("0"),
            m=Decimal("0"), sigma=Decimal("0.2"), expiry=Decimal("1"),
        )
        assert isinstance(result, Ok)


# ---------------------------------------------------------------------------
# svi_total_variance
# ---------------------------------------------------------------------------


class TestSVITotalVariance:
    def test_atm_known_value(self) -> None:
        """At k=0, m=0: w(0) = a + b*(rho*0 + sqrt(0 + sigma^2)) = a + b*sigma.

        With a=0.04, b=0.4, sigma=0.2: w(0) = 0.04 + 0.4*0.2 = 0.04 + 0.08 = 0.12.
        """
        params = _sample_params()
        w = svi_total_variance(params, Decimal("0"))
        assert w == Decimal("0.12")

    def test_wings_increasing(self) -> None:
        """Total variance increases as |k| grows (SVI is convex for b>0, sigma>0)."""
        params = _sample_params()
        w_0 = svi_total_variance(params, Decimal("0"))
        _w_pos = svi_total_variance(params, Decimal("0.5"))  # noqa: F841
        _w_neg = svi_total_variance(params, Decimal("-0.5"))  # noqa: F841
        # Both wings above ATM (note: w_neg may or may not exceed w_0
        # depending on rho; the *deep* wings always exceed ATM)
        w_deep_pos = svi_total_variance(params, Decimal("2"))
        w_deep_neg = svi_total_variance(params, Decimal("-2"))
        assert w_deep_pos > w_0
        assert w_deep_neg > w_0

    def test_non_negative(self) -> None:
        """w(k) >= 0 for valid parameters satisfying C-SVI-01."""
        params = _sample_params()
        for k_str in ["-3", "-1", "-0.5", "0", "0.5", "1", "3"]:
            w = svi_total_variance(params, Decimal(k_str))
            assert w >= Decimal("0"), f"w({k_str}) = {w} < 0"

    def test_known_analytical_value(self) -> None:
        """Verify w(0.3) against hand computation.

        k=0.3, m=0: km=0.3
        disc = sqrt(0.09 + 0.04) = sqrt(0.13) = 0.36055512...
        w = 0.04 + 0.4*(-0.4*0.3 + 0.36055512...)
          = 0.04 + 0.4*(-0.12 + 0.36055512...)
          = 0.04 + 0.4*0.24055512...
          = 0.04 + 0.09622205...
          = 0.13622205...
        """
        params = _sample_params()
        w = svi_total_variance(params, Decimal("0.3"))
        disc = sqrt_d(Decimal("0.13"))
        expected = Decimal("0.04") + Decimal("0.4") * (
            Decimal("-0.4") * Decimal("0.3") + disc
        )
        diff = abs(w - expected)
        assert diff < Decimal("1e-25"), f"w(0.3) off by {diff}"

    def test_flat_vol_when_b_zero(self) -> None:
        """When b=0, w(k) = a for all k."""
        params = SVIParameters(
            a=Decimal("0.04"), b=Decimal("0"), rho=Decimal("0"),
            m=Decimal("0"), sigma=Decimal("0.2"), expiry=Decimal("1"),
        )
        assert svi_total_variance(params, Decimal("0")) == Decimal("0.04")
        assert svi_total_variance(params, Decimal("1")) == Decimal("0.04")
        assert svi_total_variance(params, Decimal("-1")) == Decimal("0.04")


# ---------------------------------------------------------------------------
# svi_first_derivative
# ---------------------------------------------------------------------------


class TestSVIFirstDerivative:
    def test_at_m_equals_b_times_rho(self) -> None:
        """At k=m: w'(m) = b*(rho + 0/sigma) = b*rho.

        With b=0.4, rho=-0.4: w'(0) = 0.4*(-0.4) = -0.16.
        """
        params = _sample_params()
        wp = svi_first_derivative(params, Decimal("0"))
        expected = Decimal("0.4") * Decimal("-0.4")
        assert wp == expected

    def test_right_wing_slope(self) -> None:
        """As k -> +inf, w'(k) -> b*(rho+1). Verify at large k."""
        params = _sample_params()
        wp_far = svi_first_derivative(params, Decimal("100"))
        limit = params.b * (params.rho + Decimal("1"))
        diff = abs(wp_far - limit)
        assert diff < Decimal("0.001"), f"w'(100) not near b*(rho+1): diff={diff}"

    def test_left_wing_slope(self) -> None:
        """As k -> -inf, w'(k) -> b*(rho-1). Verify at large negative k."""
        params = _sample_params()
        wp_far = svi_first_derivative(params, Decimal("-100"))
        limit = params.b * (params.rho - Decimal("1"))
        diff = abs(wp_far - limit)
        assert diff < Decimal("0.001"), f"w'(-100) not near b*(rho-1): diff={diff}"


# ---------------------------------------------------------------------------
# svi_second_derivative
# ---------------------------------------------------------------------------


class TestSVISecondDerivative:
    def test_always_positive(self) -> None:
        """w''(k) > 0 for b > 0 and sigma > 0 (convexity)."""
        params = _sample_params()
        for k_str in ["-3", "-1", "0", "0.5", "1", "3"]:
            wpp = svi_second_derivative(params, Decimal(k_str))
            assert wpp > Decimal("0"), f"w''({k_str}) = {wpp} not positive"

    def test_at_m_equals_b_over_sigma(self) -> None:
        """At k=m: w''(m) = b*sigma^2 / sigma^3 = b/sigma.

        With b=0.4, sigma=0.2: w''(0) = 0.4/0.2 = 2.
        """
        params = _sample_params()
        wpp = svi_second_derivative(params, Decimal("0"))
        expected = Decimal("0.4") / Decimal("0.2")
        assert wpp == expected

    def test_curvature_decreases_in_wings(self) -> None:
        """Curvature is maximal at k=m and decreases in both wings."""
        params = _sample_params()
        wpp_m = svi_second_derivative(params, Decimal("0"))
        wpp_wing = svi_second_derivative(params, Decimal("1"))
        assert wpp_m > wpp_wing


# ---------------------------------------------------------------------------
# VolSurface.create
# ---------------------------------------------------------------------------


class TestVolSurfaceCreate:
    def test_valid_three_slice(self) -> None:
        """A valid surface with 3 expiry slices."""
        expiries = (Decimal("0.25"), Decimal("0.5"), Decimal("1"))
        slices = tuple(_make_slice(t) for t in expiries)
        result = VolSurface.create(
            underlying="SPX",
            as_of=date(2025, 6, 15),
            expiries=expiries,
            slices=slices,
            model_config_ref="SVI-CFG-001",
        )
        assert isinstance(result, Ok)
        surface = unwrap(result)
        assert len(surface.expiries) == 3
        assert surface.underlying.value == "SPX"

    def test_reject_mismatched_lengths(self) -> None:
        result = VolSurface.create(
            underlying="SPX",
            as_of=date(2025, 6, 15),
            expiries=(Decimal("0.25"), Decimal("0.5")),
            slices=(_make_slice(Decimal("0.25")),),
            model_config_ref="CFG",
        )
        assert isinstance(result, Err)
        assert "length" in result.error.lower()

    def test_reject_unsorted_expiries(self) -> None:
        expiries = (Decimal("1"), Decimal("0.5"))
        slices = (_make_slice(Decimal("1")), _make_slice(Decimal("0.5")))
        result = VolSurface.create(
            underlying="SPX",
            as_of=date(2025, 6, 15),
            expiries=expiries,
            slices=slices,
            model_config_ref="CFG",
        )
        assert isinstance(result, Err)
        assert "ascending" in result.error

    def test_reject_non_positive_expiry(self) -> None:
        # Use direct constructor for the slice since create would reject expiry=0
        bad_slice = SVIParameters(
            a=Decimal("0.04"), b=Decimal("0.4"), rho=Decimal("-0.4"),
            m=Decimal("0"), sigma=Decimal("0.2"), expiry=Decimal("0"),
        )
        result = VolSurface.create(
            underlying="SPX",
            as_of=date(2025, 6, 15),
            expiries=(Decimal("0"),),
            slices=(bad_slice,),
            model_config_ref="CFG",
        )
        assert isinstance(result, Err)
        assert "expiry" in result.error.lower()

    def test_reject_expiry_mismatch(self) -> None:
        """Slice's internal expiry doesn't match the surface's expiry."""
        slice_1y = _make_slice(Decimal("1"))
        result = VolSurface.create(
            underlying="SPX",
            as_of=date(2025, 6, 15),
            expiries=(Decimal("0.5"),),      # surface says 0.5
            slices=(slice_1y,),               # but slice says 1.0
            model_config_ref="CFG",
        )
        assert isinstance(result, Err)
        assert "expiry" in result.error.lower()

    def test_reject_empty(self) -> None:
        result = VolSurface.create(
            underlying="SPX",
            as_of=date(2025, 6, 15),
            expiries=(),
            slices=(),
            model_config_ref="CFG",
        )
        assert isinstance(result, Err)

    def test_reject_empty_underlying(self) -> None:
        result = VolSurface.create(
            underlying="",
            as_of=date(2025, 6, 15),
            expiries=(Decimal("1"),),
            slices=(_make_slice(Decimal("1")),),
            model_config_ref="CFG",
        )
        assert isinstance(result, Err)
        assert "underlying" in result.error.lower()

    def test_frozen(self) -> None:
        surface = unwrap(VolSurface.create(
            underlying="SPX",
            as_of=date(2025, 6, 15),
            expiries=(Decimal("1"),),
            slices=(_make_slice(Decimal("1")),),
            model_config_ref="CFG",
        ))
        with pytest.raises(dataclasses.FrozenInstanceError):
            surface.as_of = date(2020, 1, 1)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# implied_vol
# ---------------------------------------------------------------------------


class TestImpliedVol:
    def test_atm_known_value(self) -> None:
        """At k=0, T=1: vol = sqrt(w(0)/1) = sqrt(0.12).

        w(0) = a + b*sigma = 0.04 + 0.08 = 0.12 (for m=0).
        """
        surface = unwrap(VolSurface.create(
            underlying="SPX",
            as_of=date(2025, 6, 15),
            expiries=(Decimal("1"),),
            slices=(_make_slice(Decimal("1")),),
            model_config_ref="CFG",
        ))
        vol_result = implied_vol(surface, Decimal("0"), Decimal("1"))
        assert isinstance(vol_result, Ok)
        vol = unwrap(vol_result)
        expected = sqrt_d(Decimal("0.12"))
        diff = abs(vol - expected)
        assert diff < Decimal("1e-25"), f"ATM vol off by {diff}"

    def test_valid_result_off_atm(self) -> None:
        """implied_vol returns a positive Decimal for non-ATM point."""
        surface = unwrap(VolSurface.create(
            underlying="SPX",
            as_of=date(2025, 6, 15),
            expiries=(Decimal("1"),),
            slices=(_make_slice(Decimal("1")),),
            model_config_ref="CFG",
        ))
        vol = unwrap(implied_vol(surface, Decimal("0.5"), Decimal("1")))
        assert vol > Decimal("0")

    def test_negative_expiry_err(self) -> None:
        surface = unwrap(VolSurface.create(
            underlying="SPX",
            as_of=date(2025, 6, 15),
            expiries=(Decimal("1"),),
            slices=(_make_slice(Decimal("1")),),
            model_config_ref="CFG",
        ))
        result = implied_vol(surface, Decimal("0"), Decimal("-0.5"))
        assert isinstance(result, Err)
        assert "expiry" in result.error

    def test_zero_expiry_err(self) -> None:
        surface = unwrap(VolSurface.create(
            underlying="SPX",
            as_of=date(2025, 6, 15),
            expiries=(Decimal("1"),),
            slices=(_make_slice(Decimal("1")),),
            model_config_ref="CFG",
        ))
        result = implied_vol(surface, Decimal("0"), Decimal("0"))
        assert isinstance(result, Err)

    def test_nearest_expiry_selection(self) -> None:
        """With slices at T=0.25 and T=1.0, querying T=0.3 picks T=0.25."""
        expiries = (Decimal("0.25"), Decimal("1"))
        slices = tuple(_make_slice(t) for t in expiries)
        surface = unwrap(VolSurface.create(
            underlying="SPX",
            as_of=date(2025, 6, 15),
            expiries=expiries,
            slices=slices,
            model_config_ref="CFG",
        ))
        # Query at T=0.3 should use the T=0.25 slice
        vol_near = unwrap(implied_vol(surface, Decimal("0"), Decimal("0.3")))
        # Compute what we'd get from the 0.25 slice evaluated at T=0.3
        w = svi_total_variance(slices[0], Decimal("0"))
        expected = sqrt_d(w / Decimal("0.3"))
        diff = abs(vol_near - expected)
        assert diff < Decimal("1e-25"), f"Nearest-slice vol off by {diff}"


# ---------------------------------------------------------------------------
# Hypothesis: SVI property-based tests
# ---------------------------------------------------------------------------


# Strategy for valid SVI-like parameters (not all combos pass constraints)
_svi_a = st.decimals(
    min_value=Decimal("0.01"), max_value=Decimal("0.20"),
    places=2, allow_nan=False, allow_infinity=False,
)
_svi_b = st.decimals(
    min_value=Decimal("0.05"), max_value=Decimal("0.50"),
    places=2, allow_nan=False, allow_infinity=False,
)
_svi_rho = st.decimals(
    min_value=Decimal("-0.50"), max_value=Decimal("0.50"),
    places=2, allow_nan=False, allow_infinity=False,
)
_svi_sigma = st.decimals(
    min_value=Decimal("0.10"), max_value=Decimal("0.50"),
    places=2, allow_nan=False, allow_infinity=False,
)
_svi_k = st.decimals(
    min_value=Decimal("-3"), max_value=Decimal("3"),
    places=2, allow_nan=False, allow_infinity=False,
)


class TestSVIHypothesis:
    @given(k=_svi_k)
    @settings(max_examples=200, deadline=None)
    def test_total_variance_non_negative_property(self, k: Decimal) -> None:
        """w(k) >= 0 for textbook SVI params at any strike."""
        params = _sample_params_via_create()
        w = svi_total_variance(params, k)
        assert w >= Decimal(0), f"w({k}) = {w} < 0"

    @given(k=_svi_k)
    @settings(max_examples=200, deadline=None)
    def test_second_derivative_positive_property(self, k: Decimal) -> None:
        """w''(k) > 0 for b > 0, sigma > 0 (SVI convexity)."""
        params = _sample_params_via_create()
        wpp = svi_second_derivative(params, k)
        assert wpp > Decimal(0), f"w''({k}) = {wpp} not positive"

    @given(a=_svi_a, b=_svi_b, rho=_svi_rho, sigma=_svi_sigma)
    @settings(max_examples=200, deadline=None)
    def test_svi_create_roundtrip_property(
        self, a: Decimal, b: Decimal, rho: Decimal, sigma: Decimal,
    ) -> None:
        """If SVIParameters.create accepts, fields match inputs."""
        result = SVIParameters.create(
            a=a, b=b, rho=rho, m=Decimal("0"),
            sigma=sigma, expiry=Decimal("1"),
        )
        if isinstance(result, Ok):
            params = result.value
            assert params.a == a
            assert params.b == b
            assert params.rho == rho
            assert params.sigma == sigma

    @given(
        k=_svi_k,
        expiry=st.decimals(
            min_value=Decimal("0.1"), max_value=Decimal("5"),
            places=2, allow_nan=False, allow_infinity=False,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_implied_vol_positive_property(
        self, k: Decimal, expiry: Decimal,
    ) -> None:
        """implied_vol > 0 for valid surface at any (k, T > 0)."""
        slc = _make_slice(expiry)
        surface = unwrap(VolSurface.create(
            underlying="SPX",
            as_of=date(2025, 6, 15),
            expiries=(expiry,),
            slices=(slc,),
            model_config_ref="CFG-HYP",
        ))
        vol = unwrap(implied_vol(surface, k, expiry))
        assert vol > Decimal(0), f"implied_vol(k={k}, T={expiry}) = {vol}"


# ---------------------------------------------------------------------------
# calibrate_vol_surface
# ---------------------------------------------------------------------------


def _make_config() -> ModelConfig:
    """Create a test ModelConfig for SVI calibration."""
    return unwrap(ModelConfig.create(
        config_id="SVI-CFG-TEST",
        model_class="SVI_GRID_SEARCH",
        code_version="1.0.0",
    ))


def _generate_quotes(
    params: SVIParameters,
    ks: tuple[Decimal, ...],
    expiry: Decimal,
) -> tuple[tuple[Decimal, Decimal, Decimal], ...]:
    """Generate noise-free (k, T, w) quotes from known SVI parameters."""
    return tuple(
        (k, expiry, svi_total_variance(params, k)) for k in ks
    )


class TestCalibrateVolSurface:
    def test_two_expiry_surface(self) -> None:
        """Calibrate a 2-expiry surface from synthetic noise-free quotes."""
        # Known parameters for two slices
        p1 = unwrap(SVIParameters.create(
            a=Decimal("0.04"), b=Decimal("0.4"), rho=Decimal("-0.3"),
            m=Decimal("0"), sigma=Decimal("0.2"), expiry=Decimal("0.5"),
        ))
        p2 = unwrap(SVIParameters.create(
            a=Decimal("0.04"), b=Decimal("0.4"), rho=Decimal("-0.3"),
            m=Decimal("0"), sigma=Decimal("0.2"), expiry=Decimal("1"),
        ))

        ks = (
            Decimal("-0.5"), Decimal("-0.25"), Decimal("0"),
            Decimal("0.25"), Decimal("0.5"),
        )
        q1 = _generate_quotes(p1, ks, Decimal("0.5"))
        q2 = _generate_quotes(p2, ks, Decimal("1"))
        all_quotes = q1 + q2

        config = _make_config()
        result = calibrate_vol_surface(all_quotes, config, date(2025, 6, 15), "SPX")
        assert isinstance(result, Ok), f"Expected Ok, got {result}"
        att = unwrap(result)

        # Attestation wraps a VolSurface
        surface = att.value
        assert isinstance(surface, VolSurface)
        assert len(surface.expiries) == 2
        assert surface.expiries[0] == Decimal("0.5")
        assert surface.expiries[1] == Decimal("1")
        assert surface.underlying.value == "SPX"
        assert surface.model_config_ref == "SVI-CFG-TEST"

    def test_derived_confidence_fit_quality(self) -> None:
        """Calibration produces DerivedConfidence with rmse and max_error."""
        p = unwrap(SVIParameters.create(
            a=Decimal("0.04"), b=Decimal("0.4"), rho=Decimal("-0.3"),
            m=Decimal("0"), sigma=Decimal("0.2"), expiry=Decimal("1"),
        ))
        ks = (
            Decimal("-0.5"), Decimal("-0.25"), Decimal("0"),
            Decimal("0.25"), Decimal("0.5"),
        )
        quotes = _generate_quotes(p, ks, Decimal("1"))
        config = _make_config()
        att = unwrap(calibrate_vol_surface(quotes, config, date(2025, 6, 15), "SPX"))

        # Confidence is DerivedConfidence
        assert isinstance(att.confidence, DerivedConfidence)
        assert att.confidence.method.value == "SVI_GRID_SEARCH"
        assert att.confidence.config_ref.value == "SVI-CFG-TEST"

        # fit_quality has rmse and max_error
        fq = att.confidence.fit_quality
        assert "rmse" in fq
        assert "max_error" in fq
        # Noise-free quotes with exact grid match -> near-zero errors
        assert fq["rmse"] < Decimal("1e-10")
        assert fq["max_error"] < Decimal("1e-10")

    def test_empty_quotes_err(self) -> None:
        """Empty quotes returns Err."""
        config = _make_config()
        result = calibrate_vol_surface((), config, date(2025, 6, 15), "SPX")
        assert isinstance(result, Err)
        assert "empty" in result.error.lower()

    def test_single_expiry_valid(self) -> None:
        """Single expiry with enough quotes produces valid 1-slice surface."""
        p = unwrap(SVIParameters.create(
            a=Decimal("0.04"), b=Decimal("0.4"), rho=Decimal("-0.3"),
            m=Decimal("0"), sigma=Decimal("0.2"), expiry=Decimal("0.25"),
        ))
        ks = (
            Decimal("-0.4"), Decimal("-0.2"), Decimal("0"),
            Decimal("0.2"), Decimal("0.4"),
        )
        quotes = _generate_quotes(p, ks, Decimal("0.25"))
        config = _make_config()
        att = unwrap(calibrate_vol_surface(quotes, config, date(2025, 6, 15), "SPX"))

        surface = att.value
        assert len(surface.expiries) == 1
        assert surface.expiries[0] == Decimal("0.25")

        # Surface produces valid implied vol at ATM
        vol = unwrap(implied_vol(surface, Decimal("0"), Decimal("0.25")))
        assert vol > Decimal("0")

    def test_negative_expiry_err(self) -> None:
        """Quote with negative expiry returns Err."""
        config = _make_config()
        quotes = (
            (Decimal("0"), Decimal("-1"), Decimal("0.04")),
            (Decimal("0.1"), Decimal("-1"), Decimal("0.05")),
            (Decimal("0.2"), Decimal("-1"), Decimal("0.06")),
        )
        result = calibrate_vol_surface(quotes, config, date(2025, 6, 15), "SPX")
        assert isinstance(result, Err)

    def test_negative_variance_err(self) -> None:
        """Quote with negative total variance returns Err."""
        config = _make_config()
        quotes = (
            (Decimal("0"), Decimal("1"), Decimal("-0.04")),
            (Decimal("0.1"), Decimal("1"), Decimal("0.05")),
            (Decimal("0.2"), Decimal("1"), Decimal("0.06")),
        )
        result = calibrate_vol_surface(quotes, config, date(2025, 6, 15), "SPX")
        assert isinstance(result, Err)

    def test_too_few_quotes_err(self) -> None:
        """Fewer than 3 quotes per slice returns Err."""
        config = _make_config()
        quotes = (
            (Decimal("0"), Decimal("1"), Decimal("0.04")),
            (Decimal("0.1"), Decimal("1"), Decimal("0.05")),
        )
        result = calibrate_vol_surface(quotes, config, date(2025, 6, 15), "SPX")
        assert isinstance(result, Err)

    def test_attestation_has_content_hash(self) -> None:
        """Attestation includes non-empty content_hash and attestation_id."""
        p = unwrap(SVIParameters.create(
            a=Decimal("0.04"), b=Decimal("0.4"), rho=Decimal("-0.3"),
            m=Decimal("0"), sigma=Decimal("0.2"), expiry=Decimal("1"),
        ))
        ks = (
            Decimal("-0.5"), Decimal("-0.25"), Decimal("0"),
            Decimal("0.25"), Decimal("0.5"),
        )
        quotes = _generate_quotes(p, ks, Decimal("1"))
        config = _make_config()
        att = unwrap(calibrate_vol_surface(quotes, config, date(2025, 6, 15), "SPX"))
        assert len(att.content_hash) > 0
        assert len(att.attestation_id) > 0
        assert isinstance(att, Attestation)
