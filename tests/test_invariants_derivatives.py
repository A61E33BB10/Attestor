"""Derivative invariant tests — conservation laws and commutativity.

CL-D1..D6: Conservation laws for options and futures.
CS-D1..D5: Master Square and commutativity.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from attestor.core.money import NonEmptyStr
from attestor.core.result import Ok, unwrap
from attestor.core.types import UtcDatetime
from attestor.gateway.types import CanonicalOrder, OrderSide, OrderType
from attestor.instrument.derivative_types import (
    OptionDetail,
    OptionExerciseStyleEnum,
    OptionTypeEnum,
    SettlementTypeEnum,
)
from attestor.ledger.engine import LedgerEngine
from attestor.ledger.futures import (
    create_futures_expiry_transaction,
    create_futures_open_transaction,
    create_variation_margin_transaction,
)
from attestor.ledger.options import (
    create_cash_settlement_exercise_transaction,
    create_expiry_transaction,
    create_premium_transaction,
)
from attestor.ledger.transactions import Account, AccountType
from attestor.pricing.protocols import StubPricingEngine
from attestor.reporting.mifid2 import project_mifid2_report

_TS = UtcDatetime(value=datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC))
_LEI_A = "529900HNOAA1KXQJUQ27"
_LEI_B = "529900ODI3JL1O4COU11"


def _option_engine() -> tuple[LedgerEngine, CanonicalOrder]:
    """Set up engine with 4 accounts and a CALL option order."""
    engine = LedgerEngine()
    for name, atype in [
        ("BUYER-CASH", AccountType.CASH),
        ("SELLER-CASH", AccountType.CASH),
        ("BUYER-POS", AccountType.DERIVATIVES),
        ("SELLER-POS", AccountType.DERIVATIVES),
    ]:
        engine.register_account(Account(
            account_id=unwrap(NonEmptyStr.parse(name)),
            account_type=atype,
        ))

    detail = unwrap(OptionDetail.create(
        strike=Decimal("150"), expiry_date=date(2025, 12, 19),
        option_type=OptionTypeEnum.CALL, option_style=OptionExerciseStyleEnum.AMERICAN,
        settlement_type=SettlementTypeEnum.PHYSICAL, underlying_id="AAPL",
    ))
    order = unwrap(CanonicalOrder.create(
        order_id="OPT-001", instrument_id="AAPL251219C00150000",
        isin=None, side=OrderSide.BUY, quantity=Decimal("10"),
        price=Decimal("5.50"), currency="USD",
        order_type=OrderType.LIMIT,
        counterparty_lei=_LEI_A, executing_party_lei=_LEI_B,
        trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 16),
        venue="CBOE", timestamp=_TS, instrument_detail=detail,
    ))
    return engine, order


def _futures_engine() -> LedgerEngine:
    """Set up engine with 4 accounts for futures."""
    engine = LedgerEngine()
    for name, atype in [
        ("LONG-CASH", AccountType.MARGIN),
        ("SHORT-CASH", AccountType.MARGIN),
        ("LONG-POS", AccountType.DERIVATIVES),
        ("SHORT-POS", AccountType.DERIVATIVES),
    ]:
        engine.register_account(Account(
            account_id=unwrap(NonEmptyStr.parse(name)),
            account_type=atype,
        ))
    return engine


# ---------------------------------------------------------------------------
# CL-D1: Premium conservation
# ---------------------------------------------------------------------------


class TestCLD1PremiumConservation:
    def test_sigma_cash_zero_after_premium(self) -> None:
        engine, order = _option_engine()
        tx = unwrap(create_premium_transaction(
            order, "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-1",
        ))
        unwrap(engine.execute(tx))
        assert engine.total_supply("USD") == Decimal(0)

    def test_sigma_position_zero_after_premium(self) -> None:
        engine, order = _option_engine()
        tx = unwrap(create_premium_transaction(
            order, "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-1",
        ))
        unwrap(engine.execute(tx))
        contract_unit = (
            f"OPT-AAPL-CALL-150-{date(2025, 12, 19).isoformat()}"
        )
        assert engine.total_supply(contract_unit) == Decimal(0)

    @given(
        price=st.decimals(
            min_value=Decimal("0.01"), max_value=Decimal("1000"),
            allow_nan=False, allow_infinity=False, places=2,
        ),
        qty=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=200)
    def test_hypothesis_premium_conservation(
        self, price: Decimal, qty: int,
    ) -> None:
        engine = LedgerEngine()
        for name, atype in [
            ("B-CASH", AccountType.CASH),
            ("S-CASH", AccountType.CASH),
            ("B-POS", AccountType.DERIVATIVES),
            ("S-POS", AccountType.DERIVATIVES),
        ]:
            engine.register_account(Account(
                account_id=unwrap(NonEmptyStr.parse(name)),
                account_type=atype,
            ))
        detail = unwrap(OptionDetail.create(
            strike=Decimal("100"), expiry_date=date(2025, 12, 19),
            option_type=OptionTypeEnum.CALL, option_style=OptionExerciseStyleEnum.EUROPEAN,
            settlement_type=SettlementTypeEnum.PHYSICAL, underlying_id="X",
        ))
        order = unwrap(CanonicalOrder.create(
            order_id="H-1", instrument_id="H-OPT",
            isin=None, side=OrderSide.BUY, quantity=Decimal(qty),
            price=price, currency="USD",
            order_type=OrderType.LIMIT,
            counterparty_lei=_LEI_A, executing_party_lei=_LEI_B,
            trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 16),
            venue="CBOE", timestamp=_TS, instrument_detail=detail,
        ))
        tx = unwrap(create_premium_transaction(
            order, "B-CASH", "S-CASH", "B-POS", "S-POS", "TX-H1",
        ))
        unwrap(engine.execute(tx))
        assert engine.total_supply("USD") == Decimal(0)


# ---------------------------------------------------------------------------
# CL-D3: Expiry conservation
# ---------------------------------------------------------------------------


class TestCLD3ExpiryConservation:
    def test_sigma_returns_to_zero_after_expiry(self) -> None:
        engine, order = _option_engine()
        tx1 = unwrap(create_premium_transaction(
            order, "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-1",
        ))
        unwrap(engine.execute(tx1))

        contract_unit = (
            f"OPT-AAPL-CALL-150-{date(2025, 12, 19).isoformat()}"
        )
        tx2 = unwrap(create_expiry_transaction(
            "AAPL251219C00150000", "BUYER-POS", "SELLER-POS",
            Decimal("10"), contract_unit, "TX-2", _TS,
        ))
        unwrap(engine.execute(tx2))
        assert engine.total_supply(contract_unit) == Decimal(0)
        assert engine.total_supply("USD") == Decimal(0)


# ---------------------------------------------------------------------------
# CL-D4: Variation margin conservation
# ---------------------------------------------------------------------------


class TestCLD4MarginConservation:
    def test_sigma_cash_zero_after_margin(self) -> None:
        engine = _futures_engine()
        tx = unwrap(create_variation_margin_transaction(
            "ESZ5", "LONG-CASH", "SHORT-CASH",
            settlement_price=Decimal("5250"),
            previous_settlement_price=Decimal("5200"),
            contract_size=Decimal("50"), quantity=Decimal("5"),
            tx_id="TX-M1", timestamp=_TS,
        ))
        unwrap(engine.execute(tx))
        assert engine.total_supply("USD") == Decimal(0)

    @given(
        price_delta=st.decimals(
            min_value=Decimal("-500"), max_value=Decimal("500"),
            allow_nan=False, allow_infinity=False, places=2,
        ).filter(lambda x: x != 0),
        qty=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=200)
    def test_hypothesis_margin_conservation(
        self, price_delta: Decimal, qty: int,
    ) -> None:
        engine = _futures_engine()
        base = Decimal("5000")
        result = create_variation_margin_transaction(
            "FUT-H", "LONG-CASH", "SHORT-CASH",
            settlement_price=base + price_delta,
            previous_settlement_price=base,
            contract_size=Decimal("50"), quantity=Decimal(qty),
            tx_id="TX-HM", timestamp=_TS,
        )
        assert isinstance(result, Ok)
        unwrap(engine.execute(unwrap(result)))
        assert engine.total_supply("USD") == Decimal(0)


# ---------------------------------------------------------------------------
# CL-D5: Full option lifecycle
# ---------------------------------------------------------------------------


class TestCLD5FullOptionLifecycle:
    def test_premium_then_cash_exercise(self) -> None:
        """Full lifecycle: premium + cash exercise -> all sigmas zero."""
        engine = LedgerEngine()
        for name, atype in [
            ("B-CASH", AccountType.CASH),
            ("S-CASH", AccountType.CASH),
            ("B-POS", AccountType.DERIVATIVES),
            ("S-POS", AccountType.DERIVATIVES),
        ]:
            engine.register_account(Account(
                account_id=unwrap(NonEmptyStr.parse(name)),
                account_type=atype,
            ))

        detail = unwrap(OptionDetail.create(
            strike=Decimal("150"), expiry_date=date(2025, 12, 19),
            option_type=OptionTypeEnum.CALL, option_style=OptionExerciseStyleEnum.EUROPEAN,
            settlement_type=SettlementTypeEnum.CASH, underlying_id="AAPL",
        ))
        order = unwrap(CanonicalOrder.create(
            order_id="LIFE-1", instrument_id="OPT-LIFE",
            isin=None, side=OrderSide.BUY, quantity=Decimal("10"),
            price=Decimal("5.50"), currency="USD",
            order_type=OrderType.LIMIT,
            counterparty_lei=_LEI_A, executing_party_lei=_LEI_B,
            trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 16),
            venue="CBOE", timestamp=_TS, instrument_detail=detail,
        ))

        # Premium
        tx1 = unwrap(create_premium_transaction(
            order, "B-CASH", "S-CASH", "B-POS", "S-POS", "TX-L1",
        ))
        unwrap(engine.execute(tx1))

        # Cash exercise (ITM)
        tx2 = unwrap(create_cash_settlement_exercise_transaction(
            order, "B-CASH", "S-CASH", "B-POS", "S-POS",
            "TX-L2", settlement_price=Decimal("175"),
        ))
        unwrap(engine.execute(tx2))

        contract_unit = (
            f"OPT-AAPL-CALL-150-{date(2025, 12, 19).isoformat()}"
        )
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply(contract_unit) == Decimal(0)


# ---------------------------------------------------------------------------
# CL-D6: Full futures lifecycle
# ---------------------------------------------------------------------------


class TestCLD6FullFuturesLifecycle:
    def test_open_margins_expiry_cumulative(self) -> None:
        """Open + 3 margins + expiry: cumulative == (final - initial) * size * qty."""
        engine = _futures_engine()

        # Open position
        tx0 = unwrap(create_futures_open_transaction(
            "ESZ5", "LONG-POS", "SHORT-POS",
            Decimal("5"), "FUT-ES", "TX-OPEN", _TS,
        ))
        unwrap(engine.execute(tx0))

        # Day 1: 5200 -> 5250
        tx1 = unwrap(create_variation_margin_transaction(
            "ESZ5", "LONG-CASH", "SHORT-CASH",
            Decimal("5250"), Decimal("5200"),
            Decimal("50"), Decimal("5"), "TX-M1", _TS,
        ))
        unwrap(engine.execute(tx1))

        # Day 2: 5250 -> 5180
        tx2 = unwrap(create_variation_margin_transaction(
            "ESZ5", "LONG-CASH", "SHORT-CASH",
            Decimal("5180"), Decimal("5250"),
            Decimal("50"), Decimal("5"), "TX-M2", _TS,
        ))
        unwrap(engine.execute(tx2))

        # Day 3: 5180 -> 5300
        tx3 = unwrap(create_variation_margin_transaction(
            "ESZ5", "LONG-CASH", "SHORT-CASH",
            Decimal("5300"), Decimal("5180"),
            Decimal("50"), Decimal("5"), "TX-M3", _TS,
        ))
        unwrap(engine.execute(tx3))

        # Expiry at 5350 (last margin was at 5300)
        tx4 = unwrap(create_futures_expiry_transaction(
            "ESZ5", "LONG-CASH", "SHORT-CASH",
            "LONG-POS", "SHORT-POS",
            Decimal("5350"), Decimal("5300"),
            Decimal("50"), Decimal("5"), "FUT-ES", "TX-EXP", _TS,
        ))
        unwrap(engine.execute(tx4))

        # sigma(USD) == 0 (conservation)
        assert engine.total_supply("USD") == Decimal(0)
        # Position closed
        assert engine.total_supply("FUT-ES") == Decimal(0)

        # Cumulative long cash = (5350 - 5200) * 50 * 5 = 37500
        long_cash = engine.get_balance("LONG-CASH", "USD")
        assert long_cash == Decimal("37500")


# ---------------------------------------------------------------------------
# INV-17: GL projection totals == sub-ledger totals
# ---------------------------------------------------------------------------


class TestINV17GLProjection:
    def test_gl_projection_matches_sub_ledger(self) -> None:
        from attestor.core.types import FrozenMap
        from attestor.ledger.gl_projection import (
            GLAccountMapping,
            GLAccountType,
            project_gl,
        )

        engine, order = _option_engine()
        tx = unwrap(create_premium_transaction(
            order, "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-1",
        ))
        unwrap(engine.execute(tx))

        fm = unwrap(FrozenMap.create({
            "BUYER-CASH": ("GL-1000", GLAccountType.ASSET),
            "SELLER-CASH": ("GL-1000", GLAccountType.ASSET),
            "BUYER-POS": ("GL-3000", GLAccountType.ASSET),
            "SELLER-POS": ("GL-3000", GLAccountType.ASSET),
        }))
        mapping = GLAccountMapping(mappings=fm)
        proj = project_gl(engine, mapping, _TS)
        result = proj.trial_balance()
        assert isinstance(result, Ok)
        assert unwrap(result) == Decimal(0)


# ---------------------------------------------------------------------------
# CS-D1: Option Master Square
# ---------------------------------------------------------------------------


class TestCSD1OptionMasterSquare:
    def test_stub_price_then_book_equals_book_then_price(self) -> None:
        """Master Square: price(book(order)) == book(price(order))."""
        oracle_price = Decimal("5.50")
        pricing = StubPricingEngine(oracle_price=oracle_price)

        # Path A: price first, then book
        price_a = unwrap(pricing.price("OPT-1", "snap", "cfg")).npv

        engine_a, order = _option_engine()
        tx = unwrap(create_premium_transaction(
            order, "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-1",
        ))
        unwrap(engine_a.execute(tx))
        price_after_book = unwrap(
            pricing.price("OPT-1", "snap", "cfg"),
        ).npv

        # Path B: book first, then price
        engine_b, order_b = _option_engine()
        tx_b = unwrap(create_premium_transaction(
            order_b, "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-1",
        ))
        unwrap(engine_b.execute(tx_b))
        price_b = unwrap(pricing.price("OPT-1", "snap", "cfg")).npv

        assert price_a == price_after_book == price_b == oracle_price


# ---------------------------------------------------------------------------
# CS-D3: MiFID II naturality
# ---------------------------------------------------------------------------


class TestCSD3MiFIDNaturality:
    def test_report_before_booking_equals_after(self) -> None:
        """MiFID II report is invariant to booking order."""
        _, order = _option_engine()

        report_before = unwrap(
            project_mifid2_report(order, "ATT-1"),
        ).value

        # Book the trade
        engine, _ = _option_engine()
        tx = unwrap(create_premium_transaction(
            order, "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-1",
        ))
        unwrap(engine.execute(tx))

        report_after = unwrap(
            project_mifid2_report(order, "ATT-1"),
        ).value

        # Report content should be identical (same order produces same report)
        assert report_before.instrument_id == report_after.instrument_id
        assert report_before.price == report_after.price
        assert report_before.quantity == report_after.quantity
        assert report_before.direction == report_after.direction


# ---------------------------------------------------------------------------
# CS-D4: Sequential option bookings compose
# ---------------------------------------------------------------------------


class TestCSD4SequentialComposition:
    def test_two_premiums_compose(self) -> None:
        """Two sequential premium bookings maintain conservation."""
        engine = LedgerEngine()
        for name, atype in [
            ("B-CASH", AccountType.CASH),
            ("S-CASH", AccountType.CASH),
            ("B-POS", AccountType.DERIVATIVES),
            ("S-POS", AccountType.DERIVATIVES),
        ]:
            engine.register_account(Account(
                account_id=unwrap(NonEmptyStr.parse(name)),
                account_type=atype,
            ))

        for i, (strike, otype) in enumerate([
            (Decimal("150"), OptionTypeEnum.CALL),
            (Decimal("140"), OptionTypeEnum.PUT),
        ]):
            detail = unwrap(OptionDetail.create(
                strike=strike, expiry_date=date(2025, 12, 19),
                option_type=otype, option_style=OptionExerciseStyleEnum.EUROPEAN,
                settlement_type=SettlementTypeEnum.CASH, underlying_id="AAPL",
            ))
            order = unwrap(CanonicalOrder.create(
                order_id=f"SEQ-{i}", instrument_id=f"OPT-SEQ-{i}",
                isin=None, side=OrderSide.BUY, quantity=Decimal("5"),
                price=Decimal("3.00"), currency="USD",
                order_type=OrderType.LIMIT,
                counterparty_lei=_LEI_A, executing_party_lei=_LEI_B,
                trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 16),
                venue="CBOE", timestamp=_TS, instrument_detail=detail,
            ))
            tx = unwrap(create_premium_transaction(
                order, "B-CASH", "S-CASH", "B-POS", "S-POS", f"TX-SEQ-{i}",
            ))
            unwrap(engine.execute(tx))

        assert engine.total_supply("USD") == Decimal(0)


# ---------------------------------------------------------------------------
# CS-D5: Sequential futures margins compose
# ---------------------------------------------------------------------------


class TestCSD5SequentialMargins:
    def test_margins_compose_conserving_sigma(self) -> None:
        engine = _futures_engine()
        prices = [Decimal("5200"), Decimal("5250"), Decimal("5180"), Decimal("5300")]
        for i in range(len(prices) - 1):
            tx = unwrap(create_variation_margin_transaction(
                "ESZ5", "LONG-CASH", "SHORT-CASH",
                prices[i + 1], prices[i],
                Decimal("50"), Decimal("5"), f"TX-SM-{i}", _TS,
            ))
            unwrap(engine.execute(tx))
        assert engine.total_supply("USD") == Decimal(0)
