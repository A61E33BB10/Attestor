"""Tests for attestor.oracle.attestation — Attestation + Confidence types."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import FrozenMap, UtcDatetime
from attestor.oracle.attestation import (
    DerivedConfidence,
    FirmConfidence,
    QuoteCondition,
    QuotedConfidence,
    create_attestation,
)


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _fq() -> FrozenMap[str, Decimal]:
    return unwrap(FrozenMap.create({"rmse": Decimal("0.001")}))


# ---------------------------------------------------------------------------
# FirmConfidence (GAP-12, GAP-20)
# ---------------------------------------------------------------------------


class TestFirmConfidence:
    def test_create_valid_ok(self) -> None:
        result = FirmConfidence.create("EXCHANGE", _now(), "ref-123")
        assert isinstance(result, Ok)

    def test_create_empty_source_err(self) -> None:
        result = FirmConfidence.create("", _now(), "ref-123")
        assert isinstance(result, Err)

    def test_create_empty_ref_err(self) -> None:
        result = FirmConfidence.create("EXCHANGE", _now(), "")
        assert isinstance(result, Err)

    def test_create_naive_timestamp_err(self) -> None:
        result = FirmConfidence.create("EXCHANGE", datetime(2024, 1, 1), "ref")  # noqa: DTZ001
        assert isinstance(result, Err)

    def test_timestamp_is_utc_datetime(self) -> None:
        fc = unwrap(FirmConfidence.create("EXCHANGE", _now(), "ref-123"))
        assert isinstance(fc.timestamp, UtcDatetime)

    def test_frozen(self) -> None:
        fc = unwrap(FirmConfidence.create("EXCHANGE", _now(), "ref-123"))
        with pytest.raises(dataclasses.FrozenInstanceError):
            fc.source = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# QuotedConfidence (GAP-06)
# ---------------------------------------------------------------------------


class TestQuotedConfidence:
    def test_create_valid_ok(self) -> None:
        result = QuotedConfidence.create(Decimal("154.90"), Decimal("155.10"), "NYSE")
        assert isinstance(result, Ok)

    def test_create_bid_gt_ask_err(self) -> None:
        result = QuotedConfidence.create(Decimal("155.10"), Decimal("154.90"), "NYSE")
        assert isinstance(result, Err)
        assert "negative spread" in result.error

    def test_create_bid_eq_ask_ok(self) -> None:
        result = QuotedConfidence.create(Decimal("155"), Decimal("155"), "NYSE")
        assert isinstance(result, Ok)

    def test_create_empty_venue_err(self) -> None:
        result = QuotedConfidence.create(Decimal("1"), Decimal("2"), "")
        assert isinstance(result, Err)

    def test_mid_property(self) -> None:
        qc = unwrap(QuotedConfidence.create(Decimal("100"), Decimal("102"), "V"))
        assert qc.mid == Decimal("101")

    def test_spread_property(self) -> None:
        qc = unwrap(QuotedConfidence.create(Decimal("100"), Decimal("102"), "V"))
        assert qc.spread == Decimal("2")

    def test_half_spread_property(self) -> None:
        qc = unwrap(QuotedConfidence.create(Decimal("100"), Decimal("102"), "V"))
        assert qc.half_spread == Decimal("1")

    def test_conditions_is_enum(self) -> None:
        qc = unwrap(QuotedConfidence.create(
            Decimal("1"), Decimal("2"), "V", conditions=QuoteCondition.FIRM,
        ))
        assert qc.conditions == QuoteCondition.FIRM

    def test_size_optional(self) -> None:
        qc = unwrap(QuotedConfidence.create(
            Decimal("1"), Decimal("2"), "V", size=Decimal("1000"),
        ))
        assert qc.size == Decimal("1000")


# ---------------------------------------------------------------------------
# DerivedConfidence (GAP-07, GAP-31)
# ---------------------------------------------------------------------------


class TestDerivedConfidence:
    def test_create_valid_ok(self) -> None:
        result = DerivedConfidence.create("SABR", "cfg-1", _fq())
        assert isinstance(result, Ok)

    def test_create_empty_fit_quality_err(self) -> None:
        empty = unwrap(FrozenMap.create({}))
        result = DerivedConfidence.create("SABR", "cfg-1", empty)
        assert isinstance(result, Err)
        assert "fit_quality" in result.error

    def test_create_interval_without_level_err(self) -> None:
        result = DerivedConfidence.create(
            "SABR", "cfg-1", _fq(),
            confidence_interval=(Decimal("0.9"), Decimal("1.1")),
            confidence_level=None,
        )
        assert isinstance(result, Err)

    def test_create_level_without_interval_err(self) -> None:
        result = DerivedConfidence.create(
            "SABR", "cfg-1", _fq(),
            confidence_interval=None,
            confidence_level=Decimal("0.95"),
        )
        assert isinstance(result, Err)

    def test_create_both_none_ok(self) -> None:
        result = DerivedConfidence.create("SABR", "cfg-1", _fq())
        assert isinstance(result, Ok)

    def test_create_both_present_ok(self) -> None:
        result = DerivedConfidence.create(
            "SABR", "cfg-1", _fq(),
            confidence_interval=(Decimal("0.9"), Decimal("1.1")),
            confidence_level=Decimal("0.95"),
        )
        assert isinstance(result, Ok)

    def test_create_level_out_of_range_err(self) -> None:
        result = DerivedConfidence.create(
            "SABR", "cfg-1", _fq(),
            confidence_interval=(Decimal("0.9"), Decimal("1.1")),
            confidence_level=Decimal("1.5"),
        )
        assert isinstance(result, Err)
        assert "confidence_level" in result.error

    def test_create_level_zero_err(self) -> None:
        result = DerivedConfidence.create(
            "SABR", "cfg-1", _fq(),
            confidence_interval=(Decimal("0.9"), Decimal("1.1")),
            confidence_level=Decimal("0"),
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Attestation (GAP-01, GAP-04)
# ---------------------------------------------------------------------------


class TestAttestation:
    def test_create_returns_result(self) -> None:
        fc = unwrap(FirmConfidence.create("SRC", _now(), "ref"))
        result = create_attestation(42, fc, "oracle.price", _now())
        assert isinstance(result, Ok)

    def test_has_attestation_id(self) -> None:
        fc = unwrap(FirmConfidence.create("SRC", _now(), "ref"))
        att = unwrap(create_attestation(42, fc, "oracle.price", _now()))
        assert att.attestation_id != att.content_hash

    def test_attestation_id_differs_for_same_value_different_source(self) -> None:
        """GAP-01: attestation_id encodes source, so different sources -> different ids."""
        fc = unwrap(FirmConfidence.create("SRC", _now(), "ref"))
        ts = _now()
        a1 = unwrap(create_attestation(42, fc, "source_A", ts))
        a2 = unwrap(create_attestation(42, fc, "source_B", ts))
        assert a1.content_hash == a2.content_hash  # same value
        assert a1.attestation_id != a2.attestation_id  # different source

    def test_content_hash_same_for_same_value(self) -> None:
        fc = unwrap(FirmConfidence.create("SRC", _now(), "ref"))
        a1 = unwrap(create_attestation(42, fc, "src", _now()))
        a2 = unwrap(create_attestation(42, fc, "src", _now()))
        assert a1.content_hash == a2.content_hash

    def test_create_unsupported_type_err(self) -> None:
        """GAP-04: unsupported value type returns Err."""
        fc = unwrap(FirmConfidence.create("SRC", _now(), "ref"))
        result = create_attestation(object(), fc, "src", _now())
        assert isinstance(result, Err)

    def test_frozen(self) -> None:
        fc = unwrap(FirmConfidence.create("SRC", _now(), "ref"))
        att = unwrap(create_attestation(42, fc, "src", _now()))
        with pytest.raises(dataclasses.FrozenInstanceError):
            att.value = 99  # type: ignore[misc]

    def test_attestation_id_deterministic(self) -> None:
        fc = unwrap(FirmConfidence.create("SRC", _now(), "ref"))
        ts = _now()
        a1 = unwrap(create_attestation("data", fc, "src", ts))
        a2 = unwrap(create_attestation("data", fc, "src", ts))
        assert a1.attestation_id == a2.attestation_id

    def test_provenance(self) -> None:
        fc = unwrap(FirmConfidence.create("SRC", _now(), "ref"))
        att = unwrap(create_attestation(42, fc, "src", _now(), provenance=("step1", "step2")))
        assert att.provenance == ("step1", "step2")


# ---------------------------------------------------------------------------
# Property-based
# ---------------------------------------------------------------------------


class TestProperties:
    @given(
        bid=st.decimals(min_value=Decimal("0"), max_value=Decimal("1000"),
                        allow_nan=False, allow_infinity=False, places=2),
        spread=st.decimals(min_value=Decimal("0"), max_value=Decimal("10"),
                           allow_nan=False, allow_infinity=False, places=2),
    )
    def test_quoted_bid_leq_ask(self, bid: Decimal, spread: Decimal) -> None:
        ask = bid + spread
        qc = unwrap(QuotedConfidence.create(bid, ask, "V"))
        assert qc.bid <= qc.ask

    @given(st.integers())
    def test_attestation_id_stability(self, x: int) -> None:
        fc = unwrap(FirmConfidence.create("SRC", _now(), "ref"))
        ts = _now()
        a1 = unwrap(create_attestation(x, fc, "src", ts))
        a2 = unwrap(create_attestation(x, fc, "src", ts))
        assert a1.attestation_id == a2.attestation_id
