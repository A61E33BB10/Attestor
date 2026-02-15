"""Tests for attestor.core.money — Decimal context, refined types, Money."""

from __future__ import annotations

import dataclasses
from decimal import ROUND_HALF_EVEN, Decimal, getcontext, localcontext

import pytest
from hypothesis import given
from hypothesis import strategies as st

from attestor.core.money import (
    ATTESTOR_DECIMAL_CONTEXT,
    Money,
    NonEmptyStr,
    NonZeroDecimal,
    PositiveDecimal,
)
from attestor.core.result import Err, Ok, unwrap

# ---------------------------------------------------------------------------
# ATTESTOR_DECIMAL_CONTEXT
# ---------------------------------------------------------------------------


class TestDecimalContext:
    def test_precision_is_28(self) -> None:
        assert ATTESTOR_DECIMAL_CONTEXT.prec == 28

    def test_rounding_is_half_even(self) -> None:
        assert ATTESTOR_DECIMAL_CONTEXT.rounding == ROUND_HALF_EVEN

    def test_traps_invalid_operation(self) -> None:
        with localcontext(ATTESTOR_DECIMAL_CONTEXT), pytest.raises(Exception):  # noqa: B017
            Decimal(0) / Decimal(0)  # 0/0 is undefined

    def test_traps_division_by_zero(self) -> None:
        with localcontext(ATTESTOR_DECIMAL_CONTEXT), pytest.raises(Exception):  # noqa: B017
            Decimal("1") / Decimal("0")

    def test_traps_overflow(self) -> None:
        with localcontext(ATTESTOR_DECIMAL_CONTEXT), pytest.raises(Exception):  # noqa: B017
            Decimal("9e999999") * Decimal("9e999999")


# ---------------------------------------------------------------------------
# PositiveDecimal
# ---------------------------------------------------------------------------


class TestPositiveDecimal:
    def test_parse_positive(self) -> None:
        result = PositiveDecimal.parse(Decimal("1.5"))
        assert isinstance(result, Ok)
        assert unwrap(result).value == Decimal("1.5")

    def test_parse_zero_err(self) -> None:
        assert isinstance(PositiveDecimal.parse(Decimal("0")), Err)

    def test_parse_negative_err(self) -> None:
        assert isinstance(PositiveDecimal.parse(Decimal("-1")), Err)

    def test_parse_non_decimal_err(self) -> None:
        assert isinstance(PositiveDecimal.parse(42), Err)  # type: ignore[arg-type]

    def test_frozen(self) -> None:
        pd = unwrap(PositiveDecimal.parse(Decimal("1")))
        with pytest.raises(dataclasses.FrozenInstanceError):
            pd.value = Decimal("2")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# NonZeroDecimal
# ---------------------------------------------------------------------------


class TestNonZeroDecimal:
    def test_parse_positive(self) -> None:
        result = NonZeroDecimal.parse(Decimal("5"))
        assert isinstance(result, Ok)

    def test_parse_negative(self) -> None:
        result = NonZeroDecimal.parse(Decimal("-3"))
        assert isinstance(result, Ok)

    def test_parse_zero_err(self) -> None:
        assert isinstance(NonZeroDecimal.parse(Decimal("0")), Err)

    def test_parse_non_decimal_err(self) -> None:
        assert isinstance(NonZeroDecimal.parse(0.5), Err)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# NonEmptyStr
# ---------------------------------------------------------------------------


class TestNonEmptyStr:
    def test_parse_nonempty(self) -> None:
        result = NonEmptyStr.parse("USD")
        assert isinstance(result, Ok)
        assert unwrap(result).value == "USD"

    def test_parse_empty_err(self) -> None:
        assert isinstance(NonEmptyStr.parse(""), Err)


# ---------------------------------------------------------------------------
# Money — creation
# ---------------------------------------------------------------------------


def _usd(amount: str) -> Money:
    """Helper to create USD Money from string amount."""
    return unwrap(Money.create(Decimal(amount), "USD"))


class TestMoneyCreate:
    def test_create_valid(self) -> None:
        result = Money.create(Decimal("100.50"), "USD")
        assert isinstance(result, Ok)
        m = unwrap(result)
        assert m.amount == Decimal("100.50")
        assert m.currency.value == "USD"

    def test_create_empty_currency_err(self) -> None:
        assert isinstance(Money.create(Decimal("1"), ""), Err)

    def test_create_non_decimal_err(self) -> None:
        assert isinstance(Money.create(100.0, "USD"), Err)  # type: ignore[arg-type]

    def test_amount_is_decimal_not_float(self) -> None:
        m = _usd("42")
        assert type(m.amount) is Decimal

    def test_frozen(self) -> None:
        m = _usd("1")
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.amount = Decimal("2")  # type: ignore[misc]


class TestMoneyNaN:
    """GAP-26: NaN and Infinity rejection."""

    def test_create_nan_err(self) -> None:
        assert isinstance(Money.create(Decimal("NaN"), "USD"), Err)

    def test_create_snan_err(self) -> None:
        assert isinstance(Money.create(Decimal("sNaN"), "USD"), Err)

    def test_create_infinity_err(self) -> None:
        assert isinstance(Money.create(Decimal("Infinity"), "USD"), Err)

    def test_create_neg_infinity_err(self) -> None:
        assert isinstance(Money.create(Decimal("-Infinity"), "USD"), Err)


# ---------------------------------------------------------------------------
# Money — arithmetic
# ---------------------------------------------------------------------------


class TestMoneyArithmetic:
    def test_add_same_currency(self) -> None:
        result = _usd("100").add(_usd("50"))
        assert isinstance(result, Ok)
        assert unwrap(result).amount == Decimal("150")

    def test_add_different_currency_err(self) -> None:
        eur = unwrap(Money.create(Decimal("50"), "EUR"))
        result = _usd("100").add(eur)
        assert isinstance(result, Err)

    def test_sub_same_currency(self) -> None:
        result = _usd("100").sub(_usd("30"))
        assert unwrap(result).amount == Decimal("70")

    def test_sub_different_currency_err(self) -> None:
        eur = unwrap(Money.create(Decimal("30"), "EUR"))
        assert isinstance(_usd("100").sub(eur), Err)

    def test_mul_by_decimal(self) -> None:
        m = _usd("10").mul(Decimal("3"))
        assert m.amount == Decimal("30")
        assert m.currency.value == "USD"

    def test_negate(self) -> None:
        m = _usd("42").negate()
        assert m.amount == Decimal("-42")
        assert m.currency.value == "USD"


class TestMoneyDiv:
    """GAP-27: scalar division."""

    def test_div_by_nonzero(self) -> None:
        divisor = unwrap(NonZeroDecimal.parse(Decimal("4")))
        result = _usd("100").div(divisor)
        assert result.amount == Decimal("25")

    def test_div_preserves_currency(self) -> None:
        divisor = unwrap(NonZeroDecimal.parse(Decimal("2")))
        result = _usd("50").div(divisor)
        assert result.currency.value == "USD"


class TestMoneyRound:
    """GAP-28: round_to_minor_unit."""

    def test_round_usd(self) -> None:
        m = _usd("1.005").round_to_minor_unit()
        assert m.amount == Decimal("1.00")  # banker's rounding: 0.005 -> 0.00

    def test_round_jpy(self) -> None:
        m = unwrap(Money.create(Decimal("100.5"), "JPY"))
        rounded = m.round_to_minor_unit()
        assert rounded.amount == Decimal("100")  # banker's rounding: 0.5 -> 0

    def test_round_bhd(self) -> None:
        m = unwrap(Money.create(Decimal("1.2345"), "BHD"))
        rounded = m.round_to_minor_unit()
        assert rounded.amount == Decimal("1.234")  # 3 decimal places

    def test_round_uses_half_even(self) -> None:
        """Banker's rounding: 0.5 rounds to even."""
        m1 = _usd("2.125").round_to_minor_unit()
        m2 = _usd("2.135").round_to_minor_unit()
        assert m1.amount == Decimal("2.12")  # round down to even
        assert m2.amount == Decimal("2.14")  # round up to even


class TestMoneyLocalContext:
    """GAP-02: Money arithmetic uses ATTESTOR_DECIMAL_CONTEXT, not thread-local context."""

    def test_add_uses_attestor_context(self) -> None:
        """Even with a different thread-local context, Money.add uses ATTESTOR_DECIMAL_CONTEXT."""
        original = getcontext().copy()
        try:
            getcontext().prec = 2  # deliberately low precision
            result = _usd("1.123456789").add(_usd("2.987654321"))
            m = unwrap(result)
            # If thread-local context were used, precision would be truncated
            assert m.amount == Decimal("4.111111110")
        finally:
            getcontext().prec = original.prec

    def test_sub_uses_attestor_context(self) -> None:
        original_prec = getcontext().prec
        try:
            getcontext().prec = 2
            result = _usd("1.123456789").sub(_usd("0.000000001"))
            m = unwrap(result)
            assert m.amount == Decimal("1.123456788")
        finally:
            getcontext().prec = original_prec

    def test_mul_uses_attestor_context(self) -> None:
        original_prec = getcontext().prec
        try:
            getcontext().prec = 2
            m = _usd("1.123456789").mul(Decimal("1.000000001"))
            # With prec=2, result would be truncated. With prec=28, it's precise.
            assert len(str(m.amount).replace(".", "").lstrip("0")) > 2
        finally:
            getcontext().prec = original_prec


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------


_money_amounts = st.decimals(
    min_value=Decimal("-1e12"),
    max_value=Decimal("1e12"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)


class TestMoneyAbs:
    def test_abs_positive(self) -> None:
        m = _usd("42.50")
        assert m.abs().amount == Decimal("42.50")

    def test_abs_negative(self) -> None:
        m = _usd("-42.50")
        assert m.abs().amount == Decimal("42.50")

    def test_abs_zero(self) -> None:
        m = _usd("0")
        assert m.abs().amount == Decimal("0")

    def test_abs_preserves_currency(self) -> None:
        m = _usd("-100")
        assert m.abs().currency == m.currency


class TestValidateCurrency:
    def test_valid_usd(self) -> None:
        from attestor.core.money import validate_currency
        assert validate_currency("USD") is True

    def test_valid_eur(self) -> None:
        from attestor.core.money import validate_currency
        assert validate_currency("EUR") is True

    def test_valid_hkd(self) -> None:
        from attestor.core.money import validate_currency
        assert validate_currency("HKD") is True

    def test_invalid_xxx(self) -> None:
        from attestor.core.money import validate_currency
        assert validate_currency("XXX") is False

    def test_invalid_empty(self) -> None:
        from attestor.core.money import validate_currency
        assert validate_currency("") is False


class TestMoneyProperties:
    @given(a=_money_amounts, b=_money_amounts)
    def test_add_commutativity(self, a: Decimal, b: Decimal) -> None:
        ma = _usd(str(a))
        mb = _usd(str(b))
        assert unwrap(ma.add(mb)).amount == unwrap(mb.add(ma)).amount

    @given(a=_money_amounts, b=_money_amounts, c=_money_amounts)
    def test_add_associativity(self, a: Decimal, b: Decimal, c: Decimal) -> None:
        ma, mb, mc = _usd(str(a)), _usd(str(b)), _usd(str(c))
        lhs = unwrap(unwrap(ma.add(mb)).add(mc)).amount
        rhs = unwrap(ma.add(unwrap(mb.add(mc)))).amount
        assert lhs == rhs

    @given(a=_money_amounts)
    def test_negate_involution(self, a: Decimal) -> None:
        m = _usd(str(a))
        assert m.negate().negate().amount == m.amount

    @given(a=_money_amounts)
    def test_add_negate_identity(self, a: Decimal) -> None:
        m = _usd(str(a))
        result = unwrap(m.add(m.negate()))
        assert result.amount == Decimal("0")

    @given(
        a=st.decimals(min_value=Decimal("-1e6"), max_value=Decimal("1e6"),
                      allow_nan=False, allow_infinity=False, places=2),
        b=st.decimals(min_value=Decimal("-1e6"), max_value=Decimal("1e6"),
                      allow_nan=False, allow_infinity=False, places=2),
        k=st.decimals(min_value=Decimal("-1e6"), max_value=Decimal("1e6"),
                      allow_nan=False, allow_infinity=False, places=2),
    )
    def test_mul_distributivity(self, a: Decimal, b: Decimal, k: Decimal) -> None:
        """k*(a+b) == k*a + k*b — holds when values are small enough for prec=28."""
        ma, mb = _usd(str(a)), _usd(str(b))
        lhs = unwrap(ma.add(mb)).mul(k).amount
        rhs = unwrap(ma.mul(k).add(mb.mul(k))).amount
        assert lhs == rhs
