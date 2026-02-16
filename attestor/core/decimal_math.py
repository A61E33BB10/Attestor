"""Pure-Decimal mathematical functions for Attestor.

All functions use ATTESTOR_DECIMAL_CONTEXT (prec=28, ROUND_HALF_EVEN).
No float, no math module -- every intermediate computation is Decimal.

Functions
---------
exp_d   : Decimal -> Decimal   (Taylor series with range reduction)
ln_d    : Decimal -> Decimal   (range reduction + series; ValueError on non-positive)
sqrt_d  : Decimal -> Decimal   (wrapper around Decimal.sqrt in ATTESTOR_DECIMAL_CONTEXT)
expm1_neg_d : Decimal -> Decimal  (1 - exp(-x) without subtractive cancellation)
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from attestor.core.money import ATTESTOR_DECIMAL_CONTEXT

# ---------------------------------------------------------------------------
# Internal precision: compute at +10 guard digits, then quantize back to 28
# ---------------------------------------------------------------------------

_GUARD_DIGITS = 10
_INTERNAL_PREC = ATTESTOR_DECIMAL_CONTEXT.prec + _GUARD_DIGITS  # 38

_ZERO = Decimal("0")
_ONE = Decimal("1")
_TWO = Decimal("2")
_HALF = Decimal("0.5")


def _to_output(value: Decimal) -> Decimal:
    """Round an internal-precision Decimal back to ATTESTOR_DECIMAL_CONTEXT precision."""
    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        return value + _ZERO  # forces rounding to prec=28


# ---------------------------------------------------------------------------
# exp_d -- e^x via Taylor series with range reduction
# ---------------------------------------------------------------------------


def exp_d(x: Decimal) -> Decimal:
    """Compute exp(x) for arbitrary Decimal x.

    Algorithm
    ---------
    1. Range reduction: write x = k * ln2 + r where |r| <= ln2/2.
       Then exp(x) = 2^k * exp(r).
    2. Taylor series for exp(r) converges rapidly since |r| < 0.35.
    3. 2^k is exact integer arithmetic.

    This avoids large-argument convergence problems.
    """
    with localcontext(ATTESTOR_DECIMAL_CONTEXT) as ctx:
        ctx.prec = _INTERNAL_PREC

        if x == _ZERO:
            return _ONE

        # ln(2) to internal precision
        ln2 = _ln2_const(ctx.prec)

        # Range reduction: k = round(x / ln2), r = x - k*ln2
        k_exact = x / ln2
        # Round to nearest integer
        k = int(k_exact.to_integral_value())
        r = x - Decimal(k) * ln2

        # Taylor series for exp(r): sum_{n=0}^{inf} r^n / n!
        exp_r = _ONE
        term = _ONE
        for n in range(1, 200):
            term = term * r / Decimal(n)
            exp_r = exp_r + term
            if abs(term) < Decimal(10) ** (-(ctx.prec + 2)):
                break

        # 2^k: split into positive/negative cases for exact computation
        result = exp_r * (_TWO ** k) if k >= 0 else exp_r / (_TWO ** (-k))

        return _to_output(result)


# ---------------------------------------------------------------------------
# ln_d -- natural logarithm via range reduction + series
# ---------------------------------------------------------------------------

def _ln2_const(prec: int) -> Decimal:
    """Compute ln(2) to the given precision using the series ln(2) = sum_{k=1}^{inf} (-1)^{k+1}/k.

    Actually uses the much faster identity:
        ln(2) = 18*_atanh_recip(26) - 2*_atanh_recip(4801) + 8*_atanh_recip(8749)
    But for simplicity we use the AGM-free series:
        ln(2) = sum_{k=0}^{inf} 1/((2k+1) * 9^(2k+1)) * 2  (via atanh(1/3))
    Actually, ln(2) = 2 * atanh(1/3) where atanh(x) = sum x^(2k+1)/(2k+1).
    """
    with localcontext(ATTESTOR_DECIMAL_CONTEXT) as ctx:
        ctx.prec = prec + 5
        # ln(2) = 2 * atanh(1/3)
        # atanh(1/3) = 1/3 + 1/(3*3^3) + 1/(5*3^5) + ...
        third = _ONE / Decimal(3)
        third_sq = third * third
        term = third
        result = third
        for k in range(1, 300):
            term = term * third_sq
            contrib = term / Decimal(2 * k + 1)
            result = result + contrib
            if abs(contrib) < Decimal(10) ** (-(ctx.prec + 2)):
                break
        return result * _TWO


def ln_d(x: Decimal) -> Decimal:
    """Compute ln(x) for positive Decimal x.

    Raises
    ------
    ValueError
        If x <= 0.

    Algorithm
    ---------
    1. Reject non-positive inputs.
    2. Range reduction: write x = m * 2^e where 0.5 <= m < 2.
       Then ln(x) = ln(m) + e * ln(2).
    3. For m near 1, use the series:
       ln(m) = 2 * atanh((m-1)/(m+1))
       atanh(u) = u + u^3/3 + u^5/5 + ...
       This converges fast since |(m-1)/(m+1)| < 1/3.
    """
    if x <= _ZERO:
        raise ValueError(f"ln_d requires x > 0, got {x}")

    if x == _ONE:
        return _ZERO

    with localcontext(ATTESTOR_DECIMAL_CONTEXT) as ctx:
        ctx.prec = _INTERNAL_PREC

        # Range reduction: extract exponent and significand.
        # Write x = significand * 10^exp where 1 <= significand < 10.
        # Then further reduce using powers of 2.
        #
        # Simpler approach: repeatedly multiply/divide by 2 to bring into [0.5, 2).
        val = x + _ZERO  # copy into current context
        e = 0
        while val >= _TWO:
            val = val / _TWO
            e += 1
        while val < _HALF:
            val = val * _TWO
            e -= 1

        # Now 0.5 <= val < 2, compute ln(val) via atanh series.
        # ln(val) = 2 * atanh((val - 1) / (val + 1))
        u = (val - _ONE) / (val + _ONE)  # |u| < 1/3 since 0.5 <= val < 2
        u_sq = u * u
        term = u
        ln_val = u
        for k in range(1, 300):
            term = term * u_sq
            contrib = term / Decimal(2 * k + 1)
            ln_val = ln_val + contrib
            if abs(contrib) < Decimal(10) ** (-(ctx.prec + 2)):
                break
        ln_val = ln_val * _TWO

        # ln(x) = ln(val) + e * ln(2)
        ln2 = _ln2_const(ctx.prec)
        result = ln_val + Decimal(e) * ln2

        return _to_output(result)


# ---------------------------------------------------------------------------
# sqrt_d -- square root
# ---------------------------------------------------------------------------


def sqrt_d(x: Decimal) -> Decimal:
    """Compute sqrt(x) using Decimal.sqrt() in ATTESTOR_DECIMAL_CONTEXT.

    Raises
    ------
    ValueError
        If x < 0 (Decimal.sqrt raises InvalidOperation for negative inputs;
        we convert to ValueError for a uniform error interface).
    """
    if x < _ZERO:
        raise ValueError(f"sqrt_d requires x >= 0, got {x}")
    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        return x.sqrt()


# ---------------------------------------------------------------------------
# expm1_neg_d -- 1 - exp(-x) without subtractive cancellation
# ---------------------------------------------------------------------------


def expm1_neg_d(x: Decimal) -> Decimal:
    """Compute 1 - exp(-x) without subtractive cancellation for small x.

    For |x| < 1, uses the Taylor series directly:
        1 - exp(-x) = x - x^2/2! + x^3/3! - x^4/4! + ...

    For larger |x|, computes 1 - exp(-x) directly since cancellation
    is not significant.

    This is important in discounting: D(t) = exp(-r*t), and
    1 - D(t) = expm1_neg_d(r*t) avoids losing precision when r*t is small.
    """
    with localcontext(ATTESTOR_DECIMAL_CONTEXT) as ctx:
        ctx.prec = _INTERNAL_PREC

        if x == _ZERO:
            return _ZERO

        # For small |x|, use the direct Taylor series to avoid cancellation.
        # 1 - exp(-x) = sum_{n=1}^{inf} (-1)^{n+1} * x^n / n!
        #             = x - x^2/2 + x^3/6 - x^4/24 + ...
        abs_x = abs(x)
        if abs_x < Decimal("1"):
            # Taylor series: 1 - exp(-x) = sum_{n=1}^{inf} (-1)^{n+1} * x^n / n!
            neg_x = -x
            term = neg_x  # (-x)^1 / 1!
            total = -term  # first term contributes +x (we want 1 - exp(-x))
            # Rewrite: exp(-x) = sum_{n=0} (-x)^n/n!
            # 1 - exp(-x) = -sum_{n=1} (-x)^n/n! = sum_{n=1} -(-x)^n/n!
            #             = sum_{n=1} (-1)^{n+1} x^n / n!
            total = _ZERO
            term = _ONE
            for n in range(1, 200):
                term = term * neg_x / Decimal(n)
                total = total - term  # total = -sum_{k=1..n} (-x)^k/k!
                if abs(term) < Decimal(10) ** (-(ctx.prec + 2)):
                    break
            return _to_output(total)

        # For larger |x|, direct computation is fine.
        exp_neg_x = _ONE
        neg_x = -x
        term = _ONE
        for n in range(1, 200):
            term = term * neg_x / Decimal(n)
            exp_neg_x = exp_neg_x + term
            if abs(term) < Decimal(10) ** (-(ctx.prec + 2)):
                break
        result = _ONE - exp_neg_x
        return _to_output(result)
