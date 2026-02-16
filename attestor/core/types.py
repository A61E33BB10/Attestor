"""Core types: UtcDatetime, FrozenMap, BitemporalEnvelope, IdempotencyKey, EventTime."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar, final

from attestor.core.result import Err, Ok


@final
@dataclass(frozen=True, slots=True)
class UtcDatetime:
    """Timezone-aware UTC datetime. Naive datetimes are rejected."""

    value: datetime

    def __post_init__(self) -> None:
        if self.value.tzinfo is None:
            raise TypeError("UtcDatetime requires timezone-aware datetime, got naive")

    @staticmethod
    def parse(raw: datetime) -> Ok[UtcDatetime] | Err[str]:
        """Parse a datetime, rejecting naive (no tzinfo) datetimes."""
        if raw.tzinfo is None:
            return Err("UtcDatetime requires timezone-aware datetime, got naive")
        return Ok(UtcDatetime(value=raw.astimezone(UTC)))

    @staticmethod
    def now() -> UtcDatetime:
        """Current UTC time."""
        return UtcDatetime(value=datetime.now(tz=UTC))


@final
@dataclass(frozen=True, slots=True)
class FrozenMap[K, V]:
    """Immutable sorted mapping for deterministic hashing and serialization.

    Entries are stored as a sorted tuple of (key, value) pairs.
    This guarantees: (a) immutability, (b) deterministic iteration order,
    (c) canonical serialization for content-addressing.
    """

    _entries: tuple[tuple[K, V], ...]

    EMPTY: ClassVar[FrozenMap[Any, Any]]  # Assigned after class definition

    @staticmethod
    def create(items: dict[K, V] | Iterable[tuple[K, V]]) -> Ok[FrozenMap[K, V]] | Err[str]:
        """Create a FrozenMap from a dict or iterable of (key, value) pairs.

        Duplicate keys: last value wins (like dict constructor). GAP-10.
        Non-comparable keys: returns Err. GAP-08.
        """
        if isinstance(items, dict):  # noqa: SIM108
            d = items
        else:
            d = dict(items)  # deduplicates: last value wins (GAP-10)
        try:
            entries = tuple(sorted(d.items(), key=lambda kv: kv[0]))
        except TypeError as e:
            return Err(f"FrozenMap keys must be comparable: {e}")
        return Ok(FrozenMap(_entries=entries))

    def get(self, key: K, default: V | None = None) -> V | None:
        """Return value for key, or default if not found."""
        for k, v in self._entries:
            if k == key:
                return v
        return default

    def __getitem__(self, key: K) -> V:
        for k, v in self._entries:
            if k == key:
                return v
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        return any(k == key for k, _ in self._entries)

    def __iter__(self) -> Iterator[K]:
        return (k for k, _ in self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def items(self) -> tuple[tuple[K, V], ...]:
        """Return the sorted (key, value) entries."""
        return self._entries

    def to_dict(self) -> dict[K, V]:
        """Convert to a regular dict (for serialization boundaries)."""
        return dict(self._entries)


FrozenMap.EMPTY = FrozenMap(_entries=())


@final
@dataclass(frozen=True, slots=True)
class BitemporalEnvelope[T]:
    """Wraps payload with event-time and knowledge-time."""

    payload: T
    event_time: UtcDatetime
    knowledge_time: UtcDatetime


@final
@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    """Non-empty string key for idempotent operations."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise TypeError("IdempotencyKey requires non-empty string")

    @staticmethod
    def create(raw: str) -> Ok[IdempotencyKey] | Err[str]:
        """Create an IdempotencyKey, rejecting empty strings."""
        if not raw:
            return Err("IdempotencyKey requires non-empty string")
        return Ok(IdempotencyKey(value=raw))


@final
@dataclass(frozen=True, slots=True)
class EventTime:
    """Temporal ordering wrapper using UtcDatetime."""

    value: UtcDatetime
