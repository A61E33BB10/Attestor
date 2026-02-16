"""Tests for attestor.ledger.collateral -- margin calls, returns, substitutions."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import UtcDatetime
from attestor.ledger.collateral import (
    CollateralAgreement,
    CollateralType,
    compute_margin_call,
    create_collateral_return_transaction,
    create_collateral_substitution_transaction,
    create_margin_call_transaction,
)
from attestor.ledger.engine import LedgerEngine
from attestor.ledger.transactions import Account, AccountType, ExecuteResult

_TS = UtcDatetime(value=datetime(2025, 7, 1, 14, 0, 0, tzinfo=UTC))


def _setup_engine() -> LedgerEngine:
    """Create a LedgerEngine with collateral-relevant accounts registered."""
    engine = LedgerEngine()
    for name, atype in [
        ("CALLER-COLLATERAL", AccountType.COLLATERAL),
        ("POSTER-COLLATERAL", AccountType.COLLATERAL),
        ("HOLDER-COLLATERAL", AccountType.COLLATERAL),
        ("RECEIVER-COLLATERAL", AccountType.COLLATERAL),
        ("RETURNER-COLLATERAL", AccountType.COLLATERAL),
    ]:
        engine.register_account(Account(
            account_id=unwrap(NonEmptyStr.parse(name)),
            account_type=atype,
        ))
    return engine


# ---------------------------------------------------------------------------
# CollateralType enum
# ---------------------------------------------------------------------------


class TestCollateralType:
    def test_all_four_values(self) -> None:
        assert len(CollateralType) == 4

    def test_cash_value(self) -> None:
        assert CollateralType.CASH.value == "CASH"

    def test_government_bond_value(self) -> None:
        assert CollateralType.GOVERNMENT_BOND.value == "GOVERNMENT_BOND"

    def test_corporate_bond_value(self) -> None:
        assert CollateralType.CORPORATE_BOND.value == "CORPORATE_BOND"

    def test_equity_value(self) -> None:
        assert CollateralType.EQUITY.value == "EQUITY"


# ---------------------------------------------------------------------------
# CollateralAgreement.create
# ---------------------------------------------------------------------------


class TestCollateralAgreementCreate:
    def test_valid_all_fields(self) -> None:
        result = CollateralAgreement.create(
            agreement_id="CSA-001",
            party_a="BANK-A",
            party_b="FUND-B",
            eligible_collateral=(CollateralType.CASH, CollateralType.GOVERNMENT_BOND),
            threshold_a=Decimal("10000000"),
            threshold_b=Decimal("5000000"),
            minimum_transfer_amount=Decimal("250000"),
            currency="USD",
        )
        assert isinstance(result, Ok)
        csa = unwrap(result)
        assert csa.agreement_id.value == "CSA-001"
        assert csa.party_a.value == "BANK-A"
        assert csa.party_b.value == "FUND-B"
        assert len(csa.eligible_collateral) == 2
        assert csa.threshold_a == Decimal("10000000")
        assert csa.threshold_b == Decimal("5000000")
        assert csa.minimum_transfer_amount == Decimal("250000")
        assert csa.currency.value == "USD"

    def test_reject_negative_threshold_a(self) -> None:
        result = CollateralAgreement.create(
            agreement_id="CSA-002",
            party_a="BANK-A",
            party_b="FUND-B",
            eligible_collateral=(CollateralType.CASH,),
            threshold_a=Decimal("-1"),
            threshold_b=Decimal("0"),
            minimum_transfer_amount=Decimal("0"),
            currency="EUR",
        )
        assert isinstance(result, Err)
        assert "threshold_a" in result.error

    def test_reject_negative_threshold_b(self) -> None:
        result = CollateralAgreement.create(
            agreement_id="CSA-003",
            party_a="BANK-A",
            party_b="FUND-B",
            eligible_collateral=(CollateralType.CASH,),
            threshold_a=Decimal("0"),
            threshold_b=Decimal("-100"),
            minimum_transfer_amount=Decimal("0"),
            currency="EUR",
        )
        assert isinstance(result, Err)
        assert "threshold_b" in result.error

    def test_reject_negative_mta(self) -> None:
        result = CollateralAgreement.create(
            agreement_id="CSA-004",
            party_a="BANK-A",
            party_b="FUND-B",
            eligible_collateral=(CollateralType.CASH,),
            threshold_a=Decimal("0"),
            threshold_b=Decimal("0"),
            minimum_transfer_amount=Decimal("-50"),
            currency="EUR",
        )
        assert isinstance(result, Err)
        assert "minimum_transfer_amount" in result.error

    def test_reject_empty_eligible_collateral(self) -> None:
        result = CollateralAgreement.create(
            agreement_id="CSA-005",
            party_a="BANK-A",
            party_b="FUND-B",
            eligible_collateral=(),
            threshold_a=Decimal("0"),
            threshold_b=Decimal("0"),
            minimum_transfer_amount=Decimal("0"),
            currency="EUR",
        )
        assert isinstance(result, Err)
        assert "eligible_collateral" in result.error

    def test_reject_empty_agreement_id(self) -> None:
        result = CollateralAgreement.create(
            agreement_id="",
            party_a="BANK-A",
            party_b="FUND-B",
            eligible_collateral=(CollateralType.CASH,),
            threshold_a=Decimal("0"),
            threshold_b=Decimal("0"),
            minimum_transfer_amount=Decimal("0"),
            currency="EUR",
        )
        assert isinstance(result, Err)
        assert "agreement_id" in result.error

    def test_reject_empty_party_a(self) -> None:
        result = CollateralAgreement.create(
            agreement_id="CSA-006",
            party_a="",
            party_b="FUND-B",
            eligible_collateral=(CollateralType.CASH,),
            threshold_a=Decimal("0"),
            threshold_b=Decimal("0"),
            minimum_transfer_amount=Decimal("0"),
            currency="EUR",
        )
        assert isinstance(result, Err)
        assert "party_a" in result.error

    def test_reject_empty_currency(self) -> None:
        result = CollateralAgreement.create(
            agreement_id="CSA-007",
            party_a="BANK-A",
            party_b="FUND-B",
            eligible_collateral=(CollateralType.CASH,),
            threshold_a=Decimal("0"),
            threshold_b=Decimal("0"),
            minimum_transfer_amount=Decimal("0"),
            currency="",
        )
        assert isinstance(result, Err)
        assert "currency" in result.error

    def test_frozen_and_immutable(self) -> None:
        csa = unwrap(CollateralAgreement.create(
            agreement_id="CSA-IMM",
            party_a="BANK-A",
            party_b="FUND-B",
            eligible_collateral=(CollateralType.CASH,),
            threshold_a=Decimal("0"),
            threshold_b=Decimal("0"),
            minimum_transfer_amount=Decimal("0"),
            currency="USD",
        ))
        with pytest.raises(AttributeError):
            csa.threshold_a = Decimal("999")  # type: ignore[misc]

    def test_zero_thresholds_accepted(self) -> None:
        result = CollateralAgreement.create(
            agreement_id="CSA-ZERO",
            party_a="BANK-A",
            party_b="FUND-B",
            eligible_collateral=(CollateralType.CASH,),
            threshold_a=Decimal("0"),
            threshold_b=Decimal("0"),
            minimum_transfer_amount=Decimal("0"),
            currency="USD",
        )
        assert isinstance(result, Ok)


# ---------------------------------------------------------------------------
# Margin call transaction
# ---------------------------------------------------------------------------


class TestMarginCallTransaction:
    def test_single_move_poster_to_caller(self) -> None:
        tx = unwrap(create_margin_call_transaction(
            caller_account="CALLER-COLLATERAL",
            poster_account="POSTER-COLLATERAL",
            collateral_unit="USD",
            quantity=Decimal("5000000"),
            tx_id="MC-001",
            timestamp=_TS,
        ))
        assert len(tx.moves) == 1
        move = tx.moves[0]
        assert move.source == "POSTER-COLLATERAL"
        assert move.destination == "CALLER-COLLATERAL"
        assert move.unit == "USD"
        assert move.quantity.value == Decimal("5000000")

    def test_conservation_via_engine(self) -> None:
        engine = _setup_engine()
        tx = unwrap(create_margin_call_transaction(
            caller_account="CALLER-COLLATERAL",
            poster_account="POSTER-COLLATERAL",
            collateral_unit="USD",
            quantity=Decimal("1000000"),
            tx_id="MC-002",
            timestamp=_TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert unwrap(result) == ExecuteResult.APPLIED
        assert engine.total_supply("USD") == Decimal(0)

    def test_zero_quantity_rejected(self) -> None:
        result = create_margin_call_transaction(
            caller_account="CALLER-COLLATERAL",
            poster_account="POSTER-COLLATERAL",
            collateral_unit="USD",
            quantity=Decimal("0"),
            tx_id="MC-003",
            timestamp=_TS,
        )
        assert isinstance(result, Err)
        assert result.error.code == "INVALID_QUANTITY"

    def test_negative_quantity_rejected(self) -> None:
        result = create_margin_call_transaction(
            caller_account="CALLER-COLLATERAL",
            poster_account="POSTER-COLLATERAL",
            collateral_unit="USD",
            quantity=Decimal("-100"),
            tx_id="MC-004",
            timestamp=_TS,
        )
        assert isinstance(result, Err)
        assert result.error.code == "INVALID_QUANTITY"

    def test_accepted_by_ledger_engine(self) -> None:
        engine = _setup_engine()
        tx = unwrap(create_margin_call_transaction(
            caller_account="CALLER-COLLATERAL",
            poster_account="POSTER-COLLATERAL",
            collateral_unit="GOVT-BOND-10Y",
            quantity=Decimal("500"),
            tx_id="MC-005",
            timestamp=_TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert unwrap(result) == ExecuteResult.APPLIED


# ---------------------------------------------------------------------------
# Collateral return transaction
# ---------------------------------------------------------------------------


class TestCollateralReturnTransaction:
    def test_single_move_returner_to_receiver(self) -> None:
        tx = unwrap(create_collateral_return_transaction(
            returner_account="RETURNER-COLLATERAL",
            receiver_account="RECEIVER-COLLATERAL",
            collateral_unit="EUR",
            quantity=Decimal("2000000"),
            tx_id="CR-001",
            timestamp=_TS,
        ))
        assert len(tx.moves) == 1
        move = tx.moves[0]
        assert move.source == "RETURNER-COLLATERAL"
        assert move.destination == "RECEIVER-COLLATERAL"
        assert move.unit == "EUR"
        assert move.quantity.value == Decimal("2000000")

    def test_conservation_via_engine(self) -> None:
        engine = _setup_engine()
        tx = unwrap(create_collateral_return_transaction(
            returner_account="RETURNER-COLLATERAL",
            receiver_account="RECEIVER-COLLATERAL",
            collateral_unit="EUR",
            quantity=Decimal("750000"),
            tx_id="CR-002",
            timestamp=_TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert unwrap(result) == ExecuteResult.APPLIED
        assert engine.total_supply("EUR") == Decimal(0)

    def test_zero_quantity_rejected(self) -> None:
        result = create_collateral_return_transaction(
            returner_account="RETURNER-COLLATERAL",
            receiver_account="RECEIVER-COLLATERAL",
            collateral_unit="EUR",
            quantity=Decimal("0"),
            tx_id="CR-003",
            timestamp=_TS,
        )
        assert isinstance(result, Err)
        assert result.error.code == "INVALID_QUANTITY"


# ---------------------------------------------------------------------------
# Collateral substitution transaction
# ---------------------------------------------------------------------------


class TestCollateralSubstitutionTransaction:
    def test_two_moves_old_returned_new_delivered(self) -> None:
        tx = unwrap(create_collateral_substitution_transaction(
            poster_account="POSTER-COLLATERAL",
            holder_account="HOLDER-COLLATERAL",
            old_collateral_unit="CORP-BOND-5Y",
            old_quantity=Decimal("1000"),
            new_collateral_unit="GOVT-BOND-10Y",
            new_quantity=Decimal("800"),
            tx_id="CS-001",
            timestamp=_TS,
        ))
        assert len(tx.moves) == 2
        # Move 1: old collateral returned (holder -> poster)
        return_move = tx.moves[0]
        assert return_move.source == "HOLDER-COLLATERAL"
        assert return_move.destination == "POSTER-COLLATERAL"
        assert return_move.unit == "CORP-BOND-5Y"
        assert return_move.quantity.value == Decimal("1000")
        # Move 2: new collateral delivered (poster -> holder)
        delivery_move = tx.moves[1]
        assert delivery_move.source == "POSTER-COLLATERAL"
        assert delivery_move.destination == "HOLDER-COLLATERAL"
        assert delivery_move.unit == "GOVT-BOND-10Y"
        assert delivery_move.quantity.value == Decimal("800")

    def test_conservation_both_units_via_engine(self) -> None:
        engine = _setup_engine()
        tx = unwrap(create_collateral_substitution_transaction(
            poster_account="POSTER-COLLATERAL",
            holder_account="HOLDER-COLLATERAL",
            old_collateral_unit="CORP-BOND-5Y",
            old_quantity=Decimal("500"),
            new_collateral_unit="GOVT-BOND-10Y",
            new_quantity=Decimal("400"),
            tx_id="CS-002",
            timestamp=_TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert unwrap(result) == ExecuteResult.APPLIED
        assert engine.total_supply("CORP-BOND-5Y") == Decimal(0)
        assert engine.total_supply("GOVT-BOND-10Y") == Decimal(0)

    def test_zero_old_quantity_rejected(self) -> None:
        result = create_collateral_substitution_transaction(
            poster_account="POSTER-COLLATERAL",
            holder_account="HOLDER-COLLATERAL",
            old_collateral_unit="CORP-BOND-5Y",
            old_quantity=Decimal("0"),
            new_collateral_unit="GOVT-BOND-10Y",
            new_quantity=Decimal("400"),
            tx_id="CS-003",
            timestamp=_TS,
        )
        assert isinstance(result, Err)
        assert result.error.code == "INVALID_QUANTITY"

    def test_zero_new_quantity_rejected(self) -> None:
        result = create_collateral_substitution_transaction(
            poster_account="POSTER-COLLATERAL",
            holder_account="HOLDER-COLLATERAL",
            old_collateral_unit="CORP-BOND-5Y",
            old_quantity=Decimal("400"),
            new_collateral_unit="GOVT-BOND-10Y",
            new_quantity=Decimal("0"),
            tx_id="CS-004",
            timestamp=_TS,
        )
        assert isinstance(result, Err)
        assert result.error.code == "INVALID_QUANTITY"

    def test_accepted_by_ledger_engine(self) -> None:
        engine = _setup_engine()
        tx = unwrap(create_collateral_substitution_transaction(
            poster_account="POSTER-COLLATERAL",
            holder_account="HOLDER-COLLATERAL",
            old_collateral_unit="EQUITY-AAPL",
            old_quantity=Decimal("100"),
            new_collateral_unit="USD",
            new_quantity=Decimal("15000"),
            tx_id="CS-005",
            timestamp=_TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert unwrap(result) == ExecuteResult.APPLIED


# ---------------------------------------------------------------------------
# Hypothesis: random collateral amounts -> conservation
# ---------------------------------------------------------------------------


class TestCollateralConservationHypothesis:
    @given(
        amounts=st.lists(
            st.decimals(
                min_value=Decimal("0.01"),
                max_value=Decimal("100000000"),
                places=2,
                allow_nan=False,
                allow_infinity=False,
            ),
            min_size=1,
            max_size=10,
        ),
    )
    @settings(max_examples=200)
    def test_margin_call_conservation_random(self, amounts: list[Decimal]) -> None:
        """sigma(collateral_unit) == 0 after any number of margin calls."""
        engine = _setup_engine()
        for i, amt in enumerate(amounts):
            tx = unwrap(create_margin_call_transaction(
                caller_account="CALLER-COLLATERAL",
                poster_account="POSTER-COLLATERAL",
                collateral_unit="USD-CASH",
                quantity=amt,
                tx_id=f"MC-HYP-{i}",
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
    def test_return_conservation_property(self, quantity: Decimal) -> None:
        """sigma(collateral_unit) == 0 after return for any quantity."""
        engine = _setup_engine()
        tx = unwrap(create_collateral_return_transaction(
            returner_account="RETURNER-COLLATERAL",
            receiver_account="RECEIVER-COLLATERAL",
            collateral_unit="EUR-CASH",
            quantity=quantity,
            tx_id="RET-HYP",
            timestamp=_TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert engine.total_supply("EUR-CASH") == Decimal(0)

    @given(
        old_qty=st.decimals(
            min_value=Decimal("1"),
            max_value=Decimal("10000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
        new_qty=st.decimals(
            min_value=Decimal("1"),
            max_value=Decimal("10000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_substitution_conservation_property(
        self, old_qty: Decimal, new_qty: Decimal,
    ) -> None:
        """sigma(old)==0 and sigma(new)==0 after substitution."""
        engine = _setup_engine()
        tx = unwrap(create_collateral_substitution_transaction(
            poster_account="POSTER-COLLATERAL",
            holder_account="HOLDER-COLLATERAL",
            old_collateral_unit="CORP-BOND",
            old_quantity=old_qty,
            new_collateral_unit="GOVT-BOND",
            new_quantity=new_qty,
            tx_id="SUB-HYP",
            timestamp=_TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert engine.total_supply("CORP-BOND") == Decimal(0)
        assert engine.total_supply("GOVT-BOND") == Decimal(0)

    @given(
        quantity=st.decimals(
            min_value=Decimal("1"),
            max_value=Decimal("10000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_margin_call_return_roundtrip_property(
        self, quantity: Decimal,
    ) -> None:
        """Post then return same quantity: net positions are zero."""
        engine = _setup_engine()
        mc_tx = unwrap(create_margin_call_transaction(
            "CALLER-COLLATERAL", "POSTER-COLLATERAL",
            "GBP", quantity, "MC-RT-HYP", _TS,
        ))
        unwrap(engine.execute(mc_tx))
        ret_tx = unwrap(create_collateral_return_transaction(
            "CALLER-COLLATERAL", "POSTER-COLLATERAL",
            "GBP", quantity, "RET-RT-HYP", _TS,
        ))
        unwrap(engine.execute(ret_tx))
        assert engine.get_balance("CALLER-COLLATERAL", "GBP") == Decimal(0)
        assert engine.get_balance("POSTER-COLLATERAL", "GBP") == Decimal(0)


# ---------------------------------------------------------------------------
# Full lifecycle: margin call -> return -> substitution
# ---------------------------------------------------------------------------


class TestCollateralLifecycle:
    def test_margin_call_then_return_balances(self) -> None:
        """Post collateral, then return it -- net positions zero."""
        engine = _setup_engine()

        # 1. Margin call: poster delivers USD to caller
        mc_tx = unwrap(create_margin_call_transaction(
            caller_account="CALLER-COLLATERAL",
            poster_account="POSTER-COLLATERAL",
            collateral_unit="USD",
            quantity=Decimal("5000000"),
            tx_id="LC-MC-001",
            timestamp=_TS,
        ))
        unwrap(engine.execute(mc_tx))
        assert engine.get_balance("CALLER-COLLATERAL", "USD") == Decimal("5000000")
        assert engine.get_balance("POSTER-COLLATERAL", "USD") == Decimal("-5000000")

        # 2. Return: caller returns all USD to poster
        ret_tx = unwrap(create_collateral_return_transaction(
            returner_account="CALLER-COLLATERAL",
            receiver_account="POSTER-COLLATERAL",
            collateral_unit="USD",
            quantity=Decimal("5000000"),
            tx_id="LC-RET-001",
            timestamp=_TS,
        ))
        unwrap(engine.execute(ret_tx))
        assert engine.get_balance("CALLER-COLLATERAL", "USD") == Decimal(0)
        assert engine.get_balance("POSTER-COLLATERAL", "USD") == Decimal(0)
        assert engine.total_supply("USD") == Decimal(0)

    def test_margin_call_then_substitution(self) -> None:
        """Post collateral, then substitute -- old returned, new delivered."""
        engine = _setup_engine()

        # 1. Margin call: poster delivers corp bonds to holder
        mc_tx = unwrap(create_margin_call_transaction(
            caller_account="HOLDER-COLLATERAL",
            poster_account="POSTER-COLLATERAL",
            collateral_unit="CORP-BOND-5Y",
            quantity=Decimal("1000"),
            tx_id="LC2-MC-001",
            timestamp=_TS,
        ))
        unwrap(engine.execute(mc_tx))
        assert engine.get_balance("HOLDER-COLLATERAL", "CORP-BOND-5Y") == Decimal("1000")

        # 2. Substitution: swap corp bonds for govt bonds
        sub_tx = unwrap(create_collateral_substitution_transaction(
            poster_account="POSTER-COLLATERAL",
            holder_account="HOLDER-COLLATERAL",
            old_collateral_unit="CORP-BOND-5Y",
            old_quantity=Decimal("1000"),
            new_collateral_unit="GOVT-BOND-10Y",
            new_quantity=Decimal("900"),
            tx_id="LC2-SUB-001",
            timestamp=_TS,
        ))
        unwrap(engine.execute(sub_tx))

        # Old collateral returned to poster: net zero
        assert engine.get_balance("HOLDER-COLLATERAL", "CORP-BOND-5Y") == Decimal(0)
        assert engine.get_balance("POSTER-COLLATERAL", "CORP-BOND-5Y") == Decimal(0)
        # New collateral delivered to holder
        assert engine.get_balance("HOLDER-COLLATERAL", "GOVT-BOND-10Y") == Decimal("900")
        assert engine.get_balance("POSTER-COLLATERAL", "GOVT-BOND-10Y") == Decimal("-900")
        # Conservation holds for both
        assert engine.total_supply("CORP-BOND-5Y") == Decimal(0)
        assert engine.total_supply("GOVT-BOND-10Y") == Decimal(0)


# ---------------------------------------------------------------------------
# compute_margin_call (Phase 5 D3)
# ---------------------------------------------------------------------------


class TestComputeMarginCall:
    """compute_margin_call — pure margin call amount computation."""

    def test_above_threshold_and_mta(self) -> None:
        result = compute_margin_call(
            current_exposure=Decimal("10000000"),
            threshold=Decimal("5000000"),
            minimum_transfer_amount=Decimal("500000"),
        )
        assert isinstance(result, Ok)
        assert unwrap(result) == Decimal("5000000")

    def test_below_threshold_returns_zero(self) -> None:
        result = compute_margin_call(
            current_exposure=Decimal("3000000"),
            threshold=Decimal("5000000"),
            minimum_transfer_amount=Decimal("500000"),
        )
        assert isinstance(result, Ok)
        assert unwrap(result) == Decimal("0")

    def test_below_mta_returns_zero(self) -> None:
        result = compute_margin_call(
            current_exposure=Decimal("5200000"),
            threshold=Decimal("5000000"),
            minimum_transfer_amount=Decimal("500000"),
        )
        assert isinstance(result, Ok)
        assert unwrap(result) == Decimal("0")

    def test_exactly_at_threshold_returns_zero(self) -> None:
        result = compute_margin_call(
            current_exposure=Decimal("5000000"),
            threshold=Decimal("5000000"),
            minimum_transfer_amount=Decimal("500000"),
        )
        assert isinstance(result, Ok)
        assert unwrap(result) == Decimal("0")

    def test_negative_exposure_err(self) -> None:
        result = compute_margin_call(
            current_exposure=Decimal("-1"),
            threshold=Decimal("5000000"),
            minimum_transfer_amount=Decimal("500000"),
        )
        assert isinstance(result, Err)

    def test_negative_threshold_err(self) -> None:
        result = compute_margin_call(
            current_exposure=Decimal("10000000"),
            threshold=Decimal("-1"),
            minimum_transfer_amount=Decimal("500000"),
        )
        assert isinstance(result, Err)

    def test_negative_mta_err(self) -> None:
        result = compute_margin_call(
            current_exposure=Decimal("10000000"),
            threshold=Decimal("5000000"),
            minimum_transfer_amount=Decimal("-1"),
        )
        assert isinstance(result, Err)

    def test_zero_threshold_returns_exposure(self) -> None:
        result = compute_margin_call(
            current_exposure=Decimal("1000000"),
            threshold=Decimal("0"),
            minimum_transfer_amount=Decimal("0"),
        )
        assert isinstance(result, Ok)
        assert unwrap(result) == Decimal("1000000")
