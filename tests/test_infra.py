"""Tests for attestor.infra — protocols, config, and health checks."""

from __future__ import annotations

from attestor.core.errors import PersistenceError
from attestor.core.result import Err, Ok
from attestor.core.types import UtcDatetime
from attestor.infra.config import (
    PHASE1_TOPICS,
    KafkaConsumerConfig,
    KafkaProducerConfig,
    PostgresPoolConfig,
    TopicConfig,
    phase0_topic_configs,
    phase1_topic_configs,
)
from attestor.infra.health import (
    HealthCheckable,
    HealthStatus,
    liveness_check,
    readiness_check,
)
from attestor.infra.memory_adapter import (
    InMemoryAttestationStore,
    InMemoryEventBus,
    InMemoryStateStore,
    InMemoryTransactionLog,
)
from attestor.infra.protocols import (
    AttestationStore,
    EventBus,
    StateStore,
    TransactionLog,
)

# ---------------------------------------------------------------------------
# Protocol structural typing checks
# ---------------------------------------------------------------------------


class TestProtocolStructuralTyping:
    def test_attestation_store_is_protocol(self) -> None:
        store: AttestationStore = InMemoryAttestationStore()
        assert isinstance(store, AttestationStore)

    def test_event_bus_is_protocol(self) -> None:
        bus: EventBus = InMemoryEventBus()
        assert isinstance(bus, EventBus)

    def test_transaction_log_is_protocol(self) -> None:
        log: TransactionLog = InMemoryTransactionLog()
        assert isinstance(log, TransactionLog)

    def test_state_store_is_protocol(self) -> None:
        store: StateStore = InMemoryStateStore()
        assert isinstance(store, StateStore)

    def test_health_checkable_is_protocol(self) -> None:
        assert isinstance(HealthCheckable, type)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TestTopicConfig:
    def test_phase0_topics_count_3(self) -> None:
        configs = phase0_topic_configs()
        assert len(configs) == 3

    def test_attestations_topic_infinite_retention(self) -> None:
        configs = phase0_topic_configs()
        att_config = next(c for c in configs if "attestations" in c.name)
        assert att_config.retention_ms == -1

    def test_topic_config_has_replication_factor(self) -> None:
        configs = phase0_topic_configs()
        for c in configs:
            assert c.replication_factor == 3
            assert c.min_insync_replicas == 2

    def test_topic_config_frozen(self) -> None:
        c = TopicConfig(
            name="t", partitions=1, replication_factor=1,
            retention_ms=1000, cleanup_policy="delete", min_insync_replicas=1,
        )
        import dataclasses
        with __import__("pytest").raises(dataclasses.FrozenInstanceError):
            c.name = "x"  # type: ignore[misc]


class TestPhase1TopicConfig:
    def test_phase1_topics_count_5(self) -> None:
        configs = phase1_topic_configs()
        assert len(configs) == 5

    def test_phase1_topic_names(self) -> None:
        configs = phase1_topic_configs()
        names = {c.name for c in configs}
        assert names == set(PHASE1_TOPICS)

    def test_emir_reports_infinite_retention(self) -> None:
        configs = phase1_topic_configs()
        emir = next(c for c in configs if "emir" in c.name)
        assert emir.retention_ms == -1

    def test_market_data_higher_partitions(self) -> None:
        configs = phase1_topic_configs()
        md = next(c for c in configs if "market_data" in c.name)
        assert md.partitions == 12


class TestKafkaProducerConfig:
    def test_defaults(self) -> None:
        cfg = KafkaProducerConfig()
        assert cfg.acks == "all"
        assert cfg.enable_idempotence is True
        assert cfg.compression_type == "lz4"

    def test_frozen(self) -> None:
        import dataclasses

        import pytest
        cfg = KafkaProducerConfig()
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.acks = "1"  # type: ignore[misc]


class TestKafkaConsumerConfig:
    def test_auto_commit_false(self) -> None:
        cfg = KafkaConsumerConfig()
        assert cfg.enable_auto_commit is False

    def test_auto_offset_reset_earliest(self) -> None:
        cfg = KafkaConsumerConfig()
        assert cfg.auto_offset_reset == "earliest"


class TestPostgresPoolConfig:
    def test_dsn(self) -> None:
        cfg = PostgresPoolConfig()
        dsn = cfg.dsn
        assert "attestor" in dsn
        assert "attestor_app" in dsn

    def test_frozen(self) -> None:
        import dataclasses

        import pytest
        cfg = PostgresPoolConfig()
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.host = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_liveness_check_returns_healthy(self) -> None:
        status = liveness_check()
        assert status.healthy is True
        assert status.component == "process"

    def test_readiness_check_all_healthy(self) -> None:
        from datetime import UTC, datetime

        class _HealthyDep:
            def health_check(self) -> Ok[HealthStatus]:
                return Ok(HealthStatus(
                    healthy=True, component="test", message="ok",
                    checked_at=datetime.now(tz=UTC), latency_ms=1.0,
                ))

        result = readiness_check((_HealthyDep(),))
        assert result.overall_healthy is True
        assert len(result.checks) == 1

    def test_readiness_check_one_unhealthy(self) -> None:

        class _UnhealthyDep:
            def health_check(self) -> Err[PersistenceError]:
                return Err(PersistenceError(
                    message="db down", code="CONN_ERR",
                    timestamp=UtcDatetime.now(),
                    source="test", operation="connect",
                ))

        result = readiness_check((_UnhealthyDep(),))
        assert result.overall_healthy is False
        assert len(result.checks) == 1
        assert result.checks[0].healthy is False
