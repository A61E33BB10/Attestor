# NS5: product-template Gap Analysis

**Rosetta source**: `product-template-enum.rosetta`, `product-template-type.rosetta`, `product-template-func.rosetta`
**Date**: 2026-02-18

---

## 1. Enum Gaps

### 1.1 OptionTypeEnum (extends PutCallEnum)

**CDM**: `Payer`, `Receiver`, `Straddle` (extends Put/Call from PutCallEnum)
**Attestor**: `OptionType` with only `CALL`, `PUT`

| Gap | Action |
|-----|--------|
| Missing `PAYER`, `RECEIVER`, `STRADDLE` members | Add 3 members |
| Name mismatch: `OptionType` vs CDM `OptionTypeEnum` | Rename to `OptionTypeEnum` |

### 1.2 OptionExerciseStyleEnum

**CDM**: `European`, `Bermuda`, `American` (3 members)
**Attestor**: `OptionStyle` with `EUROPEAN`, `AMERICAN` (2 members)

| Gap | Action |
|-----|--------|
| Missing `BERMUDA` member | Add member |
| Name mismatch: `OptionStyle` vs CDM `OptionExerciseStyleEnum` | Rename to `OptionExerciseStyleEnum` |

### 1.3 ExpirationTimeTypeEnum (NEW)

**CDM**: `Close`, `Open`, `OSP`, `SpecificTime`, `XETRA`, `DerivativesClose`, `AsSpecifiedInMasterConfirmation` (7 members)
**Attestor**: Not present

| Gap | Action |
|-----|--------|
| Entire enum missing | Create `ExpirationTimeTypeEnum` with 7 members |

### 1.4 CallingPartyEnum (NEW)

**CDM**: `InitialBuyer`, `InitialSeller`, `Either`, `AsDefinedInMasterAgreement` (4 members)
**Attestor**: Not present

| Gap | Action |
|-----|--------|
| Entire enum missing | Create `CallingPartyEnum` with 4 members |

### 1.5 ExerciseNoticeGiverEnum (NEW)

**CDM**: `Buyer`, `Seller`, `Both`, `AsSpecifiedInMasterAgreement` (4 members)
**Attestor**: Not present

| Gap | Action |
|-----|--------|
| Entire enum missing | Create `ExerciseNoticeGiverEnum` with 4 members |

### 1.6 AveragingInOutEnum (NEW)

**CDM**: `In`, `Out`, `Both` (3 members)
**Attestor**: Not present

| Gap | Action |
|-----|--------|
| Entire enum missing | Create `AveragingInOutEnum` with 3 members |

### 1.7 MarginTypeEnum [DEPRECATED in CDM]

**CDM deprecated**: `Cash`, `Instrument` (securities finance context)
**Attestor**: `MarginType` with `VARIATION`, `INITIAL` (margin call context)

These are **different concepts**. CDM's deprecated MarginTypeEnum is about what asset type backs a repo margin (cash vs instrument). Attestor's MarginType is about variation vs initial margin in collateral calls.

| Gap | Action |
|-----|--------|
| Different semantics, CDM deprecated | Keep Attestor's MarginType unchanged. Document difference. |

### 1.8 RepoDurationEnum [DEPRECATED in CDM]

**CDM deprecated**: `Overnight`, `Term`
**Attestor**: Not present

| Gap | Action |
|-----|--------|
| Not needed (deprecated + repo not in scope) | Skip |

### 1.9 AssetPayoutTradeTypeEnum

**CDM**: `Repo`, `BuySellBack` (2 members)
**Attestor**: Not present

| Gap | Action |
|-----|--------|
| Securities finance only | Create stub enum for completeness |

---

## 2. Core Product Hierarchy Gaps

### 2.1 Payout (choice type)

**CDM Payout** is a `choice` with 8 variants:
1. `AssetPayout` — securities finance (repo)
2. `CommodityPayout` — commodity derivatives
3. `CreditDefaultPayout` — CDS
4. `FixedPricePayout` — fixed price (commodity)
5. `InterestRatePayout` — IRS legs, CDS fee legs
6. `OptionPayout` — options
7. `PerformancePayout` — equity/total return swaps
8. `SettlementPayout` — forward settling (FX spot/fwd)

**Attestor Payout** is a union of 10 specs:
`EquityPayoutSpec | OptionPayoutSpec | FuturesPayoutSpec | FXSpotPayoutSpec | FXForwardPayoutSpec | NDFPayoutSpec | IRSwapPayoutSpec | CDSPayoutSpec | SwaptionPayoutSpec | PerformancePayoutSpec`

| CDM Payout Variant | Attestor Equivalent | Gap |
|-------------------|---------------------|-----|
| AssetPayout | — | Missing (securities finance) |
| CommodityPayout | — | Missing (commodity) |
| CreditDefaultPayout | CDSPayoutSpec | Partial match |
| FixedPricePayout | — | Missing (commodity) |
| InterestRatePayout | IRSwapPayoutSpec (2 legs combined) | Structural mismatch: CDM models each leg separately |
| OptionPayout | OptionPayoutSpec + SwaptionPayoutSpec | Partial match |
| PerformancePayout | PerformancePayoutSpec | Partial match |
| SettlementPayout | FXSpotPayoutSpec + FXForwardPayoutSpec + NDFPayoutSpec | Structural mismatch: CDM unifies under SettlementPayout |
| — | EquityPayoutSpec | No CDM equivalent (equity is SettlementPayout in CDM) |
| — | FuturesPayoutSpec | No CDM equivalent (futures is SettlementPayout in CDM) |

**Assessment**: The Payout choice is the most fundamental structural difference. CDM's 8 variants are generic, compositional building blocks. Attestor's 10 variants are product-specific shortcuts. Full alignment would require a major rewrite of the instrument layer.

**Recommendation**: Phase this across NS5-NS7. For NS5, focus on:
- Add `AssetPayoutTradeTypeEnum` (stub)
- Align `OptionPayout` fields/conditions with CDM
- Align `PerformancePayout` fields/conditions
- Document the structural differences for later phases

### 2.2 EconomicTerms

**CDM fields**:
- `effectiveDate: AdjustableOrRelativeDate (0..1)` — Attestor has `effective_date: date` (simpler)
- `terminationDate: AdjustableOrRelativeDate (0..1)` — Attestor has `termination_date: date | None` (simpler)
- `dateAdjustments: BusinessDayAdjustments (0..1)` — **MISSING** in Attestor
- `payout: Payout (1..*)` — Attestor has `payouts: tuple[Payout, ...]` (match modulo Payout type)
- `terminationProvision: TerminationProvision (0..1)` — **MISSING** in Attestor
- `calculationAgent: CalculationAgent (0..1)` — **MISSING** in Attestor
- `nonStandardisedTerms: boolean (0..1)` — **MISSING** in Attestor
- `collateral: Collateral (0..1)` — **MISSING** in Attestor

**CDM conditions** (15): Most are about InterestRatePayout with 2 legs, CDS-specific, or PerformancePayout. Key ones:
- `ReturnType_Total_Requires_Dividends`
- `Quantity` (OptionPayout priceQuantity existence)
- `MarketPrice` (CDS index-specific)
- `NotionalResetOnPerformancePayout`
- Various FpML validation rules for IRS

| Gap | Priority | Action |
|-----|----------|--------|
| `dateAdjustments` field missing | Medium | Add optional `BusinessDayAdjustments` field |
| `terminationProvision` field missing | Medium | Add after TerminationProvision type created |
| `calculationAgent` field missing | Low | Stub later |
| `nonStandardisedTerms` field missing | Low | Add boolean field |
| `collateral` field missing | Low | Stub later (NS6 or later) |
| `effective_date` is `date` vs CDM `AdjustableOrRelativeDate` | Medium | Keep `date` for now, document |
| 15 conditions missing | Medium | Add key conditions |

### 2.3 NonTransferableProduct

**CDM**: `identifier (ProductIdentifier 0..*)`, `taxonomy (ProductTaxonomy 0..*)`, `economicTerms (EconomicTerms 1..1)` + condition
**Attestor**: `Product` has only `economic_terms: EconomicTerms`

| Gap | Action |
|-----|--------|
| Missing `identifier` | Add `identifier: tuple[...] = ()` |
| Missing `taxonomy` | Add `taxonomy: tuple[...] = ()` |
| CDM name is `NonTransferableProduct` | Rename or alias |

### 2.4 TransferableProduct

**CDM**: extends `Asset`, adds `economicTerms`
**Attestor**: Not present (Asset is `Security` only)

| Gap | Action |
|-----|--------|
| Not modelled | Create type (depends on Asset hierarchy from NS1) |

### 2.5 TradableProduct

**CDM**: `product (NonTransferableProduct 1..1)`, `tradeLot (TradeLot 1..*)`, `counterparty (Counterparty 2..2)`, `ancillaryParty (AncillaryParty 0..*)`, `adjustment (NotionalAdjustmentEnum 0..1)` + 13 conditions
**Attestor**: Not present (Instrument combines product + parties + trade_date)

| Gap | Action |
|-----|--------|
| Not modelled | Create type (later — affects Trade model in NS7) |

### 2.6 TradeLot

**CDM**: `lotIdentifier (Identifier 0..*)`, `priceQuantity (PriceQuantity 1..*)`
**Attestor**: Not present

| Gap | Action |
|-----|--------|
| Not modelled | Create type (later — affects TradableProduct) |

### 2.7 Underlier (choice)

**CDM**: `Observable | Product`
**Attestor**: Not present as standalone type (underlier is embedded as string IDs)

| Gap | Action |
|-----|--------|
| Not modelled | Create choice type |

### 2.8 Product (choice)

**CDM**: `TransferableProduct | NonTransferableProduct`
**Attestor**: `Product` is a wrapper around `EconomicTerms` (different concept)

| Gap | Action |
|-----|--------|
| Structural mismatch | Align later (after TransferableProduct + NonTransferableProduct created) |

---

## 3. Option Types Gaps

### 3.1 OptionPayout (extends PayoutBase)

**CDM fields**: `buyerSeller (1..1)`, `feature (0..1)`, `observationTerms (0..1)`, `schedule (0..1)`, `delivery (0..1)`, `underlier (1..1)`, `optionType (0..1)`, `exerciseTerms (1..1)`, `strike (0..1)` + 8 conditions
**Attestor**: `OptionPayoutSpec` with `underlying_id`, `strike`, `expiry_date`, `option_type`, `option_style`, `settlement_type`, `currency`, `exchange`, `multiplier`, `exercise_terms`

| Gap | Priority | Action |
|-----|----------|--------|
| Missing `buyerSeller` | High | Add `BuyerSeller` field |
| Missing `feature` (OptionFeature) | Low | Stub for later |
| Missing `observationTerms` | Low | Stub for later |
| Missing `underlier` as typed choice | Medium | Keep string ID for now |
| `strike` is `Decimal` vs CDM `OptionStrike` | Medium | Create OptionStrike type |
| `exerciseTerms` is optional vs CDM required | High | Make required (with style enum) |
| CDM conditions (OptionStylePresent, OptionTypePresent, Asian choice rules) | Medium | Add key conditions |

### 3.2 ExerciseTerms (CDM unified type)

**CDM**: Rich unified type with `style`, `commencementDate`, `exerciseDates`, `expirationDate`, `relevantUnderlyingDate`, times, fees, procedure, partial/multiple exercise + 8 conditions

**Attestor**: Simple union of 3 types: `AmericanExercise | EuropeanExercise | BermudaExercise`

This is a significant structural difference. CDM uses a single type with style-dependent field constraints. Attestor uses discriminated union.

| Gap | Action |
|-----|--------|
| Structural mismatch | **Keep Attestor's union approach** (it makes illegal states unrepresentable). Add missing fields to each variant. Add `OptionExerciseStyleEnum` for compatibility. |

### 3.3 OptionStrike (one-of choice)

**CDM**: `strikePrice (Price)`, `strikeReference (FixedRateSpecification)`, `referenceSwapCurve`, `averagingStrikeFeature` — one-of
**Attestor**: Strike is just a `NonNegativeDecimal`

| Gap | Action |
|-----|--------|
| Missing as standalone type | Create `OptionStrike` type with `strike_price: Price` as primary variant |

### 3.4 OptionFeature

**CDM**: `fxFeature (0..*)`, `strategyFeature (0..1)`, `averagingFeature (0..1)`, `barrier (0..1)`, `passThrough (0..1)`
**Attestor**: Not present

| Gap | Action |
|-----|--------|
| Not modelled | Create stub type for barrier at minimum |

---

## 4. Performance Types Gaps

### 4.1 PerformancePayout (extends PayoutBase)

**CDM fields**: `observationTerms`, `valuationDates (1..1)`, `paymentDates (1..1)`, `underlier (0..1)`, `fxFeature (0..*)`, `returnTerms (0..1)`, `portfolioReturnTerms (0..*)`, `initialValuationPrice (0..*)`, `interimValuationPrice (0..*)`, `finalValuationPrice (0..*)` + 10 conditions

**Attestor**: `PerformancePayoutSpec` with `underlier_id`, `initial_observation_date`, `final_observation_date`, `currency`, `notional`

| Gap | Priority | Action |
|-----|----------|--------|
| Missing `returnTerms` | High | Create `ReturnTerms` type |
| Missing `valuationDates` | Medium | Create stub type |
| Missing `paymentDates` ref | Medium | Reference existing `PaymentDates` |
| Simplified observation dates vs CDM valuation structure | Medium | Document, keep simplified |
| Missing CDM conditions | Medium | Add key conditions |

### 4.2 ReturnTerms (NEW)

**CDM**: `priceReturnTerms (0..1)`, `dividendReturnTerms (0..1)`, `varianceReturnTerms (0..1)`, `volatilityReturnTerms (0..1)`, `correlationReturnTerms (0..1)` + condition
**Attestor**: Not present

| Gap | Action |
|-----|--------|
| Not modelled | Create type with CDM's 5 optional fields |

---

## 5. Settlement/Forward Types Gaps

### 5.1 SettlementPayout (extends PayoutBase)

**CDM**: `underlier (1..1)`, `deliveryTerm (0..1)`, `delivery (0..1)`, `schedule (0..1)` + 6 conditions
**Attestor**: Modelled as 3 separate FX specs + futures

| Gap | Action |
|-----|--------|
| CDM unifies FX spot/fwd/equity settlement under one type | Document. Consider later unification. |

### 5.2 FixedPricePayout (extends PayoutBase)

**CDM**: `paymentDates (1..1)`, `fixedPrice (1..1)`, `schedule (0..1)` + condition
**Attestor**: Not present

| Gap | Action |
|-----|--------|
| Commodity-specific | Skip for equity critical path |

---

## 6. Termination Provision Gaps

### 6.1 TerminationProvision

**CDM**: `cancelableProvision`, `earlyTerminationProvision`, `evergreenProvision`, `extendibleProvision`, `recallProvision` (required choice)
**Attestor**: Not present

| Gap | Action |
|-----|--------|
| Not modelled | Create type with required choice |

### 6.2-6.6 CancelableProvision, EarlyTerminationProvision, ExtendibleProvision, EvergreenProvision, RecallProvision

All missing from Attestor. These are complex types with many sub-types.

| Gap | Action |
|-----|--------|
| Large type tree missing | Create stub types for NS5, flesh out in later NS |

---

## 7. Proposed Implementation Plan

Given the massive scope, NS5 should be split into sub-phases:

### NS5a: Enums + ExerciseTerms alignment (~focused)
1. Rename `OptionType` → `OptionTypeEnum`, add `PAYER`, `RECEIVER`, `STRADDLE`
2. Rename `OptionStyle` → `OptionExerciseStyleEnum`, add `BERMUDA`
3. Create `ExpirationTimeTypeEnum` (7 members)
4. Create `CallingPartyEnum` (4 members)
5. Create `ExerciseNoticeGiverEnum` (4 members)
6. Create `AveragingInOutEnum` (3 members)
7. Create `AssetPayoutTradeTypeEnum` (2 members)
8. Enrich exercise types with `ExpirationTimeTypeEnum` reference
9. Update all imports/tests

### NS5b: Product hierarchy + EconomicTerms
1. Add fields to `EconomicTerms` (dateAdjustments, terminationProvision, etc.)
2. Create `NonTransferableProduct` (with identifier + taxonomy)
3. Create `Underlier` choice type
4. Create `ReturnTerms`
5. Create `TerminationProvision` (stub) + sub-types
6. Add key CDM conditions to EconomicTerms
7. Update tests

### NS5c: OptionPayout/PerformancePayout enrichment (later)
1. Create `OptionStrike` type
2. Create `OptionFeature` type
3. Enrich `OptionPayoutSpec` with CDM fields
4. Enrich `PerformancePayoutSpec` with CDM fields
5. Add CDM conditions

---

## 8. Impact Assessment

### NS5a (enums + exercise):
- 7 new/modified enums
- ~50 new tests
- Ripple effect: `OptionPayoutSpec`, `OptionDetail`, all test files using `OptionType`/`OptionStyle`

### NS5b (product hierarchy):
- 4-6 new/modified types
- ~30 new tests
- Ripple effect: `EconomicTerms` used everywhere

### NS5c (payout enrichment):
- 3-5 new types
- ~40 new tests
- Lower ripple effect (optional fields)
