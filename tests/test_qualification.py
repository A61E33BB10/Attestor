"""CDM-style qualification functions — tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from attestor.core.result import unwrap
from attestor.core.types import UtcDatetime
from attestor.gateway.parser import parse_cds_order, parse_swaption_order
from attestor.gateway.types import CanonicalOrder, OrderSide, OrderType
from attestor.instrument.derivative_types import (
    FXDetail,
    IRSwapDetail,
)
from attestor.instrument.qualification import (
    AssetClassEnum,
    is_credit_default_swap,
    is_equity_product,
    is_fx_product,
    is_interest_rate_swap,
    is_swaption,
    qualify_asset_class,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = UtcDatetime(value=datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC))


def _equity_order() -> CanonicalOrder:
    return unwrap(CanonicalOrder.create(
        order_id="EQ-001", instrument_id="NVDA", isin=None,
        side=OrderSide.BUY, quantity=Decimal("100"),
        price=Decimal("130"), currency="USD",
        order_type=OrderType.LIMIT,
        counterparty_lei="529900HNOAA1KXQJUQ27",
        executing_party_lei="529900ODI3JL1O4COU11",
        trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 17),
        venue="XNAS", timestamp=_TS,
    ))


def _cds_order() -> CanonicalOrder:
    raw = {
        "order_id": "CDS-001", "instrument_id": "CDS-ITRAXX-001",
        "side": "BUY", "quantity": "10000000", "price": "100",
        "currency": "USD", "order_type": "MARKET",
        "counterparty_lei": "529900HNOAA1KXQJUQ27",
        "executing_party_lei": "529900ODI3JL1O4COU11",
        "trade_date": "2025-06-15", "venue": "XSWP",
        "timestamp": "2025-06-15T10:00:00+00:00",
        "reference_entity": "ACME Corp", "spread_bps": "100",
        "seniority": "SeniorUnsecured", "protection_side": "Buyer",
        "start_date": "2025-06-17", "maturity_date": "2030-06-17",
    }
    return unwrap(parse_cds_order(raw))


def _swaption_order() -> CanonicalOrder:
    raw = {
        "order_id": "SWN-001", "instrument_id": "SWN-USD-5Y",
        "side": "BUY", "quantity": "10000000", "price": "100",
        "currency": "USD", "order_type": "MARKET",
        "counterparty_lei": "529900HNOAA1KXQJUQ27",
        "executing_party_lei": "529900ODI3JL1O4COU11",
        "trade_date": "2025-06-15", "venue": "XSWP",
        "timestamp": "2025-06-15T10:00:00+00:00",
        "swaption_type": "Payer", "expiry_date": "2026-06-15",
        "underlying_fixed_rate": "0.035", "underlying_float_index": "SOFR",
        "underlying_tenor_months": "60", "settlement_type": "Physical",
    }
    return unwrap(parse_swaption_order(raw))


def _fx_order() -> CanonicalOrder:
    from attestor.instrument.derivative_types import SettlementTypeEnum
    detail = unwrap(FXDetail.create(
        currency_pair="EUR/USD",
        settlement_date=date(2025, 6, 17),
        settlement_type=SettlementTypeEnum.PHYSICAL,
        forward_rate=Decimal("1.10"),
    ))
    return unwrap(CanonicalOrder.create(
        order_id="FX-001", instrument_id="EURUSD", isin=None,
        side=OrderSide.BUY, quantity=Decimal("1000000"),
        price=Decimal("1.10"), currency="USD",
        order_type=OrderType.MARKET,
        counterparty_lei="529900HNOAA1KXQJUQ27",
        executing_party_lei="529900ODI3JL1O4COU11",
        trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 17),
        venue="XSWP", timestamp=_TS,
        instrument_detail=detail,
    ))


def _irs_order() -> CanonicalOrder:
    detail = unwrap(IRSwapDetail.create(
        fixed_rate=Decimal("0.035"),
        float_index="SOFR",
        day_count="ACT/360",
        payment_frequency="QUARTERLY",
        tenor_months=60,
        start_date=date(2025, 6, 17),
        end_date=date(2030, 6, 17),
    ))
    return unwrap(CanonicalOrder.create(
        order_id="IRS-001", instrument_id="IRS-USD-5Y", isin=None,
        side=OrderSide.BUY, quantity=Decimal("10000000"),
        price=Decimal("100"), currency="USD",
        order_type=OrderType.MARKET,
        counterparty_lei="529900HNOAA1KXQJUQ27",
        executing_party_lei="529900ODI3JL1O4COU11",
        trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 17),
        venue="XSWP", timestamp=_TS,
        instrument_detail=detail,
    ))


# ---------------------------------------------------------------------------
# AssetClassEnum
# ---------------------------------------------------------------------------


class TestAssetClassEnum:
    def test_member_count(self) -> None:
        assert len(AssetClassEnum) == 5

    def test_values(self) -> None:
        assert {e.value for e in AssetClassEnum} == {
            "Commodity", "Credit", "Equity",
            "ForeignExchange", "InterestRate",
        }


# ---------------------------------------------------------------------------
# qualify_asset_class
# ---------------------------------------------------------------------------


class TestQualifyAssetClass:
    def test_equity(self) -> None:
        assert qualify_asset_class(_equity_order()) == AssetClassEnum.EQUITY

    def test_cds_is_credit(self) -> None:
        assert qualify_asset_class(_cds_order()) == AssetClassEnum.CREDIT

    def test_swaption_is_interest_rate(self) -> None:
        assert qualify_asset_class(_swaption_order()) == AssetClassEnum.INTEREST_RATE

    def test_fx(self) -> None:
        assert qualify_asset_class(_fx_order()) == AssetClassEnum.FOREIGN_EXCHANGE

    def test_irs(self) -> None:
        assert qualify_asset_class(_irs_order()) == AssetClassEnum.INTEREST_RATE


# ---------------------------------------------------------------------------
# Boolean qualifiers
# ---------------------------------------------------------------------------


class TestBooleanQualifiers:
    def test_is_credit_default_swap_true(self) -> None:
        assert is_credit_default_swap(_cds_order()) is True

    def test_is_credit_default_swap_false(self) -> None:
        assert is_credit_default_swap(_equity_order()) is False

    def test_is_swaption_true(self) -> None:
        assert is_swaption(_swaption_order()) is True

    def test_is_swaption_false(self) -> None:
        assert is_swaption(_cds_order()) is False

    def test_is_interest_rate_swap_true(self) -> None:
        assert is_interest_rate_swap(_irs_order()) is True

    def test_is_interest_rate_swap_false(self) -> None:
        assert is_interest_rate_swap(_equity_order()) is False

    def test_is_equity_product_true(self) -> None:
        assert is_equity_product(_equity_order()) is True

    def test_is_equity_product_false(self) -> None:
        assert is_equity_product(_cds_order()) is False

    def test_is_fx_product_true(self) -> None:
        assert is_fx_product(_fx_order()) is True

    def test_is_fx_product_false(self) -> None:
        assert is_fx_product(_equity_order()) is False


# ---------------------------------------------------------------------------
# Re-exports
# ---------------------------------------------------------------------------


class TestQualificationReExports:
    def test_from_instrument(self) -> None:
        from attestor.instrument import (
            AssetClassEnum,
            is_credit_default_swap,
            is_equity_product,
            is_fx_product,
            is_interest_rate_swap,
            is_swaption,
            qualify_asset_class,
        )
        assert len(AssetClassEnum) == 5
        assert callable(qualify_asset_class)
        assert callable(is_credit_default_swap)
        assert callable(is_swaption)
        assert callable(is_interest_rate_swap)
        assert callable(is_equity_product)
        assert callable(is_fx_product)
