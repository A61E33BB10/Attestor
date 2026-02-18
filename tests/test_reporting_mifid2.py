"""Tests for attestor.reporting.mifid2 — MiFID II reporting."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import UtcDatetime
from attestor.gateway.types import CanonicalOrder, OrderSide, OrderType
from attestor.instrument.derivative_types import (
    FuturesDetail,
    OptionDetail,
    OptionExerciseStyleEnum,
    OptionTypeEnum,
    SettlementTypeEnum,
)
from attestor.reporting.mifid2 import (
    FuturesReportFields,
    MiFIDIIReport,
    OptionReportFields,
    project_mifid2_report,
)

_TS = UtcDatetime(value=datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC))
_LEI_A = "529900HNOAA1KXQJUQ27"
_LEI_B = "529900ODI3JL1O4COU11"


def _equity_order() -> CanonicalOrder:
    return unwrap(CanonicalOrder.create(
        order_id="EQ-001", instrument_id="AAPL", isin=None,
        side=OrderSide.BUY, quantity=Decimal("100"),
        price=Decimal("175"), currency="USD",
        order_type=OrderType.LIMIT,
        counterparty_lei=_LEI_A, executing_party_lei=_LEI_B,
        trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 17),
        venue="XNYS", timestamp=_TS,
    ))


def _option_order() -> CanonicalOrder:
    detail = unwrap(OptionDetail.create(
        strike=Decimal("150"), expiry_date=date(2025, 12, 19),
        option_type=OptionTypeEnum.CALL, option_style=OptionExerciseStyleEnum.AMERICAN,
        settlement_type=SettlementTypeEnum.PHYSICAL, underlying_id="AAPL",
    ))
    return unwrap(CanonicalOrder.create(
        order_id="OPT-001", instrument_id="AAPL251219C00150000",
        isin=None, side=OrderSide.BUY, quantity=Decimal("10"),
        price=Decimal("5.50"), currency="USD",
        order_type=OrderType.LIMIT,
        counterparty_lei=_LEI_A, executing_party_lei=_LEI_B,
        trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 16),
        venue="CBOE", timestamp=_TS, instrument_detail=detail,
    ))


def _futures_order() -> CanonicalOrder:
    detail = unwrap(FuturesDetail.create(
        expiry_date=date(2025, 12, 19), contract_size=Decimal("50"),
        settlement_type=SettlementTypeEnum.CASH, underlying_id="ES",
    ))
    return unwrap(CanonicalOrder.create(
        order_id="FUT-001", instrument_id="ESZ5",
        isin=None, side=OrderSide.BUY, quantity=Decimal("5"),
        price=Decimal("5200"), currency="USD",
        order_type=OrderType.MARKET,
        counterparty_lei=_LEI_A, executing_party_lei=_LEI_B,
        trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 15),
        venue="CME", timestamp=_TS, instrument_detail=detail,
    ))


class TestMiFIDIIReportEquity:
    def test_equity_no_instrument_fields(self) -> None:
        result = project_mifid2_report(_equity_order(), "ATT-001")
        assert isinstance(result, Ok)
        report = unwrap(result).value
        assert isinstance(report, MiFIDIIReport)
        assert report.instrument_fields is None

    def test_equity_has_all_fields(self) -> None:
        report = unwrap(project_mifid2_report(
            _equity_order(), "ATT-001",
        )).value
        assert report.direction == OrderSide.BUY
        assert report.price == Decimal("175")


class TestMiFIDIIReportOption:
    def test_option_has_option_fields(self) -> None:
        result = project_mifid2_report(_option_order(), "ATT-002")
        assert isinstance(result, Ok)
        report = unwrap(result).value
        assert isinstance(report.instrument_fields, OptionReportFields)
        assert report.instrument_fields.strike == Decimal("150")
        assert report.instrument_fields.option_type == OptionTypeEnum.CALL

    def test_option_attestation_refs(self) -> None:
        report = unwrap(project_mifid2_report(
            _option_order(), "ATT-002",
        )).value
        assert "ATT-002" in report.attestation_refs


class TestMiFIDIIReportFutures:
    def test_futures_has_futures_fields(self) -> None:
        result = project_mifid2_report(_futures_order(), "ATT-003")
        assert isinstance(result, Ok)
        report = unwrap(result).value
        assert isinstance(report.instrument_fields, FuturesReportFields)
        assert report.instrument_fields.contract_size == Decimal("50")

    def test_futures_venue(self) -> None:
        report = unwrap(project_mifid2_report(
            _futures_order(), "ATT-003",
        )).value
        assert report.venue.value == "CME"


class TestMiFIDIIReportValidation:
    def test_empty_attestation_id_err(self) -> None:
        result = project_mifid2_report(_equity_order(), "")
        assert isinstance(result, Err)

    def test_report_is_attested(self) -> None:
        att = unwrap(project_mifid2_report(_equity_order(), "ATT-001"))
        assert att.attestation_id != ""
        assert att.content_hash != ""
