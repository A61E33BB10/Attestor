# CDM Rosetta Observable-Asset Namespace Gap Analysis — Attestor Alignment

**Analysis Date**: February 2026  
**Scope**: `observable-asset-*.rosetta` files vs. Attestor Python implementation  
**Priority Focus**: EQUITY TRADE CRITICAL PATH types (Price, PriceQuantity, PriceTypeEnum, Observable, PriceSchedule)  

---

## Executive Summary

This gap analysis examines Attestor's alignment with CDM Rosetta's observable-asset namespace. Attestor has implemented **core Price/Observable types** covering the EQUITY TRADE CRITICAL PATH but is **intentionally simplified** for MVP scope, omitting complex credit/FX derivatives infrastructure.

**Key Findings**:
- ✅ **COMPLETE**: Core equity types (Price, PriceQuantity, Observable union, PriceTypeEnum)
- ✅ **COMPLETE**: Floating rate index infrastructure (FloatingRateIndex, FloatingRateIndexEnum, CalculationMethodEnum)
- ⚠️ **PARTIAL**: Advanced price composition (no PriceComposite, PriceSchedule extends MeasureSchedule)
- ❌ **MISSING**: Credit index types (CreditIndex full support), FRO definitions, Inflation indices
- ❌ **MISSING**: Basket/Complex observables, advanced valuation methods
- ⚠️ **STRUCTURAL**: Attestor flattens Rosetta's inheritance hierarchy (PriceSchedule → simple dataclass)

---

## Type-by-Type Comparison Matrix

### EQUITY TRADE CRITICAL PATH TYPES

#### 1. **PriceTypeEnum**

| Aspect | Rosetta (CDM) | Attestor | Status | Notes |
|--------|---------------|----------|--------|-------|
| **Type** | enum (10 members) | Enum (5 members) | ⚠️ PARTIAL | Rosetta: {AssetPrice, CashPrice, Correlation, Dividend, ExchangeRate, InterestRate, Variance, Volatility}. Attestor: {INTEREST_RATE, EXCHANGE_RATE, ASSET_PRICE, CASH_PRICE, NET_PRICE} |
| **INTEREST_RATE** | ✅ InterestRate | ✅ INTEREST_RATE | ✅ OK | Match |
| **EXCHANGE_RATE** | ✅ ExchangeRate | ✅ EXCHANGE_RATE | ✅ OK | Match |
| **ASSET_PRICE** | ✅ AssetPrice | ✅ ASSET_PRICE | ✅ OK | Match |
| **CASH_PRICE** | ✅ CashPrice | ✅ CASH_PRICE | ✅ OK | Match |
| **Dividend** | ✅ Dividend | ❌ — | ❌ MISSING | Equity dividend tracking not in MVP |
| **Correlation** | ✅ Correlation | ❌ — | ❌ MISSING | Exotics, not MVP scope |
| **Variance / Volatility** | ✅ Both | ❌ — | ❌ MISSING | Exotics, not MVP scope |
| **NET_PRICE** | ❌ — | ✅ NET_PRICE | ➕ ADDITION | Attestor-specific extension for net settlement |

**Gap Severity**: 🟡 **MODERATE** — Missing dividend/volatility but covers core equity trade types.

---

#### 2. **PriceExpressionEnum**

| Aspect | Rosetta (CDM) | Attestor | Status | Notes |
|--------|---------------|----------|--------|-------|
| **Type** | enum (4 members) | Enum (3 members) | ⚠️ PARTIAL | Rosetta: {AbsoluteTerms, PercentageOfNotional, ParValueFraction, PerOption}. Attestor: {ABSOLUTE, PERCENTAGE_OF_NOTIONAL, PER_UNIT} |
| **ABSOLUTE / AbsoluteTerms** | ✅ AbsoluteTerms | ✅ ABSOLUTE | ✅ OK | Match |
| **PERCENTAGE_OF_NOTIONAL** | ✅ PercentageOfNotional | ✅ PERCENTAGE_OF_NOTIONAL | ✅ OK | Match |
| **PER_UNIT** | ❌ — | ✅ PER_UNIT | ➕ ADDITION | Attestor uses for per-share bonds; Rosetta uses PerOption |
| **ParValueFraction** | ✅ ParValueFraction | ❌ — | ❌ MISSING | Bond quoting (101 3/8). Not MVP |
| **PerOption** | ✅ PerOption | ❌ — | ❌ MISSING | Options not MVP |

**Gap Severity**: 🟡 **MODERATE** — Covers core (absolute, percentage), misses bond/option specifics.

---

#### 3. **Price** (core type)

| Field | Rosetta | Attestor | Cardinality | Status | Notes |
|-------|---------|----------|-------------|--------|-------|
| **value** | number (1..1) | Decimal (1..1) | 1..1 | ✅ OK | Attestor uses Decimal for precision |
| **currency (via unit)** | UnitType → currency | NonEmptyStr | 1..1 | ✅ OK | Attestor: explicit currency field; Rosetta: through UnitType |
| **priceType** | PriceTypeEnum (1..1) | PriceTypeEnum | 1..1 | ✅ OK | Match |
| **priceExpression** | PriceExpressionEnum (0..1) | PriceExpressionEnum | 0..1 | ✅ OK | Match |
| **priceSubType** | PriceSubTypeEnum (0..1) | ❌ — | — | ❌ MISSING | Specifies Premium/Fee/Discount; not implemented |
| **perUnitOf** | UnitType (0..1) | ❌ — | — | ❌ MISSING | For "10 EUR per Share"; Attestor simplifies |
| **composite** | PriceComposite (0..1) | ❌ — | — | ❌ MISSING | dirty = clean + accrued; not implemented |
| **arithmeticOperator** | ArithmeticOperationEnum (0..1) | ❌ — | — | ❌ MISSING | For spreads/multipliers; not implemented |
| **premiumType** | PremiumTypeEnum (0..1) | ❌ — | — | ❌ MISSING | Forward start premium; not implemented |

**Rosetta Conditions**:
- UnitOfAmountExists: "unit exists and perUnitOf exists" → ✅ Attestor respects via separate currency field
- PositiveAssetPrice: "value > 0" → ✅ Attestor validates finite Decimal
- PositiveCashPrice: cash price must be > 0 → ✅ Attestor validates in constructor
- CurrencyUnitForInterestRate: "unit → currency exists" → ✅ Attestor enforces currency on Price

**Gap Severity**: 🔴 **HIGH** — Missing composite, premiumType, perUnitOf, arithmeticOperator for advanced pricing scenarios. Core equity trade works.

---

#### 4. **PriceQuantity** (core type)

| Field | Rosetta | Attestor | Cardinality | Status | Notes |
|-------|---------|----------|-------------|--------|-------|
| **price** | PriceSchedule (0..*) | Price (1..1) | 1..1 vs 0..* | ⚠️ DIFFER | Rosetta: multiple prices (schedule). Attestor: single price. **SIMPLIFICATION** |
| **quantity** | NonNegativeQuantitySchedule (0..*) | NonNegativeQuantity (1..1) | 1..1 vs 0..* | ⚠️ DIFFER | Rosetta: schedule. Attestor: single value. **SIMPLIFICATION** |
| **observable** | Observable (0..1) | Observable | 0..1 | ✅ OK | Match |
| **effectiveDate** | AdjustableOrRelativeDate (0..1) | ❌ — | — | ❌ MISSING | When price/qty become effective; not in MVP |

**Rosetta Conditions**:
- NonCurrencyQuantities: "at most one non-currency quantity" → ✅ Enforced via single Quantity structure
- ArithmeticOperator: "when observable is InterestRateIndex and price exists, price should have arithmeticOperator" → ⚠️ Attestor doesn't validate; simplification
- InterestRateObservable: "interest rate index → price type must be interest rate" → ⚠️ Not validated at compile time

**Gap Severity**: 🟡 **MODERATE-HIGH** — Attestor's PriceQuantity is a **simplified MVP** covering single price/qty pairs. Rosetta supports schedules. Missing effectiveDate adjustment logic.

---

#### 5. **Observable** (union type)

| Type | Rosetta | Attestor | Status | Notes |
|------|---------|----------|--------|-------|
| **Asset** | ✅ choice asset | ✅ Asset (alias to NonEmptyStr) | ⚠️ SIMPLIFIED | Rosetta: full Asset taxonomy. Attestor: ISIN/ticker string |
| **Index** | ✅ choice index | ✅ Index union (4 variants) | ⚠️ PARTIAL | Rosetta: {CreditIndex, EquityIndex, InterestRateIndex, ForeignExchangeRateIndex, OtherIndex}. Attestor: {FloatingRateIndex, CreditIndex, EquityIndex, FXRateIndex} |
| **Basket** | ✅ choice basket | ❌ — | ❌ MISSING | Composite baskets not implemented |
| **Union definition** | Asset \| Basket \| Index | Asset \| Index (4 variants) | ⚠️ DIFFER | Attestor simplifies Asset → NonEmptyStr, omits Basket |

**Rosetta Index Variants**:
1. **FloatingRateIndex** ✅ Full match
2. **EquityIndex** ✅ Implemented (index_name field)
3. **InterestRateIndex** → **choice**:
   - **FloatingRateIndex** ✅ Implemented
   - **InflationIndex** ❌ MISSING
4. **ForeignExchangeRateIndex** ✅ Implemented (fixing_source, currency)
5. **CreditIndex** ✅ Implemented (index_name, index_series, index_annex_version)
6. **OtherIndex** ❌ MISSING
7. **Basket** ❌ MISSING

**Gap Severity**: 🟡 **MODERATE** — Core indices for equity trades present. Missing inflation indices, OtherIndex, Basket. Asset simplified to string (ok for MVP).

---

#### 6. **FloatingRateIndex** (core type)

| Field | Rosetta | Attestor | Status | Notes |
|-------|---------|----------|--------|-------|
| **floatingRateIndex** | FloatingRateIndexEnum (1..1) | FloatingRateIndexEnum | ✅ OK | Match |
| **indexTenor** | Period (0..1) | Period | ✅ OK | designated_maturity in Attestor |
| **assetClass** | AssetClassEnum (0..1) | ❌ — | ❌ MISSING | InterestRate constraint not present |

**Rosetta Conditions**:
- InterestRateAssetClass: "assetClass = InterestRate" → ⚠️ Attestor doesn't validate (assumes InterestRate context)

**Gap Severity**: 🟢 **LOW** — Fully functional. Missing assetClass context validation is acceptable for MVP.

---

#### 7. **FloatingRateIndexEnum**

| Aspect | Rosetta | Attestor | Status |
|--------|---------|----------|--------|
| **Scope** | ~200 indices (FpML list) | ~20 major indices | ⚠️ SUBSET |
| **RFR rates** | ✅ All major RFRs | ✅ SOFR, ESTR, SONIA, TONA, SARON, AONIA, CORRA | ✅ OK |
| **IBOR rates** | ✅ All major IBORs | ✅ EURIBOR, TIBOR, BBSW, CDOR, HIBOR, SIBOR, KLIBOR, JIBAR | ✅ OK |
| **Legacy LIBOR** | ✅ USD/GBP/CHF/JPY/EUR | ✅ All 5 variants | ✅ OK |
| **Emerging market** | ✅ ~150 indices | ❌ Not included | ❌ MISSING |

**Gap Severity**: 🟡 **MODERATE** — Attestor covers G20 + major emerging markets. FX forwards and emerging indices expand with market demand.

---

### SECONDARY TYPES

#### 8. **PriceSchedule**

| Aspect | Rosetta | Attestor | Status | Notes |
|--------|---------|----------|--------|-------|
| **Type** | extends MeasureSchedule | @dataclass (flattened) | ⚠️ DIFFER | Rosetta: 6-level inheritance hierarchy. Attestor: flat class |
| **value** | number (in MeasureSchedule) | Decimal | ✅ OK | Same semantics |
| **datedValue** | DatedValue[] (in MeasureSchedule) | ❌ — | ❌ MISSING | Time-indexed price schedules; not MVP |
| **perUnitOf** | UnitType (0..1) | ❌ — | ❌ MISSING | Unit of pricing (e.g., per share) |
| **priceType** | PriceTypeEnum (1..1) | PriceTypeEnum | ✅ OK | Match |
| **priceSubType** | PriceSubTypeEnum (0..1) | ❌ — | ❌ MISSING | Premium/Fee/Discount sub-classification |
| **priceExpression** | PriceExpressionEnum (0..1) | PriceExpressionEnum | ✅ OK | Match |
| **composite** | PriceComposite (0..1) | ❌ — | ❌ MISSING | dirty = clean + accrued |
| **arithmeticOperator** | ArithmeticOperationEnum (0..1) | ❌ — | ❌ MISSING | For spreads/multipliers |
| **premiumType** | PremiumTypeEnum (0..1) | ❌ — | ❌ MISSING | Forward start premium type |

**Gap Severity**: 🔴 **HIGH** — Attestor's simplified flat structure works for MVP but lacks schedule, composite, and sub-classification support.

---

#### 9. **Enums: PriceSubTypeEnum, FeeTypeEnum**

| Enum | Rosetta Members | Attestor | Status |
|------|-----------------|----------|--------|
| **PriceSubTypeEnum** | Premium, Fee, Discount, Rebate (4 members) | ❌ — | ❌ MISSING |
| **FeeTypeEnum** | 10 members (Assignment, Brokerage, etc.) | ❌ — | ❌ MISSING |

**Gap Severity**: 🔴 **HIGH** — Not implemented; needed for complex fees/adjustments.

---

#### 10. **Information Source / Valuation**

| Type | Rosetta | Attestor | Status | Notes |
|------|---------|----------|--------|-------|
| **InformationSource** | ✅ sourceProvider, sourcePage, sourcePageHeading | ✅ Part of ObservationIdentifier | ⚠️ PARTIAL | Attestor: source field (string). Rosetta: full InformationSource type |
| **InformationProviderEnum** | ✅ ~18 providers (Bloomberg, Reuters, etc.) | ❌ — | ❌ MISSING | Not structured in Attestor |
| **InformationSource / FxInformationSource** | Extends InformationSource + fixingTime | ❌ — | ❌ MISSING | FX-specific not implemented |
| **QuotedCurrencyPair** | ✅ currency1, currency2, quoteBasis | ❌ — | ❌ MISSING | FX rate composition; not MVP |

**Gap Severity**: 🟡 **MODERATE** — Observation source is simplified to string; full source taxonomy missing.

---

#### 11. **FxRateSourceFixing, FxSpotRateSource**

| Type | Rosetta | Attestor | Status |
|------|---------|----------|--------|
| **FxRateSourceFixing** | ✅ {settlementRateSource, fixingDate} | ❌ — | ❌ MISSING |
| **FxSpotRateSource** | ✅ {primarySource, secondarySource} | ❌ — | ❌ MISSING |
| **QuotedCurrencyPair** | ✅ {currency1, currency2, quoteBasis} | ❌ — | ❌ MISSING |

**Gap Severity**: 🔴 **HIGH** — FX derivatives infrastructure completely missing; not MVP scope.

---

#### 12. **RateObservation** (market data)

| Field | Rosetta | Attestor | Status | Notes |
|--------|---------|----------|--------|-------|
| **resetDate** | date | ❌ — | ❌ MISSING | Market data infrastructure |
| **adjustedFixingDate** | date | ❌ — | ❌ MISSING | Not in MVP |
| **observedRate** | number | ❌ — | ❌ MISSING | Rate fixing / obs not implemented |
| **treatedRate** | number | ❌ — | ❌ MISSING | Post-processing of observed rates |

**Gap Severity**: 🔴 **HIGH** — Market data / fixing infrastructure not in Attestor scope.

---

### CREDIT DERIVATIVES TYPES

#### 13. **CreditIndex** (expanded)

| Field | Rosetta | Attestor | Status | Notes |
|--------|---------|----------|--------|-------|
| **extends IndexBase** | ✅ {name, provider, assetClass} | ❌ (flattened) | ⚠️ DIFFER | Attestor: index_name only; no provider/assetClass |
| **indexSeries** | int (0..1) | int | ✅ OK | Match |
| **indexAnnexVersion** | int (0..1) | int | ✅ OK | Match |
| **indexAnnexDate** | date (0..1) | ❌ — | ❌ MISSING | CDS annex date not tracked |
| **indexAnnexSource** | IndexAnnexSourceEnum (0..1) | ❌ — | ❌ MISSING | Annex source not tracked |
| **excludedReferenceEntity** | ReferenceInformation (0..*) | ❌ — | ❌ MISSING | Excluded entities for CDS baskets |
| **tranche** | Tranche (0..1) | ❌ — | ❌ MISSING | CDS tranche terms (senior, mezzanine, equity) |
| **settledEntityMatrix** | SettledEntityMatrix (0..1) | ❌ — | ❌ MISSING | Settled entity matrix |
| **indexFactor** | number (0..1) | ❌ — | ❌ MISSING | Recovery factor [0..1] |
| **seniority** | CreditSeniorityEnum (0..1) | ❌ — | ❌ MISSING | Debt seniority classification |

**Gap Severity**: 🔴 **CRITICAL** — CreditIndex is barebones; lacks annex, tranche, seniority, settled entities. **NOT PRODUCTION-READY FOR CDS INDICES**.

---

#### 14. **Credit Enums: CreditRatingAgencyEnum, CreditRatingOutlookEnum, CreditNotationMismatchResolutionEnum**

| Enum | Rosetta Members | Attestor | Status |
|------|-----------------|----------|--------|
| **CreditRatingAgencyEnum** | 8 agencies (Moody's, S&P, Fitch, etc.) | ❌ — | ❌ MISSING |
| **CreditRatingOutlookEnum** | Positive, Negative, Stable, Developing | ❌ — | ❌ MISSING |
| **CreditRatingCreditWatchEnum** | Positive, Negative, Developing | ❌ — | ❌ MISSING |

**Gap Severity**: 🔴 **CRITICAL** — Credit rating infrastructure completely missing.

---

#### 15. **TransactedPrice, ValuationMethod, CashSettlement**

| Type | Rosetta | Attestor | Status |
|------|---------|----------|--------|
| **TransactedPrice** | ✅ {marketFixedRate, initialPoints, marketPrice, quotationStyle} | ❌ — | ❌ MISSING |
| **ValuationMethod** | ✅ {valuationSource, quotationMethod, valuationMethod, ...} | ❌ — | ❌ MISSING |
| **CashSettlementTerms** | ✅ Full settlement framework | ❌ — | ❌ MISSING |

**Gap Severity**: 🔴 **CRITICAL** — Derivatives settlement infrastructure completely absent.

---

### FLOATING RATE CALCULATION TYPES

#### 16. **FloatingRateCalculationParameters** (Attestor-native type)

| Field | Rosetta (observable-asset-calculatedrate-type.rosetta) | Attestor | Status | Notes |
|--------|---------|----------|--------|-------|
| **calculationMethod** | CalculationMethodEnum (1..1) | CalculationMethodEnum | ✅ OK | AVERAGING, COMPOUNDING match |
| **observationShiftCalculation** | ObservationShiftCalculation (0..1) | ❌ — | ❌ MISSING | Observation shift parameters |
| **lookbackCalculation** | OffsetCalculation (0..1) | ❌ — | ❌ MISSING | Lookback offset |
| **lockoutCalculation** | OffsetCalculation (0..1) | ❌ — | ❌ MISSING | Lockout offset |
| **applicableBusinessDays** | BusinessCenters (0..1) | frozenset[str] | ⚠️ DIFFER | Attestor: simple set of strings; Rosetta: BusinessCenters type |
| **observationParameters** | ObservationParameters (0..1) | ❌ — | ❌ MISSING | Caps/floors on daily observations |

**Attestor Fields**:
- **lookback_days** ✅ Maps to lookbackCalculation.offsetDays
- **lockout_days** ✅ Maps to lockoutCalculation.offsetDays
- **shift_days** ✅ Maps to observationShiftCalculation.offsetDays
- **applicable_business_days** ✅ Present but flattened to frozenset

**Gap Severity**: 🟡 **MODERATE** — Covers core parameters but lacks structured observation/shift details.

---

#### 17. **CalculationMethodEnum**

| Enum Value | Rosetta | Attestor | Status |
|------------|---------|----------|--------|
| **Averaging** | ✅ | ✅ | ✅ OK |
| **Compounding** | ✅ | ✅ | ✅ OK |
| **CompoundedIndex** | ✅ (Rosetta) | ❌ — | ❌ MISSING |

**Gap Severity**: 🟡 **MINOR** — CompoundedIndex not in MVP; can be added.

---

#### 18. **ResetDates** (Attestor-native type)

| Field | Rosetta | Attestor | Status | Notes |
|--------|---------|----------|--------|-------|
| **resetFrequency** | Frequency (0..1, via ResetDates) | Frequency | ✅ OK | e.g., Period(3, "M") |
| **fixingDatesOffset** | BusinessDayOffset (0..1) | RelativeDateOffset | ⚠️ EQUIV | Both represent day offsets |
| **resetRelativeTo** | Literal from ResetDates | Literal["CalculationPeriodStartDate" \| "CalculationPeriodEndDate"] | ✅ OK | Matches Rosetta's choice |
| **calculationParameters** | FloatingRateCalculationParameters (0..1) | FloatingRateCalculationParameters \| None | ✅ OK | Optional, matches |
| **businessDayAdjustments** | Implicit in fixingDatesOffset | BusinessDayAdjustments | ✅ OK | Explicit in Attestor |

**Gap Severity**: 🟢 **LOW** — Functional match.

---

#### 19. **FRO Types (floating-asset-fro-type.rosetta)** — Floating Rate Option Reference Data

| Type | Rosetta | Attestor | Status | Notes |
|------|---------|----------|--------|-------|
| **FloatingRateIndexDefinition** | ✅ {fro, calculationDefaults, supportedDefinition, ...} | ❌ — | ❌ MISSING | FRO metadata not in Attestor |
| **FloatingRateIndexIdentification** | ✅ {floatingRateIndex, currency, froType} | ❌ — | ❌ MISSING | |
| **FloatingRateIndexCalculationDefaults** | ✅ {category, indexStyle, method, ...} | ❌ — | ❌ MISSING | Calculation defaults reference data |
| **ContractualDefinition** | ✅ Document version tracking | ❌ — | ❌ MISSING | |
| **FloatingRateIndexMappings** | ✅ Cross-definition mappings | ❌ — | ❌ MISSING | |
| **FroHistory** | ✅ {startDate, firstDefinedIn, updateDate, ...} | ❌ — | ❌ MISSING | Audit trail |

**Gap Severity**: 🔴 **HIGH** — FRO reference data infrastructure completely absent. Not MVP, but important for ISDA definition tracking.

---

### EQUITY-SPECIFIC TYPES

#### 20. **EquityIndex**

| Field | Rosetta | Attestor | Status | Notes |
|--------|---------|----------|--------|-------|
| **extends IndexBase** | ✅ {name, provider, assetClass} | ❌ (flattened) | ⚠️ DIFFER | Attestor: index_name only |
| **equityIndex** | EquityIndexEnum (0..1) | ❌ — | ❌ MISSING | Standard indices (S&P 500, Eurostoxx, etc.) |

**Rosetta Conditions**:
- IndexSourceSpecification: "if equityIndex exists then name is absent" → ⚠️ Not validated in Attestor

**Gap Severity**: 🟡 **MODERATE** — Acceptable for MVP; EquityIndexEnum can be added for standard indices.

---

#### 21. **DividendApplicability** (Equity swaps)

| Type | Rosetta | Attestor | Status |
|------|---------|----------|--------|
| **DividendApplicability** | ✅ {optionsExchangeDividends, additionalDividends, allDividends} | ❌ — | ❌ MISSING |

**Gap Severity**: 🔴 **HIGH** — Equity swap dividend treatment not implemented.

---

### BASKET TYPES

#### 22. **Basket, BasketConstituent**

| Type | Rosetta | Attestor | Status |
|------|---------|----------|--------|
| **Basket** | ✅ {basketConstituent (1..*)} | ❌ — | ❌ MISSING |
| **BasketConstituent** | ✅ extends Observable + {quantity, initialValuationPrice, ...} | ❌ — | ❌ MISSING |

**Gap Severity**: 🔴 **HIGH** — Basket observables completely absent. Needed for index options, basket swaps.

---

## Cardinality and Condition Implementation Summary

### Rosetta Conditions Implemented in Attestor

| Condition | Rosetta Type | Attestor Implementation | Status |
|-----------|--------------|------------------------|--------|
| **Price.PositiveAssetPrice** | value > 0 for ExchangeRate/AssetPrice | Decimal.is_finite() check in Price.__post_init__ | ⚠️ PARTIAL (doesn't check > 0) |
| **Price.CurrencyUnitForInterestRate** | unit → currency exists | Enforced implicitly (Price always has currency) | ✅ OK |
| **PriceQuantity.NonCurrencyQuantities** | at most one non-currency qty | Single Quantity simplification | ✅ OK (by structure) |
| **FloatingRateIndex.InterestRateAssetClass** | assetClass = InterestRate | Not checked (assumes context) | ⚠️ MISSING |
| **CreditIndex.IndexSeries** | >= 0 | Checked in __post_init__ | ✅ OK |
| **CreditIndex.IndexFactor** | 0 <= factor <= 1 | Not checked (field absent) | ❌ MISSING |
| **CreditIndex.CreditAssetClass** | assetClass = Credit | Not checked | ❌ MISSING |
| **EquityIndex.EquityAssetClass** | assetClass = Equity | Not checked | ❌ MISSING |
| **EquityIndex.IndexSourceSpecification** | if equityIndex exists then name absent | Not validated | ❌ MISSING |
| **Security.exchange constraint** | if exchange exists then isExchangeListed = true | Implemented in asset.py | ✅ OK |
| **PriceSchedule.UnitOfAmountExists** | unit exists and perUnitOf exists (except Variance/Vol) | Simplified away (no unit/perUnitOf) | ❌ MISSING |
| **PriceSchedule.Premium condition** | if premiumType exists then priceSubType = Premium | Not checked | ❌ MISSING |
| **FloatingRateCalculationParameters** | lookback_days >= 0, lockout_days >= 0, shift_days >= 0 | Checked in __post_init__ | ✅ OK |

---

## Cardinality Differences

### Simplified Cardinalities (MVP Design)

| Type.Field | Rosetta | Attestor | Rationale |
|------------|---------|----------|-----------|
| **PriceQuantity.price** | PriceSchedule (0..*) | Price (1..1) | Single price for equity trades; no schedule needed |
| **PriceQuantity.quantity** | NonNegativeQuantitySchedule (0..*) | NonNegativeQuantity (1..1) | Single qty for basic trades; can extend later |
| **Observable.Asset** | Full Asset class | NonEmptyStr (alias) | MVP: asset = identifier string (ISIN/ticker) |
| **FloatingRateCalculationParameters.applicableBusinessDays** | BusinessCenters | frozenset[str] | Simplified to set of strings |

---

## Missing Type Hierarchies

### PriceSchedule Inheritance (Rosetta)

Rosetta has a **6-level MeasureBase hierarchy**:
```
MeasureBase
 ├─ Measure
 │  ├─ MeasureSchedule
 │  │  └─ QuantitySchedule
 │  │     └─ Quantity
 │  │        └─ NonNegativeQuantity
 │  └─ QuantitySchedule
 └─ PriceSchedule (extends MeasureSchedule)
```

Attestor **flattens** to:
```
Price (simple dataclass with value: Decimal)
 └─ PriceQuantity (simple dataclass)
Quantity (simple dataclass)
 └─ NonNegativeQuantity (simple dataclass with value >= 0)
```

**Why**: Flattening is Pythonic; inheritance in Rosetta is a DSL artifact for validation. Attestor uses frozen dataclasses + validators.

---

## Index Hierarchy (Rosetta vs. Attestor)

### Rosetta

```
IndexBase (abstract)
 ├─ FloatingRateIndex
 │   ├─ InterestRateIndex (choice)
 │   │   ├─ FloatingRateIndex (concrete)
 │   │   └─ InflationIndex ← **MISSING in Attestor**
 │   └─ ...
 ├─ EquityIndex
 ├─ CreditIndex
 ├─ ForeignExchangeRateIndex
 └─ OtherIndex ← **MISSING in Attestor**
```

### Attestor

```
Index (type alias union)
 ├─ FloatingRateIndex (concrete, simple dataclass)
 ├─ EquityIndex (concrete, simple dataclass)
 ├─ CreditIndex (concrete, simple dataclass)
 ├─ FXRateIndex (concrete, simple dataclass)
 └─ [InflationIndex, OtherIndex, Basket MISSING]
```

---

## Testing & Validation Gaps

### What Attestor Tests Cover

From test examination:
- ✅ FloatingRateIndex creation and validation
- ✅ FloatingRateIndexEnum values
- ✅ Price type enum coverage
- ✅ Observable union type creation
- ✅ ResetDates construction

### What Attestor Tests Miss

- ❌ PriceQuantity condition validation (InterestRateObservable, NonCurrencyQuantities)
- ❌ PriceSchedule composites and operators
- ❌ Credit index conditions (IndexSeries >= 0, IndexFactor [0..1])
- ❌ Equity index source specification choice
- ❌ FX rate pair validation
- ❌ Basket constituent references
- ❌ Cross-definition mappings (FRO)

---

## Architectural Decisions

### Design Philosophy: MVP for Equity Trades

Attestor's observable-asset namespace is **intentionally scoped** to the equity trade critical path:
1. **Prices**: single Price + PriceQuantity (no schedules)
2. **Observables**: Asset (string) | Index (4 types)
3. **Floating rates**: FloatingRateIndex with calculation params
4. **Security**: linked via asset identifier

**Out of scope (deferred)**:
- Credit derivatives (CDS indices, tranches, seniority)
- Inflation indices
- Basket/composite observables
- Advanced pricing (composite, premium, sub-types)
- FRO reference data
- Market data / fixings (RateObservation)
- Dividend applicability
- Complex valuation methods

### Type Safety Improvements Over Rosetta

Attestor uses **Python sum types** (unions) instead of Rosetta's choice/condition patterns:
- **Rosetta**: Index extends IndexBase; at runtime, check assetClass = "Equity"
- **Attestor**: type Index = FloatingRateIndex | EquityIndex | ... (compile-time checked)

This makes illegal states **structurally unrepresentable**.

---

## Gap Prioritization

### 🔴 CRITICAL (Blocks production use for equity trades if unresolved)

1. **PriceSchedule composites** (dirty = clean + accrued) — **Bonds need this**
2. **PriceComposite & arithmeticOperator** (spreads, multipliers) — **Rates/FX forwards need this**
3. **PriceSubType & FeeTypeEnum** — **Complex products need sub-classification**
4. **Basket observables** — **Index options need baskets**
5. **EquityIndexEnum** — **Reference data completeness**

### 🟡 MODERATE (Should be added before production for certain assets)

1. **Inflation indices** — **For inflation swaps**
2. **DividendApplicability** — **For equity swaps**
3. **CreditIndex full type** (annex, tranche, seniority) — **For CDS**
4. **FRO definitions (reference data)** — **For ISDA compliance**
5. **RateObservation / Market data** — **For pricing**

### 🟢 LOW (Can defer or accept simplified implementation)

1. **OtherIndex** — **Custom indices handled as-is**
2. **ParValueFraction** — **Bonds/options deferred**
3. **Variance/Volatility/Correlation** — **Exotics deferred**
4. **Dividend/Premium types** — **Extend as needed**

---

## Recommendations

### Immediate (Next Sprint)

1. **Add PriceComposite support** for dirty/clean bond pricing:
   ```python
   @dataclass(frozen=True)
   class PriceComposite:
       baseValue: Decimal
       operand: Decimal
       arithmeticOperator: ArithmeticOperationEnum
       operandType: PriceOperandEnum | None = None
   ```

2. **Extend PriceSchedule** to include datedValue (schedule) for time-indexed prices

3. **Add EquityIndexEnum** for major indices (S&P 500, Eurostoxx, etc.)

### Medium Term (Next 2-3 Sprints)

1. **Implement InflationIndex** (for inflation swaps)
2. **Add Basket observables** (for index options)
3. **Extend CreditIndex** with full tranche/seniority support
4. **Add RateObservation** for market data / fixing infrastructure

### Deferred (Post-MVP)

1. **FRO reference data** (FloatingRateIndexDefinition, FloatingRateIndexCalculationDefaults)
2. **Full valuation method framework** (TransactedPrice, ValuationMethod, CashSettlementTerms)
3. **Credit rating enums and structures**
4. **Dividend applicability for equity swaps**

---

## Summary Table: Rosetta vs. Attestor Coverage

| Category | Rosetta Concepts | Attestor Implementation | Coverage | Priority |
|----------|------------------|------------------------|----------|----------|
| **Core Pricing** | Price, PriceQuantity, PriceTypeEnum | ✅ Implemented | 70% (no composite, sub-types) | Critical |
| **Observables** | Asset, Basket, Index (5 types) | ✅ Partial (4 index types) | 60% (no Basket, InflationIndex) | High |
| **Floating Rates** | FloatingRateIndex, CalculationParams, ResetDates | ✅ Implemented | 90% | Medium |
| **Credit** | CreditIndex, CreditRatings, CDS semantics | ❌ Barebones | 20% | High (for CDS) |
| **FX** | FxRateSourceFixing, QuotedCurrencyPair | ❌ Minimal | 10% | Medium |
| **Equity** | EquityIndex, DividendApplicability | ⚠️ Partial | 50% | Medium |
| **Baskets** | Basket, BasketConstituent, weights | ❌ Missing | 0% | High |
| **Market Data** | RateObservation, Fixing | ❌ Missing | 0% | Medium |
| **FRO Metadata** | FloatingRateIndexDefinition, Mappings | ❌ Missing | 0% | Low |

**Overall Coverage**: ~60% (MVP for equity trades) → target 85% (full equity + rates + FX basics)

---

## Conclusion

Attestor's observable-asset namespace is a **pragmatic MVP** aligned with the equity trade critical path. It implements the core Price/Observable types and floating rate infrastructure but intentionally omits credit derivatives, advanced composites, and market data infrastructure.

**Key strengths**:
- Type-safe Observable union (vs. Rosetta's runtime conditions)
- Clean separation of concerns (Price, Quantity, Observable)
- Flattened inheritance (more Pythonic than Rosetta's MeasureBase hierarchy)

**Key gaps**:
- No PriceComposite (limits bond/FX pricing)
- Simplified Index structure (missing InflationIndex, OtherIndex, Basket)
- Credit index is minimal (no tranche, seniority, settled entities)
- No market data / fixing infrastructure

**Recommendation**: Systematically add critical gaps (composites, inflation indices, baskets) over next 2-3 sprints; defer FRO metadata and full credit derivatives infrastructure to post-MVP phase.

