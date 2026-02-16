"""Integration tests for Phase 3 — full lifecycle flows.

Full FX Spot Lifecycle, NDF Lifecycle, IRS Lifecycle, Yield Curve Calibration.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import UtcDatetime
from attestor.gateway.parser import (
    parse_fx_spot_order,
    parse_irs_order,
    parse_ndf_order,
)
from attestor.instrument.derivative_types import FXDetail, IRSwapDetail
from attestor.instrument.fx_types import DayCountConvention, PaymentFrequency
from attestor.ledger.engine import LedgerEngine
from attestor.ledger.fx_settlement import (
    create_fx_spot_settlement,
    create_ndf_settlement,
)
from attestor.ledger.irs import (
    apply_rate_fixing,
    create_irs_cashflow_transaction,
    generate_fixed_leg_schedule,
    generate_float_leg_schedule,
)
from attestor.ledger.transactions import Account, AccountType
from attestor.oracle.arbitrage_gates import check_yield_curve_arbitrage_freedom
from attestor.oracle.calibration import (
    FailedCalibrationRecord,
    ModelConfig,
    RateInstrument,
    bootstrap_curve,
    handle_calibration_failure,
)
from attestor.oracle.fx_ingest import ingest_fx_rate, ingest_rate_fixing
from attestor.reporting.emir import project_emir_report
from attestor.reporting.mifid2 import (
    FXReportFields,
    IRSwapReportFields,
    project_mifid2_report,
)

_TS = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)


def _register(engine: LedgerEngine, *names: str) -> None:
    """Register CASH accounts in the engine."""
    for name in names:
        engine.register_account(Account(
            account_id=NonEmptyStr(value=name),
            account_type=AccountType.CASH,
        ))

_BASE: dict[str, object] = {
    "order_id": "ORD-INT-001",
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
# Full FX Spot Lifecycle
# ---------------------------------------------------------------------------


class TestFXSpotLifecycle:
    def test_step1_parse_fx_spot(self) -> None:
        raw = {**_BASE, "currency_pair": "EUR/USD"}
        order = unwrap(parse_fx_spot_order(raw))
        assert isinstance(order.instrument_detail, FXDetail)
        assert order.instrument_detail.currency_pair == "EUR/USD"

    def test_step3_ingest_fx_rate(self) -> None:
        att = unwrap(ingest_fx_rate(
            "EUR/USD", bid=Decimal("1.0849"), ask=Decimal("1.0851"),
            venue="REUTERS", timestamp=_TS,
        ))
        assert att.value.rate.value == (Decimal("1.0849") + Decimal("1.0851")) / 2

    def test_step4_to_7_book_and_settle(self) -> None:
        engine = LedgerEngine()
        _register(engine, "B-EUR", "B-USD", "S-EUR", "S-USD")
        order = unwrap(parse_fx_spot_order({**_BASE, "currency_pair": "EUR/USD"}))

        # Create settlement
        tx = unwrap(create_fx_spot_settlement(
            order=order,
            buyer_base_account="B-EUR", buyer_quote_account="B-USD",
            seller_base_account="S-EUR", seller_quote_account="S-USD",
            spot_rate=Decimal("1.0850"), tx_id="TX-INT-FX-1",
        ))

        # Execute
        result = engine.execute(tx)
        assert isinstance(result, Ok)

        # Multi-currency positions
        assert engine.get_balance("B-EUR", "EUR") == Decimal("1000000")
        assert engine.get_balance("S-EUR", "EUR") == Decimal("-1000000")
        assert engine.total_supply("EUR") == Decimal("0")
        assert engine.total_supply("USD") == Decimal("0")

    def test_step8_emir_report(self) -> None:
        order = unwrap(parse_fx_spot_order({**_BASE, "currency_pair": "EUR/USD"}))
        att = unwrap(project_emir_report(order, "ATT-FX-001"))
        assert att.value.instrument_id.value == "EURUSD-SPOT"

    def test_step9_mifid_report(self) -> None:
        order = unwrap(parse_fx_spot_order({**_BASE, "currency_pair": "EUR/USD"}))
        att = unwrap(project_mifid2_report(order, "ATT-FX-001"))
        assert isinstance(att.value.instrument_fields, FXReportFields)
        assert att.value.instrument_fields.currency_pair == "EUR/USD"

    def test_step10_idempotency(self) -> None:
        engine = LedgerEngine()
        _register(engine, "B-EUR", "B-USD", "S-EUR", "S-USD")
        order = unwrap(parse_fx_spot_order({**_BASE, "currency_pair": "EUR/USD"}))
        tx = unwrap(create_fx_spot_settlement(
            order=order,
            buyer_base_account="B-EUR", buyer_quote_account="B-USD",
            seller_base_account="S-EUR", seller_quote_account="S-USD",
            spot_rate=Decimal("1.0850"), tx_id="TX-INT-IDEM",
        ))
        result1 = engine.execute(tx)
        assert isinstance(result1, Ok)
        # Re-execute same tx — engine uses AlreadyApplied
        result2 = engine.execute(tx)
        assert isinstance(result2, Ok)
        # Balances unchanged (not doubled)
        assert engine.get_balance("B-EUR", "EUR") == Decimal("1000000")


# ---------------------------------------------------------------------------
# Full NDF Lifecycle
# ---------------------------------------------------------------------------


class TestNDFLifecycle:
    def _ndf_order(self) -> object:
        raw = {
            **_BASE,
            "instrument_id": "USDCNY-NDF",
            "currency_pair": "USD/CNY",
            "forward_rate": "7.2500",
            "fixing_date": "2025-09-13",
            "settlement_date": "2025-09-15",
            "fixing_source": "WMR",
        }
        return unwrap(parse_ndf_order(raw))

    def test_step1_parse_ndf(self) -> None:
        order = self._ndf_order()
        detail = order.instrument_detail
        assert isinstance(detail, FXDetail)
        assert detail.fixing_source is not None
        assert detail.fixing_source.value == "WMR"

    def test_step3_ingest_fixing(self) -> None:
        att = unwrap(ingest_rate_fixing(
            index_name="USDCNY", rate=Decimal("7.3000"),
            fixing_date=date(2025, 9, 13), source="WMR",
            timestamp=_TS, attestation_ref="ATT-FIX-001",
        ))
        assert att.value.rate == Decimal("7.3000")

    def test_step4_to_7_book_and_settle_ndf(self) -> None:
        engine = LedgerEngine()
        _register(engine, "B-USD", "S-USD")
        order = self._ndf_order()
        tx = unwrap(create_ndf_settlement(
            order=order,
            buyer_cash_account="B-USD", seller_cash_account="S-USD",
            fixing_rate=Decimal("7.3000"), tx_id="TX-INT-NDF-1",
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert engine.total_supply("USD") == Decimal("0")
        assert len(tx.moves) == 1  # single cash settlement

    def test_step8_ndf_report(self) -> None:
        order = self._ndf_order()
        att = unwrap(project_mifid2_report(order, "ATT-NDF-001"))
        fields = att.value.instrument_fields
        assert isinstance(fields, FXReportFields)
        assert fields.currency_pair == "USD/CNY"


# ---------------------------------------------------------------------------
# Full IRS Lifecycle
# ---------------------------------------------------------------------------


class TestIRSLifecycle:
    def _irs_order(self) -> object:
        raw = {
            **_BASE,
            "instrument_id": "IRS-USD-5Y",
            "fixed_rate": "0.035",
            "float_index": "SOFR",
            "day_count": "ACT/360",
            "payment_frequency": "QUARTERLY",
            "tenor_months": "60",
            "start_date": "2025-06-15",
            "end_date": "2030-06-15",
        }
        return unwrap(parse_irs_order(raw))

    def test_step1_parse_irs(self) -> None:
        order = self._irs_order()
        detail = order.instrument_detail
        assert isinstance(detail, IRSwapDetail)
        assert detail.fixed_rate.value == Decimal("0.035")
        assert detail.float_index.value == "SOFR"

    def test_step3_4_schedules(self) -> None:
        fixed = unwrap(generate_fixed_leg_schedule(
            notional=Decimal("10000000"), fixed_rate=Decimal("0.035"),
            start_date=date(2025, 6, 15), end_date=date(2026, 6, 15),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        floating = unwrap(generate_float_leg_schedule(
            notional=Decimal("10000000"),
            start_date=date(2025, 6, 15), end_date=date(2026, 6, 15),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        assert len(fixed.cashflows) == len(floating.cashflows)
        assert len(fixed.cashflows) == 4

    def test_step5_6_fixing(self) -> None:
        att = unwrap(ingest_rate_fixing(
            index_name="SOFR", rate=Decimal("0.053"),
            fixing_date=date(2025, 6, 15), source="FED",
            timestamp=_TS, attestation_ref="ATT-FIX-002",
        ))
        assert att.value.rate == Decimal("0.053")

        floating = unwrap(generate_float_leg_schedule(
            notional=Decimal("10000000"),
            start_date=date(2025, 6, 15), end_date=date(2026, 6, 15),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        fixed_float = unwrap(apply_rate_fixing(
            floating, notional=Decimal("10000000"),
            fixing_rate=Decimal("0.053"), fixing_date=date(2025, 6, 20),
        ))
        assert fixed_float.cashflows[0].amount > 0

    def test_step7_8_cashflow_booking(self) -> None:
        engine = LedgerEngine()
        _register(engine, "PAYER", "RECEIVER")
        fixed = unwrap(generate_fixed_leg_schedule(
            notional=Decimal("10000000"), fixed_rate=Decimal("0.035"),
            start_date=date(2025, 1, 1), end_date=date(2025, 7, 1),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        for i, cf in enumerate(fixed.cashflows):
            tx = unwrap(create_irs_cashflow_transaction(
                instrument_id="IRS-001", payer_account="PAYER",
                receiver_account="RECEIVER", cashflow=cf,
                tx_id=f"TX-INT-IRS-{i}", timestamp=UtcDatetime.now(),
            ))
            result = engine.execute(tx)
            assert isinstance(result, Ok)

        # Conservation after all cashflows
        assert engine.total_supply("USD") == Decimal("0")

    def test_step12_irs_report(self) -> None:
        order = self._irs_order()
        att = unwrap(project_mifid2_report(order, "ATT-IRS-001"))
        fields = att.value.instrument_fields
        assert isinstance(fields, IRSwapReportFields)
        assert fields.fixed_rate == Decimal("0.035")
        assert fields.float_index == "SOFR"
        assert fields.tenor_months == 60


# ---------------------------------------------------------------------------
# Full Yield Curve Calibration Pipeline
# ---------------------------------------------------------------------------


class TestYieldCurvePipeline:
    def _instruments(self) -> tuple[RateInstrument, ...]:
        return (
            RateInstrument(
                instrument_type=NonEmptyStr(value="DEPOSIT"),
                tenor=Decimal("0.25"), rate=Decimal("0.04"),
                currency=NonEmptyStr(value="USD"),
            ),
            RateInstrument(
                instrument_type=NonEmptyStr(value="FRA"),
                tenor=Decimal("0.5"), rate=Decimal("0.042"),
                currency=NonEmptyStr(value="USD"),
            ),
            RateInstrument(
                instrument_type=NonEmptyStr(value="SWAP"),
                tenor=Decimal("1"), rate=Decimal("0.045"),
                currency=NonEmptyStr(value="USD"),
            ),
            RateInstrument(
                instrument_type=NonEmptyStr(value="SWAP"),
                tenor=Decimal("2"), rate=Decimal("0.05"),
                currency=NonEmptyStr(value="USD"),
            ),
        )

    def _config(self) -> ModelConfig:
        return unwrap(ModelConfig.create("CFG-INT", "PIECEWISE_LOG_LINEAR", "1.0.0"))

    def test_step1_2_instruments_and_config(self) -> None:
        insts = self._instruments()
        assert len(insts) == 4
        config = self._config()
        assert config.config_id.value == "CFG-INT"

    def test_step3_bootstrap(self) -> None:
        att = unwrap(bootstrap_curve(
            self._instruments(), self._config(), date(2025, 6, 15), "USD",
        ))
        curve = att.value
        assert len(curve.tenors) == 4
        assert all(d > 0 for d in curve.discount_factors)

    def test_step4_arb_freedom_gates(self) -> None:
        att = unwrap(bootstrap_curve(
            self._instruments(), self._config(), date(2025, 6, 15), "USD",
        ))
        results = unwrap(check_yield_curve_arbitrage_freedom(att.value))
        critical = [r for r in results if r.severity.value == "CRITICAL"]
        assert all(r.passed for r in critical)

    def test_step5_discount_interpolation(self) -> None:
        from attestor.oracle.calibration import discount_factor
        att = unwrap(bootstrap_curve(
            self._instruments(), self._config(), date(2025, 6, 15), "USD",
        ))
        # Interpolate at 0.75y (between 0.5 and 1)
        d = unwrap(discount_factor(att.value, Decimal("0.75")))
        assert Decimal("0.95") < d < Decimal("0.99")

    def test_step6_7_failure_fallback(self) -> None:
        # Good curve
        good = unwrap(bootstrap_curve(
            self._instruments(), self._config(), date(2025, 6, 15), "USD",
        ))
        # Simulate failure + fallback
        result = handle_calibration_failure(
            error_reason="monotonicity violated",
            model_config=self._config(),
            last_good=good,
            timestamp=_TS,
        )
        assert isinstance(result, Ok)
        assert unwrap(result) is good

    def test_step6_no_fallback_err(self) -> None:
        result = handle_calibration_failure(
            error_reason="divergence",
            model_config=self._config(),
            last_good=None,
            timestamp=_TS,
        )
        assert isinstance(result, Err)

    def test_step8_failed_calibration_record(self) -> None:
        rec = FailedCalibrationRecord(
            model_class=NonEmptyStr(value="PIECEWISE_LOG_LINEAR"),
            reason=NonEmptyStr(value="AF-YC-03 failed"),
            fallback_config_ref="CFG-INT",
            timestamp=UtcDatetime.now(),
        )
        assert rec.reason.value == "AF-YC-03 failed"


# ---------------------------------------------------------------------------
# Import Smoke Tests
# ---------------------------------------------------------------------------


class TestImportSmoke:
    def test_import_fx_types(self) -> None:
        from attestor.instrument.fx_types import (
            FXSpotPayoutSpec,
        )
        assert FXSpotPayoutSpec is not None

    def test_import_fx_settlement(self) -> None:
        from attestor.ledger.fx_settlement import (
            create_fx_spot_settlement,
        )
        assert create_fx_spot_settlement is not None

    def test_import_irs(self) -> None:
        from attestor.ledger.irs import (
            ScheduledCashflow,
        )
        assert ScheduledCashflow is not None

    def test_import_calibration(self) -> None:
        from attestor.oracle.calibration import (
            ModelConfig,
        )
        assert ModelConfig is not None

    def test_import_arbitrage_gates(self) -> None:
        from attestor.oracle.arbitrage_gates import (
            ArbitrageCheckResult,
        )
        assert ArbitrageCheckResult is not None

    def test_import_fx_ingest(self) -> None:
        from attestor.oracle.fx_ingest import (
            FXRate,
        )
        assert FXRate is not None

    def test_import_reporting_fields(self) -> None:
        from attestor.reporting.mifid2 import FXReportFields, IRSwapReportFields
        assert FXReportFields is not None
        assert IRSwapReportFields is not None


# ---------------------------------------------------------------------------
# Engine Untouched Verification
# ---------------------------------------------------------------------------


class TestEngineUntouched:
    def test_no_fx_irs_keywords_in_engine(self) -> None:
        """engine.py must have zero FX/IRS keywords (Principle V)."""
        import inspect

        from attestor.ledger import engine
        source = inspect.getsource(engine)
        for keyword in ("FX", "forex", "currency_pair", "IRS", "swap", "cashflow",
                        "yield_curve", "calibration", "forward_rate"):
            assert keyword not in source, f"engine.py contains '{keyword}'"
