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


# GAP-28: ISO 4217 minor unit lookup
# Phase A: expanded to full ISO 4217 active currency codes.
_ISO4217_MINOR_UNITS: dict[str, int] = {
    # 0 decimal places
    "BIF": 0, "CLP": 0, "DJF": 0, "GNF": 0, "ISK": 0, "JPY": 0,
    "KMF": 0, "KRW": 0, "PYG": 0, "RWF": 0, "UGX": 0, "UYI": 0,
    "VND": 0, "VUV": 0, "XAF": 0, "XOF": 0, "XPF": 0,
    # 2 decimal places (most common)
    "AED": 2, "AFN": 2, "ALL": 2, "AMD": 2, "ANG": 2, "AOA": 2,
    "ARS": 2, "AUD": 2, "AWG": 2, "AZN": 2, "BAM": 2, "BBD": 2,
    "BDT": 2, "BGN": 2, "BMD": 2, "BND": 2, "BOB": 2, "BRL": 2,
    "BSD": 2, "BTN": 2, "BWP": 2, "BYN": 2, "BZD": 2, "CAD": 2,
    "CDF": 2, "CHF": 2, "CNY": 2, "COP": 2, "CRC": 2, "CUP": 2,
    "CVE": 2, "CZK": 2, "DKK": 2, "DOP": 2, "DZD": 2, "EGP": 2,
    "ERN": 2, "ETB": 2, "EUR": 2, "FJD": 2, "FKP": 2, "GBP": 2,
    "GEL": 2, "GHS": 2, "GIP": 2, "GMD": 2, "GTQ": 2, "GYD": 2,
    "HKD": 2, "HNL": 2, "HTG": 2, "HUF": 2, "IDR": 2, "ILS": 2,
    "INR": 2, "IQD": 2, "IRR": 2, "JMD": 2, "JOD": 2, "KES": 2,
    "KGS": 2, "KHR": 2, "KYD": 2, "KZT": 2, "LAK": 2, "LBP": 2,
    "LKR": 2, "LRD": 2, "LSL": 2, "LYD": 2, "MAD": 2, "MDL": 2,
    "MGA": 2, "MKD": 2, "MMK": 2, "MNT": 2, "MOP": 2, "MRU": 2,
    "MUR": 2, "MVR": 2, "MWK": 2, "MXN": 2, "MYR": 2, "MZN": 2,
    "NAD": 2, "NGN": 2, "NIO": 2, "NOK": 2, "NPR": 2, "NZD": 2,
    "PAB": 2, "PEN": 2, "PGK": 2, "PHP": 2, "PKR": 2, "PLN": 2,
    "QAR": 2, "RON": 2, "RSD": 2, "RUB": 2, "SAR": 2, "SBD": 2,
    "SCR": 2, "SDG": 2, "SEK": 2, "SGD": 2, "SHP": 2, "SLE": 2,
    "SOS": 2, "SRD": 2, "SSP": 2, "STN": 2, "SVC": 2, "SYP": 2,
    "SZL": 2, "THB": 2, "TJS": 2, "TMT": 2, "TND": 2, "TOP": 2,
    "TRY": 2, "TTD": 2, "TWD": 2, "TZS": 2, "UAH": 2, "USD": 2,
    "UYU": 2, "UZS": 2, "VES": 2, "WST": 2, "XCD": 2, "YER": 2,
    "ZAR": 2, "ZMW": 2, "ZWL": 2,
    # 3 decimal places
    "BHD": 3, "KWD": 3, "OMR": 3,
    # Crypto (non-ISO but supported)
    "BTC": 8, "ETH": 18,
}

# Phase A: full ISO 4217 — all active currency codes.
VALID_CURRENCIES: frozenset[str] = frozenset(_ISO4217_MINOR_UNITS.keys())


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
