"""Tests for attestor.infra Phase 4 — topics, topic configs, and SQL schemas."""

from __future__ import annotations

from pathlib import Path

from attestor.infra.config import (
    PHASE0_TOPICS,
    PHASE1_TOPICS,
    PHASE2_TOPICS,
    PHASE3_TOPICS,
    PHASE4_TOPICS,
    TOPIC_COLLATERAL,
    TOPIC_CREDIT_CURVES,
    TOPIC_CREDIT_EVENTS,
    TOPIC_VOL_SURFACES,
    TopicConfig,
    phase4_topic_configs,
)

SQL_DIR = Path(__file__).parent.parent / "sql"


class TestPhase4Topics:
    def test_topic_constants_defined(self) -> None:
        """All 4 Phase 4 topic constants are non-empty strings."""
        for topic in (
            TOPIC_VOL_SURFACES,
            TOPIC_CREDIT_CURVES,
            TOPIC_COLLATERAL,
            TOPIC_CREDIT_EVENTS,
        ):
            assert isinstance(topic, str)
            assert len(topic) > 0

    def test_phase4_topics_frozenset(self) -> None:
        """PHASE4_TOPICS has exactly 4 elements."""
        assert isinstance(PHASE4_TOPICS, frozenset)
        assert len(PHASE4_TOPICS) == 4

    def test_phase4_topics_contains_expected_values(self) -> None:
        """All expected constants are in PHASE4_TOPICS."""
        assert TOPIC_VOL_SURFACES in PHASE4_TOPICS
        assert TOPIC_CREDIT_CURVES in PHASE4_TOPICS
        assert TOPIC_COLLATERAL in PHASE4_TOPICS
        assert TOPIC_CREDIT_EVENTS in PHASE4_TOPICS

    def test_no_overlap_with_phase0123(self) -> None:
        """Phase 4 topics don't overlap with Phase 0/1/2/3."""
        earlier = (
            set(PHASE0_TOPICS)
            | set(PHASE1_TOPICS)
            | set(PHASE2_TOPICS)
            | PHASE3_TOPICS
        )
        assert PHASE4_TOPICS.isdisjoint(earlier)


class TestPhase4TopicConfigs:
    def test_config_count(self) -> None:
        """phase4_topic_configs returns 4 TopicConfig objects."""
        configs = phase4_topic_configs()
        assert len(configs) == 4
        for c in configs:
            assert isinstance(c, TopicConfig)

    def test_config_names_match_constants(self) -> None:
        """Each config.name matches a Phase 4 constant."""
        names = {c.name for c in phase4_topic_configs()}
        assert names == PHASE4_TOPICS

    def test_replication_factor(self) -> None:
        """All configs have replication_factor=3."""
        for c in phase4_topic_configs():
            assert c.replication_factor == 3

    def test_min_insync_replicas(self) -> None:
        """All configs have min_insync_replicas=2."""
        for c in phase4_topic_configs():
            assert c.min_insync_replicas == 2

    def test_partition_counts(self) -> None:
        """Vol surfaces and credit curves: 3 partitions. Collateral and credit events: 6."""
        configs = phase4_topic_configs()
        vol_surf = next(c for c in configs if c.name == TOPIC_VOL_SURFACES)
        credit_curv = next(c for c in configs if c.name == TOPIC_CREDIT_CURVES)
        collateral = next(c for c in configs if c.name == TOPIC_COLLATERAL)
        credit_evt = next(c for c in configs if c.name == TOPIC_CREDIT_EVENTS)

        assert vol_surf.partitions == 3
        assert credit_curv.partitions == 3
        assert collateral.partitions == 6
        assert credit_evt.partitions == 6

    def test_retention_policies(self) -> None:
        """All Phase 4 topics: infinite retention (-1)."""
        configs = phase4_topic_configs()
        vol_surf = next(c for c in configs if c.name == TOPIC_VOL_SURFACES)
        credit_curv = next(c for c in configs if c.name == TOPIC_CREDIT_CURVES)
        collateral = next(c for c in configs if c.name == TOPIC_COLLATERAL)
        credit_evt = next(c for c in configs if c.name == TOPIC_CREDIT_EVENTS)

        assert vol_surf.retention_ms == -1
        assert credit_curv.retention_ms == -1
        assert collateral.retention_ms == -1
        assert credit_evt.retention_ms == -1

    def test_cleanup_policies(self) -> None:
        """All Phase 4 topics: delete cleanup policy."""
        configs = phase4_topic_configs()
        vol_surf = next(c for c in configs if c.name == TOPIC_VOL_SURFACES)
        credit_curv = next(c for c in configs if c.name == TOPIC_CREDIT_CURVES)
        collateral = next(c for c in configs if c.name == TOPIC_COLLATERAL)
        credit_evt = next(c for c in configs if c.name == TOPIC_CREDIT_EVENTS)

        assert vol_surf.cleanup_policy == "delete"
        assert credit_curv.cleanup_policy == "delete"
        assert collateral.cleanup_policy == "delete"
        assert credit_evt.cleanup_policy == "delete"

    def test_configs_are_frozen(self) -> None:
        """TopicConfig instances are frozen (immutable)."""
        configs = phase4_topic_configs()
        for c in configs:
            # Attempting to modify a frozen dataclass raises FrozenInstanceError
            try:
                c.partitions = 999  # type: ignore
                raise AssertionError(f"Expected frozen dataclass, but {c} was mutable")
            except (AttributeError, ValueError):
                pass


class TestPhase4SQL:
    def test_vol_surfaces_sql(self) -> None:
        """018_vol_surfaces.sql exists, has CREATE TABLE and trigger."""
        p = SQL_DIR / "018_vol_surfaces.sql"
        assert p.exists(), f"{p} does not exist"
        content = p.read_text()
        assert "attestor.vol_surfaces" in content
        assert "prevent_mutation()" in content

    def test_credit_curves_sql(self) -> None:
        """019_credit_curves.sql exists, has CREATE TABLE and trigger."""
        p = SQL_DIR / "019_credit_curves.sql"
        assert p.exists(), f"{p} does not exist"
        content = p.read_text()
        assert "attestor.credit_curves" in content
        assert "prevent_mutation()" in content

    def test_credit_curves_recovery_rate_check(self) -> None:
        """Credit curves table has recovery_rate CHECK constraint."""
        p = SQL_DIR / "019_credit_curves.sql"
        content = p.read_text()
        assert "recovery_rate" in content
        assert "CHECK" in content

    def test_collateral_balances_sql(self) -> None:
        """020_collateral_balances.sql exists, has CREATE TABLE and trigger."""
        p = SQL_DIR / "020_collateral_balances.sql"
        assert p.exists(), f"{p} does not exist"
        content = p.read_text()
        assert "attestor.collateral_balances" in content
        assert "prevent_mutation()" in content

    def test_collateral_type_check(self) -> None:
        """Collateral balances table has collateral_type CHECK constraint."""
        p = SQL_DIR / "020_collateral_balances.sql"
        content = p.read_text()
        assert "collateral_type" in content
        assert "CHECK" in content
        assert "CASH" in content
        assert "GOVERNMENT_BOND" in content

    def test_credit_events_sql(self) -> None:
        """021_credit_events.sql exists, has CREATE TABLE and trigger."""
        p = SQL_DIR / "021_credit_events.sql"
        assert p.exists(), f"{p} does not exist"
        content = p.read_text()
        assert "attestor.credit_events" in content
        assert "prevent_mutation()" in content

    def test_credit_events_type_check(self) -> None:
        """Credit events table has event_type CHECK constraint."""
        p = SQL_DIR / "021_credit_events.sql"
        content = p.read_text()
        assert "event_type" in content
        assert "CHECK" in content
        assert "BANKRUPTCY" in content
        assert "FAILURE_TO_PAY" in content
