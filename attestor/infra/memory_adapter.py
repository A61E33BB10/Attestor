"""In-memory implementations of all four infrastructure protocols.

Test doubles that let the entire test suite run without Kafka or Postgres.
All classes are @final. None of them are production code.
"""

from __future__ import annotations

from typing import final

from attestor.core.errors import PersistenceError
from attestor.core.result import Err, Ok
from attestor.core.types import BitemporalEnvelope, UtcDatetime
from attestor.ledger.transactions import Transaction
from attestor.oracle.attestation import Attestation


def _persistence_error(operation: str, detail: str) -> PersistenceError:
    """Helper to construct PersistenceError with consistent formatting."""
    return PersistenceError(
        message=detail,
        code="PERSISTENCE_ERROR",
        timestamp=UtcDatetime.now(),
        source=f"memory_adapter.{operation}",
        operation=operation,
    )


@final
class InMemoryAttestationStore:
    """In-memory attestation store keyed by attestation_id.

    Per V-01/GAP-01: the store key is attestation_id (hash of full
    attestation identity), NOT content_hash (hash of value only).
    """

    def __init__(self) -> None:
        self._store: dict[str, Attestation[object]] = {}

    def store(
        self, attestation: Attestation[object],
    ) -> Ok[str] | Err[PersistenceError]:
        """Store. Idempotent: duplicate attestation_id is a no-op."""
        aid = attestation.attestation_id
        if aid not in self._store:
            self._store[aid] = attestation
        return Ok(aid)

    def retrieve(
        self, attestation_id: str,
    ) -> Ok[Attestation[object]] | Err[PersistenceError]:
        """Retrieve by attestation_id. Returns Err if not found."""
        if attestation_id in self._store:
            return Ok(self._store[attestation_id])
        return Err(_persistence_error(
            "retrieve",
            f"Attestation not found: {attestation_id}",
        ))

    def exists(
        self, attestation_id: str,
    ) -> Ok[bool] | Err[PersistenceError]:
        """Check existence. Returns Ok[bool] per GAP-13."""
        return Ok(attestation_id in self._store)

    def count(self) -> int:
        """Test-only helper."""
        return len(self._store)

    def all_ids(self) -> tuple[str, ...]:
        """Test-only helper."""
        return tuple(self._store.keys())


@final
class InMemoryEventBus:
    """In-memory event bus. Messages stored per-topic as (key, value) pairs."""

    def __init__(self) -> None:
        self._topics: dict[str, list[tuple[str, bytes]]] = {}

    def publish(
        self, topic: str, key: str, value: bytes,
    ) -> Ok[None] | Err[PersistenceError]:
        if topic not in self._topics:
            self._topics[topic] = []
        self._topics[topic].append((key, value))
        return Ok(None)

    def subscribe(
        self, topic: str, group: str,
    ) -> Ok[None] | Err[PersistenceError]:
        return Ok(None)

    def get_messages(self, topic: str) -> list[tuple[str, bytes]]:
        """Test-only helper."""
        return list(self._topics.get(topic, []))

    def topic_count(self) -> int:
        """Test-only helper."""
        return len(self._topics)


@final
class InMemoryTransactionLog:
    """In-memory append-only transaction log."""

    def __init__(self) -> None:
        self._log: list[BitemporalEnvelope[Transaction]] = []

    def append(
        self, envelope: BitemporalEnvelope[Transaction],
    ) -> Ok[None] | Err[PersistenceError]:
        self._log.append(envelope)
        return Ok(None)

    def replay(
        self,
    ) -> Ok[tuple[BitemporalEnvelope[Transaction], ...]] | Err[PersistenceError]:
        return Ok(tuple(self._log))

    def replay_since(
        self, since: UtcDatetime,
    ) -> Ok[tuple[BitemporalEnvelope[Transaction], ...]] | Err[PersistenceError]:
        filtered = tuple(
            e for e in self._log if e.knowledge_time.value >= since.value
        )
        return Ok(filtered)

    def count(self) -> int:
        """Test-only helper."""
        return len(self._log)


@final
class InMemoryStateStore:
    """In-memory key-value state store."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def get(
        self, key: str,
    ) -> Ok[bytes | None] | Err[PersistenceError]:
        return Ok(self._store.get(key))

    def put(
        self, key: str, value: bytes,
    ) -> Ok[None] | Err[PersistenceError]:
        self._store[key] = value
        return Ok(None)

    def count(self) -> int:
        """Test-only helper."""
        return len(self._store)

    def keys(self) -> tuple[str, ...]:
        """Test-only helper."""
        return tuple(self._store.keys())
