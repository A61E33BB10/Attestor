"""Conservation law tests — CL-A1, CL-A2, CL-A5, replay determinism.

CL-A1: Balance conservation — sigma(U) unchanged by every execute().
CL-A2: Double-entry — every Move: source debited == destination credited.
CL-A5: Deterministic execution — same inputs → same outputs across runs.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from attestor.core.money import NonEmptyStr, PositiveDecimal
from attestor.core.result import Ok, unwrap
from attestor.core.types import UtcDatetime
from attestor.ledger.engine import LedgerEngine
from attestor.ledger.settlement import create_settlement_transaction
from attestor.ledger.transactions import Account, AccountType, ExecuteResult, Move, Transaction
from attestor.gateway.types import CanonicalOrder, OrderSide, OrderType

_TS = UtcDatetime(value=datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC))


def _acct(aid: str) -> Account:
    return Account(account_id=NonEmptyStr(value=aid), account_type=AccountType.CASH)


def _move(src: str, dst: str, unit: str, qty: str) -> Move:
    return Move(
        source=src, destination=dst, unit=unit,
        quantity=unwrap(PositiveDecimal.parse(Decimal(qty))),
        contract_id="C1",
    )


def _tx(tx_id: str, moves: tuple[Move, ...]) -> Transaction:
    return Transaction(tx_id=tx_id, moves=moves, timestamp=_TS)


def _make_engine(accounts: tuple[str, ...] = ("A", "B", "C", "D")) -> LedgerEngine:
    engine = LedgerEngine()
    for a in accounts:
        engine.register_account(_acct(a))
    return engine


# ---------------------------------------------------------------------------
# CL-A1: Balance Conservation (Hypothesis)
# ---------------------------------------------------------------------------


class TestBalanceConservation:
    @given(
        amounts=st.lists(
            st.decimals(min_value=Decimal("0.01"), max_value=Decimal("1000000"),
                        places=2, allow_nan=False, allow_infinity=False),
            min_size=1, max_size=20,
        ),
        units=st.lists(
            st.sampled_from(["USD", "EUR", "AAPL", "MSFT"]),
            min_size=1, max_size=20,
        ),
    )
    @settings(max_examples=200)
    def test_sigma_invariant_random_transactions(
        self, amounts: list[Decimal], units: list[str],
    ) -> None:
        """INV-L01: For every unit U, sigma(U) == 0 after arbitrary transactions."""
        engine = _make_engine()
        accounts = ("A", "B", "C", "D")

        for i, (amt, unit) in enumerate(zip(amounts, units, strict=False)):
            src = accounts[i % len(accounts)]
            dst = accounts[(i + 1) % len(accounts)]
            move = _move(src, dst, unit, str(amt))
            engine.execute(_tx(f"TX-{i}", (move,)))

        # sigma(U) must be 0 for all units
        for unit in {"USD", "EUR", "AAPL", "MSFT"}:
            assert engine.total_supply(unit) == Decimal(0)

    def test_settlement_conservation(self) -> None:
        """Settlement: sigma(cash) == 0 and sigma(securities) == 0."""
        engine = LedgerEngine()
        for a in ("BC", "SC", "BS", "SS"):
            engine.register_account(_acct(a))

        order = unwrap(CanonicalOrder.create(
            order_id="ORD-1", instrument_id="AAPL", isin=None,
            side=OrderSide.BUY, quantity=Decimal("100"), price=Decimal("175.50"),
            currency="USD", order_type=OrderType.LIMIT,
            counterparty_lei="529900HNOAA1KXQJUQ27",
            executing_party_lei="529900ODI3JL1O4COU11",
            trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 17),
            venue="XNYS", timestamp=_TS,
        ))
        tx = unwrap(create_settlement_transaction(order, "BC", "BS", "SC", "SS", "STL-1"))
        engine.execute(tx)

        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply("AAPL") == Decimal(0)


# ---------------------------------------------------------------------------
# CL-A2: Double-Entry
# ---------------------------------------------------------------------------


class TestDoubleEntry:
    def test_every_move_is_balanced(self) -> None:
        """For every Move in a Transaction, source debit == destination credit."""
        engine = _make_engine()
        moves = (
            _move("A", "B", "USD", "100"),
            _move("B", "C", "EUR", "50"),
            _move("C", "D", "AAPL", "25"),
        )
        engine.execute(_tx("TX-1", moves))

        # Verify each move: the balance delta on source == -delta on destination
        assert engine.get_balance("A", "USD") == Decimal("-100")
        assert engine.get_balance("B", "USD") == Decimal("100")
        assert engine.get_balance("B", "EUR") == Decimal("-50")
        assert engine.get_balance("C", "EUR") == Decimal("50")
        assert engine.get_balance("C", "AAPL") == Decimal("-25")
        assert engine.get_balance("D", "AAPL") == Decimal("25")

    def test_multi_move_per_unit_balanced(self) -> None:
        """Multiple moves in same unit: net debits == net credits."""
        engine = _make_engine()
        moves = (
            _move("A", "B", "USD", "100"),
            _move("B", "C", "USD", "60"),
            _move("C", "D", "USD", "30"),
        )
        engine.execute(_tx("TX-1", moves))
        # Sum of all USD balances must be 0
        total = sum(engine.get_balance(a, "USD") for a in ("A", "B", "C", "D"))
        assert total == Decimal(0)


# ---------------------------------------------------------------------------
# CL-A5: Deterministic Execution
# ---------------------------------------------------------------------------


class TestDeterministicExecution:
    def test_same_inputs_same_outputs_100_runs(self) -> None:
        """Run the same transaction sequence 100 times, compare positions."""
        reference_positions: tuple[object, ...] | None = None

        for run in range(100):
            engine = _make_engine()
            engine.execute(_tx(f"TX-1-{run}", (_move("A", "B", "USD", "100"),)))
            engine.execute(_tx(f"TX-2-{run}", (_move("B", "C", "EUR", "50"),)))
            engine.execute(_tx(f"TX-3-{run}", (_move("C", "D", "AAPL", "25"),)))

            positions = engine.positions()
            if reference_positions is None:
                reference_positions = positions
            else:
                assert positions == reference_positions


# ---------------------------------------------------------------------------
# Replay Determinism
# ---------------------------------------------------------------------------


class TestReplayDeterminism:
    def test_replay_from_log_matches_original(self) -> None:
        """Execute sequence → clone at t → replay from clone → same state."""
        engine = _make_engine()
        txns = [
            _tx("TX-1", (_move("A", "B", "USD", "100"),)),
            _tx("TX-2", (_move("B", "C", "USD", "60"),)),
            _tx("TX-3", (_move("C", "D", "EUR", "200"),)),
        ]
        for tx in txns:
            engine.execute(tx)

        # Clone after all transactions
        clone = engine.clone()
        assert clone.positions() == engine.positions()
        assert clone.transaction_count() == engine.transaction_count()

    def test_clone_at_midpoint_replay_remaining(self) -> None:
        """Clone at midpoint, replay remaining transactions."""
        engine = _make_engine()
        tx1 = _tx("TX-1", (_move("A", "B", "USD", "100"),))
        tx2 = _tx("TX-2", (_move("B", "C", "USD", "60"),))
        tx3 = _tx("TX-3", (_move("C", "D", "USD", "30"),))

        engine.execute(tx1)
        engine.execute(tx2)
        midpoint = engine.clone()
        engine.execute(tx3)

        # Replay tx3 on midpoint clone
        midpoint.execute(tx3)
        assert midpoint.positions() == engine.positions()
        assert midpoint.get_balance("D", "USD") == engine.get_balance("D", "USD")

    def test_replay_idempotent(self) -> None:
        """Replaying the same tx on a clone is idempotent (ALREADY_APPLIED)."""
        engine = _make_engine()
        tx = _tx("TX-1", (_move("A", "B", "USD", "100"),))
        engine.execute(tx)
        clone = engine.clone()

        result = clone.execute(tx)
        assert isinstance(result, Ok)
        assert result.value is ExecuteResult.ALREADY_APPLIED
        assert clone.get_balance("A", "USD") == Decimal("-100")
