"""Integration tests — full end-to-end option and futures lifecycles.

Each test exercises Gateway -> Instrument -> Oracle -> Ledger -> Pricing -> Reporting.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from attestor.core.money import NonEmptyStr
from attestor.core.result import unwrap
from attestor.core.types import UtcDatetime
from attestor.gateway.parser import parse_futures_order, parse_option_order
from attestor.gateway.types import CanonicalOrder, OrderSide, OrderType
from attestor.instrument.derivative_types import (
    FuturesDetail,
    OptionDetail,
    OptionExerciseStyleEnum,
    OptionTypeEnum,
    SettlementType,
)
from attestor.instrument.lifecycle import (
    DERIVATIVE_TRANSITIONS,
    check_transition,
)
from attestor.instrument.types import (
    Instrument,
    PositionStatusEnum,
    create_futures_instrument,
    create_option_instrument,
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
from attestor.ledger.transactions import Account, AccountType, ExecuteResult
from attestor.oracle.derivative_ingest import (
    ingest_futures_settlement,
    ingest_option_quote,
)
from attestor.pricing.protocols import StubPricingEngine
from attestor.reporting.mifid2 import (
    FuturesReportFields,
    OptionReportFields,
    project_mifid2_report,
)

_TS = UtcDatetime(value=datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC))
_LEI_A = "529900HNOAA1KXQJUQ27"
_LEI_B = "529900ODI3JL1O4COU11"


def _make_engine(*account_specs: tuple[str, AccountType]) -> LedgerEngine:
    engine = LedgerEngine()
    for name, atype in account_specs:
        engine.register_account(Account(
            account_id=unwrap(NonEmptyStr.parse(name)),
            account_type=atype,
        ))
    return engine


# ---------------------------------------------------------------------------
# Full option lifecycle (end-to-end)
# ---------------------------------------------------------------------------


class TestFullOptionLifecycle:
    def test_option_lifecycle_cash_settlement(self) -> None:
        """
        1. Parse option order (Gateway) with OptionDetail
        2. Create option instrument with OptionPayoutSpec
        3. Oracle attests option quote (QuotedConfidence)
        4. Book premium + open position (2 Moves)
        5. Lifecycle: PROPOSED -> FORMED -> SETTLED
        6. Cash settlement exercise (2 Moves)
        7. Lifecycle: SETTLED -> CLOSED
        8. Stub pricing returns oracle price
        9. MiFID II report generated
        10. All conservation laws hold
        11. Idempotency: replay = ALREADY_APPLIED
        """
        # 1. Parse option order via Gateway
        raw: dict[str, object] = {
            "order_id": "OPT-E2E-001",
            "instrument_id": "AAPL251219C00150000",
            "side": "BUY",
            "quantity": "10",
            "price": "5.50",
            "currency": "USD",
            "order_type": "LIMIT",
            "counterparty_lei": _LEI_A,
            "executing_party_lei": _LEI_B,
            "trade_date": date(2025, 6, 15),
            "settlement_date": date(2025, 6, 16),
            "venue": "CBOE",
            "timestamp": datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC),
            # Option-specific
            "strike": "150",
            "expiry_date": date(2025, 12, 19),
            "option_type": "Call",
            "option_style": "American",
            "settlement_type": "CASH",
            "underlying_id": "AAPL",
        }
        order = unwrap(parse_option_order(raw))
        assert isinstance(order.instrument_detail, OptionDetail)

        # 2. Create option instrument
        from attestor.instrument.types import Party
        party_a = unwrap(Party.create("PA", "Party A", _LEI_A))
        party_b = unwrap(Party.create("PB", "Party B", _LEI_B))
        instrument = unwrap(create_option_instrument(
            "AAPL251219C00150000", "AAPL", Decimal("150"),
            date(2025, 12, 19), OptionTypeEnum.CALL, OptionExerciseStyleEnum.AMERICAN,
            SettlementType.CASH, "USD", "CBOE",
            (party_a, party_b), date(2025, 6, 15),
        ))
        assert isinstance(instrument, Instrument)
        assert instrument.status == PositionStatusEnum.PROPOSED

        # 3. Oracle attests option quote
        quote_att = unwrap(ingest_option_quote(
            instrument_id="AAPL251219C00150000",
            underlying_id="AAPL", strike=Decimal("150"),
            expiry_date=date(2025, 12, 19), option_type=OptionTypeEnum.CALL,
            bid=Decimal("5.00"), ask=Decimal("5.50"),
            currency="USD", venue="CBOE",
            timestamp=datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC),
        ))
        assert quote_att.value.bid == Decimal("5.00")

        # 4. Book premium + open position
        engine = _make_engine(
            ("BUYER-CASH", AccountType.CASH),
            ("SELLER-CASH", AccountType.CASH),
            ("BUYER-POS", AccountType.DERIVATIVES),
            ("SELLER-POS", AccountType.DERIVATIVES),
        )
        premium_tx = unwrap(create_premium_transaction(
            order, "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-PREM-001",
        ))
        result = unwrap(engine.execute(premium_tx))
        assert result == ExecuteResult.APPLIED

        # 5. Lifecycle transitions
        unwrap(check_transition(
            PositionStatusEnum.PROPOSED, PositionStatusEnum.FORMED,
            DERIVATIVE_TRANSITIONS,
        ))
        unwrap(check_transition(
            PositionStatusEnum.FORMED, PositionStatusEnum.SETTLED,
            DERIVATIVE_TRANSITIONS,
        ))

        # 6. Cash settlement exercise (ITM: settlement_price > strike)
        exercise_tx = unwrap(create_cash_settlement_exercise_transaction(
            order, "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS",
            "TX-EX-001", settlement_price=Decimal("175"),
        ))
        result = unwrap(engine.execute(exercise_tx))
        assert result == ExecuteResult.APPLIED

        # 7. Lifecycle: SETTLED -> CLOSED
        unwrap(check_transition(
            PositionStatusEnum.SETTLED, PositionStatusEnum.CLOSED,
            DERIVATIVE_TRANSITIONS,
        ))

        # 8. Stub pricing
        pricing = StubPricingEngine(oracle_price=Decimal("5.50"))
        price_result = unwrap(pricing.price("AAPL251219C00150000", "snap", "cfg"))
        assert price_result.npv == Decimal("5.50")

        # 9. MiFID II report
        report_att = unwrap(project_mifid2_report(order, "ATT-E2E-001"))
        report = report_att.value
        assert isinstance(report.instrument_fields, OptionReportFields)
        assert report.instrument_fields.strike == Decimal("150")
        assert report.instrument_fields.option_type == OptionTypeEnum.CALL

        # 10. Conservation
        contract_unit = (
            f"OPT-AAPL-CALL-150-{date(2025, 12, 19).isoformat()}"
        )
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply(contract_unit) == Decimal(0)

        # 11. Idempotency
        replay = unwrap(engine.execute(premium_tx))
        assert replay == ExecuteResult.ALREADY_APPLIED

    def test_option_lifecycle_expiry(self) -> None:
        """Premium + OTM expiry (no exercise) — position closed, no extra cash."""
        detail = unwrap(OptionDetail.create(
            strike=Decimal("200"), expiry_date=date(2025, 12, 19),
            option_type=OptionTypeEnum.CALL, option_style=OptionExerciseStyleEnum.EUROPEAN,
            settlement_type=SettlementType.PHYSICAL, underlying_id="AAPL",
        ))
        order = unwrap(CanonicalOrder.create(
            order_id="OPT-OTM", instrument_id="OPT-OTM-ID",
            isin=None, side=OrderSide.BUY, quantity=Decimal("5"),
            price=Decimal("2.00"), currency="USD",
            order_type=OrderType.LIMIT,
            counterparty_lei=_LEI_A, executing_party_lei=_LEI_B,
            trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 16),
            venue="CBOE", timestamp=_TS, instrument_detail=detail,
        ))

        engine = _make_engine(
            ("B-CASH", AccountType.CASH), ("S-CASH", AccountType.CASH),
            ("B-POS", AccountType.DERIVATIVES), ("S-POS", AccountType.DERIVATIVES),
        )

        # Premium
        tx1 = unwrap(create_premium_transaction(
            order, "B-CASH", "S-CASH", "B-POS", "S-POS", "TX-OTM-1",
        ))
        unwrap(engine.execute(tx1))

        # Expiry (OTM — no exercise)
        contract_unit = (
            f"OPT-AAPL-CALL-200-{date(2025, 12, 19).isoformat()}"
        )
        tx2 = unwrap(create_expiry_transaction(
            "OPT-OTM-ID", "B-POS", "S-POS",
            Decimal("5"), contract_unit, "TX-OTM-2", _TS,
        ))
        unwrap(engine.execute(tx2))

        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply(contract_unit) == Decimal(0)


# ---------------------------------------------------------------------------
# Full futures lifecycle (end-to-end)
# ---------------------------------------------------------------------------


class TestFullFuturesLifecycle:
    def test_futures_lifecycle_open_margins_expiry(self) -> None:
        """
        1. Parse futures order with FuturesDetail
        2. Create futures instrument with FuturesPayoutSpec
        3. Open position (1 Move)
        4. Oracle attests settlement prices (FirmConfidence)
        5. Day 1-2: variation margin settlements
        6. Day 3: futures expiry (final margin + close position)
        7. Lifecycle: SETTLED -> CLOSED
        8. Conservation: cumulative margin == (final - initial) * size * qty
        9. MiFID II report generated
        10. Idempotency
        """
        # 1. Parse futures order
        raw: dict[str, object] = {
            "order_id": "FUT-E2E-001",
            "instrument_id": "ESZ5",
            "side": "BUY",
            "quantity": "5",
            "price": "5200",
            "currency": "USD",
            "order_type": "MARKET",
            "counterparty_lei": _LEI_A,
            "executing_party_lei": _LEI_B,
            "trade_date": date(2025, 6, 15),
            "venue": "CME",
            "timestamp": datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC),
            # Futures-specific
            "expiry_date": date(2025, 12, 19),
            "contract_size": "50",
            "settlement_type": "CASH",
            "underlying_id": "ES",
        }
        order = unwrap(parse_futures_order(raw))
        assert isinstance(order.instrument_detail, FuturesDetail)

        # 2. Create futures instrument
        from attestor.instrument.types import Party
        party_a = unwrap(Party.create("PA", "Party A", _LEI_A))
        party_b = unwrap(Party.create("PB", "Party B", _LEI_B))
        instrument = unwrap(create_futures_instrument(
            "ESZ5", "ES", date(2025, 12, 19), date(2025, 12, 18),
            SettlementType.CASH, Decimal("50"), "USD", "CME",
            (party_a, party_b), date(2025, 6, 15),
        ))
        assert instrument.status == PositionStatusEnum.PROPOSED

        # 3. Open position
        engine = _make_engine(
            ("LONG-CASH", AccountType.MARGIN),
            ("SHORT-CASH", AccountType.MARGIN),
            ("LONG-POS", AccountType.DERIVATIVES),
            ("SHORT-POS", AccountType.DERIVATIVES),
        )
        open_tx = unwrap(create_futures_open_transaction(
            "ESZ5", "LONG-POS", "SHORT-POS",
            Decimal("5"), "FUT-ES", "TX-OPEN", _TS,
        ))
        result = unwrap(engine.execute(open_tx))
        assert result == ExecuteResult.APPLIED

        # 4. Oracle attestations
        att_d1 = unwrap(ingest_futures_settlement(
            "ESZ5", Decimal("5250"), "USD", date(2025, 6, 16),
            "CME", datetime(2025, 6, 16, 16, 0, 0, tzinfo=UTC),
            "CME-ESZ5-20250616",
        ))
        assert att_d1.value.settlement_price == Decimal("5250")

        att_d2 = unwrap(ingest_futures_settlement(
            "ESZ5", Decimal("5300"), "USD", date(2025, 6, 17),
            "CME", datetime(2025, 6, 17, 16, 0, 0, tzinfo=UTC),
            "CME-ESZ5-20250617",
        ))
        assert att_d2.value.settlement_price == Decimal("5300")

        # 5. Variation margins
        ts_d1 = UtcDatetime(value=datetime(2025, 6, 16, 16, 0, 0, tzinfo=UTC))
        margin_d1 = unwrap(create_variation_margin_transaction(
            "ESZ5", "LONG-CASH", "SHORT-CASH",
            Decimal("5250"), Decimal("5200"),
            Decimal("50"), Decimal("5"), "TX-M1", ts_d1,
        ))
        unwrap(engine.execute(margin_d1))

        ts_d2 = UtcDatetime(value=datetime(2025, 6, 17, 16, 0, 0, tzinfo=UTC))
        margin_d2 = unwrap(create_variation_margin_transaction(
            "ESZ5", "LONG-CASH", "SHORT-CASH",
            Decimal("5300"), Decimal("5250"),
            Decimal("50"), Decimal("5"), "TX-M2", ts_d2,
        ))
        unwrap(engine.execute(margin_d2))

        # 6. Futures expiry: final settlement at 5350
        ts_exp = UtcDatetime(value=datetime(2025, 6, 18, 16, 0, 0, tzinfo=UTC))
        expiry_tx = unwrap(create_futures_expiry_transaction(
            "ESZ5", "LONG-CASH", "SHORT-CASH",
            "LONG-POS", "SHORT-POS",
            Decimal("5350"), Decimal("5300"),
            Decimal("50"), Decimal("5"), "FUT-ES", "TX-EXP", ts_exp,
        ))
        unwrap(engine.execute(expiry_tx))

        # 7. Lifecycle transitions
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

        # 8. Conservation + cumulative check
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply("FUT-ES") == Decimal(0)
        # Long cumulative: (5350 - 5200) * 50 * 5 = 37500
        long_cash = engine.get_balance("LONG-CASH", "USD")
        assert long_cash == Decimal("37500")

        # 9. MiFID II report
        report_att = unwrap(project_mifid2_report(order, "ATT-FUT-001"))
        report = report_att.value
        assert isinstance(report.instrument_fields, FuturesReportFields)
        assert report.instrument_fields.contract_size == Decimal("50")

        # 10. Idempotency
        replay = unwrap(engine.execute(open_tx))
        assert replay == ExecuteResult.ALREADY_APPLIED


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------


class TestImportSmoke:
    def test_import_derivative_types(self) -> None:
        from attestor.instrument.derivative_types import (
            OptionTypeEnum,
            SettlementType,
        )
        assert OptionTypeEnum.CALL.value == "Call"
        assert SettlementType.PHYSICAL.value == "PHYSICAL"

    def test_import_ledger_options(self) -> None:
        from attestor.ledger.options import create_premium_transaction as f
        assert callable(f)

    def test_import_ledger_futures(self) -> None:
        from attestor.ledger.futures import create_futures_open_transaction as f
        assert callable(f)

    def test_import_gl_projection(self) -> None:
        from attestor.ledger.gl_projection import project_gl as f
        assert callable(f)

    def test_import_oracle_derivatives(self) -> None:
        from attestor.oracle.derivative_ingest import ingest_option_quote as f
        assert callable(f)

    def test_import_mifid2(self) -> None:
        from attestor.reporting.mifid2 import project_mifid2_report as f
        assert callable(f)

    def test_import_lifecycle_derivatives(self) -> None:
        from attestor.instrument.lifecycle import DERIVATIVE_TRANSITIONS
        assert len(DERIVATIVE_TRANSITIONS) > 0

    def test_import_infra_phase2(self) -> None:
        from attestor.infra.config import PHASE2_TOPICS
        assert len(PHASE2_TOPICS) == 5


# ---------------------------------------------------------------------------
# Engine untouched verification
# ---------------------------------------------------------------------------


class TestEngineUntouched:
    def test_engine_has_no_instrument_specific_code(self) -> None:
        """Verify engine.py has no references to options, futures, derivatives."""
        import inspect

        from attestor.ledger import engine
        source = inspect.getsource(engine)
        # Strip __future__ import line so "future" doesn't false-positive
        lines = [
            line for line in source.splitlines()
            if "__future__" not in line
        ]
        filtered = "\n".join(lines).lower()
        for keyword in ["option", "future", "derivative", "margin", "exercise"]:
            assert keyword not in filtered, (
                f"engine.py must not reference '{keyword}' — "
                f"parametric polymorphism (Principle V)"
            )
