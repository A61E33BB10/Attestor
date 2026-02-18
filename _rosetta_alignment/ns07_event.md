# NS7 Gap Analysis: event-common

**Source**: `event-common-enum.rosetta`, `event-common-type.rosetta`, `event-common-func.rosetta`
**Attestor**: `attestor/instrument/lifecycle.py`, `attestor/instrument/derivative_types.py`

---

## 1. Enum Gaps

### 1a. Existing enums — missing members

| Enum | Attestor members | CDM members | Missing |
|------|-----------------|-------------|---------|
| `ClosedStateEnum` | 6: MATURED, TERMINATED, NOVATED, EXERCISED, EXPIRED, CANCELLED | 7: +Allocated | `ALLOCATED` |
| `EventIntentEnum` | 10: ALLOCATION, CLEARING, COMPRESSION, CORPORATE_ACTION, EARLY_TERMINATION, EXERCISE, INCREASE, INDEX_TRANSITION, NOVATION, PARTIAL_TERMINATION | 23: +CashFlow, ContractFormation, ContractTermsAmendment, CorporateActionAdjustment, CreditEvent, Decrease, EarlyTerminationProvision, NotionalReset, NotionalStep, ObservationRecord, OptionExercise, OptionalExtension, OptionalCancellation, PortfolioRebalancing, PrincipalExchange, Reallocation, Repurchase | 13 new members |
| `CorporateActionTypeEnum` | 6: CASH_DIVIDEND, STOCK_DIVIDEND, STOCK_SPLIT, REVERSE_STOCK_SPLIT, MERGER, SPIN_OFF | 20: +Delisting, StockNameChange, StockIdentifierChange, RightsIssue, Takeover, StockReclassification, BonusIssue, ClassAction, EarlyRedemption, Liquidation, BankruptcyOrInsolvency, IssuerNationalization, Relisting, BespokeEvent | 14 new members |
| `CreditEventType` | 6: BANKRUPTCY, FAILURE_TO_PAY, RESTRUCTURING, OBLIGATION_DEFAULT, OBLIGATION_ACCELERATION, REPUDIATION_MORATORIUM | 13: +DistressedRatingsDowngrade, FailureToPayInterest, FailureToPayPrincipal, GovernmentalIntervention, ImpliedWritedown, MaturityExtension, Writedown | 7 new members |
| `ActionEnum` | 3: NEW, CORRECT, CANCEL | 3: New, Correct, Cancel | Values → PascalCase |

### 1b. Existing enums — value alignment

| Enum | Current values | CDM values | Action |
|------|---------------|------------|--------|
| `ClosedStateEnum` | SCREAMING_SNAKE | PascalCase | Change values to PascalCase |
| `EventIntentEnum` | SCREAMING_SNAKE | PascalCase | Change values to PascalCase |
| `CorporateActionTypeEnum` | SCREAMING_SNAKE | PascalCase | Change values to PascalCase |
| `ActionEnum` | SCREAMING_SNAKE | PascalCase | Change values to PascalCase |
| `TransferStatusEnum` | SCREAMING_SNAKE | PascalCase | Change values to PascalCase |
| `CreditEventType` | SCREAMING_SNAKE | PascalCase | Rename to `CreditEventTypeEnum`, change values to PascalCase |

### 1c. Existing enums — naming alignment

| Current name | CDM name | Action |
|-------------|----------|--------|
| `CreditEventType` | `CreditEventTypeEnum` | Rename (add `Enum` suffix) |
| `EventIntentEnum` | `EventIntentEnum` | OK (CDM calls it `IntentEnum` but Attestor name is fine) |
| `MarginType` | N/A | Not in event-common (lives in collateral namespace) |

### 1d. New CDM enums needed

| Enum | Members | Priority |
|------|---------|----------|
| `ExecutionTypeEnum` | Electronic, OffFacility, OnVenue (3) | HIGH — needed for Trade.executionDetails |
| `ConfirmationStatusEnum` | Confirmed, Unconfirmed (2) | MEDIUM |
| `AffirmationStatusEnum` | Affirmed, Unaffirmed (2) | MEDIUM |
| `PerformanceTransferTypeEnum` | Commodity, Correlation, Dividend, Equity, Interest, Volatility, Variance (7) | LOW |
| `ValuationTypeEnum` | MarkToMarket, MarkToModel (2) | LOW |
| `ValuationSourceEnum` | CentralCounterparty (1) | LOW |
| `ValuationScopeEnum` | Collateral, Trade (2) | LOW |
| `PriceTimingEnum` | ClosingPrice, OpeningPrice (2) | LOW |
| `RecordAmountTypeEnum` | AccountTotal, GrandTotal, ParentTotal (3) | LOW |
| `InstructionFunctionEnum` | Execution, ContractFormation, QuantityChange, Renegotiation, Compression (5) | LOW |
| `AssetTransferTypeEnum` | FreeOfPayment (1) | LOW |
| `PositionEventIntentEnum` | PositionCreation, CorporateActionAdjustment, Decrease, Increase, Transfer, OptionExercise, Valuation (7) | LOW |
| `CallTypeEnum` | MarginCall, Notification, ExpectedCall (3) | LOW |
| `MarginCallActionEnum` | Delivery, Return (2) | LOW |
| `CollateralStatusEnum` | FullAmount, SettledAmount, InTransitAmount (3) | LOW |
| `MarginCallResponseTypeEnum` | AgreeinFull, PartiallyAgree, Dispute (3) | LOW |
| `RegMarginTypeEnum` | VM, RegIM, NonRegIM (3) | LOW |
| `RegIMRoleEnum` | Pledgor, Secured (2) | LOW |
| `HaircutIndicatorEnum` | PreHaircut, PostHaircut (2) | LOW |

---

## 2. Type Gaps

### 2a. ClosedState enrichment

**CDM** (`ClosedState`):
```
state: ClosedStateEnum (1..1)
activityDate: date (1..1)
effectiveDate: date (0..1)
lastPaymentDate: date (0..1)
```

**Attestor** (`ClosedState`):
```python
state: ClosedStateEnum
effective_date: date
```

**Gap**: Missing `activity_date` (1..1 in CDM — the date the closing action happened), `last_payment_date` (0..1). Attestor's `effective_date` maps to CDM's `activityDate`, not CDM's `effectiveDate`.

**Action**: Rename `effective_date` → `activity_date`, add optional `effective_date: date | None` and `last_payment_date: date | None`.

### 2b. Trade enrichment

**CDM** (`Trade extends TradableProduct`):
```
tradeIdentifier: TradeIdentifier (1..*)
tradeDate: date (1..1)
tradeTime: TimeZone (0..1)
party: Party (0..*)
partyRole: PartyRole (0..*)
executionDetails: ExecutionDetails (0..1)
contractDetails: ContractDetails (0..1)
clearedDate: date (0..1) [deprecated]
collateral: Collateral (0..1)
account: Account (0..*) [deprecated]
+ 20+ conditions
```

**Attestor** (`Trade`):
```python
trade_id: NonEmptyStr
trade_date: date
payer_receiver: PayerReceiver
product_id: NonEmptyStr
currency: NonEmptyStr
legal_agreement_id: NonEmptyStr | None
```

**Gap**: CDM Trade is much richer. Key missing fields for equity critical path:
- `execution_type: ExecutionTypeEnum | None` (from executionDetails)
- `execution_venue: NonEmptyStr | None` (from executionDetails)
- `cleared_date: date | None` (deprecated but present)

**Action (NS7b)**: Add optional CDM fields to Trade.

### 2c. TradeState enrichment

**CDM** (`TradeState`):
```
trade: Trade (1..1)
state: State (0..1)        # State = closedState + positionState
resetHistory: Reset (0..*)  # Rich Reset objects with value + date + observations
transferHistory: TransferState (0..*)  # TransferState = Transfer + TransferStatusEnum
observationHistory: ObservationEvent (0..*)
valuationHistory: Valuation (0..*)
```

**Attestor** (`TradeState`):
```python
trade: Trade
status: PositionStatusEnum
closed_state: ClosedState | None
reset_history: tuple[UtcDatetime, ...]       # timestamps only
transfer_history: tuple[UtcDatetime, ...]    # timestamps only
```

**Gap**:
- CDM wraps `closedState` + `positionState` in a `State` object; Attestor puts them flat on TradeState (acceptable simplification)
- CDM reset_history uses rich `Reset` objects; Attestor uses bare timestamps
- CDM transfer_history uses `TransferState` objects; Attestor uses bare timestamps
- Missing: `observationHistory`, `valuationHistory`

**Action (NS7b)**: Add optional `observation_history` and `valuation_history` fields. Consider whether to enrich reset/transfer history (deferred — current timestamps are adequate for the equity path).

### 2d. BusinessEvent enrichment

**CDM** (`BusinessEvent extends EventInstruction`):
```
# from EventInstruction:
instruction: PrimitiveInstruction (0..1)   # note: CDM PrimitiveInstruction is flat type
before: TradeState (0..1)
intent: EventIntentEnum (0..1)
eventDate: date (0..1)
effectiveDate: date (0..1)
packageInformation: IdentifiedList (0..1)
corporateActionIntent: CorporateActionTypeEnum (0..1)

# from BusinessEvent:
eventQualifier: string (0..1)
after: TradeState (0..*)                    # note: 0..*
```

**Attestor** (`BusinessEvent`):
```python
instruction: PrimitiveInstruction
timestamp: UtcDatetime
attestation_id: str | None
before: TradeState | None
after: TradeState | None
event_intent: EventIntentEnum | None
action: ActionEnum
event_ref: NonEmptyStr | None
```

**Gap**:
- CDM separates `eventDate` (when event happens) from `effectiveDate` (when it takes contractual effect). Attestor has `timestamp` (datetime, not date).
- CDM `after` is `TradeState (0..*)` (multiple output trades, e.g. for splits). Attestor has single `TradeState | None`.
- Missing: `event_date: date | None`, `effective_date: date | None`, `event_qualifier: str | None`, `corporate_action_intent: CorporateActionTypeEnum | None`
- `after` should be `tuple[TradeState, ...] | None` to support split events

**Action (NS7b)**: Add missing fields, change `after` to tuple.

---

## 3. PrimitiveInstruction modeling

**CDM**: Single flat `PrimitiveInstruction` type with 12 optional fields (one-of semantics):
```
contractFormation, execution, exercise, partyChange, quantityChange,
reset, split, termsChange, transfer, indexTransition, stockSplit,
observation, valuation
```

**Attestor**: Union of 18 separate PI types:
```python
PrimitiveInstruction = ExecutePI | TransferPI | DividendPI | ExercisePI | AssignPI
    | ExpiryPI | MarginPI | FixingPI | NettingPI | MaturityPI
    | CreditEventPI | SwaptionExercisePI | CollateralCallPI
    | QuantityChangePI | PartyChangePI | SplitPI | TermsChangePI | IndexTransitionPI
```

**Assessment**: Attestor's union approach is type-safe and Pythonic (makes illegal states unrepresentable via `match`). CDM's flat approach with runtime one-of is the Java/Rosetta idiom. The union approach is **preferred** — no change needed.

Attestor has PI types CDM doesn't (DividendPI, AssignPI, ExpiryPI, MarginPI, FixingPI, NettingPI, MaturityPI, SwaptionExercisePI, CollateralCallPI) — these are more granular than CDM. CDM rolls dividends/corporate actions into `CorporateAction` observations and handles margin through the margin-call type hierarchy. These extra PI types are **acceptable extensions**.

---

## 4. Phasing

### NS7a — Enums (this session)

1. Expand `ClosedStateEnum`: add `ALLOCATED` (PascalCase values)
2. Expand `EventIntentEnum`: add 13 CDM members (PascalCase values)
3. Expand `CorporateActionTypeEnum`: add 14 CDM members (PascalCase values)
4. Expand `CreditEventType` → rename to `CreditEventTypeEnum`: add 7 CDM members (PascalCase values)
5. Align `ActionEnum` values to PascalCase
6. Align `TransferStatusEnum` values to PascalCase
7. Add `ExecutionTypeEnum` (3 members)
8. Add `ConfirmationStatusEnum` (2 members)
9. Add `AffirmationStatusEnum` (2 members)
10. Update all usages site-wide (bulk rename CreditEventType → CreditEventTypeEnum)

### NS7b — Type enrichment (deferred)

1. Enrich `ClosedState`: rename effective_date → activity_date, add effective_date + last_payment_date
2. Enrich `Trade`: add execution_type, execution_venue, cleared_date
3. Enrich `TradeState`: add observation_history, valuation_history
4. Enrich `BusinessEvent`: add event_date, effective_date, event_qualifier, corporate_action_intent; change after to tuple

### NS7c — Deep types (deferred)

1. Reset, TransferState, Transfer, Valuation, CreditEvent, CorporateAction types
2. Billing types (SecurityLendingInvoice, BillingRecord, etc.)
3. Margin call type hierarchy (MarginCallBase → MarginCallExposure/Issuance/Response)
4. Qualification functions (Qualify_*)
