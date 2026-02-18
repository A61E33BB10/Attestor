"""Observable and Index taxonomy — CDM observable-asset namespace alignment.

Aligned with ISDA CDM Rosetta (observable-asset-*):
  Index = CreditIndex | EquityIndex | InterestRateIndex
        | ForeignExchangeRateIndex | OtherIndex
  InterestRateIndex = FloatingRateIndex | InflationIndex
  Observable = Asset | Basket | Index
  PriceSchedule → Price (flattened)
  PriceQuantity = price (0..*) + quantity (0..*) + observable (0..1)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Literal, final

from attestor.core.money import NonEmptyStr
from attestor.core.quantity import (
    ArithmeticOperationEnum,
    NonNegativeQuantity,
    UnitType,
)
from attestor.core.types import (
    BusinessDayAdjustments,
    Frequency,
    Period,
    RelativeDateOffset,
)

# ---------------------------------------------------------------------------
# Enums  (CDM Rosetta: observable-asset-enum.rosetta)
# ---------------------------------------------------------------------------


class PriceTypeEnum(Enum):
    """What kind of price is being quoted.

    CDM: PriceTypeEnum (exact 8 members).
    """

    ASSET_PRICE = "AssetPrice"
    CASH_PRICE = "CashPrice"
    CORRELATION = "Correlation"
    DIVIDEND = "Dividend"
    EXCHANGE_RATE = "ExchangeRate"
    INTEREST_RATE = "InterestRate"
    VARIANCE = "Variance"
    VOLATILITY = "Volatility"


class PriceExpressionEnum(Enum):
    """How the price value is expressed.

    CDM: PriceExpressionEnum (exact 4 members).
    """

    ABSOLUTE_TERMS = "AbsoluteTerms"
    PERCENTAGE_OF_NOTIONAL = "PercentageOfNotional"
    PAR_VALUE_FRACTION = "ParValueFraction"
    PER_OPTION = "PerOption"


class PriceSubTypeEnum(Enum):
    """Sub-classification of price type.

    CDM: PriceSubTypeEnum (exact 4 members).
    """

    PREMIUM = "Premium"
    FEE = "Fee"
    DISCOUNT = "Discount"
    REBATE = "Rebate"


class FeeTypeEnum(Enum):
    """Event that gave rise to a fee.

    CDM: FeeTypeEnum (exact 11 members).
    """

    ASSIGNMENT = "Assignment"
    BROKERAGE_COMMISSION = "BrokerageCommission"
    INCREASE = "Increase"
    NOVATION = "Novation"
    PARTIAL_TERMINATION = "PartialTermination"
    PREMIUM = "Premium"
    RENEGOTIATION = "Renegotiation"
    TERMINATION = "Termination"
    UPFRONT = "Upfront"
    CREDIT_EVENT = "CreditEvent"
    CORPORATE_ACTION = "CorporateAction"


class PremiumTypeEnum(Enum):
    """Premium type for forward start options.

    CDM: PremiumTypeEnum (exact 4 members).
    """

    PRE_PAID = "PrePaid"
    POST_PAID = "PostPaid"
    VARIABLE = "Variable"
    FIXED = "Fixed"


class PriceOperandEnum(Enum):
    """Qualifies the type of operand in a PriceComposite.

    CDM: PriceOperandEnum (exact 3 members).
    """

    ACCRUED_INTEREST = "AccruedInterest"
    COMMISSION = "Commission"
    FORWARD_POINT = "ForwardPoint"


class InformationProviderEnum(Enum):
    """Information source providers.

    CDM: InformationProviderEnum (exact 18 members).
    """

    ASSOC_BANKS_SINGAPORE = "AssocBanksSingapore"
    BANCO_CENTRAL_CHILE = "BancoCentralChile"
    BANK_OF_CANADA = "BankOfCanada"
    BANK_OF_ENGLAND = "BankOfEngland"
    BANK_OF_JAPAN = "BankOfJapan"
    BLOOMBERG = "Bloomberg"
    EURO_CENTRAL_BANK = "EuroCentralBank"
    FEDERAL_RESERVE = "FederalReserve"
    FHLBSF = "FHLBSF"
    ICESWAP = "ICESWAP"
    ISDA = "ISDA"
    REFINITIV = "Refinitiv"
    RESERVE_BANK_AUSTRALIA = "ReserveBankAustralia"
    RESERVE_BANK_NEW_ZEALAND = "ReserveBankNewZealand"
    REUTERS = "Reuters"
    SAFEX = "SAFEX"
    TELERATE = "Telerate"
    TOKYOSWAP = "TOKYOSWAP"


class QuoteBasisEnum(Enum):
    """How an exchange rate is quoted.

    CDM: QuoteBasisEnum (exact 2 members).
    """

    CURRENCY1_PER_CURRENCY2 = "Currency1PerCurrency2"
    CURRENCY2_PER_CURRENCY1 = "Currency2PerCurrency1"


class CreditRatingAgencyEnum(Enum):
    """Credit rating agencies.

    CDM: CreditRatingAgencyEnum (exact 8 members).
    """

    AM_BEST = "AMBest"
    CBRS = "CBRS"
    DBRS = "DBRS"
    FITCH = "Fitch"
    JAPANAGENCY = "Japanagency"
    MOODYS = "Moodys"
    RATING_AND_INVESTMENT_INFORMATION = "RatingAndInvestmentInformation"
    STANDARD_AND_POORS = "StandardAndPoors"


class CreditRatingOutlookEnum(Enum):
    """Credit rating outlook direction.

    CDM: CreditRatingOutlookEnum (exact 4 members).
    """

    POSITIVE = "Positive"
    NEGATIVE = "Negative"
    STABLE = "Stable"
    DEVELOPING = "Developing"


class CreditRatingCreditWatchEnum(Enum):
    """Credit watch rating direction.

    CDM: CreditRatingCreditWatchEnum (exact 3 members).
    """

    POSITIVE = "Positive"
    NEGATIVE = "Negative"
    DEVELOPING = "Developing"


class QuotationStyleEnum(Enum):
    """Quotation style for CDS fee legs.

    CDM: QuotationStyleEnum (exact 3 members).
    """

    POINTS_UP_FRONT = "PointsUpFront"
    TRADED_SPREAD = "TradedSpread"
    PRICE = "Price"


class ValuationMethodEnum(Enum):
    """ISDA methodology for determining final price.

    CDM: ValuationMethodEnum (exact 8 members).
    """

    MARKET = "Market"
    HIGHEST = "Highest"
    AVERAGE_MARKET = "AverageMarket"
    AVERAGE_HIGHEST = "AverageHighest"
    BLENDED_MARKET = "BlendedMarket"
    BLENDED_HIGHEST = "BlendedHighest"
    AVERAGE_BLENDED_MARKET = "AverageBlendedMarket"
    AVERAGE_BLENDED_HIGHEST = "AverageBlendedHighest"


# ---------------------------------------------------------------------------
# Floating rate indices
# ---------------------------------------------------------------------------


class FloatingRateIndexEnum(Enum):
    """Major floating rate indices.

    CDM: FloatingRateIndexEnum (~200 values). We model the ~20 most
    commonly traded indices. Expand as needed.
    """

    # Overnight rates (RFR)
    SOFR = "USD-SOFR"
    ESTR = "EUR-ESTR"
    SONIA = "GBP-SONIA"
    TONA = "JPY-TONA"
    SARON = "CHF-SARON"
    AONIA = "AUD-AONIA"
    CORRA = "CAD-CORRA"
    # IBOR rates
    EURIBOR = "EUR-EURIBOR"
    TIBOR = "JPY-TIBOR"
    BBSW = "AUD-BBSW"
    CDOR = "CAD-CDOR"
    HIBOR = "HKD-HIBOR"
    SIBOR = "SGD-SIBOR"
    KLIBOR = "MYR-KLIBOR"
    JIBAR = "ZAR-JIBAR"
    # Legacy (still used in outstanding contracts)
    USD_LIBOR = "USD-LIBOR"
    GBP_LIBOR = "GBP-LIBOR"
    CHF_LIBOR = "CHF-LIBOR"
    JPY_LIBOR = "JPY-LIBOR"
    EUR_LIBOR = "EUR-LIBOR"


class InflationRateIndexEnum(Enum):
    """Major inflation rate indices.

    CDM: InflationRateIndexEnum (~60 values). We model the ~10 most
    commonly referenced. Expand as needed.
    """

    USA_CPI_U = "USA-CPI-U"
    EUR_HICP = "EUR-HICP"
    GBP_RPI = "GBP-RPI"
    FRA_CPI = "FRA-CPI"
    AUS_CPI = "AUS-CPI"
    JPN_CPI = "JPN-CPI"
    ITA_CPI = "ITA-CPI"
    SWE_CPI = "SWE-CPI"
    CAN_CPI = "CAN-CPI"
    BRA_IPCA = "BRA-IPCA"


class EquityIndexEnum(Enum):
    """Major equity indices.

    CDM: EquityIndexEnum (~340 values). We model the ~30 most
    commonly traded. Expand as needed.
    """

    SP500 = "SP500"
    DOWI = "DOWI"
    NASDAQ = "NASDAQ"
    RU2000 = "RU2000"
    DJES50 = "DJES50"
    FT100 = "FT100"
    DAX = "DAX"
    CAC40 = "CAC40"
    SPMIB = "SPMIB"
    IBEX35 = "IBEX35"
    SMI = "SMI"
    AEX = "AEX"
    NIKKEI = "NIKKEI"
    TOPIX = "TOPIX"
    HSENG = "HSENG"
    HSCEI = "HSCEI"
    ASX200 = "ASX200"
    KSPI = "KSPI"
    TWSE = "TWSE"
    BOVESP = "BOVESP"
    CSSC = "CSSC"
    S300 = "S300"
    INSPCN = "INSPCN"
    INSENS = "INSENS"
    SNGSTR = "SNGSTR"
    TSE300 = "TSE300"
    OMX = "OMX"
    ATX = "ATX"
    PSI = "PSI"


# ---------------------------------------------------------------------------
# Calculated rate enums  (observable-asset-calculatedrate-enum.rosetta)
# ---------------------------------------------------------------------------


class CalculationMethodEnum(Enum):
    """How floating rate resets are combined over a period.

    CDM: CalculationMethodEnum (exact 3 members).
    """

    COMPOUNDING = "Compounding"
    AVERAGING = "Averaging"
    COMPOUNDED_INDEX = "CompoundedIndex"


# ---------------------------------------------------------------------------
# Supporting types  (observable-asset-type.rosetta)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class InformationSource:
    """Source for obtaining market data.

    CDM: InformationSource = sourceProvider (1..1)
         + sourcePage (0..1) + sourcePageHeading (0..1).
    """

    source_provider: InformationProviderEnum
    source_page: NonEmptyStr | None = None
    source_page_heading: NonEmptyStr | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_provider, InformationProviderEnum):
            raise TypeError(
                f"InformationSource.source_provider must be "
                f"InformationProviderEnum, "
                f"got {type(self.source_provider).__name__}"
            )


@final
@dataclass(frozen=True, slots=True)
class QuotedCurrencyPair:
    """Composition of an FX rate quotation.

    CDM: QuotedCurrencyPair = currency1 (1..1)
         + currency2 (1..1) + quoteBasis (1..1).
    """

    currency1: NonEmptyStr
    currency2: NonEmptyStr
    quote_basis: QuoteBasisEnum

    def __post_init__(self) -> None:
        if not isinstance(self.currency1, NonEmptyStr):
            raise TypeError(
                f"QuotedCurrencyPair.currency1 must be NonEmptyStr, "
                f"got {type(self.currency1).__name__}"
            )
        if not isinstance(self.currency2, NonEmptyStr):
            raise TypeError(
                f"QuotedCurrencyPair.currency2 must be NonEmptyStr, "
                f"got {type(self.currency2).__name__}"
            )
        if not isinstance(self.quote_basis, QuoteBasisEnum):
            raise TypeError(
                f"QuotedCurrencyPair.quote_basis must be QuoteBasisEnum, "
                f"got {type(self.quote_basis).__name__}"
            )
        if self.currency1.value == self.currency2.value:
            raise TypeError(
                f"QuotedCurrencyPair: currency1 and currency2 must differ, "
                f"both are '{self.currency1.value}'"
            )


@final
@dataclass(frozen=True, slots=True)
class PriceComposite:
    """Composite of two price values.

    CDM: PriceComposite = baseValue + operand + arithmeticOperator
         + operandType (0..1).
    Invariant: if operandType is ForwardPoint or AccruedInterest,
    operator must be Add or Subtract.
    """

    base_value: Decimal
    operand: Decimal
    arithmetic_operator: ArithmeticOperationEnum
    operand_type: PriceOperandEnum | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.base_value, Decimal) or not self.base_value.is_finite():
            raise TypeError(
                f"PriceComposite.base_value must be finite Decimal, "
                f"got {self.base_value!r}"
            )
        if not isinstance(self.operand, Decimal) or not self.operand.is_finite():
            raise TypeError(
                f"PriceComposite.operand must be finite Decimal, "
                f"got {self.operand!r}"
            )
        if not isinstance(self.arithmetic_operator, ArithmeticOperationEnum):
            raise TypeError(
                f"PriceComposite.arithmetic_operator must be "
                f"ArithmeticOperationEnum, "
                f"got {type(self.arithmetic_operator).__name__}"
            )
        # CDM condition: if operandType is ForwardPoint or AccruedInterest,
        # operator must be Add or Subtract
        if self.operand_type in (
            PriceOperandEnum.FORWARD_POINT,
            PriceOperandEnum.ACCRUED_INTEREST,
        ) and self.arithmetic_operator not in (
            ArithmeticOperationEnum.ADD,
            ArithmeticOperationEnum.SUBTRACT,
        ):
            raise TypeError(
                f"PriceComposite: when operand_type is "
                f"{self.operand_type!r}, arithmetic_operator must be "
                f"Add or Subtract, got {self.arithmetic_operator!r}"
            )


# ---------------------------------------------------------------------------
# Index types  (observable-asset-type.rosetta)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class FloatingRateIndex:
    """A specific floating rate index with its designated maturity.

    CDM: FloatingRateIndex extends IndexBase
         = floatingRateIndex (1..1) + indexTenor (0..1).
    """

    index: FloatingRateIndexEnum
    designated_maturity: Period  # e.g. Period(3, "M") for 3M EURIBOR

    def __post_init__(self) -> None:
        if not isinstance(self.index, FloatingRateIndexEnum):
            raise TypeError(
                "FloatingRateIndex.index must be FloatingRateIndexEnum, "
                f"got {type(self.index).__name__}"
            )
        if not isinstance(self.designated_maturity, Period):
            raise TypeError(
                "FloatingRateIndex.designated_maturity must be Period, "
                f"got {type(self.designated_maturity).__name__}"
            )


@final
@dataclass(frozen=True, slots=True)
class InflationIndex:
    """Inflation rate index (e.g. US CPI-U, EUR HICP).

    CDM: InflationIndex extends IndexBase
         = inflationRateIndex (1..1) + indexTenor (0..1).
    """

    inflation_rate_index: InflationRateIndexEnum
    index_tenor: Period | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.inflation_rate_index, InflationRateIndexEnum):
            raise TypeError(
                "InflationIndex.inflation_rate_index must be "
                "InflationRateIndexEnum, "
                f"got {type(self.inflation_rate_index).__name__}"
            )
        if self.index_tenor is not None and not isinstance(
            self.index_tenor, Period
        ):
            raise TypeError(
                "InflationIndex.index_tenor must be Period, "
                f"got {type(self.index_tenor).__name__}"
            )


type InterestRateIndex = FloatingRateIndex | InflationIndex


@final
@dataclass(frozen=True, slots=True)
class CreditIndex:
    """Credit default swap index (e.g. CDX.NA.IG, iTraxx Europe).

    CDM: CreditIndex extends IndexBase = indexSeries + indexAnnexVersion
         + indexAnnexDate + indexAnnexSource + indexFactor + seniority
         + excludedReferenceEntity + tranche + settledEntityMatrix.

    Attestor models the fields directly referenced by equity-trade
    critical path and CDS index basics.
    """

    index_name: NonEmptyStr
    index_series: int | None = None
    index_annex_version: int | None = None
    index_annex_date: date | None = None
    index_factor: Decimal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.index_name, NonEmptyStr):
            raise TypeError(
                "CreditIndex.index_name must be NonEmptyStr, "
                f"got {type(self.index_name).__name__}"
            )
        if self.index_series is not None:
            if not isinstance(self.index_series, int) or isinstance(
                self.index_series, bool
            ):
                raise TypeError(
                    "CreditIndex.index_series must be int, "
                    f"got {type(self.index_series).__name__}"
                )
            if self.index_series < 0:
                raise TypeError(
                    f"CreditIndex.index_series must be >= 0, "
                    f"got {self.index_series}"
                )
        if self.index_annex_version is not None:
            if not isinstance(self.index_annex_version, int) or isinstance(
                self.index_annex_version, bool
            ):
                raise TypeError(
                    "CreditIndex.index_annex_version must be int, "
                    f"got {type(self.index_annex_version).__name__}"
                )
            if self.index_annex_version < 0:
                raise TypeError(
                    f"CreditIndex.index_annex_version must be >= 0, "
                    f"got {self.index_annex_version}"
                )
        if self.index_factor is not None:
            if not isinstance(self.index_factor, Decimal):
                raise TypeError(
                    "CreditIndex.index_factor must be Decimal, "
                    f"got {type(self.index_factor).__name__}"
                )
            if self.index_factor < 0 or self.index_factor > 1:
                raise TypeError(
                    f"CreditIndex.index_factor must be in [0, 1], "
                    f"got {self.index_factor}"
                )


@final
@dataclass(frozen=True, slots=True)
class EquityIndex:
    """Equity index reference (e.g. S&P 500, EURO STOXX 50).

    CDM: EquityIndex extends IndexBase = equityIndex (0..1).
    Condition: if equityIndex exists then name is absent.
    """

    index_name: NonEmptyStr | None = None
    equity_index: EquityIndexEnum | None = None

    def __post_init__(self) -> None:
        if self.index_name is not None and not isinstance(
            self.index_name, NonEmptyStr
        ):
            raise TypeError(
                "EquityIndex.index_name must be NonEmptyStr, "
                f"got {type(self.index_name).__name__}"
            )
        if self.equity_index is not None and not isinstance(
            self.equity_index, EquityIndexEnum
        ):
            raise TypeError(
                "EquityIndex.equity_index must be EquityIndexEnum, "
                f"got {type(self.equity_index).__name__}"
            )
        # CDM condition: one must be set, and if equityIndex then name absent
        if self.index_name is None and self.equity_index is None:
            raise TypeError(
                "EquityIndex: at least one of index_name or equity_index "
                "must be set"
            )
        if self.index_name is not None and self.equity_index is not None:
            raise TypeError(
                "EquityIndex: index_name and equity_index are mutually "
                "exclusive (CDM IndexSourceSpecification)"
            )


@final
@dataclass(frozen=True, slots=True)
class ForeignExchangeRateIndex:
    """FX rate source for fixings.

    CDM: ForeignExchangeRateIndex extends IndexBase
         = quotedCurrencyPair (1..1) + primaryFxSpotRateSource (1..1)
         + secondaryFxSpotRateSource (0..1).
    """

    quoted_currency_pair: QuotedCurrencyPair
    primary_source: InformationSource
    secondary_source: InformationSource | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.quoted_currency_pair, QuotedCurrencyPair):
            raise TypeError(
                "ForeignExchangeRateIndex.quoted_currency_pair must be "
                "QuotedCurrencyPair, "
                f"got {type(self.quoted_currency_pair).__name__}"
            )
        if not isinstance(self.primary_source, InformationSource):
            raise TypeError(
                "ForeignExchangeRateIndex.primary_source must be "
                "InformationSource, "
                f"got {type(self.primary_source).__name__}"
            )
        if self.secondary_source is not None and not isinstance(
            self.secondary_source, InformationSource
        ):
            raise TypeError(
                "ForeignExchangeRateIndex.secondary_source must be "
                "InformationSource or None, "
                f"got {type(self.secondary_source).__name__}"
            )


@final
@dataclass(frozen=True, slots=True)
class OtherIndex:
    """User-defined index not matching standard categories.

    CDM: OtherIndex extends IndexBase = description (0..1).
    Condition: assetClass must exist (Attestor: required name).
    """

    index_name: NonEmptyStr
    description: NonEmptyStr | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.index_name, NonEmptyStr):
            raise TypeError(
                "OtherIndex.index_name must be NonEmptyStr, "
                f"got {type(self.index_name).__name__}"
            )


# ---------------------------------------------------------------------------
# Index and Observable unions  (CDM choices)
# ---------------------------------------------------------------------------

type Index = (
    FloatingRateIndex
    | InflationIndex
    | CreditIndex
    | EquityIndex
    | ForeignExchangeRateIndex
    | OtherIndex
)

type Asset = NonEmptyStr  # Simplified: asset identifier (e.g. ISIN, ticker)

type Basket = NonEmptyStr  # Stub: basket identifier; expand to full type later

type Observable = Asset | Basket | Index


# ---------------------------------------------------------------------------
# Price types  (CDM PriceSchedule → Price flattened)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class Price:
    """A price observation with type, expression, and optional composition.

    CDM: Price extends PriceSchedule extends MeasureSchedule.
    Attestor flattens the inheritance chain.  Fields:
      value (1..1), unit/currency (1..1), priceType (1..1),
      priceExpression (0..1), perUnitOf (0..1), priceSubType (0..1),
      composite (0..1), arithmeticOperator (0..1), premiumType (0..1).

    CDM Conditions:
      PositiveAssetPrice: ExchangeRate/AssetPrice without operator → value > 0
      PositiveCashPrice: CashPrice → value > 0
      CurrencyUnitForInterestRate: InterestRate → unit is currency
      Choice: arithmeticOperator and composite are mutually exclusive
      Premium: premiumType → priceSubType == Premium
      ArithmeticOperator: operator must not be Subtract or Divide
    """

    value: Decimal
    currency: NonEmptyStr
    price_type: PriceTypeEnum
    price_expression: PriceExpressionEnum | None = None
    per_unit_of: UnitType | None = None
    price_sub_type: PriceSubTypeEnum | None = None
    composite: PriceComposite | None = None
    arithmetic_operator: ArithmeticOperationEnum | None = None
    premium_type: PremiumTypeEnum | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise TypeError(
                f"Price.value must be finite Decimal, got {self.value!r}"
            )
        if not isinstance(self.currency, NonEmptyStr):
            raise TypeError(
                f"Price.currency must be NonEmptyStr, "
                f"got {type(self.currency).__name__}"
            )
        if not isinstance(self.price_type, PriceTypeEnum):
            raise TypeError(
                f"Price.price_type must be PriceTypeEnum, "
                f"got {type(self.price_type).__name__}"
            )
        # CDM PositiveAssetPrice: ExchangeRate/AssetPrice w/o operator → > 0
        if (
            self.price_type
            in (PriceTypeEnum.EXCHANGE_RATE, PriceTypeEnum.ASSET_PRICE)
            and self.arithmetic_operator is None
            and self.value <= 0
        ):
            raise TypeError(
                f"Price: {self.price_type.name} without arithmetic_operator "
                f"must have value > 0, got {self.value}"
            )
        # CDM PositiveCashPrice: CashPrice → value > 0
        if self.price_type == PriceTypeEnum.CASH_PRICE and self.value <= 0:
            raise TypeError(
                f"Price: CashPrice must have value > 0, got {self.value}"
            )
        # CDM Choice: arithmeticOperator and composite mutually exclusive
        if self.arithmetic_operator is not None and self.composite is not None:
            raise TypeError(
                "Price: arithmetic_operator and composite are "
                "mutually exclusive (CDM Choice condition)"
            )
        # CDM Premium: premiumType → priceSubType == Premium
        if (
            self.premium_type is not None
            and self.price_sub_type != PriceSubTypeEnum.PREMIUM
        ):
            raise TypeError(
                "Price: premium_type requires price_sub_type == PREMIUM"
            )
        # CDM ArithmeticOperator: must not be Subtract or Divide
        if self.arithmetic_operator in (
            ArithmeticOperationEnum.SUBTRACT,
            ArithmeticOperationEnum.DIVIDE,
        ):
            raise TypeError(
                f"Price: arithmetic_operator must not be Subtract or "
                f"Divide, got {self.arithmetic_operator!r}"
            )
        # CDM PositiveSpotRate: ExchangeRate/AssetPrice with composite
        # → composite.base_value > 0
        if (
            self.price_type
            in (PriceTypeEnum.EXCHANGE_RATE, PriceTypeEnum.ASSET_PRICE)
            and self.composite is not None
            and self.composite.base_value <= 0
        ):
            raise TypeError(
                f"Price: {self.price_type.name} composite base_value "
                f"must be > 0 (CDM PositiveSpotRate), "
                f"got {self.composite.base_value}"
            )
        # CDM PremiumSubType: priceSubType == Premium → priceType == CashPrice
        if (
            self.price_sub_type == PriceSubTypeEnum.PREMIUM
            and self.price_type != PriceTypeEnum.CASH_PRICE
        ):
            raise TypeError(
                "Price: price_sub_type PREMIUM requires "
                "price_type == CASH_PRICE (CDM PremiumSubType)"
            )
        # CDM SpreadPrice: arithmeticOperator == Add → priceType in
        # {AssetPrice, InterestRate}
        if (
            self.arithmetic_operator == ArithmeticOperationEnum.ADD
            and self.price_type
            not in (PriceTypeEnum.ASSET_PRICE, PriceTypeEnum.INTEREST_RATE)
        ):
            raise TypeError(
                f"Price: arithmetic_operator Add requires price_type "
                f"AssetPrice or InterestRate (CDM SpreadPrice), "
                f"got {self.price_type.name}"
            )
        # CDM ForwardPoint: composite.operand_type == ForwardPoint
        # → priceType == ExchangeRate
        if (
            self.composite is not None
            and self.composite.operand_type == PriceOperandEnum.FORWARD_POINT
            and self.price_type != PriceTypeEnum.EXCHANGE_RATE
        ):
            raise TypeError(
                "Price: ForwardPoint operand requires price_type == "
                "ExchangeRate (CDM ForwardPoint condition)"
            )
        # CDM AccruedInterest: composite.operand_type == AccruedInterest
        # → priceType == AssetPrice
        if (
            self.composite is not None
            and self.composite.operand_type
            == PriceOperandEnum.ACCRUED_INTEREST
            and self.price_type != PriceTypeEnum.ASSET_PRICE
        ):
            raise TypeError(
                "Price: AccruedInterest operand requires price_type == "
                "AssetPrice (CDM AccruedInterest condition)"
            )


@final
@dataclass(frozen=True, slots=True)
class PriceQuantity:
    """Coupling of price(s), quantity(ies), and the observable being priced.

    CDM: PriceQuantity = price (0..*) + quantity (0..*) + observable (0..1)
         + effectiveDate (0..1).

    All fields are optional per CDM spec.  Tuples represent 0..*.
    """

    price: tuple[Price, ...] = ()
    quantity: tuple[NonNegativeQuantity, ...] = ()
    observable: Observable | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.price, tuple):
            raise TypeError(
                f"PriceQuantity.price must be tuple, "
                f"got {type(self.price).__name__}"
            )
        for i, p in enumerate(self.price):
            if not isinstance(p, Price):
                raise TypeError(
                    f"PriceQuantity.price[{i}] must be Price, "
                    f"got {type(p).__name__}"
                )
        if not isinstance(self.quantity, tuple):
            raise TypeError(
                f"PriceQuantity.quantity must be tuple, "
                f"got {type(self.quantity).__name__}"
            )
        for i, q in enumerate(self.quantity):
            if not isinstance(q, NonNegativeQuantity):
                raise TypeError(
                    f"PriceQuantity.quantity[{i}] must be NonNegativeQuantity, "
                    f"got {type(q).__name__}"
                )


@final
@dataclass(frozen=True, slots=True)
class ObservationIdentifier:
    """Identifies a specific observation: what, when, from where.

    CDM: ObservationIdentifier = observable + observationDate + source.
    """

    observable: Observable
    observation_date: date
    source: NonEmptyStr

    def __post_init__(self) -> None:
        if not isinstance(self.observation_date, date):
            raise TypeError(
                "ObservationIdentifier.observation_date must be date, "
                f"got {type(self.observation_date).__name__}"
            )
        if not isinstance(self.source, NonEmptyStr):
            raise TypeError(
                "ObservationIdentifier.source must be NonEmptyStr, "
                f"got {type(self.source).__name__}"
            )


# ---------------------------------------------------------------------------
# Floating rate calculation parameters
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class FloatingRateCalculationParameters:
    """Parameters for overnight rate compounding/averaging.

    CDM: FloatingRateCalculationParameters = calculationMethod
         + applicableBusinessDays + lookbackDays + lockoutDays + shiftDays.
    """

    calculation_method: CalculationMethodEnum
    applicable_business_days: frozenset[str]
    lookback_days: int
    lockout_days: int
    shift_days: int

    def __post_init__(self) -> None:
        if not isinstance(self.calculation_method, CalculationMethodEnum):
            raise TypeError(
                "FloatingRateCalculationParameters.calculation_method "
                "must be CalculationMethodEnum, "
                f"got {type(self.calculation_method).__name__}"
            )
        for name in ("lookback_days", "lockout_days", "shift_days"):
            val = getattr(self, name)
            if not isinstance(val, int) or isinstance(val, bool):
                raise TypeError(
                    f"FloatingRateCalculationParameters.{name} must be int, "
                    f"got {type(val).__name__}"
                )
            if val < 0:
                raise TypeError(
                    f"FloatingRateCalculationParameters.{name} "
                    f"must be >= 0, got {val}"
                )


# ---------------------------------------------------------------------------
# Reset dates
# ---------------------------------------------------------------------------


type ResetRelativeTo = Literal[
    "CalculationPeriodStartDate", "CalculationPeriodEndDate",
]


@final
@dataclass(frozen=True, slots=True)
class ResetDates:
    """Floating rate reset schedule parameters.

    CDM: ResetDates = resetFrequency + fixingDatesOffset
         + resetRelativeTo + calculationParameters.
    """

    reset_frequency: Frequency
    fixing_dates_offset: RelativeDateOffset
    reset_relative_to: ResetRelativeTo
    calculation_parameters: FloatingRateCalculationParameters | None
    business_day_adjustments: BusinessDayAdjustments
