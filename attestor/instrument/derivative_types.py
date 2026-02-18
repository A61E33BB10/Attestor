"""Derivative instrument types — options, futures, and supporting enums.

All types are @final @dataclass(frozen=True, slots=True). Smart constructors
return Ok | Err for validated creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import final

from attestor.core.money import NonEmptyStr, NonNegativeDecimal, PositiveDecimal
from attestor.core.result import Err, Ok

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OptionTypeEnum(Enum):
    """CDM: OptionTypeEnum extends PutCallEnum.

    Put/Call for vanilla options; Payer/Receiver for swaptions on index CDS;
    Straddle for combined call+put at same strike/expiry.
    """

    CALL = "Call"
    PUT = "Put"
    PAYER = "Payer"
    RECEIVER = "Receiver"
    STRADDLE = "Straddle"


class OptionExerciseStyleEnum(Enum):
    """CDM: OptionExerciseStyleEnum — option exercise style.

    European (single), Bermuda (multiple specified dates), American (continuous range).
    """

    EUROPEAN = "European"
    BERMUDA = "Bermuda"
    AMERICAN = "American"


class ExpirationTimeTypeEnum(Enum):
    """CDM: ExpirationTimeTypeEnum — time of day at which equity option expires."""

    CLOSE = "Close"
    OPEN = "Open"
    OSP = "OSP"
    SPECIFIC_TIME = "SpecificTime"
    XETRA = "XETRA"
    DERIVATIVES_CLOSE = "DerivativesClose"
    AS_SPECIFIED_IN_MASTER_CONFIRMATION = "AsSpecifiedInMasterConfirmation"


class CallingPartyEnum(Enum):
    """CDM: CallingPartyEnum — party with right to demand termination."""

    INITIAL_BUYER = "InitialBuyer"
    INITIAL_SELLER = "InitialSeller"
    EITHER = "Either"
    AS_DEFINED_IN_MASTER_AGREEMENT = "AsDefinedInMasterAgreement"


class ExerciseNoticeGiverEnum(Enum):
    """CDM: ExerciseNoticeGiverEnum — principal party with right to exercise."""

    BUYER = "Buyer"
    SELLER = "Seller"
    BOTH = "Both"
    AS_SPECIFIED_IN_MASTER_AGREEMENT = "AsSpecifiedInMasterAgreement"


class AveragingInOutEnum(Enum):
    """CDM: AveragingInOutEnum — type of averaging in Asian options."""

    IN = "In"
    OUT = "Out"
    BOTH = "Both"


class AssetPayoutTradeTypeEnum(Enum):
    """CDM: AssetPayoutTradeTypeEnum — securities finance trade type."""

    REPO = "Repo"
    BUY_SELL_BACK = "BuySellBack"


class SettlementTypeEnum(Enum):
    """CDM: SettlementTypeEnum — how a product is settled.

    Physical delivery of securities, cash settlement of intrinsic value,
    election between the two, or either without prior election.
    """

    CASH = "Cash"
    PHYSICAL = "Physical"
    ELECTION = "Election"
    CASH_OR_PHYSICAL = "CashOrPhysical"


class DeliveryMethodEnum(Enum):
    """CDM: DeliveryMethodEnum — securities delivery mechanism."""

    DELIVERY_VERSUS_PAYMENT = "DeliveryVersusPayment"
    FREE_OF_PAYMENT = "FreeOfPayment"
    PRE_DELIVERY = "PreDelivery"
    PRE_PAYMENT = "PrePayment"


class TransferSettlementEnum(Enum):
    """CDM: TransferSettlementEnum — how a transfer settles."""

    DELIVERY_VERSUS_DELIVERY = "DeliveryVersusDelivery"
    DELIVERY_VERSUS_PAYMENT = "DeliveryVersusPayment"
    PAYMENT_VERSUS_PAYMENT = "PaymentVersusPayment"
    NOT_CENTRAL_SETTLEMENT = "NotCentralSettlement"


class StandardSettlementStyleEnum(Enum):
    """CDM: StandardSettlementStyleEnum — settlement style."""

    STANDARD = "Standard"
    NET = "Net"
    STANDARD_AND_NET = "StandardAndNet"
    PAIR_AND_NET = "PairAndNet"


class SettlementCentreEnum(Enum):
    """CDM: SettlementCentreEnum — settlement centre."""

    EUROCLEAR_BANK = "EuroclearBank"
    CLEARSTREAM_BANKING_LUXEMBOURG = "ClearstreamBankingLuxembourg"


class CashSettlementMethodEnum(Enum):
    """CDM: CashSettlementMethodEnum — ISDA cash settlement methods.

    Values from ISDA 2006 Definitions Section 18.3 and
    ISDA 2021 Definitions Section 18.2.
    """

    CASH_PRICE_METHOD = "CashPriceMethod"
    CASH_PRICE_ALTERNATE_METHOD = "CashPriceAlternateMethod"
    PAR_YIELD_CURVE_ADJUSTED_METHOD = "ParYieldCurveAdjustedMethod"
    ZERO_COUPON_YIELD_ADJUSTED_METHOD = "ZeroCouponYieldAdjustedMethod"
    PAR_YIELD_CURVE_UNADJUSTED_METHOD = "ParYieldCurveUnadjustedMethod"
    CROSS_CURRENCY_METHOD = "CrossCurrencyMethod"
    COLLATERALIZED_CASH_PRICE_METHOD = "CollateralizedCashPriceMethod"
    MID_MARKET_INDICATIVE_QUOTATIONS = "MidMarketIndicativeQuotations"
    MID_MARKET_INDICATIVE_QUOTATIONS_ALTERNATE = "MidMarketIndicativeQuotationsAlternate"
    MID_MARKET_CALCULATION_AGENT_DETERMINATION = "MidMarketCalculationAgentDetermination"
    REPLACEMENT_VALUE_FIRM_QUOTATIONS = "ReplacementValueFirmQuotations"
    REPLACEMENT_VALUE_CALCULATION_AGENT_DETERMINATION = (
        "ReplacementValueCalculationAgentDetermination"
    )


class ScheduledTransferEnum(Enum):
    """CDM: ScheduledTransferEnum — type of scheduled cashflow."""

    CORPORATE_ACTION = "CorporateAction"
    COUPON = "Coupon"
    CREDIT_EVENT = "CreditEvent"
    DIVIDEND_RETURN = "DividendReturn"
    EXERCISE = "Exercise"
    FIXED_RATE_RETURN = "FixedRateReturn"
    FLOATING_RATE_RETURN = "FloatingRateReturn"
    FRACTIONAL_AMOUNT = "FractionalAmount"
    INTEREST_RETURN = "InterestReturn"
    NET_INTEREST = "NetInterest"
    PERFORMANCE = "Performance"
    PRINCIPAL = "Principal"


class UnscheduledTransferEnum(Enum):
    """CDM: UnscheduledTransferEnum — type of non-scheduled transfer."""

    RECALL = "Recall"
    RETURN = "Return"


class MarginType(Enum):
    """Variation or initial margin."""

    VARIATION = "VARIATION"
    INITIAL = "INITIAL"


class CreditEventType(Enum):
    """ISDA credit event triggers for CDS contracts.

    CDM: CreditEventTypeEnum (~6 of 12 values).
    Phase F: expanded with OBLIGATION_DEFAULT, GOVERNMENTAL_INTERVENTION,
    REPUDIATION_MORATORIUM.
    """

    BANKRUPTCY = "BANKRUPTCY"
    FAILURE_TO_PAY = "FAILURE_TO_PAY"
    RESTRUCTURING = "RESTRUCTURING"
    OBLIGATION_DEFAULT = "OBLIGATION_DEFAULT"
    GOVERNMENTAL_INTERVENTION = "GOVERNMENTAL_INTERVENTION"
    REPUDIATION_MORATORIUM = "REPUDIATION_MORATORIUM"


class SeniorityLevel(Enum):
    """Debt seniority for CDS reference obligation."""

    SENIOR_UNSECURED = "SENIOR_UNSECURED"
    SUBORDINATED = "SUBORDINATED"
    SENIOR_SECURED = "SENIOR_SECURED"


class ProtectionSide(Enum):
    """CDS protection buyer or seller."""

    BUYER = "BUYER"
    SELLER = "SELLER"


class SwaptionType(Enum):
    """Payer or receiver swaption."""

    PAYER = "PAYER"
    RECEIVER = "RECEIVER"


class RestructuringEnum(Enum):
    """ISDA restructuring clause type for CDS contracts.

    CDM: RestructuringEnum (3 of 3 CDM values; excludes ISDA XR/No Restructuring).
    Controls deliverable obligation limitations after a restructuring credit event.
    """

    MOD_R = "MOD_R"          # Modified Restructuring (2003 Definitions)
    MOD_MOD_R = "MOD_MOD_R"  # Modified Modified Restructuring (2014)
    FULL_R = "FULL_R"        # Full (Old) Restructuring


# ---------------------------------------------------------------------------
# PayoutSpec types
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class OptionPayoutSpec:
    """Vanilla option payout specification.

    Note: exercise_terms, when present, provides richer exercise detail
    than option_style. exercise_terms takes precedence over option_style
    for downstream logic.
    """

    underlying_id: NonEmptyStr
    strike: NonNegativeDecimal  # zero-strike allowed for total return structures
    expiry_date: date
    option_type: OptionTypeEnum
    option_style: OptionExerciseStyleEnum
    settlement_type: SettlementTypeEnum
    currency: NonEmptyStr
    exchange: NonEmptyStr
    multiplier: PositiveDecimal  # typically 100
    # Phase C enrichment
    exercise_terms: AmericanExercise | EuropeanExercise | BermudaExercise | None = None

    @staticmethod
    def create(
        underlying_id: str,
        strike: Decimal,
        expiry_date: date,
        option_type: OptionTypeEnum,
        option_style: OptionExerciseStyleEnum,
        settlement_type: SettlementTypeEnum,
        currency: str,
        exchange: str,
        multiplier: Decimal = Decimal("100"),
    ) -> Ok[OptionPayoutSpec] | Err[str]:
        match NonEmptyStr.parse(underlying_id):
            case Err(e):
                return Err(f"OptionPayoutSpec.underlying_id: {e}")
            case Ok(uid):
                pass
        match NonNegativeDecimal.parse(strike):
            case Err(e):
                return Err(f"OptionPayoutSpec.strike: {e}")
            case Ok(s):
                pass
        match NonEmptyStr.parse(currency):
            case Err(e):
                return Err(f"OptionPayoutSpec.currency: {e}")
            case Ok(cur):
                pass
        match NonEmptyStr.parse(exchange):
            case Err(e):
                return Err(f"OptionPayoutSpec.exchange: {e}")
            case Ok(ex):
                pass
        match PositiveDecimal.parse(multiplier):
            case Err(e):
                return Err(f"OptionPayoutSpec.multiplier: {e}")
            case Ok(mul):
                pass
        return Ok(OptionPayoutSpec(
            underlying_id=uid, strike=s, expiry_date=expiry_date,
            option_type=option_type, option_style=option_style,
            settlement_type=settlement_type,
            currency=cur, exchange=ex, multiplier=mul,
        ))


@final
@dataclass(frozen=True, slots=True)
class FuturesPayoutSpec:
    """Listed futures payout specification."""

    underlying_id: NonEmptyStr
    expiry_date: date
    last_trading_date: date
    settlement_type: SettlementTypeEnum
    contract_size: PositiveDecimal  # point value (USD per unit of price movement)
    currency: NonEmptyStr
    exchange: NonEmptyStr

    def __post_init__(self) -> None:
        if self.last_trading_date > self.expiry_date:
            raise TypeError(
                f"FuturesPayoutSpec: last_trading_date ({self.last_trading_date}) "
                f"must be <= expiry_date ({self.expiry_date})"
            )

    @staticmethod
    def create(
        underlying_id: str,
        expiry_date: date,
        last_trading_date: date,
        settlement_type: SettlementTypeEnum,
        contract_size: Decimal,
        currency: str,
        exchange: str,
    ) -> Ok[FuturesPayoutSpec] | Err[str]:
        match NonEmptyStr.parse(underlying_id):
            case Err(e):
                return Err(f"FuturesPayoutSpec.underlying_id: {e}")
            case Ok(uid):
                pass
        if last_trading_date > expiry_date:
            return Err(
                f"FuturesPayoutSpec: last_trading_date ({last_trading_date}) "
                f"must be <= expiry_date ({expiry_date})"
            )
        match PositiveDecimal.parse(contract_size):
            case Err(e):
                return Err(f"FuturesPayoutSpec.contract_size: {e}")
            case Ok(cs):
                pass
        match NonEmptyStr.parse(currency):
            case Err(e):
                return Err(f"FuturesPayoutSpec.currency: {e}")
            case Ok(cur):
                pass
        match NonEmptyStr.parse(exchange):
            case Err(e):
                return Err(f"FuturesPayoutSpec.exchange: {e}")
            case Ok(ex):
                pass
        return Ok(FuturesPayoutSpec(
            underlying_id=uid, expiry_date=expiry_date,
            last_trading_date=last_trading_date,
            settlement_type=settlement_type,
            contract_size=cs, currency=cur, exchange=ex,
        ))


# ---------------------------------------------------------------------------
# InstrumentDetail (gateway-level discriminated union)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class EquityDetail:
    """Marker type for equity orders. No extra fields needed."""


@final
@dataclass(frozen=True, slots=True)
class OptionDetail:
    """Option-specific fields on a CanonicalOrder."""

    strike: NonNegativeDecimal
    expiry_date: date
    option_type: OptionTypeEnum
    option_style: OptionExerciseStyleEnum
    settlement_type: SettlementTypeEnum
    underlying_id: NonEmptyStr
    multiplier: PositiveDecimal

    @staticmethod
    def create(
        strike: Decimal,
        expiry_date: date,
        option_type: OptionTypeEnum,
        option_style: OptionExerciseStyleEnum,
        settlement_type: SettlementTypeEnum,
        underlying_id: str,
        multiplier: Decimal = Decimal("100"),
    ) -> Ok[OptionDetail] | Err[str]:
        match NonNegativeDecimal.parse(strike):
            case Err(e):
                return Err(f"OptionDetail.strike: {e}")
            case Ok(s):
                pass
        match NonEmptyStr.parse(underlying_id):
            case Err(e):
                return Err(f"OptionDetail.underlying_id: {e}")
            case Ok(uid):
                pass
        match PositiveDecimal.parse(multiplier):
            case Err(e):
                return Err(f"OptionDetail.multiplier: {e}")
            case Ok(mul):
                pass
        return Ok(OptionDetail(
            strike=s, expiry_date=expiry_date,
            option_type=option_type, option_style=option_style,
            settlement_type=settlement_type,
            underlying_id=uid, multiplier=mul,
        ))


@final
@dataclass(frozen=True, slots=True)
class FuturesDetail:
    """Futures-specific fields on a CanonicalOrder."""

    expiry_date: date
    contract_size: PositiveDecimal
    settlement_type: SettlementTypeEnum
    underlying_id: NonEmptyStr

    @staticmethod
    def create(
        expiry_date: date,
        contract_size: Decimal,
        settlement_type: SettlementTypeEnum,
        underlying_id: str,
    ) -> Ok[FuturesDetail] | Err[str]:
        match PositiveDecimal.parse(contract_size):
            case Err(e):
                return Err(f"FuturesDetail.contract_size: {e}")
            case Ok(cs):
                pass
        match NonEmptyStr.parse(underlying_id):
            case Err(e):
                return Err(f"FuturesDetail.underlying_id: {e}")
            case Ok(uid):
                pass
        return Ok(FuturesDetail(
            expiry_date=expiry_date, contract_size=cs,
            settlement_type=settlement_type, underlying_id=uid,
        ))


@final
@dataclass(frozen=True, slots=True)
class FXDetail:
    """FX order detail — covers spot, forward, and NDF."""

    currency_pair: str  # "EUR/USD" format, validated at gateway
    settlement_date: date
    settlement_type: SettlementTypeEnum
    forward_rate: PositiveDecimal | None = None  # None for spot
    fixing_source: NonEmptyStr | None = None  # non-None for NDF
    fixing_date: date | None = None  # non-None for NDF

    @staticmethod
    def create(
        currency_pair: str,
        settlement_date: date,
        settlement_type: SettlementTypeEnum,
        forward_rate: Decimal | None = None,
        fixing_source: str | None = None,
        fixing_date: date | None = None,
    ) -> Ok[FXDetail] | Err[str]:
        if not currency_pair or "/" not in currency_pair:
            return Err(f"FXDetail.currency_pair must be BASE/QUOTE, got '{currency_pair}'")
        fr: PositiveDecimal | None = None
        if forward_rate is not None:
            match PositiveDecimal.parse(forward_rate):
                case Err(e):
                    return Err(f"FXDetail.forward_rate: {e}")
                case Ok(f):
                    fr = f
        fs: NonEmptyStr | None = None
        if fixing_source is not None:
            match NonEmptyStr.parse(fixing_source):
                case Err(e):
                    return Err(f"FXDetail.fixing_source: {e}")
                case Ok(s):
                    fs = s
        if fixing_date is not None and fixing_date > settlement_date:
            return Err(
                f"FXDetail: fixing_date ({fixing_date}) "
                f"must be <= settlement_date ({settlement_date})"
            )
        return Ok(FXDetail(
            currency_pair=currency_pair, settlement_date=settlement_date,
            settlement_type=settlement_type, forward_rate=fr,
            fixing_source=fs, fixing_date=fixing_date,
        ))


@final
@dataclass(frozen=True, slots=True)
class IRSwapDetail:
    """IRS order detail on a CanonicalOrder."""

    fixed_rate: Decimal
    float_index: NonEmptyStr
    day_count: str  # "ACT/360", "ACT/365", "30/360"
    payment_frequency: str  # "MONTHLY", "QUARTERLY", etc.
    tenor_months: int
    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        if not isinstance(self.fixed_rate, Decimal) or not self.fixed_rate.is_finite():
            raise TypeError(
                f"IRSwapDetail.fixed_rate must be finite Decimal, "
                f"got {self.fixed_rate!r}"
            )
        if self.tenor_months <= 0:
            raise TypeError(f"IRSwapDetail.tenor_months must be > 0, got {self.tenor_months}")
        if self.start_date >= self.end_date:
            raise TypeError(
                f"IRSwapDetail: start_date ({self.start_date}) must be < end_date ({self.end_date})"
            )

    @staticmethod
    def create(
        fixed_rate: Decimal,
        float_index: str,
        day_count: str,
        payment_frequency: str,
        tenor_months: int,
        start_date: date,
        end_date: date,
    ) -> Ok[IRSwapDetail] | Err[str]:
        if not isinstance(fixed_rate, Decimal) or not fixed_rate.is_finite():
            return Err(f"IRSwapDetail.fixed_rate must be finite Decimal, got {fixed_rate!r}")
        match NonEmptyStr.parse(float_index):
            case Err(e):
                return Err(f"IRSwapDetail.float_index: {e}")
            case Ok(fi):
                pass
        if tenor_months <= 0:
            return Err(f"IRSwapDetail.tenor_months must be > 0, got {tenor_months}")
        if start_date >= end_date:
            return Err(
                f"IRSwapDetail: start_date ({start_date}) "
                f"must be < end_date ({end_date})"
            )
        return Ok(IRSwapDetail(
            fixed_rate=fixed_rate, float_index=fi, day_count=day_count,
            payment_frequency=payment_frequency, tenor_months=tenor_months,
            start_date=start_date, end_date=end_date,
        ))


@final
@dataclass(frozen=True, slots=True)
class CDSDetail:
    """CDS order detail on a CanonicalOrder."""

    reference_entity: NonEmptyStr
    spread_bps: PositiveDecimal
    seniority: SeniorityLevel
    protection_side: ProtectionSide
    start_date: date
    maturity_date: date

    def __post_init__(self) -> None:
        if self.start_date >= self.maturity_date:
            raise TypeError(
                f"CDSDetail: start_date ({self.start_date}) must be "
                f"< maturity_date ({self.maturity_date})"
            )

    @staticmethod
    def create(
        reference_entity: str,
        spread_bps: Decimal,
        seniority: SeniorityLevel,
        protection_side: ProtectionSide,
        start_date: date,
        maturity_date: date,
    ) -> Ok[CDSDetail] | Err[str]:
        match NonEmptyStr.parse(reference_entity):
            case Err(e):
                return Err(f"CDSDetail.reference_entity: {e}")
            case Ok(ref):
                pass
        match PositiveDecimal.parse(spread_bps):
            case Err(e):
                return Err(f"CDSDetail.spread_bps: {e}")
            case Ok(s):
                pass
        if start_date >= maturity_date:
            return Err(
                f"CDSDetail: start_date ({start_date}) "
                f"must be < maturity_date ({maturity_date})"
            )
        return Ok(CDSDetail(
            reference_entity=ref, spread_bps=s, seniority=seniority,
            protection_side=protection_side,
            start_date=start_date, maturity_date=maturity_date,
        ))


@final
@dataclass(frozen=True, slots=True)
class SwaptionDetail:
    """Swaption order detail on a CanonicalOrder."""

    swaption_type: SwaptionType
    expiry_date: date
    underlying_fixed_rate: Decimal
    underlying_float_index: NonEmptyStr
    underlying_tenor_months: int
    settlement_type: SettlementTypeEnum

    def __post_init__(self) -> None:
        ufr = self.underlying_fixed_rate
        if not isinstance(ufr, Decimal) or not ufr.is_finite():
            raise TypeError(
                f"SwaptionDetail.underlying_fixed_rate must be finite Decimal, "
                f"got {self.underlying_fixed_rate!r}"
            )
        if self.underlying_tenor_months <= 0:
            raise TypeError(
                f"SwaptionDetail.underlying_tenor_months must be > 0, "
                f"got {self.underlying_tenor_months}"
            )

    @staticmethod
    def create(
        swaption_type: SwaptionType,
        expiry_date: date,
        underlying_fixed_rate: Decimal,
        underlying_float_index: str,
        underlying_tenor_months: int,
        settlement_type: SettlementTypeEnum,
    ) -> Ok[SwaptionDetail] | Err[str]:
        if not isinstance(underlying_fixed_rate, Decimal) or not underlying_fixed_rate.is_finite():
            return Err(
                f"SwaptionDetail.underlying_fixed_rate must be finite Decimal, "
                f"got {underlying_fixed_rate!r}"
            )
        match NonEmptyStr.parse(underlying_float_index):
            case Err(e):
                return Err(f"SwaptionDetail.underlying_float_index: {e}")
            case Ok(fi):
                pass
        if underlying_tenor_months <= 0:
            return Err(
                f"SwaptionDetail.underlying_tenor_months must be > 0, "
                f"got {underlying_tenor_months}"
            )
        return Ok(SwaptionDetail(
            swaption_type=swaption_type, expiry_date=expiry_date,
            underlying_fixed_rate=underlying_fixed_rate, underlying_float_index=fi,
            underlying_tenor_months=underlying_tenor_months,
            settlement_type=settlement_type,
        ))


type InstrumentDetail = (
    EquityDetail | OptionDetail | FuturesDetail | FXDetail | IRSwapDetail
    | CDSDetail | SwaptionDetail
)


# ---------------------------------------------------------------------------
# Phase C: Performance payout
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class PerformancePayoutSpec:
    """Equity or total return swap payout (return on underlier).

    CDM: PerformancePayout = returnTerms + underlier + observationTerms.
    Simplified: underlier identifier + initial/final observation dates.
    """

    underlier_id: NonEmptyStr
    initial_observation_date: date
    final_observation_date: date
    currency: NonEmptyStr
    notional: PositiveDecimal

    def __post_init__(self) -> None:
        if self.initial_observation_date >= self.final_observation_date:
            raise TypeError(
                "PerformancePayoutSpec: initial_observation_date "
                f"({self.initial_observation_date}) must be < "
                f"final_observation_date ({self.final_observation_date})"
            )


# ---------------------------------------------------------------------------
# Phase C: Settlement and Exercise Terms
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class CashSettlementTerms:
    """CDM: CashSettlementTerms — parameters for cash settlement computation.

    settlement_method: ISDA settlement method (e.g. CashPriceMethod).
    valuation_date: date of valuation for settlement amount.
    currency: settlement currency.
    cash_settlement_method: CDM enum for method (optional, typed).
    cash_settlement_amount: fixed amount (optional).
    recovery_factor: fixed recovery level for Recovery Lock (0.0-1.0).
    fixed_settlement: whether fixed settlement applies.
    accrued_interest: include/exclude accrued interest.
    """

    settlement_method: NonEmptyStr
    valuation_date: date
    currency: NonEmptyStr
    cash_settlement_method: CashSettlementMethodEnum | None = None
    cash_settlement_amount: NonNegativeDecimal | None = None
    recovery_factor: Decimal | None = None
    fixed_settlement: bool | None = None
    accrued_interest: bool | None = None

    def __post_init__(self) -> None:
        if self.recovery_factor is not None:
            if not isinstance(self.recovery_factor, Decimal):
                raise TypeError(
                    "CashSettlementTerms.recovery_factor must be Decimal or None, "
                    f"got {type(self.recovery_factor).__name__}"
                )
            if not (Decimal("0") <= self.recovery_factor <= Decimal("1")):
                raise TypeError(
                    "CashSettlementTerms.recovery_factor must be in [0.0, 1.0], "
                    f"got {self.recovery_factor}"
                )
        if self.fixed_settlement is not None and not isinstance(
            self.fixed_settlement, bool
        ):
            raise TypeError(
                "CashSettlementTerms.fixed_settlement must be bool or None, "
                f"got {type(self.fixed_settlement).__name__}"
            )
        if self.accrued_interest is not None and not isinstance(
            self.accrued_interest, bool
        ):
            raise TypeError(
                "CashSettlementTerms.accrued_interest must be bool or None, "
                f"got {type(self.accrued_interest).__name__}"
            )


@final
@dataclass(frozen=True, slots=True)
class PhysicalSettlementPeriod:
    """CDM: PhysicalSettlementPeriod — physical settlement period specification.

    CDM one-of choice: businessDaysNotSpecified | businessDays | maximumBusinessDays.
    Exactly one must be set.
    """

    business_days_not_specified: bool = False
    business_days: int | None = None
    maximum_business_days: int | None = None

    def __post_init__(self) -> None:
        choices = sum([
            self.business_days_not_specified,
            self.business_days is not None,
            self.maximum_business_days is not None,
        ])
        if choices != 1:
            raise TypeError(
                "PhysicalSettlementPeriod: exactly one of "
                "business_days_not_specified, business_days, "
                f"maximum_business_days must be set (got {choices})"
            )
        if self.business_days is not None:
            if not isinstance(self.business_days, int) or isinstance(
                self.business_days, bool
            ):
                raise TypeError(
                    "PhysicalSettlementPeriod.business_days must be int, "
                    f"got {type(self.business_days).__name__}"
                )
            if self.business_days < 0:
                raise TypeError(
                    "PhysicalSettlementPeriod.business_days must be >= 0, "
                    f"got {self.business_days}"
                )
        if self.maximum_business_days is not None:
            if not isinstance(self.maximum_business_days, int) or isinstance(
                self.maximum_business_days, bool
            ):
                raise TypeError(
                    "PhysicalSettlementPeriod.maximum_business_days must be int, "
                    f"got {type(self.maximum_business_days).__name__}"
                )
            if self.maximum_business_days < 0:
                raise TypeError(
                    "PhysicalSettlementPeriod.maximum_business_days must be >= 0, "
                    f"got {self.maximum_business_days}"
                )


@final
@dataclass(frozen=True, slots=True)
class PhysicalSettlementTerms:
    """CDM: PhysicalSettlementTerms — physical settlement for CDS or option.

    delivery_period_days: legacy field (number of business days).
    settlement_currency: settlement currency.
    cleared_physical_settlement: swap clears through CCP.
    physical_settlement_period: CDM period specification (optional).
    escrow: settlement through escrow agent.
    sixty_business_day_settlement_cap: ISDA 2003 sixty-day cap.
    """

    delivery_period_days: int
    settlement_currency: NonEmptyStr
    cleared_physical_settlement: bool | None = None
    physical_settlement_period: PhysicalSettlementPeriod | None = None
    escrow: bool | None = None
    sixty_business_day_settlement_cap: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.delivery_period_days, int) or isinstance(
            self.delivery_period_days, bool
        ):
            raise TypeError(
                "PhysicalSettlementTerms.delivery_period_days must be int, "
                f"got {type(self.delivery_period_days).__name__}"
            )
        if self.delivery_period_days <= 0:
            raise TypeError(
                "PhysicalSettlementTerms.delivery_period_days must be > 0, "
                f"got {self.delivery_period_days}"
            )
        if (
            self.physical_settlement_period is not None
            and not isinstance(
                self.physical_settlement_period, PhysicalSettlementPeriod
            )
        ):
            raise TypeError(
                "PhysicalSettlementTerms.physical_settlement_period must be "
                "PhysicalSettlementPeriod or None, "
                f"got {type(self.physical_settlement_period).__name__}"
            )
        for field_name in (
            "cleared_physical_settlement", "escrow",
            "sixty_business_day_settlement_cap",
        ):
            val = getattr(self, field_name)
            if val is not None and not isinstance(val, bool):
                raise TypeError(
                    f"PhysicalSettlementTerms.{field_name} must be bool or None, "
                    f"got {type(val).__name__}"
                )


type SettlementTerms = CashSettlementTerms | PhysicalSettlementTerms


@final
@dataclass(frozen=True, slots=True)
class AmericanExercise:
    """American-style exercise: any date in [earliest, latest].

    CDM: AmericanExercise = earliestExerciseDate + latestExerciseDate.
    """

    earliest_exercise_date: date
    latest_exercise_date: date

    def __post_init__(self) -> None:
        if self.earliest_exercise_date > self.latest_exercise_date:
            raise TypeError(
                "AmericanExercise: earliest_exercise_date "
                f"({self.earliest_exercise_date}) "
                f"must be <= latest_exercise_date "
                f"({self.latest_exercise_date})"
            )


@final
@dataclass(frozen=True, slots=True)
class EuropeanExercise:
    """European-style exercise: single exercise date.

    CDM: EuropeanExercise = expirationDate.
    """

    expiration_date: date


@final
@dataclass(frozen=True, slots=True)
class BermudaExercise:
    """Bermuda-style exercise: specific discrete dates.

    CDM: BermudaExercise = bermudaExerciseDates.
    """

    exercise_dates: tuple[date, ...]

    def __post_init__(self) -> None:
        if not self.exercise_dates:
            raise TypeError(
                "BermudaExercise.exercise_dates must be non-empty"
            )
        # Verify dates are in strictly ascending order
        for i in range(1, len(self.exercise_dates)):
            if self.exercise_dates[i] <= self.exercise_dates[i - 1]:
                raise TypeError(
                    "BermudaExercise.exercise_dates must be strictly "
                    f"ascending, but date[{i}]={self.exercise_dates[i]} "
                    f"<= date[{i - 1}]={self.exercise_dates[i - 1]}"
                )


type ExerciseTerms = AmericanExercise | EuropeanExercise | BermudaExercise


# ---------------------------------------------------------------------------
# NS5b: ReturnTerms, TerminationProvision, CalculationAgent
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class ReturnTerms:
    """CDM: ReturnTerms — specifies the type of return of a performance payout.

    At least one return term must be present (CDM condition ReturnTermsExists).
    When priceReturnTerms.returnType == Total, dividendReturnTerms must exist.
    """

    price_return: bool = False
    dividend_return: bool = False
    variance_return: bool = False
    volatility_return: bool = False
    correlation_return: bool = False

    def __post_init__(self) -> None:
        if not any((
            self.price_return, self.dividend_return,
            self.variance_return, self.volatility_return,
            self.correlation_return,
        )):
            raise TypeError(
                "ReturnTerms: at least one return type must be True"
            )
        for field_name in (
            "price_return", "dividend_return", "variance_return",
            "volatility_return", "correlation_return",
        ):
            val = getattr(self, field_name)
            if not isinstance(val, bool):
                raise TypeError(
                    f"ReturnTerms.{field_name} must be bool, "
                    f"got {type(val).__name__}"
                )


@final
@dataclass(frozen=True, slots=True)
class CalculationAgent:
    """CDM: CalculationAgent — ISDA calculation agent for a product.

    calculation_agent_party references an AncillaryRoleEnum; simplified
    here to an optional NonEmptyStr identifier.
    """

    calculation_agent_party: NonEmptyStr | None = None
    calculation_agent_business_center: NonEmptyStr | None = None

    def __post_init__(self) -> None:
        if (
            self.calculation_agent_party is not None
            and not isinstance(self.calculation_agent_party, NonEmptyStr)
        ):
            raise TypeError(
                "CalculationAgent.calculation_agent_party must be "
                f"NonEmptyStr or None, "
                f"got {type(self.calculation_agent_party).__name__}"
            )


@final
@dataclass(frozen=True, slots=True)
class TerminationProvision:
    """CDM: TerminationProvision — optional provisions for contract termination.

    CDM requires choice among: cancelableProvision, earlyTerminationProvision,
    evergreenProvision, extendibleProvision, recallProvision.

    Simplified stub: flags indicating which provisions are present.
    Full sub-types will be added in later NS iterations.
    """

    cancelable: bool = False
    early_termination: bool = False
    evergreen: bool = False
    extendible: bool = False
    recallable: bool = False

    def __post_init__(self) -> None:
        # CDM required choice: at least one must be set
        if not any((
            self.cancelable, self.early_termination,
            self.evergreen, self.extendible, self.recallable,
        )):
            raise TypeError(
                "TerminationProvision: at least one provision must be True "
                "(CDM required choice)"
            )
        for field_name in (
            "cancelable", "early_termination",
            "evergreen", "extendible", "recallable",
        ):
            val = getattr(self, field_name)
            if not isinstance(val, bool):
                raise TypeError(
                    f"TerminationProvision.{field_name} must be bool, "
                    f"got {type(val).__name__}"
                )
