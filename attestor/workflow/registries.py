"""Extensibility registries for pre-trade checks and pricing.

Lattner's "Library Over Workflow Engine" principle: new product types
register their domain logic here.  The workflow and activities are unchanged.

Usage at worker startup::

    check_registry = PreTradeCheckRegistry()
    check_registry.register(RestrictedUnderlyingCheck())
    check_registry.register(CreditLimitCheck())

    pricing_registry = PricingRegistry()
    pricing_registry.register(qualifier=is_equity_product, pricer=BSPricer())
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, final, runtime_checkable

from attestor.core.result import Err, Ok
from attestor.instrument.derivative_types import InstrumentDetail
from attestor.instrument.types import Product
from attestor.workflow.types import PricingInput, PricingResult, RFQInput

# ---------------------------------------------------------------------------
# Pre-trade check protocol + registry
# ---------------------------------------------------------------------------


@runtime_checkable
class PreTradeCheck(Protocol):
    """Protocol for a single pre-trade compliance check."""

    @property
    def name(self) -> str: ...

    def run(self, rfq: RFQInput, product: Product) -> Ok[None] | Err[str]:
        """Return Ok(None) if passed, Err(reason) if failed."""
        ...


@final
@dataclass
class PreTradeCheckRegistry:
    """Registry of pre-trade checks.  Iterable in insertion order."""

    _checks: list[PreTradeCheck] = field(default_factory=list)

    def register(self, check: PreTradeCheck) -> None:
        self._checks.append(check)

    @property
    def checks(self) -> tuple[PreTradeCheck, ...]:
        return tuple(self._checks)


# ---------------------------------------------------------------------------
# Pricing protocol + registry
# ---------------------------------------------------------------------------


@runtime_checkable
class Pricer(Protocol):
    """Protocol for a product pricer."""

    def price(self, inp: PricingInput) -> Ok[PricingResult] | Err[str]:
        """Compute price + Greeks for the given product."""
        ...


type Qualifier = Callable[[InstrumentDetail], bool]


@final
@dataclass
class PricingRegistry:
    """Registry of pricers keyed by product qualifier.

    Qualifiers are tried in registration order; first match wins.
    """

    _entries: list[tuple[Qualifier, Pricer]] = field(default_factory=list)

    def register(self, *, qualifier: Qualifier, pricer: Pricer) -> None:
        self._entries.append((qualifier, pricer))

    def resolve(self, detail: InstrumentDetail) -> Pricer | None:
        """Return the first matching pricer, or None."""
        for qual, pricer in self._entries:
            if qual(detail):
                return pricer
        return None
