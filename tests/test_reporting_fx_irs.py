"""Tests for reporting extensions — MiFID II and EMIR with FX/IRS orders."""

from __future__ import annotations

from decimal import Decimal

from attestor.core.result import Ok, unwrap
from attestor.gateway.parser import parse_fx_forward_order, parse_fx_spot_order, parse_irs_order
from attestor.gateway.types import CanonicalOrder
from attestor.instrument.derivative_types import IRSwapDetail
from attestor.reporting.emir import project_emir_report
from attestor.reporting.mifid2 import (
    FXReportFields,
    IRSwapReportFields,
    project_mifid2_report,
)

_BASE: dict[str, object] = {
    "order_id": "ORD-RPT-001",
    "instrument_id": "EURUSD-SPOT",
    "side": "BUY",
    "quantity": "1000000",
    "price": "1.0850",
    "currency": "USD",
    "order_type": "MARKET",
    "counterparty_lei": "529900HNOAA1KXQJUQ27",
    "executing_party_lei": "529900ODI3JL1O4COU11",
    "trade_date": "2025-06-15",
    "venue": "XFOR",
    "timestamp": "2025-06-15T10:00:00+00:00",
}


def _fx_spot_order() -> CanonicalOrder:
    raw = {**_BASE, "currency_pair": "EUR/USD"}
    return unwrap(parse_fx_spot_order(raw))


def _fx_forward_order() -> CanonicalOrder:
    raw = {
        **_BASE,
        "currency_pair": "EUR/USD",
        "forward_rate": "1.0920",
        "settlement_date": "2025-09-15",
    }
    return unwrap(parse_fx_forward_order(raw))


def _irs_order() -> CanonicalOrder:
    raw = {
        **_BASE,
        "instrument_id": "IRS-USD-5Y",
        "fixed_rate": "0.035",
        "float_index": "SOFR",
        "day_count": "ACT/360",
        "payment_frequency": "QUARTERLY",
        "tenor_months": "60",
        "start_date": "2025-06-15",
        "end_date": "2030-06-15",
    }
    return unwrap(parse_irs_order(raw))


# ---------------------------------------------------------------------------
# MiFID II — FX
# ---------------------------------------------------------------------------


class TestMiFIDIIFXReport:
    def test_fx_spot_report_ok(self) -> None:
        result = project_mifid2_report(_fx_spot_order(), "ATT-001")
        assert isinstance(result, Ok)

    def test_fx_spot_fields(self) -> None:
        att = unwrap(project_mifid2_report(_fx_spot_order(), "ATT-001"))
        report = att.value
        assert isinstance(report.instrument_fields, FXReportFields)
        assert report.instrument_fields.currency_pair == "EUR/USD"
        assert report.instrument_fields.forward_rate is None

    def test_fx_forward_fields(self) -> None:
        att = unwrap(project_mifid2_report(_fx_forward_order(), "ATT-002"))
        report = att.value
        assert isinstance(report.instrument_fields, FXReportFields)
        assert report.instrument_fields.forward_rate == Decimal("1.0920")

    def test_fx_settlement_type(self) -> None:
        att = unwrap(project_mifid2_report(_fx_spot_order(), "ATT-001"))
        fields = att.value.instrument_fields
        assert isinstance(fields, FXReportFields)
        assert fields.settlement_type == "PHYSICAL"

    def test_fx_provenance(self) -> None:
        att = unwrap(project_mifid2_report(_fx_spot_order(), "ATT-001"))
        assert att.content_hash != ""
        assert "ATT-001" in att.value.attestation_refs


# ---------------------------------------------------------------------------
# MiFID II — IRS
# ---------------------------------------------------------------------------


class TestMiFIDIIIRSReport:
    def test_irs_report_ok(self) -> None:
        result = project_mifid2_report(_irs_order(), "ATT-003")
        assert isinstance(result, Ok)

    def test_irs_fields(self) -> None:
        att = unwrap(project_mifid2_report(_irs_order(), "ATT-003"))
        report = att.value
        assert isinstance(report.instrument_fields, IRSwapReportFields)
        assert report.instrument_fields.fixed_rate == Decimal("0.035")
        assert report.instrument_fields.float_index == "SOFR"
        assert report.instrument_fields.day_count == "ACT/360"
        assert report.instrument_fields.tenor_months == 60

    def test_irs_notional_currency(self) -> None:
        att = unwrap(project_mifid2_report(_irs_order(), "ATT-003"))
        fields = att.value.instrument_fields
        assert isinstance(fields, IRSwapReportFields)
        assert fields.notional_currency == "USD"


# ---------------------------------------------------------------------------
# EMIR — FX/IRS (generic projection — no instrument-specific fields)
# ---------------------------------------------------------------------------


class TestEMIRFXReport:
    def test_fx_spot_report_ok(self) -> None:
        result = project_emir_report(_fx_spot_order(), "ATT-001")
        assert isinstance(result, Ok)

    def test_fx_fields_projected(self) -> None:
        att = unwrap(project_emir_report(_fx_spot_order(), "ATT-001"))
        report = att.value
        assert report.instrument_id.value == "EURUSD-SPOT"
        assert report.quantity.value == Decimal("1000000")

    def test_fx_provenance(self) -> None:
        att = unwrap(project_emir_report(_fx_spot_order(), "ATT-001"))
        assert "ATT-001" in att.value.attestation_refs


class TestEMIRIRSReport:
    def test_irs_report_ok(self) -> None:
        result = project_emir_report(_irs_order(), "ATT-003")
        assert isinstance(result, Ok)

    def test_irs_fields_projected(self) -> None:
        att = unwrap(project_emir_report(_irs_order(), "ATT-003"))
        report = att.value
        assert report.instrument_id.value == "IRS-USD-5Y"


# ---------------------------------------------------------------------------
# INV-R01: Projection only — no new values computed
# ---------------------------------------------------------------------------


class TestReportingProjection:
    def test_mifid_fx_no_new_values(self) -> None:
        """Report fields come only from order, not computed."""
        order = _fx_spot_order()
        att = unwrap(project_mifid2_report(order, "ATT-001"))
        report = att.value
        # All report values are projections of order values
        assert report.price == order.price
        assert report.quantity == order.quantity
        assert report.trade_date == order.trade_date

    def test_mifid_irs_no_new_values(self) -> None:
        order = _irs_order()
        att = unwrap(project_mifid2_report(order, "ATT-003"))
        report = att.value
        detail = order.instrument_detail
        assert isinstance(detail, IRSwapDetail)
        fields = report.instrument_fields
        assert isinstance(fields, IRSwapReportFields)
        # All fields projected from detail, not computed
        assert fields.fixed_rate == detail.fixed_rate
        assert fields.float_index == detail.float_index.value
