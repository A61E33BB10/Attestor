# NS6: product-common-settlement — Gap Analysis

## CDM Rosetta Source
- `product-common-settlement-enum.rosetta` — 8 enums
- `product-common-settlement-type.rosetta` — ~46 types
- `product-common-settlement-func.rosetta` — 6 functions
- `product-common-schedule-enum.rosetta` — 4 enums
- `product-common-schedule-type.rosetta` — ~37 types
- `product-common-enum.rosetta` — 1 enum (NotionalAdjustmentEnum)
- `product-common-type.rosetta` — PayoutBase, ResolvablePriceQuantity

Total CDM: **14 enums, 83 types, 6 functions, 70+ conditions**

## Current Attestor Settlement Types

| Type | Fields | Notes |
|------|--------|-------|
| `SettlementType` (Enum) | PHYSICAL, CASH | CDM has 4: +Election, +CashOrPhysical |
| `CashSettlementTerms` | settlement_method, valuation_date, currency | CDM: 8 fields + 5 conditions |
| `PhysicalSettlementTerms` | delivery_period_days, settlement_currency | CDM: 6 fields + 1 condition |
| `SettlementTerms` (alias) | Cash \| Physical union | CDM: extends SettlementBase with 7 inherited fields |

## Gap Summary

### Priority A — Enums (direct alignment, low risk)

| CDM Enum | Members | Attestor Status | Action |
|----------|---------|-----------------|--------|
| `SettlementTypeEnum` | Cash, Physical, Election, CashOrPhysical (4) | Partial — 2 of 4 | Add ELECTION, CASH_OR_PHYSICAL; PascalCase values |
| `CashSettlementMethodEnum` | 12 ISDA methods | Missing | Create — critical for CDS/swaption cash settlement |
| `DeliveryMethodEnum` | DvP, FoP, PreDelivery, PrePayment (4) | Missing | Create |
| `TransferSettlementEnum` | DvD, DvP, PvP, NotCentral (4) | Missing | Create |
| `StandardSettlementStyleEnum` | Standard, Net, StandardAndNet, PairAndNet (4) | Missing | Create |
| `SettlementCentreEnum` | EuroclearBank, ClearstreamBankingLuxembourg (2) | Missing | Create |
| `ScheduledTransferEnum` | 12 cashflow types | Missing | Create |
| `UnscheduledTransferEnum` | Recall, Return (2) | Missing | Create |

### Priority B — Settlement types (enrich existing)

| CDM Type | Key Fields | Attestor Status | Action |
|----------|-----------|-----------------|--------|
| `SettlementBase` | settlementType + transferSettlementType + currency + date + centre + provision + style (7) | Missing | Create as dataclass (SettlementTerms inherits) |
| `SettlementTerms` (extends SettlementBase) | + cashSettlementTerms + physicalSettlementTerms | Type alias only | Promote to dataclass extending SettlementBase |
| `CashSettlementTerms` | +cashSettlementMethod + valuationMethod + valuationDate + valuationTime + cashSettlementAmount + recoveryFactor + fixedSettlement + accruedInterest (8) | 3 fields | Enrich with 5 more optional CDM fields |
| `PhysicalSettlementTerms` | +clearedPhysicalSettlement + predeterminedClearingOrganizationParty + physicalSettlementPeriod + deliverableObligations + escrow + sixtyBusinessDaySettlementCap (6) | 2 fields | Enrich with 4 more optional CDM fields (stub DeliverableObligations) |
| `PhysicalSettlementPeriod` | businessDaysNotSpecified \| businessDays \| maximumBusinessDays | Missing | Create (one-of choice) |
| `SettlementDate` | adjustableOrRelativeDate \| valueDate \| adjustableDates \| businessDateRange + cashSettlementBusinessDays + paymentDelay (6) | Missing | Create (simplified stub) |

### Priority C — Cashflow types (new, lower priority)

| CDM Type | Purpose | Action |
|----------|---------|--------|
| `AssetFlowBase` | Base for asset transfers (quantity + asset + settlementDate) | Defer — no consumer yet |
| `Cashflow` (extends AssetFlowBase) | Computed cashflow outcome | Defer |
| `CashflowType` | Scheduled vs non-scheduled classification | Defer |
| `PayoutBase` | Base for all payouts (payerReceiver + priceQuantity + principal + settlement) | Defer — would require payout refactor |
| `ResolvablePriceQuantity` | Varying quantities across legs/time | Defer |
| `PrincipalPayments` | Principal exchange specification | Defer |
| `DeliverableObligations` | 22-field ISDA deliverable obligation terms | Defer — CDS-specific deep detail |

### Priority D — Schedule types (new, low priority)

The 37 schedule types (CalculationPeriodDates, PaymentDates, ResetDates, etc.) are deeply nested IRS/CDS calculation infrastructure. Defer entirely — Attestor's schedule needs are covered by existing Period/Schedule types from base-math.

## Proposed Phasing

### NS6a: Enums (8 new enums + SettlementType expansion)
- Expand `SettlementType` → `SettlementTypeEnum` (4 members, PascalCase)
- Create 7 new enums: CashSettlementMethodEnum, DeliveryMethodEnum, TransferSettlementEnum, StandardSettlementStyleEnum, SettlementCentreEnum, ScheduledTransferEnum, UnscheduledTransferEnum
- Bulk rename SettlementType → SettlementTypeEnum across codebase
- ~24 new tests

### NS6b: Settlement type enrichment
- Create `PhysicalSettlementPeriod` (one-of: businessDaysNotSpecified | businessDays | maximumBusinessDays)
- Enrich `CashSettlementTerms` with CDM optional fields
- Enrich `PhysicalSettlementTerms` with CDM optional fields
- Promote `SettlementTerms` from type alias to SettlementBase-like dataclass
- ~25 new tests

### NS6c: Cashflow base types (future)
- AssetFlowBase, Cashflow, CashflowType, PayoutBase
- Deferred — no consumers in current Attestor

### NS6d: Schedule types (future)
- CalculationPeriodDates, PaymentDates, ResetDates, etc.
- Deferred — covered by existing Period/Schedule

## Impact Estimate (NS6a + NS6b)
- New enums: 7 + 1 rename = 8
- New types: 1 (PhysicalSettlementPeriod)
- Modified types: 3 (SettlementType→SettlementTypeEnum, CashSettlementTerms, PhysicalSettlementTerms)
- Modified: SettlementTerms (alias → dataclass)
- ~50 new tests
- Files touched: ~25 (bulk rename SettlementType → SettlementTypeEnum)
