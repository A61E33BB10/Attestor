"""Integration tests for attestation store — round-trip, provenance, identity.

Uses InMemoryAttestationStore as the SUT. These tests verify the full
attestation lifecycle: create -> store -> retrieve -> verify identity.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import FrozenMap
from attestor.infra.memory_adapter import InMemoryAttestationStore
from attestor.oracle.attestation import (
    DerivedConfidence,
    FirmConfidence,
    QuotedConfidence,
    create_attestation,
)


def _now() -> datetime:
    return datetime.now(tz=UTC)


class TestAttestationStoreIntegration:
    def test_store_firm_attestation_and_retrieve(self) -> None:
        """Store a FirmConfidence attestation, retrieve by attestation_id."""
        store = InMemoryAttestationStore()
        confidence = unwrap(FirmConfidence.create("NYSE", _now(), "ref-001"))
        att = unwrap(create_attestation(
            value=Decimal("100.50"), confidence=confidence,
            source="test", timestamp=_now(),
        ))
        aid = unwrap(store.store(att))
        retrieved = unwrap(store.retrieve(aid))
        assert retrieved.content_hash == att.content_hash
        assert retrieved.attestation_id == att.attestation_id

    def test_store_quoted_attestation_and_retrieve(self) -> None:
        """Store a QuotedConfidence attestation, retrieve by attestation_id."""
        store = InMemoryAttestationStore()
        confidence = unwrap(QuotedConfidence.create(
            bid=Decimal("99.50"), ask=Decimal("100.50"), venue="Bloomberg",
        ))
        att = unwrap(create_attestation(
            value=Decimal("100"), confidence=confidence,
            source="market", timestamp=_now(),
        ))
        aid = unwrap(store.store(att))
        retrieved = unwrap(store.retrieve(aid))
        assert retrieved.attestation_id == att.attestation_id

    def test_store_derived_attestation_with_provenance(self) -> None:
        """Store a DerivedConfidence attestation with provenance refs."""
        store = InMemoryAttestationStore()

        # First, create and store input attestations
        fc = unwrap(FirmConfidence.create("ICE", _now(), "ref-A"))
        input1 = unwrap(create_attestation(
            value=Decimal("50"), confidence=fc,
            source="ice", timestamp=_now(),
        ))
        fc2 = unwrap(FirmConfidence.create("CME", _now(), "ref-B"))
        input2 = unwrap(create_attestation(
            value=Decimal("51"), confidence=fc2,
            source="cme", timestamp=_now(),
        ))
        store.store(input1)
        store.store(input2)

        # Create derived attestation with provenance
        fq = unwrap(FrozenMap.create({"r_squared": Decimal("0.95")}))
        dc = unwrap(DerivedConfidence.create(
            method="GPRegression", config_ref="a" * 64,
            fit_quality=fq,
        ))
        derived = unwrap(create_attestation(
            value=Decimal("50.5"), confidence=dc,
            source="model", timestamp=_now(),
            provenance=(input1.attestation_id, input2.attestation_id),
        ))
        aid = unwrap(store.store(derived))
        retrieved = unwrap(store.retrieve(aid))
        assert retrieved.provenance == (input1.attestation_id, input2.attestation_id)

    def test_content_addressing_idempotent(self) -> None:
        """Same attestation stored twice produces one copy."""
        store = InMemoryAttestationStore()
        fc = unwrap(FirmConfidence.create("LCH", _now(), "ref-X"))
        att = unwrap(create_attestation(
            value="hello", confidence=fc,
            source="test", timestamp=_now(),
        ))
        r1 = unwrap(store.store(att))
        r2 = unwrap(store.store(att))
        assert r1 == r2
        assert store.count() == 1

    def test_retrieve_nonexistent_returns_err(self) -> None:
        """Retrieving a non-existent attestation_id returns Err."""
        store = InMemoryAttestationStore()
        result = store.retrieve("0" * 64)
        assert isinstance(result, Err)

    def test_full_provenance_chain_walkable(self) -> None:
        """Can walk the full provenance chain from a derived attestation."""
        store = InMemoryAttestationStore()

        # Layer 1: firm observations
        fc1 = unwrap(FirmConfidence.create("NYSE", _now(), "r1"))
        obs1 = unwrap(create_attestation(
            value=Decimal("100"), confidence=fc1,
            source="nyse", timestamp=_now(),
        ))
        fc2 = unwrap(FirmConfidence.create("CME", _now(), "r2"))
        obs2 = unwrap(create_attestation(
            value=Decimal("101"), confidence=fc2,
            source="cme", timestamp=_now(),
        ))
        store.store(obs1)
        store.store(obs2)

        # Layer 2: derived from both observations
        fq = unwrap(FrozenMap.create({"rmse": Decimal("0.01")}))
        dc = unwrap(DerivedConfidence.create("SVI", "b" * 64, fq))
        derived = unwrap(create_attestation(
            value=Decimal("100.5"), confidence=dc,
            source="model", timestamp=_now(),
            provenance=(obs1.attestation_id, obs2.attestation_id),
        ))
        store.store(derived)

        # Walk provenance
        retrieved = unwrap(store.retrieve(derived.attestation_id))
        for prov_id in retrieved.provenance:
            parent = store.retrieve(prov_id)
            assert isinstance(parent, Ok)

    def test_same_value_different_source_distinct_attestation_ids(self) -> None:
        """GAP-01: Same value from different sources => different attestation_ids."""
        store = InMemoryAttestationStore()
        now = _now()

        fc1 = unwrap(FirmConfidence.create("NYSE", now, "ref-1"))
        att1 = unwrap(create_attestation(
            value=Decimal("100"), confidence=fc1,
            source="source-A", timestamp=now,
        ))

        fc2 = unwrap(FirmConfidence.create("CME", now, "ref-2"))
        att2 = unwrap(create_attestation(
            value=Decimal("100"), confidence=fc2,
            source="source-B", timestamp=now,
        ))

        # Same value => same content_hash
        assert att1.content_hash == att2.content_hash

        # Different source => different attestation_id
        assert att1.attestation_id != att2.attestation_id

        # Both stored successfully
        store.store(att1)
        store.store(att2)
        assert store.count() == 2

    def test_attestation_content_hash_stability_across_store_retrieve(self) -> None:
        """content_hash is stable across store/retrieve cycle."""
        store = InMemoryAttestationStore()
        fc = unwrap(FirmConfidence.create("Eurex", _now(), "ref-Z"))
        att = unwrap(create_attestation(
            value={"rate": Decimal("0.05"), "tenor": "1Y"},
            confidence=fc, source="test", timestamp=_now(),
        ))
        original_hash = att.content_hash
        aid = unwrap(store.store(att))
        retrieved = unwrap(store.retrieve(aid))
        assert retrieved.content_hash == original_hash
