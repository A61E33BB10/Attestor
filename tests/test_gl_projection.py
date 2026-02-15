"""Tests for attestor.ledger.gl_projection — GL projection and trial balance."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import FrozenMap, UtcDatetime
from attestor.ledger.engine import LedgerEngine
from attestor.ledger.gl_projection import (
    GLAccountMapping,
    GLAccountType,
    GLProjection,
    project_gl,
)
from attestor.ledger.transactions import (
    Account,
    AccountType,
    Move,
    Transaction,
)

_TS = UtcDatetime(value=datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC))


def _setup_engine_with_trade() -> LedgerEngine:
    engine = LedgerEngine()
    for name, atype in [
        ("CASH-A", AccountType.CASH),
        ("CASH-B", AccountType.CASH),
        ("SEC-A", AccountType.SECURITIES),
        ("SEC-B", AccountType.SECURITIES),
    ]:
        engine.register_account(Account(
            account_id=unwrap(NonEmptyStr.parse(name)),
            account_type=atype,
        ))

    # Simple trade: A buys 100 AAPL from B for 17500 USD
    qty = unwrap(
        __import__("attestor.core.money", fromlist=["PositiveDecimal"])
        .PositiveDecimal.parse(Decimal("17500"))
    )
    sec_qty = unwrap(
        __import__("attestor.core.money", fromlist=["PositiveDecimal"])
        .PositiveDecimal.parse(Decimal("100"))
    )
    cash_move = Move("CASH-A", "CASH-B", "USD", qty, "TX-1")
    sec_move = Move("SEC-B", "SEC-A", "AAPL", sec_qty, "TX-1")
    tx = Transaction(tx_id="TX-1", moves=(cash_move, sec_move), timestamp=_TS)
    unwrap(engine.execute(tx))
    return engine


def _mapping() -> GLAccountMapping:
    fm = unwrap(FrozenMap.create({
        "CASH-A": ("GL-1000", GLAccountType.ASSET),
        "CASH-B": ("GL-1000", GLAccountType.ASSET),
        "SEC-A": ("GL-2000", GLAccountType.ASSET),
        "SEC-B": ("GL-2000", GLAccountType.ASSET),
    }))
    return GLAccountMapping(mappings=fm)


class TestGLProjection:
    def test_empty_engine(self) -> None:
        engine = LedgerEngine()
        mapping = _mapping()
        proj = project_gl(engine, mapping, _TS)
        assert len(proj.entries) == 0

    def test_trial_balance_balanced(self) -> None:
        engine = _setup_engine_with_trade()
        proj = project_gl(engine, _mapping(), _TS)
        result = proj.trial_balance()
        assert isinstance(result, Ok)
        assert unwrap(result) == Decimal(0)

    def test_entries_present(self) -> None:
        engine = _setup_engine_with_trade()
        proj = project_gl(engine, _mapping(), _TS)
        assert len(proj.entries) > 0

    def test_debit_credit_aggregation(self) -> None:
        engine = _setup_engine_with_trade()
        proj = project_gl(engine, _mapping(), _TS)
        # Find USD entries
        usd_entries = [
            e for e in proj.entries if e.instrument_id.value == "USD"
        ]
        total_debits = sum(e.debit_total for e in usd_entries)
        total_cr_total = sum(e.credit_total for e in usd_entries)
        assert total_debits == total_cr_total

    def test_unmapped_accounts_ignored(self) -> None:
        engine = _setup_engine_with_trade()
        # Only map CASH accounts
        fm = unwrap(FrozenMap.create({
            "CASH-A": ("GL-1000", GLAccountType.ASSET),
            "CASH-B": ("GL-1000", GLAccountType.ASSET),
        }))
        mapping = GLAccountMapping(mappings=fm)
        proj = project_gl(engine, mapping, _TS)
        # Only USD entries, no AAPL
        instruments = {e.instrument_id.value for e in proj.entries}
        assert "AAPL" not in instruments


class TestTrialBalance:
    def test_empty_projection_balanced(self) -> None:
        proj = GLProjection(entries=(), as_of=_TS)
        result = proj.trial_balance()
        assert isinstance(result, Ok)

    def test_unbalanced_returns_err(self) -> None:
        from attestor.ledger.gl_projection import GLEntry
        entry = GLEntry(
            gl_account=unwrap(NonEmptyStr.parse("GL-1000")),
            gl_account_type=GLAccountType.ASSET,
            instrument_id=unwrap(NonEmptyStr.parse("USD")),
            debit_total=Decimal("100"),
            credit_total=Decimal("50"),
        )
        proj = GLProjection(entries=(entry,), as_of=_TS)
        result = proj.trial_balance()
        assert isinstance(result, Err)
        assert "unbalanced" in result.error
