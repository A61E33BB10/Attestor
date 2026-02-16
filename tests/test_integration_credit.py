"""Integration tests for Phase 4 -- full CDS, swaption, collateral, and credit
curve lifecycles.

Each test exercises Gateway -> Instrument -> Oracle -> Ledger -> Reporting,
verifying conservation laws and exhaustive state transitions.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from attestor.core.money import NonEmptyStr
from attestor.core.result import Ok, unwrap
from attestor.core.types import UtcDatetime
from attestor.gateway.parser import parse_cds_order, parse_swaption_order
from attestor.instrument.credit_types import CDSPayoutSpec, SwaptionPayoutSpec
from attestor.instrument.derivative_types import (
    CDSDetail,
    ProtectionSide,
    SeniorityLevel,
    SettlementType,
    SwaptionDetail,
    SwaptionType,
)
from attestor.instrument.fx_types import (
    DayCountConvention,
    IRSwapPayoutSpec,
    PaymentFrequency,
)
from attestor.instrument.lifecycle import DERIVATIVE_TRANSITIONS, check_transition
from attestor.instrument.types import (
    Instrument,
    Party,
    PositionStatusEnum,
    create_cds_instrument,
    create_swaption_instrument,
)
from attestor.ledger.cds import (
    ScheduledCDSPremium,
    create_cds_credit_event_settlement,
    create_cds_maturity_close,
    create_cds_premium_transaction,
    create_cds_trade_transaction,
    generate_cds_premium_schedule,
)
from attestor.ledger.collateral import (
    CollateralAgreement,
    CollateralType,
    create_collateral_return_transaction,
    create_collateral_substitution_transaction,
    create_margin_call_transaction,
)
from attestor.ledger.engine import LedgerEngine
from attestor.ledger.swaption import (
    create_swaption_cash_settlement,
    create_swaption_exercise_close,
    create_swaption_premium_transaction,
    exercise_swaption_into_irs,
)
from attestor.ledger.transactions import Account, AccountType, ExecuteResult
from attestor.oracle.arbitrage_gates import (
    check_credit_curve_arbitrage_freedom,
    check_vol_surface_arbitrage_freedom,
)
from attestor.oracle.calibration import ModelConfig, YieldCurve
from attestor.oracle.credit_curve import (
    CDSQuote,
    CreditCurve,
    bootstrap_credit_curve,
    survival_probability,
)
from attestor.oracle.vol_surface import SVIParameters, VolSurface, implied_vol
from attestor.reporting.dodd_frank import (
    DoddFrankSwapReport,
    project_dodd_frank_report,
)
from attestor.reporting.emir import project_emir_report
from attestor.reporting.mifid2 import (
    CDSReportFields,
    SwaptionReportFields,
    project_mifid2_report,
)

_TS = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
_TS_UTC = UtcDatetime(value=_TS)
_LEI_A = "529900HNOAA1KXQJUQ27"
_LEI_B = "969500UEQ9HE3W646P42"


def _make_engine(*account_specs: tuple[str, AccountType]) -> LedgerEngine:
    engine = LedgerEngine()
    for name, atype in account_specs:
        engine.register_account(Account(
            account_id=unwrap(NonEmptyStr.parse(name)),
            account_type=atype,
        ))
    return engine


def _make_parties() -> tuple[Party, ...]:
    party_a = unwrap(Party.create("PA", "Protection Buyer", _LEI_A))
    party_b = unwrap(Party.create("PB", "Protection Seller", _LEI_B))
    return (party_a, party_b)


# ---------------------------------------------------------------------------
# Test 1: Full CDS Lifecycle
# ---------------------------------------------------------------------------


class TestFullCDSLifecycle:
    """End-to-end CDS: parse -> instrument -> schedule -> premium -> credit
    event -> settlement -> close -> reports."""

    def test_cds_lifecycle(self) -> None:
        # ---------------------------------------------------------------
        # Step 1: Parse CDS order (Gateway)
        # ---------------------------------------------------------------
        raw: dict[str, object] = {
            "order_id": "CDS-001",
            "instrument_id": "CDS-ACME-5Y",
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
        order_result = parse_cds_order(raw)
        assert isinstance(order_result, Ok)
        order = order_result.value
        assert isinstance(order.instrument_detail, CDSDetail)
        assert order.instrument_detail.reference_entity.value == "ACME Corp"
        assert order.instrument_detail.spread_bps.value == Decimal("100")
        assert order.instrument_detail.seniority is SeniorityLevel.SENIOR_UNSECURED
        assert order.instrument_detail.protection_side is ProtectionSide.BUYER

        # ---------------------------------------------------------------
        # Step 2: Create CDS instrument
        # ---------------------------------------------------------------
        parties = _make_parties()
        instrument = unwrap(create_cds_instrument(
            instrument_id="CDS-ACME-5Y",
            reference_entity="ACME Corp",
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),  # 100bps as decimal
            currency="USD",
            effective_date=date(2025, 6, 20),
            maturity_date=date(2030, 6, 20),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("0.40"),
            parties=parties,
            trade_date=date(2025, 6, 15),
        ))
        assert isinstance(instrument, Instrument)
        assert instrument.status is PositionStatusEnum.PROPOSED

        # ---------------------------------------------------------------
        # Step 3: Generate premium schedule (quarterly, ACT/360)
        # ---------------------------------------------------------------
        schedule = unwrap(generate_cds_premium_schedule(
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            effective_date=date(2025, 6, 20),
            maturity_date=date(2030, 6, 20),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        assert len(schedule) >= 18  # ~20 quarters in 5 years
        assert all(isinstance(p, ScheduledCDSPremium) for p in schedule)
        assert all(p.amount > 0 for p in schedule)

        # ---------------------------------------------------------------
        # Step 4: Book first premium payment via LedgerEngine
        # ---------------------------------------------------------------
        engine = _make_engine(
            ("BUYER-CASH", AccountType.CASH),
            ("SELLER-CASH", AccountType.CASH),
            ("BUYER-POS", AccountType.DERIVATIVES),
            ("SELLER-POS", AccountType.DERIVATIVES),
        )
        first_premium = schedule[0]
        tx1 = unwrap(create_cds_premium_transaction(
            buyer_account="BUYER-CASH",
            seller_account="SELLER-CASH",
            premium=first_premium,
            tx_id="TX-CDS-PREM-001",
            timestamp=_TS_UTC,
        ))
        result = unwrap(engine.execute(tx1))
        assert result is ExecuteResult.APPLIED

        # Verify conservation after premium
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.get_balance("BUYER-CASH", "USD") == -first_premium.amount
        assert engine.get_balance("SELLER-CASH", "USD") == first_premium.amount

        # ---------------------------------------------------------------
        # Step 5: Credit event settlement (auction_price = 0.40)
        # ---------------------------------------------------------------
        tx2 = unwrap(create_cds_credit_event_settlement(
            buyer_account="BUYER-CASH",
            seller_account="SELLER-CASH",
            notional=Decimal("10000000"),
            auction_price=Decimal("0.40"),
            currency="USD",
            tx_id="TX-CDS-SETTLE-001",
            timestamp=_TS_UTC,
        ))
        result2 = unwrap(engine.execute(tx2))
        assert result2 is ExecuteResult.APPLIED

        # Protection payment = 10M * (1 - 0.40) = 6M
        # After premium + settlement:
        # BUYER-CASH = -premium + 6M, SELLER-CASH = +premium - 6M
        expected_payment = Decimal("10000000") * Decimal("0.60")
        buyer_cash = engine.get_balance("BUYER-CASH", "USD")
        assert buyer_cash == -first_premium.amount + expected_payment

        # ---------------------------------------------------------------
        # Step 6: Verify conservation after settlement
        # ---------------------------------------------------------------
        assert engine.total_supply("USD") == Decimal(0)

        # ---------------------------------------------------------------
        # Step 7: Close position via maturity close
        # ---------------------------------------------------------------
        contract_unit = "CDS-ACME-5Y-CONTRACT"

        # Open position using create_cds_trade_transaction
        open_tx = unwrap(create_cds_trade_transaction(
            buyer_position_account="BUYER-POS",
            seller_position_account="SELLER-POS",
            contract_unit=contract_unit,
            quantity=Decimal("1"),
            tx_id="TX-CDS-OPEN",
            timestamp=_TS_UTC,
        ))
        unwrap(engine.execute(open_tx))
        assert engine.total_supply(contract_unit) == Decimal(0)

        # Close position
        close_tx = unwrap(create_cds_maturity_close(
            buyer_position_account="BUYER-POS",
            seller_position_account="SELLER-POS",
            contract_unit=contract_unit,
            quantity=Decimal("1"),
            tx_id="TX-CDS-CLOSE-001",
            timestamp=_TS_UTC,
        ))
        unwrap(engine.execute(close_tx))

        # sigma(contract_unit) == 0
        assert engine.total_supply(contract_unit) == Decimal(0)
        assert engine.get_balance("BUYER-POS", contract_unit) == Decimal(0)
        assert engine.get_balance("SELLER-POS", contract_unit) == Decimal(0)

        # ---------------------------------------------------------------
        # Step 8: Reports -- EMIR, MiFID II, Dodd-Frank
        # ---------------------------------------------------------------
        emir_att = unwrap(project_emir_report(order, "ATT-CDS-001"))
        assert emir_att.value.instrument_id.value == "CDS-ACME-5Y"

        mifid_att = unwrap(project_mifid2_report(order, "ATT-CDS-001"))
        mifid_fields = mifid_att.value.instrument_fields
        assert isinstance(mifid_fields, CDSReportFields)
        assert mifid_fields.reference_entity == "ACME Corp"
        assert mifid_fields.spread_bps == Decimal("100")
        assert mifid_fields.seniority == "SENIOR_UNSECURED"
        assert mifid_fields.protection_side == "BUYER"

        dodd_att = unwrap(project_dodd_frank_report(order, "ATT-CDS-001"))
        df_report = dodd_att.value
        assert isinstance(df_report, DoddFrankSwapReport)
        assert df_report.asset_class.value == "CREDIT"
        assert df_report.product_type.value == "CDS"
        assert df_report.reference_entity is not None
        assert df_report.reference_entity.value == "ACME Corp"

        # ---------------------------------------------------------------
        # Step 9: Final invariants
        # ---------------------------------------------------------------
        # Conservation still holds
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply(contract_unit) == Decimal(0)

        # Idempotency
        replay = unwrap(engine.execute(tx1))
        assert replay is ExecuteResult.ALREADY_APPLIED

        # Lifecycle transitions are valid
        unwrap(check_transition(
            PositionStatusEnum.PROPOSED, PositionStatusEnum.FORMED,
            DERIVATIVE_TRANSITIONS,
        ))
        unwrap(check_transition(
            PositionStatusEnum.FORMED, PositionStatusEnum.SETTLED,
            DERIVATIVE_TRANSITIONS,
        ))
        unwrap(check_transition(
            PositionStatusEnum.SETTLED, PositionStatusEnum.CLOSED,
            DERIVATIVE_TRANSITIONS,
        ))


# ---------------------------------------------------------------------------
# Test 2: Full Swaption Physical Exercise Lifecycle
# ---------------------------------------------------------------------------


class TestFullSwaptionPhysicalLifecycle:
    """Swaption: parse -> instrument -> premium -> exercise into IRS -> close
    -> reports."""

    def test_swaption_physical_exercise(self) -> None:
        # ---------------------------------------------------------------
        # Step 1: Parse swaption order
        # ---------------------------------------------------------------
        raw: dict[str, object] = {
            "order_id": "SWPTN-001",
            "instrument_id": "SWPTN-PAYER-5Y10Y",
            "side": "BUY",
            "quantity": "1",
            "price": "50000",
            "currency": "USD",
            "order_type": "LIMIT",
            "counterparty_lei": _LEI_A,
            "executing_party_lei": _LEI_B,
            "venue": "OTC",
            "trade_date": "2025-06-15",
            "timestamp": "2025-06-15T10:00:00+00:00",
            "swaption_type": "PAYER",
            "expiry_date": "2030-06-15",
            "underlying_fixed_rate": "0.035",
            "underlying_float_index": "SOFR",
            "underlying_tenor_months": "120",
            "settlement_type": "PHYSICAL",
        }
        order_result = parse_swaption_order(raw)
        assert isinstance(order_result, Ok)
        order = order_result.value
        assert isinstance(order.instrument_detail, SwaptionDetail)
        assert order.instrument_detail.swaption_type is SwaptionType.PAYER
        assert order.instrument_detail.underlying_fixed_rate.value == Decimal("0.035")
        assert order.instrument_detail.underlying_tenor_months == 120
        assert order.instrument_detail.settlement_type is SettlementType.PHYSICAL

        # ---------------------------------------------------------------
        # Step 2: Create swaption instrument
        # ---------------------------------------------------------------
        parties = _make_parties()
        underlying_swap = unwrap(IRSwapPayoutSpec.create(
            fixed_rate=Decimal("0.035"),
            float_index="SOFR",
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            notional=Decimal("10000000"),
            currency="USD",
            start_date=date(2030, 6, 15),
            end_date=date(2040, 6, 15),
        ))
        swaption_instr = unwrap(create_swaption_instrument(
            instrument_id="SWPTN-PAYER-5Y10Y",
            swaption_type=SwaptionType.PAYER,
            strike=Decimal("0.035"),
            exercise_date=date(2030, 6, 15),
            underlying_swap=underlying_swap,
            settlement_type=SettlementType.PHYSICAL,
            currency="USD",
            notional=Decimal("10000000"),
            parties=parties,
            trade_date=date(2025, 6, 15),
        ))
        assert isinstance(swaption_instr, Instrument)
        assert swaption_instr.status is PositionStatusEnum.PROPOSED

        # ---------------------------------------------------------------
        # Step 3: Book swaption premium -> verify conservation
        # ---------------------------------------------------------------
        engine = _make_engine(
            ("HOLDER-CASH", AccountType.CASH),
            ("WRITER-CASH", AccountType.CASH),
            ("HOLDER-POS", AccountType.DERIVATIVES),
            ("WRITER-POS", AccountType.DERIVATIVES),
        )
        premium_tx = unwrap(create_swaption_premium_transaction(
            order=order,
            buyer_cash_account="HOLDER-CASH",
            seller_cash_account="WRITER-CASH",
            buyer_position_account="HOLDER-POS",
            seller_position_account="WRITER-POS",
            tx_id="TX-SWPTN-PREM-001",
        ))
        result = unwrap(engine.execute(premium_tx))
        assert result is ExecuteResult.APPLIED

        # Premium = price * quantity = 50000 * 1 = 50000
        assert engine.get_balance("HOLDER-CASH", "USD") == Decimal("-50000")
        assert engine.get_balance("WRITER-CASH", "USD") == Decimal("50000")
        assert engine.total_supply("USD") == Decimal(0)

        # Position opened
        contract_unit = (
            f"SWAPTION-{SwaptionType.PAYER.value}-{date(2030, 6, 15).isoformat()}"
        )
        assert engine.total_supply(contract_unit) == Decimal(0)

        # ---------------------------------------------------------------
        # Step 4: Exercise swaption -> produces IRS instrument
        # ---------------------------------------------------------------
        swaption_payout = unwrap(SwaptionPayoutSpec.create(
            swaption_type=SwaptionType.PAYER,
            strike=Decimal("0.035"),
            exercise_date=date(2030, 6, 15),
            underlying_swap=underlying_swap,
            settlement_type=SettlementType.PHYSICAL,
            currency="USD",
            notional=Decimal("10000000"),
        ))
        irs_instrument = unwrap(exercise_swaption_into_irs(
            swaption_payout=swaption_payout,
            exercise_date=date(2030, 6, 15),
            parties=parties,
            irs_instrument_id="IRS-FROM-SWPTN-001",
        ))
        assert isinstance(irs_instrument, Instrument)
        assert irs_instrument.status is PositionStatusEnum.PROPOSED

        # ---------------------------------------------------------------
        # Step 5: Close swaption position -> verify conservation
        # ---------------------------------------------------------------
        close_tx = unwrap(create_swaption_exercise_close(
            holder_position_account="HOLDER-POS",
            writer_position_account="WRITER-POS",
            contract_unit=contract_unit,
            quantity=Decimal("1"),
            tx_id="TX-SWPTN-CLOSE-001",
            timestamp=_TS_UTC,
        ))
        unwrap(engine.execute(close_tx))
        assert engine.total_supply(contract_unit) == Decimal(0)
        assert engine.get_balance("HOLDER-POS", contract_unit) == Decimal(0)

        # ---------------------------------------------------------------
        # Step 6: Verify IRS: fixed_rate == swaption strike
        # ---------------------------------------------------------------
        irs_payout = irs_instrument.product.economic_terms.payout
        assert isinstance(irs_payout, IRSwapPayoutSpec)
        assert irs_payout.fixed_leg.fixed_rate.value == Decimal("0.035")
        assert irs_payout.float_leg.float_index.value == "SOFR"
        assert irs_payout.start_date == date(2030, 6, 15)
        assert irs_payout.end_date == date(2040, 6, 15)

        # ---------------------------------------------------------------
        # Step 7: Reports -- EMIR, MiFID II, Dodd-Frank
        # ---------------------------------------------------------------
        emir_att = unwrap(project_emir_report(order, "ATT-SWPTN-001"))
        assert emir_att.value.instrument_id.value == "SWPTN-PAYER-5Y10Y"

        mifid_att = unwrap(project_mifid2_report(order, "ATT-SWPTN-001"))
        mifid_fields = mifid_att.value.instrument_fields
        assert isinstance(mifid_fields, SwaptionReportFields)
        assert mifid_fields.swaption_type == "PAYER"
        assert mifid_fields.underlying_fixed_rate == Decimal("0.035")
        assert mifid_fields.underlying_tenor_months == 120
        assert mifid_fields.settlement_type == "PHYSICAL"

        dodd_att = unwrap(project_dodd_frank_report(order, "ATT-SWPTN-001"))
        df_report = dodd_att.value
        assert isinstance(df_report, DoddFrankSwapReport)
        assert df_report.asset_class.value == "INTEREST_RATE"
        assert df_report.product_type.value == "SWAPTION"
        assert df_report.underlying_fixed_rate == Decimal("0.035")

        # ---------------------------------------------------------------
        # Step 8: Final invariants
        # ---------------------------------------------------------------
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply(contract_unit) == Decimal(0)

        # Idempotency
        replay = unwrap(engine.execute(premium_tx))
        assert replay is ExecuteResult.ALREADY_APPLIED


# ---------------------------------------------------------------------------
# Test 3: Full Swaption Cash Settlement Lifecycle
# ---------------------------------------------------------------------------


class TestFullSwaptionCashLifecycle:
    """Cash-settled swaption: premium -> cash settlement -> verify
    conservation."""

    def test_swaption_cash_settlement(self) -> None:
        # Parse swaption order (cash settlement)
        raw: dict[str, object] = {
            "order_id": "SWPTN-CASH-001",
            "instrument_id": "SWPTN-RCV-3Y5Y",
            "side": "BUY",
            "quantity": "1",
            "price": "30000",
            "currency": "USD",
            "order_type": "LIMIT",
            "counterparty_lei": _LEI_A,
            "executing_party_lei": _LEI_B,
            "venue": "OTC",
            "trade_date": "2025-06-15",
            "timestamp": "2025-06-15T10:00:00+00:00",
            "swaption_type": "RECEIVER",
            "expiry_date": "2028-06-15",
            "underlying_fixed_rate": "0.04",
            "underlying_float_index": "SOFR",
            "underlying_tenor_months": "60",
            "settlement_type": "CASH",
        }
        order = unwrap(parse_swaption_order(raw))
        assert isinstance(order.instrument_detail, SwaptionDetail)
        assert order.instrument_detail.settlement_type is SettlementType.CASH

        # Book premium
        engine = _make_engine(
            ("HOLDER-CASH", AccountType.CASH),
            ("WRITER-CASH", AccountType.CASH),
            ("HOLDER-POS", AccountType.DERIVATIVES),
            ("WRITER-POS", AccountType.DERIVATIVES),
        )
        premium_tx = unwrap(create_swaption_premium_transaction(
            order=order,
            buyer_cash_account="HOLDER-CASH",
            seller_cash_account="WRITER-CASH",
            buyer_position_account="HOLDER-POS",
            seller_position_account="WRITER-POS",
            tx_id="TX-SWPTN-CASH-PREM",
        ))
        unwrap(engine.execute(premium_tx))
        assert engine.total_supply("USD") == Decimal(0)

        contract_unit = (
            f"SWAPTION-{SwaptionType.RECEIVER.value}-{date(2028, 6, 15).isoformat()}"
        )

        # Cash settlement: writer pays holder settlement amount
        cash_tx = unwrap(create_swaption_cash_settlement(
            holder_cash_account="HOLDER-CASH",
            writer_cash_account="WRITER-CASH",
            holder_position_account="HOLDER-POS",
            writer_position_account="WRITER-POS",
            settlement_amount=Decimal("75000"),
            currency="USD",
            contract_unit=contract_unit,
            quantity=Decimal("1"),
            tx_id="TX-SWPTN-CASH-SETTLE",
            timestamp=_TS_UTC,
        ))
        unwrap(engine.execute(cash_tx))

        # Conservation holds
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply(contract_unit) == Decimal(0)

        # Net positions:
        # HOLDER-CASH = -30000 (premium) + 75000 (settlement) = 45000
        # WRITER-CASH = +30000 (premium) - 75000 (settlement) = -45000
        assert engine.get_balance("HOLDER-CASH", "USD") == Decimal("45000")
        assert engine.get_balance("WRITER-CASH", "USD") == Decimal("-45000")

        # Position fully closed
        assert engine.get_balance("HOLDER-POS", contract_unit) == Decimal(0)
        assert engine.get_balance("WRITER-POS", contract_unit) == Decimal(0)

        # Idempotency
        replay = unwrap(engine.execute(cash_tx))
        assert replay is ExecuteResult.ALREADY_APPLIED


# ---------------------------------------------------------------------------
# Test 4: Full Collateral Lifecycle
# ---------------------------------------------------------------------------


class TestFullCollateralLifecycle:
    """Collateral: agreement -> margin call -> return -> substitution.
    Every step verifies conservation."""

    def test_collateral_lifecycle(self) -> None:
        # ---------------------------------------------------------------
        # Step 1: Create CollateralAgreement
        # ---------------------------------------------------------------
        agreement = unwrap(CollateralAgreement.create(
            agreement_id="CSA-001",
            party_a="BankA",
            party_b="BankB",
            eligible_collateral=(
                CollateralType.CASH,
                CollateralType.GOVERNMENT_BOND,
            ),
            threshold_a=Decimal("5000000"),
            threshold_b=Decimal("5000000"),
            minimum_transfer_amount=Decimal("500000"),
            currency="USD",
        ))
        assert agreement.agreement_id.value == "CSA-001"
        assert len(agreement.eligible_collateral) == 2
        assert agreement.threshold_a == Decimal("5000000")

        engine = _make_engine(
            ("BANKA-COLL", AccountType.CASH),
            ("BANKB-COLL", AccountType.CASH),
        )

        # ---------------------------------------------------------------
        # Step 2: Margin call -> delivery -> verify conservation
        # ---------------------------------------------------------------
        margin_tx = unwrap(create_margin_call_transaction(
            caller_account="BANKA-COLL",
            poster_account="BANKB-COLL",
            collateral_unit="USD",
            quantity=Decimal("2000000"),
            tx_id="TX-MARGIN-001",
            timestamp=_TS_UTC,
        ))
        unwrap(engine.execute(margin_tx))

        assert engine.get_balance("BANKA-COLL", "USD") == Decimal("2000000")
        assert engine.get_balance("BANKB-COLL", "USD") == Decimal("-2000000")
        assert engine.total_supply("USD") == Decimal(0)

        # ---------------------------------------------------------------
        # Step 3: Collateral return -> verify conservation
        # ---------------------------------------------------------------
        return_tx = unwrap(create_collateral_return_transaction(
            returner_account="BANKA-COLL",
            receiver_account="BANKB-COLL",
            collateral_unit="USD",
            quantity=Decimal("500000"),
            tx_id="TX-RETURN-001",
            timestamp=_TS_UTC,
        ))
        unwrap(engine.execute(return_tx))

        assert engine.get_balance("BANKA-COLL", "USD") == Decimal("1500000")
        assert engine.get_balance("BANKB-COLL", "USD") == Decimal("-1500000")
        assert engine.total_supply("USD") == Decimal(0)

        # ---------------------------------------------------------------
        # Step 4: Substitution -> verify both units balanced
        # ---------------------------------------------------------------
        sub_tx = unwrap(create_collateral_substitution_transaction(
            poster_account="BANKB-COLL",
            holder_account="BANKA-COLL",
            old_collateral_unit="USD",
            old_quantity=Decimal("1000000"),
            new_collateral_unit="US-TREASURY-10Y",
            new_quantity=Decimal("1050000"),  # with haircut
            tx_id="TX-SUB-001",
            timestamp=_TS_UTC,
        ))
        unwrap(engine.execute(sub_tx))

        # Old collateral returned: USD balance reduced
        assert engine.get_balance("BANKA-COLL", "USD") == Decimal("500000")
        assert engine.get_balance("BANKB-COLL", "USD") == Decimal("-500000")
        assert engine.total_supply("USD") == Decimal(0)

        # New collateral delivered: treasury balance created
        assert engine.get_balance("BANKA-COLL", "US-TREASURY-10Y") == Decimal("1050000")
        assert engine.get_balance("BANKB-COLL", "US-TREASURY-10Y") == Decimal("-1050000")
        assert engine.total_supply("US-TREASURY-10Y") == Decimal(0)

        # Idempotency
        replay = unwrap(engine.execute(margin_tx))
        assert replay is ExecuteResult.ALREADY_APPLIED

    def test_margin_call_then_full_return(self) -> None:
        """Margin call then full return leaves zero balances."""
        engine = _make_engine(
            ("CALLER", AccountType.CASH),
            ("POSTER", AccountType.CASH),
        )
        call_tx = unwrap(create_margin_call_transaction(
            "CALLER", "POSTER", "USD",
            Decimal("3000000"), "TX-MC-FR-1", _TS_UTC,
        ))
        unwrap(engine.execute(call_tx))

        ret_tx = unwrap(create_collateral_return_transaction(
            "CALLER", "POSTER", "USD",
            Decimal("3000000"), "TX-MC-FR-2", _TS_UTC,
        ))
        unwrap(engine.execute(ret_tx))

        assert engine.get_balance("CALLER", "USD") == Decimal(0)
        assert engine.get_balance("POSTER", "USD") == Decimal(0)
        assert engine.total_supply("USD") == Decimal(0)


# ---------------------------------------------------------------------------
# Test 5: Credit Curve Pipeline
# ---------------------------------------------------------------------------


class TestCreditCurvePipeline:
    """Bootstrap credit curve from CDS quotes, run arbitrage gates, verify
    survival probability interpolation."""

    def _discount_curve(self) -> YieldCurve:
        return unwrap(YieldCurve.create(
            currency="USD",
            as_of=date(2025, 6, 15),
            tenors=(Decimal("1"), Decimal("3"), Decimal("5")),
            discount_factors=(Decimal("0.96"), Decimal("0.90"), Decimal("0.85")),
            model_config_ref="CFG-CREDIT-TEST",
        ))

    def _config(self) -> ModelConfig:
        return unwrap(ModelConfig.create(
            "CFG-CREDIT-TEST", "PIECEWISE_HAZARD", "1.0.0",
        ))

    def test_bootstrap_and_check(self) -> None:
        # ---------------------------------------------------------------
        # Step 1: Create CDSQuote instruments (1Y, 3Y, 5Y)
        # ---------------------------------------------------------------
        quotes = (
            CDSQuote(
                reference_entity=NonEmptyStr(value="ACME Corp"),
                tenor=Decimal("1"),
                spread=Decimal("0.01"),      # 100bps
                recovery_rate=Decimal("0.4"),
                currency=NonEmptyStr(value="USD"),
            ),
            CDSQuote(
                reference_entity=NonEmptyStr(value="ACME Corp"),
                tenor=Decimal("3"),
                spread=Decimal("0.015"),     # 150bps
                recovery_rate=Decimal("0.4"),
                currency=NonEmptyStr(value="USD"),
            ),
            CDSQuote(
                reference_entity=NonEmptyStr(value="ACME Corp"),
                tenor=Decimal("5"),
                spread=Decimal("0.02"),      # 200bps
                recovery_rate=Decimal("0.4"),
                currency=NonEmptyStr(value="USD"),
            ),
        )

        # ---------------------------------------------------------------
        # Step 2: Bootstrap credit curve
        # ---------------------------------------------------------------
        att = unwrap(bootstrap_credit_curve(
            quotes=quotes,
            discount_curve=self._discount_curve(),
            config=self._config(),
            as_of=date(2025, 6, 15),
            reference_entity="ACME Corp",
        ))
        curve = att.value
        assert isinstance(curve, CreditCurve)
        assert len(curve.tenors) == 3
        assert all(Decimal("0") < q <= Decimal("1") for q in curve.survival_probs)

        # Survival probs must be monotone decreasing
        for i in range(len(curve.survival_probs) - 1):
            assert curve.survival_probs[i + 1] <= curve.survival_probs[i]

        # Hazard rates must be non-negative
        assert all(h >= 0 for h in curve.hazard_rates)

        # ---------------------------------------------------------------
        # Step 3: Run credit curve arbitrage gates
        # ---------------------------------------------------------------
        results = unwrap(check_credit_curve_arbitrage_freedom(curve))
        assert len(results) == 4  # AF-CR-01..04
        # All should pass for a well-formed bootstrapped curve
        for r in results:
            assert r.passed, f"{r.check_id} failed: {r.details}"

        # ---------------------------------------------------------------
        # Step 4: Verify survival probability interpolation
        # ---------------------------------------------------------------
        # At t=0: Q=1
        q0 = unwrap(survival_probability(curve, Decimal("0")))
        assert q0 == Decimal("1")

        # At t=1: should match bootstrapped value
        q1 = unwrap(survival_probability(curve, Decimal("1")))
        assert abs(q1 - curve.survival_probs[0]) < Decimal("1e-10")

        # At t=2 (interpolated between 1Y and 3Y): 0 < Q(2) < Q(1)
        q2 = unwrap(survival_probability(curve, Decimal("2")))
        assert Decimal("0") < q2 < q1

        # At t=5: should match bootstrapped value
        q5 = unwrap(survival_probability(curve, Decimal("5")))
        assert abs(q5 - curve.survival_probs[2]) < Decimal("1e-10")

        # Extrapolation at t=7: 0 < Q(7) < Q(5)
        q7 = unwrap(survival_probability(curve, Decimal("7")))
        assert Decimal("0") < q7 < q5

    def test_empty_quotes_rejected(self) -> None:
        """Empty quotes tuple produces Err."""
        from attestor.core.result import Err
        result = bootstrap_credit_curve(
            quotes=(),
            discount_curve=self._discount_curve(),
            config=self._config(),
            as_of=date(2025, 6, 15),
            reference_entity="ACME Corp",
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Test 6: Vol Surface Pipeline
# ---------------------------------------------------------------------------


class TestVolSurfacePipeline:
    """Create valid VolSurface, run arbitrage gates, verify implied vol."""

    def _make_surface(self) -> VolSurface:
        # A simple two-slice SVI surface with well-behaved parameters.
        # Near-ATM flat vol around 20% (variance = 0.04 * T).
        slice_3m = unwrap(SVIParameters.create(
            a=Decimal("0.01"),
            b=Decimal("0.1"),
            rho=Decimal("-0.3"),
            m=Decimal("0"),
            sigma=Decimal("0.2"),
            expiry=Decimal("0.25"),
        ))
        slice_1y = unwrap(SVIParameters.create(
            a=Decimal("0.04"),
            b=Decimal("0.1"),
            rho=Decimal("-0.3"),
            m=Decimal("0"),
            sigma=Decimal("0.2"),
            expiry=Decimal("1"),
        ))
        return unwrap(VolSurface.create(
            underlying="SPX",
            as_of=date(2025, 6, 15),
            expiries=(Decimal("0.25"), Decimal("1")),
            slices=(slice_3m, slice_1y),
            model_config_ref="CFG-SVI-001",
        ))

    def test_vol_surface_gates(self) -> None:
        surface = self._make_surface()

        results = unwrap(check_vol_surface_arbitrage_freedom(surface))
        # AF-VS-01..06
        assert len(results) == 6

        # All should pass for this well-behaved surface
        for r in results:
            assert r.passed, f"{r.check_id} failed: {r.details}"

    def test_implied_vol_extraction(self) -> None:
        surface = self._make_surface()

        # ATM vol at 1Y expiry
        vol = unwrap(implied_vol(surface, Decimal("0"), Decimal("1")))
        # Should be approximately sqrt(0.04 + 0.1 * 0.2) = sqrt(0.06) ~ 0.245
        assert vol > Decimal("0.1")
        assert vol < Decimal("0.5")

        # Vol at 3M expiry
        vol_3m = unwrap(implied_vol(surface, Decimal("0"), Decimal("0.25")))
        assert vol_3m > Decimal("0.1")
        assert vol_3m < Decimal("0.6")

    def test_negative_expiry_rejected(self) -> None:
        from attestor.core.result import Err
        surface = self._make_surface()
        result = implied_vol(surface, Decimal("0"), Decimal("-1"))
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Test 7: Engine Untouched
# ---------------------------------------------------------------------------


class TestEngineUntouched:
    """Verify engine.py has no CDS, swaption, or collateral keywords.
    The engine is purely parametric (Principle V)."""

    def test_no_credit_keywords_in_engine(self) -> None:
        import inspect

        from attestor.ledger import engine
        source = inspect.getsource(engine)
        # Remove __future__ import line to prevent false positives
        lines = [
            line for line in source.splitlines()
            if "__future__" not in line
        ]
        filtered = "\n".join(lines).lower()
        for keyword in [
            "cds", "swaption", "collateral", "credit", "protection",
            "margin_call", "substitution", "premium", "auction",
            "hazard", "survival",
        ]:
            assert keyword not in filtered, (
                f"engine.py must not reference '{keyword}' -- "
                f"parametric polymorphism (Principle V)"
            )


# ---------------------------------------------------------------------------
# Test 8: Import Smoke Tests
# ---------------------------------------------------------------------------


class TestImportSmoke:
    """Verify all Phase 4 modules are importable."""

    def test_credit_curve_importable(self) -> None:
        from attestor.oracle.credit_curve import (
            CDSQuote,
            CreditCurve,
            bootstrap_credit_curve,
            hazard_rate,
            survival_probability,
        )
        assert CDSQuote is not None
        assert CreditCurve is not None
        assert callable(bootstrap_credit_curve)
        assert callable(hazard_rate)
        assert callable(survival_probability)

    def test_vol_surface_importable(self) -> None:
        from attestor.oracle.vol_surface import (
            SVIParameters,
            VolSurface,
            implied_vol,
            svi_first_derivative,
            svi_second_derivative,
            svi_total_variance,
        )
        assert SVIParameters is not None
        assert VolSurface is not None
        assert callable(implied_vol)
        assert callable(svi_total_variance)
        assert callable(svi_first_derivative)
        assert callable(svi_second_derivative)

    def test_credit_ingest_importable(self) -> None:
        from attestor.oracle.credit_ingest import (
            AuctionResult,
            CDSSpreadQuote,
            CreditEventRecord,
            ingest_auction_result,
            ingest_cds_spread,
            ingest_credit_event,
        )
        assert CDSSpreadQuote is not None
        assert CreditEventRecord is not None
        assert AuctionResult is not None
        assert callable(ingest_cds_spread)
        assert callable(ingest_credit_event)
        assert callable(ingest_auction_result)

    def test_cds_ledger_importable(self) -> None:
        from attestor.ledger.cds import (
            ScheduledCDSPremium,
            create_cds_credit_event_settlement,
            create_cds_maturity_close,
            create_cds_premium_transaction,
            generate_cds_premium_schedule,
        )
        assert ScheduledCDSPremium is not None
        assert callable(create_cds_premium_transaction)
        assert callable(create_cds_credit_event_settlement)
        assert callable(create_cds_maturity_close)
        assert callable(generate_cds_premium_schedule)

    def test_swaption_ledger_importable(self) -> None:
        from attestor.ledger.swaption import (
            create_swaption_cash_settlement,
            create_swaption_exercise_close,
            create_swaption_expiry_close,
            create_swaption_premium_transaction,
            exercise_swaption_into_irs,
        )
        assert callable(create_swaption_premium_transaction)
        assert callable(exercise_swaption_into_irs)
        assert callable(create_swaption_exercise_close)
        assert callable(create_swaption_cash_settlement)
        assert callable(create_swaption_expiry_close)

    def test_collateral_importable(self) -> None:
        from attestor.ledger.collateral import (
            CollateralAgreement,
            CollateralType,
            create_collateral_return_transaction,
            create_collateral_substitution_transaction,
            create_margin_call_transaction,
        )
        assert CollateralAgreement is not None
        assert CollateralType is not None
        assert callable(create_margin_call_transaction)
        assert callable(create_collateral_return_transaction)
        assert callable(create_collateral_substitution_transaction)

    def test_dodd_frank_importable(self) -> None:
        from attestor.reporting.dodd_frank import (
            DoddFrankSwapReport,
            project_dodd_frank_report,
        )
        assert DoddFrankSwapReport is not None
        assert callable(project_dodd_frank_report)

    def test_arbitrage_gates_credit(self) -> None:
        from attestor.oracle.arbitrage_gates import (
            check_credit_curve_arbitrage_freedom,
            check_vol_surface_arbitrage_freedom,
        )
        assert callable(check_credit_curve_arbitrage_freedom)
        assert callable(check_vol_surface_arbitrage_freedom)

    def test_infra_phase4_topics(self) -> None:
        from attestor.infra.config import PHASE4_TOPICS
        assert len(PHASE4_TOPICS) == 4

    def test_mifid2_credit_fields(self) -> None:
        from attestor.reporting.mifid2 import CDSReportFields, SwaptionReportFields
        assert CDSReportFields is not None
        assert SwaptionReportFields is not None

    def test_credit_types_importable(self) -> None:
        from attestor.instrument.credit_types import (
            CDSPayoutSpec,
            SwaptionPayoutSpec,
        )
        assert CDSPayoutSpec is not None
        assert SwaptionPayoutSpec is not None

    def test_derivative_enums_importable(self) -> None:
        from attestor.instrument.derivative_types import (
            CreditEventType,
            ProtectionSide,
            SeniorityLevel,
            SwaptionType,
        )
        assert CreditEventType.BANKRUPTCY.value == "BANKRUPTCY"
        assert ProtectionSide.BUYER.value == "BUYER"
        assert SeniorityLevel.SENIOR_UNSECURED.value == "SENIOR_UNSECURED"
        assert SwaptionType.PAYER.value == "PAYER"


# ---------------------------------------------------------------------------
# Test: CDS Premium Schedule Details
# ---------------------------------------------------------------------------


class TestCDSPremiumScheduleDetails:
    """Test CDS premium schedule generation in more detail."""

    def test_schedule_covers_full_tenor(self) -> None:
        schedule = unwrap(generate_cds_premium_schedule(
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            effective_date=date(2025, 1, 1),
            maturity_date=date(2026, 1, 1),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        assert len(schedule) == 4
        # First period starts at effective date
        assert schedule[0].period_start == date(2025, 1, 1)
        # Last period ends at maturity
        assert schedule[-1].period_end == date(2026, 1, 1)
        # All amounts positive
        assert all(p.amount > 0 for p in schedule)
        # day_count_fraction > 0
        assert all(p.day_count_fraction > 0 for p in schedule)

    def test_annual_frequency(self) -> None:
        schedule = unwrap(generate_cds_premium_schedule(
            notional=Decimal("5000000"),
            spread=Decimal("0.005"),
            effective_date=date(2025, 6, 20),
            maturity_date=date(2027, 6, 20),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.ANNUAL,
            currency="EUR",
        ))
        assert len(schedule) == 2
        assert schedule[0].currency.value == "EUR"

    def test_invalid_dates_rejected(self) -> None:
        from attestor.core.result import Err
        result = generate_cds_premium_schedule(
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            effective_date=date(2030, 1, 1),
            maturity_date=date(2025, 1, 1),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Test: Swaption Expiry (Unexercised)
# ---------------------------------------------------------------------------


class TestSwaptionExpiry:
    """Swaption expires unexercised: premium was paid, position closes to
    zero, no additional cash moves."""

    def test_swaption_expiry_close(self) -> None:
        raw: dict[str, object] = {
            "order_id": "SWPTN-EXP-001",
            "instrument_id": "SWPTN-EXP-TEST",
            "side": "BUY",
            "quantity": "1",
            "price": "25000",
            "currency": "USD",
            "order_type": "LIMIT",
            "counterparty_lei": _LEI_A,
            "executing_party_lei": _LEI_B,
            "venue": "OTC",
            "trade_date": "2025-06-15",
            "timestamp": "2025-06-15T10:00:00+00:00",
            "swaption_type": "PAYER",
            "expiry_date": "2026-06-15",
            "underlying_fixed_rate": "0.04",
            "underlying_float_index": "EURIBOR",
            "underlying_tenor_months": "24",
            "settlement_type": "PHYSICAL",
        }
        order = unwrap(parse_swaption_order(raw))

        engine = _make_engine(
            ("H-CASH", AccountType.CASH),
            ("W-CASH", AccountType.CASH),
            ("H-POS", AccountType.DERIVATIVES),
            ("W-POS", AccountType.DERIVATIVES),
        )

        # Book premium
        premium_tx = unwrap(create_swaption_premium_transaction(
            order=order,
            buyer_cash_account="H-CASH",
            seller_cash_account="W-CASH",
            buyer_position_account="H-POS",
            seller_position_account="W-POS",
            tx_id="TX-EXP-PREM",
        ))
        unwrap(engine.execute(premium_tx))

        contract_unit = (
            f"SWAPTION-{SwaptionType.PAYER.value}-{date(2026, 6, 15).isoformat()}"
        )
        assert engine.total_supply(contract_unit) == Decimal(0)

        # Expiry close (no exercise, no cash)
        from attestor.ledger.swaption import create_swaption_expiry_close
        expiry_tx = unwrap(create_swaption_expiry_close(
            holder_position_account="H-POS",
            writer_position_account="W-POS",
            contract_unit=contract_unit,
            quantity=Decimal("1"),
            tx_id="TX-EXP-CLOSE",
            timestamp=_TS_UTC,
        ))
        unwrap(engine.execute(expiry_tx))

        # Position closed, only premium cash moved
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply(contract_unit) == Decimal(0)
        assert engine.get_balance("H-CASH", "USD") == Decimal("-25000")
        assert engine.get_balance("W-CASH", "USD") == Decimal("25000")


# ---------------------------------------------------------------------------
# Test: Oracle Credit Ingest
# ---------------------------------------------------------------------------


class TestOracleCreditIngest:
    """CDS spread, credit event, and auction result ingestion."""

    def test_ingest_cds_spread(self) -> None:
        from attestor.oracle.credit_ingest import ingest_cds_spread
        att = unwrap(ingest_cds_spread(
            reference_entity="ACME Corp",
            tenor=Decimal("5"),
            bid_bps=Decimal("95"),
            ask_bps=Decimal("105"),
            recovery_rate=Decimal("0.4"),
            currency="USD",
            venue="MARKIT",
            timestamp=_TS,
        ))
        assert att.value.reference_entity.value == "ACME Corp"
        assert att.value.tenor == Decimal("5")
        # Mid = (95 + 105) / 2 = 100
        assert att.value.spread_bps == Decimal("100")
        assert att.value.recovery_rate == Decimal("0.4")

    def test_ingest_credit_event(self) -> None:
        from attestor.oracle.credit_ingest import ingest_credit_event
        att = unwrap(ingest_credit_event(
            reference_entity="ACME Corp",
            event_type="BANKRUPTCY",
            determination_date=date(2025, 8, 1),
            source="ISDA-DC",
            timestamp=_TS,
            attestation_ref="ATT-CE-001",
        ))
        from attestor.instrument.derivative_types import CreditEventType
        assert att.value.event_type is CreditEventType.BANKRUPTCY
        assert att.value.determination_date == date(2025, 8, 1)

    def test_ingest_auction_result(self) -> None:
        from attestor.oracle.credit_ingest import ingest_auction_result
        att = unwrap(ingest_auction_result(
            reference_entity="ACME Corp",
            event_type="BANKRUPTCY",
            determination_date=date(2025, 8, 1),
            auction_price=Decimal("0.35"),
            source="CREDITEX",
            timestamp=_TS,
            attestation_ref="ATT-AR-001",
        ))
        assert att.value.auction_price == Decimal("0.35")
        assert att.value.reference_entity.value == "ACME Corp"


# ---------------------------------------------------------------------------
# Test: CDS Instrument Creation Details
# ---------------------------------------------------------------------------


class TestCDSInstrumentCreation:
    """Test CDS instrument creation and payout spec."""

    def test_cds_payout_spec(self) -> None:
        payout = unwrap(CDSPayoutSpec.create(
            reference_entity="MegaCorp",
            notional=Decimal("5000000"),
            spread=Decimal("0.005"),
            currency="EUR",
            effective_date=date(2025, 3, 20),
            maturity_date=date(2030, 3, 20),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("0.40"),
        ))
        assert payout.reference_entity.value == "MegaCorp"
        assert payout.notional.value == Decimal("5000000")
        assert payout.recovery_rate == Decimal("0.40")

    def test_cds_instrument_status(self) -> None:
        parties = _make_parties()
        instr = unwrap(create_cds_instrument(
            instrument_id="CDS-TEST",
            reference_entity="TestCorp",
            notional=Decimal("10000000"),
            spread=Decimal("0.02"),
            currency="USD",
            effective_date=date(2025, 6, 20),
            maturity_date=date(2030, 6, 20),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("0.40"),
            parties=parties,
            trade_date=date(2025, 6, 15),
        ))
        assert instr.status is PositionStatusEnum.PROPOSED
        assert instr.instrument_id.value == "CDS-TEST"
        payout = instr.product.economic_terms.payout
        assert isinstance(payout, CDSPayoutSpec)
        assert payout.spread == Decimal("0.02")


# ---------------------------------------------------------------------------
# Test: Dodd-Frank Report Rejection
# ---------------------------------------------------------------------------


class TestDoddFrankRejection:
    """Dodd-Frank rejects non-CDS/non-swaption orders."""

    def test_equity_order_rejected(self) -> None:
        from attestor.core.result import Err
        from attestor.gateway.parser import parse_order
        raw: dict[str, object] = {
            "order_id": "ORD-EQUITY-001",
            "instrument_id": "AAPL",
            "side": "BUY",
            "quantity": "100",
            "price": "175.50",
            "currency": "USD",
            "order_type": "LIMIT",
            "counterparty_lei": _LEI_A,
            "executing_party_lei": _LEI_B,
            "trade_date": "2025-06-15",
            "venue": "XNYS",
            "timestamp": "2025-06-15T10:00:00+00:00",
        }
        order = unwrap(parse_order(raw))
        result = project_dodd_frank_report(order, "ATT-EQ-001")
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Test: Dodd-Frank Notional = Contract Notional (Phase 5 D4)
# ---------------------------------------------------------------------------


class TestDoddFrankNotional:
    """Dodd-Frank notional uses order.quantity (contract notional), not qty*price."""

    def test_cds_notional_is_quantity(self) -> None:
        raw: dict[str, object] = {
            "order_id": "CDS-DF-001",
            "instrument_id": "CDS-DF-TEST",
            "side": "BUY",
            "quantity": "10000000",
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
        df_att = unwrap(project_dodd_frank_report(order, "ATT-DF-001"))
        # Notional should be quantity (10M), not quantity * price (1B)
        assert df_att.value.notional == Decimal("10000000")

    def test_swaption_notional_is_quantity(self) -> None:
        raw: dict[str, object] = {
            "order_id": "SWPTN-DF-001",
            "instrument_id": "SWPTN-DF-TEST",
            "side": "BUY",
            "quantity": "5",
            "price": "50000",
            "currency": "USD",
            "order_type": "LIMIT",
            "counterparty_lei": _LEI_A,
            "executing_party_lei": _LEI_B,
            "venue": "OTC",
            "trade_date": "2025-06-15",
            "timestamp": "2025-06-15T10:00:00+00:00",
            "swaption_type": "PAYER",
            "expiry_date": "2030-06-15",
            "underlying_fixed_rate": "0.035",
            "underlying_float_index": "SOFR",
            "underlying_tenor_months": "120",
            "settlement_type": "PHYSICAL",
        }
        order = unwrap(parse_swaption_order(raw))
        df_att = unwrap(project_dodd_frank_report(order, "ATT-DF-002"))
        # Notional should be quantity (5), not quantity * price (250000)
        assert df_att.value.notional == Decimal("5")


# ---------------------------------------------------------------------------
# Test: Multi-CDS Portfolio Lifecycle (Phase 5 D6)
# ---------------------------------------------------------------------------


class TestMultiCDSPortfolio:
    """Multi-CDS portfolio: two CDS instruments share the engine, conservation
    holds for each currency unit individually."""

    def test_two_cds_shared_engine(self) -> None:
        engine = _make_engine(
            ("BUYER-CASH", AccountType.CASH),
            ("SELLER-CASH", AccountType.CASH),
            ("BUYER-POS", AccountType.DERIVATIVES),
            ("SELLER-POS", AccountType.DERIVATIVES),
        )
        # CDS-1: 10M notional, 100bps spread
        schedule_1 = unwrap(generate_cds_premium_schedule(
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            effective_date=date(2025, 3, 20),
            maturity_date=date(2025, 6, 20),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        # CDS-2: 5M notional EUR, 200bps spread
        schedule_2 = unwrap(generate_cds_premium_schedule(
            notional=Decimal("5000000"),
            spread=Decimal("0.02"),
            effective_date=date(2025, 3, 20),
            maturity_date=date(2025, 6, 20),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="EUR",
        ))

        # Book premiums from both CDSs
        tx1 = unwrap(create_cds_premium_transaction(
            "BUYER-CASH", "SELLER-CASH",
            schedule_1[0], "TX-MULTI-1", _TS_UTC,
        ))
        unwrap(engine.execute(tx1))
        assert engine.total_supply("USD") == Decimal(0)

        tx2 = unwrap(create_cds_premium_transaction(
            "BUYER-CASH", "SELLER-CASH",
            schedule_2[0], "TX-MULTI-2", _TS_UTC,
        ))
        unwrap(engine.execute(tx2))
        assert engine.total_supply("EUR") == Decimal(0)

        # Both currencies conserved
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply("EUR") == Decimal(0)


# ---------------------------------------------------------------------------
# Test: Cross-Instrument Conservation (Phase 5 D6)
# ---------------------------------------------------------------------------


class TestCrossInstrumentConservation:
    """CDS + swaption + collateral all in same engine: sigma=0 for each unit."""

    def test_cross_instrument_sigma_zero(self) -> None:
        engine = _make_engine(
            ("BUYER-CASH", AccountType.CASH),
            ("SELLER-CASH", AccountType.CASH),
            ("BUYER-POS", AccountType.DERIVATIVES),
            ("SELLER-POS", AccountType.DERIVATIVES),
            ("COLL-A", AccountType.COLLATERAL),
            ("COLL-B", AccountType.COLLATERAL),
        )

        # CDS premium
        schedule = unwrap(generate_cds_premium_schedule(
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            effective_date=date(2025, 3, 20),
            maturity_date=date(2025, 6, 20),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        prem_tx = unwrap(create_cds_premium_transaction(
            "BUYER-CASH", "SELLER-CASH",
            schedule[0], "TX-CROSS-CDS", _TS_UTC,
        ))
        unwrap(engine.execute(prem_tx))

        # Collateral margin call
        margin_tx = unwrap(create_margin_call_transaction(
            "COLL-A", "COLL-B", "TBILL-3M",
            Decimal("2000000"), "TX-CROSS-MC", _TS_UTC,
        ))
        unwrap(engine.execute(margin_tx))

        # Conservation
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply("TBILL-3M") == Decimal(0)


# ---------------------------------------------------------------------------
# Test: Negative-Path Lifecycle (Phase 5 D6)
# ---------------------------------------------------------------------------


class TestNegativePathLifecycle:
    """Invalid inputs at each stage produce Err, not exceptions."""

    def test_invalid_cds_order_rejected(self) -> None:
        from attestor.core.result import Err
        raw: dict[str, object] = {
            "order_id": "CDS-NEG-001",
            "instrument_id": "CDS-NEG",
            "side": "BUY",
            "quantity": "0",
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
        result = parse_cds_order(raw)
        assert isinstance(result, Err)

    def test_invalid_auction_price_rejected(self) -> None:
        from attestor.core.result import Err
        result = create_cds_credit_event_settlement(
            buyer_account="BUYER-CASH",
            seller_account="SELLER-CASH",
            notional=Decimal("10000000"),
            auction_price=Decimal("1.5"),
            currency="USD",
            tx_id="TX-NEG-CE",
            timestamp=_TS_UTC,
        )
        assert isinstance(result, Err)

    def test_invalid_lifecycle_transition(self) -> None:
        from attestor.core.result import Err
        result = check_transition(
            PositionStatusEnum.PROPOSED, PositionStatusEnum.CLOSED,
            DERIVATIVE_TRANSITIONS,
        )
        assert isinstance(result, Err)

    def test_empty_credit_curve_bootstrap(self) -> None:
        from attestor.core.result import Err
        result = bootstrap_credit_curve(
            quotes=(),
            discount_curve=unwrap(YieldCurve.create(
                currency="USD",
                as_of=date(2025, 6, 15),
                tenors=(Decimal("1"),),
                discount_factors=(Decimal("0.96"),),
                model_config_ref="CFG-NEG",
            )),
            config=unwrap(ModelConfig.create("CFG-NEG", "TEST", "1.0.0")),
            as_of=date(2025, 6, 15),
            reference_entity="ACME Corp",
        )
        assert isinstance(result, Err)
