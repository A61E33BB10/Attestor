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

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal) or not (self.value > 0):
            raise TypeError(f"PositiveDecimal requires Decimal > 0, got {self.value!r}")

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

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal) or self.value == 0:
            raise TypeError(f"NonZeroDecimal requires Decimal != 0, got {self.value!r}")

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

    def __post_init__(self) -> None:
        if not self.value:
            raise TypeError("NonEmptyStr requires non-empty string")

    @staticmethod
    def parse(raw: str) -> Ok[NonEmptyStr] | Err[str]:
        if not raw:
            return Err("NonEmptyStr requires non-empty string")
        return Ok(NonEmptyStr(value=raw))


@final
@dataclass(frozen=True, slots=True)
class NonNegativeDecimal:
    """Decimal constrained to be >= 0."""

    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal) or self.value < 0:
            raise TypeError(f"NonNegativeDecimal requires Decimal >= 0, got {self.value!r}")

    @staticmethod
    def parse(raw: Decimal) -> Ok[NonNegativeDecimal] | Err[str]:
        if not isinstance(raw, Decimal):
            return Err(f"NonNegativeDecimal requires Decimal, got {type(raw).__name__}")
        if raw < 0:
            return Err(f"NonNegativeDecimal requires >= 0, got {raw}")
        return Ok(NonNegativeDecimal(value=raw))


# GAP-28: ISO 4217 minor unit lookup (subset for Phase 0)
_ISO4217_MINOR_UNITS: dict[str, int] = {
    "USD": 2, "EUR": 2, "GBP": 2, "CHF": 2, "CAD": 2, "AUD": 2, "SEK": 2,
    "JPY": 0, "KRW": 0,
    "BHD": 3, "KWD": 3, "OMR": 3,
    "BTC": 8, "ETH": 18,
}

# Gatheral Phase 1 finding: validate currency codes
VALID_CURRENCIES: frozenset[str] = frozenset(_ISO4217_MINOR_UNITS.keys()) | frozenset({
    "HKD", "SGD", "NZD", "NOK", "DKK", "ZAR", "MXN", "BRL", "INR",
    "CNY", "TWD", "THB", "PLN", "CZK", "HUF", "TRY", "ILS", "KRW",
})


def validate_currency(code: str) -> bool:
    """Check if a currency code is in the known set."""
    return code in VALID_CURRENCIES


@final
@dataclass(frozen=True, slots=True)
class Money:
    """Immutable monetary amount with currency. All arithmetic uses ATTESTOR_DECIMAL_CONTEXT."""

    amount: Decimal
    currency: NonEmptyStr

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal) or not self.amount.is_finite():
            raise TypeError(f"Money.amount must be finite Decimal, got {self.amount!r}")

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

    def abs(self) -> Money:
        """Absolute value. Currency preserved."""
        return Money(amount=abs(self.amount), currency=self.currency)

    def round_to_minor_unit(self) -> Money:
        """Quantize to ISO 4217 minor unit (GAP-28). Defaults to 2 decimal places."""
        minor_units = _ISO4217_MINOR_UNITS.get(self.currency.value, 2)
        quantizer = Decimal(10) ** -minor_units
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            rounded = self.amount.quantize(quantizer)
        return Money(amount=rounded, currency=self.currency)


# ---------------------------------------------------------------------------
# CurrencyPair — validated FX pair (Phase 3)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class CurrencyPair:
    """Validated FX currency pair, e.g. EUR/USD (base/quote)."""

    base: NonEmptyStr
    quote: NonEmptyStr

    def __post_init__(self) -> None:
        if self.base.value == self.quote.value:
            raise TypeError(
                f"CurrencyPair base and quote must differ, "
                f"both are '{self.base.value}'"
            )

    @staticmethod
    def parse(raw: str) -> Ok[CurrencyPair] | Err[str]:
        """Parse 'BASE/QUOTE' string into CurrencyPair."""
        parts = raw.split("/")
        if len(parts) != 2:
            return Err(f"CurrencyPair must be BASE/QUOTE, got '{raw}'")
        base_str, quote_str = parts[0].strip(), parts[1].strip()
        if not validate_currency(base_str):
            return Err(f"Invalid base currency: {base_str}")
        if not validate_currency(quote_str):
            return Err(f"Invalid quote currency: {quote_str}")
        if base_str == quote_str:
            return Err(f"Base and quote must differ: {base_str}")
        match NonEmptyStr.parse(base_str):
            case Err(e):
                return Err(f"CurrencyPair.base: {e}")
            case Ok(b):
                pass
        match NonEmptyStr.parse(quote_str):
            case Err(e):
                return Err(f"CurrencyPair.quote: {e}")
            case Ok(q):
                pass
        return Ok(CurrencyPair(base=b, quote=q))

    @property
    def value(self) -> str:
        """String representation: BASE/QUOTE."""
        return f"{self.base.value}/{self.quote.value}"
