# CDM Gap Review: Rosetta Source Comparison and Execution Plan

**Date:** 2026-02-16
**Attestor Version:** Phase 0 Complete (1,513 tests passing, 55 source files, 11,705 lines)
**CDM Source:** `common-domain-model/rosetta-source/src/main/rosetta/` (142 Rosetta DSL files; 62 type+enum files analyzed for this comparison)
**Scope:** Namespace-by-namespace comparison of every CDM type and enum in type+enum files against Attestor's implementation. CDM `func` files (function signatures and qualification logic) were out of scope for this type-level comparison.
**Method:** Direct analysis of Rosetta DSL source files, not documentation summaries

---

## 1. Executive Summary

### What Changed From Prior Analysis

The prior gap analysis (consolidated from `CDM_GAP_ANALYSIS.md` and `CDM_gap.md`) was based on domain knowledge and CDM documentation. This revision is based on **direct comparison against every Rosetta type and enum file** in the CDM source repository. Key differences:

| Aspect | Prior Analysis | This Revision |
|--------|---------------|---------------|
| Method | Domain-knowledge extrapolation | Direct Rosetta source comparison |
| CDM types examined | ~155 (estimated) | **438** in-scope + **232** legal = **670** total (from 62 type+enum files) |
| Namespace coverage | Approximate | Complete (base, product, event, observable, legal, margin, regulation) |
| CRITICAL gaps identified | 4 | **10** |
| HIGH gaps identified | 7 | **50+** |
| New gaps found | -- | Date infrastructure (schedule, roll, stub), Observable taxonomy, Calculated rate parameters, MiFIR reporting fields |
| Confirmed out-of-scope | Legal documentation | Legal documentation (200+ types confirmed irrelevant) |

### Where Attestor Stands

Attestor implements a **pragmatic, type-safe subset** of CDM's domain. The Rosetta source defines 438 types/enums across its non-legal type+enum files. Attestor covers:

| Coverage | Count | Description |
|----------|-------|-------------|
| OK (aligned) | 7 | Types that match CDM semantics (OptionType, PositionStatusEnum, Money, etc.) |
| PARTIAL | 79 | Types where Attestor has a simpler equivalent |
| MISSING | 290+ | Types with no Attestor equivalent |
| OUT OF SCOPE | ~200+ | Legal documentation types (by design decision) |
| EXTRA | 24 | Attestor strengths CDM does not specify |

The effective alignment rate for in-scope types is **~37% partial-or-better** (86 of 230 in-scope types).

### Attestor Strengths Beyond CDM

These EXTRA capabilities must be preserved during alignment:

| Attestor Feature | CDM Equivalent |
|-----------------|----------------|
| Arbitrage-free vol surfaces (SVI with 6 gates) | None |
| Pure Decimal arithmetic (prec=28, no float contamination) | Not specified |
| Conservation laws (`sigma(U) = 0` per transaction) | None |
| Result monad (`Ok[T] | Err[str]`) | No error model |
| Bitemporal envelope (event-time + knowledge-time) | None |
| Content-addressed identity (`content_hash()`) | Metadata references |
| VaR / Expected Shortfall / PnL attribution | Not in CDM scope |
| Yield curve and credit curve bootstrap | Model-agnostic |
| Epistemic confidence model (Firm/Quoted/Derived) | None |

---

## 2. Gap Analysis by Namespace

### 2.1 Base Namespace (`base-*`)

**Files analyzed:** 17 Rosetta files (type + enum)
**CDM types/enums found:** ~130
**Coverage:** 3 CRITICAL gaps, 14 HIGH gaps

#### CRITICAL Gaps

| Gap ID | CDM Type | Impact |
|--------|----------|--------|
| BASE-C1 | `BusinessCenters` + `BusinessCenterEnum` (~250 centers) | All date adjustments wrong without holiday calendars. Attestor's `calendar.py` only skips weekends. |
| BASE-C2 | `BusinessDayConventionEnum` (ModifiedFollowing, Following, Preceding, etc.) | Cannot implement ModifiedFollowing -- the standard for IRS, CDS, and virtually all OTC derivatives. |
| BASE-C3 | `DayCountFractionEnum` (14 conventions) | Attestor has 3 of 14: ACT_360, ACT_365, THIRTY_360. Missing: ACT/ACT.ISDA (the bond standard), ACT/ACT.ICMA, 30E/360, ACT/ACT.AFB, BUS/252, and 8 others. |

#### HIGH Gaps

| Gap ID | CDM Type | What's Missing |
|--------|----------|---------------|
| BASE-H1 | `BusinessDayAdjustments` | Core type coupling convention + business centers |
| BASE-H2 | `AdjustableDate` / `AdjustableDates` | No adjusted-date concept anywhere in Attestor |
| BASE-H3 | `Period` + `PeriodEnum` (D/W/M/Y) | Cannot represent arbitrary time periods; Attestor uses fixed enum |
| BASE-H4 | `Frequency` | Coupled period + roll convention; Attestor has rigid `PaymentFrequency` enum |
| BASE-H5 | `Offset` / `RelativeDateOffset` | Cannot compute fixing dates, payment lags, or relative date adjustments |
| BASE-H6 | `PeriodicDates` / `CalculationPeriodFrequency` | Cannot generate coupon schedules |
| BASE-H7 | `RollConventionEnum` (30+ values) | Cannot handle IMM dates, EOM, or specific day-of-month rolls |
| BASE-H8 | `MeasureSchedule` / `Schedule` / `DatedValue` | No step/amortizing schedule support for notionals or rates |
| BASE-H9 | `CounterpartyRoleEnum` (Party1/Party2) + `PayerReceiver` | Cashflow direction ambiguous -- parties stored as unordered tuple |
| BASE-H10 | `ISOCurrencyCodeEnum` (~180 currencies) | Attestor validates ~30 currencies; trades in others fail silently |
| BASE-H11 | `FloatingRateIndexEnum` (500+ indices) | Float index stored as unvalidated `NonEmptyStr`; typos silently accepted |
| BASE-H12 | `Identifier` (generic issuer + value + version) | Attestor has LEI/UTI/ISIN but no generic identifier pattern |
| BASE-H13 | `Party` (rich: multiple identifiers, business units, persons) | Attestor Party has only 3 fields (party_id, name, LEI) |
| BASE-H14 | `PartyRoleEnum` (~45 roles) | No party role assignment for regulatory reporting |

#### OK/PARTIAL Alignments

- `OptionType` (CALL/PUT) -- exact match with CDM `PutCallEnum`
- `NonNegativeDecimal` -- matches CDM `NonNegativeQuantity` constraint
- `Money` -- adequate coverage of CDM `Cash` concept
- `LEI`, `UTI`, `ISIN` -- validated types exist (not in generic Identifier wrapper)
- `SeniorityLevel` -- partial match with CDM `DebtSeniorityEnum`
- `DayCountConvention` -- 3 of 14 conventions

### 2.2 Product Namespace (`product-*`)

**Files analyzed:** 14 Rosetta files
**CDM types/enums found:** 138
**Coverage:** 0 OK, 27 PARTIAL, 108 MISSING, 3 MISMATCHED

#### CRITICAL Gaps

| Gap ID | CDM Type | Impact |
|--------|----------|--------|
| PROD-C1 | `CalculationPeriodDates` | Cannot generate accrual period schedules for IRS/CDS |
| PROD-C2 | `ResetDates` | No floating rate reset schedule; observation timing undefined |
| PROD-C3 | `PaymentDates` | No parameterized payment schedule (first/last dates, offsets, BDA) |
| PROD-C4 | `Cashflow` | No typed cashflow with payer/receiver semantics |
| PROD-C5 | `ResolvablePriceQuantity` | No generic quantity with schedule, cross-leg reference, multiplier |
| PROD-C6 | `PayoutBase` | CDM payouts share a common interface; Attestor's are structurally independent |
| PROD-C7 | `InterestRatePayout` | Attestor's FixedLeg/FloatLeg lacks rate specification choice, discounting, compounding, cashflow representation, stub periods |

#### HIGH Gaps (18 items)

Key items:
- **Schedule infrastructure**: `StubPeriod`, `StubValue`, `StubCalculationPeriodAmount`, `RateSchedule`, `FixedRateSpecification`
- **Floating rate**: `FloatingRateSpecification`, `FloatingRateBase`, `FloatingRate`, `CompoundingMethodEnum`, `NegativeInterestRateTreatmentEnum`
- **Settlement**: `CashSettlementTerms`, `PrincipalPayments`, `ScheduledTransferEnum`, `CashSettlementMethodEnum`
- **Credit**: `CreditDefaultPayout` (full specification), `GeneralTerms`, `ProtectionTerms`, `ReferenceInformation`
- **Options**: `OptionPayout` (full specification), `ExerciseTerms`, `BermudaExercise`
- **Collateral**: `CollateralValuationTreatment` (haircuts), `EligibleCollateralCriteria`

#### Structural Divergences

| Aspect | CDM | Attestor |
|--------|-----|----------|
| Payout taxonomy | 8 choice variants | 9 union variants (different composition) |
| Payout base | Common `PayoutBase` with shared fields | Independent per-type dataclasses |
| Schedule | Rich parametric generation framework | Simple date + frequency enum |
| Quantity | `ResolvablePriceQuantity` with schedules | `PositiveDecimal` flat value |
| Inheritance | Deep hierarchy (up to 6 levels) | Flat `@final @dataclass` |

### 2.3 Event Namespace (`event-*`)

**Files analyzed:** 6 Rosetta files
**CDM types/enums found:** 60
**Coverage:** 2 OK, 18 PARTIAL, 40 MISSING

#### HIGH Gaps (7 items)

| Gap ID | CDM Type | Impact |
|--------|----------|--------|
| EVT-H1 | `TradeState` | No state-snapshot wrapper; Attestor uses Instrument with status field |
| EVT-H2 | `Trade` | Missing multi-identifier (USI/UTI), party roles, execution details |
| EVT-H3 | `BusinessEvent` (CDM version) | Attestor's is instruction-centric (cause); CDM's is state-centric (effect) |
| EVT-H4 | `QuantityChangeInstruction` | Cannot model partial termination, notional step, or trade decrease |
| EVT-H5 | `PartyChangeInstruction` | Cannot model novation or clearing |
| EVT-H6 | `SplitInstruction` | Cannot model trade allocation |
| EVT-H7 | `WorkflowStep` | No multi-party approval, event chaining, correction/cancellation envelope |

#### Key Architectural Difference

CDM models events as **state transformations** (before TradeState -> BusinessEvent -> after TradeState). Attestor models events as **instructions processed by a conservation-law-enforced ledger**. Both are valid. Attestor's approach provides stronger bookkeeping guarantees (atomicity, conservation) but requires a mapping layer for CDM interop.

### 2.4 Observable Namespace (`observable-*`)

**Files analyzed:** 9 Rosetta files
**CDM types/enums found:** 62
**Coverage:** 3 OK, 16 PARTIAL, 34 MISSING

#### CRITICAL Gap

| Gap ID | CDM Type | Impact |
|--------|----------|--------|
| OBS-C1 | `Observable` choice type (Asset/Basket/Index) | No unified observable reference; observations not linked to what was observed |

#### HIGH Gaps (4 items)

| Gap ID | CDM Type | Impact |
|--------|----------|--------|
| OBS-H2 | `Index` hierarchy (Float/Credit/Equity/FX/Inflation) | All indices are untyped strings |
| OBS-H3 | `FloatingRateCalculationParameters` | No compounding/averaging/lookback/lockout for SOFR/SONIA |
| OBS-H4 | `PriceTypeEnum` (InterestRate/ExchangeRate/AssetPrice/etc.) | Prices are untyped Decimals |
| OBS-H5 | `Observation` / `ObservationIdentifier` | CDM uses structured identity; Attestor uses content-addressed hashing |

#### Cross-Cutting Observation

Attestor's Oracle layer is functionally rich (vol surfaces, yield curves, credit curves, confidence model) but uses its own type taxonomy. The CDM's formal type hierarchy (Observable, Index, Price, Observation) has no direct equivalent. This is the gap between **doing the computation** (Attestor excels) and **interoperating with the standard** (CDM alignment needed).

### 2.5 Legal Documentation Namespace (`legaldocumentation-*`)

**Files analyzed:** 16 Rosetta files
**CDM types/enums found:** ~200+
**Status:** OUT OF SCOPE by design (Phase F KILLED)

The Rosetta source confirms the prior decision: ~200+ legal documentation types covering CSA elections, ISDA Master Agreement schedules, GMRA, GMSLA, transaction additional terms, and bespoke clauses. None of these are needed for Attestor's core ledger/attestation/pricing mission. Legal agreements are referenced via `legal_agreement_id: str | None`.

### 2.6 Margin Namespace (`margin-schedule-*`)

**Files analyzed:** 2 Rosetta files (type + enum)
**CDM types/enums found:** 5

| Gap ID | CDM Type | Severity | Impact |
|--------|----------|----------|--------|
| MAR-H1 | `StandardizedSchedule` | HIGH | Needed for UMR phase 5/6 initial margin calculation |
| MAR-H2 | `StandardizedScheduleTradeInfo` | HIGH | Trade-level IM input |
| MAR-H3 | `StandardizedScheduleInitialMargin` | HIGH | Aggregated IM output |
| MAR-M1 | `StandardizedScheduleAssetClassEnum` | MEDIUM | Attestor uses ad-hoc strings |
| MAR-M2 | `StandardizedScheduleProductClassEnum` (~40 values) | MEDIUM | No product classification enum |

### 2.7 Regulation Namespace (`regulation-*`)

**Files analyzed:** 1 Rosetta file (regulation-type.rosetta)
**CDM types/enums found:** ~25

| Gap ID | CDM Type | Severity | Impact |
|--------|----------|----------|--------|
| REG-H1 | `InvstmtDcsnPrsn` / `ExctgPrsn` | HIGH | MiFIR-mandated person identification |
| REG-H2 | `AddtlAttrbts` (rskRdcgTx, sctiesFincgTxInd) | HIGH | MiFIR-mandated fields |
| REG-H3 | `FinInstrmGnlAttrbts.clssfctnTp` (CFI code) | HIGH | ISO 10962 classification mandatory |
| REG-H4 | `New` (full MiFIR transaction report) | HIGH | Several mandatory fields missing |
| REG-M1 | Trading capacity, country of branch | MEDIUM | MiFIR-required |
| REG-M2 | Price multiplier, delivery type | MEDIUM | Derivative attributes |

---

## 3. Consolidated Gap Statistics

### 3.1 By Namespace and Status

| Namespace | OK | PARTIAL | MISSING | MISMATCHED | OUT OF SCOPE | Total |
|-----------|---:|--------:|--------:|-----------:|-------------:|------:|
| Base | 4 | 18 | ~85 | 0 | 0 | ~107 |
| Product | 0 | 27 | 108 | 3 | 0 | 138 |
| Event | 2 | 18 | 40 | 0 | 0 | 60 |
| Observable | 3 | 16 | 34 | 0 | 9 | 62 |
| Legal Documentation | 0 | 1 | 0 | 0 | ~200 | ~201 |
| Margin | 0 | 2 | 3 | 0 | 0 | 5 |
| Regulation | 2 | 7 | 11 | 2 | 0 | 22 |
| **Total** | **11** | **89** | **~281** | **5** | **~209** | **~595** |

### 3.2 By Severity (In-Scope Only)

| Severity | Count | Impact |
|----------|-------|--------|
| CRITICAL | 11 | Model admits arbitrage or produces incorrect cashflows |
| HIGH | 53 | Model fails to capture essential market features |
| MEDIUM | ~80 | Feature or implementation gaps |
| LOW | ~140 | Niche, commodity-specific, or administrative types |

### 3.3 All CRITICAL Gaps

| ID | Source | CDM Type | Financial Impact |
|----|--------|----------|-----------------|
| BASE-C1 | base-datetime | BusinessCenters + BusinessCenterEnum | All date adjustments wrong without holiday calendars |
| BASE-C2 | base-datetime | BusinessDayConventionEnum | Cannot implement ModifiedFollowing (IRS/CDS standard) |
| BASE-C3 | base-datetime | DayCountFractionEnum | Missing ACT/ACT.ISDA, 30E/360, and 11 other conventions |
| PROD-C1 | product-schedule | CalculationPeriodDates | Cannot generate IRS/CDS accrual schedules |
| PROD-C2 | product-schedule | ResetDates | Floating rate observation timing undefined |
| PROD-C3 | product-schedule | PaymentDates | No parameterized payment schedule |
| PROD-C4 | product-settlement | Cashflow | No typed cashflow with payer/receiver |
| PROD-C5 | product-settlement | ResolvablePriceQuantity | No schedule-aware quantity abstraction |
| PROD-C6 | product-settlement | PayoutBase | No common payout interface |
| PROD-C7 | product-asset | InterestRatePayout | IRS model missing rate choice, compounding, stubs |
| OBS-C1 | observable-asset | Observable choice type (Asset/Basket/Index) | No unified observable reference; observations not linked to what was observed |

---

## 4. Phase 0: Safety Hardening -- COMPLETED

*(This section is unchanged from the prior analysis. Phase 0 fixed systemic type-safety vulnerabilities before adding new types.)*

### Summary

- **7 sub-tasks completed**: Constructor sealing, NonNegativeDecimal, pure Decimal calibration, negative rate support, multi-leg payouts, date invariants, gateway exhaustiveness
- **46 new tests**: All passing
- **1,513 total tests**: No regressions
- **mypy --strict**: Clean on all modified files
- **ruff**: No linting violations

### Construction Invariants Established

Every type in Attestor is now sealed: `__post_init__` guards prevent construction-time invariant violation even via direct `__init__`. The Minsky test passes: illegal states cannot be constructed.

---

## 5. Updated Execution Plan

The execution plan is reorganized based on the detailed Rosetta source comparison. Phases are reordered by dependency and criticality.

### Hard Caps (Non-Negotiable)

| Metric | Current | Target Max | Rationale |
|--------|---------|------------|-----------|
| Named types | 162 | 200 | Beyond this, CDM ceremony leaked in |
| Lines of code | 11,705 | 13,000 | Complexity budget |
| Source files | 55 | 57 | Only 2 new files permitted |
| Compression vs CDM | -- | 5.3x | 80% functional scope in 19% of types |

### Anti-Cargo-Cult Principles

1. Do NOT replicate CDM's 6-level Quantity inheritance chain. Use flat `Quantity` + `QuantitySchedule`.
2. Do NOT create 7 AdjustableDate variants. Use `AdjustableDate` + `RelativeDateOffset` + union.
3. Do NOT convert PrimitiveInstruction from discriminated union to optional-fields struct.
4. Do NOT import CDM metadata/reference system. Keep content-addressed identity.
5. Do NOT build legal documentation types. Store `legal_agreement_id: str | None`.
6. Do NOT import governance-only types with no financial modeling purpose.
7. Do NOT import CDM's FpML coding scheme infrastructure. Use Python enums and frozensets.
8. Do NOT replicate CDM's PayoutBase inheritance. Use composition where shared fields are needed.
9. Do NOT replicate CDM's `ArithmeticOperationEnum` or `Rounding` types. Attestor's `ATTESTOR_DECIMAL_CONTEXT` (prec=28) with pure `Decimal` arithmetic is strictly superior.
10. Do NOT introduce CDM's `metaType` / `key` / `reference` graph-reference system. Content-addressed identity (`content_hash()`) provides integrity verification, not just referential identity.
11. Do NOT import CDM's `Qualify` functions as types. CDM uses `isProduct_*` and `isEvent_*` runtime qualification. Attestor's discriminated unions provide this at the type level.

### Phase A: Date and Schedule Foundation

**Depends on:** Phase 0 (completed)
**Resolves:** BASE-C1, BASE-C2, BASE-C3, BASE-H1 through BASE-H8

**Delivers:**

| Type | Description | Attestor Design |
|------|-------------|-----------------|
| `PeriodEnum` | D, W, M, Y | Enum in `core/types.py` |
| `Period` | multiplier + period_enum | `@dataclass(frozen=True)` |
| `Frequency` | period + roll_convention | `@dataclass(frozen=True)` |
| `RollConventionEnum` | EOM, IMM, 1-30, NONE | Enum (subset: ~10 of 30+ CDM values) |
| `BusinessDayConventionEnum` | MODFOLLOWING, FOLLOWING, PRECEDING, NONE | Enum (4 of 7 CDM values) |
| `DayCountFractionEnum` expansion | Add ACT_ACT_ISDA, ACT_ACT_ICMA, THIRTY_E_360, ACT_365L, BUS_252 | Extend existing enum to 8 values |
| `BusinessDayAdjustments` | convention + business_centers | `@dataclass(frozen=True)` |
| `AdjustableDate` | unadjusted + adjustments | `@dataclass(frozen=True)` |
| `RelativeDateOffset` | period + convention + reference | `@dataclass(frozen=True)` |
| `Schedule` / `DatedValue` | tuple of (date, Decimal) pairs | `@dataclass(frozen=True)` with `len >= 1` and **strict date monotonicity**: `dates[i] < dates[i+1]` enforced in `__post_init__` |
| `CalculationPeriodDates` | effective + termination + frequency + roll + stub + BDA | `@dataclass(frozen=True)` (moved from Phase B per Minsky review) |
| `PaymentDates` | frequency + pay_relative_to + offset + BDA | `@dataclass(frozen=True)` (moved from Phase B per Minsky review) |
| `CounterpartyRoleEnum` | PARTY1, PARTY2 | Enum in `instrument/types.py` |
| `PayerReceiver` | payer + receiver (CounterpartyRoleEnum) | `@dataclass(frozen=True)` with **`payer != receiver`** invariant in `__post_init__` (a party cannot pay itself) |

**PayerReceiver integration:** Added as required field to `FixedLeg`, `FloatLeg`, `CDSPayoutSpec`, `SwaptionPayoutSpec` (4 types modified).

**ISO currency expansion:** Expand `VALID_CURRENCIES` from 31 to full ISO 4217 (~180 codes).

**Phase A-0 Prerequisite (Minsky mandate):** Before adding any new types, audit **every** `match` statement on union types and enums in production code and add `assert_never` guards. This includes:
- `mifid2.py` line 192: wildcard `case _: inst_fields = None` (silently drops new variants)
- `dodd_frank.py` line 100: wildcard `case _: return Err(...)` (silent failure)
- `calendar.py` line 29: `DayCountConvention` match with 3 cases and no fallthrough
- All `PaymentFrequency` matches in `ledger/irs.py` and `ledger/cds.py`
Without this, Phase A's enum expansions will introduce silent missing-case bugs at runtime.

**Estimated:** ~15 new types (11 truly new + 2 moved from Phase B + 2 enum expansions), ~60 new tests, ~180 lines of new code.

**Test gate:** After Phase A, no IRS/CDS payout can be constructed without specifying who pays and who receives. Every date field that needs adjustment carries its adjustment rule. Schedule generation terminates for all valid inputs where `start <= end` and `freq > 0`.

### Phase B: Observable and Index Taxonomy

**Depends on:** Phase A

**Delivers:**

| Type | Description | Attestor Design |
|------|-------------|-----------------|
| `FloatingRateIndexEnum` | SOFR, ESTR, SONIA, EURIBOR, TONA, TIBOR (~20 major indices) | Enum in `oracle/observable.py` (new file) |
| `FloatingRateIndex` | enum + designated_maturity (Period) | `@dataclass(frozen=True)` |
| `Index` | Discriminated union: `FloatingRateIndex \| CreditIndex \| EquityIndex \| FXRateIndex` | Union type |
| `Observable` | `Asset \| Index` (Basket deferred) | Union type |
| `PriceTypeEnum` | INTEREST_RATE, EXCHANGE_RATE, ASSET_PRICE, CASH_PRICE | Enum |
| `PriceExpressionEnum` | ABSOLUTE, PERCENTAGE_OF_NOTIONAL, PER_MILLE | Enum |
| `Price` | value + type + expression + currency | `@dataclass(frozen=True)` |
| `PriceQuantity` | price + quantity + observable | `@dataclass(frozen=True)` |
| `ObservationIdentifier` | observable + date + source | `@dataclass(frozen=True)` |
| `CalculationMethodEnum` | COMPOUNDING, AVERAGING | Enum |
| `FloatingRateCalculationParameters` | method + lookback + lockout + shift | `@dataclass(frozen=True)` |
| `ResetDates` | reset_frequency + fixing_offset + calculation_params (depends on `FloatingRateIndex`) | `@dataclass(frozen=True)` |

**Float index integration:** `FloatLeg.float_index` changes from `NonEmptyStr` to `FloatingRateIndex`.

**Estimated:** ~14 new types (CalculationPeriodDates and PaymentDates moved to Phase A), ~55 new tests.

**Test gate:** After Phase B, all floating rate references are validated against a known index set. No code path can introduce an unvalidated index string -- every constructor accepting a float index requires `FloatingRateIndex`, not `str` or `NonEmptyStr`. Observation identity is structured.

### Phase C: Product Enrichment

**Depends on:** Phase B

**Delivers:**

| Type | Description | Attestor Design |
|------|-------------|-----------------|
| `FixedRateSpecification` | rate + schedule (step-ups) + day_count | `@dataclass(frozen=True)` |
| `FloatingRateSpecification` | index + spread + cap + floor + multiplier + negative_treatment | `@dataclass(frozen=True)` |
| `RateSpecification` | `FixedRateSpecification \| FloatingRateSpecification` | Union type |
| `StubPeriod` | initial/final stub rates | `@dataclass(frozen=True)` |
| `CompoundingMethodEnum` | FLAT, STRAIGHT, SPREAD_EXCLUSIVE, NONE | Enum |
| Enriched `FixedLeg` | + `calculation_period_dates` + `payment_dates` + `stub` (NO reset_dates -- illegal for fixed legs) | Modified existing type |
| Enriched `FloatLeg` | + `calculation_period_dates` + `payment_dates` + `reset_dates` + `floating_rate_calc_params` + `stub` | Modified existing type |
| `CashSettlementTerms` | method + valuation_date + valuation_time | `@dataclass(frozen=True)` |
| `PhysicalSettlementTerms` | delivery_period + settlement_currency | `@dataclass(frozen=True)` |
| `SettlementTerms` | `CashSettlementTerms \| PhysicalSettlementTerms` | Union type |
| `ExerciseTerms` | `AmericanExercise \| EuropeanExercise \| BermudaExercise` | Union type |
| `PerformancePayoutSpec` | return_terms + underlier + observation | `@dataclass(frozen=True)` |
| `GeneralTerms` | reference_entity + reference_obligation + reference_info | `@dataclass(frozen=True)` |
| `ProtectionTerms` | credit_events + obligations + floating_amount_events | `@dataclass(frozen=True)` |

**Architectural decision (Minsky mandate):** CDM's `InterestRatePayout` uses a single type with `RateSpecification` choice and optional `ResetDates`. This admits illegal states: a fixed-rate payout with reset dates populated. Attestor preserves the **`FixedLeg` / `FloatLeg` separation** to make this illegal state unrepresentable. `FixedLeg` structurally cannot have `reset_dates`. `FloatLeg` structurally must have them.

**Payout migration:** `FixedLeg` and `FloatLeg` enriched with schedule types. `CDSPayoutSpec` enriched with `GeneralTerms` and `ProtectionTerms`. `OptionPayoutSpec` enriched with `ExerciseTerms`.

**Estimated:** ~15 new types, ~50 new tests.

**Test gate:** After Phase C, IRS payouts have full rate specification and schedule parameterization. CDS payouts carry reference entity details and credit event specifications.

### Phase D: Event and Lifecycle Alignment

**Depends on:** Phase C

**Delivers:**

| Type | Description | Attestor Design |
|------|-------------|-----------------|
| `Trade` | Enriched with trade_id, trade_date, parties, counterparty roles, legal_agreement_id | `@dataclass(frozen=True)` |
| `TradeState` | trade + status + reset_history + transfer_history | `@dataclass(frozen=True)` -- **snapshot, not mutable container**. State evolution is a chain of `(TradeState, BusinessEvent, TradeState)` triples. |
| `ClosedState` + `ClosedStateEnum` | MATURED, TERMINATED, NOVATED, EXERCISED, EXPIRED, CANCELLED | Enum + type |
| `TransferStatusEnum` | PENDING, INSTRUCTED, SETTLED, NETTED, DISPUTED | Enum |
| `QuantityChangePI` | quantity delta for partial termination / decrease | `@dataclass(frozen=True)` |
| `PartyChangePI` | old_party + new_party for novation | `@dataclass(frozen=True)` |
| `SplitPI` | split into sub-trades for allocation | `@dataclass(frozen=True)` |
| `TermsChangePI` | amendment to trade terms | `@dataclass(frozen=True)` |
| `IndexTransitionPI` | IBOR fallback transition | `@dataclass(frozen=True)` |
| `EventIntentEnum` | Allocation, Clearing, Novation, PartialTermination, etc. (~10 of 20 CDM values) | Enum |
| `CorporateActionTypeEnum` | CashDividend, StockDividend, StockSplit, ReverseStockSplit, Merger, SpinOff (~6 of 19) | Enum |
| `ActionEnum` | NEW, CORRECT, CANCEL | Enum |

**BusinessEvent enrichment:** Add `before`/`after` TradeState, `event_qualifier`, `event_ref` (causation chain to Transaction).

**Estimated:** ~14 new types, ~50 new tests.

**Test gate:** After Phase D, BusinessEvents carry before/after state snapshots. New PI types (QuantityChange, PartyChange, Split) have conservation law tests.

### Phase E: Collateral and Margin

**Depends on:** Phase D transitively (D depends on C depends on B). The collateral types themselves do not reference rate/schedule types from Phases B-C, but the phase ordering is serial because Phase E modifies types (`CollateralAgreement`) that may have been touched in Phase D. If Phase D is split, the collateral subset could be extracted into a parallel track.

**Delivers:**

| Type | Description | Attestor Design |
|------|-------------|-----------------|
| `Haircut` | `value in [0, 1)` | `@dataclass(frozen=True)` with bounds |
| `CollateralValuationTreatment` | haircut + margin_pct + fx_haircut | `@dataclass(frozen=True)` |
| `ConcentrationLimit` | asset_type + limit_value | `@dataclass(frozen=True)` |
| `StandardizedSchedule` | asset_class + product_class + notional + duration | `@dataclass(frozen=True)` |
| `AssetClassEnum` | INTEREST_RATES, CREDIT, FX, EQUITY, COMMODITY | Enum |
| `MarginCallIssuance` / `MarginCallResponse` | Workflow for margin calls | `@dataclass(frozen=True)` |

**Estimated:** ~8 new types, ~24 new tests.

### Phase F: Regulatory Reporting Enrichment

**Depends on:** Phase D

**Delivers:**

| Type | Description | Where |
|------|-------------|-------|
| CFI classification code | 6-char ISO 10962 | Add to `MiFIDIIReport` |
| Investment decision person / executing person | Natural person identification | Add to `MiFIDIIReport` |
| Risk-reducing transaction indicator | Boolean | Add to `MiFIDIIReport` + `EMIRTradeReport` |
| Securities financing indicator | Boolean | Add to `MiFIDIIReport` |
| Trading capacity | Enum (DEAL, MTCH, AOTC) | Add to `MiFIDIIReport` |
| `RestructuringEnum` | ModR, ModModR, R | Enum in `instrument/derivative_types.py` |
| Credit event expansion | Add obligationDefault, governmentalIntervention, etc. | Expand `CreditEventType` |

**Estimated:** ~4 new types/enums, ~12 new tests. Mostly field additions to existing types.

### File Allocation Plan

The file hard cap is 57 (currently 55, +2 new files permitted).

| File | New Types Housed | Phase |
|------|-----------------|-------|
| `core/types.py` | `Period`, `Schedule`, `DatedValue`, `AdjustableDate`, `RelativeDateOffset`, `BusinessDayAdjustments` | A |
| `core/calendar.py` | Expanded `DayCountConvention` enum, `RollConventionEnum`, `BusinessDayConventionEnum` | A |
| `instrument/types.py` | `CounterpartyRoleEnum`, `PayerReceiver`, `CalculationPeriodDates`, `PaymentDates` | A |
| `instrument/fx_types.py` (rename to `instrument/rate_types.py` in Phase C) | Enriched `FixedLeg`, `FloatLeg`, `FixedRateSpecification`, `FloatingRateSpecification`, `RateSpecification`, `StubPeriod` | C |
| **`oracle/observable.py`** (NEW -- slot 1 of 2) | `FloatingRateIndexEnum`, `FloatingRateIndex`, `Index`, `Observable`, `PriceTypeEnum`, `Price`, `PriceQuantity`, `ObservationIdentifier`, `ResetDates`, `FloatingRateCalculationParameters` | B |
| `instrument/lifecycle.py` | New PI types (`QuantityChangePI`, `PartyChangePI`, `SplitPI`, `TermsChangePI`, `IndexTransitionPI`), enriched `BusinessEvent`, `TradeState`, `ClosedState`, `Trade` | D |
| **`instrument/settlement.py`** (NEW -- slot 2 of 2) | `CashSettlementTerms`, `PhysicalSettlementTerms`, `SettlementTerms`, `ExerciseTerms` | C |
| `ledger/collateral.py` | `Haircut`, `CollateralValuationTreatment`, `ConcentrationLimit` | E |
| `reporting/mifid2.py` + `reporting/emir.py` | Field additions (CFI code, person ID, risk-reducing flag) | F |

### Cumulative Projection

| Phase | Running Tests | Running Types (gross) | After Consolidation | Running Lines | Status |
|-------|--------------|----------------------|--------------------:|---------------|--------|
| 0 (done) | 1,513 | 162 | 162 | 11,705 | COMPLETED |
| A-0 (`assert_never` sweep) | 1,513 | 162 | 162 | 11,738 | COMPLETED |
| A | ~1,580 | ~177 | ~173 | ~11,910 | PLANNED |
| B | ~1,635 | ~187 | ~181 | ~12,180 | PLANNED |
| C | ~1,685 | ~196 | ~188 | ~12,450 | PLANNED |
| D | ~1,735 | ~210 | ~196 | ~12,700 | PLANNED |
| E | ~1,759 | ~218 | ~199 | ~12,850 | PLANNED |
| F | ~1,771 | ~222 | ~198 | ~12,950 | PLANNED |

"After Consolidation" column applies the type budget strategies (Literal unions for small enums, enrichment instead of new types, etc.). Every phase boundary triggers a type count audit. **No phase ships above 200 types.**

### Type Budget Strategy

The hard cap is 200 named types. Phases A-F project ~233 before consolidation. The budget must close on paper before Phase A begins.

**Concrete type savings (targeting -35 types):**

| Strategy | Types Saved | Specifics |
|----------|------------|-----------|
| Merge small enums to `Literal` unions | -8 | `CounterpartyRoleEnum` (2 vals), `CalculationMethodEnum` (2 vals), `ActionEnum` (3 vals), `PriceExpressionEnum` (3 vals), `CompoundingMethodEnum` (4 vals), `PeriodEnum` (4 vals), `BusinessDayConventionEnum` (4 vals), `PriceTypeEnum` (4 vals) -- all under 5 values, use `Literal["PARTY1", "PARTY2"]` syntax instead of separate enum class |
| Avoid wrapper types | -4 | No `Periods`, `Dates`, `Cashflows`, `Schedules` wrappers; use bare `tuple[T, ...]` |
| Enrich existing types instead of new types | -6 | `FixedLeg`/`FloatLeg` enrichment (not new InterestRatePayout), `Trade` as enriched `Instrument`, `CDSPayoutSpec` enrichment (not new CreditDefaultPayout) |
| Consolidate new PI types as nested union | -5 | `QuantityChangePI | PartyChangePI | SplitPI | TermsChangePI | IndexTransitionPI` added to existing `PrimitiveInstruction` union (not 5 new top-level types -- they ARE the union members but counted as variants, not standalone classes only if designed as inner types) |
| Phase F delivered as field additions | -4 | CFI code, risk-reducing indicator, etc. are fields on existing `MiFIDIIReport`, not new types |
| Defer/merge at boundary | -8 | At each phase boundary, audit and merge types that turned out to be single-use |
| **Total savings** | **-35** | Projected final: ~198 types |

**Prerequisites (Minsky mandates):** Before Phase A begins:
- **P-1**: Build a concrete type budget spreadsheet with every proposed type assigned a file slot.
- **P-2**: `assert_never` sweep on all production match statements.
- **P-3**: Write `FixedLeg`/`FloatLeg` enrichment type signatures on paper and verify against Minsky test.

5. **Phase gating** -- at each phase boundary, count types and audit for consolidation. If count exceeds 200, the phase cannot ship until types are consolidated.

---

## 6. Structural Pattern Summary

### CDM Rosetta vs Attestor Python

| Aspect | CDM (Rosetta DSL) | Attestor (Python) |
|--------|-------------------|-------------------|
| Hierarchy | Deep inheritance (up to 6 levels) | Flat `@final @dataclass`, no inheritance |
| Polymorphism | Inheritance polymorphism + choice types | Discriminated unions (`type X = A \| B \| C`) |
| Validation | `condition` blocks (runtime) | Smart constructors + `__post_init__` (construction-time) |
| Mutability | Implementation choice | `frozen=True` enforced on every type |
| Error handling | Not modeled | `Result[T, E]` monad (`Ok`/`Err`) |
| Identity | Reference-based (`key`, `ref`) | Content-addressed (`content_hash`) |
| Numeric | Not specified | Pure Decimal (prec=28, no float) |
| Instructions | 13 optional fields on PrimitiveInstruction | Discriminated union of PI dataclasses |
| State model | State-centric (before -> event -> after) | Instruction-centric (ledger processes PIs) |
| Workflow | WorkflowStep envelope with approval | Direct processing, no envelope |
| Uncertainty | Not modeled | Giry monad, confidence classes |

### Translation Strategy

When translating CDM concepts to Attestor:
- **CDM inheritance** becomes **Attestor union types** (e.g., `InterestRatePayout extends PayoutBase` -> `Payout = IRSwapPayoutSpec | ...`)
- **CDM choice types** become **Attestor union types** (direct 1:1 mapping)
- **CDM conditions** become **`__post_init__` guards** (shifted from runtime to construction)
- **CDM optional fields** become **union variants** where the optionality encodes different states
- **CDM `(1..*)` cardinality** becomes **`tuple[T, ...]` with `len >= 1` in `__post_init__`**

---

## 7. Detailed Gap Reference

The full type-by-type analysis for each namespace is available in the following working documents:

| File | Namespace | Types Analyzed |
|------|-----------|---------------|
| `_gap_base.md` | `base-*` (datetime, math, identifiers, parties) | ~130 |
| `_gap_product.md` | `product-*` (payouts, schedules, settlement) | 138 |
| `_gap_event.md` | `event-*` (lifecycle, positions, workflow) | 60 |
| `_gap_observable.md` | `observable-*` (market data, indices, rates) | 62 |
| `_gap_legal_margin_reg.md` | `legaldocumentation-*`, `margin-*`, `regulation-*` | ~228 |

These files contain the complete type-by-type CDM definition, Attestor equivalent, status, gap details, severity, and notes for every type/enum in the Rosetta source.

---

## 8. Type Safety Invariants -- Current Status

### The Minsky Test

| Question | Status |
|----------|--------|
| Can illegal states be constructed? | **NO** -- `__post_init__` seals every smart constructor bypass |
| Is every case handled? | **YES** for gateway match; remaining match statements audited in Phase A |
| Is failure explicit? | **YES** -- `Ok[T] \| Err[str]` on every constructor |
| Would a reviewer catch a bug by reading? | **YES** -- frozen types, explicit invariants, no hidden mutation |
| Are invariants encoded or documented? | **ENCODED** in types and `__post_init__` |
| Is this total? | **YES** -- all match statements on expandable types have `assert_never` guards (Phase A-0 complete) |

### Ledger Conservation Law (INV-L01)

For every unit U and every `LedgerEngine.execute(transaction)` call:

```
sum(credit quantities for unit U) == sum(debit quantities for unit U)
```

This invariant is verified atomically. No partial execution. No balance drift.

---

*This document supersedes the prior `cdm_gap_review.md` and consolidates:*
- Direct Rosetta source analysis (438 in-scope + 232 legal = 670 types/enums compared)
- `_gap_base.md` (base namespace, ~130 types/enums)
- `_gap_product.md` (product namespace, 138 types/enums)
- `_gap_event.md` (event namespace, 60 types/enums)
- `_gap_observable.md` (observable namespace, 62 types/enums)
- `_gap_legal_margin_reg.md` (legal/margin/regulation, ~228 types/enums)

*Attestor source: 55 files, 11,705 lines, 162 types, 1,513 tests*
*CDM source: 142 Rosetta DSL files (62 type+enum files) in `common-domain-model/rosetta-source/`*
