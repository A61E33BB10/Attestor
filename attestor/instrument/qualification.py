"""CDM-style product qualification functions.

CDM defines ~90 Qualify_* boolean predicates on EconomicTerms.
In Attestor, products are already typed via the InstrumentDetail
discriminated union, so qualification is a projection from our
typed model to CDM's taxonomy strings.
"""

from __future__ import annotations

from enum import Enum

from attestor.gateway.types import CanonicalOrder
from attestor.instrument.derivative_types import (
    CDSDetail,
    EquityDetail,
    FuturesDetail,
    FXDetail,
    IRSwapDetail,
    OptionDetail,
    SwaptionDetail,
)


class AssetClassEnum(Enum):
    """CDM asset class taxonomy.

    CDM: Qualify_AssetClass_* functions map to these values.
    """

    COMMODITY = "Commodity"
    CREDIT = "Credit"
    EQUITY = "Equity"
    FOREIGN_EXCHANGE = "ForeignExchange"
    INTEREST_RATE = "InterestRate"


def qualify_asset_class(order: CanonicalOrder) -> AssetClassEnum | None:
    """Determine the CDM asset class of an order.

    Returns None if the product does not map to a known asset class.
    """
    detail = order.instrument_detail
    if isinstance(detail, CDSDetail):
        return AssetClassEnum.CREDIT
    if isinstance(detail, (SwaptionDetail, IRSwapDetail)):
        return AssetClassEnum.INTEREST_RATE
    if isinstance(detail, FXDetail):
        return AssetClassEnum.FOREIGN_EXCHANGE
    if isinstance(detail, EquityDetail):
        return AssetClassEnum.EQUITY
    if isinstance(detail, OptionDetail):
        return AssetClassEnum.EQUITY
    if isinstance(detail, FuturesDetail):
        return AssetClassEnum.EQUITY
    return None


def is_credit_default_swap(order: CanonicalOrder) -> bool:
    """CDM: Qualify_CreditDefaultSwap_SingleName (simplified)."""
    return isinstance(order.instrument_detail, CDSDetail)


def is_swaption(order: CanonicalOrder) -> bool:
    """CDM: Qualify_InterestRate_Option_Swaption (simplified)."""
    return isinstance(order.instrument_detail, SwaptionDetail)


def is_interest_rate_swap(order: CanonicalOrder) -> bool:
    """CDM: Qualify_BaseProduct_IRSwap (simplified)."""
    return isinstance(order.instrument_detail, IRSwapDetail)


def is_equity_product(order: CanonicalOrder) -> bool:
    """CDM: Qualify_AssetClass_Equity (simplified)."""
    return isinstance(
        order.instrument_detail, (EquityDetail, OptionDetail, FuturesDetail)
    )


def is_fx_product(order: CanonicalOrder) -> bool:
    """CDM: Qualify_AssetClass_ForeignExchange (simplified)."""
    return isinstance(order.instrument_detail, FXDetail)
