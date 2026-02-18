"""FX and IRS instrument types — payout specs, enums, and gateway detail types.

All types are @final @dataclass(frozen=True, slots=True). Smart constructors
return Ok | Err for validated creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import final

from attestor.core.money import CurrencyPair, NonEmptyStr, PositiveDecimal
from attestor.core.result import Err, Ok
from attestor.core.types import (
    CalculationPeriodDates,
    PayerReceiver,
    PaymentDates,
)
from attestor.core.types import (
    DayCountConvention as DayCountConvention,
)
from attestor.instrument.derivative_types import SettlementTypeEnum
from attestor.instrument.rate_spec import StubPeriod
from attestor.oracle.observable import (
    FloatingRateCalculationParameters,
    FloatingRateIndex,
    ResetDates,
)


class PaymentFrequency(Enum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    SEMI_ANNUAL = "SEMI_ANNUAL"
    ANNUAL = "ANNUAL"


class SwapLegType(Enum):
    FIXED = "FIXED"
    FLOAT = "FLOAT"


# ---------------------------------------------------------------------------
# FX PayoutSpecs
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class FXSpotPayoutSpec:
    """FX spot payout: exchange base_notional of base currency for quote amount."""

    currency_pair: CurrencyPair
    base_notional: PositiveDecimal
    settlement_type: SettlementTypeEnum
    currency: NonEmptyStr  # settlement currency (quote leg)

    @staticmethod
    def create(
        currency_pair: str,
        base_notional: Decimal,
        currency: str,
        settlement_type: SettlementTypeEnum = SettlementTypeEnum.PHYSICAL,
    ) -> Ok[FXSpotPayoutSpec] | Err[str]:
        match CurrencyPair.parse(currency_pair):
            case Err(e):
                return Err(f"FXSpotPayoutSpec.currency_pair: {e}")
            case Ok(cp):
                pass
        match PositiveDecimal.parse(base_notional):
            case Err(e):
                return Err(f"FXSpotPayoutSpec.base_notional: {e}")
            case Ok(bn):
                pass
        match NonEmptyStr.parse(currency):
            case Err(e):
                return Err(f"FXSpotPayoutSpec.currency: {e}")
            case Ok(cur):
                pass
        return Ok(FXSpotPayoutSpec(
            currency_pair=cp, base_notional=bn,
            settlement_type=settlement_type, currency=cur,
        ))


@final
@dataclass(frozen=True, slots=True)
class FXForwardPayoutSpec:
    """FX forward: exchange at agreed forward rate on future date."""

    currency_pair: CurrencyPair
    base_notional: PositiveDecimal
    forward_rate: PositiveDecimal
    settlement_date: date
    settlement_type: SettlementTypeEnum
    currency: NonEmptyStr

    @staticmethod
    def create(
        currency_pair: str,
        base_notional: Decimal,
        forward_rate: Decimal,
        settlement_date: date,
        currency: str,
        settlement_type: SettlementTypeEnum = SettlementTypeEnum.PHYSICAL,
    ) -> Ok[FXForwardPayoutSpec] | Err[str]:
        match CurrencyPair.parse(currency_pair):
            case Err(e):
                return Err(f"FXForwardPayoutSpec.currency_pair: {e}")
            case Ok(cp):
                pass
        match PositiveDecimal.parse(base_notional):
            case Err(e):
                return Err(f"FXForwardPayoutSpec.base_notional: {e}")
            case Ok(bn):
                pass
        match PositiveDecimal.parse(forward_rate):
            case Err(e):
                return Err(f"FXForwardPayoutSpec.forward_rate: {e}")
            case Ok(fr):
                pass
        match NonEmptyStr.parse(currency):
            case Err(e):
                return Err(f"FXForwardPayoutSpec.currency: {e}")
            case Ok(cur):
                pass
        return Ok(FXForwardPayoutSpec(
            currency_pair=cp, base_notional=bn, forward_rate=fr,
            settlement_date=settlement_date, settlement_type=settlement_type,
            currency=cur,
        ))


@final
@dataclass(frozen=True, slots=True)
class NDFPayoutSpec:
    """Non-deliverable forward: cash settled at fixing."""

    currency_pair: CurrencyPair
    base_notional: PositiveDecimal
    forward_rate: PositiveDecimal
    fixing_date: date
    settlement_date: date
    fixing_source: NonEmptyStr
    currency: NonEmptyStr  # settlement currency (freely tradeable leg)

    def __post_init__(self) -> None:
        if self.fixing_date > self.settlement_date:
            raise TypeError(
                f"NDFPayoutSpec: fixing_date ({self.fixing_date}) "
                f"must be <= settlement_date ({self.settlement_date})"
            )

    @staticmethod
    def create(
        currency_pair: str,
        base_notional: Decimal,
        forward_rate: Decimal,
        fixing_date: date,
        settlement_date: date,
        fixing_source: str,
        currency: str,
    ) -> Ok[NDFPayoutSpec] | Err[str]:
        match CurrencyPair.parse(currency_pair):
            case Err(e):
                return Err(f"NDFPayoutSpec.currency_pair: {e}")
            case Ok(cp):
                pass
        match PositiveDecimal.parse(base_notional):
            case Err(e):
                return Err(f"NDFPayoutSpec.base_notional: {e}")
            case Ok(bn):
                pass
        match PositiveDecimal.parse(forward_rate):
            case Err(e):
                return Err(f"NDFPayoutSpec.forward_rate: {e}")
            case Ok(fr):
                pass
        if fixing_date > settlement_date:
            return Err(
                f"NDFPayoutSpec: fixing_date ({fixing_date}) "
                f"must be <= settlement_date ({settlement_date})"
            )
        match NonEmptyStr.parse(fixing_source):
            case Err(e):
                return Err(f"NDFPayoutSpec.fixing_source: {e}")
            case Ok(fs):
                pass
        match NonEmptyStr.parse(currency):
            case Err(e):
                return Err(f"NDFPayoutSpec.currency: {e}")
            case Ok(cur):
                pass
        return Ok(NDFPayoutSpec(
            currency_pair=cp, base_notional=bn, forward_rate=fr,
            fixing_date=fixing_date, settlement_date=settlement_date,
            fixing_source=fs, currency=cur,
        ))


# ---------------------------------------------------------------------------
# IRS PayoutSpec
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class FixedLeg:
    """Fixed leg of a vanilla IRS.

    fixed_rate is Decimal (negative rates allowed for EUR/JPY/CHF).
    CDM: InterestRatePayout with fixedRateSpecification + payerReceiver.

    Phase C enrichment: optional schedule fields. FixedLeg structurally
    CANNOT have reset_dates — making this illegal state unrepresentable.
    """

    payer_receiver: PayerReceiver
    fixed_rate: Decimal
    day_count: DayCountConvention
    payment_frequency: PaymentFrequency
    currency: NonEmptyStr
    notional: PositiveDecimal
    # Phase C: optional schedule enrichment
    calculation_period_dates: CalculationPeriodDates | None = None
    payment_dates: PaymentDates | None = None
    stub: StubPeriod | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.fixed_rate, Decimal) or not self.fixed_rate.is_finite():
            raise TypeError(f"FixedLeg.fixed_rate must be finite Decimal, got {self.fixed_rate!r}")


@final
@dataclass(frozen=True, slots=True)
class FloatLeg:
    """Floating leg of a vanilla IRS.

    CDM: InterestRatePayout with floatingRateSpecification + payerReceiver.

    Phase C enrichment: optional schedule and reset fields. FloatLeg
    CAN have reset_dates (unlike FixedLeg which structurally cannot).
    """

    payer_receiver: PayerReceiver
    float_index: FloatingRateIndex
    spread: Decimal  # basis point spread over index (can be 0 or negative)
    day_count: DayCountConvention
    payment_frequency: PaymentFrequency
    currency: NonEmptyStr
    notional: PositiveDecimal
    # Phase C: optional schedule/reset enrichment
    calculation_period_dates: CalculationPeriodDates | None = None
    payment_dates: PaymentDates | None = None
    reset_dates: ResetDates | None = None
    floating_rate_calc_params: FloatingRateCalculationParameters | None = None
    stub: StubPeriod | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.spread, Decimal) or not self.spread.is_finite():
            raise TypeError(
                f"FloatLeg.spread must be finite Decimal, got {self.spread!r}"
            )


@final
@dataclass(frozen=True, slots=True)
class IRSwapPayoutSpec:
    """Vanilla IRS (fixed-float) payout specification.

    Invariants:
    - start_date < end_date
    - fixed_leg payer == float_leg receiver (swap directions must be inverse)
    """

    fixed_leg: FixedLeg
    float_leg: FloatLeg
    start_date: date
    end_date: date
    currency: NonEmptyStr

    def __post_init__(self) -> None:
        if self.start_date >= self.end_date:
            raise TypeError(
                f"IRSwapPayoutSpec: start_date ({self.start_date}) "
                f"must be < end_date ({self.end_date})"
            )
        # Swap direction invariant: legs must be inverse.
        # We check fixed.payer == float.receiver; the converse
        # (fixed.receiver == float.payer) follows because
        # |CounterpartyRole| = 2 and PayerReceiver enforces payer != receiver.
        fp = self.fixed_leg.payer_receiver
        flp = self.float_leg.payer_receiver
        if fp.payer != flp.receiver:
            raise TypeError(
                "IRSwapPayoutSpec: fixed_leg payer must equal float_leg receiver "
                f"(got fixed payer={fp.payer!r}, "
                f"float receiver={flp.receiver!r})"
            )

    @staticmethod
    def create(
        fixed_rate: Decimal,
        float_index: FloatingRateIndex,
        day_count: DayCountConvention,
        payment_frequency: PaymentFrequency,
        notional: Decimal,
        currency: str,
        start_date: date,
        end_date: date,
        payer_receiver: PayerReceiver,
        spread: Decimal = Decimal("0"),
    ) -> Ok[IRSwapPayoutSpec] | Err[str]:
        """Create IRS payout. Both legs share currency, notional, day count, frequency.

        payer_receiver: who pays fixed. Float leg gets the inverse direction.
        """
        if start_date >= end_date:
            return Err(
                f"IRSwapPayoutSpec: start_date ({start_date}) "
                f"must be < end_date ({end_date})"
            )
        if not isinstance(fixed_rate, Decimal) or not fixed_rate.is_finite():
            return Err(
                "IRSwapPayoutSpec.fixed_rate must be finite Decimal, "
                f"got {fixed_rate!r}"
            )
        match PositiveDecimal.parse(notional):
            case Err(e):
                return Err(f"IRSwapPayoutSpec.notional: {e}")
            case Ok(n):
                pass
        match NonEmptyStr.parse(currency):
            case Err(e):
                return Err(f"IRSwapPayoutSpec.currency: {e}")
            case Ok(cur):
                pass
        float_pr = PayerReceiver(
            payer=payer_receiver.receiver, receiver=payer_receiver.payer,
        )
        fixed = FixedLeg(
            payer_receiver=payer_receiver, fixed_rate=fixed_rate,
            day_count=day_count, payment_frequency=payment_frequency,
            currency=cur, notional=n,
        )
        floating = FloatLeg(
            payer_receiver=float_pr, float_index=float_index, spread=spread,
            day_count=day_count, payment_frequency=payment_frequency,
            currency=cur, notional=n,
        )
        return Ok(IRSwapPayoutSpec(
            fixed_leg=fixed, float_leg=floating,
            start_date=start_date, end_date=end_date, currency=cur,
        ))
