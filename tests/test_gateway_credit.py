"""Tests for CDS and swaption gateway parsers."""

from __future__ import annotations

from decimal import Decimal

from attestor.core.result import Err, Ok, unwrap
from attestor.gateway.parser import parse_cds_order, parse_swaption_order
from attestor.instrument.derivative_types import (
    CDSDetail,
    ProtectionSide,
    SeniorityLevel,
    SettlementTypeEnum,
    SwaptionDetail,
    SwaptionType,
)

# ---------------------------------------------------------------------------
# Shared base fields
# ---------------------------------------------------------------------------

_BASE: dict[str, object] = {
    "order_id": "ORD-CR-001",
    "instrument_id": "CDS-ITRAXX-001",
    "side": "BUY",
    "quantity": "10000000",
    "price": "100",
    "currency": "USD",
    "order_type": "MARKET",
    "counterparty_lei": "529900HNOAA1KXQJUQ27",
    "executing_party_lei": "529900ODI3JL1O4COU11",
    "trade_date": "2025-06-15",
    "venue": "XSWP",
    "timestamp": "2025-06-15T10:00:00+00:00",
}


def _with(**overrides: object) -> dict[str, object]:
    return {**_BASE, **overrides}


# ---------------------------------------------------------------------------
# parse_cds_order
# ---------------------------------------------------------------------------


class TestParseCDSOrder:
    def test_valid_produces_canonical_order(self) -> None:
        raw = _with(
            reference_entity="ACME Corp",
            spread_bps="100",
            seniority="SeniorUnsecured",
            protection_side="Buyer",
            start_date="2025-06-17",
            maturity_date="2030-06-17",
        )
        result = parse_cds_order(raw)
        assert isinstance(result, Ok)
        order = unwrap(result)
        assert isinstance(order.instrument_detail, CDSDetail)

    def test_missing_reference_entity_err(self) -> None:
        raw = _with(
            spread_bps="100",
            seniority="SeniorUnsecured",
            protection_side="Buyer",
            start_date="2025-06-17",
            maturity_date="2030-06-17",
        )
        result = parse_cds_order(raw)
        assert isinstance(result, Err)

    def test_invalid_seniority_err(self) -> None:
        raw = _with(
            reference_entity="ACME Corp",
            spread_bps="100",
            seniority="MEZZANINE",
            protection_side="Buyer",
            start_date="2025-06-17",
            maturity_date="2030-06-17",
        )
        result = parse_cds_order(raw)
        assert isinstance(result, Err)

    def test_maturity_before_start_err(self) -> None:
        raw = _with(
            reference_entity="ACME Corp",
            spread_bps="100",
            seniority="SeniorUnsecured",
            protection_side="Buyer",
            start_date="2030-06-17",
            maturity_date="2025-06-17",
        )
        result = parse_cds_order(raw)
        assert isinstance(result, Err)

    def test_negative_spread_err(self) -> None:
        raw = _with(
            reference_entity="ACME Corp",
            spread_bps="-50",
            seniority="SeniorUnsecured",
            protection_side="Buyer",
            start_date="2025-06-17",
            maturity_date="2030-06-17",
        )
        result = parse_cds_order(raw)
        assert isinstance(result, Err)

    def test_instrument_detail_is_cds_detail(self) -> None:
        raw = _with(
            reference_entity="ACME Corp",
            spread_bps="100",
            seniority="Subordinated",
            protection_side="Seller",
            start_date="2025-06-17",
            maturity_date="2030-06-17",
        )
        order = unwrap(parse_cds_order(raw))
        detail = order.instrument_detail
        assert isinstance(detail, CDSDetail)
        assert not isinstance(detail, SwaptionDetail)

    def test_settlement_date_defaults_to_t_plus_1(self) -> None:
        raw = _with(
            reference_entity="ACME Corp",
            spread_bps="100",
            seniority="SeniorUnsecured",
            protection_side="Buyer",
            start_date="2025-06-17",
            maturity_date="2030-06-17",
        )
        assert "settlement_date" not in raw
        order = unwrap(parse_cds_order(raw))
        # trade_date 2025-06-15 (Sunday) + 1 bday = Monday 2025-06-16
        assert order.settlement_date > order.trade_date


# ---------------------------------------------------------------------------
# parse_swaption_order
# ---------------------------------------------------------------------------


class TestParseSwaptionOrder:
    def test_valid_produces_canonical_order(self) -> None:
        raw = _with(
            swaption_type="Payer",
            expiry_date="2026-06-15",
            underlying_fixed_rate="0.035",
            underlying_float_index="SOFR",
            underlying_tenor_months="60",
            settlement_type="Physical",
        )
        result = parse_swaption_order(raw)
        assert isinstance(result, Ok)
        order = unwrap(result)
        assert isinstance(order.instrument_detail, SwaptionDetail)

    def test_invalid_swaption_type_err(self) -> None:
        raw = _with(
            swaption_type="STRADDLE",
            expiry_date="2026-06-15",
            underlying_fixed_rate="0.035",
            underlying_float_index="SOFR",
            underlying_tenor_months="60",
            settlement_type="Physical",
        )
        result = parse_swaption_order(raw)
        assert isinstance(result, Err)

    def test_negative_underlying_fixed_rate_ok(self) -> None:
        raw = _with(
            swaption_type="Payer",
            expiry_date="2026-06-15",
            underlying_fixed_rate="-0.01",
            underlying_float_index="SOFR",
            underlying_tenor_months="60",
            settlement_type="Physical",
        )
        result = parse_swaption_order(raw)
        assert isinstance(result, Ok)
        assert result.value.instrument_detail.underlying_fixed_rate == Decimal("-0.01")

    def test_zero_tenor_months_err(self) -> None:
        raw = _with(
            swaption_type="Payer",
            expiry_date="2026-06-15",
            underlying_fixed_rate="0.035",
            underlying_float_index="SOFR",
            underlying_tenor_months="0",
            settlement_type="Physical",
        )
        result = parse_swaption_order(raw)
        assert isinstance(result, Err)

    def test_instrument_detail_is_swaption_detail(self) -> None:
        raw = _with(
            swaption_type="Receiver",
            expiry_date="2026-06-15",
            underlying_fixed_rate="0.035",
            underlying_float_index="SOFR",
            underlying_tenor_months="60",
            settlement_type="Cash",
        )
        order = unwrap(parse_swaption_order(raw))
        detail = order.instrument_detail
        assert isinstance(detail, SwaptionDetail)
        assert not isinstance(detail, CDSDetail)

    def test_settlement_date_defaults_to_t_plus_1(self) -> None:
        raw = _with(
            swaption_type="Payer",
            expiry_date="2026-06-15",
            underlying_fixed_rate="0.035",
            underlying_float_index="SOFR",
            underlying_tenor_months="60",
            settlement_type="Physical",
        )
        assert "settlement_date" not in raw
        order = unwrap(parse_swaption_order(raw))
        assert order.settlement_date > order.trade_date


# ---------------------------------------------------------------------------
# Invariants: idempotency (INV-G01)
# ---------------------------------------------------------------------------


class TestIdempotency:
    """INV-G01: parsing twice with same input gives same result."""

    def test_cds_idempotent(self) -> None:
        raw = _with(
            reference_entity="ACME Corp",
            spread_bps="100",
            seniority="SeniorUnsecured",
            protection_side="Buyer",
            start_date="2025-06-17",
            maturity_date="2030-06-17",
        )
        r1 = parse_cds_order(raw)
        r2 = parse_cds_order(raw)
        assert isinstance(r1, Ok) and isinstance(r2, Ok)
        o1 = unwrap(r1)
        o2 = unwrap(r2)
        assert o1.order_id == o2.order_id
        assert o1.instrument_detail == o2.instrument_detail

    def test_swaption_idempotent(self) -> None:
        raw = _with(
            swaption_type="Payer",
            expiry_date="2026-06-15",
            underlying_fixed_rate="0.035",
            underlying_float_index="SOFR",
            underlying_tenor_months="60",
            settlement_type="Physical",
        )
        r1 = parse_swaption_order(raw)
        r2 = parse_swaption_order(raw)
        assert isinstance(r1, Ok) and isinstance(r2, Ok)
        o1 = unwrap(r1)
        o2 = unwrap(r2)
        assert o1.order_id == o2.order_id
        assert o1.instrument_detail == o2.instrument_detail


# ---------------------------------------------------------------------------
# Invariants: totality (INV-G02)
# ---------------------------------------------------------------------------


class TestTotality:
    """INV-G02: parsers never raise, always return Ok or Err."""

    def test_cds_empty_dict(self) -> None:
        result = parse_cds_order({})
        assert isinstance(result, Err)

    def test_swaption_empty_dict(self) -> None:
        result = parse_swaption_order({})
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Integration: field values match raw input
# ---------------------------------------------------------------------------


class TestFieldValueIntegration:
    def test_cds_fields_match_raw(self) -> None:
        raw = _with(
            reference_entity="ACME Corp",
            spread_bps="100",
            seniority="SeniorUnsecured",
            protection_side="Buyer",
            start_date="2025-06-17",
            maturity_date="2030-06-17",
        )
        order = unwrap(parse_cds_order(raw))
        detail = order.instrument_detail
        assert isinstance(detail, CDSDetail)
        assert detail.reference_entity.value == "ACME Corp"
        assert detail.spread_bps.value == Decimal("100")
        assert detail.seniority is SeniorityLevel.SENIOR_UNSECURED
        assert detail.protection_side is ProtectionSide.BUYER
        from datetime import date
        assert detail.start_date == date(2025, 6, 17)
        assert detail.maturity_date == date(2030, 6, 17)

    def test_swaption_fields_match_raw(self) -> None:
        raw = _with(
            swaption_type="Receiver",
            expiry_date="2026-06-15",
            underlying_fixed_rate="0.035",
            underlying_float_index="SOFR",
            underlying_tenor_months="60",
            settlement_type="Cash",
        )
        order = unwrap(parse_swaption_order(raw))
        detail = order.instrument_detail
        assert isinstance(detail, SwaptionDetail)
        assert detail.swaption_type is SwaptionType.RECEIVER
        from datetime import date
        assert detail.expiry_date == date(2026, 6, 15)
        assert detail.underlying_fixed_rate == Decimal("0.035")
        assert detail.underlying_float_index.value == "SOFR"
        assert detail.underlying_tenor_months == 60
        assert detail.settlement_type is SettlementTypeEnum.CASH
