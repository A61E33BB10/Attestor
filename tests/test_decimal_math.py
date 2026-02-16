"""Tests for attestor.core.decimal_math -- pure-Decimal exp, ln, sqrt, expm1_neg."""

from __future__ import annotations

from decimal import Decimal, localcontext

import pytest

from attestor.core.decimal_math import exp_d, expm1_neg_d, ln_d, sqrt_d
from attestor.core.money import ATTESTOR_DECIMAL_CONTEXT

# ---------------------------------------------------------------------------
# Reference constants (computed to > 28 significant digits)
# ---------------------------------------------------------------------------

# e = 2.71828182845904523536028747135...
_E = Decimal("2.7182818284590452353602874714")
# 1/e = 0.36787944117144232159552377016...
_INV_E = Decimal("0.3678794411714423215955237702")
# ln(2) = 0.69314718055994530941723212145...
_LN2 = Decimal("0.6931471805599453094172321215")
# sqrt(2) = 1.41421356237309504880168872421...
_SQRT2 = Decimal("1.414213562373095048801688724")
# e^50 = 5184705528587072464087.4533229...
_E50 = Decimal("5184705528587072464087.453323")
# e^(-10) = 0.0000453999297624848515...
_E_NEG10 = Decimal("0.00004539992976248485153559152")


def _ulp_28() -> Decimal:
    """One unit in the last place for 28-digit precision near magnitude 1."""
    return Decimal("1e-27")


# ---------------------------------------------------------------------------
# exp_d tests
# ---------------------------------------------------------------------------


class TestExpD:
    def test_exp_zero_is_one(self) -> None:
        assert exp_d(Decimal("0")) == Decimal("1")

    def test_exp_one_matches_e(self) -> None:
        result = exp_d(Decimal("1"))
        diff = abs(result - _E)
        # Within 1 ULP at prec=28 (last digit may differ by rounding)
        assert diff <= _ulp_28(), f"exp(1) off by {diff}"

    def test_exp_negative_one_matches_inv_e(self) -> None:
        result = exp_d(Decimal("-1"))
        diff = abs(result - _INV_E)
        assert diff <= _ulp_28(), f"exp(-1) off by {diff}"

    def test_exp_large_argument_range_reduction(self) -> None:
        """exp(50) exercises range reduction (50/ln2 ~ 72 halvings)."""
        result = exp_d(Decimal("50"))
        diff = abs(result - _E50)
        # For a 22-digit integer part, 1 ULP at prec=28 is ~1e(22-28)=1e-6
        relative = diff / _E50
        assert relative < Decimal("1e-26"), f"exp(50) relative error {relative}"

    def test_exp_negative_large(self) -> None:
        """exp(-10) is a small positive number."""
        result = exp_d(Decimal("-10"))
        diff = abs(result - _E_NEG10)
        assert diff <= _ulp_28() * Decimal("10"), f"exp(-10) off by {diff}"

    def test_exp_small_positive(self) -> None:
        """exp(1e-10) ~ 1 + 1e-10 + 5e-21 + ..."""
        result = exp_d(Decimal("1e-10"))
        expected = Decimal("1.000000000100000000005000000")
        diff = abs(result - expected)
        assert diff <= _ulp_28() * Decimal("10"), f"exp(1e-10) off by {diff}"

    def test_exp_returns_decimal(self) -> None:
        result = exp_d(Decimal("1"))
        assert isinstance(result, Decimal)

    def test_exp_no_float_internally(self) -> None:
        """Verify output is Decimal, not a float-derived approximation."""
        result = exp_d(Decimal("1"))
        # A float-derived Decimal would have a long non-repeating representation.
        # Our result should have exactly 28 significant digits (the context precision).
        assert isinstance(result, Decimal)
        # The adjusted exponent + number of digits should equal precision
        digits = len(result.as_tuple().digits)
        assert digits <= ATTESTOR_DECIMAL_CONTEXT.prec


# ---------------------------------------------------------------------------
# ln_d tests
# ---------------------------------------------------------------------------


class TestLnD:
    def test_ln_one_is_zero(self) -> None:
        assert ln_d(Decimal("1")) == Decimal("0")

    def test_ln_e_is_one(self) -> None:
        """ln(e) == 1 to 27+ digits."""
        result = ln_d(_E)
        diff = abs(result - Decimal("1"))
        # The input _E itself has 28-digit precision, so round-trip loses ~1 ULP
        assert diff <= _ulp_28() * Decimal("10"), f"ln(e) off by {diff}"

    def test_ln_two_matches_known(self) -> None:
        result = ln_d(Decimal("2"))
        diff = abs(result - _LN2)
        assert diff <= _ulp_28(), f"ln(2) off by {diff}"

    def test_ln_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="requires x > 0"):
            ln_d(Decimal("0"))

    def test_ln_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="requires x > 0"):
            ln_d(Decimal("-5"))

    def test_ln_large_value(self) -> None:
        """ln(1000) = 3 * ln(10) ~ 6.9077..."""
        result = ln_d(Decimal("1000"))
        # ln(1000) = 6.9077552789821370520539743640...
        expected = Decimal("6.907755278982137052053974364")
        diff = abs(result - expected)
        assert diff <= _ulp_28() * Decimal("10"), f"ln(1000) off by {diff}"

    def test_ln_small_value(self) -> None:
        """ln(0.001) = -ln(1000)."""
        result = ln_d(Decimal("0.001"))
        expected = -Decimal("6.907755278982137052053974364")
        diff = abs(result - expected)
        assert diff <= _ulp_28() * Decimal("10"), f"ln(0.001) off by {diff}"


# ---------------------------------------------------------------------------
# Round-trip tests: ln(exp(x)) == x and exp(ln(x)) == x
# ---------------------------------------------------------------------------


class TestRoundTrips:
    @pytest.mark.parametrize("x", [
        Decimal("0"), Decimal("1"), Decimal("-1"),
        Decimal("3.7"), Decimal("0.001"), Decimal("10"),
    ])
    def test_ln_exp_round_trip(self, x: Decimal) -> None:
        """ln(exp(x)) == x to within a few ULP."""
        if x == Decimal("0"):
            # ln(exp(0)) = ln(1) = 0 exactly
            assert ln_d(exp_d(x)) == Decimal("0")
            return
        result = ln_d(exp_d(x))
        diff = abs(result - x)
        # Allow a few ULP relative to |x|
        tolerance = max(abs(x), Decimal("1")) * Decimal("1e-25")
        assert diff < tolerance, f"ln(exp({x})) off by {diff}"

    @pytest.mark.parametrize("x", [
        Decimal("0.25"), Decimal("1"), Decimal("2.5"),
        Decimal("100"), Decimal("0.01"),
    ])
    def test_exp_ln_round_trip(self, x: Decimal) -> None:
        """exp(ln(x)) == x to within a few ULP."""
        if x == Decimal("1"):
            assert exp_d(ln_d(x)) == Decimal("1")
            return
        result = exp_d(ln_d(x))
        diff = abs(result - x)
        tolerance = max(x, Decimal("1")) * Decimal("1e-25")
        assert diff < tolerance, f"exp(ln({x})) off by {diff}"


# ---------------------------------------------------------------------------
# sqrt_d tests
# ---------------------------------------------------------------------------


class TestSqrtD:
    def test_sqrt_four_is_two(self) -> None:
        assert sqrt_d(Decimal("4")) == Decimal("2")

    def test_sqrt_one_is_one(self) -> None:
        assert sqrt_d(Decimal("1")) == Decimal("1")

    def test_sqrt_zero_is_zero(self) -> None:
        assert sqrt_d(Decimal("0")) == Decimal("0")

    def test_sqrt_two_matches_known(self) -> None:
        result = sqrt_d(Decimal("2"))
        diff = abs(result - _SQRT2)
        assert diff <= _ulp_28(), f"sqrt(2) off by {diff}"

    def test_sqrt_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="requires x >= 0"):
            sqrt_d(Decimal("-1"))

    def test_sqrt_uses_attestor_context(self) -> None:
        """Even with a different thread-local context, uses ATTESTOR_DECIMAL_CONTEXT."""
        with localcontext() as ctx:
            ctx.prec = 3  # deliberately low
            result = sqrt_d(Decimal("2"))
            # Should still have full precision, not 3 digits
            assert len(result.as_tuple().digits) > 3


# ---------------------------------------------------------------------------
# expm1_neg_d tests
# ---------------------------------------------------------------------------


class TestExpm1NegD:
    def test_zero_gives_zero(self) -> None:
        assert expm1_neg_d(Decimal("0")) == Decimal("0")

    def test_small_argument_precision(self) -> None:
        """For x = 1e-10, 1 - exp(-x) ~ x - x^2/2.

        Naive 1 - exp(-1e-10) would lose all significant digits due to
        catastrophic cancellation. expm1_neg_d preserves them.
        """
        x = Decimal("1e-10")
        result = expm1_neg_d(x)
        # 1 - exp(-1e-10) = 1e-10 - 5e-21 + 1.667e-31 - ...
        expected = Decimal("9.999999999500000000016666667E-11")
        diff = abs(result - expected)
        # The result should match to ~27 significant digits
        assert diff < Decimal("1e-37"), f"expm1_neg(-1e-10) off by {diff}"

    def test_large_argument(self) -> None:
        """For large x, 1 - exp(-x) ~ 1."""
        x = Decimal("50")
        result = expm1_neg_d(x)
        # 1 - exp(-50) is very close to 1
        assert result > Decimal("0.999999999999999")
        assert result < Decimal("1")

    def test_moderate_argument(self) -> None:
        """1 - exp(-1) = 1 - 1/e."""
        result = expm1_neg_d(Decimal("1"))
        expected = Decimal("1") - _INV_E
        diff = abs(result - expected)
        assert diff <= _ulp_28() * Decimal("10"), f"expm1_neg(1) off by {diff}"

    def test_negative_argument(self) -> None:
        """expm1_neg_d(-1) = 1 - exp(1) = 1 - e < 0."""
        result = expm1_neg_d(Decimal("-1"))
        expected = Decimal("1") - _E
        diff = abs(result - expected)
        assert diff <= _ulp_28() * Decimal("100"), f"expm1_neg(-1) off by {diff}"

    def test_consistency_with_exp_d(self) -> None:
        """For moderate x, expm1_neg_d(x) == 1 - exp_d(-x) to high precision."""
        for x in [Decimal("0.5"), Decimal("2"), Decimal("7")]:
            via_expm1 = expm1_neg_d(x)
            via_exp = Decimal("1") - exp_d(-x)
            diff = abs(via_expm1 - via_exp)
            tolerance = _ulp_28() * Decimal("100")
            assert diff < tolerance, (
                f"expm1_neg_d({x}) vs 1-exp_d(-{x}): diff={diff}"
            )


# ---------------------------------------------------------------------------
# Context isolation: all functions use ATTESTOR_DECIMAL_CONTEXT
# ---------------------------------------------------------------------------


class TestContextIsolation:
    def test_exp_ignores_thread_local_context(self) -> None:
        """exp_d uses ATTESTOR_DECIMAL_CONTEXT even when thread-local prec is low."""
        with localcontext() as ctx:
            ctx.prec = 3
            result = exp_d(Decimal("1"))
            digits = len(result.as_tuple().digits)
            assert digits >= 20, f"Only got {digits} digits -- leaked thread-local context?"

    def test_ln_ignores_thread_local_context(self) -> None:
        with localcontext() as ctx:
            ctx.prec = 3
            result = ln_d(Decimal("2"))
            digits = len(result.as_tuple().digits)
            assert digits >= 20, f"Only got {digits} digits -- leaked thread-local context?"
