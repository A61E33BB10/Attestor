"""Kafka topic definitions and infrastructure configuration for Phase 0.

No Kafka client library is imported. Pure configuration data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import final

# ---------------------------------------------------------------------------
# Topic names
# ---------------------------------------------------------------------------

TOPIC_EVENTS_RAW: str = "attestor.events.raw"
TOPIC_EVENTS_NORMALIZED: str = "attestor.events.normalized"
TOPIC_ATTESTATIONS: str = "attestor.attestations"

PHASE0_TOPICS: tuple[str, ...] = (
    TOPIC_EVENTS_RAW,
    TOPIC_EVENTS_NORMALIZED,
    TOPIC_ATTESTATIONS,
)

# Phase 1 topics
TOPIC_ORDERS: str = "attestor.orders"
TOPIC_SETTLEMENTS: str = "attestor.settlements"
TOPIC_DIVIDENDS: str = "attestor.dividends"
TOPIC_MARKET_DATA: str = "attestor.market_data"
TOPIC_EMIR_REPORTS: str = "attestor.emir_reports"

PHASE1_TOPICS: tuple[str, ...] = (
    TOPIC_ORDERS,
    TOPIC_SETTLEMENTS,
    TOPIC_DIVIDENDS,
    TOPIC_MARKET_DATA,
    TOPIC_EMIR_REPORTS,
)


# ---------------------------------------------------------------------------
# Topic configuration
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class TopicConfig:
    """Kafka topic configuration."""

    name: str
    partitions: int
    replication_factor: int
    retention_ms: int              # -1 for infinite retention
    cleanup_policy: str
    min_insync_replicas: int


def phase0_topic_configs() -> tuple[TopicConfig, ...]:
    """Return topic configs for the three Phase 0 topics."""
    return (
        TopicConfig(
            name=TOPIC_EVENTS_RAW,
            partitions=6, replication_factor=3,
            retention_ms=30 * 24 * 3600 * 1000,
            cleanup_policy="delete", min_insync_replicas=2,
        ),
        TopicConfig(
            name=TOPIC_EVENTS_NORMALIZED,
            partitions=6, replication_factor=3,
            retention_ms=90 * 24 * 3600 * 1000,
            cleanup_policy="delete", min_insync_replicas=2,
        ),
        TopicConfig(
            name=TOPIC_ATTESTATIONS,
            partitions=6, replication_factor=3,
            retention_ms=-1,
            cleanup_policy="delete", min_insync_replicas=2,
        ),
    )


def phase1_topic_configs() -> tuple[TopicConfig, ...]:
    """Return topic configs for the five Phase 1 topics."""
    return (
        TopicConfig(
            name=TOPIC_ORDERS,
            partitions=6, replication_factor=3,
            retention_ms=90 * 24 * 3600 * 1000,
            cleanup_policy="delete", min_insync_replicas=2,
        ),
        TopicConfig(
            name=TOPIC_SETTLEMENTS,
            partitions=6, replication_factor=3,
            retention_ms=90 * 24 * 3600 * 1000,
            cleanup_policy="delete", min_insync_replicas=2,
        ),
        TopicConfig(
            name=TOPIC_DIVIDENDS,
            partitions=3, replication_factor=3,
            retention_ms=90 * 24 * 3600 * 1000,
            cleanup_policy="delete", min_insync_replicas=2,
        ),
        TopicConfig(
            name=TOPIC_MARKET_DATA,
            partitions=12, replication_factor=3,
            retention_ms=7 * 24 * 3600 * 1000,
            cleanup_policy="delete", min_insync_replicas=2,
        ),
        TopicConfig(
            name=TOPIC_EMIR_REPORTS,
            partitions=3, replication_factor=3,
            retention_ms=-1,
            cleanup_policy="delete", min_insync_replicas=2,
        ),
    )


# ---------------------------------------------------------------------------
# Kafka producer/consumer configuration
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class KafkaProducerConfig:
    """Configuration for Kafka producers.

    Designed for exactly-once semantics and durability. Every setting
    is justified by a production failure mode it prevents.
    """

    bootstrap_servers: str = "localhost:9092"
    key_serializer: str = "utf-8"
    value_serializer: str = "raw"
    acks: str = "all"
    enable_idempotence: bool = True
    max_in_flight_requests_per_connection: int = 1
    retries: int = 3
    retry_backoff_ms: int = 100
    linger_ms: int = 5
    batch_size: int = 16384
    compression_type: str = "lz4"
    request_timeout_ms: int = 30000
    delivery_timeout_ms: int = 120000


@final
@dataclass(frozen=True, slots=True)
class KafkaConsumerConfig:
    """Configuration for Kafka consumers.

    At-least-once delivery with application-level dedup via idempotency_key.
    """

    bootstrap_servers: str = "localhost:9092"
    key_deserializer: str = "utf-8"
    value_deserializer: str = "raw"
    group_id: str = "attestor-default"
    auto_offset_reset: str = "earliest"
    enable_auto_commit: bool = False
    max_poll_records: int = 100
    session_timeout_ms: int = 30000
    max_poll_interval_ms: int = 300000
    fetch_min_bytes: int = 1
    fetch_max_wait_ms: int = 500


# ---------------------------------------------------------------------------
# Postgres connection pool configuration
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class PostgresPoolConfig:
    """Configuration for the Postgres connection pool."""

    host: str = "localhost"
    port: int = 5432
    database: str = "attestor"
    user: str = "attestor_app"
    # password: loaded from env var ATTESTOR_DB_PASSWORD. NEVER in config.
    min_size: int = 2
    max_size: int = 10
    connection_timeout_s: int = 5
    statement_timeout_ms: int = 30000
    idle_timeout_s: int = 300
    search_path: str = "attestor,public"
    ssl_mode: str = "prefer"
    application_name: str = "attestor-phase0"

    @property
    def dsn(self) -> str:
        """Construct a connection string (without password)."""
        return (
            f"host={self.host} port={self.port} dbname={self.database} "
            f"user={self.user} sslmode={self.ssl_mode} "
            f"application_name={self.application_name} "
            f"options='-c search_path={self.search_path} "
            f"-c statement_timeout={self.statement_timeout_ms}'"
        )
