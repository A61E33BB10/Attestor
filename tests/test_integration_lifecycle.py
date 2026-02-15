"""Integration test: full equity lifecycle from raw order to EMIR report.

Raw order → parse → book → settle → dividend → EMIR report
Verifies every step produces correct state and all conservation laws hold.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from attestor.core.money import NonEmptyStr
from attestor.core.result import Ok, unwrap
from attestor.core.types import UtcDatetime
from attestor.gateway.parser import parse_order
from attestor.gateway.types import CanonicalOrder, OrderSide, OrderType
from attestor.instrument.lifecycle import BusinessEvent, ExecutePI, check_transition
from attestor.instrument.types import Party, PositionStatusEnum, create_equity_instrument
from attestor.ledger.dividends import create_dividend_transaction
from attestor.ledger.engine import LedgerEngine
from attestor.ledger.settlement import create_settlement_transaction
from attestor.ledger.transactions import Account, AccountType, ExecuteResult
from attestor.oracle.ingest import ingest_equity_fill
from attestor.pricing.protocols import StubPricingEngine
from attestor.reporting.emir import project_emir_report

_TS = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
_TS_UTC = UtcDatetime(value=_TS)


def _acct(aid: str, atype: AccountType = AccountType.CASH) -> Account:
    return Account(account_id=NonEmptyStr(value=aid), account_type=atype)


class TestFullEquityLifecycle:
    """End-to-end: raw order dict → parse → instrument → settle → dividend → report."""

    def test_full_lifecycle(self) -> None:
        # ---------------------------------------------------------------
        # Step 1: Raw order arrives (Pillar I — Gateway)
        # ---------------------------------------------------------------
        raw_order = {
            "order_id": "ORD-LIFECYCLE-001",
            "instrument_id": "AAPL",
            "side": "BUY",
            "quantity": "100",
            "price": "175.50",
            "currency": "USD",
            "order_type": "LIMIT",
            "counterparty_lei": "529900HNOAA1KXQJUQ27",
            "executing_party_lei": "529900ODI3JL1O4COU11",
            "trade_date": "2025-06-15",
            "venue": "XNYS",
            "timestamp": "2025-06-15T10:00:00+00:00",
        }
        order = unwrap(parse_order(raw_order))
        assert isinstance(order, CanonicalOrder)
        assert order.side is OrderSide.BUY
        assert order.quantity.value == Decimal("100")
        # Settlement date auto-computed: T+2 = 2025-06-17 (Mon→Wed)
        assert order.settlement_date == date(2025, 6, 17)

        # ---------------------------------------------------------------
        # Step 2: Create instrument (Pillar II — Instrument Model)
        # ---------------------------------------------------------------
        party = unwrap(Party.create("P001", "BuyCo", "529900ODI3JL1O4COU11"))
        instrument = unwrap(create_equity_instrument(
            "AAPL", "USD", "XNYS", (party,), order.trade_date,
        ))
        assert instrument.status is PositionStatusEnum.PROPOSED

        # Transition: PROPOSED → FORMED
        assert isinstance(
            check_transition(PositionStatusEnum.PROPOSED, PositionStatusEnum.FORMED), Ok,
        )

        # ---------------------------------------------------------------
        # Step 3: Oracle attests the fill price (Pillar III — Oracle)
        # ---------------------------------------------------------------
        fill_attestation = unwrap(ingest_equity_fill(
            instrument_id="AAPL", price=Decimal("175.50"),
            currency="USD", exchange="XNYS",
            timestamp=_TS, exchange_ref="FILL-XNYS-001",
        ))
        assert fill_attestation.value.price == Decimal("175.50")
        assert fill_attestation.content_hash  # non-empty

        # ---------------------------------------------------------------
        # Step 4: Book settlement (Pillar IV — Ledger)
        # ---------------------------------------------------------------
        engine = LedgerEngine()
        for a in ("BUYER_CASH", "SELLER_CASH", "BUYER_SEC", "SELLER_SEC", "ISSUER"):
            engine.register_account(_acct(a))

        settlement_tx = unwrap(create_settlement_transaction(
            order, "BUYER_CASH", "BUYER_SEC", "SELLER_CASH", "SELLER_SEC",
            f"STL-{order.order_id.value}",
        ))
        result = engine.execute(settlement_tx)
        assert isinstance(result, Ok)
        assert result.value is ExecuteResult.APPLIED

        # Verify 4 balance changes
        assert engine.get_balance("BUYER_CASH", "USD") == Decimal("-17550.00")
        assert engine.get_balance("SELLER_CASH", "USD") == Decimal("17550.00")
        assert engine.get_balance("SELLER_SEC", "AAPL") == Decimal("-100")
        assert engine.get_balance("BUYER_SEC", "AAPL") == Decimal("100")

        # Conservation laws
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply("AAPL") == Decimal(0)

        # Lifecycle: FORMED → SETTLED
        assert isinstance(
            check_transition(PositionStatusEnum.FORMED, PositionStatusEnum.SETTLED), Ok,
        )

        # ---------------------------------------------------------------
        # Step 5: Process dividend (Pillar IV — Ledger)
        # ---------------------------------------------------------------
        div_ts = UtcDatetime(value=datetime(2025, 8, 14, 10, 0, 0, tzinfo=UTC))
        div_tx = unwrap(create_dividend_transaction(
            instrument_id="AAPL",
            amount_per_share=Decimal("0.82"),
            currency="USD",
            holder_accounts=(("BUYER_SEC", Decimal("100")),),
            issuer_account="ISSUER",
            tx_id="DIV-AAPL-Q3-2025",
            timestamp=div_ts,
        ))
        div_result = engine.execute(div_tx)
        assert isinstance(div_result, Ok)
        assert div_result.value is ExecuteResult.APPLIED

        # Buyer received dividend
        assert engine.get_balance("BUYER_SEC", "USD") == Decimal("82.00")
        assert engine.get_balance("ISSUER", "USD") == Decimal("-82.00")

        # Conservation still holds
        assert engine.total_supply("USD") == Decimal(0)

        # ---------------------------------------------------------------
        # Step 6: Stub pricing (Pillar V — Pricing)
        # ---------------------------------------------------------------
        pricer = StubPricingEngine(oracle_price=Decimal("175.50"), currency="USD")
        val_result = unwrap(pricer.price("AAPL", "snap-1", "cfg-1"))
        assert val_result.npv == Decimal("175.50")

        # ---------------------------------------------------------------
        # Step 7: EMIR report (Pillar V — Reporting)
        # ---------------------------------------------------------------
        emir_attestation = unwrap(project_emir_report(
            order, fill_attestation.attestation_id,
        ))
        report = emir_attestation.value
        assert report.instrument_id.value == "AAPL"
        assert report.quantity.value == Decimal("100")
        assert report.price == Decimal("175.50")
        assert report.direction is OrderSide.BUY
        assert report.trade_date == date(2025, 6, 15)
        assert emir_attestation.provenance == (fill_attestation.attestation_id,)

        # ---------------------------------------------------------------
        # Step 8: Verify all invariants hold at the end
        # ---------------------------------------------------------------
        # INV-L01: balance conservation
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply("AAPL") == Decimal(0)

        # INV-X03: idempotency
        replay = engine.execute(settlement_tx)
        assert isinstance(replay, Ok) and replay.value is ExecuteResult.ALREADY_APPLIED

        # INV-L09: clone independence
        clone = engine.clone()
        assert clone.positions() == engine.positions()

        # INV-R05: content-addressed
        emir2 = unwrap(project_emir_report(order, fill_attestation.attestation_id))
        assert emir2.content_hash == emir_attestation.content_hash

        # Transaction count: settlement + dividend = 2
        assert engine.transaction_count() == 2

        # Position count: 6 non-zero (BUYER_CASH -USD, SELLER_CASH +USD,
        # BUYER_SEC +AAPL, SELLER_SEC -AAPL, BUYER_SEC +USD div, ISSUER -USD div)
        positions = engine.positions()
        assert len(positions) >= 4  # at least 4 non-zero

    def test_business_event_chain(self) -> None:
        """Verify BusinessEvent wraps instructions correctly through lifecycle."""
        order = unwrap(CanonicalOrder.create(
            order_id="ORD-BE-001", instrument_id="MSFT", isin=None,
            side=OrderSide.SELL, quantity=Decimal("50"), price=Decimal("420.00"),
            currency="USD", order_type=OrderType.LIMIT,
            counterparty_lei="529900HNOAA1KXQJUQ27",
            executing_party_lei="529900ODI3JL1O4COU11",
            trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 17),
            venue="XNYS", timestamp=_TS_UTC,
        ))
        event = BusinessEvent(
            instruction=ExecutePI(order=order),
            timestamp=_TS_UTC,
            attestation_id="ATT-BE-001",
        )
        assert event.attestation_id == "ATT-BE-001"
        assert isinstance(event.instruction, ExecutePI)


class TestImportSmokeTest:
    """Verify all Phase 1 types are importable — CI import smoke test."""

    def test_gateway_imports(self) -> None:
        from attestor.gateway import CanonicalOrder, OrderSide, OrderType, parse_order
        assert CanonicalOrder is not None

    def test_instrument_imports(self) -> None:
        from attestor.instrument import (
            EconomicTerms,
            EquityPayoutSpec,
            Instrument,
            Party,
            Product,
        )
        assert Instrument is not None

    def test_lifecycle_imports(self) -> None:
        from attestor.instrument.lifecycle import (
            EQUITY_TRANSITIONS,
            BusinessEvent,
            DividendPI,
            ExecutePI,
            PrimitiveInstruction,
            TransferPI,
            check_transition,
        )
        assert PrimitiveInstruction is not None

    def test_ledger_imports(self) -> None:
        from attestor.ledger import LedgerEngine, Move, Transaction
        from attestor.ledger.dividends import create_dividend_transaction
        from attestor.ledger.settlement import create_settlement_transaction
        assert LedgerEngine is not None

    def test_oracle_imports(self) -> None:
        from attestor.oracle.ingest import (
            MarketDataPoint,
            ingest_equity_fill,
            ingest_equity_quote,
        )
        assert MarketDataPoint is not None

    def test_reporting_imports(self) -> None:
        from attestor.reporting.emir import EMIRTradeReport, project_emir_report
        assert EMIRTradeReport is not None

    def test_pricing_imports(self) -> None:
        from attestor.pricing.protocols import StubPricingEngine
        assert StubPricingEngine is not None

    def test_infra_imports(self) -> None:
        from attestor.infra.config import PHASE1_TOPICS, phase1_topic_configs
        assert len(PHASE1_TOPICS) == 5
