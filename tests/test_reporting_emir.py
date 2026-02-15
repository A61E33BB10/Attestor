"""Tests for attestor.reporting.emir — EMIR trade report projection."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import UtcDatetime
from attestor.gateway.types import CanonicalOrder, OrderSide, OrderType
from attestor.oracle.attestation import FirmConfidence
from attestor.reporting.emir import EMIRTradeReport, project_emir_report

_TS = UtcDatetime(value=datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC))


def _order(side: OrderSide = OrderSide.BUY) -> CanonicalOrder:
    return unwrap(CanonicalOrder.create(
        order_id="ORD-001", instrument_id="AAPL", isin=None,
        side=side, quantity=Decimal("100"), price=Decimal("175.50"),
        currency="USD", order_type=OrderType.LIMIT,
        counterparty_lei="529900HNOAA1KXQJUQ27",
        executing_party_lei="529900ODI3JL1O4COU11",
        trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 17),
        venue="XNYS", timestamp=_TS,
    ))


# ---------------------------------------------------------------------------
# Valid projection
# ---------------------------------------------------------------------------


class TestProjectEMIRReport:
    def test_valid_projection(self) -> None:
        order = _order()
        result = project_emir_report(order, "ATT-12345")
        assert isinstance(result, Ok)
        att = result.value
        assert isinstance(att.value, EMIRTradeReport)
        assert isinstance(att.confidence, FirmConfidence)

    def test_report_fields_match_order(self) -> None:
        """INV-R01: report fields are a strict subset of order fields."""
        order = _order()
        report = unwrap(project_emir_report(order, "ATT-12345")).value
        assert report.reporting_counterparty_lei == order.executing_party_lei
        assert report.other_counterparty_lei == order.counterparty_lei
        assert report.instrument_id == order.instrument_id
        assert report.isin == order.isin
        assert report.direction == order.side
        assert report.quantity == order.quantity
        assert report.price == order.price
        assert report.currency == order.currency
        assert report.trade_date == order.trade_date
        assert report.settlement_date == order.settlement_date
        assert report.venue == order.venue

    def test_uti_format(self) -> None:
        order = _order()
        report = unwrap(project_emir_report(order, "ATT-12345")).value
        # UTI is LEI (20 chars) + 32 hex chars = 52 chars
        assert len(report.uti.value) == 52
        # First 20 chars = executing party LEI
        assert report.uti.value[:20] == order.executing_party_lei.value

    def test_attestation_refs(self) -> None:
        order = _order()
        report = unwrap(project_emir_report(order, "ATT-12345")).value
        assert report.attestation_refs == ("ATT-12345",)

    def test_provenance_chain(self) -> None:
        order = _order()
        att = unwrap(project_emir_report(order, "ATT-12345"))
        assert att.provenance == ("ATT-12345",)

    def test_idempotency(self) -> None:
        """Same order → same report content_hash."""
        order = _order()
        a1 = unwrap(project_emir_report(order, "ATT-12345"))
        a2 = unwrap(project_emir_report(order, "ATT-12345"))
        assert a1.content_hash == a2.content_hash

    def test_buy_direction(self) -> None:
        order = _order(side=OrderSide.BUY)
        report = unwrap(project_emir_report(order, "ATT-001")).value
        assert report.direction is OrderSide.BUY

    def test_sell_direction(self) -> None:
        order = _order(side=OrderSide.SELL)
        report = unwrap(project_emir_report(order, "ATT-002")).value
        assert report.direction is OrderSide.SELL

    def test_report_is_attestation(self) -> None:
        order = _order()
        att = unwrap(project_emir_report(order, "ATT-001"))
        assert att.source.value == "EMIR_REPORTING"
        assert att.content_hash  # non-empty
        assert att.attestation_id  # non-empty
