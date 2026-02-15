"""Pricing and Risk Engine protocols for Attestor Phase 0.

IMPORTANT: These signatures are PROVISIONAL for Phase 0. The target
signatures from PLAN Section 3.4.3 use rich typed inputs:
  - instrument: Instrument (not yet defined)
  - market: Attestation[MarketDataSnapshot] (not yet defined)
  - model_config: Attestation[ModelConfig] (not yet defined)
  - returns: Result[Attestation[ValuationResult], PricingError]

Phase 1 will introduce these types and migrate the protocols.
See PLAN Section 3.4.3 for the definitive contract.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, final

from attestor.core.errors import PricingError
from attestor.core.result import Ok
from attestor.core.types import UtcDatetime
from attestor.pricing.types import (
    Greeks,
    PnLAttribution,
    Scenario,
    ScenarioResult,
    ValuationResult,
    VaRResult,
)


class PricingEngine(Protocol):
    """Protocol for pricing computations."""

    def price(
        self, instrument_id: str, market_snapshot_id: str, model_config_id: str,
    ) -> Ok[ValuationResult] | PricingError: ...

    def greeks(
        self, instrument_id: str, market_snapshot_id: str, model_config_id: str,
    ) -> Ok[Greeks] | PricingError: ...

    def var(
        self, portfolio: tuple[str, ...], market_snapshot_id: str,
        confidence_level: Decimal, horizon_days: int, method: str,
    ) -> Ok[VaRResult] | PricingError: ...

    def pnl_attribution(
        self, portfolio: tuple[str, ...],
        start_snapshot_id: str, end_snapshot_id: str,
    ) -> Ok[PnLAttribution] | PricingError: ...


class RiskEngine(Protocol):
    """Protocol for risk scenario computations."""

    def scenario_pnl(
        self, portfolio: tuple[str, ...], scenarios: tuple[Scenario, ...],
        market_snapshot_id: str,
    ) -> Ok[tuple[ScenarioResult, ...]] | PricingError: ...


@final
class StubPricingEngine:
    """Test double. Returns deterministic Ok values.

    When oracle_price is provided, price() returns that value as NPV.
    This enables the Master Square test: stub_price(book(trade)) == book(stub_price(trade)).
    """

    def __init__(self, oracle_price: Decimal | None = None, currency: str = "USD") -> None:
        self._oracle_price = oracle_price
        self._currency = currency

    def price(
        self, instrument_id: str, market_snapshot_id: str, model_config_id: str,
    ) -> Ok[ValuationResult]:
        npv = self._oracle_price if self._oracle_price is not None else Decimal("0")
        return Ok(ValuationResult(
            instrument_id=instrument_id, npv=npv, currency=self._currency,
            valuation_date=UtcDatetime.now(),
        ))

    def greeks(
        self, instrument_id: str, market_snapshot_id: str, model_config_id: str,
    ) -> Ok[Greeks]:
        return Ok(Greeks())

    def var(
        self, portfolio: tuple[str, ...], market_snapshot_id: str,
        confidence_level: Decimal, horizon_days: int, method: str,
    ) -> Ok[VaRResult]:
        return Ok(VaRResult(
            confidence_level=confidence_level, horizon_days=horizon_days,
            var_amount=Decimal("0"), es_amount=Decimal("0"),
            currency="USD", method=method,
        ))

    def pnl_attribution(
        self, portfolio: tuple[str, ...],
        start_snapshot_id: str, end_snapshot_id: str,
    ) -> Ok[PnLAttribution]:
        return Ok(PnLAttribution.create(
            Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), "USD",
        ))
