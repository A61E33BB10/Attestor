"""Tests for attestor.ledger.swaption -- premium, exercise, close, expiry."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from attestor.core.money import NonEmptyStr
from attestor.core.party import CounterpartyRoleEnum
from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import PayerReceiver, Period, UtcDatetime
from attestor.gateway.types import CanonicalOrder, OrderSide, OrderType
from attestor.instrument.credit_types import SwaptionPayoutSpec
from attestor.instrument.derivative_types import (
    SettlementTypeEnum,
    SwaptionDetail,
    SwaptionType,
)
from attestor.instrument.fx_types import (
    DayCountConvention,
    IRSwapPayoutSpec,
    PaymentFrequency,
)
from attestor.instrument.types import Instrument, Party
from attestor.ledger.engine import LedgerEngine
from attestor.ledger.swaption import (
    create_swaption_cash_settlement,
    create_swaption_exercise_close,
    create_swaption_expiry_close,
    create_swaption_premium_transaction,
    exercise_swaption_into_irs,
)
from attestor.ledger.transactions import Account, AccountType, ExecuteResult
from attestor.oracle.observable import FloatingRateIndex, FloatingRateIndexEnum

_TS = UtcDatetime(value=datetime(2025, 7, 1, 10, 0, 0, tzinfo=UTC))
_LEI_A = "529900HNOAA1KXQJUQ27"
_LEI_B = "529900ODI3JL1O4COU11"
_PR = PayerReceiver(payer=CounterpartyRoleEnum.PARTY1, receiver=CounterpartyRoleEnum.PARTY2)
_SOFR = FloatingRateIndex(
    index=FloatingRateIndexEnum.SOFR, designated_maturity=Period(1, "D"),
)


def _make_swaption_detail(
    swaption_type: SwaptionType = SwaptionType.PAYER,
    settlement_type: SettlementTypeEnum = SettlementTypeEnum.PHYSICAL,
) -> SwaptionDetail:
    return unwrap(SwaptionDetail.create(
        swaption_type=swaption_type,
        expiry_date=date(2026, 1, 15),
        underlying_fixed_rate=Decimal("0.035"),
        underlying_float_index="USD-SOFR",
        underlying_tenor_months=60,
        settlement_type=settlement_type,
    ))


def _make_underlying_swap() -> IRSwapPayoutSpec:
    return unwrap(IRSwapPayoutSpec.create(
        fixed_rate=Decimal("0.035"),
        float_index=_SOFR,
        day_count=DayCountConvention.ACT_360,
        payment_frequency=PaymentFrequency.SEMI_ANNUAL,
        notional=Decimal("10000000"),
        currency="USD",
        start_date=date(2026, 1, 15),
        end_date=date(2031, 1, 15),
        payer_receiver=_PR,
    ))


def _make_swaption_payout(
    swaption_type: SwaptionType = SwaptionType.PAYER,
    settlement_type: SettlementTypeEnum = SettlementTypeEnum.PHYSICAL,
) -> SwaptionPayoutSpec:
    return unwrap(SwaptionPayoutSpec.create(
        swaption_type=swaption_type,
        strike=Decimal("0.035"),
        exercise_date=date(2026, 1, 15),
        underlying_swap=_make_underlying_swap(),
        settlement_type=settlement_type,
        currency="USD",
        notional=Decimal("10000000"),
        payer_receiver=_PR,
    ))


def _make_parties() -> tuple[Party, ...]:
    return (
        unwrap(Party.create("PARTY-A", "Alpha Fund", _LEI_A)),
        unwrap(Party.create("PARTY-B", "Beta Bank", _LEI_B)),
    )


def _swaption_order(
    swaption_type: SwaptionType = SwaptionType.PAYER,
    settlement_type: SettlementTypeEnum = SettlementTypeEnum.PHYSICAL,
) -> CanonicalOrder:
    detail = _make_swaption_detail(swaption_type, settlement_type)
    return unwrap(CanonicalOrder.create(
        order_id="SWN-001",
        instrument_id="SWAPTION-PAYER-5Y",
        isin=None,
        side=OrderSide.BUY,
        quantity=Decimal("5"),
        price=Decimal("25000"),
        currency="USD",
        order_type=OrderType.LIMIT,
        counterparty_lei=_LEI_A,
        executing_party_lei=_LEI_B,
        trade_date=date(2025, 7, 1),
        settlement_date=date(2025, 7, 2),
        venue="OTC",
        timestamp=_TS,
        instrument_detail=detail,
    ))


def _setup_engine() -> LedgerEngine:
    engine = LedgerEngine()
    for name, atype in [
        ("BUYER-CASH", AccountType.CASH),
        ("SELLER-CASH", AccountType.CASH),
        ("BUYER-POS", AccountType.DERIVATIVES),
        ("SELLER-POS", AccountType.DERIVATIVES),
        ("HOLDER-CASH", AccountType.CASH),
        ("WRITER-CASH", AccountType.CASH),
        ("HOLDER-POS", AccountType.DERIVATIVES),
        ("WRITER-POS", AccountType.DERIVATIVES),
    ]:
        engine.register_account(Account(
            account_id=unwrap(NonEmptyStr.parse(name)),
            account_type=atype,
        ))
    return engine


# ---------------------------------------------------------------------------
# Premium transaction
# ---------------------------------------------------------------------------


class TestSwaptionPremium:
    def test_creates_two_moves(self) -> None:
        tx = unwrap(create_swaption_premium_transaction(
            _swaption_order(), "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-SP1",
        ))
        assert len(tx.moves) == 2

    def test_premium_amount_no_multiplier(self) -> None:
        # Premium = price * quantity = 25000 * 5 = 125000
        tx = unwrap(create_swaption_premium_transaction(
            _swaption_order(), "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-SP2",
        ))
        cash_move = tx.moves[0]
        assert cash_move.quantity.value == Decimal("125000")

    def test_cash_move_direction(self) -> None:
        tx = unwrap(create_swaption_premium_transaction(
            _swaption_order(), "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-SP3",
        ))
        cash_move = tx.moves[0]
        assert cash_move.source == "BUYER-CASH"
        assert cash_move.destination == "SELLER-CASH"
        assert cash_move.unit == "USD"

    def test_position_move_quantity(self) -> None:
        tx = unwrap(create_swaption_premium_transaction(
            _swaption_order(), "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-SP4",
        ))
        pos_move = tx.moves[1]
        assert pos_move.quantity.value == Decimal("5")

    def test_position_move_contract_unit(self) -> None:
        tx = unwrap(create_swaption_premium_transaction(
            _swaption_order(), "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-SP5",
        ))
        pos_move = tx.moves[1]
        assert pos_move.unit == "SWAPTION-PAYER-2026-01-15"

    def test_conservation_cash_and_position(self) -> None:
        engine = _setup_engine()
        tx = unwrap(create_swaption_premium_transaction(
            _swaption_order(), "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-SP-CON",
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert unwrap(result) == ExecuteResult.APPLIED
        # sigma(USD) == 0
        assert engine.total_supply("USD") == Decimal(0)
        # sigma(swaption position) == 0
        contract = tx.moves[1].unit
        assert engine.total_supply(contract) == Decimal(0)

    def test_reject_non_swaption_detail(self) -> None:
        # Use an equity order (default EquityDetail)
        order = unwrap(CanonicalOrder.create(
            order_id="EQ-001", instrument_id="AAPL", isin=None,
            side=OrderSide.BUY, quantity=Decimal("100"),
            price=Decimal("175"), currency="USD",
            order_type=OrderType.LIMIT,
            counterparty_lei=_LEI_A,
            executing_party_lei=_LEI_B,
            trade_date=date(2025, 7, 1),
            settlement_date=date(2025, 7, 2),
            venue="XNYS", timestamp=_TS,
        ))
        result = create_swaption_premium_transaction(
            order, "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-FAIL",
        )
        assert isinstance(result, Err)
        assert "SwaptionDetail" in result.error.message


# ---------------------------------------------------------------------------
# Exercise swaption into IRS
# ---------------------------------------------------------------------------


class TestExerciseSwaptionIntoIrs:
    def test_payer_swaption_creates_valid_irs(self) -> None:
        payout = _make_swaption_payout(SwaptionType.PAYER)
        result = exercise_swaption_into_irs(
            payout, date(2026, 1, 15), _make_parties(), "IRS-FROM-SWN-001",
        )
        assert isinstance(result, Ok)
        irs = unwrap(result)
        assert isinstance(irs, Instrument)

    def test_receiver_swaption_creates_valid_irs(self) -> None:
        payout = _make_swaption_payout(SwaptionType.RECEIVER)
        result = exercise_swaption_into_irs(
            payout, date(2026, 1, 15), _make_parties(), "IRS-FROM-SWN-002",
        )
        assert isinstance(result, Ok)

    def test_irs_fixed_rate_matches_strike(self) -> None:
        payout = _make_swaption_payout()
        irs = unwrap(exercise_swaption_into_irs(
            payout, date(2026, 1, 15), _make_parties(), "IRS-FROM-SWN-003",
        ))
        payout_spec = irs.product.economic_terms.payouts[0]
        assert isinstance(payout_spec, IRSwapPayoutSpec)
        assert payout_spec.fixed_leg.fixed_rate == Decimal("0.035")

    def test_irs_start_date_matches_underlying(self) -> None:
        payout = _make_swaption_payout()
        irs = unwrap(exercise_swaption_into_irs(
            payout, date(2026, 1, 15), _make_parties(), "IRS-FROM-SWN-004",
        ))
        payout_spec = irs.product.economic_terms.payouts[0]
        assert isinstance(payout_spec, IRSwapPayoutSpec)
        assert payout_spec.start_date == date(2026, 1, 15)

    def test_irs_end_date_matches_underlying(self) -> None:
        payout = _make_swaption_payout()
        irs = unwrap(exercise_swaption_into_irs(
            payout, date(2026, 1, 15), _make_parties(), "IRS-FROM-SWN-005",
        ))
        payout_spec = irs.product.economic_terms.payouts[0]
        assert isinstance(payout_spec, IRSwapPayoutSpec)
        assert payout_spec.end_date == date(2031, 1, 15)

    def test_irs_notional_matches_swaption(self) -> None:
        payout = _make_swaption_payout()
        irs = unwrap(exercise_swaption_into_irs(
            payout, date(2026, 1, 15), _make_parties(), "IRS-FROM-SWN-006",
        ))
        payout_spec = irs.product.economic_terms.payouts[0]
        assert isinstance(payout_spec, IRSwapPayoutSpec)
        assert payout_spec.fixed_leg.notional.value == Decimal("10000000")

    def test_irs_float_index_matches_underlying(self) -> None:
        payout = _make_swaption_payout()
        irs = unwrap(exercise_swaption_into_irs(
            payout, date(2026, 1, 15), _make_parties(), "IRS-FROM-SWN-007",
        ))
        payout_spec = irs.product.economic_terms.payouts[0]
        assert isinstance(payout_spec, IRSwapPayoutSpec)
        assert payout_spec.float_leg.float_index.index == FloatingRateIndexEnum.SOFR


# ---------------------------------------------------------------------------
# Physical exercise close
# ---------------------------------------------------------------------------


class TestSwaptionExerciseClose:
    def test_single_move(self) -> None:
        tx = unwrap(create_swaption_exercise_close(
            "HOLDER-POS", "WRITER-POS",
            "SWAPTION-PAYER-2026-01-15", Decimal("5"),
            "TX-EC1", _TS,
        ))
        assert len(tx.moves) == 1

    def test_position_returned(self) -> None:
        tx = unwrap(create_swaption_exercise_close(
            "HOLDER-POS", "WRITER-POS",
            "SWAPTION-PAYER-2026-01-15", Decimal("5"),
            "TX-EC2", _TS,
        ))
        move = tx.moves[0]
        assert move.source == "HOLDER-POS"
        assert move.destination == "WRITER-POS"
        assert move.unit == "SWAPTION-PAYER-2026-01-15"
        assert move.quantity.value == Decimal("5")

    def test_conservation_in_engine(self) -> None:
        engine = _setup_engine()
        contract = "SWAPTION-PAYER-2026-01-15"
        tx = unwrap(create_swaption_exercise_close(
            "HOLDER-POS", "WRITER-POS",
            contract, Decimal("5"), "TX-EC-CON", _TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert engine.total_supply(contract) == Decimal(0)


# ---------------------------------------------------------------------------
# Cash settlement
# ---------------------------------------------------------------------------


class TestSwaptionCashSettlement:
    def test_creates_two_moves(self) -> None:
        tx = unwrap(create_swaption_cash_settlement(
            "HOLDER-CASH", "WRITER-CASH",
            "HOLDER-POS", "WRITER-POS",
            settlement_amount=Decimal("500000"),
            currency="USD",
            contract_unit="SWAPTION-PAYER-2026-01-15",
            quantity=Decimal("5"),
            tx_id="TX-CS1",
            timestamp=_TS,
        ))
        assert len(tx.moves) == 2

    def test_cash_direction(self) -> None:
        tx = unwrap(create_swaption_cash_settlement(
            "HOLDER-CASH", "WRITER-CASH",
            "HOLDER-POS", "WRITER-POS",
            settlement_amount=Decimal("500000"),
            currency="USD",
            contract_unit="SWAPTION-PAYER-2026-01-15",
            quantity=Decimal("5"),
            tx_id="TX-CS2",
            timestamp=_TS,
        ))
        cash_move = tx.moves[0]
        assert cash_move.source == "WRITER-CASH"
        assert cash_move.destination == "HOLDER-CASH"
        assert cash_move.quantity.value == Decimal("500000")

    def test_position_close_direction(self) -> None:
        tx = unwrap(create_swaption_cash_settlement(
            "HOLDER-CASH", "WRITER-CASH",
            "HOLDER-POS", "WRITER-POS",
            settlement_amount=Decimal("500000"),
            currency="USD",
            contract_unit="SWAPTION-PAYER-2026-01-15",
            quantity=Decimal("5"),
            tx_id="TX-CS3",
            timestamp=_TS,
        ))
        pos_move = tx.moves[1]
        assert pos_move.source == "HOLDER-POS"
        assert pos_move.destination == "WRITER-POS"

    def test_conservation_cash_and_position(self) -> None:
        engine = _setup_engine()
        contract = "SWAPTION-PAYER-2026-01-15"
        tx = unwrap(create_swaption_cash_settlement(
            "HOLDER-CASH", "WRITER-CASH",
            "HOLDER-POS", "WRITER-POS",
            settlement_amount=Decimal("500000"),
            currency="USD",
            contract_unit=contract,
            quantity=Decimal("5"),
            tx_id="TX-CS-CON",
            timestamp=_TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply(contract) == Decimal(0)


# ---------------------------------------------------------------------------
# Expiry close
# ---------------------------------------------------------------------------


class TestSwaptionExpiryClose:
    def test_single_move(self) -> None:
        tx = unwrap(create_swaption_expiry_close(
            "HOLDER-POS", "WRITER-POS",
            "SWAPTION-PAYER-2026-01-15", Decimal("5"),
            "TX-EXP1", _TS,
        ))
        assert len(tx.moves) == 1

    def test_position_returned(self) -> None:
        tx = unwrap(create_swaption_expiry_close(
            "HOLDER-POS", "WRITER-POS",
            "SWAPTION-PAYER-2026-01-15", Decimal("5"),
            "TX-EXP2", _TS,
        ))
        move = tx.moves[0]
        assert move.source == "HOLDER-POS"
        assert move.destination == "WRITER-POS"

    def test_conservation_in_engine(self) -> None:
        engine = _setup_engine()
        contract = "SWAPTION-PAYER-2026-01-15"
        tx = unwrap(create_swaption_expiry_close(
            "HOLDER-POS", "WRITER-POS",
            contract, Decimal("5"), "TX-EXP-CON", _TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert engine.total_supply(contract) == Decimal(0)

    def test_zero_quantity_rejected(self) -> None:
        result = create_swaption_expiry_close(
            "HOLDER-POS", "WRITER-POS",
            "SWAPTION-PAYER-2026-01-15", Decimal("0"),
            "TX-FAIL", _TS,
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Full lifecycle: premium -> expiry (conservation)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Hypothesis: conservation properties
# ---------------------------------------------------------------------------


class TestSwaptionConservationHypothesis:
    @given(
        price=st.decimals(
            min_value=Decimal("100"),
            max_value=Decimal("1000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
        qty=st.decimals(
            min_value=Decimal("1"),
            max_value=Decimal("100"),
            places=0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_premium_conservation_property(
        self, price: Decimal, qty: Decimal,
    ) -> None:
        """sigma(USD)==0 and sigma(position)==0 for random premium params."""
        detail = _make_swaption_detail()
        order = unwrap(CanonicalOrder.create(
            order_id="SWN-HYP",
            instrument_id="SWAPTION-PAYER-5Y",
            isin=None,
            side=OrderSide.BUY,
            quantity=qty,
            price=price,
            currency="USD",
            order_type=OrderType.LIMIT,
            counterparty_lei=_LEI_A,
            executing_party_lei=_LEI_B,
            trade_date=date(2025, 7, 1),
            settlement_date=date(2025, 7, 2),
            venue="OTC",
            timestamp=_TS,
            instrument_detail=detail,
        ))
        engine = _setup_engine()
        tx = unwrap(create_swaption_premium_transaction(
            order, "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-HYP-PREM",
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply(tx.moves[1].unit) == Decimal(0)

    @given(
        qty=st.decimals(
            min_value=Decimal("1"),
            max_value=Decimal("100"),
            places=0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_exercise_close_conservation_property(
        self, qty: Decimal,
    ) -> None:
        """sigma(position)==0 after exercise close for any quantity."""
        engine = _setup_engine()
        contract = "SWAPTION-PAYER-2026-01-15"
        tx = unwrap(create_swaption_exercise_close(
            "HOLDER-POS", "WRITER-POS",
            contract, qty, "TX-HYP-EC", _TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert engine.total_supply(contract) == Decimal(0)

    @given(
        settle_amt=st.decimals(
            min_value=Decimal("100"),
            max_value=Decimal("10000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
        qty=st.decimals(
            min_value=Decimal("1"),
            max_value=Decimal("100"),
            places=0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_cash_settlement_conservation_property(
        self, settle_amt: Decimal, qty: Decimal,
    ) -> None:
        """sigma(USD)==0 and sigma(position)==0 after cash settlement."""
        engine = _setup_engine()
        contract = "SWAPTION-PAYER-2026-01-15"
        tx = unwrap(create_swaption_cash_settlement(
            "HOLDER-CASH", "WRITER-CASH",
            "HOLDER-POS", "WRITER-POS",
            settlement_amount=settle_amt,
            currency="USD",
            contract_unit=contract,
            quantity=qty,
            tx_id="TX-HYP-CS",
            timestamp=_TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply(contract) == Decimal(0)

    @given(
        qty=st.decimals(
            min_value=Decimal("1"),
            max_value=Decimal("100"),
            places=0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_expiry_close_conservation_property(
        self, qty: Decimal,
    ) -> None:
        """sigma(position)==0 after expiry close for any quantity."""
        engine = _setup_engine()
        contract = "SWAPTION-PAYER-2026-01-15"
        tx = unwrap(create_swaption_expiry_close(
            "HOLDER-POS", "WRITER-POS",
            contract, qty, "TX-HYP-EXP", _TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert engine.total_supply(contract) == Decimal(0)


# ---------------------------------------------------------------------------
# Full lifecycle: premium -> expiry (conservation)
# ---------------------------------------------------------------------------


class TestSwaptionFullLifecycle:
    def test_premium_then_expiry_sigma_zero(self) -> None:
        engine = _setup_engine()
        order = _swaption_order()
        contract = "SWAPTION-PAYER-2026-01-15"

        # 1. Premium transaction
        premium_tx = unwrap(create_swaption_premium_transaction(
            order, "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-PREM",
        ))
        unwrap(engine.execute(premium_tx))

        # Verify positions after premium
        assert engine.get_balance("BUYER-POS", contract) == Decimal("5")
        assert engine.get_balance("SELLER-POS", contract) == Decimal("-5")

        # 2. Expiry (unexercised -- close positions)
        expiry_tx = unwrap(create_swaption_expiry_close(
            "BUYER-POS", "SELLER-POS",
            contract, Decimal("5"), "TX-EXP", _TS,
        ))
        unwrap(engine.execute(expiry_tx))

        # sigma for all units == 0
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply(contract) == Decimal(0)
        assert engine.get_balance("BUYER-POS", contract) == Decimal(0)
        assert engine.get_balance("SELLER-POS", contract) == Decimal(0)
