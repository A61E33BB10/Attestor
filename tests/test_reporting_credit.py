"""Tests for CDS/swaption reporting — MiFID II, Dodd-Frank, and EMIR."""

from __future__ import annotations

import dataclasses
from decimal import Decimal

from attestor.core.result import Err, Ok, unwrap
from attestor.gateway.parser import parse_cds_order, parse_swaption_order
from attestor.gateway.types import CanonicalOrder
from attestor.instrument.derivative_types import CDSDetail, SwaptionDetail
from attestor.oracle.attestation import FirmConfidence
from attestor.reporting.dodd_frank import (
    DoddFrankSwapReport,
    project_dodd_frank_report,
)
from attestor.reporting.emir import project_emir_report
from attestor.reporting.mifid2 import (
    CDSReportFields,
    SwaptionReportFields,
    project_mifid2_report,
)

# ---------------------------------------------------------------------------
# Shared raw order dicts
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


def _cds_order() -> CanonicalOrder:
    raw = {
        **_BASE,
        "reference_entity": "ACME Corp",
        "spread_bps": "100",
        "seniority": "SENIOR_UNSECURED",
        "protection_side": "BUYER",
        "start_date": "2025-06-17",
        "maturity_date": "2030-06-17",
    }
    return unwrap(parse_cds_order(raw))


def _swaption_order() -> CanonicalOrder:
    raw = {
        **_BASE,
        "instrument_id": "SWN-USD-5Y",
        "swaption_type": "PAYER",
        "expiry_date": "2026-06-15",
        "underlying_fixed_rate": "0.035",
        "underlying_float_index": "SOFR",
        "underlying_tenor_months": "60",
        "settlement_type": "PHYSICAL",
    }
    return unwrap(parse_swaption_order(raw))


def _equity_order() -> CanonicalOrder:
    """An equity order -- not CDS or swaption."""
    from datetime import UTC, date, datetime

    from attestor.core.types import UtcDatetime
    from attestor.gateway.types import OrderSide, OrderType

    ts = UtcDatetime(value=datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC))
    return unwrap(CanonicalOrder.create(
        order_id="EQ-001", instrument_id="AAPL", isin=None,
        side=OrderSide.BUY, quantity=Decimal("100"),
        price=Decimal("175"), currency="USD",
        order_type=OrderType.LIMIT,
        counterparty_lei="529900HNOAA1KXQJUQ27",
        executing_party_lei="529900ODI3JL1O4COU11",
        trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 17),
        venue="XNYS", timestamp=ts,
    ))


# ---------------------------------------------------------------------------
# MiFID II -- CDS
# ---------------------------------------------------------------------------


class TestMiFIDIICDS:
    def test_cds_produces_cds_report_fields(self) -> None:
        """1. MiFID II with CDSDetail produces CDSReportFields."""
        result = project_mifid2_report(_cds_order(), "ATT-CDS-001")
        assert isinstance(result, Ok)
        report = unwrap(result).value
        assert isinstance(report.instrument_fields, CDSReportFields)

    def test_cds_report_field_values(self) -> None:
        """3. CDSReportFields contain correct projected values."""
        order = _cds_order()
        att = unwrap(project_mifid2_report(order, "ATT-CDS-002"))
        fields = att.value.instrument_fields
        assert isinstance(fields, CDSReportFields)
        detail = order.instrument_detail
        assert isinstance(detail, CDSDetail)
        assert fields.reference_entity == detail.reference_entity.value
        assert fields.spread_bps == detail.spread_bps.value
        assert fields.seniority == detail.seniority.value
        assert fields.protection_side == detail.protection_side.value

    def test_cds_report_field_exact_values(self) -> None:
        """3b. CDSReportFields contain the expected literal values."""
        att = unwrap(project_mifid2_report(_cds_order(), "ATT-CDS-003"))
        fields = att.value.instrument_fields
        assert isinstance(fields, CDSReportFields)
        assert fields.reference_entity == "ACME Corp"
        assert fields.spread_bps == Decimal("100")
        assert fields.seniority == "SENIOR_UNSECURED"
        assert fields.protection_side == "BUYER"


# ---------------------------------------------------------------------------
# MiFID II -- Swaption
# ---------------------------------------------------------------------------


class TestMiFIDIISwaption:
    def test_swaption_produces_swaption_report_fields(self) -> None:
        """2. MiFID II with SwaptionDetail produces SwaptionReportFields."""
        result = project_mifid2_report(_swaption_order(), "ATT-SWN-001")
        assert isinstance(result, Ok)
        report = unwrap(result).value
        assert isinstance(report.instrument_fields, SwaptionReportFields)

    def test_swaption_report_field_values(self) -> None:
        """4. SwaptionReportFields contain correct projected values."""
        order = _swaption_order()
        att = unwrap(project_mifid2_report(order, "ATT-SWN-002"))
        fields = att.value.instrument_fields
        assert isinstance(fields, SwaptionReportFields)
        detail = order.instrument_detail
        assert isinstance(detail, SwaptionDetail)
        assert fields.swaption_type == detail.swaption_type.value
        assert fields.expiry_date == detail.expiry_date
        assert fields.underlying_fixed_rate == detail.underlying_fixed_rate
        assert fields.underlying_tenor_months == detail.underlying_tenor_months
        assert fields.settlement_type == detail.settlement_type.value

    def test_swaption_report_field_exact_values(self) -> None:
        """4b. SwaptionReportFields contain expected literal values."""
        from datetime import date

        att = unwrap(project_mifid2_report(_swaption_order(), "ATT-SWN-003"))
        fields = att.value.instrument_fields
        assert isinstance(fields, SwaptionReportFields)
        assert fields.swaption_type == "PAYER"
        assert fields.expiry_date == date(2026, 6, 15)
        assert fields.underlying_fixed_rate == Decimal("0.035")
        assert fields.underlying_tenor_months == 60
        assert fields.settlement_type == "PHYSICAL"


# ---------------------------------------------------------------------------
# Dodd-Frank -- CDS
# ---------------------------------------------------------------------------


class TestDoddFrankCDS:
    def test_cds_report_ok(self) -> None:
        """5. Dodd-Frank CDS report: CDS fields populated, swaption fields None."""
        result = project_dodd_frank_report(_cds_order(), "ATT-DF-001")
        assert isinstance(result, Ok)
        report = unwrap(result).value
        assert isinstance(report, DoddFrankSwapReport)
        assert report.reference_entity is not None
        assert report.spread_bps is not None
        assert report.expiry_date is None
        assert report.underlying_fixed_rate is None

    def test_cds_asset_class(self) -> None:
        """9a. Dodd-Frank: asset_class is 'CREDIT' for CDS."""
        report = unwrap(project_dodd_frank_report(_cds_order(), "ATT-DF-002")).value
        assert report.asset_class.value == "CREDIT"

    def test_cds_product_type(self) -> None:
        """9b. product_type is 'CDS' for CDS orders."""
        report = unwrap(project_dodd_frank_report(_cds_order(), "ATT-DF-003")).value
        assert report.product_type.value == "CDS"

    def test_cds_effective_date_from_start(self) -> None:
        """CDS effective_date comes from CDSDetail.start_date."""
        order = _cds_order()
        report = unwrap(project_dodd_frank_report(order, "ATT-DF-004")).value
        detail = order.instrument_detail
        assert isinstance(detail, CDSDetail)
        assert report.effective_date == detail.start_date

    def test_cds_maturity_date(self) -> None:
        """CDS maturity_date comes from CDSDetail.maturity_date."""
        order = _cds_order()
        report = unwrap(project_dodd_frank_report(order, "ATT-DF-005")).value
        detail = order.instrument_detail
        assert isinstance(detail, CDSDetail)
        assert report.maturity_date == detail.maturity_date


# ---------------------------------------------------------------------------
# Dodd-Frank -- Swaption
# ---------------------------------------------------------------------------


class TestDoddFrankSwaption:
    def test_swaption_report_ok(self) -> None:
        """6. Dodd-Frank swaption report: swaption fields populated, CDS fields None."""
        result = project_dodd_frank_report(_swaption_order(), "ATT-DF-010")
        assert isinstance(result, Ok)
        report = unwrap(result).value
        assert isinstance(report, DoddFrankSwapReport)
        assert report.expiry_date is not None
        assert report.underlying_fixed_rate is not None
        assert report.reference_entity is None
        assert report.spread_bps is None

    def test_swaption_asset_class(self) -> None:
        """9c. Dodd-Frank: asset_class is 'INTEREST_RATE' for swaption."""
        report = unwrap(
            project_dodd_frank_report(_swaption_order(), "ATT-DF-011")
        ).value
        assert report.asset_class.value == "INTEREST_RATE"

    def test_swaption_product_type(self) -> None:
        """9d. product_type is 'SWAPTION' for swaption orders."""
        report = unwrap(
            project_dodd_frank_report(_swaption_order(), "ATT-DF-012")
        ).value
        assert report.product_type.value == "SWAPTION"


# ---------------------------------------------------------------------------
# Dodd-Frank -- rejection and USI
# ---------------------------------------------------------------------------


class TestDoddFrankRejection:
    def test_non_cds_non_swaption_err(self) -> None:
        """7. Dodd-Frank: non-CDS/non-swaption order returns Err."""
        result = project_dodd_frank_report(_equity_order(), "ATT-DF-020")
        assert isinstance(result, Err)

    def test_usi_generated(self) -> None:
        """8. Dodd-Frank: USI is generated and non-empty."""
        report = unwrap(project_dodd_frank_report(_cds_order(), "ATT-DF-021")).value
        assert report.usi.value != ""
        assert len(report.usi.value) > 0

    def test_usi_starts_with_lei(self) -> None:
        """USI starts with the executing party LEI."""
        order = _cds_order()
        report = unwrap(project_dodd_frank_report(order, "ATT-DF-022")).value
        assert report.usi.value.startswith(order.executing_party_lei.value)


# ---------------------------------------------------------------------------
# EMIR -- CDS/swaption (generic projection, no instrument-specific fields)
# ---------------------------------------------------------------------------


class TestEMIRCredit:
    def test_emir_cds_report_ok(self) -> None:
        """10. EMIR with CDS order produces valid report."""
        result = project_emir_report(_cds_order(), "ATT-EMIR-001")
        assert isinstance(result, Ok)
        report = unwrap(result).value
        assert report.instrument_id.value == "CDS-ITRAXX-001"

    def test_emir_swaption_report_ok(self) -> None:
        """11. EMIR with swaption order produces valid report."""
        result = project_emir_report(_swaption_order(), "ATT-EMIR-002")
        assert isinstance(result, Ok)
        report = unwrap(result).value
        assert report.instrument_id.value == "SWN-USD-5Y"

    def test_emir_cds_instrument_fields(self) -> None:
        """EMIR CDS report has CDSReportFields with correct values."""
        report = unwrap(project_emir_report(_cds_order(), "ATT-EMIR-003")).value
        assert isinstance(report.instrument_fields, CDSReportFields)
        assert report.instrument_fields.reference_entity == "ACME Corp"
        assert report.instrument_fields.spread_bps == Decimal("100")
        assert report.instrument_fields.seniority == "SENIOR_UNSECURED"
        assert report.instrument_fields.protection_side == "BUYER"

    def test_emir_swaption_instrument_fields(self) -> None:
        """EMIR swaption report has SwaptionReportFields with correct values."""
        from datetime import date

        report = unwrap(project_emir_report(_swaption_order(), "ATT-EMIR-004")).value
        assert isinstance(report.instrument_fields, SwaptionReportFields)
        assert report.instrument_fields.swaption_type == "PAYER"
        assert report.instrument_fields.expiry_date == date(2026, 6, 15)
        assert report.instrument_fields.underlying_fixed_rate == Decimal("0.035")
        assert report.instrument_fields.underlying_tenor_months == 60
        assert report.instrument_fields.settlement_type == "PHYSICAL"

    def test_emir_equity_has_no_instrument_fields(self) -> None:
        """EMIR report for non-CDS/swaption has instrument_fields=None."""
        report = unwrap(project_emir_report(_equity_order(), "ATT-EMIR-005")).value
        assert report.instrument_fields is None


# ---------------------------------------------------------------------------
# Provenance / attestation
# ---------------------------------------------------------------------------


class TestReportProvenance:
    def test_dodd_frank_provenance_contains_trade_attestation_id(self) -> None:
        """12. Report attestation has provenance containing trade_attestation_id."""
        att = unwrap(project_dodd_frank_report(_cds_order(), "ATT-PROV-001"))
        assert "ATT-PROV-001" in att.provenance

    def test_dodd_frank_confidence_is_firm(self) -> None:
        """Dodd-Frank report confidence is FirmConfidence."""
        att = unwrap(project_dodd_frank_report(_cds_order(), "ATT-PROV-002"))
        assert isinstance(att.confidence, FirmConfidence)

    def test_dodd_frank_source(self) -> None:
        """Dodd-Frank report source is 'dodd-frank-reporter'."""
        att = unwrap(project_dodd_frank_report(_cds_order(), "ATT-PROV-003"))
        assert att.source.value == "dodd-frank-reporter"


# ---------------------------------------------------------------------------
# Frozen invariants
# ---------------------------------------------------------------------------


class TestFrozenInvariants:
    def test_cds_report_fields_frozen(self) -> None:
        """13. CDSReportFields is frozen."""
        fields = CDSReportFields(
            reference_entity="ACME",
            spread_bps=Decimal("100"),
            seniority="SENIOR_UNSECURED",
            protection_side="BUYER",
        )
        assert dataclasses.is_dataclass(fields)
        try:
            fields.reference_entity = "OTHER"  # type: ignore[misc]
            raised = False
        except (dataclasses.FrozenInstanceError, AttributeError):
            raised = True
        assert raised

    def test_swaption_report_fields_frozen(self) -> None:
        """14. SwaptionReportFields is frozen."""
        from datetime import date

        fields = SwaptionReportFields(
            swaption_type="PAYER",
            expiry_date=date(2026, 6, 15),
            underlying_fixed_rate=Decimal("0.035"),
            underlying_tenor_months=60,
            settlement_type="PHYSICAL",
        )
        assert dataclasses.is_dataclass(fields)
        try:
            fields.swaption_type = "RECEIVER"  # type: ignore[misc]
            raised = False
        except (dataclasses.FrozenInstanceError, AttributeError):
            raised = True
        assert raised

    def test_dodd_frank_swap_report_frozen(self) -> None:
        """15. DoddFrankSwapReport is frozen."""
        report = unwrap(project_dodd_frank_report(_cds_order(), "ATT-FZ-001")).value
        assert dataclasses.is_dataclass(report)
        try:
            report.usi = report.usi  # type: ignore[misc]
            raised = False
        except (dataclasses.FrozenInstanceError, AttributeError):
            raised = True
        assert raised
