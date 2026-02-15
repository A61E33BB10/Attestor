"""Tests for attestor.infra Phase 2 — topics and topic configs."""

from __future__ import annotations

from pathlib import Path

from attestor.infra.config import (
    PHASE2_TOPICS,
    TOPIC_DERIVATIVE_ORDERS,
    TOPIC_FUTURES_SETTLEMENTS,
    TOPIC_MARGIN_EVENTS,
    TOPIC_MIFID2_REPORTS,
    TOPIC_OPTION_PRICES,
    TopicConfig,
    phase2_topic_configs,
)


class TestPhase2Topics:
    def test_phase2_topics_count_5(self) -> None:
        assert len(PHASE2_TOPICS) == 5

    def test_all_topic_names_present(self) -> None:
        assert TOPIC_DERIVATIVE_ORDERS in PHASE2_TOPICS
        assert TOPIC_OPTION_PRICES in PHASE2_TOPICS
        assert TOPIC_FUTURES_SETTLEMENTS in PHASE2_TOPICS
        assert TOPIC_MIFID2_REPORTS in PHASE2_TOPICS
        assert TOPIC_MARGIN_EVENTS in PHASE2_TOPICS

    def test_topic_names_start_with_attestor(self) -> None:
        for topic in PHASE2_TOPICS:
            assert topic.startswith("attestor."), f"{topic} missing prefix"


class TestPhase2TopicConfigs:
    def test_phase2_topic_configs_count_5(self) -> None:
        configs = phase2_topic_configs()
        assert len(configs) == 5

    def test_phase2_topic_config_names(self) -> None:
        configs = phase2_topic_configs()
        names = {c.name for c in configs}
        assert names == set(PHASE2_TOPICS)

    def test_mifid2_reports_infinite_retention(self) -> None:
        configs = phase2_topic_configs()
        mifid = next(c for c in configs if "mifid2" in c.name)
        assert mifid.retention_ms == -1

    def test_margin_events_infinite_retention(self) -> None:
        configs = phase2_topic_configs()
        margin = next(c for c in configs if "margin" in c.name)
        assert margin.retention_ms == -1

    def test_replication_factor_3(self) -> None:
        for c in phase2_topic_configs():
            assert c.replication_factor == 3
            assert c.min_insync_replicas == 2

    def test_all_configs_are_topic_config(self) -> None:
        for c in phase2_topic_configs():
            assert isinstance(c, TopicConfig)


class TestPhase2SQL:
    def test_sql_010_exists(self) -> None:
        p = Path(__file__).parent.parent / "sql" / "010_margin_events.sql"
        assert p.exists()
        content = p.read_text()
        assert "attestor.margin_events" in content
        assert "prevent_mutation()" in content

    def test_sql_011_exists(self) -> None:
        p = Path(__file__).parent.parent / "sql" / "011_gl_projection.sql"
        assert p.exists()
        content = p.read_text()
        assert "attestor.gl_projection" in content
        assert "prevent_mutation()" in content

    def test_sql_012_exists(self) -> None:
        p = Path(__file__).parent.parent / "sql" / "012_reports_mifid2.sql"
        assert p.exists()
        content = p.read_text()
        assert "attestor.reports_mifid2" in content
        assert "prevent_mutation()" in content
