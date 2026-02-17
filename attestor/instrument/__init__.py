"""attestor.instrument -- Pillar II: instrument model and lifecycle."""

# CDM asset taxonomy
from attestor.instrument.asset import (
    Asset as Asset,
)
from attestor.instrument.asset import (
    AssetIdentifier as AssetIdentifier,
)
from attestor.instrument.asset import (
    AssetIdTypeEnum as AssetIdTypeEnum,
)
from attestor.instrument.asset import (
    EquityClassification as EquityClassification,
)
from attestor.instrument.asset import (
    EquityType as EquityType,
)
from attestor.instrument.asset import (
    EquityTypeEnum as EquityTypeEnum,
)
from attestor.instrument.asset import (
    FundClassification as FundClassification,
)
from attestor.instrument.asset import (
    FundProductTypeEnum as FundProductTypeEnum,
)
from attestor.instrument.asset import (
    InstrumentTypeEnum as InstrumentTypeEnum,
)
from attestor.instrument.asset import (
    Security as Security,
)
from attestor.instrument.asset import (
    SecurityClassification as SecurityClassification,
)
from attestor.instrument.asset import (
    create_equity_security as create_equity_security,
)
from attestor.instrument.asset import (
    create_fund_security as create_fund_security,
)
from attestor.instrument.credit_types import (
    CDSPayoutSpec as CDSPayoutSpec,
)
from attestor.instrument.credit_types import (
    GeneralTerms as GeneralTerms,
)
from attestor.instrument.credit_types import (
    ProtectionTerms as ProtectionTerms,
)
from attestor.instrument.credit_types import (
    SwaptionPayoutSpec as SwaptionPayoutSpec,
)

# Phase C: exercise terms, settlement terms, performance payout
from attestor.instrument.derivative_types import (
    AmericanExercise as AmericanExercise,
)
from attestor.instrument.derivative_types import (
    BermudaExercise as BermudaExercise,
)
from attestor.instrument.derivative_types import (
    CashSettlementTerms as CashSettlementTerms,
)
from attestor.instrument.derivative_types import (
    CDSDetail as CDSDetail,
)
from attestor.instrument.derivative_types import (
    CreditEventType as CreditEventType,
)
from attestor.instrument.derivative_types import (
    EquityDetail as EquityDetail,
)
from attestor.instrument.derivative_types import (
    EuropeanExercise as EuropeanExercise,
)
from attestor.instrument.derivative_types import (
    ExerciseTerms as ExerciseTerms,
)
from attestor.instrument.derivative_types import (
    FuturesDetail as FuturesDetail,
)
from attestor.instrument.derivative_types import (
    FuturesPayoutSpec as FuturesPayoutSpec,
)

# Phase 3: FX and IRS types
from attestor.instrument.derivative_types import (
    FXDetail as FXDetail,
)
from attestor.instrument.derivative_types import (
    InstrumentDetail as InstrumentDetail,
)
from attestor.instrument.derivative_types import (
    IRSwapDetail as IRSwapDetail,
)
from attestor.instrument.derivative_types import (
    MarginType as MarginType,
)
from attestor.instrument.derivative_types import (
    OptionDetail as OptionDetail,
)
from attestor.instrument.derivative_types import (
    OptionPayoutSpec as OptionPayoutSpec,
)
from attestor.instrument.derivative_types import (
    OptionStyle as OptionStyle,
)
from attestor.instrument.derivative_types import (
    OptionType as OptionType,
)
from attestor.instrument.derivative_types import (
    PerformancePayoutSpec as PerformancePayoutSpec,
)
from attestor.instrument.derivative_types import (
    PhysicalSettlementTerms as PhysicalSettlementTerms,
)
from attestor.instrument.derivative_types import (
    ProtectionSide as ProtectionSide,
)
from attestor.instrument.derivative_types import (
    RestructuringEnum as RestructuringEnum,
)
from attestor.instrument.derivative_types import (
    SeniorityLevel as SeniorityLevel,
)
from attestor.instrument.derivative_types import (
    SettlementTerms as SettlementTerms,
)
from attestor.instrument.derivative_types import (
    SettlementType as SettlementType,
)
from attestor.instrument.derivative_types import (
    SwaptionDetail as SwaptionDetail,
)
from attestor.instrument.derivative_types import (
    SwaptionType as SwaptionType,
)
from attestor.instrument.fx_types import (
    DayCountConvention as DayCountConvention,
)
from attestor.instrument.fx_types import (
    FXForwardPayoutSpec as FXForwardPayoutSpec,
)
from attestor.instrument.fx_types import (
    FXSpotPayoutSpec as FXSpotPayoutSpec,
)
from attestor.instrument.fx_types import (
    IRSwapPayoutSpec as IRSwapPayoutSpec,
)
from attestor.instrument.fx_types import (
    NDFPayoutSpec as NDFPayoutSpec,
)
from attestor.instrument.fx_types import (
    PaymentFrequency as PaymentFrequency,
)
from attestor.instrument.fx_types import (
    SwapLegType as SwapLegType,
)

# Phase C: rate specifications
from attestor.instrument.rate_spec import (
    CompoundingMethodEnum as CompoundingMethodEnum,
)
from attestor.instrument.rate_spec import (
    FixedRateSpecification as FixedRateSpecification,
)
from attestor.instrument.rate_spec import (
    FloatingRateSpecification as FloatingRateSpecification,
)
from attestor.instrument.rate_spec import (
    RateSpecification as RateSpecification,
)
from attestor.instrument.rate_spec import (
    StubPeriod as StubPeriod,
)
from attestor.instrument.types import (
    EconomicTerms as EconomicTerms,
)
from attestor.instrument.types import (
    EquityPayoutSpec as EquityPayoutSpec,
)
from attestor.instrument.types import (
    Instrument as Instrument,
)
from attestor.instrument.types import (
    Party as Party,
)
from attestor.instrument.types import (
    Payout as Payout,
)
from attestor.instrument.types import (
    Product as Product,
)
from attestor.instrument.types import (
    create_cds_instrument as create_cds_instrument,
)
from attestor.instrument.types import (
    create_equity_instrument as create_equity_instrument,
)
from attestor.instrument.types import (
    create_futures_instrument as create_futures_instrument,
)
from attestor.instrument.types import (
    create_fx_forward_instrument as create_fx_forward_instrument,
)
from attestor.instrument.types import (
    create_fx_spot_instrument as create_fx_spot_instrument,
)
from attestor.instrument.types import (
    create_irs_instrument as create_irs_instrument,
)
from attestor.instrument.types import (
    create_ndf_instrument as create_ndf_instrument,
)
from attestor.instrument.types import (
    create_option_instrument as create_option_instrument,
)
from attestor.instrument.types import (
    create_swaption_instrument as create_swaption_instrument,
)
