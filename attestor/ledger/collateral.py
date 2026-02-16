"""Collateral management -- margin calls, returns, substitutions.

All functions produce Transaction objects that the LedgerEngine executes.
Conservation: sigma(collateral_unit) unchanged after every transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import final

from attestor.core.errors import ValidationError
from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, Ok
from attestor.core.types import UtcDatetime
from attestor.ledger._validation import create_move, create_tx, parse_positive
from attestor.ledger.transactions import Transaction

# ---------------------------------------------------------------------------
# CollateralType enum
# ---------------------------------------------------------------------------


class CollateralType(Enum):
    """Eligible collateral asset classes under CSA/ISDA agreements."""

    CASH = "CASH"
    GOVERNMENT_BOND = "GOVERNMENT_BOND"
    CORPORATE_BOND = "CORPORATE_BOND"
    EQUITY = "EQUITY"


# ---------------------------------------------------------------------------
# CollateralAgreement
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class CollateralAgreement:
    """CSA/ISDA collateral agreement parameters.

    Invariants enforced at construction:
    - All string fields non-empty
    - threshold_a >= 0, threshold_b >= 0, minimum_transfer_amount >= 0
    - eligible_collateral non-empty
    """

    agreement_id: NonEmptyStr
    party_a: NonEmptyStr
    party_b: NonEmptyStr
    eligible_collateral: tuple[CollateralType, ...]
    threshold_a: Decimal          # >= 0
    threshold_b: Decimal          # >= 0
    minimum_transfer_amount: Decimal  # >= 0
    currency: NonEmptyStr

    @staticmethod
    def create(
        agreement_id: str,
        party_a: str,
        party_b: str,
        eligible_collateral: tuple[CollateralType, ...],
        threshold_a: Decimal,
        threshold_b: Decimal,
        minimum_transfer_amount: Decimal,
        currency: str,
    ) -> Ok[CollateralAgreement] | Err[str]:
        """Validated construction of a CollateralAgreement.

        Rejects: empty strings, negative thresholds/MTA, empty eligible collateral.
        """
        match NonEmptyStr.parse(agreement_id):
            case Err(e):
                return Err(f"agreement_id: {e}")
            case Ok(aid):
                pass

        match NonEmptyStr.parse(party_a):
            case Err(e):
                return Err(f"party_a: {e}")
            case Ok(pa):
                pass

        match NonEmptyStr.parse(party_b):
            case Err(e):
                return Err(f"party_b: {e}")
            case Ok(pb):
                pass

        match NonEmptyStr.parse(currency):
            case Err(e):
                return Err(f"currency: {e}")
            case Ok(cur):
                pass

        if not eligible_collateral:
            return Err("eligible_collateral must be non-empty")

        if threshold_a < 0:
            return Err(f"threshold_a must be >= 0, got {threshold_a}")

        if threshold_b < 0:
            return Err(f"threshold_b must be >= 0, got {threshold_b}")

        if minimum_transfer_amount < 0:
            return Err(
                f"minimum_transfer_amount must be >= 0, got {minimum_transfer_amount}"
            )

        return Ok(CollateralAgreement(
            agreement_id=aid,
            party_a=pa,
            party_b=pb,
            eligible_collateral=eligible_collateral,
            threshold_a=threshold_a,
            threshold_b=threshold_b,
            minimum_transfer_amount=minimum_transfer_amount,
            currency=cur,
        ))


# ---------------------------------------------------------------------------
# Margin call computation (pure)
# ---------------------------------------------------------------------------


def compute_margin_call(
    current_exposure: Decimal,
    threshold: Decimal,
    minimum_transfer_amount: Decimal,
) -> Ok[Decimal] | Err[str]:
    """Compute margin call amount (pure, no ledger side effects).

    call_amount = max(0, current_exposure - threshold)
    If call_amount > 0 but < minimum_transfer_amount, returns 0 (below MTA).

    Validates: current_exposure >= 0, threshold >= 0, MTA >= 0.
    """
    if not isinstance(current_exposure, Decimal) or not current_exposure.is_finite():
        return Err(f"current_exposure must be finite Decimal, got {current_exposure}")
    if current_exposure < Decimal("0"):
        return Err(f"current_exposure must be >= 0, got {current_exposure}")
    if not isinstance(threshold, Decimal) or not threshold.is_finite():
        return Err(f"threshold must be finite Decimal, got {threshold}")
    if threshold < Decimal("0"):
        return Err(f"threshold must be >= 0, got {threshold}")
    if not isinstance(minimum_transfer_amount, Decimal) or not minimum_transfer_amount.is_finite():
        return Err(
            f"minimum_transfer_amount must be finite Decimal, got {minimum_transfer_amount}"
        )
    if minimum_transfer_amount < Decimal("0"):
        return Err(f"minimum_transfer_amount must be >= 0, got {minimum_transfer_amount}")

    raw = current_exposure - threshold
    if raw <= Decimal("0"):
        return Ok(Decimal("0"))
    if raw < minimum_transfer_amount:
        return Ok(Decimal("0"))
    return Ok(raw)


# ---------------------------------------------------------------------------
# Margin call transaction
# ---------------------------------------------------------------------------


def create_margin_call_transaction(
    caller_account: str,
    poster_account: str,
    collateral_unit: str,
    quantity: Decimal,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Book collateral delivery after margin call.

    One Move: poster -> caller, unit = collateral_unit, quantity = quantity.
    Conservation: sigma(collateral_unit) unchanged.
    """
    _fn = "create_margin_call_transaction"
    _src = f"ledger.collateral.{_fn}"

    match parse_positive(quantity, "quantity", _fn, timestamp, _src):
        case Err(e):
            return Err(e)
        case Ok(qty_pd):
            pass

    match create_move(
        poster_account, caller_account,
        collateral_unit, qty_pd, tx_id, _fn, timestamp, _src,
    ):
        case Err(e):
            return Err(e)
        case Ok(collateral_move):
            pass

    return create_tx(tx_id, (collateral_move,), timestamp, _fn, _src)


# ---------------------------------------------------------------------------
# Collateral return transaction
# ---------------------------------------------------------------------------


def create_collateral_return_transaction(
    returner_account: str,
    receiver_account: str,
    collateral_unit: str,
    quantity: Decimal,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Book collateral return.

    One Move: returner -> receiver, unit = collateral_unit, quantity = quantity.
    Conservation: sigma(collateral_unit) unchanged.
    """
    _fn = "create_collateral_return_transaction"
    _src = f"ledger.collateral.{_fn}"

    match parse_positive(quantity, "quantity", _fn, timestamp, _src):
        case Err(e):
            return Err(e)
        case Ok(qty_pd):
            pass

    match create_move(
        returner_account, receiver_account,
        collateral_unit, qty_pd, tx_id, _fn, timestamp, _src,
    ):
        case Err(e):
            return Err(e)
        case Ok(collateral_move):
            pass

    return create_tx(tx_id, (collateral_move,), timestamp, _fn, _src)


# ---------------------------------------------------------------------------
# Collateral substitution transaction
# ---------------------------------------------------------------------------


def create_collateral_substitution_transaction(
    poster_account: str,
    holder_account: str,
    old_collateral_unit: str,
    old_quantity: Decimal,
    new_collateral_unit: str,
    new_quantity: Decimal,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Book collateral substitution.

    Move 1: old collateral holder -> poster (return old)
    Move 2: new collateral poster -> holder (deliver new)
    Conservation: sigma(old_collateral_unit) and sigma(new_collateral_unit) unchanged.
    """
    _fn = "create_collateral_substitution_transaction"
    _src = f"ledger.collateral.{_fn}"

    match parse_positive(old_quantity, "old_quantity", _fn, timestamp, _src):
        case Err(e):
            return Err(e)
        case Ok(old_qty_pd):
            pass

    match parse_positive(new_quantity, "new_quantity", _fn, timestamp, _src):
        case Err(e):
            return Err(e)
        case Ok(new_qty_pd):
            pass

    # Move 1: return old collateral (holder -> poster)
    match create_move(
        holder_account, poster_account,
        old_collateral_unit, old_qty_pd, tx_id,
        _fn, timestamp, _src, label="old move",
    ):
        case Err(e):
            return Err(e)
        case Ok(return_move):
            pass

    # Move 2: deliver new collateral (poster -> holder)
    match create_move(
        poster_account, holder_account,
        new_collateral_unit, new_qty_pd, tx_id,
        _fn, timestamp, _src, label="new move",
    ):
        case Err(e):
            return Err(e)
        case Ok(delivery_move):
            pass

    return create_tx(tx_id, (return_move, delivery_move), timestamp, _fn, _src)
