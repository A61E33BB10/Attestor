"""Collateral management -- margin calls, returns, substitutions.

All functions produce Transaction objects that the LedgerEngine executes.
Conservation: sigma(collateral_unit) unchanged after every transaction.

Phase E additions: AssetClassEnum, Haircut, CollateralValuationTreatment,
ConcentrationLimit, StandardizedSchedule, MarginCallResponseEnum,
MarginCallIssuance, MarginCallResponse.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import final

from attestor.core.errors import ValidationError
from attestor.core.money import Money, NonEmptyStr, PositiveDecimal
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
# Phase E: Enums
# ---------------------------------------------------------------------------


class AssetClassEnum(Enum):
    """BCBS/IOSCO standardized schedule asset classes.

    CDM: StandardizedScheduleAssetClassEnum (5 of 5 values).
    """

    INTEREST_RATES = "INTEREST_RATES"
    CREDIT = "CREDIT"
    FX = "FX"
    EQUITY = "EQUITY"
    COMMODITY = "COMMODITY"


class MarginCallResponseEnum(Enum):
    """Response type for a margin call.

    CDM: conceptual (AGREE vs DISPUTE covers standard workflow).
    """

    AGREE = "AGREE"
    DISPUTE = "DISPUTE"


# ---------------------------------------------------------------------------
# Phase E: Haircut and valuation types
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class Haircut:
    """Collateral valuation haircut.

    CDM: haircutPercentage in CollateralValuationTreatment.
    Invariant: value in [0, 1) — 0 means no haircut, 0.50 means 50% haircut.
    A value of 1.0 (100%) would mean worthless collateral, which is excluded.
    """

    value: Decimal

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, Decimal)
            or not self.value.is_finite()
        ):
            raise TypeError(
                f"Haircut.value must be finite Decimal, got {self.value!r}"
            )
        if self.value < 0 or self.value >= 1:
            raise TypeError(
                "Haircut.value must be in [0, 1), "
                f"got {self.value}"
            )


@final
@dataclass(frozen=True, slots=True)
class CollateralValuationTreatment:
    """Haircuts and adjustments for collateral valuation.

    CDM: CollateralValuationTreatment = haircutPercentage +
    marginPercentage + fxHaircutPercentage.
    """

    haircut: Haircut
    margin_percentage: Decimal | None = None
    fx_haircut: Haircut | None = None

    def __post_init__(self) -> None:
        if self.margin_percentage is not None:
            if (
                not isinstance(self.margin_percentage, Decimal)
                or not self.margin_percentage.is_finite()
            ):
                raise TypeError(
                    "CollateralValuationTreatment.margin_percentage "
                    "must be finite Decimal, "
                    f"got {self.margin_percentage!r}"
                )
            if self.margin_percentage < 0:
                raise TypeError(
                    "CollateralValuationTreatment.margin_percentage "
                    f"must be >= 0, got {self.margin_percentage}"
                )


@final
@dataclass(frozen=True, slots=True)
class ConcentrationLimit:
    """Maximum concentration of a single collateral type in a portfolio.

    CDM: ConcentrationLimit conceptual (eligibility criteria).
    Invariant: limit_fraction in (0, 1].
    """

    collateral_type: CollateralType
    limit_fraction: Decimal

    def __post_init__(self) -> None:
        if (
            not isinstance(self.limit_fraction, Decimal)
            or not self.limit_fraction.is_finite()
        ):
            raise TypeError(
                "ConcentrationLimit.limit_fraction must be finite "
                f"Decimal, got {self.limit_fraction!r}"
            )
        if self.limit_fraction <= 0 or self.limit_fraction > 1:
            raise TypeError(
                "ConcentrationLimit.limit_fraction must be in (0, 1], "
                f"got {self.limit_fraction}"
            )


# ---------------------------------------------------------------------------
# Phase E: Standardized Schedule (UMR initial margin)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class StandardizedSchedule:
    """BCBS/IOSCO standardized schedule for initial margin calculation.

    CDM: StandardizedSchedule = assetClass + productClass + notional +
    notionalCurrency + durationInYears.
    Invariant: duration_in_years > 0 when present.
    """

    asset_class: AssetClassEnum
    product_class: NonEmptyStr
    notional: PositiveDecimal
    currency: NonEmptyStr
    duration_in_years: Decimal | None = None

    def __post_init__(self) -> None:
        if self.duration_in_years is not None:
            if (
                not isinstance(self.duration_in_years, Decimal)
                or not self.duration_in_years.is_finite()
            ):
                raise TypeError(
                    "StandardizedSchedule.duration_in_years must be "
                    f"finite Decimal, got {self.duration_in_years!r}"
                )
            if self.duration_in_years <= 0:
                raise TypeError(
                    "StandardizedSchedule.duration_in_years must be "
                    f"> 0, got {self.duration_in_years}"
                )


# ---------------------------------------------------------------------------
# Phase E: Margin call workflow types
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class MarginCallIssuance:
    """Structured margin call demand.

    CDM: conceptual MarginCallInstruction.
    Represents a formal request for collateral delivery.
    Invariant: call_amount must be positive.
    """

    agreement_id: NonEmptyStr
    call_amount: Money
    call_date: date
    demanding_party: NonEmptyStr
    collateral_type: CollateralType | None = None

    def __post_init__(self) -> None:
        if self.call_amount.amount <= 0:
            raise TypeError(
                "MarginCallIssuance: call_amount must be positive, "
                f"got {self.call_amount.amount}"
            )


@final
@dataclass(frozen=True, slots=True)
class MarginCallResponse:
    """Response to a margin call.

    CDM: conceptual MarginCallResponse.
    Invariants:
    - agreed_amount currency must match issuance.call_amount currency
    - agreed_amount must be non-negative
    - response_date >= issuance.call_date
    - AGREE: agreed_amount == issuance.call_amount
    - DISPUTE: agreed_amount < issuance.call_amount
    """

    issuance: MarginCallIssuance
    response: MarginCallResponseEnum
    agreed_amount: Money
    response_date: date

    def __post_init__(self) -> None:
        if (
            self.agreed_amount.currency
            != self.issuance.call_amount.currency
        ):
            raise TypeError(
                "MarginCallResponse: agreed_amount currency must "
                "match issuance.call_amount currency; "
                f"got {self.agreed_amount.currency.value} vs "
                f"{self.issuance.call_amount.currency.value}"
            )
        if self.agreed_amount.amount < 0:
            raise TypeError(
                "MarginCallResponse: agreed_amount must be "
                f"non-negative, got {self.agreed_amount.amount}"
            )
        if self.response_date < self.issuance.call_date:
            raise TypeError(
                "MarginCallResponse: response_date must be >= "
                "issuance.call_date; "
                f"got {self.response_date} < {self.issuance.call_date}"
            )
        if (
            self.response == MarginCallResponseEnum.AGREE
            and self.agreed_amount != self.issuance.call_amount
        ):
            raise TypeError(
                "MarginCallResponse: when response is AGREE, "
                "agreed_amount must equal issuance.call_amount; "
                f"got {self.agreed_amount} vs "
                f"{self.issuance.call_amount}"
            )
        if (
            self.response == MarginCallResponseEnum.DISPUTE
            and self.agreed_amount.amount
            >= self.issuance.call_amount.amount
        ):
            raise TypeError(
                "MarginCallResponse: when response is DISPUTE, "
                "agreed_amount must be less than "
                "issuance.call_amount; "
                f"got {self.agreed_amount.amount} >= "
                f"{self.issuance.call_amount.amount}"
            )


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

    def __post_init__(self) -> None:
        if not self.eligible_collateral:
            raise TypeError("CollateralAgreement: eligible_collateral must be non-empty")
        if self.threshold_a < 0:
            raise TypeError(
                f"CollateralAgreement: threshold_a must be >= 0, "
                f"got {self.threshold_a}"
            )
        if self.threshold_b < 0:
            raise TypeError(
                f"CollateralAgreement: threshold_b must be >= 0, "
                f"got {self.threshold_b}"
            )
        if self.minimum_transfer_amount < 0:
            raise TypeError(
                f"CollateralAgreement: minimum_transfer_amount must be >= 0, "
                f"got {self.minimum_transfer_amount}"
            )

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
