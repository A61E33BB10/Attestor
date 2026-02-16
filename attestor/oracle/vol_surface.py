"""SVI volatility surface types and pure-Decimal evaluation.

Implements Gatheral's Stochastic Volatility Inspired (SVI) parameterization
for the implied variance smile at each expiry slice.

SVI raw parameterization
------------------------
    w(k) = a + b * (rho * (k - m) + sqrt((k - m)^2 + sigma^2))

where k = log(K/F) is log-moneyness, and w(k) = sigma_BS^2 * T is total
implied variance.

Constraints (per Gatheral & Jacquier 2014)
------------------------------------------
    C-SVI-01: a + b * sigma * sqrt(1 - rho^2) >= 0   (vertex non-negativity)
    C-SVI-02: b >= 0
    C-SVI-03: |rho| < 1
    C-SVI-04: sigma > 0
    C-SVI-05: b * (1 + |rho|) <= 2                    (Roger Lee wing bound)

Functions
---------
    svi_total_variance   : SVIParameters x Decimal -> Decimal
    svi_first_derivative : SVIParameters x Decimal -> Decimal
    svi_second_derivative: SVIParameters x Decimal -> Decimal
    implied_vol          : VolSurface x Decimal x Decimal -> Ok[Decimal] | Err[str]
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, localcontext
from typing import final

from attestor.core.decimal_math import sqrt_d
from attestor.core.money import ATTESTOR_DECIMAL_CONTEXT, NonEmptyStr
from attestor.core.result import Err, Ok
from attestor.core.types import FrozenMap, UtcDatetime
from attestor.oracle.attestation import Attestation, DerivedConfidence, create_attestation
from attestor.oracle.calibration import ModelConfig

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ZERO = Decimal("0")
_ONE = Decimal("1")
_TWO = Decimal("2")


# ---------------------------------------------------------------------------
# SVIParameters -- single expiry slice
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class SVIParameters:
    """SVI raw parameterization for a single expiry slice.

    w(k) = a + b * (rho * (k - m) + sqrt((k - m)^2 + sigma^2))

    All five SVI constraints are enforced at construction time.
    """

    a: Decimal
    b: Decimal       # >= 0  (C-SVI-02)
    rho: Decimal     # (-1, 1)  (C-SVI-03)
    m: Decimal
    sigma: Decimal   # > 0  (C-SVI-04)
    expiry: Decimal  # > 0  (year fraction for this slice)

    @staticmethod
    def create(
        a: Decimal,
        b: Decimal,
        rho: Decimal,
        m: Decimal,
        sigma: Decimal,
        expiry: Decimal,
    ) -> Ok[SVIParameters] | Err[str]:
        """Validate all SVI constraints and construct.

        Returns Err with a diagnostic message if any constraint is violated.
        """
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            # C-SVI-02: b >= 0
            if b < _ZERO:
                return Err(f"C-SVI-02: b must be >= 0, got {b}")

            # C-SVI-03: |rho| < 1
            if abs(rho) >= _ONE:
                return Err(f"C-SVI-03: |rho| must be < 1, got {rho}")

            # C-SVI-04: sigma > 0
            if sigma <= _ZERO:
                return Err(f"C-SVI-04: sigma must be > 0, got {sigma}")

            # C-SVI-05: Roger Lee wing bound -- b * (1 + |rho|) <= 2
            lee_lhs = b * (_ONE + abs(rho))
            if lee_lhs > _TWO:
                return Err(
                    f"C-SVI-05: b*(1+|rho|) must be <= 2, got {lee_lhs}"
                )

            # C-SVI-01: vertex non-negativity -- a + b*sigma*sqrt(1-rho^2) >= 0
            one_minus_rho_sq = _ONE - rho * rho
            vertex = a + b * sigma * sqrt_d(one_minus_rho_sq)
            if vertex < _ZERO:
                return Err(
                    f"C-SVI-01: a + b*sigma*sqrt(1-rho^2) must be >= 0, "
                    f"got {vertex}"
                )

            # Expiry must be positive
            if expiry <= _ZERO:
                return Err(f"expiry must be > 0, got {expiry}")

            return Ok(SVIParameters(
                a=a, b=b, rho=rho, m=m, sigma=sigma, expiry=expiry,
            ))


# ---------------------------------------------------------------------------
# SVI evaluation functions (pure Decimal, no float)
# ---------------------------------------------------------------------------


def svi_total_variance(params: SVIParameters, k: Decimal) -> Decimal:
    """Compute total implied variance w(k) from SVI parameters.

    w(k) = a + b * (rho * (k - m) + sqrt((k - m)^2 + sigma^2))
    """
    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        km = k - params.m
        km_sq = km * km
        disc = sqrt_d(km_sq + params.sigma * params.sigma)
        return params.a + params.b * (params.rho * km + disc)


def svi_first_derivative(params: SVIParameters, k: Decimal) -> Decimal:
    """First derivative of total variance w.r.t. log-moneyness.

    w'(k) = b * (rho + (k - m) / sqrt((k - m)^2 + sigma^2))
    """
    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        km = k - params.m
        km_sq = km * km
        disc = sqrt_d(km_sq + params.sigma * params.sigma)
        return params.b * (params.rho + km / disc)


def svi_second_derivative(params: SVIParameters, k: Decimal) -> Decimal:
    """Second derivative of total variance w.r.t. log-moneyness.

    w''(k) = b * sigma^2 / ((k - m)^2 + sigma^2)^(3/2)
    """
    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        km = k - params.m
        km_sq = km * km
        sigma_sq = params.sigma * params.sigma
        denom_sq = km_sq + sigma_sq
        denom_three_half = denom_sq * sqrt_d(denom_sq)
        return params.b * sigma_sq / denom_three_half


# ---------------------------------------------------------------------------
# VolSurface -- calibrated SVI surface across expiries
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class VolSurface:
    """Calibrated volatility surface -- SVI parameters per expiry.

    Invariants enforced at construction:
    - expiries and slices have the same length (>= 1)
    - expiries are sorted in strictly ascending order
    - every expiry is positive
    - each slice's expiry field matches the corresponding surface expiry
    """

    underlying: NonEmptyStr
    as_of: date
    expiries: tuple[Decimal, ...]
    slices: tuple[SVIParameters, ...]
    model_config_ref: str

    @staticmethod
    def create(
        underlying: str,
        as_of: date,
        expiries: tuple[Decimal, ...],
        slices: tuple[SVIParameters, ...],
        model_config_ref: str,
    ) -> Ok[VolSurface] | Err[str]:
        """Validate and construct a VolSurface."""
        # Underlying must be non-empty
        match NonEmptyStr.parse(underlying):
            case Err(e):
                return Err(f"VolSurface.underlying: {e}")
            case Ok(und):
                pass

        # Must have at least one slice
        if len(expiries) == 0:
            return Err("VolSurface requires at least one expiry")

        # Lengths must match
        if len(expiries) != len(slices):
            return Err(
                f"VolSurface: expiries length ({len(expiries)}) != "
                f"slices length ({len(slices)})"
            )

        # Expiries must be positive and strictly ascending
        for i, t in enumerate(expiries):
            if t <= _ZERO:
                return Err(f"VolSurface: expiry[{i}] must be > 0, got {t}")
            if i > 0 and t <= expiries[i - 1]:
                return Err(
                    f"VolSurface: expiries must be strictly ascending, "
                    f"but expiry[{i}]={t} <= expiry[{i - 1}]={expiries[i - 1]}"
                )

        # Each slice's expiry must match the corresponding surface expiry
        for i, (t, sl) in enumerate(zip(expiries, slices, strict=True)):
            if sl.expiry != t:
                return Err(
                    f"VolSurface: slice[{i}].expiry={sl.expiry} != "
                    f"expiry[{i}]={t}"
                )

        return Ok(VolSurface(
            underlying=und,
            as_of=as_of,
            expiries=expiries,
            slices=slices,
            model_config_ref=model_config_ref,
        ))


# ---------------------------------------------------------------------------
# implied_vol -- extract implied vol from surface at (k, T)
# ---------------------------------------------------------------------------


def implied_vol(
    surface: VolSurface,
    log_moneyness: Decimal,
    expiry: Decimal,
) -> Ok[Decimal] | Err[str]:
    """Interpolate implied volatility at (k, T).

    sigma(k, T) = sqrt(w(k, T) / T)

    Interpolation: linear in total variance between the two bracketing
    expiry slices.  For exact matches or extrapolation (T beyond the
    surface range), the nearest slice is used directly.
    Returns Err if expiry <= 0.
    """
    if expiry <= _ZERO:
        return Err(f"implied_vol: expiry must be > 0, got {expiry}")

    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        k = log_moneyness
        n = len(surface.expiries)

        # Exact match -- fast path
        for i in range(n):
            if surface.expiries[i] == expiry:
                w = svi_total_variance(surface.slices[i], k)
                if w < _ZERO:
                    return Err(
                        f"implied_vol: negative total variance w={w} "
                        f"at k={k}"
                    )
                return Ok(sqrt_d(w / expiry))

        # Find bracketing slices for interpolation
        # If expiry < first or > last, extrapolate from nearest slice
        if expiry < surface.expiries[0]:
            w = svi_total_variance(surface.slices[0], k)
            if w < _ZERO:
                return Err(
                    f"implied_vol: negative total variance w={w} at k={k}"
                )
            return Ok(sqrt_d(w / expiry))

        if expiry > surface.expiries[-1]:
            w = svi_total_variance(surface.slices[-1], k)
            if w < _ZERO:
                return Err(
                    f"implied_vol: negative total variance w={w} at k={k}"
                )
            return Ok(sqrt_d(w / expiry))

        # Interpolate: find i such that expiries[i] < expiry < expiries[i+1]
        lo = 0
        for i in range(n - 1):
            if surface.expiries[i] < expiry < surface.expiries[i + 1]:
                lo = i
                break

        t_lo = surface.expiries[lo]
        t_hi = surface.expiries[lo + 1]
        w_lo = svi_total_variance(surface.slices[lo], k)
        w_hi = svi_total_variance(surface.slices[lo + 1], k)

        # Linear interpolation in total variance
        alpha = (expiry - t_lo) / (t_hi - t_lo)
        w_interp = w_lo + alpha * (w_hi - w_lo)

        if w_interp < _ZERO:
            return Err(
                f"implied_vol: negative interpolated total variance "
                f"w={w_interp} at k={k}"
            )
        return Ok(sqrt_d(w_interp / expiry))


# ---------------------------------------------------------------------------
# SVI calibration -- grid search with analytical linear solve
# ---------------------------------------------------------------------------


def _det3(
    r0: tuple[Decimal, Decimal, Decimal],
    r1: tuple[Decimal, Decimal, Decimal],
    r2: tuple[Decimal, Decimal, Decimal],
) -> Decimal:
    """Determinant of 3x3 matrix given as row tuples."""
    return (
        r0[0] * (r1[1] * r2[2] - r1[2] * r2[1])
        - r0[1] * (r1[0] * r2[2] - r1[2] * r2[0])
        + r0[2] * (r1[0] * r2[1] - r1[1] * r2[0])
    )


def _solve_normal_equations(
    mat: tuple[
        tuple[Decimal, Decimal, Decimal],
        tuple[Decimal, Decimal, Decimal],
        tuple[Decimal, Decimal, Decimal],
    ],
    rhs: tuple[Decimal, Decimal, Decimal],
) -> tuple[Decimal, Decimal, Decimal] | None:
    """Solve 3x3 system via Cramer's rule. Returns None if singular."""
    d = _det3(mat[0], mat[1], mat[2])
    if d == _ZERO:
        return None
    d0 = _det3(
        (rhs[0], mat[0][1], mat[0][2]),
        (rhs[1], mat[1][1], mat[1][2]),
        (rhs[2], mat[2][1], mat[2][2]),
    )
    d1 = _det3(
        (mat[0][0], rhs[0], mat[0][2]),
        (mat[1][0], rhs[1], mat[1][2]),
        (mat[2][0], rhs[2], mat[2][2]),
    )
    d2 = _det3(
        (mat[0][0], mat[0][1], rhs[0]),
        (mat[1][0], mat[1][1], rhs[1]),
        (mat[2][0], mat[2][1], rhs[2]),
    )
    return (d0 / d, d1 / d, d2 / d)


# Grid values for (m, sigma) search
_M_OFFSETS: tuple[Decimal, ...] = tuple(
    Decimal(s) for s in ("-0.5", "-0.3", "-0.1", "0", "0.1", "0.3", "0.5")
)
_SIGMA_GRID: tuple[Decimal, ...] = tuple(
    Decimal(s) for s in ("0.05", "0.10", "0.15", "0.20", "0.30", "0.40", "0.50")
)


def _fit_svi_slice(
    quotes: tuple[tuple[Decimal, Decimal], ...],
    expiry: Decimal,
) -> Ok[tuple[SVIParameters, Decimal]] | Err[str]:
    """Fit SVI to a single expiry slice.

    Grid search over (m, sigma), analytical solve for (a, b*rho, b).
    Returns (best_params, rmse) or Err.
    """
    n = len(quotes)
    if n < 3:
        return Err(f"Need >= 3 quotes per slice, got {n}")

    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        ks = tuple(q[0] for q in quotes)
        k_min, k_max = min(ks), max(ks)
        k_mid = (k_min + k_max) / _TWO
        k_range = max(k_max - k_min, Decimal("0.1"))
        n_dec = Decimal(n)

        best_sse: Decimal | None = None
        best_params: SVIParameters | None = None

        for m_off in _M_OFFSETS:
            m_try = k_mid + k_range * m_off
            for sigma_try in _SIGMA_GRID:
                # Precompute u_i, v_i for this (m, sigma)
                us: list[Decimal] = []
                vs: list[Decimal] = []
                ws: list[Decimal] = []
                for k_i, w_i in quotes:
                    u = k_i - m_try
                    v = sqrt_d(u * u + sigma_try * sigma_try)
                    us.append(u)
                    vs.append(v)
                    ws.append(w_i)

                # Build normal equations: X^T X * theta = X^T w
                s_u = sum(us, _ZERO)
                s_v = sum(vs, _ZERO)
                s_w = sum(ws, _ZERO)
                s_uu = sum((u * u for u in us), _ZERO)
                s_uv = sum((u * v for u, v in zip(us, vs, strict=True)), _ZERO)
                s_vv = sum((v * v for v in vs), _ZERO)
                s_uw = sum((u * w for u, w in zip(us, ws, strict=True)), _ZERO)
                s_vw = sum((v * w for v, w in zip(vs, ws, strict=True)), _ZERO)

                mat = (
                    (n_dec, s_u, s_v),
                    (s_u, s_uu, s_uv),
                    (s_v, s_uv, s_vv),
                )
                sol = _solve_normal_equations(mat, (s_w, s_uw, s_vw))
                if sol is None:
                    continue

                alpha, beta, gamma = sol

                # gamma = b (must be > 0), rho = beta / gamma
                if gamma <= _ZERO:
                    continue
                rho_try = beta / gamma
                if abs(rho_try) >= _ONE:
                    continue

                match SVIParameters.create(
                    a=alpha, b=gamma, rho=rho_try,
                    m=m_try, sigma=sigma_try, expiry=expiry,
                ):
                    case Err():
                        continue
                    case Ok(params):
                        pass

                # Compute SSE
                sse = _ZERO
                for k_i, w_i in quotes:
                    w_pred = svi_total_variance(params, k_i)
                    diff = w_pred - w_i
                    sse += diff * diff

                if best_sse is None or sse < best_sse:
                    best_sse = sse
                    best_params = params

        if best_params is None or best_sse is None:
            return Err("No valid SVI parameters found for slice")

        rmse = sqrt_d(best_sse / n_dec)
        return Ok((best_params, rmse))


def calibrate_vol_surface(
    quotes: tuple[tuple[Decimal, Decimal, Decimal], ...],
    config: ModelConfig,
    as_of: date,
    underlying: str,
) -> Ok[Attestation[VolSurface]] | Err[str]:
    """Calibrate SVI vol surface from total variance quotes.

    Each quote is (log_moneyness, expiry, market_total_variance).
    Groups quotes by expiry, fits SVI parameters per slice using
    grid search over (m, sigma) with analytical solution for (a, b, rho).
    Returns Attestation[VolSurface] with DerivedConfidence.
    """
    if len(quotes) == 0:
        return Err("calibrate_vol_surface: empty quotes")

    # Group by expiry
    expiry_groups: dict[Decimal, list[tuple[Decimal, Decimal]]] = {}
    for k, t, w in quotes:
        if t <= _ZERO:
            return Err(f"calibrate_vol_surface: expiry must be > 0, got {t}")
        if w < _ZERO:
            return Err(
                f"calibrate_vol_surface: total variance must be >= 0, got {w}"
            )
        expiry_groups.setdefault(t, []).append((k, w))

    sorted_expiries = sorted(expiry_groups.keys())

    slices: list[SVIParameters] = []
    total_sse = _ZERO
    total_quotes = 0
    max_err = _ZERO

    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        for t in sorted_expiries:
            group = tuple(expiry_groups[t])
            match _fit_svi_slice(group, t):
                case Err(e):
                    return Err(f"calibrate_vol_surface: slice T={t}: {e}")
                case Ok((params, _rmse)):
                    slices.append(params)
                    # Track errors for fit_quality
                    for k_i, w_i in group:
                        w_pred = svi_total_variance(params, k_i)
                        err = abs(w_pred - w_i)
                        if err > max_err:
                            max_err = err
                        total_sse += err * err
                    total_quotes += len(group)

        overall_rmse = sqrt_d(total_sse / Decimal(total_quotes))

    # Build VolSurface
    match VolSurface.create(
        underlying=underlying,
        as_of=as_of,
        expiries=tuple(sorted_expiries),
        slices=tuple(slices),
        model_config_ref=config.config_id.value,
    ):
        case Err(e):
            return Err(f"calibrate_vol_surface: {e}")
        case Ok(surface):
            pass

    # DerivedConfidence with fit_quality metrics
    match FrozenMap.create({"rmse": overall_rmse, "max_error": max_err}):
        case Err(e):
            return Err(f"calibrate_vol_surface fit_quality: {e}")
        case Ok(fq):
            pass

    match DerivedConfidence.create(
        method=config.model_class.value,
        config_ref=config.config_id.value,
        fit_quality=fq,
    ):
        case Err(e):
            return Err(f"calibrate_vol_surface confidence: {e}")
        case Ok(confidence):
            pass

    return create_attestation(
        value=surface,
        confidence=confidence,
        source=config.model_class.value,
        timestamp=datetime.now(tz=UtcDatetime.now().value.tzinfo),
    )
