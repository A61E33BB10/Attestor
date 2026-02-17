"""Instrument model types -- Party, PayoutSpecs, EconomicTerms, Product, Instrument.

Payout = EquityPayoutSpec | OptionPayoutSpec | FuturesPayoutSpec
       | FXSpotPayoutSpec | FXForwardPayoutSpec | NDFPayoutSpec | IRSwapPayoutSpec
       | CDSPayoutSpec | SwaptionPayoutSpec.

Phase A: CalculationPeriodDates, PaymentDates (PayerReceiver in core/types).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Literal, final

from attestor.core.identifiers import LEI
from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, Ok
from attestor.core.types import (
    AdjustableDate,
    BusinessDayAdjustments,
    Frequency,
    PayerReceiver,
)
from attestor.instrument.credit_types import (
    CDSPayoutSpec,
    SwaptionPayoutSpec,
)
from attestor.instrument.derivative_types import (
    FuturesPayoutSpec,
    OptionPayoutSpec,
    OptionStyle,
    OptionType,
    SettlementType,
    SwaptionType,
)
from attestor.instrument.fx_types import (
    DayCountConvention,
    FXForwardPayoutSpec,
    FXSpotPayoutSpec,
    IRSwapPayoutSpec,
    NDFPayoutSpec,
    PaymentFrequency,
)
from attestor.oracle.observable import FloatingRateIndex


class PositionStatusEnum(Enum):
    """Lifecycle states for a trade/position."""

    PROPOSED = "Proposed"
    FORMED = "Formed"
    SETTLED = "Settled"
    CANCELLED = "Cancelled"
    CLOSED = "Closed"


@final
@dataclass(frozen=True, slots=True)
class Party:
    """Counterparty or executing party."""

    party_id: NonEmptyStr
    name: NonEmptyStr
    lei: LEI

    @staticmethod
    def create(party_id: str, name: str, lei: str) -> Ok[Party] | Err[str]:
        match NonEmptyStr.parse(party_id):
            case Err(e):
                return Err(f"Party.party_id: {e}")
            case Ok(pid):
                pass
        match NonEmptyStr.parse(name):
            case Err(e):
                return Err(f"Party.name: {e}")
            case Ok(n):
                pass
        match LEI.parse(lei):
            case Err(e):
                return Err(f"Party.lei: {e}")
            case Ok(l_):
                pass
        return Ok(Party(party_id=pid, name=n, lei=l_))


@final
@dataclass(frozen=True, slots=True)
class EquityPayoutSpec:
    """Cash equity or ETF payout specification."""

    instrument_id: NonEmptyStr
    currency: NonEmptyStr
    exchange: NonEmptyStr

    @staticmethod
    def create(
        instrument_id: str, currency: str, exchange: str,
    ) -> Ok[EquityPayoutSpec] | Err[str]:
        match NonEmptyStr.parse(instrument_id):
            case Err(e):
                return Err(f"EquityPayoutSpec.instrument_id: {e}")
            case Ok(iid):
                pass
        match NonEmptyStr.parse(currency):
            case Err(e):
                return Err(f"EquityPayoutSpec.currency: {e}")
            case Ok(cur):
                pass
        match NonEmptyStr.parse(exchange):
            case Err(e):
                return Err(f"EquityPayoutSpec.exchange: {e}")
            case Ok(ex):
                pass
        return Ok(EquityPayoutSpec(instrument_id=iid, currency=cur, exchange=ex))


type Payout = (
    EquityPayoutSpec | OptionPayoutSpec | FuturesPayoutSpec
    | FXSpotPayoutSpec | FXForwardPayoutSpec | NDFPayoutSpec | IRSwapPayoutSpec
    | CDSPayoutSpec | SwaptionPayoutSpec
)


@final
@dataclass(frozen=True, slots=True)
class EconomicTerms:
    """Economic terms of an instrument. CDM: payout (1..*)."""

    payouts: tuple[Payout, ...]
    effective_date: date
    termination_date: date | None  # None for perpetual equities

    def __post_init__(self) -> None:
        if not self.payouts:
            raise TypeError("EconomicTerms.payouts must contain at least one Payout")
        if self.termination_date is not None and self.effective_date > self.termination_date:
            raise TypeError(
                f"EconomicTerms: effective_date ({self.effective_date}) "
                f"must be <= termination_date ({self.termination_date})"
            )


@final
@dataclass(frozen=True, slots=True)
class Product:
    """Product wrapping economic terms."""

    economic_terms: EconomicTerms


@final
@dataclass(frozen=True, slots=True)
class Instrument:
    """A tradeable instrument with its parties and lifecycle status."""

    instrument_id: NonEmptyStr
    product: Product
    parties: tuple[Party, ...]
    trade_date: date
    status: PositionStatusEnum


def create_equity_instrument(
    instrument_id: str,
    currency: str,
    exchange: str,
    parties: tuple[Party, ...],
    trade_date: date,
) -> Ok[Instrument] | Err[str]:
    """Create an equity Instrument from basic parameters."""
    match EquityPayoutSpec.create(instrument_id, currency, exchange):
        case Err(e):
            return Err(e)
        case Ok(payout):
            pass
    match NonEmptyStr.parse(instrument_id):
        case Err(e):
            return Err(f"Instrument.instrument_id: {e}")
        case Ok(iid):
            pass
    terms = EconomicTerms(payouts=(payout,), effective_date=trade_date, termination_date=None)
    product = Product(economic_terms=terms)
    return Ok(Instrument(
        instrument_id=iid,
        product=product,
        parties=parties,
        trade_date=trade_date,
        status=PositionStatusEnum.PROPOSED,
    ))


def create_option_instrument(
    instrument_id: str,
    underlying_id: str,
    strike: Decimal,
    expiry_date: date,
    option_type: OptionType,
    option_style: OptionStyle,
    settlement_type: SettlementType,
    currency: str,
    exchange: str,
    parties: tuple[Party, ...],
    trade_date: date,
    multiplier: Decimal = Decimal("100"),
) -> Ok[Instrument] | Err[str]:
    """Create an option Instrument from basic parameters."""
    match OptionPayoutSpec.create(
        underlying_id=underlying_id, strike=strike, expiry_date=expiry_date,
        option_type=option_type, option_style=option_style,
        settlement_type=settlement_type, currency=currency,
        exchange=exchange, multiplier=multiplier,
    ):
        case Err(e):
            return Err(e)
        case Ok(payout):
            pass
    match NonEmptyStr.parse(instrument_id):
        case Err(e):
            return Err(f"Instrument.instrument_id: {e}")
        case Ok(iid):
            pass
    terms = EconomicTerms(
        payouts=(payout,), effective_date=trade_date, termination_date=expiry_date,
    )
    product = Product(economic_terms=terms)
    return Ok(Instrument(
        instrument_id=iid,
        product=product,
        parties=parties,
        trade_date=trade_date,
        status=PositionStatusEnum.PROPOSED,
    ))


def create_futures_instrument(
    instrument_id: str,
    underlying_id: str,
    expiry_date: date,
    last_trading_date: date,
    settlement_type: SettlementType,
    contract_size: Decimal,
    currency: str,
    exchange: str,
    parties: tuple[Party, ...],
    trade_date: date,
) -> Ok[Instrument] | Err[str]:
    """Create a futures Instrument from basic parameters."""
    match FuturesPayoutSpec.create(
        underlying_id=underlying_id, expiry_date=expiry_date,
        last_trading_date=last_trading_date, settlement_type=settlement_type,
        contract_size=contract_size, currency=currency, exchange=exchange,
    ):
        case Err(e):
            return Err(e)
        case Ok(payout):
            pass
    match NonEmptyStr.parse(instrument_id):
        case Err(e):
            return Err(f"Instrument.instrument_id: {e}")
        case Ok(iid):
            pass
    terms = EconomicTerms(
        payouts=(payout,), effective_date=trade_date, termination_date=expiry_date,
    )
    product = Product(economic_terms=terms)
    return Ok(Instrument(
        instrument_id=iid,
        product=product,
        parties=parties,
        trade_date=trade_date,
        status=PositionStatusEnum.PROPOSED,
    ))


# ---------------------------------------------------------------------------
# Phase 3 instrument factories
# ---------------------------------------------------------------------------


def create_fx_spot_instrument(
    instrument_id: str,
    currency_pair: str,
    base_notional: Decimal,
    currency: str,
    parties: tuple[Party, ...],
    trade_date: date,
) -> Ok[Instrument] | Err[str]:
    """Create an FX spot Instrument."""
    match FXSpotPayoutSpec.create(
        currency_pair=currency_pair, base_notional=base_notional,
        currency=currency,
    ):
        case Err(e):
            return Err(e)
        case Ok(payout):
            pass
    match NonEmptyStr.parse(instrument_id):
        case Err(e):
            return Err(f"Instrument.instrument_id: {e}")
        case Ok(iid):
            pass
    terms = EconomicTerms(payouts=(payout,), effective_date=trade_date, termination_date=None)
    product = Product(economic_terms=terms)
    return Ok(Instrument(
        instrument_id=iid, product=product, parties=parties,
        trade_date=trade_date, status=PositionStatusEnum.PROPOSED,
    ))


def create_fx_forward_instrument(
    instrument_id: str,
    currency_pair: str,
    base_notional: Decimal,
    forward_rate: Decimal,
    settlement_date: date,
    currency: str,
    parties: tuple[Party, ...],
    trade_date: date,
) -> Ok[Instrument] | Err[str]:
    """Create an FX forward Instrument."""
    match FXForwardPayoutSpec.create(
        currency_pair=currency_pair, base_notional=base_notional,
        forward_rate=forward_rate, settlement_date=settlement_date,
        currency=currency,
    ):
        case Err(e):
            return Err(e)
        case Ok(payout):
            pass
    match NonEmptyStr.parse(instrument_id):
        case Err(e):
            return Err(f"Instrument.instrument_id: {e}")
        case Ok(iid):
            pass
    terms = EconomicTerms(
        payouts=(payout,), effective_date=trade_date, termination_date=settlement_date,
    )
    product = Product(economic_terms=terms)
    return Ok(Instrument(
        instrument_id=iid, product=product, parties=parties,
        trade_date=trade_date, status=PositionStatusEnum.PROPOSED,
    ))


def create_ndf_instrument(
    instrument_id: str,
    currency_pair: str,
    base_notional: Decimal,
    forward_rate: Decimal,
    fixing_date: date,
    settlement_date: date,
    fixing_source: str,
    currency: str,
    parties: tuple[Party, ...],
    trade_date: date,
) -> Ok[Instrument] | Err[str]:
    """Create an NDF Instrument."""
    match NDFPayoutSpec.create(
        currency_pair=currency_pair, base_notional=base_notional,
        forward_rate=forward_rate, fixing_date=fixing_date,
        settlement_date=settlement_date, fixing_source=fixing_source,
        currency=currency,
    ):
        case Err(e):
            return Err(e)
        case Ok(payout):
            pass
    match NonEmptyStr.parse(instrument_id):
        case Err(e):
            return Err(f"Instrument.instrument_id: {e}")
        case Ok(iid):
            pass
    terms = EconomicTerms(
        payouts=(payout,), effective_date=trade_date, termination_date=settlement_date,
    )
    product = Product(economic_terms=terms)
    return Ok(Instrument(
        instrument_id=iid, product=product, parties=parties,
        trade_date=trade_date, status=PositionStatusEnum.PROPOSED,
    ))


def create_irs_instrument(
    instrument_id: str,
    fixed_rate: Decimal,
    float_index: FloatingRateIndex,
    day_count: DayCountConvention,
    payment_frequency: PaymentFrequency,
    notional: Decimal,
    currency: str,
    start_date: date,
    end_date: date,
    parties: tuple[Party, ...],
    trade_date: date,
    payer_receiver: PayerReceiver,
    spread: Decimal = Decimal("0"),
) -> Ok[Instrument] | Err[str]:
    """Create a vanilla IRS Instrument."""
    match IRSwapPayoutSpec.create(
        fixed_rate=fixed_rate, float_index=float_index,
        day_count=day_count, payment_frequency=payment_frequency,
        notional=notional, currency=currency,
        start_date=start_date, end_date=end_date,
        payer_receiver=payer_receiver, spread=spread,
    ):
        case Err(e):
            return Err(e)
        case Ok(payout):
            pass
    match NonEmptyStr.parse(instrument_id):
        case Err(e):
            return Err(f"Instrument.instrument_id: {e}")
        case Ok(iid):
            pass
    terms = EconomicTerms(
        payouts=(payout,), effective_date=start_date, termination_date=end_date,
    )
    product = Product(economic_terms=terms)
    return Ok(Instrument(
        instrument_id=iid, product=product, parties=parties,
        trade_date=trade_date, status=PositionStatusEnum.PROPOSED,
    ))


# ---------------------------------------------------------------------------
# Phase 4 instrument factories — CDS and Swaption
# ---------------------------------------------------------------------------


def create_cds_instrument(
    instrument_id: str,
    reference_entity: str,
    notional: Decimal,
    spread: Decimal,
    currency: str,
    effective_date: date,
    maturity_date: date,
    payment_frequency: PaymentFrequency,
    day_count: DayCountConvention,
    recovery_rate: Decimal,
    parties: tuple[Party, ...],
    trade_date: date,
    payer_receiver: PayerReceiver,
) -> Ok[Instrument] | Err[str]:
    """Create a CDS Instrument from basic parameters."""
    match CDSPayoutSpec.create(
        reference_entity=reference_entity, notional=notional, spread=spread,
        currency=currency, effective_date=effective_date,
        maturity_date=maturity_date, payment_frequency=payment_frequency,
        day_count=day_count, recovery_rate=recovery_rate,
        payer_receiver=payer_receiver,
    ):
        case Err(e):
            return Err(e)
        case Ok(payout):
            pass
    match NonEmptyStr.parse(instrument_id):
        case Err(e):
            return Err(f"Instrument.instrument_id: {e}")
        case Ok(iid):
            pass
    terms = EconomicTerms(
        payouts=(payout,), effective_date=effective_date, termination_date=maturity_date,
    )
    product = Product(economic_terms=terms)
    return Ok(Instrument(
        instrument_id=iid, product=product, parties=parties,
        trade_date=trade_date, status=PositionStatusEnum.PROPOSED,
    ))


def create_swaption_instrument(
    instrument_id: str,
    swaption_type: SwaptionType,
    strike: Decimal,
    exercise_date: date,
    underlying_swap: IRSwapPayoutSpec,
    settlement_type: SettlementType,
    currency: str,
    notional: Decimal,
    parties: tuple[Party, ...],
    trade_date: date,
    payer_receiver: PayerReceiver,
) -> Ok[Instrument] | Err[str]:
    """Create a swaption Instrument from basic parameters."""
    match SwaptionPayoutSpec.create(
        swaption_type=swaption_type, strike=strike,
        exercise_date=exercise_date, underlying_swap=underlying_swap,
        settlement_type=settlement_type, currency=currency, notional=notional,
        payer_receiver=payer_receiver,
    ):
        case Err(e):
            return Err(e)
        case Ok(payout):
            pass
    match NonEmptyStr.parse(instrument_id):
        case Err(e):
            return Err(f"Instrument.instrument_id: {e}")
        case Ok(iid):
            pass
    terms = EconomicTerms(
        payouts=(payout,), effective_date=trade_date, termination_date=exercise_date,
    )
    product = Product(economic_terms=terms)
    return Ok(Instrument(
        instrument_id=iid, product=product, parties=parties,
        trade_date=trade_date, status=PositionStatusEnum.PROPOSED,
    ))


# ---------------------------------------------------------------------------
# Phase A: Counterparty direction and schedule types
# ---------------------------------------------------------------------------

# CounterpartyRole and PayerReceiver imported from core/types.py above.


@final
@dataclass(frozen=True, slots=True)
class CalculationPeriodDates:
    """Effective/termination dates with schedule generation parameters.

    CDM: CalculationPeriodDates = effectiveDate + terminationDate + frequency
         + rollConvention + firstPeriodStartDate + lastRegularPeriodEndDate + BDA.
    """

    effective_date: AdjustableDate
    termination_date: AdjustableDate
    frequency: Frequency
    business_day_adjustments: BusinessDayAdjustments
    first_period_start_date: date | None = None  # Stub at start
    last_regular_period_end_date: date | None = None  # Stub at end

    def __post_init__(self) -> None:
        eff = self.effective_date.unadjusted_date
        term = self.termination_date.unadjusted_date
        if eff >= term:
            raise TypeError(
                f"CalculationPeriodDates: effective_date ({eff}) "
                f"must be < termination_date ({term})"
            )
        fpsd = self.first_period_start_date
        lrped = self.last_regular_period_end_date
        # Stub start must be <= effective and < termination
        if fpsd is not None:
            if fpsd > eff:
                raise TypeError(
                    "CalculationPeriodDates: "
                    "first_period_start_date must be <= effective_date"
                )
            if fpsd >= term:
                raise TypeError(
                    "CalculationPeriodDates: "
                    "first_period_start_date must be < termination_date"
                )
        # Last regular end must be > effective and <= termination
        if lrped is not None:
            if lrped <= eff:
                raise TypeError(
                    "CalculationPeriodDates: "
                    "last_regular_period_end_date must be > effective_date"
                )
            if lrped > term:
                raise TypeError(
                    "CalculationPeriodDates: "
                    "last_regular_period_end_date must be <= termination_date"
                )
        # Cross-validate: stub start < last regular end
        if fpsd is not None and lrped is not None and fpsd >= lrped:
            raise TypeError(
                "CalculationPeriodDates: first_period_start_date "
                "must be < last_regular_period_end_date"
            )


@final
@dataclass(frozen=True, slots=True)
class PaymentDates:
    """Payment schedule parameters for a payout leg.

    CDM: PaymentDates = paymentFrequency + payRelativeTo + paymentDaysOffset + BDA.
    """

    payment_frequency: Frequency
    pay_relative_to: Literal["CalculationPeriodStartDate", "CalculationPeriodEndDate"]
    payment_day_offset: int  # Number of business days offset (can be 0)
    business_day_adjustments: BusinessDayAdjustments

    def __post_init__(self) -> None:
        if self.payment_day_offset < 0:
            raise TypeError(
                f"PaymentDates: payment_day_offset must be >= 0, got {self.payment_day_offset}"
            )
