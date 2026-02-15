"""Money, Decimal context, and refined numeric/string types.

All financial arithmetic uses ATTESTOR_DECIMAL_CONTEXT with prec=28,
ROUND_HALF_EVEN, and traps for InvalidOperation/DivisionByZero/Overflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN as _ROUND_HALF_EVEN
from decimal import (
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)
from typing import final

from attestor.core.result import Err, Ok

ATTESTOR_DECIMAL_CONTEXT = Context(
    prec=28,
    rounding=_ROUND_HALF_EVEN,
    Emin=-999999,
    Emax=999999,
    capitals=1,
    clamp=0,
    flags=[],
    traps=[InvalidOperation, DivisionByZero, Overflow],
)


# --- Refined types ---


@final
@dataclass(frozen=True, slots=True)
class PositiveDecimal:
    """Decimal constrained to be > 0."""

    value: Decimal

    @staticmethod
    def parse(raw: Decimal) -> Ok[PositiveDecimal] | Err[str]:
        if not isinstance(raw, Decimal):
            return Err(f"PositiveDecimal requires Decimal, got {type(raw).__name__}")
        if raw <= 0:
            return Err(f"PositiveDecimal requires > 0, got {raw}")
        return Ok(PositiveDecimal(value=raw))


@final
@dataclass(frozen=True, slots=True)
class NonZeroDecimal:
    """Decimal constrained to be != 0."""

    value: Decimal

    @staticmethod
    def parse(raw: Decimal) -> Ok[NonZeroDecimal] | Err[str]:
        if not isinstance(raw, Decimal):
            return Err(f"NonZeroDecimal requires Decimal, got {type(raw).__name__}")
        if raw == 0:
            return Err("NonZeroDecimal requires != 0")
        return Ok(NonZeroDecimal(value=raw))


@final
@dataclass(frozen=True, slots=True)
class NonEmptyStr:
    """String constrained to be non-empty."""

    value: str

    @staticmethod
    def parse(raw: str) -> Ok[NonEmptyStr] | Err[str]:
        if not raw:
            return Err("NonEmptyStr requires non-empty string")
        return Ok(NonEmptyStr(value=raw))


# GAP-28: ISO 4217 minor unit lookup (subset for Phase 0)
_ISO4217_MINOR_UNITS: dict[str, int] = {
    "USD": 2, "EUR": 2, "GBP": 2, "CHF": 2, "CAD": 2, "AUD": 2, "SEK": 2,
    "JPY": 0, "KRW": 0,
    "BHD": 3, "KWD": 3, "OMR": 3,
    "BTC": 8, "ETH": 18,
}


@final
@dataclass(frozen=True, slots=True)
class Money:
    """Immutable monetary amount with currency. All arithmetic uses ATTESTOR_DECIMAL_CONTEXT."""

    amount: Decimal
    currency: NonEmptyStr

    @staticmethod
    def create(amount: Decimal, currency: str) -> Ok[Money] | Err[str]:
        """Create Money, rejecting non-Decimal, NaN, and Infinity (GAP-26)."""
        if not isinstance(amount, Decimal):
            return Err(f"Money.amount must be Decimal, got {type(amount).__name__}")
        if not amount.is_finite():
            return Err(f"Money.amount must be finite, got {amount}")
        match NonEmptyStr.parse(currency):
            case Err(e):
                return Err(f"Money.currency: {e}")
            case Ok(c):
                return Ok(Money(amount=amount, currency=c))

    def add(self, other: Money) -> Ok[Money] | Err[str]:
        """Add two Money values. Err if currencies differ. GAP-02: uses localcontext."""
        if self.currency != other.currency:
            return Err(f"Currency mismatch: {self.currency} vs {other.currency}")
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            return Ok(Money(amount=self.amount + other.amount, currency=self.currency))

    def sub(self, other: Money) -> Ok[Money] | Err[str]:
        """Subtract. Err if currencies differ. GAP-02: uses localcontext."""
        if self.currency != other.currency:
            return Err(f"Currency mismatch: {self.currency} vs {other.currency}")
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            return Ok(Money(amount=self.amount - other.amount, currency=self.currency))

    def mul(self, factor: Decimal) -> Money:
        """Scalar multiplication. Currency preserved. GAP-02: uses localcontext."""
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            return Money(amount=self.amount * factor, currency=self.currency)

    def negate(self) -> Money:
        """Flip sign. Currency preserved."""
        return Money(amount=-self.amount, currency=self.currency)

    def div(self, divisor: NonZeroDecimal) -> Money:
        """Scalar division (GAP-27). Currency preserved. GAP-02: uses localcontext."""
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            return Money(amount=self.amount / divisor.value, currency=self.currency)

    def round_to_minor_unit(self) -> Money:
        """Quantize to ISO 4217 minor unit (GAP-28). Defaults to 2 decimal places."""
        minor_units = _ISO4217_MINOR_UNITS.get(self.currency.value, 2)
        quantizer = Decimal(10) ** -minor_units
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            rounded = self.amount.quantize(quantizer)
        return Money(amount=rounded, currency=self.currency)
