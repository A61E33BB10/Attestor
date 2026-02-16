"""Tests for attestor.ledger.fx_settlement — FX spot, forward, NDF settlement."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from attestor.core.result import Err, Ok, unwrap
from attestor.gateway.parser import parse_fx_forward_order, parse_fx_spot_order, parse_ndf_order
from attestor.gateway.types import CanonicalOrder
from attestor.instrument.derivative_types import FXDetail
from attestor.ledger.engine import LedgerEngine
from attestor.ledger.fx_settlement import (
    create_fx_forward_settlement,
    create_fx_spot_settlement,
    create_ndf_settlement,
)

_TS = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)

_BASE_FX: dict[str, object] = {
    "order_id": "ORD-FX-001",
    "instrument_id": "EURUSD-SPOT",
    "side": "BUY",
    "quantity": "1000000",
    "price": "1.0850",
    "currency": "USD",
    "order_type": "MARKET",
    "counterparty_lei": "529900HNOAA1KXQJUQ27",
    "executing_party_lei": "529900ODI3JL1O4COU11",
    "trade_date": "2025-06-15",
    "venue": "XFOR",
    "timestamp": "2025-06-15T10:00:00+00:00",
}


def _spot_order() -> CanonicalOrder:
    raw = {**_BASE_FX, "currency_pair": "EUR/USD"}
    return unwrap(parse_fx_spot_order(raw))


def _forward_order() -> CanonicalOrder:
    raw = {
        **_BASE_FX,
        "currency_pair": "EUR/USD",
        "forward_rate": "1.0920",
        "settlement_date": "2025-09-15",
    }
    return unwrap(parse_fx_forward_order(raw))


def _ndf_order() -> CanonicalOrder:
    raw = {
        **_BASE_FX,
        "instrument_id": "USDCNY-NDF",
        "currency_pair": "USD/CNY",
        "forward_rate": "7.2500",
        "fixing_date": "2025-09-13",
        "settlement_date": "2025-09-15",
        "fixing_source": "WMR",
    }
    return unwrap(parse_ndf_order(raw))


# ---------------------------------------------------------------------------
# FX Spot Settlement
# ---------------------------------------------------------------------------


class TestFXSpotSettlement:
    def test_two_moves(self) -> None:
        tx = unwrap(create_fx_spot_settlement(
            order=_spot_order(),
            buyer_base_account="BUYER-EUR",
            buyer_quote_account="BUYER-USD",
            seller_base_account="SELLER-EUR",
            seller_quote_account="SELLER-USD",
            spot_rate=Decimal("1.0850"),
            tx_id="TX-FX-001",
        ))
        assert len(tx.moves) == 2

    def test_base_currency_move(self) -> None:
        tx = unwrap(create_fx_spot_settlement(
            order=_spot_order(),
            buyer_base_account="BUYER-EUR",
            buyer_quote_account="BUYER-USD",
            seller_base_account="SELLER-EUR",
            seller_quote_account="SELLER-USD",
            spot_rate=Decimal("1.0850"),
            tx_id="TX-FX-001",
        ))
        base_move = tx.moves[0]
        assert base_move.unit == "EUR"
        assert base_move.quantity.value == Decimal("1000000")

    def test_quote_currency_move(self) -> None:
        tx = unwrap(create_fx_spot_settlement(
            order=_spot_order(),
            buyer_base_account="BUYER-EUR",
            buyer_quote_account="BUYER-USD",
            seller_base_account="SELLER-EUR",
            seller_quote_account="SELLER-USD",
            spot_rate=Decimal("1.0850"),
            tx_id="TX-FX-001",
        ))
        quote_move = tx.moves[1]
        assert quote_move.unit == "USD"
        assert quote_move.quantity.value == Decimal("1085000.00")

    def test_conservation_in_engine(self) -> None:
        """sigma(EUR) = 0, sigma(USD) = 0 after settlement."""
        engine = LedgerEngine()
        tx = unwrap(create_fx_spot_settlement(
            order=_spot_order(),
            buyer_base_account="BUYER-EUR",
            buyer_quote_account="BUYER-USD",
            seller_base_account="SELLER-EUR",
            seller_quote_account="SELLER-USD",
            spot_rate=Decimal("1.0850"),
            tx_id="TX-FX-001",
        ))
        engine.execute(tx)
        assert engine.total_supply("EUR") == Decimal("0")
        assert engine.total_supply("USD") == Decimal("0")

    def test_empty_account_err(self) -> None:
        result = create_fx_spot_settlement(
            order=_spot_order(),
            buyer_base_account="",
            buyer_quote_account="BUYER-USD",
            seller_base_account="SELLER-EUR",
            seller_quote_account="SELLER-USD",
            spot_rate=Decimal("1.0850"),
            tx_id="TX-FX-001",
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# FX Forward Settlement
# ---------------------------------------------------------------------------


class TestFXForwardSettlement:
    def test_uses_forward_rate(self) -> None:
        tx = unwrap(create_fx_forward_settlement(
            order=_forward_order(),
            buyer_base_account="BUYER-EUR",
            buyer_quote_account="BUYER-USD",
            seller_base_account="SELLER-EUR",
            seller_quote_account="SELLER-USD",
            tx_id="TX-FWD-001",
        ))
        quote_move = tx.moves[1]
        assert quote_move.quantity.value == Decimal("1092000.00")

    def test_conservation(self) -> None:
        engine = LedgerEngine()
        tx = unwrap(create_fx_forward_settlement(
            order=_forward_order(),
            buyer_base_account="BUYER-EUR",
            buyer_quote_account="BUYER-USD",
            seller_base_account="SELLER-EUR",
            seller_quote_account="SELLER-USD",
            tx_id="TX-FWD-001",
        ))
        engine.execute(tx)
        for ccy in ("EUR", "USD"):
            assert engine.total_supply(ccy) == Decimal("0")


# ---------------------------------------------------------------------------
# NDF Settlement
# ---------------------------------------------------------------------------


class TestNDFSettlement:
    def test_single_move(self) -> None:
        tx = unwrap(create_ndf_settlement(
            order=_ndf_order(),
            buyer_cash_account="BUYER-USD",
            seller_cash_account="SELLER-USD",
            fixing_rate=Decimal("7.3000"),
            tx_id="TX-NDF-001",
        ))
        assert len(tx.moves) == 1

    def test_settlement_amount(self) -> None:
        """amount = notional * (fixing - forward) / fixing."""
        order = _ndf_order()
        detail = order.instrument_detail
        assert isinstance(detail, FXDetail)
        assert detail.forward_rate is not None
        fixing = Decimal("7.3000")
        forward = detail.forward_rate.value  # 7.2500
        notional = order.quantity.value  # 1_000_000
        expected = notional * (fixing - forward) / fixing

        tx = unwrap(create_ndf_settlement(
            order=order,
            buyer_cash_account="BUYER-USD",
            seller_cash_account="SELLER-USD",
            fixing_rate=fixing,
            tx_id="TX-NDF-001",
        ))
        assert tx.moves[0].quantity.value == abs(expected)

    def test_ndf_conservation(self) -> None:
        engine = LedgerEngine()
        tx = unwrap(create_ndf_settlement(
            order=_ndf_order(),
            buyer_cash_account="BUYER-USD",
            seller_cash_account="SELLER-USD",
            fixing_rate=Decimal("7.3000"),
            tx_id="TX-NDF-001",
        ))
        engine.execute(tx)
        assert engine.total_supply("USD") == Decimal("0")

    def test_zero_fixing_rate_err(self) -> None:
        result = create_ndf_settlement(
            order=_ndf_order(),
            buyer_cash_account="BUYER-USD",
            seller_cash_account="SELLER-USD",
            fixing_rate=Decimal("0"),
            tx_id="TX-NDF-001",
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Hypothesis: conservation for random FX spots
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    rate=st.decimals(
        min_value=Decimal("0.01"), max_value=Decimal("999"),
        allow_nan=False, allow_infinity=False, places=4,
    ),
)
def test_fx_spot_conservation_hypothesis(rate: Decimal) -> None:
    """Random FX rates always conserve both currency units."""
    order = _spot_order()
    result = create_fx_spot_settlement(
        order=order,
        buyer_base_account="B-EUR",
        buyer_quote_account="B-USD",
        seller_base_account="S-EUR",
        seller_quote_account="S-USD",
        spot_rate=rate,
        tx_id="TX-HYP",
    )
    assert isinstance(result, Ok)
    tx = unwrap(result)
    engine = LedgerEngine()
    engine.execute(tx)
    for ccy in ("EUR", "USD"):
        assert engine.total_supply(ccy) == Decimal("0"), (
            f"sigma({ccy}) != 0 for rate={rate}"
        )
