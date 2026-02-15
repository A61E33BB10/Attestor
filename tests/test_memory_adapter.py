"""Tests for attestor.infra.memory_adapter — in-memory test doubles."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from attestor.core.money import PositiveDecimal
from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import BitemporalEnvelope, UtcDatetime
from attestor.infra.memory_adapter import (
    InMemoryAttestationStore,
    InMemoryEventBus,
    InMemoryStateStore,
    InMemoryTransactionLog,
)
from attestor.ledger.transactions import Move, Transaction
from attestor.oracle.attestation import Attestation, FirmConfidence, create_attestation


def _make_firm_attestation(value: str = "test-value") -> Attestation[str]:
    """Create a firm attestation for testing."""
    from datetime import UTC, datetime

    now = datetime.now(tz=UTC)
    confidence = unwrap(FirmConfidence.create("test-source", now, "ref-1"))
    return unwrap(create_attestation(
        value=value,
        confidence=confidence,
        source="test",
        timestamp=now,
    ))


def _make_transaction(tx_id: str = "TX-1") -> Transaction:
    """Create a simple transaction for testing."""
    qty = unwrap(PositiveDecimal.parse(Decimal("100")))
    m = Move("A", "B", "USD", qty, "C-1")
    return Transaction(tx_id=tx_id, moves=(m,), timestamp=UtcDatetime.now())


# ---------------------------------------------------------------------------
# InMemoryAttestationStore
# ---------------------------------------------------------------------------


class TestInMemoryAttestationStore:
    def test_store_and_retrieve(self) -> None:
        store = InMemoryAttestationStore()
        att = _make_firm_attestation()
        result = store.store(att)
        assert isinstance(result, Ok)
        aid = result.value

        retrieved = store.retrieve(aid)
        assert isinstance(retrieved, Ok)
        assert retrieved.value == att

    def test_keyed_by_attestation_id(self) -> None:
        """GAP-01: store keys by attestation_id, not content_hash."""
        store = InMemoryAttestationStore()
        att = _make_firm_attestation()
        result = store.store(att)
        aid = unwrap(result)

        # The attestation_id is the store key
        assert aid == att.attestation_id

    def test_idempotent(self) -> None:
        store = InMemoryAttestationStore()
        att = _make_firm_attestation()
        r1 = store.store(att)
        r2 = store.store(att)
        assert unwrap(r1) == unwrap(r2)
        assert store.count() == 1

    def test_retrieve_not_found_err(self) -> None:
        store = InMemoryAttestationStore()
        result = store.retrieve("nonexistent-id")
        assert isinstance(result, Err)

    def test_exists_returns_result(self) -> None:
        """GAP-13: exists() returns Result[bool, PersistenceError]."""
        store = InMemoryAttestationStore()
        att = _make_firm_attestation()
        store.store(att)
        aid = att.attestation_id

        exists_result = store.exists(aid)
        assert isinstance(exists_result, Ok)
        assert exists_result.value is True

        not_exists = store.exists("nope")
        assert isinstance(not_exists, Ok)
        assert not_exists.value is False


# ---------------------------------------------------------------------------
# InMemoryEventBus
# ---------------------------------------------------------------------------


class TestInMemoryEventBus:
    def test_publish_and_get(self) -> None:
        bus = InMemoryEventBus()
        result = bus.publish("topic-1", "key-1", b"value-1")
        assert isinstance(result, Ok)

        msgs = bus.get_messages("topic-1")
        assert len(msgs) == 1
        assert msgs[0] == ("key-1", b"value-1")

    def test_multi_topic_isolation(self) -> None:
        bus = InMemoryEventBus()
        bus.publish("t1", "k1", b"v1")
        bus.publish("t2", "k2", b"v2")
        assert len(bus.get_messages("t1")) == 1
        assert len(bus.get_messages("t2")) == 1
        assert bus.topic_count() == 2

    def test_subscribe_returns_ok(self) -> None:
        bus = InMemoryEventBus()
        result = bus.subscribe("topic-1", "group-1")
        assert isinstance(result, Ok)


# ---------------------------------------------------------------------------
# InMemoryTransactionLog
# ---------------------------------------------------------------------------


class TestInMemoryTransactionLog:
    def test_append_replay_order(self) -> None:
        log = InMemoryTransactionLog()
        tx1 = _make_transaction("TX-1")
        tx2 = _make_transaction("TX-2")
        now = UtcDatetime.now()

        env1 = BitemporalEnvelope(payload=tx1, event_time=now, knowledge_time=now)
        env2 = BitemporalEnvelope(payload=tx2, event_time=now, knowledge_time=now)

        log.append(env1)
        log.append(env2)

        result = log.replay()
        assert isinstance(result, Ok)
        entries = result.value
        assert len(entries) == 2
        assert entries[0].payload.tx_id == "TX-1"
        assert entries[1].payload.tx_id == "TX-2"

    def test_replay_since(self) -> None:
        import time

        log = InMemoryTransactionLog()
        tx1 = _make_transaction("TX-OLD")
        early = UtcDatetime.now()
        env1 = BitemporalEnvelope(payload=tx1, event_time=early, knowledge_time=early)
        log.append(env1)

        time.sleep(0.01)
        cutoff = UtcDatetime.now()
        time.sleep(0.01)

        tx2 = _make_transaction("TX-NEW")
        late = UtcDatetime.now()
        env2 = BitemporalEnvelope(payload=tx2, event_time=late, knowledge_time=late)
        log.append(env2)

        result = log.replay_since(cutoff)
        assert isinstance(result, Ok)
        entries = result.value
        assert len(entries) == 1
        assert entries[0].payload.tx_id == "TX-NEW"


# ---------------------------------------------------------------------------
# InMemoryStateStore
# ---------------------------------------------------------------------------


class TestInMemoryStateStore:
    def test_put_get_roundtrip(self) -> None:
        store = InMemoryStateStore()
        store.put("key-1", b"value-1")
        result = store.get("key-1")
        assert isinstance(result, Ok)
        assert result.value == b"value-1"

    def test_missing_returns_ok_none(self) -> None:
        store = InMemoryStateStore()
        result = store.get("nonexistent")
        assert isinstance(result, Ok)
        assert result.value is None

    def test_overwrite(self) -> None:
        store = InMemoryStateStore()
        store.put("k", b"v1")
        store.put("k", b"v2")
        result = store.get("k")
        assert isinstance(result, Ok)
        assert result.value == b"v2"


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------


class TestProperties:
    @given(aid=st.text(min_size=1, max_size=50))
    def test_attestation_store_idempotent_property(self, aid: str) -> None:
        """Storing the same attestation twice produces the same ID."""
        store = InMemoryAttestationStore()
        att = _make_firm_attestation(aid)
        r1 = store.store(att)
        r2 = store.store(att)
        assert unwrap(r1) == unwrap(r2)
        assert store.count() == 1

    @given(key=st.text(min_size=1, max_size=50), value=st.binary(max_size=100))
    def test_state_store_roundtrip_property(self, key: str, value: bytes) -> None:
        """put(k, v) followed by get(k) returns v."""
        store = InMemoryStateStore()
        store.put(key, value)
        result = store.get(key)
        assert isinstance(result, Ok)
        assert result.value == value
