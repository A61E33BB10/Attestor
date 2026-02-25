"""Unit tests for attestor.workflow.types — frozen dataclass invariants."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from attestor.core.identifiers import LEI
from attestor.core.money import Money, NonEmptyStr, PositiveDecimal
from attestor.core.result import unwrap
from attestor.core.types import FrozenMap, UtcDatetime
from attestor.gateway.types import OrderSide
from attestor.instrument.derivative_types import EquityDetail
from attestor.oracle.attestation import DerivedConfidence
from attestor.workflow.types import (
    BookingInput,
    BookingOutput,
    BookingResult,
    ClientAction,
    ClientResponse,
    ConfirmationInput,
    IndicativeInput,
    MappingOutput,
    PreTradeCheckResult,
    PreTradeInput,
    PricingInput,
    PricingOutput,
    PricingResult,
    RFQInput,
    RFQOutcome,
    RFQResult,
    TermSheet,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = UtcDatetime(value=datetime(2025, 6, 15, 12, 0, tzinfo=UTC))
_LEI = unwrap(LEI.parse("529900T8BM49AURSDO55"))
_NES = NonEmptyStr(value="test")
_PD = PositiveDecimal(value=Decimal("1000000"))
_MONEY = unwrap(Money.create(Decimal("42.50"), "USD"))


def _greeks() -> FrozenMap[str, Decimal]:
    return unwrap(FrozenMap.create({"delta": Decimal("0.55")}))


def _confidence() -> DerivedConfidence:
    fq = unwrap(FrozenMap.create({"rmse": Decimal("0.001")}))
    return unwrap(DerivedConfidence.create(
        method="BlackScholes", config_ref="bs-v1", fit_quality=fq,
    ))


def _pricing_result() -> PricingResult:
    return PricingResult(
        indicative_price=_MONEY,
        greeks=_greeks(),
        model_name=NonEmptyStr(value="BlackScholes"),
        market_data_snapshot_id=NonEmptyStr(value="snap-001"),
        confidence=_confidence(),
        pricing_attestation_id=NonEmptyStr(value="att-001"),
        timestamp=_NOW,
    )


def _rfq_input() -> RFQInput:
    return RFQInput(
        rfq_id=NonEmptyStr(value="RFQ-001"),
        client_lei=_LEI,
        instrument_detail=EquityDetail(),
        notional=_PD,
        currency=NonEmptyStr(value="USD"),
        side=OrderSide.BUY,
        trade_date=date(2025, 6, 15),
        settlement_date=date(2025, 6, 17),
        timestamp=_NOW,
    )


def _product():
    from attestor.instrument.types import EconomicTerms, EquityPayoutSpec, Product
    payout = unwrap(EquityPayoutSpec.create("NVDA", "USD", "XNAS"))
    terms = EconomicTerms(
        payouts=(payout,),
        effective_date=date(2025, 6, 15),
        termination_date=None,
    )
    return Product(economic_terms=terms)


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestClientAction:
    def test_members(self) -> None:
        assert len(ClientAction) == 3
        assert {m.value for m in ClientAction} == {"Accept", "Reject", "Refresh"}


class TestRFQOutcome:
    def test_members(self) -> None:
        assert len(RFQOutcome) == 5
        assert {m.value for m in RFQOutcome} == {
            "Executed", "RejectedPreTrade", "RejectedByClient", "Expired", "Failed",
        }


# ---------------------------------------------------------------------------
# RFQInput
# ---------------------------------------------------------------------------


class TestRFQInput:
    def test_valid(self) -> None:
        rfq = _rfq_input()
        assert rfq.rfq_id.value == "RFQ-001"
        assert rfq.side == OrderSide.BUY

    def test_frozen(self) -> None:
        rfq = _rfq_input()
        with pytest.raises(AttributeError):
            rfq.rfq_id = _NES  # type: ignore[misc]

    def test_settlement_before_trade_rejected(self) -> None:
        with pytest.raises(TypeError, match="settlement_date.*must be >= trade_date"):
            RFQInput(
                rfq_id=NonEmptyStr(value="RFQ-002"),
                client_lei=_LEI,
                instrument_detail=EquityDetail(),
                notional=_PD,
                currency=NonEmptyStr(value="USD"),
                side=OrderSide.BUY,
                trade_date=date(2025, 6, 17),
                settlement_date=date(2025, 6, 15),
                timestamp=_NOW,
            )

    def test_same_date_ok(self) -> None:
        rfq = RFQInput(
            rfq_id=NonEmptyStr(value="RFQ-003"),
            client_lei=_LEI,
            instrument_detail=EquityDetail(),
            notional=_PD,
            currency=NonEmptyStr(value="USD"),
            side=OrderSide.SELL,
            trade_date=date(2025, 6, 15),
            settlement_date=date(2025, 6, 15),
            timestamp=_NOW,
        )
        assert rfq.trade_date == rfq.settlement_date


# ---------------------------------------------------------------------------
# PreTradeCheckResult
# ---------------------------------------------------------------------------


class TestPreTradeCheckResult:
    def test_all_pass(self) -> None:
        r = PreTradeCheckResult(
            restricted_underlying_ok=True,
            credit_limit_ok=True,
            eligibility_ok=True,
        )
        assert r.passed is True
        assert r.rejection_reasons == ()

    def test_one_fails(self) -> None:
        r = PreTradeCheckResult(
            restricted_underlying_ok=True,
            credit_limit_ok=False,
            eligibility_ok=True,
        )
        assert r.passed is False
        assert "Credit limit exceeded" in r.rejection_reasons

    def test_all_fail(self) -> None:
        r = PreTradeCheckResult(
            restricted_underlying_ok=False,
            credit_limit_ok=False,
            eligibility_ok=False,
        )
        assert r.passed is False
        assert len(r.rejection_reasons) == 3

    def test_frozen(self) -> None:
        r = PreTradeCheckResult(
            restricted_underlying_ok=True,
            credit_limit_ok=True,
            eligibility_ok=True,
        )
        with pytest.raises(AttributeError):
            r.credit_limit_ok = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PricingResult
# ---------------------------------------------------------------------------


class TestPricingResult:
    def test_valid(self) -> None:
        pr = _pricing_result()
        assert pr.indicative_price == _MONEY
        assert pr.model_name.value == "BlackScholes"

    def test_frozen(self) -> None:
        pr = _pricing_result()
        with pytest.raises(AttributeError):
            pr.model_name = _NES  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TermSheet
# ---------------------------------------------------------------------------


class TestTermSheet:
    def test_valid(self) -> None:
        ts = TermSheet(
            rfq_id=NonEmptyStr(value="RFQ-001"),
            pricing_result=_pricing_result(),
            document_hash=NonEmptyStr(value="abc123"),
            valid_until=UtcDatetime(value=datetime(2025, 6, 15, 13, 0, tzinfo=UTC)),
            generated_at=_NOW,
        )
        assert ts.document_hash.value == "abc123"

    def test_frozen(self) -> None:
        ts = TermSheet(
            rfq_id=NonEmptyStr(value="RFQ-001"),
            pricing_result=_pricing_result(),
            document_hash=NonEmptyStr(value="abc123"),
            valid_until=UtcDatetime(value=datetime(2025, 6, 15, 13, 0, tzinfo=UTC)),
            generated_at=_NOW,
        )
        with pytest.raises(AttributeError):
            ts.document_hash = _NES  # type: ignore[misc]

    def test_valid_until_before_generated_at_rejected(self) -> None:
        with pytest.raises(TypeError, match="valid_until.*must be >= generated_at"):
            TermSheet(
                rfq_id=NonEmptyStr(value="RFQ-001"),
                pricing_result=_pricing_result(),
                document_hash=NonEmptyStr(value="abc123"),
                valid_until=UtcDatetime(value=datetime(2025, 6, 15, 11, 0, tzinfo=UTC)),
                generated_at=_NOW,
            )

    def test_same_time_ok(self) -> None:
        ts = TermSheet(
            rfq_id=NonEmptyStr(value="RFQ-001"),
            pricing_result=_pricing_result(),
            document_hash=NonEmptyStr(value="abc123"),
            valid_until=_NOW,
            generated_at=_NOW,
        )
        assert ts.valid_until == ts.generated_at


# ---------------------------------------------------------------------------
# ClientResponse
# ---------------------------------------------------------------------------


class TestClientResponse:
    def test_accept_with_hash(self) -> None:
        cr = ClientResponse(
            rfq_id=NonEmptyStr(value="RFQ-001"),
            action=ClientAction.ACCEPT,
            timestamp=_NOW,
            term_sheet_hash=NonEmptyStr(value="abc123"),
        )
        assert cr.action == ClientAction.ACCEPT

    def test_accept_without_hash_rejected(self) -> None:
        with pytest.raises(TypeError, match="term_sheet_hash is required"):
            ClientResponse(
                rfq_id=NonEmptyStr(value="RFQ-001"),
                action=ClientAction.ACCEPT,
                timestamp=_NOW,
            )

    def test_reject_without_hash_ok(self) -> None:
        cr = ClientResponse(
            rfq_id=NonEmptyStr(value="RFQ-001"),
            action=ClientAction.REJECT,
            timestamp=_NOW,
            message="Too expensive",
        )
        assert cr.term_sheet_hash is None

    def test_refresh_ok(self) -> None:
        cr = ClientResponse(
            rfq_id=NonEmptyStr(value="RFQ-001"),
            action=ClientAction.REFRESH,
            timestamp=_NOW,
        )
        assert cr.action == ClientAction.REFRESH

    def test_frozen(self) -> None:
        cr = ClientResponse(
            rfq_id=NonEmptyStr(value="RFQ-001"),
            action=ClientAction.REJECT,
            timestamp=_NOW,
        )
        with pytest.raises(AttributeError):
            cr.action = ClientAction.ACCEPT  # type: ignore[misc]


# ---------------------------------------------------------------------------
# RFQResult
# ---------------------------------------------------------------------------


class TestRFQResult:
    def test_executed(self) -> None:
        r = RFQResult(
            rfq_id=NonEmptyStr(value="RFQ-001"),
            outcome=RFQOutcome.EXECUTED,
            trade_id=NonEmptyStr(value="TRADE-001"),
            pricing_attestation_id=NonEmptyStr(value="att-001"),
        )
        assert r.outcome == RFQOutcome.EXECUTED
        assert r.trade_id is not None

    def test_rejected(self) -> None:
        r = RFQResult(
            rfq_id=NonEmptyStr(value="RFQ-001"),
            outcome=RFQOutcome.REJECTED_PRE_TRADE,
            rejection_reasons=("Credit limit exceeded",),
        )
        assert r.trade_id is None
        assert len(r.rejection_reasons) == 1

    def test_frozen(self) -> None:
        r = RFQResult(
            rfq_id=NonEmptyStr(value="RFQ-001"),
            outcome=RFQOutcome.FAILED,
        )
        with pytest.raises(AttributeError):
            r.outcome = RFQOutcome.EXECUTED  # type: ignore[misc]

    def test_executed_without_trade_id_rejected(self) -> None:
        with pytest.raises(TypeError, match="EXECUTED outcome requires trade_id"):
            RFQResult(
                rfq_id=NonEmptyStr(value="RFQ-001"),
                outcome=RFQOutcome.EXECUTED,
            )

    def test_rejected_with_trade_id_rejected(self) -> None:
        with pytest.raises(TypeError, match="must not have trade_id"):
            RFQResult(
                rfq_id=NonEmptyStr(value="RFQ-001"),
                outcome=RFQOutcome.REJECTED_PRE_TRADE,
                trade_id=NonEmptyStr(value="T-001"),
            )


# ---------------------------------------------------------------------------
# Activity I/O wrappers
# ---------------------------------------------------------------------------


class TestMappingOutput:
    def test_success(self) -> None:
        p = _product()
        out = MappingOutput(product=p)
        assert out.product is not None
        assert out.error is None

    def test_error(self) -> None:
        out = MappingOutput(error="bad product")
        assert out.product is None
        assert out.error == "bad product"

    def test_neither_rejected(self) -> None:
        with pytest.raises(TypeError, match="exactly one"):
            MappingOutput()

    def test_both_rejected(self) -> None:
        with pytest.raises(TypeError, match="exactly one"):
            MappingOutput(product=_product(), error="also an error")


class TestPricingOutput:
    def test_success(self) -> None:
        out = PricingOutput(result=_pricing_result())
        assert out.result is not None
        assert out.error is None

    def test_error(self) -> None:
        out = PricingOutput(error="calibration failed")
        assert out.result is None

    def test_neither_rejected(self) -> None:
        with pytest.raises(TypeError, match="exactly one"):
            PricingOutput()

    def test_both_rejected(self) -> None:
        with pytest.raises(TypeError, match="exactly one"):
            PricingOutput(result=_pricing_result(), error="also an error")


class TestBookingOutput:
    def test_success(self) -> None:
        br = BookingResult(trade_id=NonEmptyStr(value="T-001"))
        out = BookingOutput(result=br)
        assert out.result is not None

    def test_error(self) -> None:
        out = BookingOutput(error="ledger conflict")
        assert out.result is None

    def test_neither_rejected(self) -> None:
        with pytest.raises(TypeError, match="exactly one"):
            BookingOutput()

    def test_both_rejected(self) -> None:
        with pytest.raises(TypeError, match="exactly one"):
            BookingOutput(
                result=BookingResult(trade_id=NonEmptyStr(value="T-001")),
                error="also an error",
            )


class TestPreTradeInput:
    def test_valid(self) -> None:
        inp = PreTradeInput(rfq=_rfq_input(), product=_product())
        assert inp.rfq.rfq_id.value == "RFQ-001"


class TestPricingInput:
    def test_valid(self) -> None:
        inp = PricingInput(rfq=_rfq_input(), product=_product())
        assert inp.product is not None


class TestIndicativeInput:
    def test_valid(self) -> None:
        inp = IndicativeInput(
            rfq=_rfq_input(),
            pricing=_pricing_result(),
            valid_for=timedelta(hours=1),
        )
        assert inp.valid_for == timedelta(hours=1)


class TestBookingInput:
    def test_valid(self) -> None:
        inp = BookingInput(
            rfq=_rfq_input(),
            product=_product(),
            pricing=_pricing_result(),
            accepted_price=_MONEY,
        )
        assert inp.accepted_price == _MONEY


class TestConfirmationInput:
    def test_valid(self) -> None:
        inp = ConfirmationInput(
            rfq=_rfq_input(),
            trade_result=BookingResult(trade_id=NonEmptyStr(value="T-001")),
            term_sheet=TermSheet(
                rfq_id=NonEmptyStr(value="RFQ-001"),
                pricing_result=_pricing_result(),
                document_hash=NonEmptyStr(value="abc"),
                valid_until=_NOW,
                generated_at=_NOW,
            ),
        )
        assert inp.trade_result.trade_id.value == "T-001"
