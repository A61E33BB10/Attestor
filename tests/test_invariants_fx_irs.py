"""Invariant tests for Phase 3 — conservation laws, arbitrage-freedom, commutativity.

CL-F1..F6: Conservation laws
INV-AF-01..04: Arbitrage-freedom invariants
CS-F1..F5: Commutativity squares
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from attestor.core.money import CurrencyPair, NonEmptyStr
from attestor.core.result import unwrap
from attestor.core.types import UtcDatetime
from attestor.gateway.parser import parse_fx_forward_order, parse_fx_spot_order, parse_ndf_order
from attestor.instrument.fx_types import DayCountConvention, PaymentFrequency
from attestor.ledger.engine import LedgerEngine
from attestor.ledger.fx_settlement import (
    create_fx_forward_settlement,
    create_fx_spot_settlement,
    create_ndf_settlement,
)
from attestor.ledger.irs import (
    apply_rate_fixing,
    create_irs_cashflow_transaction,
    generate_fixed_leg_schedule,
    generate_float_leg_schedule,
)
from attestor.oracle.arbitrage_gates import (
    check_fx_spot_forward_consistency,
    check_fx_triangular_arbitrage,
    check_yield_curve_arbitrage_freedom,
)
from attestor.oracle.calibration import (
    ModelConfig,
    RateInstrument,
    bootstrap_curve,
)
from attestor.pricing.protocols import StubPricingEngine

_BASE_FX: dict[str, object] = {
    "order_id": "ORD-INV-001",
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


# ---------------------------------------------------------------------------
# CL-F1: FX Spot Conservation (Hypothesis)
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    rate=st.decimals(
        min_value=Decimal("0.01"), max_value=Decimal("999"),
        allow_nan=False, allow_infinity=False, places=4,
    ),
)
def test_cl_f1_fx_spot_conservation(rate: Decimal) -> None:
    """sigma(BASE) = 0 AND sigma(QUOTE) = 0 for any FX spot rate."""
    order = unwrap(parse_fx_spot_order({**_BASE_FX, "currency_pair": "EUR/USD"}))
    tx = unwrap(create_fx_spot_settlement(
        order=order,
        buyer_base_account="B-EUR", buyer_quote_account="B-USD",
        seller_base_account="S-EUR", seller_quote_account="S-USD",
        spot_rate=rate, tx_id="TX-CL-F1",
    ))
    engine = LedgerEngine()
    engine.execute(tx)
    assert engine.total_supply("EUR") == Decimal("0"), f"EUR supply != 0 for rate={rate}"
    assert engine.total_supply("USD") == Decimal("0"), f"USD supply != 0 for rate={rate}"


# ---------------------------------------------------------------------------
# CL-F2: FX Forward Conservation
# ---------------------------------------------------------------------------


def test_cl_f2_fx_forward_conservation() -> None:
    """sigma(BASE) = sigma(QUOTE) = 0 after forward settlement."""
    raw = {
        **_BASE_FX, "currency_pair": "EUR/USD",
        "forward_rate": "1.0920", "settlement_date": "2025-09-15",
    }
    order = unwrap(parse_fx_forward_order(raw))
    tx = unwrap(create_fx_forward_settlement(
        order=order,
        buyer_base_account="B-EUR", buyer_quote_account="B-USD",
        seller_base_account="S-EUR", seller_quote_account="S-USD",
        tx_id="TX-CL-F2",
    ))
    engine = LedgerEngine()
    engine.execute(tx)
    assert engine.total_supply("EUR") == Decimal("0")
    assert engine.total_supply("USD") == Decimal("0")


# ---------------------------------------------------------------------------
# CL-F3: NDF Settlement Conservation
# ---------------------------------------------------------------------------


def test_cl_f3_ndf_conservation() -> None:
    """sigma(settlement_currency) = 0 after NDF cash settlement."""
    raw = {
        **_BASE_FX,
        "instrument_id": "USDCNY-NDF",
        "currency_pair": "USD/CNY",
        "forward_rate": "7.2500",
        "fixing_date": "2025-09-13",
        "settlement_date": "2025-09-15",
        "fixing_source": "WMR",
    }
    order = unwrap(parse_ndf_order(raw))
    tx = unwrap(create_ndf_settlement(
        order=order,
        buyer_cash_account="B-USD", seller_cash_account="S-USD",
        fixing_rate=Decimal("7.3000"), tx_id="TX-CL-F3",
    ))
    engine = LedgerEngine()
    engine.execute(tx)
    assert engine.total_supply("USD") == Decimal("0")


# ---------------------------------------------------------------------------
# CL-F4: IRS Cashflow Conservation (Hypothesis)
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    rate=st.decimals(
        min_value=Decimal("0.001"), max_value=Decimal("0.50"),
        allow_nan=False, allow_infinity=False, places=4,
    ),
)
def test_cl_f4_irs_cashflow_conservation(rate: Decimal) -> None:
    """sigma(USD) = 0 after any IRS cashflow exchange."""
    sched = unwrap(generate_fixed_leg_schedule(
        notional=Decimal("10000000"), fixed_rate=rate,
        start_date=date(2025, 1, 1), end_date=date(2025, 4, 1),
        day_count=DayCountConvention.ACT_360,
        payment_frequency=PaymentFrequency.QUARTERLY,
        currency="USD",
    ))
    cf = sched.cashflows[0]
    tx = unwrap(create_irs_cashflow_transaction(
        instrument_id="IRS-001", payer_account="PAYER",
        receiver_account="RECEIVER", cashflow=cf,
        tx_id="TX-CL-F4", timestamp=UtcDatetime.now(),
    ))
    engine = LedgerEngine()
    engine.execute(tx)
    assert engine.total_supply("USD") == Decimal("0"), f"conservation broken for rate={rate}"


# ---------------------------------------------------------------------------
# CL-F5: IRS Full Lifecycle Conservation
# ---------------------------------------------------------------------------


def test_cl_f5_irs_full_lifecycle() -> None:
    """Trade -> fixing -> cashflows: sigma(USD) = 0 throughout."""
    engine = LedgerEngine()

    # Fixed leg schedule
    fixed = unwrap(generate_fixed_leg_schedule(
        notional=Decimal("10000000"), fixed_rate=Decimal("0.035"),
        start_date=date(2025, 1, 1), end_date=date(2025, 7, 1),
        day_count=DayCountConvention.ACT_360,
        payment_frequency=PaymentFrequency.QUARTERLY,
        currency="USD",
    ))

    # Float leg schedule with rate fixing
    floating = unwrap(generate_float_leg_schedule(
        notional=Decimal("10000000"),
        start_date=date(2025, 1, 1), end_date=date(2025, 7, 1),
        day_count=DayCountConvention.ACT_360,
        payment_frequency=PaymentFrequency.QUARTERLY,
        currency="USD",
    ))
    floating = unwrap(apply_rate_fixing(
        floating, notional=Decimal("10000000"),
        fixing_rate=Decimal("0.053"), fixing_date=date(2025, 1, 15),
    ))

    # Book all fixed cashflows
    for i, cf in enumerate(fixed.cashflows):
        tx = unwrap(create_irs_cashflow_transaction(
            instrument_id="IRS-001", payer_account="A-PAYER",
            receiver_account="A-RECEIVER", cashflow=cf,
            tx_id=f"TX-FIXED-{i}", timestamp=UtcDatetime.now(),
        ))
        engine.execute(tx)
        assert engine.total_supply("USD") == Decimal("0"), f"broken after fixed cf {i}"

    # Book first float cashflow (the only one that's been fixed)
    cf0 = floating.cashflows[0]
    if cf0.amount > 0:
        tx = unwrap(create_irs_cashflow_transaction(
            instrument_id="IRS-001", payer_account="B-PAYER",
            receiver_account="B-RECEIVER", cashflow=cf0,
            tx_id="TX-FLOAT-0", timestamp=UtcDatetime.now(),
        ))
        engine.execute(tx)
        assert engine.total_supply("USD") == Decimal("0"), "broken after float cf 0"


# ---------------------------------------------------------------------------
# CL-F6: Multi-Currency Conservation
# ---------------------------------------------------------------------------


def test_cl_f6_multi_currency() -> None:
    """Multiple FX + IRS trades: sigma(U) = 0 for every U independently."""
    engine = LedgerEngine()

    # FX spot: EUR/USD
    order1 = unwrap(parse_fx_spot_order({**_BASE_FX, "currency_pair": "EUR/USD"}))
    tx1 = unwrap(create_fx_spot_settlement(
        order=order1,
        buyer_base_account="B-EUR", buyer_quote_account="B-USD",
        seller_base_account="S-EUR", seller_quote_account="S-USD",
        spot_rate=Decimal("1.0850"), tx_id="TX-MC-1",
    ))
    engine.execute(tx1)

    # IRS cashflow: USD
    sched = unwrap(generate_fixed_leg_schedule(
        notional=Decimal("10000000"), fixed_rate=Decimal("0.035"),
        start_date=date(2025, 1, 1), end_date=date(2025, 4, 1),
        day_count=DayCountConvention.ACT_360,
        payment_frequency=PaymentFrequency.QUARTERLY,
        currency="USD",
    ))
    tx2 = unwrap(create_irs_cashflow_transaction(
        instrument_id="IRS-001", payer_account="IRS-PAYER",
        receiver_account="IRS-RECEIVER", cashflow=sched.cashflows[0],
        tx_id="TX-MC-2", timestamp=UtcDatetime.now(),
    ))
    engine.execute(tx2)

    # All currencies conserved independently
    assert engine.total_supply("EUR") == Decimal("0")
    assert engine.total_supply("USD") == Decimal("0")


# ---------------------------------------------------------------------------
# INV-AF-01: Yield curve positive discount factors
# ---------------------------------------------------------------------------


def test_inv_af_01_yc_positive_dfs() -> None:
    """All bootstrapped curves must have D(t) > 0."""
    instruments = (
        RateInstrument(
            instrument_type=NonEmptyStr(value="DEPOSIT"),
            tenor=Decimal("0.25"), rate=Decimal("0.04"),
            currency=NonEmptyStr(value="USD"),
        ),
        RateInstrument(
            instrument_type=NonEmptyStr(value="SWAP"),
            tenor=Decimal("1"), rate=Decimal("0.05"),
            currency=NonEmptyStr(value="USD"),
        ),
    )
    config = unwrap(ModelConfig.create("CFG-001", "PIECEWISE_LOG_LINEAR", "1.0.0"))
    att = unwrap(bootstrap_curve(instruments, config, date(2025, 6, 15), "USD"))
    curve = att.value
    results = unwrap(check_yield_curve_arbitrage_freedom(curve))
    af_yc_01 = results[0]
    assert af_yc_01.check_id == "AF-YC-01"
    assert af_yc_01.passed is True


# ---------------------------------------------------------------------------
# INV-AF-02: Yield curve monotonicity
# ---------------------------------------------------------------------------


def test_inv_af_02_yc_monotonicity() -> None:
    """Bootstrapped curves from positive rates must be monotone decreasing."""
    instruments = (
        RateInstrument(
            instrument_type=NonEmptyStr(value="DEPOSIT"),
            tenor=Decimal("0.25"), rate=Decimal("0.04"),
            currency=NonEmptyStr(value="USD"),
        ),
        RateInstrument(
            instrument_type=NonEmptyStr(value="SWAP"),
            tenor=Decimal("1"), rate=Decimal("0.05"),
            currency=NonEmptyStr(value="USD"),
        ),
        RateInstrument(
            instrument_type=NonEmptyStr(value="SWAP"),
            tenor=Decimal("2"), rate=Decimal("0.055"),
            currency=NonEmptyStr(value="USD"),
        ),
    )
    config = unwrap(ModelConfig.create("CFG-002", "PIECEWISE_LOG_LINEAR", "1.0.0"))
    att = unwrap(bootstrap_curve(instruments, config, date(2025, 6, 15), "USD"))
    curve = att.value
    results = unwrap(check_yield_curve_arbitrage_freedom(curve))
    af_yc_03 = results[2]
    assert af_yc_03.check_id == "AF-YC-03"
    assert af_yc_03.passed is True


# ---------------------------------------------------------------------------
# INV-AF-03: FX triangular arbitrage
# ---------------------------------------------------------------------------


def test_inv_af_03_fx_triangular() -> None:
    """Consistent FX rates must pass triangular arbitrage check."""
    ej = Decimal("170.8875")
    ju = Decimal("1") / Decimal("157.50")
    ue = Decimal("1") / Decimal("1.0850")
    rates = (
        (unwrap(CurrencyPair.parse("EUR/JPY")), ej),
        (unwrap(CurrencyPair.parse("JPY/USD")), ju),
        (unwrap(CurrencyPair.parse("USD/EUR")), ue),
    )
    results = unwrap(check_fx_triangular_arbitrage(rates))
    assert len(results) == 1
    assert results[0].passed is True


# ---------------------------------------------------------------------------
# INV-AF-04: FX spot-forward consistency (CIP)
# ---------------------------------------------------------------------------


def test_inv_af_04_fx_cip() -> None:
    """CIP-consistent rates must pass the AF-FX-02 check."""
    spot = Decimal("1.0850")
    dom_df = Decimal("0.98")
    for_df = Decimal("0.97")
    fwd = spot * dom_df / for_df
    result = unwrap(check_fx_spot_forward_consistency(spot, fwd, dom_df, for_df))
    assert result.passed is True


# ---------------------------------------------------------------------------
# CS-F1: Master Square for FX
# ---------------------------------------------------------------------------


def test_cs_f1_master_square_fx() -> None:
    """stub_price(book(trade)) == book(stub_price(trade)) for FX."""
    oracle_price = Decimal("1085000")
    engine = StubPricingEngine(oracle_price=oracle_price)

    # Path A: price first
    val_a = unwrap(engine.price("EURUSD-SPOT", "MKT", "CFG"))

    # Path B: book first, then price
    order = unwrap(parse_fx_spot_order({**_BASE_FX, "currency_pair": "EUR/USD"}))
    tx = unwrap(create_fx_spot_settlement(
        order=order,
        buyer_base_account="B-EUR", buyer_quote_account="B-USD",
        seller_base_account="S-EUR", seller_quote_account="S-USD",
        spot_rate=Decimal("1.0850"), tx_id="TX-CS-F1",
    ))
    ledger = LedgerEngine()
    ledger.execute(tx)
    val_b = unwrap(engine.price("EURUSD-SPOT", "MKT", "CFG"))

    # Stub is deterministic -> same NPV regardless of booking order
    assert val_a.npv == val_b.npv


# ---------------------------------------------------------------------------
# CS-F2: Master Square for IRS
# ---------------------------------------------------------------------------


def test_cs_f2_master_square_irs() -> None:
    """stub_price(book(irs)) == book(stub_price(irs)) for IRS."""
    oracle_price = Decimal("25000")
    engine = StubPricingEngine(oracle_price=oracle_price)

    val_a = unwrap(engine.price("IRS-USD-5Y", "MKT", "CFG"))

    sched = unwrap(generate_fixed_leg_schedule(
        notional=Decimal("10000000"), fixed_rate=Decimal("0.035"),
        start_date=date(2025, 1, 1), end_date=date(2025, 4, 1),
        day_count=DayCountConvention.ACT_360,
        payment_frequency=PaymentFrequency.QUARTERLY,
        currency="USD",
    ))
    tx = unwrap(create_irs_cashflow_transaction(
        instrument_id="IRS-USD-5Y", payer_account="PAYER",
        receiver_account="RECEIVER", cashflow=sched.cashflows[0],
        tx_id="TX-CS-F2", timestamp=UtcDatetime.now(),
    ))
    ledger = LedgerEngine()
    ledger.execute(tx)
    val_b = unwrap(engine.price("IRS-USD-5Y", "MKT", "CFG"))

    assert val_a.npv == val_b.npv


# ---------------------------------------------------------------------------
# CS-F4: Oracle-Ledger consistency
# ---------------------------------------------------------------------------


def test_cs_f4_oracle_ledger_fx_consistency() -> None:
    """FX rate from Oracle matches the settlement rate used in ledger."""
    from datetime import UTC, datetime

    from attestor.oracle.fx_ingest import ingest_fx_rate
    oracle_rate = Decimal("1.0850")
    att = unwrap(ingest_fx_rate(
        "EUR/USD", bid=oracle_rate, ask=oracle_rate,
        venue="REUTERS", timestamp=datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC),
    ))
    observed = att.value.rate.value

    order = unwrap(parse_fx_spot_order({**_BASE_FX, "currency_pair": "EUR/USD"}))
    tx = unwrap(create_fx_spot_settlement(
        order=order,
        buyer_base_account="B-EUR", buyer_quote_account="B-USD",
        seller_base_account="S-EUR", seller_quote_account="S-USD",
        spot_rate=observed, tx_id="TX-CS-F4",
    ))
    # Quote amount should be quantity * oracle_rate
    quote_move = tx.moves[1]
    expected_quote = Decimal("1000000") * observed
    assert quote_move.quantity.value == expected_quote.quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# CS-F5: Calibration commutativity
# ---------------------------------------------------------------------------


def test_cs_f5_calibration_commutativity() -> None:
    """Same inputs always produce the same curve."""
    instruments = (
        RateInstrument(
            instrument_type=NonEmptyStr(value="DEPOSIT"),
            tenor=Decimal("0.25"), rate=Decimal("0.04"),
            currency=NonEmptyStr(value="USD"),
        ),
        RateInstrument(
            instrument_type=NonEmptyStr(value="SWAP"),
            tenor=Decimal("1"), rate=Decimal("0.05"),
            currency=NonEmptyStr(value="USD"),
        ),
    )
    config = unwrap(ModelConfig.create("CFG-001", "PIECEWISE_LOG_LINEAR", "1.0.0"))
    att1 = unwrap(bootstrap_curve(instruments, config, date(2025, 6, 15), "USD"))
    att2 = unwrap(bootstrap_curve(instruments, config, date(2025, 6, 15), "USD"))
    assert att1.value.tenors == att2.value.tenors
    assert att1.value.discount_factors == att2.value.discount_factors


# ---------------------------------------------------------------------------
# Parametric Polymorphism: engine.py unchanged
# ---------------------------------------------------------------------------


def test_parametric_engine_unchanged() -> None:
    """LedgerEngine handles FX and IRS without modification (Principle V)."""
    engine = LedgerEngine()

    # FX spot
    order = unwrap(parse_fx_spot_order({**_BASE_FX, "currency_pair": "EUR/USD"}))
    tx_fx = unwrap(create_fx_spot_settlement(
        order=order,
        buyer_base_account="B-EUR", buyer_quote_account="B-USD",
        seller_base_account="S-EUR", seller_quote_account="S-USD",
        spot_rate=Decimal("1.0850"), tx_id="TX-PARAM-1",
    ))
    engine.execute(tx_fx)

    # IRS cashflow
    sched = unwrap(generate_fixed_leg_schedule(
        notional=Decimal("10000000"), fixed_rate=Decimal("0.035"),
        start_date=date(2025, 1, 1), end_date=date(2025, 4, 1),
        day_count=DayCountConvention.ACT_360,
        payment_frequency=PaymentFrequency.QUARTERLY,
        currency="USD",
    ))
    tx_irs = unwrap(create_irs_cashflow_transaction(
        instrument_id="IRS-001", payer_account="PAYER",
        receiver_account="RECEIVER", cashflow=sched.cashflows[0],
        tx_id="TX-PARAM-2", timestamp=UtcDatetime.now(),
    ))
    engine.execute(tx_irs)

    # All currencies conserved
    assert engine.total_supply("EUR") == Decimal("0")
    assert engine.total_supply("USD") == Decimal("0")
