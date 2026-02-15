"""Tests for attestor.core.serialization — canonical bytes and content hashing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

from hypothesis import given
from hypothesis import strategies as st

from attestor.core.result import Err, Ok, unwrap
from attestor.core.serialization import canonical_bytes, content_hash, derive_seed
from attestor.core.types import FrozenMap, UtcDatetime

# ---------------------------------------------------------------------------
# canonical_bytes — basic types
# ---------------------------------------------------------------------------


class TestCanonicalBytesBasic:
    def test_returns_result(self) -> None:
        assert isinstance(canonical_bytes(42), Ok)

    def test_none(self) -> None:
        assert unwrap(canonical_bytes(None)) == b"null"

    def test_bool_true(self) -> None:
        assert unwrap(canonical_bytes(True)) == b"true"

    def test_bool_false(self) -> None:
        assert unwrap(canonical_bytes(False)) == b"false"

    def test_int(self) -> None:
        assert unwrap(canonical_bytes(42)) == b"42"

    def test_string(self) -> None:
        assert unwrap(canonical_bytes("hello")) == b'"hello"'

    def test_tuple(self) -> None:
        assert unwrap(canonical_bytes((1, 2, 3))) == b"[1,2,3]"

    def test_list(self) -> None:
        assert unwrap(canonical_bytes([1, 2, 3])) == b"[1,2,3]"


class TestCanonicalBytesDecimal:
    def test_decimal_serialized_as_string(self) -> None:
        raw = unwrap(canonical_bytes(Decimal("1.5")))
        assert raw == b'"1.5"'

    def test_decimal_zero_canonical(self) -> None:
        """GAP-05: all zeros normalize to '0'."""
        a = unwrap(canonical_bytes(Decimal("0")))
        b = unwrap(canonical_bytes(Decimal("0E+2")))
        c = unwrap(canonical_bytes(Decimal("0.00")))
        assert a == b == c

    def test_decimal_zero_is_string_zero(self) -> None:
        raw = unwrap(canonical_bytes(Decimal("0")))
        assert raw == b'"0"'


class TestCanonicalBytesDatetime:
    def test_aware_datetime(self) -> None:
        dt = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
        raw = unwrap(canonical_bytes(dt))
        parsed = json.loads(raw)
        assert "2024-01-15" in parsed
        assert "12:00:00" in parsed

    def test_utc_datetime(self) -> None:
        utc = UtcDatetime.now()
        result = canonical_bytes(utc)
        assert isinstance(result, Ok)

    def test_naive_datetime_returns_err(self) -> None:
        """GAP-14: naive datetimes are rejected."""
        dt = datetime(2024, 1, 15, 12, 0)  # no tzinfo
        result = canonical_bytes(dt)
        assert isinstance(result, Err)


class TestCanonicalBytesFrozenMap:
    def test_frozen_map_sorted_keys(self) -> None:
        fm = unwrap(FrozenMap.create({"b": 2, "a": 1}))
        raw = unwrap(canonical_bytes(fm))
        parsed = json.loads(raw)
        assert list(parsed.keys()) == ["a", "b"]

    def test_dict_order_irrelevant(self) -> None:
        a = unwrap(canonical_bytes({"b": 2, "a": 1}))
        b = unwrap(canonical_bytes({"a": 1, "b": 2}))
        assert a == b


class TestCanonicalBytesDataclass:
    def test_frozen_dataclass_includes_type(self) -> None:
        @dataclass(frozen=True)
        class Point:
            x: int
            y: int

        raw = unwrap(canonical_bytes(Point(x=1, y=2)))
        parsed = json.loads(raw)
        assert parsed["_type"] == "Point"
        assert parsed["x"] == 1
        assert parsed["y"] == 2

    def test_frozen_dataclass_fields_sorted(self) -> None:
        @dataclass(frozen=True)
        class ZFirst:
            z: int
            a: int

        raw = unwrap(canonical_bytes(ZFirst(z=9, a=1)))
        parsed = json.loads(raw)
        keys = list(parsed.keys())
        # _type first, then sorted fields
        assert keys == ["_type", "a", "z"]


class TestCanonicalBytesEnum:
    def test_enum_value(self) -> None:
        class Color(Enum):
            RED = "red"
            BLUE = "blue"

        raw = unwrap(canonical_bytes(Color.RED))
        assert raw == b'"red"'


class TestCanonicalBytesUnsupported:
    def test_unsupported_type_returns_err(self) -> None:
        """GAP-04: returns Err instead of raising."""
        result = canonical_bytes(object())
        assert isinstance(result, Err)
        assert "Cannot serialize" in result.error or "Unsupported" in result.error


class TestCanonicalBytesDeterministic:
    def test_same_input_same_output(self) -> None:
        obj = {"key": Decimal("1.5"), "list": [1, 2, 3]}
        assert unwrap(canonical_bytes(obj)) == unwrap(canonical_bytes(obj))


# ---------------------------------------------------------------------------
# content_hash
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_returns_64_char_hex(self) -> None:
        h = unwrap(content_hash(42))
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self) -> None:
        assert unwrap(content_hash("hello")) == unwrap(content_hash("hello"))

    def test_different_inputs_differ(self) -> None:
        assert unwrap(content_hash("hello")) != unwrap(content_hash("world"))

    def test_unsupported_type_returns_err(self) -> None:
        result = content_hash(object())
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# derive_seed
# ---------------------------------------------------------------------------


class TestDeriveSeed:
    def test_deterministic(self) -> None:
        assert derive_seed("test") == derive_seed("test")

    def test_different_inputs_differ(self) -> None:
        assert derive_seed("a") != derive_seed("b")

    def test_returns_64_char_hex(self) -> None:
        s = derive_seed("test")
        assert len(s) == 64


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------


class TestProperties:
    @given(st.integers())
    def test_content_hash_int_deterministic(self, x: int) -> None:
        assert unwrap(content_hash(x)) == unwrap(content_hash(x))

    @given(st.text())
    def test_content_hash_str_deterministic(self, s: str) -> None:
        assert unwrap(content_hash(s)) == unwrap(content_hash(s))

    @given(st.decimals(allow_nan=False, allow_infinity=False))
    def test_canonical_bytes_decimal_is_string(self, d: Decimal) -> None:
        raw = unwrap(canonical_bytes(d))
        parsed = json.loads(raw)
        assert isinstance(parsed, str)

    @given(st.datetimes(timezones=st.just(UTC)))
    def test_canonical_bytes_aware_datetime_ok(self, dt: datetime) -> None:
        result = canonical_bytes(dt)
        assert isinstance(result, Ok)

    @given(st.datetimes(timezones=st.none()))
    def test_canonical_bytes_naive_datetime_err(self, dt: datetime) -> None:
        result = canonical_bytes(dt)
        assert isinstance(result, Err)

    @given(st.dictionaries(st.text(min_size=1, max_size=5), st.integers(), max_size=5))
    def test_canonical_bytes_dict_deterministic(self, d: dict[str, int]) -> None:
        assert unwrap(canonical_bytes(d)) == unwrap(canonical_bytes(d))
