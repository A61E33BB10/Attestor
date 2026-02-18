"""Invariant tests for Phase 4 credit, swaption, and collateral instruments.

Conservation Laws (CL-C1 through CL-C8):
  CL-C1: CDS premium payment conservation — sigma(currency) == 0.
  CL-C2: CDS credit event settlement conservation — sigma(currency) == 0.
  CL-C3: CDS full lifecycle — sigma == 0 at every step.
  CL-C4: Swaption premium conservation — sigma(cash) == 0, sigma(position) == 0.
  CL-C5: Swaption exercise close — sigma(position) returns to 0.
  CL-C6: Swaption cash settlement — sigma(cash) == 0, sigma(position) == 0.
  CL-C7: Collateral margin call conservation — sigma(collateral_unit) == 0.
  CL-C8: Collateral substitution — sigma(old_unit) == 0 AND sigma(new_unit) == 0.

Arbitrage Freedom (AF-CR, AF-VS):
  AF-CR: Bootstrapped credit curve passes all CreditCurve.create gates.
  AF-VS: Calibrated vol surface passes all VolSurface.create gates.

Commutativity Squares (CS-C5, CS-C6):
  CS-C5: Same CDS quotes produce same credit curve (deterministic).
  CS-C6: Same vol quotes produce same VolSurface (deterministic).
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
from attestor.instrument.derivative_types import SettlementTypeEnum, SwaptionDetail, SwaptionType
from attestor.instrument.fx_types import DayCountConvention, PaymentFrequency
from attestor.ledger.cds import (
    ScheduledCDSPremium,
    create_cds_credit_event_settlement,
    create_cds_premium_transaction,
    create_cds_trade_transaction,
    generate_cds_premium_schedule,
)
from attestor.ledger.collateral import (
    create_collateral_return_transaction,
    create_collateral_substitution_transaction,
    create_margin_call_transaction,
)
from attestor.ledger.engine import LedgerEngine
from attestor.ledger.swaption import (
    create_swaption_cash_settlement,
    create_swaption_exercise_close,
    create_swaption_premium_transaction,
)
from attestor.ledger.transactions import Account, AccountType, ExecuteResult
from attestor.oracle.calibration import ModelConfig, YieldCurve
from attestor.oracle.credit_curve import (
    CDSQuote,
    bootstrap_credit_curve,
    survival_probability,
)
from attestor.oracle.vol_surface import (
    SVIParameters,
    VolSurface,
    implied_vol,
    svi_total_variance,
)

_TS = UtcDatetime(value=datetime(2025, 9, 20, 14, 0, 0, tzinfo=UTC))
_CDS_ID = "CDS-INV-001"
_LEI_A = "529900HNOAA1KXQJUQ27"
_LEI_B = "529900ODI3JL1O4COU11"


# ---------------------------------------------------------------------------
# Shared setup helpers
# ---------------------------------------------------------------------------


def _cds_engine() -> LedgerEngine:
    """Create engine with CDS-appropriate accounts."""
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
    return engine


def _swaption_engine() -> LedgerEngine:
    """Create engine with swaption-appropriate accounts."""
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


def _collateral_engine() -> LedgerEngine:
    """Create engine with collateral-appropriate accounts."""
    engine = LedgerEngine()
    for name in [
        "CALLER-COLLATERAL",
        "POSTER-COLLATERAL",
        "HOLDER-COLLATERAL",
        "RECEIVER-COLLATERAL",
    ]:
        engine.register_account(Account(
            account_id=unwrap(NonEmptyStr.parse(name)),
            account_type=AccountType.COLLATERAL,
        ))
    return engine


def _make_premium(
    amount: Decimal = Decimal("12500"),
    currency: str = "USD",
) -> ScheduledCDSPremium:
    return ScheduledCDSPremium(
        payment_date=date(2025, 12, 20),
        amount=amount,
        currency=NonEmptyStr(value=currency),
        period_start=date(2025, 9, 20),
        period_end=date(2025, 12, 20),
        day_count_fraction=Decimal("91") / Decimal("360"),
    )


def _swaption_order() -> CanonicalOrder:
    """Create a standard swaption order for testing."""
    detail = unwrap(SwaptionDetail.create(
        swaption_type=SwaptionType.PAYER,
        expiry_date=date(2026, 1, 15),
        underlying_fixed_rate=Decimal("0.035"),
        underlying_float_index="USD-SOFR",
        underlying_tenor_months=60,
        settlement_type=SettlementTypeEnum.PHYSICAL,
    ))
    return unwrap(CanonicalOrder.create(
        order_id="SWN-INV-001",
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


def _sample_config() -> ModelConfig:
    return unwrap(ModelConfig.create(
        config_id="CFG-CDS-INV",
        model_class="CDS_BOOTSTRAP",
        code_version="1.0.0",
    ))


def _sample_discount_curve() -> YieldCurve:
    return unwrap(YieldCurve.create(
        currency="USD",
        as_of=date(2025, 6, 15),
        tenors=(Decimal("1"), Decimal("3"), Decimal("5")),
        discount_factors=(Decimal("0.96"), Decimal("0.90"), Decimal("0.85")),
        model_config_ref="CFG-YC-INV",
    ))


def _sample_quotes() -> tuple[CDSQuote, ...]:
    """3-point CDS quote strip: 1Y, 3Y, 5Y."""
    return (
        CDSQuote(
            reference_entity=NonEmptyStr(value="ACME Corp"),
            tenor=Decimal("1"),
            spread=Decimal("0.01"),
            recovery_rate=Decimal("0.4"),
            currency=NonEmptyStr(value="USD"),
        ),
        CDSQuote(
            reference_entity=NonEmptyStr(value="ACME Corp"),
            tenor=Decimal("3"),
            spread=Decimal("0.012"),
            recovery_rate=Decimal("0.4"),
            currency=NonEmptyStr(value="USD"),
        ),
        CDSQuote(
            reference_entity=NonEmptyStr(value="ACME Corp"),
            tenor=Decimal("5"),
            spread=Decimal("0.015"),
            recovery_rate=Decimal("0.4"),
            currency=NonEmptyStr(value="USD"),
        ),
    )


def _make_svi_slice(expiry: Decimal) -> SVIParameters:
    """Make a valid SVI slice with the given expiry."""
    return unwrap(SVIParameters.create(
        a=Decimal("0.04"),
        b=Decimal("0.4"),
        rho=Decimal("-0.4"),
        m=Decimal("0"),
        sigma=Decimal("0.2"),
        expiry=expiry,
    ))


# ===========================================================================
# CL-C1: CDS Premium Conservation (Hypothesis property-based)
# ===========================================================================


class TestCLC1CDSPremiumConservation:
    """CL-C1: For every CDS premium payment, sigma(currency) unchanged."""

    @given(
        notional=st.decimals(
            min_value=Decimal("1000"),
            max_value=Decimal("100000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
        spread=st.decimals(
            min_value=Decimal("0.0001"),
            max_value=Decimal("0.05"),
            places=4,
            allow_nan=False,
            allow_infinity=False,
        ).filter(lambda d: d > 0),
    )
    @settings(max_examples=200, deadline=None)
    def test_conservation(self, notional: Decimal, spread: Decimal) -> None:
        """Generate a single premium, create transaction, execute, verify sigma==0."""
        engine = _cds_engine()

        schedule_result = generate_cds_premium_schedule(
            notional=notional,
            spread=spread,
            effective_date=date(2025, 3, 20),
            maturity_date=date(2025, 6, 20),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        )
        assert isinstance(schedule_result, Ok)
        schedule = unwrap(schedule_result)
        assert len(schedule) >= 1

        premium = schedule[0]
        tx_result = create_cds_premium_transaction(
            "BUYER-CASH", "SELLER-CASH",
            premium, "TX-CLC1", _TS,
        )
        assert isinstance(tx_result, Ok)
        tx = unwrap(tx_result)

        exec_result = engine.execute(tx)
        assert isinstance(exec_result, Ok)
        assert engine.total_supply("USD") == Decimal(0)


# ===========================================================================
# CL-C2: CDS Credit Event Conservation (Hypothesis property-based)
# ===========================================================================


class TestCLC2CDSCreditEventConservation:
    """CL-C2: For every credit event settlement, sigma(currency) unchanged."""

    @given(
        notional=st.decimals(
            min_value=Decimal("1000"),
            max_value=Decimal("100000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
        auction_price=st.decimals(
            min_value=Decimal("0"),
            max_value=Decimal("0.999"),
            places=3,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_conservation(self, notional: Decimal, auction_price: Decimal) -> None:
        """Create credit event settlement, execute, verify sigma==0."""
        engine = _cds_engine()

        result = create_cds_credit_event_settlement(
            "BUYER-CASH", "SELLER-CASH",
            notional=notional,
            auction_price=auction_price,
            currency="USD",
            tx_id="TX-CLC2",
            timestamp=_TS,
        )
        assert isinstance(result, Ok), f"Unexpected Err: {result}"
        tx = unwrap(result)

        exec_result = engine.execute(tx)
        assert isinstance(exec_result, Ok)
        assert engine.total_supply("USD") == Decimal(0)


# ===========================================================================
# CL-C3: CDS Full Lifecycle (deterministic)
# ===========================================================================


class TestCLC3CDSFullLifecycle:
    """CL-C3: Trade -> 4 premiums -> credit event -> settlement. sigma == 0 each step."""

    def test_conservation(self) -> None:
        engine = _cds_engine()
        contract = f"CDS-{_CDS_ID}"

        # Step 0: Open position using create_cds_trade_transaction
        open_tx = unwrap(create_cds_trade_transaction(
            "BUYER-POS", "SELLER-POS",
            contract, Decimal("1"), "TX-CLC3-OPEN", _TS,
        ))
        unwrap(engine.execute(open_tx))
        assert engine.total_supply(contract) == Decimal(0)

        # Generate 4 quarterly premiums for a 1Y CDS
        schedule = unwrap(generate_cds_premium_schedule(
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            effective_date=date(2025, 3, 20),
            maturity_date=date(2026, 3, 20),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        assert len(schedule) == 4

        # Execute each premium -- sigma(USD) == 0 at every step
        for i, premium in enumerate(schedule):
            tx = unwrap(create_cds_premium_transaction(
                "BUYER-CASH", "SELLER-CASH",
                premium, f"TX-CLC3-PREM-{i}", _TS,
            ))
            result = engine.execute(tx)
            assert isinstance(result, Ok)
            assert unwrap(result) == ExecuteResult.APPLIED
            assert engine.total_supply("USD") == Decimal(0), (
                f"sigma(USD) != 0 after premium {i}"
            )

        # Credit event settlement with accrued premium + position close
        ce_tx = unwrap(create_cds_credit_event_settlement(
            "BUYER-CASH", "SELLER-CASH",
            notional=Decimal("10000000"),
            auction_price=Decimal("0.40"),
            currency="USD",
            tx_id="TX-CLC3-CE",
            timestamp=_TS,
            accrued_premium=Decimal("12500"),
            buyer_position_account="BUYER-POS",
            seller_position_account="SELLER-POS",
            contract_unit=contract,
            position_quantity=Decimal("1"),
        ))
        result = engine.execute(ce_tx)
        assert isinstance(result, Ok)
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply(contract) == Decimal(0)
        # Position is fully closed
        assert engine.get_balance("BUYER-POS", contract) == Decimal(0)
        assert engine.get_balance("SELLER-POS", contract) == Decimal(0)

    def test_premium_positions_accumulate_correctly(self) -> None:
        """Verify buyer/seller cash positions are consistent with premiums paid."""
        engine = _cds_engine()

        schedule = unwrap(generate_cds_premium_schedule(
            notional=Decimal("5000000"),
            spread=Decimal("0.005"),
            effective_date=date(2025, 3, 20),
            maturity_date=date(2026, 3, 20),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="EUR",
        ))

        total_paid = Decimal(0)
        for i, premium in enumerate(schedule):
            tx = unwrap(create_cds_premium_transaction(
                "BUYER-CASH", "SELLER-CASH",
                premium, f"TX-CLC3B-{i}", _TS,
            ))
            unwrap(engine.execute(tx))
            total_paid += premium.amount

        assert engine.get_balance("BUYER-CASH", "EUR") == -total_paid
        assert engine.get_balance("SELLER-CASH", "EUR") == total_paid
        assert engine.total_supply("EUR") == Decimal(0)


# ===========================================================================
# CL-C4: Swaption Premium Conservation (Hypothesis property-based)
# ===========================================================================


class TestCLC4SwaptionPremiumConservation:
    """CL-C4: sigma(cash) == 0, sigma(swaption_position) == 0 after premium."""

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
    def test_conservation(self, price: Decimal, qty: Decimal) -> None:
        """Swaption premium: sigma(USD) == 0, sigma(position) == 0."""
        detail = unwrap(SwaptionDetail.create(
            swaption_type=SwaptionType.PAYER,
            expiry_date=date(2026, 1, 15),
            underlying_fixed_rate=Decimal("0.035"),
            underlying_float_index="USD-SOFR",
            underlying_tenor_months=60,
            settlement_type=SettlementTypeEnum.PHYSICAL,
        ))
        order = unwrap(CanonicalOrder.create(
            order_id="SWN-CLC4",
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

        engine = _swaption_engine()
        tx = unwrap(create_swaption_premium_transaction(
            order, "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-CLC4",
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert unwrap(result) == ExecuteResult.APPLIED

        # sigma(cash) == 0
        assert engine.total_supply("USD") == Decimal(0)
        # sigma(swaption position) == 0
        contract = tx.moves[1].unit
        assert engine.total_supply(contract) == Decimal(0)


# ===========================================================================
# CL-C5: Swaption Exercise Close Conservation (deterministic)
# ===========================================================================


class TestCLC5SwaptionExerciseConservation:
    """CL-C5: sigma(position) returns to 0 after exercise close."""

    def test_conservation(self) -> None:
        engine = _swaption_engine()
        order = _swaption_order()
        contract = "SWAPTION-PAYER-2026-01-15"

        # Step 1: Premium (opens position)
        premium_tx = unwrap(create_swaption_premium_transaction(
            order, "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-CLC5-PREM",
        ))
        unwrap(engine.execute(premium_tx))
        assert engine.get_balance("BUYER-POS", contract) == Decimal("5")
        assert engine.get_balance("SELLER-POS", contract) == Decimal("-5")
        assert engine.total_supply(contract) == Decimal(0)

        # Step 2: Exercise close (closes position)
        close_tx = unwrap(create_swaption_exercise_close(
            "BUYER-POS", "SELLER-POS",
            contract, Decimal("5"), "TX-CLC5-CLOSE", _TS,
        ))
        unwrap(engine.execute(close_tx))

        # sigma(position) returns to 0
        assert engine.total_supply(contract) == Decimal(0)
        assert engine.get_balance("BUYER-POS", contract) == Decimal(0)
        assert engine.get_balance("SELLER-POS", contract) == Decimal(0)

    def test_sigma_cash_unchanged_by_exercise(self) -> None:
        """Exercise close does not touch cash -- sigma(USD) still 0."""
        engine = _swaption_engine()
        order = _swaption_order()
        contract = "SWAPTION-PAYER-2026-01-15"

        premium_tx = unwrap(create_swaption_premium_transaction(
            order, "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-CLC5B-PREM",
        ))
        unwrap(engine.execute(premium_tx))

        close_tx = unwrap(create_swaption_exercise_close(
            "BUYER-POS", "SELLER-POS",
            contract, Decimal("5"), "TX-CLC5B-CLOSE", _TS,
        ))
        unwrap(engine.execute(close_tx))

        assert engine.total_supply("USD") == Decimal(0)


# ===========================================================================
# CL-C6: Swaption Cash Settlement Conservation (deterministic)
# ===========================================================================


class TestCLC6SwaptionCashSettlementConservation:
    """CL-C6: sigma(cash) == 0, sigma(position) == 0 after cash settlement."""

    def test_conservation(self) -> None:
        engine = _swaption_engine()
        contract = "SWAPTION-PAYER-2026-01-15"

        # Cash settlement: writer pays holder, position closes
        tx = unwrap(create_swaption_cash_settlement(
            "HOLDER-CASH", "WRITER-CASH",
            "HOLDER-POS", "WRITER-POS",
            settlement_amount=Decimal("500000"),
            currency="USD",
            contract_unit=contract,
            quantity=Decimal("5"),
            tx_id="TX-CLC6",
            timestamp=_TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)

        # sigma(cash) == 0
        assert engine.total_supply("USD") == Decimal(0)
        # sigma(position) == 0
        assert engine.total_supply(contract) == Decimal(0)

    def test_full_lifecycle_premium_then_cash_settle(self) -> None:
        """Premium -> Cash settlement: both sigma(USD) and sigma(position) are 0."""
        engine = _swaption_engine()
        order = _swaption_order()
        contract = "SWAPTION-PAYER-2026-01-15"

        # Step 1: Premium
        premium_tx = unwrap(create_swaption_premium_transaction(
            order, "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-CLC6B-PREM",
        ))
        unwrap(engine.execute(premium_tx))
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply(contract) == Decimal(0)

        # Step 2: Cash settlement (using different accounts for holder/writer)
        settle_tx = unwrap(create_swaption_cash_settlement(
            "HOLDER-CASH", "WRITER-CASH",
            "HOLDER-POS", "WRITER-POS",
            settlement_amount=Decimal("350000"),
            currency="USD",
            contract_unit=contract,
            quantity=Decimal("5"),
            tx_id="TX-CLC6B-SETTLE",
            timestamp=_TS,
        ))
        unwrap(engine.execute(settle_tx))

        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply(contract) == Decimal(0)


# ===========================================================================
# CL-C7: Collateral Conservation (Hypothesis property-based)
# ===========================================================================


class TestCLC7CollateralConservation:
    """CL-C7: For every collateral movement, sigma(collateral_unit) unchanged."""

    @given(
        quantity=st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("100000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_margin_call_conservation(self, quantity: Decimal) -> None:
        engine = _collateral_engine()

        tx = unwrap(create_margin_call_transaction(
            caller_account="CALLER-COLLATERAL",
            poster_account="POSTER-COLLATERAL",
            collateral_unit="USD-CASH",
            quantity=quantity,
            tx_id="TX-CLC7-MC",
            timestamp=_TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert engine.total_supply("USD-CASH") == Decimal(0)

    @given(
        quantity=st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("100000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_collateral_return_conservation(self, quantity: Decimal) -> None:
        engine = _collateral_engine()

        tx = unwrap(create_collateral_return_transaction(
            returner_account="CALLER-COLLATERAL",
            receiver_account="POSTER-COLLATERAL",
            collateral_unit="EUR-CASH",
            quantity=quantity,
            tx_id="TX-CLC7-RET",
            timestamp=_TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert engine.total_supply("EUR-CASH") == Decimal(0)


# ===========================================================================
# CL-C8: Collateral Substitution Conservation (deterministic)
# ===========================================================================


class TestCLC8CollateralSubstitutionConservation:
    """CL-C8: sigma(old_unit) unchanged AND sigma(new_unit) unchanged."""

    def test_conservation(self) -> None:
        engine = _collateral_engine()

        # Step 1: Margin call delivers corp bonds
        mc_tx = unwrap(create_margin_call_transaction(
            caller_account="HOLDER-COLLATERAL",
            poster_account="POSTER-COLLATERAL",
            collateral_unit="CORP-BOND-5Y",
            quantity=Decimal("1000"),
            tx_id="TX-CLC8-MC",
            timestamp=_TS,
        ))
        unwrap(engine.execute(mc_tx))
        assert engine.total_supply("CORP-BOND-5Y") == Decimal(0)

        # Step 2: Substitution -- swap corp bonds for govt bonds
        sub_tx = unwrap(create_collateral_substitution_transaction(
            poster_account="POSTER-COLLATERAL",
            holder_account="HOLDER-COLLATERAL",
            old_collateral_unit="CORP-BOND-5Y",
            old_quantity=Decimal("1000"),
            new_collateral_unit="GOVT-BOND-10Y",
            new_quantity=Decimal("900"),
            tx_id="TX-CLC8-SUB",
            timestamp=_TS,
        ))
        unwrap(engine.execute(sub_tx))

        # sigma(old) == 0
        assert engine.total_supply("CORP-BOND-5Y") == Decimal(0)
        # sigma(new) == 0
        assert engine.total_supply("GOVT-BOND-10Y") == Decimal(0)

    def test_substitution_standalone_conservation(self) -> None:
        """Even without prior margin call, substitution is conservative."""
        engine = _collateral_engine()

        sub_tx = unwrap(create_collateral_substitution_transaction(
            poster_account="POSTER-COLLATERAL",
            holder_account="HOLDER-COLLATERAL",
            old_collateral_unit="EQUITY-AAPL",
            old_quantity=Decimal("100"),
            new_collateral_unit="USD-CASH",
            new_quantity=Decimal("15000"),
            tx_id="TX-CLC8B-SUB",
            timestamp=_TS,
        ))
        result = engine.execute(sub_tx)
        assert isinstance(result, Ok)
        assert engine.total_supply("EQUITY-AAPL") == Decimal(0)
        assert engine.total_supply("USD-CASH") == Decimal(0)

    def test_round_trip_margin_then_return_net_zero(self) -> None:
        """Margin call -> return: all positions return to zero."""
        engine = _collateral_engine()

        # Post
        mc_tx = unwrap(create_margin_call_transaction(
            caller_account="CALLER-COLLATERAL",
            poster_account="POSTER-COLLATERAL",
            collateral_unit="USD",
            quantity=Decimal("5000000"),
            tx_id="TX-CLC8C-MC",
            timestamp=_TS,
        ))
        unwrap(engine.execute(mc_tx))

        # Return
        ret_tx = unwrap(create_collateral_return_transaction(
            returner_account="CALLER-COLLATERAL",
            receiver_account="POSTER-COLLATERAL",
            collateral_unit="USD",
            quantity=Decimal("5000000"),
            tx_id="TX-CLC8C-RET",
            timestamp=_TS,
        ))
        unwrap(engine.execute(ret_tx))

        assert engine.get_balance("CALLER-COLLATERAL", "USD") == Decimal(0)
        assert engine.get_balance("POSTER-COLLATERAL", "USD") == Decimal(0)
        assert engine.total_supply("USD") == Decimal(0)


# ===========================================================================
# AF-CR: Arbitrage Freedom -- Bootstrapped Credit Curve
# ===========================================================================


class TestAFCreditCurve:
    """AF-CR: bootstrapped credit curve passes all CreditCurve.create gates."""

    def test_bootstrap_passes_all_invariants(self) -> None:
        """Bootstrap from quotes -> all construction invariants hold."""
        result = bootstrap_credit_curve(
            quotes=_sample_quotes(),
            discount_curve=_sample_discount_curve(),
            config=_sample_config(),
            as_of=date(2025, 6, 15),
            reference_entity="ACME Corp",
        )
        assert isinstance(result, Ok)
        curve = result.value.value

        # Gate 1: tenors positive and ascending
        for i, t in enumerate(curve.tenors):
            assert t > Decimal(0)
            if i > 0:
                assert t > curve.tenors[i - 1]

        # Gate 2: survival probabilities in (0, 1] and monotone decreasing
        for i, q in enumerate(curve.survival_probs):
            assert Decimal(0) < q <= Decimal(1)
            if i > 0:
                assert q <= curve.survival_probs[i - 1]

        # Gate 3: hazard rates non-negative
        for h in curve.hazard_rates:
            assert h >= Decimal(0)

        # Gate 4: recovery rate in [0, 1)
        assert Decimal(0) <= curve.recovery_rate < Decimal(1)

    def test_survival_monotone_at_arbitrary_points(self) -> None:
        """Survival probability is monotone decreasing across the curve."""
        result = bootstrap_credit_curve(
            quotes=_sample_quotes(),
            discount_curve=_sample_discount_curve(),
            config=_sample_config(),
            as_of=date(2025, 6, 15),
            reference_entity="ACME Corp",
        )
        curve = unwrap(result).value

        test_points = [Decimal(str(t)) for t in
                       ("0.5", "1", "1.5", "2", "3", "4", "5", "7", "10")]
        prev_q = Decimal("1")
        for t in test_points:
            q = unwrap(survival_probability(curve, t))
            assert q <= prev_q, (
                f"Q({t})={q} > Q(prev)={prev_q} -- monotonicity violated"
            )
            assert q > Decimal(0), f"Q({t})={q} -- must be > 0"
            prev_q = q

    def test_single_quote_bootstrap(self) -> None:
        """Even a single quote produces a valid curve."""
        single = (CDSQuote(
            reference_entity=NonEmptyStr(value="SingleName"),
            tenor=Decimal("5"),
            spread=Decimal("0.02"),
            recovery_rate=Decimal("0.4"),
            currency=NonEmptyStr(value="USD"),
        ),)
        result = bootstrap_credit_curve(
            quotes=single,
            discount_curve=_sample_discount_curve(),
            config=_sample_config(),
            as_of=date(2025, 6, 15),
            reference_entity="SingleName",
        )
        assert isinstance(result, Ok)
        curve = result.value.value
        assert len(curve.tenors) == 1
        assert curve.hazard_rates[0] >= Decimal(0)
        assert Decimal(0) < curve.survival_probs[0] <= Decimal(1)


# ===========================================================================
# AF-VS: Arbitrage Freedom -- Calibrated Vol Surface
# ===========================================================================


class TestAFVolSurface:
    """AF-VS: calibrated vol surface passes all construction-guaranteed gates."""

    def test_surface_construction_invariants(self) -> None:
        """A multi-slice surface constructed via create passes all gates."""
        expiries = (Decimal("0.25"), Decimal("0.5"), Decimal("1"))
        slices = tuple(_make_svi_slice(t) for t in expiries)
        result = VolSurface.create(
            underlying="SPX",
            as_of=date(2025, 6, 15),
            expiries=expiries,
            slices=slices,
            model_config_ref="SVI-CFG-INV",
        )
        assert isinstance(result, Ok)
        surface = unwrap(result)

        # Gate 1: expiries positive and ascending
        for i, t in enumerate(surface.expiries):
            assert t > Decimal(0)
            if i > 0:
                assert t > surface.expiries[i - 1]

        # Gate 2: slice expiry matches surface expiry
        for _i, (t, sl) in enumerate(
            zip(surface.expiries, surface.slices, strict=True)
        ):
            assert sl.expiry == t

    def test_svi_constraints_hold(self) -> None:
        """All five SVI constraints hold for each slice."""
        expiries = (Decimal("0.25"), Decimal("0.5"), Decimal("1"))
        slices = tuple(_make_svi_slice(t) for t in expiries)
        surface = unwrap(VolSurface.create(
            underlying="SPX",
            as_of=date(2025, 6, 15),
            expiries=expiries,
            slices=slices,
            model_config_ref="SVI-CFG-INV",
        ))

        from attestor.core.decimal_math import sqrt_d

        for sl in surface.slices:
            # C-SVI-02: b >= 0
            assert sl.b >= Decimal(0)
            # C-SVI-03: |rho| < 1
            assert abs(sl.rho) < Decimal(1)
            # C-SVI-04: sigma > 0
            assert sl.sigma > Decimal(0)
            # C-SVI-05: b*(1+|rho|) <= 2
            assert sl.b * (Decimal(1) + abs(sl.rho)) <= Decimal(2)
            # C-SVI-01: vertex non-negativity
            vertex = sl.a + sl.b * sl.sigma * sqrt_d(
                Decimal(1) - sl.rho * sl.rho
            )
            assert vertex >= Decimal(0)

    def test_total_variance_non_negative(self) -> None:
        """w(k) >= 0 at all sampled strikes (no-arb necessary condition)."""
        slc = _make_svi_slice(Decimal("1"))
        for k_str in ("-2", "-1", "-0.5", "0", "0.5", "1", "2"):
            w = svi_total_variance(slc, Decimal(k_str))
            assert w >= Decimal(0), f"w({k_str}) = {w} < 0"

    def test_implied_vol_positive(self) -> None:
        """implied_vol > 0 at sampled (k, T) points."""
        expiries = (Decimal("0.25"), Decimal("0.5"), Decimal("1"))
        slices = tuple(_make_svi_slice(t) for t in expiries)
        surface = unwrap(VolSurface.create(
            underlying="SPX",
            as_of=date(2025, 6, 15),
            expiries=expiries,
            slices=slices,
            model_config_ref="SVI-CFG-INV",
        ))

        for t in expiries:
            for k_str in ("-1", "0", "1"):
                vol = unwrap(implied_vol(surface, Decimal(k_str), t))
                assert vol > Decimal(0), (
                    f"implied_vol(k={k_str}, T={t}) = {vol}"
                )


# ===========================================================================
# CS-C5: Calibration Commutativity -- Credit Curve
# ===========================================================================


class TestCSC5CalibrationCommutativity:
    """CS-C5: Same CDS quotes produce same credit curve (deterministic)."""

    def test_deterministic_bootstrap(self) -> None:
        """Running bootstrap twice produces identical credit curves."""
        quotes = _sample_quotes()
        dc = _sample_discount_curve()
        cfg = _sample_config()

        result_a = bootstrap_credit_curve(
            quotes=quotes,
            discount_curve=dc,
            config=cfg,
            as_of=date(2025, 6, 15),
            reference_entity="ACME Corp",
        )
        result_b = bootstrap_credit_curve(
            quotes=quotes,
            discount_curve=dc,
            config=cfg,
            as_of=date(2025, 6, 15),
            reference_entity="ACME Corp",
        )
        curve_a = unwrap(result_a).value
        curve_b = unwrap(result_b).value

        assert curve_a.tenors == curve_b.tenors
        assert curve_a.survival_probs == curve_b.survival_probs
        assert curve_a.hazard_rates == curve_b.hazard_rates
        assert curve_a.recovery_rate == curve_b.recovery_rate

    def test_deterministic_100_runs(self) -> None:
        """Bootstrap is deterministic across 100 runs (no float, no RNG)."""
        quotes = _sample_quotes()
        dc = _sample_discount_curve()
        cfg = _sample_config()

        reference_sprobs: tuple[Decimal, ...] | None = None
        reference_hazards: tuple[Decimal, ...] | None = None

        for _ in range(100):
            result = bootstrap_credit_curve(
                quotes=quotes,
                discount_curve=dc,
                config=cfg,
                as_of=date(2025, 6, 15),
                reference_entity="ACME Corp",
            )
            curve = unwrap(result).value
            if reference_sprobs is None:
                reference_sprobs = curve.survival_probs
                reference_hazards = curve.hazard_rates
            else:
                assert curve.survival_probs == reference_sprobs
                assert curve.hazard_rates == reference_hazards

    def test_quote_ordering_invariance(self) -> None:
        """Bootstrap sorts quotes by tenor, so ordering does not matter."""
        quotes_fwd = _sample_quotes()
        quotes_rev = tuple(reversed(quotes_fwd))
        dc = _sample_discount_curve()
        cfg = _sample_config()

        curve_fwd = unwrap(bootstrap_credit_curve(
            quotes=quotes_fwd, discount_curve=dc, config=cfg,
            as_of=date(2025, 6, 15), reference_entity="ACME Corp",
        )).value

        curve_rev = unwrap(bootstrap_credit_curve(
            quotes=quotes_rev, discount_curve=dc, config=cfg,
            as_of=date(2025, 6, 15), reference_entity="ACME Corp",
        )).value

        assert curve_fwd.tenors == curve_rev.tenors
        assert curve_fwd.survival_probs == curve_rev.survival_probs
        assert curve_fwd.hazard_rates == curve_rev.hazard_rates


# ===========================================================================
# CS-C6: Vol Calibration Commutativity
# ===========================================================================


class TestCSC6VolCalibrationCommutativity:
    """CS-C6: Same vol quotes produce same VolSurface (deterministic)."""

    def test_deterministic_construction(self) -> None:
        """Same inputs -> same VolSurface, twice."""
        expiries = (Decimal("0.25"), Decimal("0.5"), Decimal("1"))
        slices = tuple(_make_svi_slice(t) for t in expiries)

        surface_a = unwrap(VolSurface.create(
            underlying="SPX", as_of=date(2025, 6, 15),
            expiries=expiries, slices=slices,
            model_config_ref="SVI-CFG-001",
        ))
        surface_b = unwrap(VolSurface.create(
            underlying="SPX", as_of=date(2025, 6, 15),
            expiries=expiries, slices=slices,
            model_config_ref="SVI-CFG-001",
        ))

        assert surface_a.expiries == surface_b.expiries
        for sl_a, sl_b in zip(surface_a.slices, surface_b.slices, strict=True):
            assert sl_a.a == sl_b.a
            assert sl_a.b == sl_b.b
            assert sl_a.rho == sl_b.rho
            assert sl_a.m == sl_b.m
            assert sl_a.sigma == sl_b.sigma

    def test_implied_vol_deterministic(self) -> None:
        """Same surface + same query -> exact same implied vol."""
        expiries = (Decimal("1"),)
        slices = (_make_svi_slice(Decimal("1")),)
        surface = unwrap(VolSurface.create(
            underlying="SPX", as_of=date(2025, 6, 15),
            expiries=expiries, slices=slices,
            model_config_ref="SVI-CFG-001",
        ))

        # Query the same point 100 times
        reference_vol: Decimal | None = None
        for _ in range(100):
            vol = unwrap(implied_vol(surface, Decimal("0.3"), Decimal("1")))
            if reference_vol is None:
                reference_vol = vol
            else:
                assert vol == reference_vol

    def test_total_variance_deterministic(self) -> None:
        """svi_total_variance is a pure function -- deterministic."""
        slc = _make_svi_slice(Decimal("1"))
        reference: Decimal | None = None
        for _ in range(100):
            w = svi_total_variance(slc, Decimal("-0.5"))
            if reference is None:
                reference = w
            else:
                assert w == reference


# ===========================================================================
# Additional Hypothesis property tests (GAP-TC-01)
# ===========================================================================


class TestCDSTradeCloseRoundtrip:
    """Trade open + maturity close = net zero position for any quantity."""

    @given(
        quantity=st.decimals(
            min_value=Decimal("1"),
            max_value=Decimal("10000"),
            places=0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_trade_close_roundtrip(self, quantity: Decimal) -> None:
        engine = _cds_engine()
        contract = f"CDS-{_CDS_ID}"

        # Open position
        open_tx = unwrap(create_cds_trade_transaction(
            "BUYER-POS", "SELLER-POS",
            contract, quantity, "TX-OPEN-RT", _TS,
        ))
        unwrap(engine.execute(open_tx))
        assert engine.total_supply(contract) == Decimal(0)
        assert engine.get_balance("BUYER-POS", contract) == quantity

        # Close position (maturity or credit event)
        ce_tx = unwrap(create_cds_credit_event_settlement(
            "BUYER-CASH", "SELLER-CASH",
            notional=Decimal("10000000"),
            auction_price=Decimal("0.40"),
            currency="USD",
            tx_id="TX-CLOSE-RT",
            timestamp=_TS,
            buyer_position_account="BUYER-POS",
            seller_position_account="SELLER-POS",
            contract_unit=contract,
            position_quantity=quantity,
        ))
        unwrap(engine.execute(ce_tx))

        # Net position zero
        assert engine.get_balance("BUYER-POS", contract) == Decimal(0)
        assert engine.get_balance("SELLER-POS", contract) == Decimal(0)
        assert engine.total_supply(contract) == Decimal(0)
        assert engine.total_supply("USD") == Decimal(0)


class TestCreditCurveMonotonicityProperty:
    """Survival probability is monotone decreasing for random query points."""

    @given(
        spread_1y=st.decimals(
            min_value=Decimal("0.005"), max_value=Decimal("0.05"),
            places=4, allow_nan=False, allow_infinity=False,
        ).filter(lambda d: d > 0),
        spread_5y=st.decimals(
            min_value=Decimal("0.005"), max_value=Decimal("0.05"),
            places=4, allow_nan=False, allow_infinity=False,
        ).filter(lambda d: d > 0),
    )
    @settings(max_examples=200, deadline=None)
    def test_survival_monotone_property(
        self, spread_1y: Decimal, spread_5y: Decimal,
    ) -> None:
        """If bootstrap accepts, Q(t1) >= Q(t2) for t1 < t2."""
        from hypothesis import assume

        quotes = (
            CDSQuote(
                reference_entity=NonEmptyStr(value="ACME Corp"),
                tenor=Decimal("1"),
                spread=spread_1y,
                recovery_rate=Decimal("0.4"),
                currency=NonEmptyStr(value="USD"),
            ),
            CDSQuote(
                reference_entity=NonEmptyStr(value="ACME Corp"),
                tenor=Decimal("5"),
                spread=spread_5y,
                recovery_rate=Decimal("0.4"),
                currency=NonEmptyStr(value="USD"),
            ),
        )
        result = bootstrap_credit_curve(
            quotes=quotes,
            discount_curve=_sample_discount_curve(),
            config=_sample_config(),
            as_of=date(2025, 6, 15),
            reference_entity="ACME Corp",
        )
        # Some spread combos produce invalid curves; skip those
        assume(isinstance(result, Ok))
        curve = result.value.value

        # Monotonicity guaranteed by construction (bootstrap gate)
        prev_q = Decimal("1")
        for t_str in ("0.5", "1", "2", "3", "5", "7"):
            q = unwrap(survival_probability(curve, Decimal(t_str)))
            assert q <= prev_q, (
                f"Q({t_str})={q} > Q(prev)={prev_q}"
            )
            assert q > Decimal(0)
            prev_q = q


class TestSwaptionExerciseConservationHypothesis:
    """Swaption exercise close: sigma(position)==0 for random quantities."""

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
    def test_exercise_close_conservation(self, qty: Decimal) -> None:
        engine = _swaption_engine()
        contract = "SWAPTION-PAYER-2026-01-15"
        tx = unwrap(create_swaption_exercise_close(
            "HOLDER-POS", "WRITER-POS",
            contract, qty, "TX-HYP-EC", _TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert engine.total_supply(contract) == Decimal(0)


class TestSwaptionCashSettlementConservationHypothesis:
    """Swaption cash settlement: sigma(cash)==0 and sigma(position)==0."""

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
    def test_cash_settlement_conservation(
        self, settle_amt: Decimal, qty: Decimal,
    ) -> None:
        engine = _swaption_engine()
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


# ===========================================================================
# CS-C1..C4: Commutativity Squares (Phase 5 D6 GAP-TC-H1)
# ===========================================================================


class TestCSC1CDSPremiumCommutativity:
    """CS-C1: Two CDS premium payments in either order produce same final balances."""

    def test_order_invariance(self) -> None:
        schedule = unwrap(generate_cds_premium_schedule(
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            effective_date=date(2025, 3, 20),
            maturity_date=date(2025, 9, 20),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        assert len(schedule) >= 2

        # Order A: prem0 then prem1
        engine_a = _cds_engine()
        tx0_a = unwrap(create_cds_premium_transaction(
            "BUYER-CASH", "SELLER-CASH", schedule[0], "TX-A0", _TS,
        ))
        tx1_a = unwrap(create_cds_premium_transaction(
            "BUYER-CASH", "SELLER-CASH", schedule[1], "TX-A1", _TS,
        ))
        unwrap(engine_a.execute(tx0_a))
        unwrap(engine_a.execute(tx1_a))

        # Order B: prem1 then prem0
        engine_b = _cds_engine()
        tx0_b = unwrap(create_cds_premium_transaction(
            "BUYER-CASH", "SELLER-CASH", schedule[0], "TX-B0", _TS,
        ))
        tx1_b = unwrap(create_cds_premium_transaction(
            "BUYER-CASH", "SELLER-CASH", schedule[1], "TX-B1", _TS,
        ))
        unwrap(engine_b.execute(tx1_b))
        unwrap(engine_b.execute(tx0_b))

        bal_a_buy = engine_a.get_balance("BUYER-CASH", "USD")
        bal_b_buy = engine_b.get_balance("BUYER-CASH", "USD")
        assert bal_a_buy == bal_b_buy
        bal_a_sell = engine_a.get_balance("SELLER-CASH", "USD")
        bal_b_sell = engine_b.get_balance("SELLER-CASH", "USD")
        assert bal_a_sell == bal_b_sell


class TestCSC2CollateralCommutativity:
    """CS-C2: Two margin calls in either order produce same final balances."""

    def test_order_invariance(self) -> None:
        # Order A
        engine_a = _collateral_engine()
        mc1_a = unwrap(create_margin_call_transaction(
            "CALLER-COLLATERAL", "POSTER-COLLATERAL",
            "USD", Decimal("1000000"), "TX-MC1-A", _TS,
        ))
        mc2_a = unwrap(create_margin_call_transaction(
            "CALLER-COLLATERAL", "POSTER-COLLATERAL",
            "USD", Decimal("500000"), "TX-MC2-A", _TS,
        ))
        unwrap(engine_a.execute(mc1_a))
        unwrap(engine_a.execute(mc2_a))

        # Order B (reversed)
        engine_b = _collateral_engine()
        mc1_b = unwrap(create_margin_call_transaction(
            "CALLER-COLLATERAL", "POSTER-COLLATERAL",
            "USD", Decimal("1000000"), "TX-MC1-B", _TS,
        ))
        mc2_b = unwrap(create_margin_call_transaction(
            "CALLER-COLLATERAL", "POSTER-COLLATERAL",
            "USD", Decimal("500000"), "TX-MC2-B", _TS,
        ))
        unwrap(engine_b.execute(mc2_b))
        unwrap(engine_b.execute(mc1_b))

        assert engine_a.get_balance("CALLER-COLLATERAL", "USD") == \
            engine_b.get_balance("CALLER-COLLATERAL", "USD")


class TestCSC3ReportProjectionIdempotent:
    """CS-C3: Projecting report twice from same order produces same content."""

    def test_emir_idempotent(self) -> None:
        from attestor.gateway.parser import parse_cds_order
        from attestor.reporting.emir import project_emir_report
        raw: dict[str, object] = {
            "order_id": "CDS-CS3",
            "instrument_id": "CDS-CS3-5Y",
            "side": "BUY",
            "quantity": "1",
            "price": "100",
            "currency": "USD",
            "order_type": "LIMIT",
            "counterparty_lei": _LEI_A,
            "executing_party_lei": _LEI_B,
            "venue": "OTC",
            "trade_date": "2025-06-15",
            "timestamp": "2025-06-15T10:00:00+00:00",
            "reference_entity": "ACME Corp",
            "spread_bps": "100",
            "seniority": "SENIOR_UNSECURED",
            "protection_side": "BUYER",
            "start_date": "2025-06-20",
            "maturity_date": "2030-06-20",
        }
        order = unwrap(parse_cds_order(raw))
        r1 = unwrap(project_emir_report(order, "ATT-CS3"))
        r2 = unwrap(project_emir_report(order, "ATT-CS3"))
        assert r1.value.instrument_id == r2.value.instrument_id
        assert r1.value.direction == r2.value.direction
        assert r1.value.quantity == r2.value.quantity


class TestCSC4CreditCurveIdempotent:
    """CS-C4: Bootstrap is pure — same quotes → same curve (already tested in CS-C5,
    this specifically verifies hazard rate computation idempotence)."""

    def test_hazard_rate_idempotent(self) -> None:
        from attestor.oracle.credit_curve import hazard_rate
        curve = unwrap(bootstrap_credit_curve(
            quotes=_sample_quotes(),
            discount_curve=_sample_discount_curve(),
            config=_sample_config(),
            as_of=date(2025, 6, 15),
            reference_entity="ACME Corp",
        )).value
        h1 = unwrap(hazard_rate(curve, Decimal("0"), Decimal("1")))
        h2 = unwrap(hazard_rate(curve, Decimal("0"), Decimal("1")))
        assert h1 == h2


# ===========================================================================
# Durrleman Butterfly Failure Mode Test (Phase 5 D6 GAP-TC-H3)
# ===========================================================================


class TestDurrlemanButterflyFailure:
    """Verify that a surface with Durrleman butterfly violation is detected."""

    def test_butterfly_violation_detected(self) -> None:
        from attestor.oracle.arbitrage_gates import check_vol_surface_arbitrage_freedom
        # Construct a slice with extreme parameters that may violate Durrleman
        # condition. b=1.9, rho=0 => b*(1+|rho|)=1.9 <= 2 (valid for Roger Lee)
        # but high curvature can cause butterfly violation.
        # Durrleman condition: g(k) = (1 - kw'/2w)^2 - w'/4*(1/w + 1/4) + w''/2 >= 0
        slc = unwrap(SVIParameters.create(
            a=Decimal("0.001"),
            b=Decimal("1.9"),
            rho=Decimal("0"),
            m=Decimal("0"),
            sigma=Decimal("0.01"),  # very tight sigma => high curvature
            expiry=Decimal("1"),
        ))
        surface = unwrap(VolSurface.create(
            underlying="SPX",
            as_of=date(2025, 6, 15),
            expiries=(Decimal("1"),),
            slices=(slc,),
            model_config_ref="SVI-DURR-FAIL",
        ))
        results = unwrap(check_vol_surface_arbitrage_freedom(surface))
        # AF-VS-02 is the Durrleman butterfly check
        butterfly_result = next(r for r in results if r.check_id == "AF-VS-02")
        # With these extreme params (high b, tiny sigma), butterfly condition should fail
        assert butterfly_result.passed is False
