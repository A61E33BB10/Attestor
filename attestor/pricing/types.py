"""Pricing interface types — output contracts for Pillar V.

All numeric fields are Decimal. All mappings are FrozenMap.
These types exist so Pillars I-IV can code against them now.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import final

from attestor.core.money import ATTESTOR_DECIMAL_CONTEXT
from attestor.core.types import FrozenMap, UtcDatetime


@final
@dataclass(frozen=True, slots=True)
class ValuationResult:
    """Output of a pricing computation."""

    instrument_id: str
    npv: Decimal
    currency: str
    valuation_date: UtcDatetime  # GAP-36
    components: FrozenMap[str, Decimal] = FrozenMap.EMPTY
    model_config_id: str = ""
    market_snapshot_id: str = ""


@final
@dataclass(frozen=True, slots=True)
class Greeks:
    """First and second order sensitivities."""

    delta: Decimal = Decimal("0")
    gamma: Decimal = Decimal("0")
    vega: Decimal = Decimal("0")
    theta: Decimal = Decimal("0")
    rho: Decimal = Decimal("0")
    vanna: Decimal = Decimal("0")
    volga: Decimal = Decimal("0")
    charm: Decimal = Decimal("0")
    additional: FrozenMap[str, Decimal] = FrozenMap.EMPTY  # GAP-35

@final
@dataclass(frozen=True, slots=True)
class Scenario:
    """A stress scenario definition."""

    label: str
    overrides: FrozenMap[str, Decimal]
    base_snapshot_id: str

    @staticmethod
    def create(
        label: str, overrides: dict[str, Decimal], base_snapshot_id: str,
    ) -> Scenario:
        from attestor.core.result import unwrap  # avoid circular

        return Scenario(
            label=label,
            overrides=unwrap(FrozenMap.create(overrides)),
            base_snapshot_id=base_snapshot_id,
        )


@final
@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """Result of running a scenario."""

    scenario_label: str
    base_npv: Decimal
    stressed_npv: Decimal
    pnl_impact: Decimal
    instrument_impacts: FrozenMap[str, Decimal]


@final
@dataclass(frozen=True, slots=True)
class VaRResult:
    """Value at Risk computation result."""

    confidence_level: Decimal
    horizon_days: int
    var_amount: Decimal
    es_amount: Decimal  # GAP-34: Expected Shortfall / CVaR
    currency: str
    method: str
    component_var: FrozenMap[str, Decimal] = FrozenMap.EMPTY

@final
@dataclass(frozen=True, slots=True)
class PnLAttribution:
    """Decomposed P&L. total == market + carry + trade + residual by construction."""

    total_pnl: Decimal
    market_pnl: Decimal
    carry_pnl: Decimal
    trade_pnl: Decimal
    residual_pnl: Decimal
    currency: str

    @staticmethod
    def create(
        market_pnl: Decimal, carry_pnl: Decimal,
        trade_pnl: Decimal, residual_pnl: Decimal,
        currency: str,
    ) -> PnLAttribution:
        """Compute total from components. Invariant unbreakable by construction (GAP-37)."""
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            total = market_pnl + carry_pnl + trade_pnl + residual_pnl
        return PnLAttribution(
            total_pnl=total, market_pnl=market_pnl,
            carry_pnl=carry_pnl, trade_pnl=trade_pnl,
            residual_pnl=residual_pnl, currency=currency,
        )
