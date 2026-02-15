"""Tests for attestor.core.types — UtcDatetime, FrozenMap, BitemporalEnvelope, etc."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import (
    BitemporalEnvelope,
    EventTime,
    FrozenMap,
    IdempotencyKey,
    UtcDatetime,
)

# ---------------------------------------------------------------------------
# UtcDatetime (GAP-03)
# ---------------------------------------------------------------------------


class TestUtcDatetime:
    def test_parse_aware_ok(self) -> None:
        dt = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
        result = UtcDatetime.parse(dt)
        assert isinstance(result, Ok)
        assert unwrap(result).value == dt

    def test_parse_naive_err(self) -> None:
        dt = datetime(2024, 1, 15, 12, 0)  # naive
        result = UtcDatetime.parse(dt)
        assert isinstance(result, Err)
        assert "naive" in result.error

    def test_converts_to_utc(self) -> None:
        """EST input is stored as UTC."""
        est = timezone(timedelta(hours=-5))
        dt = datetime(2024, 1, 15, 12, 0, tzinfo=est)
        utc_dt = unwrap(UtcDatetime.parse(dt))
        assert utc_dt.value.tzinfo == UTC
        assert utc_dt.value.hour == 17  # 12 EST = 17 UTC

    def test_now_is_aware(self) -> None:
        now = UtcDatetime.now()
        assert now.value.tzinfo is not None

    def test_frozen(self) -> None:
        utc = UtcDatetime.now()
        with pytest.raises(dataclasses.FrozenInstanceError):
            utc.value = datetime.now(tz=UTC)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# FrozenMap (GAP-08, GAP-10)
# ---------------------------------------------------------------------------


class TestFrozenMapCreate:
    def test_create_from_dict(self) -> None:
        result = FrozenMap.create({"b": 2, "a": 1})
        fm = unwrap(result)
        assert fm._entries == (("a", 1), ("b", 2))

    def test_create_from_iterable(self) -> None:
        result = FrozenMap.create([("z", 3), ("a", 1)])
        fm = unwrap(result)
        assert fm._entries == (("a", 1), ("z", 3))

    def test_create_returns_result(self) -> None:
        result = FrozenMap.create({"a": 1})
        assert isinstance(result, Ok)

    def test_create_deduplicates_keys(self) -> None:
        """GAP-10: last value wins for duplicate keys."""
        result = FrozenMap.create([("a", 1), ("a", 2)])
        fm = unwrap(result)
        assert fm["a"] == 2
        assert len(fm) == 1

    def test_create_non_comparable_keys_err(self) -> None:
        """GAP-08: non-comparable keys return Err."""
        result = FrozenMap.create({complex(1, 2): "a", complex(3, 4): "b"})
        assert isinstance(result, Err)
        assert "comparable" in result.error


class TestFrozenMapAccess:
    def test_get_existing_key(self) -> None:
        fm = unwrap(FrozenMap.create({"a": 1, "b": 2}))
        assert fm.get("a") == 1

    def test_get_missing_key_returns_default(self) -> None:
        fm = unwrap(FrozenMap.create({"a": 1}))
        assert fm.get("z") is None
        assert fm.get("z", 99) == 99

    def test_getitem_existing(self) -> None:
        fm = unwrap(FrozenMap.create({"a": 1}))
        assert fm["a"] == 1

    def test_getitem_missing_raises_keyerror(self) -> None:
        fm = unwrap(FrozenMap.create({"a": 1}))
        with pytest.raises(KeyError):
            _ = fm["z"]

    def test_contains_true(self) -> None:
        fm = unwrap(FrozenMap.create({"a": 1}))
        assert "a" in fm

    def test_contains_false(self) -> None:
        fm = unwrap(FrozenMap.create({"a": 1}))
        assert "z" not in fm

    def test_iter_yields_keys_sorted(self) -> None:
        fm = unwrap(FrozenMap.create({"c": 3, "a": 1, "b": 2}))
        assert list(fm) == ["a", "b", "c"]

    def test_len(self) -> None:
        fm = unwrap(FrozenMap.create({"a": 1, "b": 2}))
        assert len(fm) == 2

    def test_items_returns_sorted_tuples(self) -> None:
        fm = unwrap(FrozenMap.create({"b": 2, "a": 1}))
        assert fm.items() == (("a", 1), ("b", 2))

    def test_to_dict_round_trip(self) -> None:
        d = {"a": 1, "b": 2, "c": 3}
        fm = unwrap(FrozenMap.create(d))
        assert fm.to_dict() == d


class TestFrozenMapMisc:
    def test_empty_frozen_map(self) -> None:
        assert len(FrozenMap.EMPTY) == 0
        assert list(FrozenMap.EMPTY) == []

    def test_frozen(self) -> None:
        fm = unwrap(FrozenMap.create({"a": 1}))
        with pytest.raises(dataclasses.FrozenInstanceError):
            fm._entries = ()  # type: ignore[misc]

    def test_equality(self) -> None:
        fm1 = unwrap(FrozenMap.create({"a": 1, "b": 2}))
        fm2 = unwrap(FrozenMap.create({"b": 2, "a": 1}))  # same entries, different order
        assert fm1 == fm2

    def test_inequality(self) -> None:
        fm1 = unwrap(FrozenMap.create({"a": 1}))
        fm2 = unwrap(FrozenMap.create({"a": 2}))
        assert fm1 != fm2


# ---------------------------------------------------------------------------
# BitemporalEnvelope
# ---------------------------------------------------------------------------


class TestBitemporalEnvelope:
    def test_wraps_payload(self) -> None:
        now = UtcDatetime.now()
        env = BitemporalEnvelope(payload="data", event_time=now, knowledge_time=now)
        assert env.payload == "data"

    def test_has_event_time_and_knowledge_time(self) -> None:
        et = UtcDatetime.now()
        kt = UtcDatetime.now()
        env = BitemporalEnvelope(payload=42, event_time=et, knowledge_time=kt)
        assert env.event_time == et
        assert env.knowledge_time == kt

    def test_frozen(self) -> None:
        now = UtcDatetime.now()
        env = BitemporalEnvelope(payload="x", event_time=now, knowledge_time=now)
        with pytest.raises(dataclasses.FrozenInstanceError):
            env.payload = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# IdempotencyKey
# ---------------------------------------------------------------------------


class TestIdempotencyKey:
    def test_create_valid(self) -> None:
        result = IdempotencyKey.create("txn-123")
        assert isinstance(result, Ok)
        assert unwrap(result).value == "txn-123"

    def test_create_empty(self) -> None:
        result = IdempotencyKey.create("")
        assert isinstance(result, Err)
        assert "non-empty" in result.error

    def test_frozen(self) -> None:
        key = unwrap(IdempotencyKey.create("abc"))
        with pytest.raises(dataclasses.FrozenInstanceError):
            key.value = "xyz"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# EventTime
# ---------------------------------------------------------------------------


class TestBusinessDayCalendar:
    def test_add_1_business_day_from_monday(self) -> None:
        from datetime import date as _date

        from attestor.core.calendar import add_business_days
        # Monday 2025-06-16 + 1 = Tuesday 2025-06-17
        assert add_business_days(_date(2025, 6, 16), 1) == _date(2025, 6, 17)

    def test_add_2_business_days_from_monday(self) -> None:
        from datetime import date as _date

        from attestor.core.calendar import add_business_days
        # Monday 2025-06-16 + 2 = Wednesday 2025-06-18
        assert add_business_days(_date(2025, 6, 16), 2) == _date(2025, 6, 18)

    def test_add_1_business_day_from_friday(self) -> None:
        from datetime import date as _date

        from attestor.core.calendar import add_business_days
        # Friday 2025-06-13 + 1 = Monday 2025-06-16
        assert add_business_days(_date(2025, 6, 13), 1) == _date(2025, 6, 16)

    def test_add_5_business_days_skips_weekend(self) -> None:
        from datetime import date as _date

        from attestor.core.calendar import add_business_days
        # Monday 2025-06-16 + 5 = Monday 2025-06-23
        assert add_business_days(_date(2025, 6, 16), 5) == _date(2025, 6, 23)


class TestEventTime:
    def test_wraps_utc_datetime(self) -> None:
        utc = UtcDatetime.now()
        et = EventTime(value=utc)
        assert et.value == utc

    def test_frozen(self) -> None:
        et = EventTime(value=UtcDatetime.now())
        with pytest.raises(dataclasses.FrozenInstanceError):
            et.value = UtcDatetime.now()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------


class TestProperties:
    @given(st.dictionaries(st.text(min_size=1), st.integers(), min_size=0, max_size=20))
    def test_frozen_map_to_dict_round_trip(self, d: dict[str, int]) -> None:
        fm = unwrap(FrozenMap.create(d))
        assert fm.to_dict() == d

    @given(st.dictionaries(st.text(min_size=1), st.integers(), min_size=1, max_size=20))
    def test_frozen_map_len_matches_dict(self, d: dict[str, int]) -> None:
        fm = unwrap(FrozenMap.create(d))
        assert len(fm) == len(d)

    @given(st.dictionaries(st.text(min_size=1), st.integers(), min_size=1, max_size=20))
    def test_frozen_map_contains_all_keys(self, d: dict[str, int]) -> None:
        fm = unwrap(FrozenMap.create(d))
        for k in d:
            assert k in fm

    @given(st.dictionaries(st.text(min_size=1), st.integers(), min_size=2, max_size=20))
    def test_frozen_map_entries_sorted(self, d: dict[str, int]) -> None:
        fm = unwrap(FrozenMap.create(d))
        keys = [k for k, _ in fm.items()]
        assert keys == sorted(keys)

    @given(st.datetimes(timezones=st.just(UTC)))
    def test_utc_datetime_parse_preserves_value(self, dt: datetime) -> None:
        result = UtcDatetime.parse(dt)
        assert isinstance(result, Ok)
        assert unwrap(result).value == dt

    @given(st.datetimes(timezones=st.none()))
    def test_utc_datetime_parse_rejects_naive(self, dt: datetime) -> None:
        result = UtcDatetime.parse(dt)
        assert isinstance(result, Err)
