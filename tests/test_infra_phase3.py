"""Tests for attestor.infra Phase 3 — topics, topic configs, and SQL schemas."""

from __future__ import annotations

from pathlib import Path

from attestor.infra.config import (
    PHASE0_TOPICS,
    PHASE1_TOPICS,
    PHASE2_TOPICS,
    PHASE3_TOPICS,
    TOPIC_CALIBRATION_EVENTS,
    TOPIC_FX_RATES,
    TOPIC_MODEL_CONFIGS,
    TOPIC_RATE_FIXINGS,
    TOPIC_YIELD_CURVES,
    TopicConfig,
    phase3_topic_configs,
)

SQL_DIR = Path(__file__).parent.parent / "sql"


class TestPhase3Topics:
    def test_topic_constants_defined(self) -> None:
        """All 5 Phase 3 topic constants are non-empty strings."""
        for topic in (
            TOPIC_FX_RATES,
            TOPIC_YIELD_CURVES,
            TOPIC_RATE_FIXINGS,
            TOPIC_CALIBRATION_EVENTS,
            TOPIC_MODEL_CONFIGS,
        ):
            assert isinstance(topic, str)
            assert len(topic) > 0

    def test_phase3_topics_frozenset(self) -> None:
        """PHASE3_TOPICS has exactly 5 elements."""
        assert isinstance(PHASE3_TOPICS, frozenset)
        assert len(PHASE3_TOPICS) == 5

    def test_no_overlap_with_phase012(self) -> None:
        """Phase 3 topics don't overlap with Phase 0/1/2."""
        earlier = set(PHASE0_TOPICS) | set(PHASE1_TOPICS) | set(PHASE2_TOPICS)
        assert PHASE3_TOPICS.isdisjoint(earlier)


class TestPhase3TopicConfigs:
    def test_config_count(self) -> None:
        """phase3_topic_configs returns 5 TopicConfig objects."""
        configs = phase3_topic_configs()
        assert len(configs) == 5
        for c in configs:
            assert isinstance(c, TopicConfig)

    def test_config_names_match_constants(self) -> None:
        """Each config.name matches a Phase 3 constant."""
        names = {c.name for c in phase3_topic_configs()}
        assert names == PHASE3_TOPICS

    def test_retention_policies(self) -> None:
        """FX rates: 90 days. Others: infinite (-1)."""
        configs = phase3_topic_configs()
        fx = next(c for c in configs if c.name == TOPIC_FX_RATES)
        assert fx.retention_ms == 90 * 24 * 3600 * 1000
        for c in configs:
            if c.name != TOPIC_FX_RATES:
                assert c.retention_ms == -1, f"{c.name} should have infinite retention"

    def test_replication_factor(self) -> None:
        """All configs have replication_factor=3."""
        for c in phase3_topic_configs():
            assert c.replication_factor == 3

    def test_min_insync_replicas(self) -> None:
        """All configs have min_insync_replicas=2."""
        for c in phase3_topic_configs():
            assert c.min_insync_replicas == 2

    def test_partition_counts(self) -> None:
        """FX rates: 6 partitions. Others: 3."""
        configs = phase3_topic_configs()
        fx = next(c for c in configs if c.name == TOPIC_FX_RATES)
        assert fx.partitions == 6
        for c in configs:
            if c.name != TOPIC_FX_RATES:
                assert c.partitions == 3, f"{c.name} should have 3 partitions"


class TestPhase3SQL:
    def test_yield_curves_sql(self) -> None:
        """013_yield_curves.sql exists, has CREATE TABLE and trigger."""
        p = SQL_DIR / "013_yield_curves.sql"
        assert p.exists()
        content = p.read_text()
        assert "attestor.yield_curves" in content
        assert "prevent_mutation()" in content

    def test_fx_rates_sql(self) -> None:
        """014_fx_rates.sql exists, has CREATE TABLE and trigger."""
        p = SQL_DIR / "014_fx_rates.sql"
        assert p.exists()
        content = p.read_text()
        assert "attestor.fx_rates" in content
        assert "prevent_mutation()" in content

    def test_model_configs_sql(self) -> None:
        """015_model_configs.sql has composite PK and trigger."""
        p = SQL_DIR / "015_model_configs.sql"
        assert p.exists()
        content = p.read_text()
        assert "attestor.model_configs" in content
        assert "PRIMARY KEY" in content
        assert "prevent_mutation()" in content

    def test_calibration_failures_sql(self) -> None:
        """016_calibration_failures.sql exists with trigger."""
        p = SQL_DIR / "016_calibration_failures.sql"
        assert p.exists()
        content = p.read_text()
        assert "attestor.calibration_failures" in content
        assert "prevent_mutation()" in content

    def test_cashflows_sql(self) -> None:
        """017_cashflows.sql has status CHECK and trigger."""
        p = SQL_DIR / "017_cashflows.sql"
        assert p.exists()
        content = p.read_text()
        assert "attestor.cashflows" in content
        assert "status" in content
        assert "CHECK" in content
        assert "prevent_mutation()" in content
