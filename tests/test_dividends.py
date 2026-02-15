"""Tests for attestor.ledger.dividends — dividend transaction creation."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import UtcDatetime
from attestor.ledger.dividends import create_dividend_transaction
from attestor.ledger.engine import LedgerEngine
from attestor.ledger.transactions import Account, AccountType, ExecuteResult

_TS = UtcDatetime(value=datetime(2025, 8, 14, 10, 0, 0, tzinfo=UTC))


def _acct(aid: str, atype: AccountType = AccountType.CASH) -> Account:
    return Account(account_id=NonEmptyStr(value=aid), account_type=atype)


# ---------------------------------------------------------------------------
# Valid dividend
# ---------------------------------------------------------------------------


class TestValidDividend:
    def test_single_holder(self) -> None:
        result = create_dividend_transaction(
            instrument_id="AAPL",
            amount_per_share=Decimal("0.82"),
            currency="USD",
            holder_accounts=(("HOLDER_A", Decimal("100")),),
            issuer_account="ISSUER",
            tx_id="DIV-001",
            timestamp=_TS,
        )
        assert isinstance(result, Ok)
        tx = result.value
        assert len(tx.moves) == 1
        assert tx.moves[0].quantity.value == Decimal("82.00")
        assert tx.moves[0].source == "ISSUER"
        assert tx.moves[0].destination == "HOLDER_A"

    def test_multiple_holders(self) -> None:
        result = create_dividend_transaction(
            instrument_id="AAPL",
            amount_per_share=Decimal("0.82"),
            currency="USD",
            holder_accounts=(
                ("HOLDER_A", Decimal("100")),
                ("HOLDER_B", Decimal("200")),
                ("HOLDER_C", Decimal("50")),
            ),
            issuer_account="ISSUER",
            tx_id="DIV-002",
            timestamp=_TS,
        )
        assert isinstance(result, Ok)
        tx = result.value
        assert len(tx.moves) == 3
        total = sum(m.quantity.value for m in tx.moves)
        # 0.82 * (100 + 200 + 50) = 0.82 * 350 = 287.00
        assert total == Decimal("287.00")

    def test_total_cash_out_equals_sum_in(self) -> None:
        """Conservation: cash out of issuer == sum into all holders."""
        tx = unwrap(create_dividend_transaction(
            instrument_id="AAPL",
            amount_per_share=Decimal("1.50"),
            currency="USD",
            holder_accounts=(
                ("HOLDER_A", Decimal("100")),
                ("HOLDER_B", Decimal("300")),
            ),
            issuer_account="ISSUER",
            tx_id="DIV-003",
            timestamp=_TS,
        ))
        # All moves have source=ISSUER, so total out = sum of qty
        total_out = sum(m.quantity.value for m in tx.moves)
        assert total_out == Decimal("600.00")


# ---------------------------------------------------------------------------
# Dividend with LedgerEngine
# ---------------------------------------------------------------------------


class TestDividendWithEngine:
    def test_sigma_preserved(self) -> None:
        engine = LedgerEngine()
        engine.register_account(_acct("ISSUER"))
        engine.register_account(_acct("HOLDER_A"))
        engine.register_account(_acct("HOLDER_B"))

        tx = unwrap(create_dividend_transaction(
            instrument_id="AAPL",
            amount_per_share=Decimal("0.82"),
            currency="USD",
            holder_accounts=(
                ("HOLDER_A", Decimal("100")),
                ("HOLDER_B", Decimal("200")),
            ),
            issuer_account="ISSUER",
            tx_id="DIV-004",
            timestamp=_TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert result.value is ExecuteResult.APPLIED
        assert engine.total_supply("USD") == Decimal(0)

    def test_balances_after_dividend(self) -> None:
        engine = LedgerEngine()
        engine.register_account(_acct("ISSUER"))
        engine.register_account(_acct("HOLDER_A"))

        tx = unwrap(create_dividend_transaction(
            instrument_id="AAPL",
            amount_per_share=Decimal("2.00"),
            currency="USD",
            holder_accounts=(("HOLDER_A", Decimal("500")),),
            issuer_account="ISSUER",
            tx_id="DIV-005",
            timestamp=_TS,
        ))
        engine.execute(tx)
        assert engine.get_balance("ISSUER", "USD") == Decimal("-1000.00")
        assert engine.get_balance("HOLDER_A", "USD") == Decimal("1000.00")


# ---------------------------------------------------------------------------
# Invalid dividend
# ---------------------------------------------------------------------------


class TestInvalidDividend:
    def test_empty_holders(self) -> None:
        result = create_dividend_transaction(
            instrument_id="AAPL",
            amount_per_share=Decimal("0.82"),
            currency="USD",
            holder_accounts=(),
            issuer_account="ISSUER",
            tx_id="DIV-006",
            timestamp=_TS,
        )
        assert isinstance(result, Err)

    def test_zero_amount_per_share(self) -> None:
        result = create_dividend_transaction(
            instrument_id="AAPL",
            amount_per_share=Decimal("0"),
            currency="USD",
            holder_accounts=(("HOLDER_A", Decimal("100")),),
            issuer_account="ISSUER",
            tx_id="DIV-007",
            timestamp=_TS,
        )
        assert isinstance(result, Err)

    def test_empty_instrument_id(self) -> None:
        result = create_dividend_transaction(
            instrument_id="",
            amount_per_share=Decimal("0.82"),
            currency="USD",
            holder_accounts=(("HOLDER_A", Decimal("100")),),
            issuer_account="ISSUER",
            tx_id="DIV-008",
            timestamp=_TS,
        )
        assert isinstance(result, Err)

    def test_empty_tx_id(self) -> None:
        result = create_dividend_transaction(
            instrument_id="AAPL",
            amount_per_share=Decimal("0.82"),
            currency="USD",
            holder_accounts=(("HOLDER_A", Decimal("100")),),
            issuer_account="ISSUER",
            tx_id="",
            timestamp=_TS,
        )
        assert isinstance(result, Err)
