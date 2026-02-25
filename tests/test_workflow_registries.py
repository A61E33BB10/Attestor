"""Unit tests for attestor.workflow.registries."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from attestor.core.identifiers import LEI
from attestor.core.money import Money, NonEmptyStr, PositiveDecimal
from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import FrozenMap, UtcDatetime
from attestor.gateway.types import OrderSide
from attestor.instrument.derivative_types import EquityDetail
from attestor.instrument.types import EconomicTerms, EquityPayoutSpec, Product
from attestor.oracle.attestation import DerivedConfidence
from attestor.workflow.registries import (
    PreTradeCheck,
    PreTradeCheckRegistry,
    Pricer,
    PricingRegistry,
)
from attestor.workflow.types import PricingInput, PricingResult, RFQInput

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = UtcDatetime(value=datetime(2025, 6, 15, 12, 0, tzinfo=UTC))
_LEI = unwrap(LEI.parse("529900T8BM49AURSDO55"))
_MONEY = unwrap(Money.create(Decimal("100"), "USD"))


def _rfq() -> RFQInput:
    return RFQInput(
        rfq_id=NonEmptyStr(value="RFQ-001"),
        client_lei=_LEI,
        instrument_detail=EquityDetail(),
        notional=PositiveDecimal(value=Decimal("1000")),
        currency=NonEmptyStr(value="USD"),
        side=OrderSide.BUY,
        trade_date=date(2025, 6, 15),
        settlement_date=date(2025, 6, 17),
        timestamp=_NOW,
    )


def _product() -> Product:
    payout = unwrap(EquityPayoutSpec.create("NVDA", "USD", "XNAS"))
    terms = EconomicTerms(
        payouts=(payout,), effective_date=date(2025, 6, 15), termination_date=None,
    )
    return Product(economic_terms=terms)


def _pricing_result() -> PricingResult:
    fq = unwrap(FrozenMap.create({"rmse": Decimal("0.001")}))
    conf = unwrap(DerivedConfidence.create(
        method="BS", config_ref="v1", fit_quality=fq,
    ))
    return PricingResult(
        indicative_price=_MONEY,
        greeks=unwrap(FrozenMap.create({"delta": Decimal("0.55")})),
        model_name=NonEmptyStr(value="BS"),
        market_data_snapshot_id=NonEmptyStr(value="snap-1"),
        confidence=conf,
        pricing_attestation_id=NonEmptyStr(value="att-1"),
        timestamp=_NOW,
    )


# ---------------------------------------------------------------------------
# Concrete check/pricer for testing
# ---------------------------------------------------------------------------


class AlwaysPassCheck:
    @property
    def name(self) -> str:
        return "always_pass"

    def run(self, rfq: RFQInput, product: Product) -> Ok[None] | Err[str]:
        return Ok(None)


class AlwaysFailCheck:
    @property
    def name(self) -> str:
        return "always_fail"

    def run(self, rfq: RFQInput, product: Product) -> Ok[None] | Err[str]:
        return Err("failed on purpose")


class StubPricer:
    def __init__(self, result: PricingResult) -> None:
        self._result = result

    def price(self, inp: PricingInput) -> Ok[PricingResult] | Err[str]:
        return Ok(self._result)


# ---------------------------------------------------------------------------
# PreTradeCheckRegistry
# ---------------------------------------------------------------------------


class TestPreTradeCheckRegistry:
    def test_empty_registry(self) -> None:
        reg = PreTradeCheckRegistry()
        assert reg.checks == ()

    def test_register_and_retrieve(self) -> None:
        reg = PreTradeCheckRegistry()
        reg.register(AlwaysPassCheck())
        reg.register(AlwaysFailCheck())
        assert len(reg.checks) == 2
        assert reg.checks[0].name == "always_pass"
        assert reg.checks[1].name == "always_fail"

    def test_checks_run(self) -> None:
        reg = PreTradeCheckRegistry()
        reg.register(AlwaysPassCheck())
        rfq, prod = _rfq(), _product()
        for check in reg.checks:
            result = check.run(rfq, prod)
            assert isinstance(result, Ok)

    def test_failing_check(self) -> None:
        reg = PreTradeCheckRegistry()
        reg.register(AlwaysFailCheck())
        rfq, prod = _rfq(), _product()
        result = reg.checks[0].run(rfq, prod)
        assert isinstance(result, Err)
        assert result.error == "failed on purpose"

    def test_protocol_compliance(self) -> None:
        assert isinstance(AlwaysPassCheck(), PreTradeCheck)
        assert isinstance(AlwaysFailCheck(), PreTradeCheck)


# ---------------------------------------------------------------------------
# PricingRegistry
# ---------------------------------------------------------------------------


class TestPricingRegistry:
    def test_empty_registry(self) -> None:
        reg = PricingRegistry()
        assert reg.resolve(EquityDetail()) is None

    def test_register_and_resolve(self) -> None:
        reg = PricingRegistry()
        pr = _pricing_result()
        reg.register(
            qualifier=lambda d: isinstance(d, EquityDetail),
            pricer=StubPricer(pr),
        )
        pricer = reg.resolve(EquityDetail())
        assert pricer is not None

    def test_first_match_wins(self) -> None:
        reg = PricingRegistry()
        pr1 = _pricing_result()
        pr2 = _pricing_result()
        reg.register(
            qualifier=lambda d: isinstance(d, EquityDetail),
            pricer=StubPricer(pr1),
        )
        reg.register(
            qualifier=lambda d: True,
            pricer=StubPricer(pr2),
        )
        pricer = reg.resolve(EquityDetail())
        assert pricer is not None
        result = pricer.price(PricingInput(rfq=_rfq(), product=_product()))
        assert isinstance(result, Ok)

    def test_no_match(self) -> None:
        reg = PricingRegistry()
        reg.register(
            qualifier=lambda d: False,
            pricer=StubPricer(_pricing_result()),
        )
        assert reg.resolve(EquityDetail()) is None

    def test_protocol_compliance(self) -> None:
        assert isinstance(StubPricer(_pricing_result()), Pricer)
