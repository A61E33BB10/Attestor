"""Infrastructure protocol definitions for Attestor Phase 0.

Domain code depends on these abstractions. Infrastructure code implements them.
The two never meet except in orchestration/.

All protocols return Ok[T] | Err[PersistenceError]. Infrastructure failures
are visible values in the type system, never invisible exceptions.

D-07 clarification (GAP-41): infra/protocols.py may import domain types from
any pillar for protocol signatures. infra/ implementation modules import only
core/ and infra/protocols.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from attestor.core.errors import PersistenceError
from attestor.core.result import Err, Ok
from attestor.core.types import BitemporalEnvelope, UtcDatetime
from attestor.ledger.transactions import Transaction
from attestor.oracle.attestation import Attestation


@runtime_checkable
class AttestationStore(Protocol):
    """Content-addressed attestation storage.

    Keyed by attestation_id (hash of full attestation identity, per V-01/GAP-01).
    content_hash is a secondary attribute for dedup-by-value queries.

    Invariants:
      - store() is idempotent: storing the same attestation twice returns
        the same attestation_id without creating a duplicate (INV-X03).
      - retrieve() returns Err if the attestation_id is not found.
      - exists() returns Ok[bool] | Err[PersistenceError] (GAP-13).
    """

    def store(
        self, attestation: Attestation[object],
    ) -> Ok[str] | Err[PersistenceError]: ...

    def retrieve(
        self, attestation_id: str,
    ) -> Ok[Attestation[object]] | Err[PersistenceError]: ...

    def exists(
        self, attestation_id: str,
    ) -> Ok[bool] | Err[PersistenceError]: ...


@runtime_checkable
class EventBus(Protocol):
    """Append-only event transport (Kafka in production).

    Messages are keyed for deterministic partitioning. Values are opaque
    bytes — serialization is the caller's responsibility.
    """

    def publish(
        self, topic: str, key: str, value: bytes,
    ) -> Ok[None] | Err[PersistenceError]: ...

    def subscribe(
        self, topic: str, group: str,
    ) -> Ok[None] | Err[PersistenceError]: ...


@runtime_checkable
class TransactionLog(Protocol):
    """Append-only transaction log for deterministic replay.

    Every accounting mutation is recorded as a BitemporalEnvelope[Transaction].
    """

    def append(
        self, envelope: BitemporalEnvelope[Transaction],
    ) -> Ok[None] | Err[PersistenceError]: ...

    def replay(
        self,
    ) -> Ok[tuple[BitemporalEnvelope[Transaction], ...]] | Err[PersistenceError]: ...

    def replay_since(
        self, since: UtcDatetime,
    ) -> Ok[tuple[BitemporalEnvelope[Transaction], ...]] | Err[PersistenceError]: ...


@runtime_checkable
class StateStore(Protocol):
    """Key-value state store for derived projections.

    Used by consumers for checkpoint offsets and materialized view metadata.
    NOT the accounting state (which lives in TransactionLog).
    """

    def get(
        self, key: str,
    ) -> Ok[bytes | None] | Err[PersistenceError]: ...

    def put(
        self, key: str, value: bytes,
    ) -> Ok[None] | Err[PersistenceError]: ...
