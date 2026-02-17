"""CDS and Swaption payout spec types.

All types are @final @dataclass(frozen=True, slots=True). Smart constructors
return Ok | Err for validated creation.

Enums (CreditEventType, SeniorityLevel, ProtectionSide, SwaptionType) live in
derivative_types.py to avoid circular imports (this module imports SettlementType
from there).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import final

from attestor.core.money import NonEmptyStr, NonNegativeDecimal, PositiveDecimal
from attestor.core.result import Err, Ok
from attestor.core.types import PayerReceiver
from attestor.instrument.derivative_types import SettlementType, SwaptionType
from attestor.instrument.fx_types import (
    DayCountConvention,
    IRSwapPayoutSpec,
    PaymentFrequency,
)

# ---------------------------------------------------------------------------
# CDS PayoutSpec
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class CDSPayoutSpec:
    """Credit default swap payout specification.

    Represents a single-name CDS with contractual spread, recovery rate,
    and standard ISDA conventions (ACT/360, quarterly premium payments).

    CDM: CreditDefaultPayout + payerReceiver.
    payer = protection buyer (pays premium), receiver = protection seller.
    """

    payer_receiver: PayerReceiver
    reference_entity: NonEmptyStr
    notional: PositiveDecimal
    spread: Decimal  # contractual spread as decimal (0.01 = 100bps)
    currency: NonEmptyStr
    effective_date: date
    maturity_date: date
    payment_frequency: PaymentFrequency  # typically QUARTERLY
    day_count: DayCountConvention  # ACT_360 per ISDA
    recovery_rate: Decimal  # assumed recovery (typically 0.4)

    def __post_init__(self) -> None:
        if self.spread <= 0:
            raise TypeError(f"CDSPayoutSpec.spread must be > 0, got {self.spread}")
        if self.effective_date >= self.maturity_date:
            raise TypeError(
                f"CDSPayoutSpec: effective_date ({self.effective_date}) "
                f"must be < maturity_date ({self.maturity_date})"
            )
        if self.recovery_rate < 0 or self.recovery_rate >= 1:
            raise TypeError(
                f"CDSPayoutSpec.recovery_rate must be in [0, 1), got {self.recovery_rate}"
            )

    @staticmethod
    def create(
        reference_entity: str,
        notional: Decimal,
        spread: Decimal,
        currency: str,
        effective_date: date,
        maturity_date: date,
        payment_frequency: PaymentFrequency,
        day_count: DayCountConvention,
        recovery_rate: Decimal,
        payer_receiver: PayerReceiver,
    ) -> Ok[CDSPayoutSpec] | Err[str]:
        """Create a CDS payout spec with full validation.

        payer_receiver: payer = protection buyer, receiver = protection seller.
        """
        match NonEmptyStr.parse(reference_entity):
            case Err(e):
                return Err(f"CDSPayoutSpec.reference_entity: {e}")
            case Ok(ref):
                pass
        match PositiveDecimal.parse(notional):
            case Err(e):
                return Err(f"CDSPayoutSpec.notional: {e}")
            case Ok(n):
                pass
        if spread <= 0:
            return Err(
                f"CDSPayoutSpec.spread must be > 0, got {spread}"
            )
        match NonEmptyStr.parse(currency):
            case Err(e):
                return Err(f"CDSPayoutSpec.currency: {e}")
            case Ok(cur):
                pass
        if effective_date >= maturity_date:
            return Err(
                f"CDSPayoutSpec: effective_date ({effective_date}) "
                f"must be < maturity_date ({maturity_date})"
            )
        if recovery_rate < 0 or recovery_rate >= 1:
            return Err(
                f"CDSPayoutSpec.recovery_rate must be in [0, 1), got {recovery_rate}"
            )
        return Ok(CDSPayoutSpec(
            payer_receiver=payer_receiver,
            reference_entity=ref, notional=n, spread=spread,
            currency=cur, effective_date=effective_date,
            maturity_date=maturity_date, payment_frequency=payment_frequency,
            day_count=day_count, recovery_rate=recovery_rate,
        ))


# ---------------------------------------------------------------------------
# Swaption PayoutSpec
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class SwaptionPayoutSpec:
    """Interest rate swaption payout specification.

    Represents the right (but not obligation) to enter an IRS at a given
    strike rate on the exercise date.

    CDM: OptionPayout + payerReceiver.
    payer = option buyer, receiver = option seller (writer).
    """

    payer_receiver: PayerReceiver
    swaption_type: SwaptionType
    strike: NonNegativeDecimal  # fixed rate K (zero-strike allowed for total return)
    exercise_date: date
    underlying_swap: IRSwapPayoutSpec  # the IRS that exercise creates
    settlement_type: SettlementType  # PHYSICAL or CASH
    currency: NonEmptyStr
    notional: PositiveDecimal

    def __post_init__(self) -> None:
        if self.exercise_date > self.underlying_swap.start_date:
            raise TypeError(
                f"SwaptionPayoutSpec: exercise_date ({self.exercise_date}) "
                f"must be <= underlying_swap.start_date ({self.underlying_swap.start_date})"
            )

    @staticmethod
    def create(
        swaption_type: SwaptionType,
        strike: Decimal,
        exercise_date: date,
        underlying_swap: IRSwapPayoutSpec,
        settlement_type: SettlementType,
        currency: str,
        notional: Decimal,
        payer_receiver: PayerReceiver,
    ) -> Ok[SwaptionPayoutSpec] | Err[str]:
        """Create a swaption payout spec with full validation.

        payer_receiver: payer = option buyer, receiver = option seller.
        """
        match NonNegativeDecimal.parse(strike):
            case Err(e):
                return Err(f"SwaptionPayoutSpec.strike: {e}")
            case Ok(s):
                pass
        if exercise_date > underlying_swap.start_date:
            return Err(
                f"SwaptionPayoutSpec: exercise_date ({exercise_date}) "
                f"must be <= underlying_swap.start_date ({underlying_swap.start_date})"
            )
        match NonEmptyStr.parse(currency):
            case Err(e):
                return Err(f"SwaptionPayoutSpec.currency: {e}")
            case Ok(cur):
                pass
        match PositiveDecimal.parse(notional):
            case Err(e):
                return Err(f"SwaptionPayoutSpec.notional: {e}")
            case Ok(n):
                pass
        return Ok(SwaptionPayoutSpec(
            payer_receiver=payer_receiver,
            swaption_type=swaption_type, strike=s,
            exercise_date=exercise_date, underlying_swap=underlying_swap,
            settlement_type=settlement_type, currency=cur, notional=n,
        ))
