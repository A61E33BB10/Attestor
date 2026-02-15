"""Validated identifier newtypes: LEI, UTI, ISIN.

Each wraps a string validated at construction time via parse().
ISIN check digit uses the Luhn algorithm over letter-to-digit expansion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import final

from attestor.core.result import Err, Ok


@final
@dataclass(frozen=True, slots=True)
class LEI:
    """Legal Entity Identifier — exactly 20 alphanumeric characters."""

    value: str

    @staticmethod
    def parse(raw: str) -> Ok[LEI] | Err[str]:
        if len(raw) != 20:
            return Err(f"LEI must be 20 characters, got {len(raw)}")
        if not raw.isalnum():
            return Err(f"LEI must be alphanumeric, got '{raw}'")
        return Ok(LEI(value=raw))


@final
@dataclass(frozen=True, slots=True)
class UTI:
    """Unique Transaction Identifier — 1-52 chars, first 20 alphanumeric."""

    value: str

    @staticmethod
    def parse(raw: str) -> Ok[UTI] | Err[str]:
        if not raw:
            return Err("UTI must be non-empty")
        if len(raw) > 52:
            return Err(f"UTI must be at most 52 characters, got {len(raw)}")
        prefix = raw[:20]
        if not prefix.isalnum():
            return Err(f"UTI first 20 chars must be alphanumeric, got '{prefix}'")
        return Ok(UTI(value=raw))


def _isin_luhn_check(isin: str) -> bool:
    """Luhn check for ISIN: expand letters to digits, then standard Luhn."""
    # Step 1: expand each char to digits (A=10, B=11, ..., Z=35)
    digits_str = ""
    for c in isin:
        if c.isdigit():
            digits_str += c
        else:
            digits_str += str(ord(c) - ord("A") + 10)

    # Step 2: standard Luhn on the resulting digit string
    digits = [int(d) for d in digits_str]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


@final
@dataclass(frozen=True, slots=True)
class ISIN:
    """International Securities Identification Number — 12 chars with Luhn check."""

    value: str

    @staticmethod
    def parse(raw: str) -> Ok[ISIN] | Err[str]:
        if len(raw) != 12:
            return Err(f"ISIN must be 12 characters, got {len(raw)}")
        country = raw[:2]
        if not country.isalpha() or not country.isupper():
            return Err(f"ISIN country code must be 2 uppercase letters, got '{country}'")
        body = raw[2:11]
        if not body.isalnum():
            return Err(f"ISIN body must be alphanumeric, got '{body}'")
        if not raw[11].isdigit():
            return Err(f"ISIN check digit must be numeric, got '{raw[11]}'")
        if not _isin_luhn_check(raw):
            return Err(f"ISIN check digit invalid for '{raw}'")
        return Ok(ISIN(value=raw))
