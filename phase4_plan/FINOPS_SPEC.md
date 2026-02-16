# Attestor Phase 4 -- Credit and Structured Products: Financial Operations Specification

**Author:** FinOps Architect
**Date:** 2026-02-15
**Status:** Draft -- For Committee Review
**Scope:** Ledger booking (Pillar II), regulatory reporting (Pillar IV), infrastructure (Kafka + Postgres), and conservation laws for CDS, swaptions, and collateral management.
**Companion:** `PLAN.md` (Gatheral) covers Oracle (Pillar III) mathematics -- SVI/SSVI calibration, credit curve bootstrap, arbitrage gates, numerical methods.

---

## Table of Contents

1. [CDS Ledger Booking](#1-cds-ledger-booking)
2. [Swaption Ledger Booking](#2-swaption-ledger-booking)
3. [Collateral Management](#3-collateral-management)
4. [Regulatory Reporting](#4-regulatory-reporting)
5. [Infrastructure](#5-infrastructure)
6. [Conservation Laws](#6-conservation-laws)
7. [Build Order and Test Budget](#7-build-order-and-test-budget)
8. [Integration Test Scenarios](#8-integration-test-scenarios)
9. [Risk Register](#9-risk-register)
10. [Acceptance Criteria](#10-acceptance-criteria)

---

## Existing Pattern Summary

Before specifying Phase 4, here is the established ledger booking pattern from Phases 2 and 3 that Phase 4 MUST follow:

- **All transaction functions** return `Ok[Transaction] | Err[ValidationError]`.
- **All money arithmetic** uses `Decimal` with `localcontext(ATTESTOR_DECIMAL_CONTEXT)`.
- **All Move quantities** are `PositiveDecimal`. Direction is encoded by source/destination, not by sign.
- **All Move creation** uses `Move.create()` for validated construction (source != destination, non-empty fields).
- **All functions are pure**: no side effects, no shared mutable state.
- **Conservation**: for every Transaction, `sigma(unit) = 0` for every unit involved. This means the sum of all quantities leaving accounts equals the sum entering accounts, per unit.
- **Contract unit strings** follow a convention: `OPT-{underlying}-{type}-{strike}-{expiry}` for options, etc.
- **Reporting is projection** (INV-R01): reports contain exactly the fields from the order, reformatted. No new values are computed.
- **engine.py is never modified**: all new products work through the existing `Transaction`/`Move` abstraction (Principle V).

Reference files:
- `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/transactions.py` -- Move, Transaction, Account types
- `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/options.py` -- Option premium, exercise, expiry
- `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/futures.py` -- Futures margin
- `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/irs.py` -- IRS cashflows
- `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/fx_settlement.py` -- FX settlement
- `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/reporting/emir.py` -- EMIR reporting
- `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/reporting/mifid2.py` -- MiFID II reporting

---

## 1. CDS Ledger Booking

### 1.1 CDS Financial Structure (First Principles)

A Credit Default Swap is a bilateral contract between a **protection buyer** and a **protection seller** on a **reference entity**. From the ledger's perspective, a CDS is a series of deterministic premium payments (like the fixed leg of an IRS) plus a single contingent protection payment (triggered by a credit event).

The fundamental accounting identity for a CDS:

```
sum(all_premiums_paid_by_buyer) + accrued_premium_at_event - protection_payment_to_buyer = net_cost_of_protection
```

And the bilateral zero-sum:

```
buyer_total_cashflow + seller_total_cashflow = 0
```

This must hold to the penny.

### 1.2 CDS Account Structure

| Account | AccountType | Purpose |
|---------|------------|---------|
| `buyer_cash` | `CASH` | Protection buyer's cash account |
| `seller_cash` | `CASH` | Protection seller's cash account |
| `buyer_cds_position` | `DERIVATIVES` | Buyer's CDS position (positive = long protection) |
| `seller_cds_position` | `DERIVATIVES` | Seller's CDS position (positive = short protection) |

The `ACCRUALS` account type (already in `AccountType` enum) can be used for tracking accrued premium between payment dates in future phases, but in Phase 4 accrued premium is computed at credit event time and settled directly.

### 1.3 CDS Contract Unit Convention

```
CDS-{reference_entity}-{seniority}-{currency}-{maturity_date_iso}
```

Example: `CDS-FORD_MOTOR_CO-SNRFOR-USD-2031-03-20`

### 1.4 CDS Transaction Functions

All functions live in new file `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/cds.py`.

#### 1.4.1 Trade Booking: `create_cds_trade_transaction`

At trade inception, no cash changes hands. A CDS position is opened bilaterally.

**Moves:**
```
Move 1: CDS position (notional) seller_cds_position -> buyer_cds_position
```

**Signature:**
```python
def create_cds_trade_transaction(
    instrument_id: str,
    buyer_position_account: str,
    seller_position_account: str,
    notional: Decimal,
    contract_unit: str,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
```

**Pattern:** Identical to `create_futures_open_transaction` in `futures.py` (line 18-68). Position opens, no cash exchange.

**Conservation:** sigma(contract_unit) = 0 after the Move.

#### 1.4.2 Premium Payment: `create_cds_premium_transaction`

Periodic premium payment from protection buyer to protection seller.

**Premium calculation (ISDA standard):**
```
premium = notional * spread * dcf(period_start, period_end, ACT_360)
```

**Moves:**
```
Move 1: Cash (premium) buyer_cash -> seller_cash
```

**Signature:**
```python
def create_cds_premium_transaction(
    instrument_id: str,
    buyer_cash_account: str,
    seller_cash_account: str,
    notional: Decimal,
    spread: Decimal,               # annual spread in decimal (0.01 = 100 bps)
    period_start: date,
    period_end: date,
    day_count: DayCountConvention,  # ACT_360 for standard CDS
    currency: str,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
```

**Pattern:** Analogous to `create_irs_cashflow_transaction` in `irs.py` (line 192-259). Single cash Move for a scheduled cashflow.

**Conservation:** sigma(currency) = 0. Buyer pays exactly what seller receives.

**Validation:**
- `notional > 0` (via PositiveDecimal)
- `spread > 0` (via PositiveDecimal)
- `period_start < period_end`
- `premium > 0` (computed amount must be positive)

#### 1.4.3 Credit Event Settlement: `create_cds_credit_event_transaction`

When a credit event occurs, three legs settle atomically in a single Transaction:

**Moves:**
```
Move 1: Protection payment = notional * (1 - recovery_rate), seller_cash -> buyer_cash
Move 2: Accrued premium = notional * spread * dcf(last_payment_date, determination_date), buyer_cash -> seller_cash
Move 3: Position close = notional, buyer_cds_position -> seller_cds_position
```

If accrued premium is zero (credit event falls exactly on a premium payment date), Move 2 is omitted.

**Signature:**
```python
def create_cds_credit_event_transaction(
    instrument_id: str,
    buyer_cash_account: str,
    seller_cash_account: str,
    buyer_position_account: str,
    seller_position_account: str,
    notional: Decimal,
    recovery_rate: Decimal,          # from ISDA auction, in [0, 1)
    spread: Decimal,
    last_premium_date: date,
    determination_date: date,
    day_count: DayCountConvention,
    currency: str,
    contract_unit: str,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
```

**Pattern:** Closest analogy is `create_cash_settlement_exercise_transaction` in `options.py` (line 190-276): cash settlement + position close in one Transaction.

**Conservation:**
- sigma(currency) = 0 (protection payment and accrued premium are both cash moves)
- sigma(contract_unit) = 0 (position fully closed)

**The fundamental CDS settlement identity:**
```
protection_payment = notional * (1 - recovery_rate)
```

Equivalently: `protection_payment + notional * recovery_rate = notional`. This is the credit identity -- the protection payment plus the recovered value equals par. This MUST hold exactly in Decimal arithmetic.

**Validation:**
- `0 <= recovery_rate < 1` -- recovery_rate = 1 means no loss (protection payment = 0, but this is a degenerate case; reject it since there is no Move to create)
- `recovery_rate >= 0` -- negative recovery is meaningless
- `determination_date > last_premium_date` (or equal, in which case accrued = 0)
- `notional > 0`

**Edge cases (must be tested):**
- recovery_rate = 0: total loss, protection_payment = notional
- recovery_rate very close to 1 (e.g. 0.999): protection_payment is tiny. Accrued premium may exceed it. Net flow reverses direction (buyer pays net to seller). This is correct -- the buyer still pays accrued premium even if protection payment is small.
- Credit event on premium payment date: accrued_premium = 0, Move 2 omitted.
- Credit event one day after premium payment: accrued_premium = notional * spread * 1/360 (ACT/360).

#### 1.4.4 Maturity: `create_cds_maturity_transaction`

If the CDS reaches maturity without a credit event:

**Moves:**
```
Move 1: Position close = notional, buyer_cds_position -> seller_cds_position
```

No cash. The last premium payment was already made on the final scheduled date.

**Signature:**
```python
def create_cds_maturity_transaction(
    instrument_id: str,
    buyer_position_account: str,
    seller_position_account: str,
    notional: Decimal,
    contract_unit: str,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
```

**Pattern:** Identical to `create_expiry_transaction` in `options.py` (line 279-328). Position closes, no cash.

**Conservation:** sigma(contract_unit) returns to 0.

### 1.5 CDS Premium Schedule Generation

**Function:** `generate_cds_premium_schedule`

Reuses the scheduling infrastructure from `irs.py`. CDS uses:
- Day count: ACT/360 (ISDA standard)
- Payment frequency: QUARTERLY
- Standard dates: 20-Mar, 20-Jun, 20-Sep, 20-Dec (IMM dates)
- First period: short stub from effective date to next IMM date

**Signature:**
```python
def generate_cds_premium_schedule(
    notional: Decimal,
    spread: Decimal,
    effective_date: date,
    maturity_date: date,
    day_count: DayCountConvention,
    payment_frequency: PaymentFrequency,
    currency: str,
) -> Ok[CashflowSchedule] | Err[str]:
```

**Pattern:** Delegates to `_generate_period_dates` from `irs.py` for the period date generation. The premium amount per period is `notional * spread * dcf(period_start, period_end, ACT_360)`.

The schedule also stores IMM date alignment:

```python
CDS_IMM_MONTHS = (3, 6, 9, 12)
CDS_IMM_DAY = 20

def next_imm_date(from_date: date) -> date:
    """Return the next CDS IMM date (20th of Mar/Jun/Sep/Dec) after from_date."""
```

### 1.6 CDS Instrument Types

#### New enums in `attestor/instrument/credit_types.py`:

```python
class CreditEventType(Enum):
    BANKRUPTCY = "BANKRUPTCY"
    FAILURE_TO_PAY = "FAILURE_TO_PAY"
    RESTRUCTURING = "RESTRUCTURING"
    OBLIGATION_ACCELERATION = "OBLIGATION_ACCELERATION"
    OBLIGATION_DEFAULT = "OBLIGATION_DEFAULT"
    REPUDIATION_MORATORIUM = "REPUDIATION_MORATORIUM"

class Seniority(Enum):
    SENIOR_UNSECURED = "SNRFOR"     # ISDA code
    SUBORDINATED = "SUBLT2"
    SENIOR_SECURED = "SECDOM"

class RestructuringType(Enum):
    NO_RESTRUCTURING = "XR"
    FULL_RESTRUCTURING = "CR"
    MODIFIED_RESTRUCTURING = "MR"
    MODIFIED_MOD_RESTRUCTURING = "MM"
```

#### New detail type in `attestor/instrument/derivative_types.py`:

```python
@final
@dataclass(frozen=True, slots=True)
class CDSDetail:
    """CDS-specific fields on a CanonicalOrder."""
    reference_entity: NonEmptyStr
    reference_entity_lei: LEI
    seniority: Seniority
    restructuring_type: RestructuringType
    spread: PositiveDecimal
    notional: PositiveDecimal
    effective_date: date
    maturity_date: date
    day_count: DayCountConvention
    payment_frequency: PaymentFrequency

    @staticmethod
    def create(...) -> Ok[CDSDetail] | Err[str]:
        # Validates: effective_date < maturity_date, all refined types
        ...
```

#### Updated InstrumentDetail union:

```python
type InstrumentDetail = (
    EquityDetail | OptionDetail | FuturesDetail
    | FXDetail | IRSwapDetail
    | CDSDetail | SwaptionDetail
)
```

### 1.7 CDS Lifecycle

New `PrimitiveInstruction` variants:

```python
@final
@dataclass(frozen=True, slots=True)
class CreditEventPI:
    """Credit event declaration instruction."""
    instrument_id: NonEmptyStr
    reference_entity: NonEmptyStr
    event_type: CreditEventType
    determination_date: date
    auction_date: date | None
    recovery_rate: Decimal | None

@final
@dataclass(frozen=True, slots=True)
class AuctionSettlementPI:
    """Auction result settles CDS protection leg."""
    instrument_id: NonEmptyStr
    recovery_rate: Decimal
    auction_date: date
    settlement_date: date
```

CDS transition table:

```python
CDS_TRANSITIONS: TransitionTable = frozenset({
    (PositionStatusEnum.PROPOSED, PositionStatusEnum.FORMED),
    (PositionStatusEnum.PROPOSED, PositionStatusEnum.CANCELLED),
    (PositionStatusEnum.FORMED, PositionStatusEnum.SETTLED),
    (PositionStatusEnum.FORMED, PositionStatusEnum.CANCELLED),
    (PositionStatusEnum.SETTLED, PositionStatusEnum.CLOSED),
})
```

### 1.8 Tests: `tests/test_cds.py`

| Test | What it verifies |
|------|-----------------|
| `test_cds_trade_transaction_creates_position` | Single position Move, no cash |
| `test_cds_trade_conservation` | sigma(contract_unit) = 0 |
| `test_cds_premium_amount_calculation` | premium = notional * spread * dcf |
| `test_cds_premium_transaction_single_move` | One cash Move buyer -> seller |
| `test_cds_premium_conservation` | sigma(currency) = 0 |
| `test_cds_premium_schedule_imm_dates` | Schedule aligns to 20-Mar/Jun/Sep/Dec |
| `test_cds_premium_schedule_short_stub` | First period is short stub |
| `test_cds_credit_event_three_moves` | Protection + accrued + position close |
| `test_cds_credit_event_protection_payment` | = notional * (1 - recovery_rate) |
| `test_cds_credit_event_accrued_premium` | = notional * spread * dcf(last_pay, det_date) |
| `test_cds_settlement_identity` | protection + recovery = notional (exact) |
| `test_cds_credit_event_conservation_cash` | sigma(currency) = 0 |
| `test_cds_credit_event_conservation_position` | sigma(contract_unit) = 0 |
| `test_cds_credit_event_recovery_zero` | Total loss: protection = notional |
| `test_cds_credit_event_recovery_high` | Net flow reverses (buyer pays seller) |
| `test_cds_credit_event_on_payment_date` | Accrued = 0, only 2 Moves |
| `test_cds_maturity_position_close_only` | Single position Move, no cash |
| `test_cds_maturity_conservation` | sigma(contract_unit) = 0 |
| `test_cds_full_lifecycle_zero_sum` | buyer_total + seller_total = 0 |
| `test_cds_invalid_recovery_rate_gte_1` | Err returned |
| `test_cds_invalid_recovery_rate_negative` | Err returned |
| `test_cds_invalid_empty_accounts` | Err returned |
| `test_cds_invalid_zero_notional` | Err returned |
| `test_hypothesis_cds_premium_conservation` | 200 random examples |
| `test_hypothesis_cds_credit_event_conservation` | 200 random examples |
| `test_hypothesis_cds_bilateral_zero_sum` | 200 random lifecycle examples |

**Expected tests: ~35**

---

## 2. Swaption Ledger Booking

### 2.1 Swaption Financial Structure (First Principles)

A **European swaption** is an option to enter an IRS at a predetermined fixed rate on expiry. The key insight for the ledger: a swaption decomposes into two distinct phases.

**Phase A (option lifetime):** Premium is paid, position exists. Identical pattern to vanilla options in `options.py`.

**Phase B (if exercised):** Option position closes, IRS position opens. The IRS then follows the complete Phase 3 IRS lifecycle (`generate_fixed_leg_schedule`, `generate_float_leg_schedule`, `apply_rate_fixing`, `create_irs_cashflow_transaction`).

The swaption exercise is the bridge between Phase 2 (options) and Phase 3 (IRS). It reuses both.

### 2.2 Swaption Account Structure

| Account | AccountType | Purpose |
|---------|------------|---------|
| `buyer_cash` | `CASH` | Premium payment (same as option buyer) |
| `seller_cash` | `CASH` | Premium received |
| `buyer_swaption_position` | `DERIVATIVES` | Long swaption position |
| `seller_swaption_position` | `DERIVATIVES` | Short swaption position |

On exercise, IRS accounts are created per the Phase 3 convention.

### 2.3 Swaption Contract Unit Convention

```
SWAPTION-{PAYER|RECEIVER}-{strike_rate}-{expiry_date_iso}-{underlying_tenor}
```

Example: `SWAPTION-PAYER-0.035-2027-06-20-5Y`

### 2.4 Swaption Transaction Functions

All functions live in new file `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/swaption.py`.

#### 2.4.1 Premium: `create_swaption_premium_transaction`

**Moves:**
```
Move 1: Cash (premium) buyer_cash -> seller_cash
Move 2: Swaption position (quantity) seller_position -> buyer_position
```

Premium is upfront (not periodic).

**Signature:**
```python
def create_swaption_premium_transaction(
    order: CanonicalOrder,
    buyer_cash_account: str,
    seller_cash_account: str,
    buyer_position_account: str,
    seller_position_account: str,
    tx_id: str,
) -> Ok[Transaction] | Err[ValidationError]:
```

**Pattern:** Identical to `create_premium_transaction` in `options.py` (line 35-113).

**Conservation:** sigma(currency) = 0 AND sigma(swaption_unit) = 0.

#### 2.4.2 Exercise: `create_swaption_exercise_transaction`

On exercise of a physically-settled swaption, the swaption position closes. The IRS creation is a separate operation using existing Phase 3 functions.

**Moves:**
```
Move 1: Swaption position (quantity) buyer_position -> seller_position
```

**Signature:**
```python
def create_swaption_exercise_transaction(
    instrument_id: str,
    buyer_position_account: str,
    seller_position_account: str,
    quantity: Decimal,
    contract_unit: str,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
```

**Pattern:** Identical to `create_expiry_transaction` in `options.py` (line 279-328), but semantically different: this is exercise, not expiry.

**Conservation:** sigma(swaption_unit) returns to 0.

#### 2.4.3 IRS Parameter Derivation: `derive_irs_params_from_exercise`

Pure function that extracts IRS parameters from a swaption. This is NOT a transaction function -- it produces the parameters needed to call Phase 3 IRS functions.

**Signature:**
```python
@final
@dataclass(frozen=True, slots=True)
class ExercisedIRSParams:
    """Parameters for the IRS created by swaption exercise."""
    fixed_rate: Decimal
    float_index: str
    start_date: date
    end_date: date
    notional: Decimal
    day_count: DayCountConvention
    payment_frequency: PaymentFrequency
    currency: str
    payer_is_buyer: bool     # True for payer swaption

def derive_irs_params_from_exercise(
    detail: SwaptionDetail,
    exercise_date: date,
) -> Ok[ExercisedIRSParams] | Err[str]:
    """Derive IRS parameters from a swaption upon exercise.

    fixed_rate = swaption strike rate
    start_date = exercise_date (or next business day)
    end_date = start_date + underlying_tenor_months
    payer_is_buyer = True if swaption_type == PAYER

    The caller uses these params to:
    1. Call generate_fixed_leg_schedule() from irs.py
    2. Call generate_float_leg_schedule() from irs.py
    3. Book IRS cashflows via create_irs_cashflow_transaction() from irs.py
    """
```

**Linkage convention:** The swaption exercise tx_id and the IRS booking tx_id share a prefix:
- Swaption close: `SWAPTION-EX-{instrument_id}-{ts}`
- IRS open: `SWAPTION-EX-IRS-{instrument_id}-{ts}`

This provides complete audit trail from swaption to resulting IRS.

#### 2.4.4 Cash-Settled Exercise: `create_swaption_cash_exercise_transaction`

For cash-settled swaptions, no IRS is created. The intrinsic value is exchanged as cash.

**Moves:**
```
Move 1: Cash (settlement_amount) seller_cash -> buyer_cash  (if swaption is ITM)
Move 2: Swaption position (quantity) buyer_position -> seller_position
```

**Signature:**
```python
def create_swaption_cash_exercise_transaction(
    instrument_id: str,
    buyer_cash_account: str,
    seller_cash_account: str,
    buyer_position_account: str,
    seller_position_account: str,
    settlement_amount: Decimal,
    quantity: Decimal,
    contract_unit: str,
    currency: str,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
```

**Pattern:** Identical to `create_cash_settlement_exercise_transaction` in `options.py` (line 190-276).

**Conservation:** sigma(currency) = 0 AND sigma(swaption_unit) = 0.

#### 2.4.5 Expiry (Unexercised): `create_swaption_expiry_transaction`

If the swaption expires unexercised:

**Moves:**
```
Move 1: Swaption position (quantity) buyer_position -> seller_position
```

No cash. Seller keeps the premium received at inception.

**Signature:**
```python
def create_swaption_expiry_transaction(
    instrument_id: str,
    buyer_position_account: str,
    seller_position_account: str,
    quantity: Decimal,
    contract_unit: str,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
```

**Pattern:** Identical to `create_expiry_transaction` in `options.py`.

**Conservation:** sigma(swaption_unit) returns to 0.

### 2.5 Swaption Instrument Types

#### New detail type in `attestor/instrument/derivative_types.py`:

```python
class SwaptionType(Enum):
    PAYER = "PAYER"
    RECEIVER = "RECEIVER"

@final
@dataclass(frozen=True, slots=True)
class SwaptionDetail:
    """European swaption detail on a CanonicalOrder."""
    swaption_type: SwaptionType
    strike_rate: PositiveDecimal
    expiry_date: date
    underlying_tenor_months: int
    underlying_float_index: NonEmptyStr
    underlying_day_count: DayCountConvention
    underlying_payment_frequency: PaymentFrequency
    settlement_type: SettlementType
    notional: PositiveDecimal

    @staticmethod
    def create(...) -> Ok[SwaptionDetail] | Err[str]:
        # Validates: underlying_tenor_months > 0, expiry_date, all refined types
        ...
```

### 2.6 Swaption Lifecycle

Swaption transition table:

```python
SWAPTION_TRANSITIONS: TransitionTable = frozenset({
    (PositionStatusEnum.PROPOSED, PositionStatusEnum.FORMED),
    (PositionStatusEnum.PROPOSED, PositionStatusEnum.CANCELLED),
    (PositionStatusEnum.FORMED, PositionStatusEnum.SETTLED),
    (PositionStatusEnum.FORMED, PositionStatusEnum.CANCELLED),
    (PositionStatusEnum.SETTLED, PositionStatusEnum.CLOSED),
})
```

### 2.7 Tests: `tests/test_swaption.py`

| Test | What it verifies |
|------|-----------------|
| `test_swaption_premium_two_moves` | Cash + position Moves |
| `test_swaption_premium_conservation_cash` | sigma(currency) = 0 |
| `test_swaption_premium_conservation_position` | sigma(swaption_unit) = 0 |
| `test_swaption_exercise_closes_position` | Single position Move |
| `test_swaption_exercise_conservation` | sigma(swaption_unit) = 0 |
| `test_derive_irs_params_payer` | fixed_rate = strike, payer_is_buyer = True |
| `test_derive_irs_params_receiver` | fixed_rate = strike, payer_is_buyer = False |
| `test_derive_irs_params_start_end_dates` | start = exercise_date, end = start + tenor |
| `test_swaption_cash_exercise_two_moves` | Cash + position close |
| `test_swaption_cash_exercise_conservation` | sigma(currency) = 0, sigma(unit) = 0 |
| `test_swaption_expiry_no_cash` | Position close only |
| `test_swaption_expiry_conservation` | sigma(swaption_unit) = 0 |
| `test_swaption_exercise_then_irs_lifecycle` | Full integration: exercise -> IRS -> cashflows -> maturity |
| `test_swaption_exercise_irs_passes_phase3_invariants` | IRS from exercise satisfies all CL-F4/F5 |
| `test_swaption_full_lifecycle_exercise_path` | Premium -> exercise -> IRS -> maturity |
| `test_swaption_full_lifecycle_expiry_path` | Premium -> expiry |
| `test_swaption_invalid_exercise_after_expiry` | Err returned |
| `test_swaption_invalid_empty_accounts` | Err returned |
| `test_hypothesis_swaption_conservation` | 200 random examples |

**Expected tests: ~25**

---

## 3. Collateral Management

### 3.1 Collateral Financial Model (First Principles)

Collateral management is the discipline of mitigating counterparty credit exposure by requiring the posting of assets against open derivative positions. The fundamental constraint:

**Collateral transfers preserve value.** Posting collateral does not create or destroy assets -- it moves them from a trading account to a segregated collateral account. The accounting equation is preserved at every step.

### 3.2 Collateral Account Structure

| Account | AccountType | Purpose |
|---------|------------|---------|
| `party_a_cash` | `CASH` | Party A's trading cash |
| `party_a_securities` | `SECURITIES` | Party A's trading securities |
| `party_a_collateral_cash` | `COLLATERAL` | Party A's pledged cash collateral |
| `party_a_collateral_sec` | `COLLATERAL` | Party A's pledged securities collateral |

**Segregation principle:** Assets in COLLATERAL accounts cannot be used for trading. They are pledged to the counterparty as credit protection. The `AccountType.COLLATERAL` enum value (already present in `transactions.py` line 71) enforces this conceptual separation.

### 3.3 Collateral Types and Haircuts

```python
class CollateralType(Enum):
    CASH = "CASH"
    GOVERNMENT_BOND = "GOVERNMENT_BOND"
    CORPORATE_BOND = "CORPORATE_BOND"
    EQUITY = "EQUITY"
    LETTER_OF_CREDIT = "LETTER_OF_CREDIT"

@final
@dataclass(frozen=True, slots=True)
class HaircutSchedule:
    """Haircut percentages by collateral type. Immutable, attested."""
    haircuts: FrozenMap[str, Decimal]   # CollateralType.value -> haircut in [0, 1)

    @staticmethod
    def create(
        haircuts: dict[str, Decimal],
    ) -> Ok[HaircutSchedule] | Err[str]:
        """Validate all haircuts are in [0, 1). Reject >= 1 or < 0."""
        ...

@final
@dataclass(frozen=True, slots=True)
class CollateralItem:
    """A single piece of collateral with its valuation."""
    collateral_type: CollateralType
    instrument_id: NonEmptyStr
    quantity: PositiveDecimal
    market_value: PositiveDecimal        # per unit, from Oracle attestation
    haircut: Decimal                     # from HaircutSchedule, in [0, 1)
    currency: NonEmptyStr

    @property
    def post_haircut_value(self) -> Decimal:
        """Post-haircut collateral value."""
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            return self.quantity.value * self.market_value.value * (Decimal("1") - self.haircut)
```

### 3.4 Margin Call Calculation

The margin call is a pure function -- it produces a data record, not a Transaction.

```python
@final
@dataclass(frozen=True, slots=True)
class MarginCall:
    """Computed margin call record."""
    call_id: NonEmptyStr
    agreement_id: NonEmptyStr
    calling_party: NonEmptyStr
    receiving_party: NonEmptyStr
    required_margin: Decimal
    current_collateral_value: Decimal
    call_amount: Decimal                 # > 0 means deliver, < 0 means return
    currency: NonEmptyStr
    valuation_date: date
    delivery_date: date
    timestamp: UtcDatetime

def compute_margin_call(
    agreement_id: str,
    exposure: Decimal,
    threshold: Decimal,
    minimum_transfer_amount: Decimal,
    rounding: Decimal,
    current_collateral: Decimal,
    currency: str,
    valuation_date: date,
    timestamp: UtcDatetime,
) -> Ok[MarginCall] | Err[str]:
    """Compute margin call amount.

    required_margin = max(0, exposure - threshold)
    raw_call = required_margin - current_collateral
    if abs(raw_call) < minimum_transfer_amount: call_amount = 0
    else: call_amount = round_up(raw_call, rounding)

    Positive call_amount = delivery required.
    Negative call_amount = excess to return.
    """
```

### 3.5 Collateral Transaction Functions

All functions live in new file `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/collateral.py`.

#### 3.5.1 Delivery: `create_collateral_delivery_transaction`

**Moves:**
```
Move 1: Asset (quantity) from trading_account -> collateral_account
```

Single Move. Works for both cash and securities.

**Signature:**
```python
def create_collateral_delivery_transaction(
    agreement_id: str,
    call_id: str,
    delivering_party_account: str,
    collateral_account: str,
    unit: str,
    quantity: Decimal,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
```

**Conservation:** sigma(unit) = 0. Assets move between accounts; nothing created or destroyed.

#### 3.5.2 Return: `create_collateral_return_transaction`

Exact reverse of delivery.

**Moves:**
```
Move 1: Asset (quantity) from collateral_account -> trading_account
```

**Signature:**
```python
def create_collateral_return_transaction(
    agreement_id: str,
    collateral_account: str,
    receiving_party_account: str,
    unit: str,
    quantity: Decimal,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
```

**Conservation:** sigma(unit) = 0.

#### 3.5.3 Substitution: `create_collateral_substitution_transaction`

**CRITICAL: Must be atomic.** A single Transaction with two Moves. No intermediate state where collateral is insufficient.

**Moves:**
```
Move 1: Return old collateral -- old_collateral_account -> old_return_account (old_unit, old_quantity)
Move 2: Deliver new collateral -- new_delivery_account -> new_collateral_account (new_unit, new_quantity)
```

**Signature:**
```python
def create_collateral_substitution_transaction(
    agreement_id: str,
    # Return leg
    old_collateral_account: str,
    old_return_account: str,
    old_unit: str,
    old_quantity: Decimal,
    # Delivery leg
    new_delivery_account: str,
    new_collateral_account: str,
    new_unit: str,
    new_quantity: Decimal,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
```

**Conservation:** sigma(old_unit) = 0 AND sigma(new_unit) = 0. Each unit is conserved independently. If old_unit == new_unit, the net sigma is still 0 but amounts may differ (e.g., replacing 100 units of bond A with 105 units of bond A due to haircut differences).

**Business rule (enforced by caller, not by the ledger):**
```
post_haircut_value(new_collateral) >= post_haircut_value(old_collateral)
```

### 3.6 Tests: `tests/test_collateral.py`

| Test | What it verifies |
|------|-----------------|
| `test_haircut_schedule_valid` | All haircuts in [0, 1) |
| `test_haircut_schedule_reject_gte_1` | Haircut >= 1 rejected |
| `test_haircut_schedule_reject_negative` | Haircut < 0 rejected |
| `test_collateral_item_post_haircut_value` | qty * price * (1 - haircut) |
| `test_margin_call_normal` | exposure > threshold + current |
| `test_margin_call_sufficient_collateral` | call_amount = 0 |
| `test_margin_call_below_mta` | call_amount zeroed |
| `test_margin_call_rounding` | round_up applied |
| `test_margin_call_return_excess` | negative call_amount |
| `test_delivery_single_move` | One Move, correct accounts |
| `test_delivery_conservation` | sigma(unit) = 0 |
| `test_return_single_move` | One Move, reversed |
| `test_return_conservation` | sigma(unit) = 0 |
| `test_substitution_two_moves_atomic` | Single Transaction, 2 Moves |
| `test_substitution_conservation_old_unit` | sigma(old_unit) = 0 |
| `test_substitution_conservation_new_unit` | sigma(new_unit) = 0 |
| `test_substitution_same_unit` | old_unit == new_unit, different quantities |
| `test_delivery_invalid_empty_accounts` | Err returned |
| `test_delivery_invalid_zero_quantity` | Err returned |
| `test_substitution_invalid_same_source_dest` | Err returned |
| `test_hypothesis_collateral_delivery_conservation` | 200 random examples |
| `test_hypothesis_collateral_substitution_conservation` | 200 random examples |

**Expected tests: ~30**

---

## 4. Regulatory Reporting

### 4.1 CDS EMIR Reporting

EMIR (European Market Infrastructure Regulation) requires CDS trades to be reported to a trade repository. The report is a **pure projection** from `CanonicalOrder` with `CDSDetail` -- INV-R01 holds.

#### New report fields in `attestor/reporting/emir.py`:

```python
@final
@dataclass(frozen=True, slots=True)
class EMIRCDSFields:
    """CDS-specific EMIR reporting fields (ESMA RTS)."""
    reference_entity_name: str         # Field 2.37
    reference_entity_lei: str          # Field 2.38
    seniority: str                     # Field 2.39 -- ISDA code (SNRFOR, SUBLT2, etc.)
    restructuring_type: str            # Field 2.40 -- ISDA code (XR, CR, MR, MM)
    notional: Decimal                  # Field 2.20
    spread_bps: Decimal                # Field 2.41 -- spread in basis points
    effective_date: date               # Field 2.42
    maturity_date: date                # Field 2.43
    day_count: str                     # Field 2.44
    payment_frequency: str             # Field 2.45
```

**Field mapping (projection, not transformation):**

| EMIR Field | Source | Notes |
|------------|--------|-------|
| 2.37 Reference entity | `detail.reference_entity.value` | Direct projection |
| 2.38 Reference entity LEI | `detail.reference_entity_lei.value` | Direct projection |
| 2.39 Seniority | `detail.seniority.value` | Already ISDA code |
| 2.40 Restructuring type | `detail.restructuring_type.value` | Already ISDA code |
| 2.20 Notional | `detail.notional.value` | Direct projection |
| 2.41 Spread | `detail.spread.value * Decimal("10000")` | Convert decimal to basis points |
| 2.42 Effective date | `detail.effective_date` | Direct projection |
| 2.43 Maturity date | `detail.maturity_date` | Direct projection |
| 2.44 Day count | `detail.day_count.value` | Direct projection |
| 2.45 Payment frequency | `detail.payment_frequency.value` | Direct projection |

**NOTE on spread conversion:** The spread is stored internally as a decimal (e.g., `0.01` for 100 bps) but EMIR requires basis points (e.g., `100`). The conversion `spread * 10000` is a unit conversion (like Celsius to Fahrenheit), not a transformation. It is acceptable under INV-R01.

Extend `project_emir_report` with CDSDetail match case:

```python
# In project_emir_report:
case CDSDetail() as cd:
    # Map CDSDetail -> EMIRCDSFields
    ...
```

### 4.2 CDS Dodd-Frank Reporting

Dodd-Frank (CFTC Part 45) requires similar but not identical fields.

#### New file: `attestor/reporting/dodd_frank.py`

```python
@final
@dataclass(frozen=True, slots=True)
class DoddFrankCDSFields:
    """CDS-specific fields for CFTC Part 45 reporting."""
    reference_entity: str                # Appendix 1 Field 34
    seniority: str                       # Field 35
    restructuring_type: str              # Field 36
    notional_amount: Decimal             # Field 20
    price_notation: Decimal              # Field 22 (spread in bps)
    effective_date: date                 # Field 25
    end_date: date                       # Field 26
    day_count: str                       # Field 27
    payment_frequency: str               # Field 28
    cds_index_name: str | None           # Field 37 (None for single-name)

@final
@dataclass(frozen=True, slots=True)
class DoddFrankCDSReport:
    """Full Dodd-Frank CDS report."""
    usi: NonEmptyStr                     # Unique Swap Identifier
    reporting_counterparty_lei: LEI
    other_counterparty_lei: LEI
    instrument_id: NonEmptyStr
    direction: OrderSide
    cds_fields: DoddFrankCDSFields
    trade_date: date
    report_timestamp: UtcDatetime
    attestation_refs: tuple[str, ...]

def project_dodd_frank_cds_report(
    order: CanonicalOrder,
    trade_attestation_id: str,
) -> Ok[Attestation[DoddFrankCDSReport]] | Err[str]:
    """INV-R01: pure projection for Dodd-Frank CDS reporting."""
```

### 4.3 Swaption EMIR Reporting

#### New report fields:

```python
@final
@dataclass(frozen=True, slots=True)
class EMIRSwaptionFields:
    """Swaption-specific EMIR reporting fields."""
    swaption_type: str                   # "PAYER" or "RECEIVER"
    strike_rate: Decimal
    expiry_date: date
    underlying_tenor_months: int
    underlying_float_index: str
    settlement_type: str
    notional: Decimal
    premium: Decimal                     # upfront premium from order.price
```

Extend `project_emir_report` and `project_mifid2_report` with SwaptionDetail match case.

### 4.4 Swaption MiFID II Reporting

#### New report fields in `attestor/reporting/mifid2.py`:

```python
@final
@dataclass(frozen=True, slots=True)
class CDSReportFields:
    """CDS-specific fields for MiFID II."""
    reference_entity: str
    seniority: str
    restructuring_type: str
    spread: Decimal
    notional: Decimal

@final
@dataclass(frozen=True, slots=True)
class SwaptionReportFields:
    """Swaption-specific fields for MiFID II."""
    swaption_type: str
    strike_rate: Decimal
    expiry_date: date
    underlying_tenor_months: int
```

Updated InstrumentReportFields union:

```python
type InstrumentReportFields = (
    OptionReportFields | FuturesReportFields
    | FXReportFields | IRSwapReportFields
    | CDSReportFields | SwaptionReportFields | None
)
```

### 4.5 Collateral Reporting

EMIR Article 9 requires reporting of collateral posted under derivative agreements.

#### New file: `attestor/reporting/collateral_report.py`

```python
@final
@dataclass(frozen=True, slots=True)
class CollateralReport:
    """EMIR Article 9 collateral report."""
    reporting_counterparty_lei: str
    other_counterparty_lei: str
    agreement_id: str
    collateral_portfolio: bool           # True if portfolio margining (always False in Phase 4)
    initial_margin_posted: Decimal
    initial_margin_received: Decimal
    variation_margin_posted: Decimal
    variation_margin_received: Decimal
    excess_collateral_posted: Decimal
    excess_collateral_received: Decimal
    currency: str
    valuation_date: date
    report_timestamp: UtcDatetime

def project_collateral_report(
    agreement_id: str,
    reporting_lei: str,
    other_lei: str,
    posted_items: tuple[CollateralItem, ...],
    received_items: tuple[CollateralItem, ...],
    currency: str,
    valuation_date: date,
    timestamp: UtcDatetime,
) -> Ok[CollateralReport] | Err[str]:
    """Projection from collateral positions to EMIR collateral report.

    All values are aggregations of post-haircut collateral values.
    INV-R01: no new values computed, only aggregations of existing attested values.
    """
```

### 4.6 Model Governance Reporting

Vol surfaces and credit curves are calibrated model outputs. Regulatory requirements (SR 11-7, SS1/23) require governance reporting.

#### New file: `attestor/reporting/model_governance.py`

```python
@final
@dataclass(frozen=True, slots=True)
class ModelGovernanceReport:
    """Model governance report for calibrated market data."""
    model_class: str                     # "SVI", "SSVI", "PIECEWISE_HAZARD"
    model_config_ref: str
    calibration_timestamp: UtcDatetime
    underlying: str
    fit_quality_metrics: FrozenMap[str, Decimal]
    arbitrage_check_results: tuple[str, ...]  # attestation IDs of arb checks
    provenance_chain: tuple[str, ...]
    report_timestamp: UtcDatetime

def project_model_governance_report(
    model_class: str,
    model_config_ref: str,
    calibration_timestamp: UtcDatetime,
    underlying: str,
    fit_quality: FrozenMap[str, Decimal],
    arb_check_refs: tuple[str, ...],
    provenance: tuple[str, ...],
) -> Ok[ModelGovernanceReport] | Err[str]:
    """Projection from calibration attestations to model governance report."""
```

### 4.7 Tests: `tests/test_reporting_phase4.py`

| Test | What it verifies |
|------|-----------------|
| `test_emir_cds_all_fields_mapped` | CDSDetail -> EMIRCDSFields complete |
| `test_emir_cds_spread_to_bps` | spread * 10000 = bps |
| `test_emir_cds_seniority_code` | ISDA seniority code preserved |
| `test_emir_swaption_fields_mapped` | SwaptionDetail -> EMIRSwaptionFields |
| `test_dodd_frank_cds_all_fields` | CFTC fields complete |
| `test_dodd_frank_cds_single_name_no_index` | cds_index_name = None |
| `test_mifid2_cds_report_fields` | CDSReportFields populated |
| `test_mifid2_swaption_report_fields` | SwaptionReportFields populated |
| `test_collateral_report_aggregation` | sum of post-haircut values correct |
| `test_collateral_report_no_portfolio_margining` | collateral_portfolio = False |
| `test_model_governance_report_complete` | provenance chain populated |
| `test_model_governance_report_fit_quality` | fit_quality metrics present |
| `test_all_reports_inv_r01` | No new values computed in any report |
| `test_emir_report_attestation_provenance` | attestation_refs populated |

**Expected tests: ~25**

---

## 5. Infrastructure

### 5.1 Kafka Topic Specifications

Four new topics as specified in MASTER_PLAN Phase 4 scope.

#### `attestor.oracle.vol_surfaces`

| Property | Value | Rationale |
|----------|-------|-----------|
| Partitions | 6 | One per major underlying asset class; hash on underlying |
| Replication factor | 3 | Standard HA for production |
| Retention | Infinite (`-1`) | Attested calibration data; full replay capability |
| Cleanup policy | `delete` | No compaction (immutable attestations) |
| Min ISR | 2 | Write quorum |
| Key | `{underlying}-{as_of_date}` | Efficient lookup by underlying + date |
| Value schema | `BitemporalEnvelope[Attestation[VolSurface]]` | Avro-registered |

#### `attestor.oracle.credit_curves`

| Property | Value | Rationale |
|----------|-------|-----------|
| Partitions | 3 | Lower cardinality than equities; hash on reference_entity |
| Replication factor | 3 | Standard HA |
| Retention | Infinite (`-1`) | Attested data |
| Cleanup policy | `delete` | No compaction |
| Min ISR | 2 | Write quorum |
| Key | `{reference_entity}-{as_of_date}` | Entity + date lookup |
| Value schema | `BitemporalEnvelope[Attestation[CreditCurve]]` | Avro-registered |

#### `attestor.ledger.collateral`

| Property | Value | Rationale |
|----------|-------|-----------|
| Partitions | 6 | Hash on agreement_id; multiple CSAs active |
| Replication factor | 3 | Standard HA |
| Retention | Infinite (`-1`) | Audit trail (regulatory requirement) |
| Cleanup policy | `delete` | No compaction |
| Min ISR | 2 | Write quorum |
| Key | `{agreement_id}-{event_id}` | Events scoped to agreement |
| Value schema | `BitemporalEnvelope[CollateralEvent]` | Avro-registered |

#### `attestor.lifecycle.credit_events`

| Property | Value | Rationale |
|----------|-------|-----------|
| Partitions | 3 | Low volume (credit events are rare; 3 sufficient) |
| Replication factor | 3 | Standard HA |
| Retention | Infinite (`-1`) | Regulatory requirement; must be reproducible |
| Cleanup policy | `delete` | No compaction |
| Min ISR | 2 | Write quorum |
| Key | `{reference_entity}-{determination_date}` | Entity + date |
| Value schema | `BitemporalEnvelope[CreditEvent]` | Avro-registered |

### 5.2 Topic Configuration Code

Modify `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/infra/config.py`:

```python
TOPIC_VOL_SURFACES = "attestor.oracle.vol_surfaces"
TOPIC_CREDIT_CURVES = "attestor.oracle.credit_curves"
TOPIC_COLLATERAL = "attestor.ledger.collateral"
TOPIC_CREDIT_EVENTS = "attestor.lifecycle.credit_events"

PHASE4_TOPICS = frozenset({
    TOPIC_VOL_SURFACES, TOPIC_CREDIT_CURVES,
    TOPIC_COLLATERAL, TOPIC_CREDIT_EVENTS,
})

def phase4_topic_configs() -> tuple[TopicConfig, ...]:
    return (
        TopicConfig(name=TOPIC_VOL_SURFACES, partitions=6, replication_factor=3,
                    retention_ms=-1, cleanup_policy="delete", min_insync_replicas=2),
        TopicConfig(name=TOPIC_CREDIT_CURVES, partitions=3, replication_factor=3,
                    retention_ms=-1, cleanup_policy="delete", min_insync_replicas=2),
        TopicConfig(name=TOPIC_COLLATERAL, partitions=6, replication_factor=3,
                    retention_ms=-1, cleanup_policy="delete", min_insync_replicas=2),
        TopicConfig(name=TOPIC_CREDIT_EVENTS, partitions=3, replication_factor=3,
                    retention_ms=-1, cleanup_policy="delete", min_insync_replicas=2),
    )
```

### 5.3 Postgres Table DDL

All tables follow the existing pattern: bitemporal columns (`valid_time`, `system_time`), prevent_mutation triggers, explicit column types (no JSON blobs for core fields).

#### `sql/018_vol_surfaces.sql`

```sql
CREATE TABLE IF NOT EXISTS attestor.vol_surfaces (
    surface_id          TEXT            PRIMARY KEY,
    underlying          TEXT            NOT NULL,
    as_of               DATE            NOT NULL,
    strikes             DECIMAL[]       NOT NULL,
    expiries            DECIMAL[]       NOT NULL,
    vols                DECIMAL[][]     NOT NULL,
    svi_params          JSONB           NOT NULL DEFAULT '[]',
    model_config_ref    TEXT            NOT NULL,
    arb_checks          JSONB           NOT NULL DEFAULT '{}',
    confidence_payload  JSONB           NOT NULL DEFAULT '{}',
    valid_time          TIMESTAMPTZ     NOT NULL,
    system_time         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    CONSTRAINT vol_surfaces_strikes_nonempty CHECK (array_length(strikes, 1) > 0),
    CONSTRAINT vol_surfaces_expiries_nonempty CHECK (array_length(expiries, 1) > 0)
);

CREATE INDEX IF NOT EXISTS idx_vol_surfaces_underlying_as_of
    ON attestor.vol_surfaces (underlying, as_of);

CREATE TRIGGER prevent_mutation_vol_surfaces
    BEFORE UPDATE OR DELETE ON attestor.vol_surfaces
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();
```

#### `sql/019_credit_curves.sql`

```sql
CREATE TABLE IF NOT EXISTS attestor.credit_curves (
    curve_id            TEXT            PRIMARY KEY,
    reference_entity    TEXT            NOT NULL,
    as_of               DATE            NOT NULL,
    tenors              DECIMAL[]       NOT NULL,
    survival_probs      DECIMAL[]       NOT NULL,
    hazard_rates        DECIMAL[]       NOT NULL DEFAULT '{}',
    model_config_ref    TEXT            NOT NULL,
    arb_checks          JSONB           NOT NULL DEFAULT '{}',
    confidence_payload  JSONB           NOT NULL DEFAULT '{}',
    valid_time          TIMESTAMPTZ     NOT NULL,
    system_time         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    CONSTRAINT credit_curves_tenors_nonempty CHECK (array_length(tenors, 1) > 0),
    CONSTRAINT credit_curves_matching_lengths CHECK (
        array_length(tenors, 1) = array_length(survival_probs, 1)
    )
);

CREATE INDEX IF NOT EXISTS idx_credit_curves_entity_as_of
    ON attestor.credit_curves (reference_entity, as_of);

CREATE TRIGGER prevent_mutation_credit_curves
    BEFORE UPDATE OR DELETE ON attestor.credit_curves
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();
```

#### `sql/020_collateral_balances.sql`

```sql
CREATE TABLE IF NOT EXISTS attestor.collateral_balances (
    balance_id          TEXT            PRIMARY KEY,
    agreement_id        TEXT            NOT NULL,
    account_id          TEXT            NOT NULL,
    collateral_type     TEXT            NOT NULL CHECK (
        collateral_type IN (
            'CASH', 'GOVERNMENT_BOND', 'CORPORATE_BOND',
            'EQUITY', 'LETTER_OF_CREDIT'
        )
    ),
    instrument_id       TEXT            NOT NULL,
    quantity            DECIMAL         NOT NULL CHECK (quantity >= 0),
    market_value        DECIMAL         NOT NULL CHECK (market_value >= 0),
    haircut             DECIMAL         NOT NULL CHECK (haircut >= 0 AND haircut < 1),
    collateral_value    DECIMAL         NOT NULL,
    currency            TEXT            NOT NULL,
    valid_time          TIMESTAMPTZ     NOT NULL,
    system_time         TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_collateral_balances_agreement
    ON attestor.collateral_balances (agreement_id, valid_time);

-- Collateral balances use bitemporal versioning (new row per state change).
-- DELETE is still prevented for audit trail integrity.
CREATE TRIGGER prevent_delete_collateral_balances
    BEFORE DELETE ON attestor.collateral_balances
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();
```

#### `sql/021_credit_events.sql`

```sql
CREATE TABLE IF NOT EXISTS attestor.credit_events (
    event_id            TEXT            PRIMARY KEY,
    reference_entity    TEXT            NOT NULL,
    reference_entity_lei TEXT           NOT NULL,
    event_type          TEXT            NOT NULL CHECK (
        event_type IN (
            'BANKRUPTCY', 'FAILURE_TO_PAY', 'RESTRUCTURING',
            'OBLIGATION_ACCELERATION', 'OBLIGATION_DEFAULT',
            'REPUDIATION_MORATORIUM'
        )
    ),
    determination_date  DATE            NOT NULL,
    auction_date        DATE,
    auction_price       DECIMAL         CHECK (
        auction_price IS NULL OR (auction_price >= 0 AND auction_price <= 1)
    ),
    recovery_rate       DECIMAL         CHECK (
        recovery_rate IS NULL OR (recovery_rate >= 0 AND recovery_rate < 1)
    ),
    settlement_date     DATE,
    status              TEXT            NOT NULL CHECK (
        status IN ('DECLARED', 'AUCTION_SCHEDULED', 'AUCTION_COMPLETE', 'SETTLED')
    ),
    attestation_ref     TEXT,
    valid_time          TIMESTAMPTZ     NOT NULL,
    system_time         TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_credit_events_entity
    ON attestor.credit_events (reference_entity, determination_date);

CREATE TRIGGER prevent_mutation_credit_events
    BEFORE UPDATE OR DELETE ON attestor.credit_events
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();
```

### 5.4 Tests: `tests/test_infra_phase4.py`

| Test | What it verifies |
|------|-----------------|
| `test_phase4_topic_constants` | All 4 defined, no duplicates |
| `test_phase4_topics_frozenset` | 4 elements |
| `test_phase4_topic_configs_count` | 4 configs returned |
| `test_phase4_topic_configs_retention_infinite` | All retention = -1 |
| `test_phase4_topic_configs_cleanup_delete` | All cleanup = "delete" |
| `test_phase4_topic_configs_min_isr` | All min_insync_replicas = 2 |
| `test_vol_surfaces_sql_constraints` | Non-empty arrays |
| `test_credit_curves_sql_matching_lengths` | tenors.length = survival_probs.length |
| `test_collateral_balances_sql_haircut_bounds` | haircut in [0, 1) |
| `test_credit_events_sql_status_enum` | Valid status values only |
| `test_credit_events_sql_auction_price_bounds` | [0, 1] or NULL |
| `test_all_tables_prevent_mutation` | Triggers exist |

**Expected tests: ~14**

---

## 6. Conservation Laws

### 6.1 Existing Laws (Must Continue to Hold)

All nine CL-A1 through CL-A9 from MASTER_PLAN Section 5.2 must hold for all Phase 4 transactions. In particular:

- **CL-A1 (Unit Conservation):** sigma(U) unchanged for every `execute()`. This means for every Phase 4 Transaction, the sum of all Move quantities entering accounts equals the sum leaving, per unit.
- **CL-A2 (Double-Entry):** Every Transaction's Move tuples sum to zero.
- **CL-A9 (P&L Zero-Sum):** buyer_pnl + seller_pnl = 0 for all bilateral trades.

### 6.2 New Phase 4 Conservation Laws

#### CL-C1: CDS Premium Bilateral Conservation

```
For every CDS premium transaction:
    sigma(currency) = 0
    buyer_cash_outflow = seller_cash_inflow   (exact)
```

**Formal:** Let `P_j = notional * spread * dcf(T_{j-1}, T_j, ACT_360)`. Then `Move.quantity = P_j` and `Move.source = buyer_cash, Move.destination = seller_cash`. The net cash across all accounts is zero.

**Test:** Hypothesis property-based, 200 random (notional, spread, period_start, period_end) tuples.

#### CL-C2: CDS Credit Event Bilateral Conservation

```
For every CDS credit event settlement transaction:
    sigma(currency) = 0
    sigma(contract_unit) = 0   (position fully closed)
```

**Formal:** The Transaction contains up to 3 Moves:
1. protection_payment: seller -> buyer, amount = `N * (1 - R)`
2. accrued_premium: buyer -> seller, amount = `N * s * dcf(...)`
3. position_close: buyer -> seller, contract_unit, quantity = N

Cash conservation: `N * (1 - R)` flows one way, `N * s * dcf` flows the other. Net cash movement is `N * (1 - R) - N * s * dcf`. This is NOT zero (it is the net settlement), but sigma(currency) IS zero because each Move individually transfers between two accounts -- no cash is created.

**Test:** Hypothesis property-based, 200 random (notional, recovery_rate, spread, dates) tuples.

#### CL-C3: CDS Full Lifecycle Zero-Sum

```
Over a CDS from trade to maturity or credit event:
    buyer_total_cashflow + seller_total_cashflow = 0    (exact)
```

**Formal:** Let buyer total = -sum(premiums paid) + protection_received - accrued_at_event. Let seller total = +sum(premiums received) - protection_paid + accrued_at_event. Then buyer_total + seller_total = 0 because every cash Move has a source and destination.

**Test:** Full lifecycle integration test with exact Decimal verification.

#### CL-C4: CDS Settlement Identity

```
protection_payment = notional * (1 - recovery_rate)
protection_payment + notional * recovery_rate = notional    (exact)
```

This is the fundamental credit identity. It must hold to the penny in Decimal arithmetic.

**Test:** Exact Decimal assertion for multiple recovery rates including edge cases (0, 0.4, 0.95).

#### CL-C5: Swaption Premium Conservation

```
For every swaption premium transaction:
    sigma(currency) = 0
    sigma(swaption_contract_unit) = 0
```

**Test:** Hypothesis property-based, 200 random examples.

#### CL-C6: Swaption Exercise Produces Valid IRS

```
After swaption exercise:
    sigma(swaption_contract_unit) = 0   (swaption closed)
    The resulting IRS passes all Phase 3 conservation laws:
        CL-F4: IRS cashflow conservation
        CL-F5: IRS full lifecycle conservation
```

**Test:** Integration test: exercise -> generate IRS schedules -> book cashflows -> verify conservation.

#### CL-C7: Swaption Full Lifecycle Zero-Sum

```
For swaption trade -> exercise -> IRS lifecycle -> IRS maturity:
    sigma(currency) = 0   at every step
    sigma(swaption_unit) = 0   after exercise
    sigma(irs_unit) = 0   after IRS maturity   (if applicable)
```

**Test:** Full lifecycle integration test.

#### CL-C8: Collateral Unit Conservation

```
For every collateral transaction (delivery, return, substitution):
    sigma(unit) = 0   for EVERY unit involved

For substitution:
    sigma(old_unit) = 0   AND   sigma(new_unit) = 0   independently
```

**Test:** Hypothesis property-based, 200 random collateral operations.

#### CL-C9: Collateral Substitution Value Preservation

```
For collateral substitution:
    post_haircut_value(new_collateral) >= post_haircut_value(old_collateral)
```

This is a business rule enforced by the caller (margin call computation), NOT by the Transaction itself. The ledger only enforces unit conservation (CL-C8).

**Test:** Business logic test in `compute_margin_call` / substitution validation.

### 6.3 Conservation Law Summary Table

| Law | Description | Symmetry | Test Type | CI Stage |
|-----|-------------|----------|-----------|----------|
| CL-C1 | CDS premium bilateral | Cash conservation | Hypothesis (200) | Pre-commit |
| CL-C2 | CDS credit event bilateral | Cash + position conservation | Hypothesis (200) | Pre-commit |
| CL-C3 | CDS lifecycle zero-sum | Bilateral symmetry | Integration | Pre-commit |
| CL-C4 | CDS settlement identity | Credit identity | Exact Decimal | Pre-commit |
| CL-C5 | Swaption premium bilateral | Cash + position conservation | Hypothesis (200) | Pre-commit |
| CL-C6 | Swaption exercise -> valid IRS | Product composition | Integration | Pre-commit |
| CL-C7 | Swaption full lifecycle | Bilateral symmetry | Integration | Pre-commit |
| CL-C8 | Collateral unit conservation | Asset conservation | Hypothesis (200) | Pre-commit |
| CL-C9 | Substitution value preservation | Business rule | Logic test | Pre-commit |

---

## 7. Build Order and Test Budget

### 7.1 Step-by-Step Build Order

| Step | Description | New/Modified Files | Tests |
|------|------------|-------------------|-------|
| 0 | Phase 3 cleanup prerequisites | Verify COLLATERAL AccountType, calendar T+1 | 0 |
| 1 | CDS + swaption instrument types | `instrument/credit_types.py` (new), `instrument/derivative_types.py` (extend) | ~30 |
| 2 | CDS + swaption lifecycle | `instrument/lifecycle.py` (extend) | ~15 |
| 3 | Gateway parsers for CDS + swaption | `gateway/parser.py` (extend) | ~20 |
| 4 | CDS ledger booking | `ledger/cds.py` (new) | ~35 |
| 5 | Swaption ledger booking | `ledger/swaption.py` (new) | ~25 |
| 6 | Collateral management | `ledger/collateral.py` (new) | ~30 |
| 7 | Oracle: credit curve types + bootstrap | `oracle/credit_curve.py` (new) or extend `calibration.py` | ~25 |
| 8 | Oracle: vol surface types + SVI/SSVI | `oracle/vol_surface.py` (new) or extend `calibration.py` | ~30 |
| 9 | Oracle: arbitrage gates (credit + vol) | `oracle/arbitrage_gates.py` (extend) | ~20 |
| 10 | Reporting: EMIR CDS + Dodd-Frank | `reporting/emir.py` (extend), `reporting/dodd_frank.py` (new) | ~15 |
| 11 | Reporting: swaption + collateral + model governance | `reporting/mifid2.py` (extend), `reporting/collateral_report.py` (new), `reporting/model_governance.py` (new) | ~10 |
| 12 | Pricing stub extension | `pricing/types.py` (extend), `pricing/protocols.py` (verify) | ~8 |
| 13 | Infrastructure (Kafka + Postgres) | `infra/config.py` (extend), 4 SQL files | ~14 |
| 14 | Invariant tests | `tests/test_invariants_phase4.py` (new) | ~30 |
| 15 | Integration tests | `tests/test_integration_phase4.py` (new) | ~50 |
| 16 | Re-exports and package init | Various `__init__.py` | ~0 |
| **Total** | | | **~357** |

### 7.2 Source Line Budget

| File | Est. lines | Notes |
|------|-----------|-------|
| `instrument/credit_types.py` (new) | ~120 | Enums: CreditEventType, Seniority, RestructuringType |
| `instrument/derivative_types.py` (extend) | +100 | CDSDetail, SwaptionDetail, SwaptionType |
| `instrument/types.py` (extend) | +60 | Payout union, factory functions |
| `instrument/lifecycle.py` (extend) | +50 | CreditEventPI, AuctionSettlementPI, transitions |
| `gateway/parser.py` (extend) | +100 | parse_cds_order, parse_swaption_order |
| `ledger/cds.py` (new) | ~300 | Trade, premium, credit event, maturity, schedule |
| `ledger/swaption.py` (new) | ~200 | Premium, exercise (physical + cash), expiry, IRS derivation |
| `ledger/collateral.py` (new) | ~350 | Types, margin call, delivery, return, substitution |
| `oracle/credit_curve.py` or extend `calibration.py` | +400 | CreditCurve, CDSQuote, bootstrap |
| `oracle/vol_surface.py` or extend `calibration.py` | +400 | SVISlice, SSVISurface, VolSurface |
| `oracle/arbitrage_gates.py` (extend) | +250 | AF-CR and AF-VS gates |
| `oracle/decimal_math.py` (new) | ~150 | exp_d, ln_d, sqrt_d, expm1_neg_d |
| `reporting/emir.py` (extend) | +60 | EMIRCDSFields, EMIRSwaptionFields |
| `reporting/mifid2.py` (extend) | +40 | CDSReportFields, SwaptionReportFields |
| `reporting/dodd_frank.py` (new) | ~150 | DoddFrankCDSReport, projection |
| `reporting/collateral_report.py` (new) | ~80 | CollateralReport, projection |
| `reporting/model_governance.py` (new) | ~80 | ModelGovernanceReport, projection |
| `pricing/types.py` (extend) | +15 | CDS/swaption stub fields |
| `infra/config.py` (extend) | +40 | 4 topics, phase4_topic_configs |
| SQL files (4 new) | ~150 | Postgres tables |
| **Total new source** | **~3145** | Under 5,000 line budget |

---

## 8. Integration Test Scenarios

### 8.1 CDS Full Lifecycle -- Credit Event Path (14 steps)

1. Parse CDS order -> `CanonicalOrder` with `CDSDetail`
2. Create CDS instrument with `CDSPayoutSpec`
3. Book CDS trade -> `create_cds_trade_transaction` -> single position Move
4. Generate premium schedule (quarterly, ACT/360, IMM dates) -> `CashflowSchedule`
5. Book first premium payment -> `create_cds_premium_transaction`
6. Book second premium payment
7. Credit event declared -> `CreditEventPI` published to `attestor.lifecycle.credit_events`
8. ISDA auction result: recovery_rate = 0.40
9. Book credit event settlement -> `create_cds_credit_event_transaction`
   - Protection = notional * 0.60 (seller -> buyer)
   - Accrued premium (buyer -> seller)
   - Position close (buyer -> seller)
10. **Verify CL-C4:** protection_payment = notional * (1 - 0.40) exactly
11. **Verify CL-C2:** sigma(currency) = 0, sigma(contract_unit) = 0
12. **Verify CL-C3:** buyer_total + seller_total = 0
13. Project EMIR CDS report -> all ESMA fields populated
14. Project Dodd-Frank CDS report -> all CFTC fields populated

### 8.2 CDS Full Lifecycle -- Maturity Path (10 steps)

1. Parse CDS order
2. Book CDS trade
3. Generate full premium schedule (20 quarters for 5Y CDS)
4. Book all 20 premium payments
5. No credit event occurs
6. Book CDS maturity -> `create_cds_maturity_transaction`
7. **Verify:** sigma(CDS contract unit) = 0
8. **Verify:** buyer paid total = sum(notional * spread * dcf_i) for all i
9. **Verify:** seller received exactly what buyer paid
10. **Verify CL-C3:** bilateral zero-sum

### 8.3 Swaption Lifecycle -- Physical Exercise Path (12 steps)

1. Parse swaption order -> `CanonicalOrder` with `SwaptionDetail`
2. Book swaption trade -> `create_swaption_premium_transaction`
3. Expiry date arrives, market rates moved, swaption is ITM
4. Exercise swaption -> `create_swaption_exercise_transaction`
5. Derive IRS params -> `derive_irs_params_from_exercise`
6. Generate IRS fixed leg schedule (Phase 3 `generate_fixed_leg_schedule`)
7. Generate IRS float leg schedule (Phase 3 `generate_float_leg_schedule`)
8. Apply SOFR fixings -> Phase 3 `apply_rate_fixing`
9. Book IRS cashflow exchanges -> Phase 3 `create_irs_cashflow_transaction`
10. IRS maturity
11. **Verify CL-C6:** IRS passes all Phase 3 conservation laws
12. **Verify CL-C7:** full lifecycle zero-sum (premium + IRS cashflows)

### 8.4 Swaption Lifecycle -- Expiry Path (5 steps)

1. Parse swaption order
2. Book swaption trade (premium + position)
3. Expiry arrives, swaption is OTM
4. Expire swaption -> `create_swaption_expiry_transaction`
5. **Verify:** seller keeps premium, sigma(swaption_unit) = 0

### 8.5 Collateral Lifecycle (10 steps)

1. CDS trade booked (from 8.1)
2. Compute margin call -> `compute_margin_call`
3. Deliver cash collateral -> `create_collateral_delivery_transaction`
4. **Verify CL-C8:** sigma(currency) = 0
5. Market moves, exposure increases
6. Compute second margin call
7. Deliver government bond collateral
8. Substitution: return bonds, deliver cash -> `create_collateral_substitution_transaction`
9. **Verify:** substitution is atomic (single Transaction, 2 Moves)
10. Trade matures, return all collateral -> `create_collateral_return_transaction`

### 8.6 Cross-Product Integration (8 steps)

1. Book CDS trade
2. Book swaption trade
3. Compute aggregate portfolio exposure
4. Deliver collateral for both trades
5. CDS credit event -> settlement
6. Swaption exercised -> IRS created
7. Updated margin call reflecting new portfolio
8. **Verify:** all conservation laws hold across all products simultaneously

### 8.7 Engine Untouched Verification

- `engine.py` has zero CDS/swaption/collateral keywords
- SHA-256 of `engine.py` unchanged from Phase 3

**Expected integration tests: ~50**

---

## 9. Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| CDS accrual convention mismatch | HIGH | Use exclusively ISDA standard: ACT/360, quarterly, IMM dates. No configurable overrides in Phase 4. Test against known ISDA calculator outputs. |
| Credit event timing race condition | HIGH | Credit event timestamp is `UtcDatetime`. All CDS premium payments after `determination_date` must be rejected by validation. |
| Recovery rate source disagreement | MEDIUM | Recovery rate comes exclusively from ISDA auction via Oracle attestation. No manual override path. Recovery rate is immutable once attested. |
| Swaption exercise -> IRS atomicity | HIGH | Exercise and IRS creation share tx_id prefix for audit linkage. If IRS creation fails, swaption exercise must be compensated (new reversal Transaction, not an update). |
| Collateral substitution partial failure | HIGH | Enforced by Transaction atomicity: both Moves in one Transaction. LedgerEngine executes all Moves or none. No partial state. |
| Float contamination in SVI parameters | HIGH | All SVI parameters are `Decimal`. Use `Decimal.sqrt()` not `math.sqrt`. Ship `decimal_math.py` with pure-Decimal `exp_d`, `ln_d`. |
| Vol surface overfitting | MEDIUM | AF-VS-01..07 gates reject overfitted surfaces. Roger Lee bounds prevent wing explosion. RMSE threshold rejects poor fits. |
| Credit curve extrapolation beyond last tenor | MEDIUM | Flat hazard rate extrapolation. Staleness attestation if curve age exceeds threshold. |
| Collateral haircut schedule stale | MEDIUM | HaircutSchedule is an attested object with provenance. Staleness monitoring via Oracle. |
| Dodd-Frank reporting field mapping error | HIGH | Field mapping table in this specification is the source of truth. Each field maps 1:1 from CDSDetail. Unit tests verify every field. |

---

## 10. Acceptance Criteria

From MASTER_PLAN Phase 4, verified against this specification:

- [ ] CDS trade booked with premium and protection legs (Section 1.4)
- [ ] Credit event triggers settlement -- auction price from Oracle, recovery payment booked (Section 1.4.3)
- [ ] Swaption exercise produces IRS instrument and lifecycle continues from Phase 3 (Section 2.4.2, 2.4.3)
- [ ] Vol surface calibration produces arbitrage-free surface (Gatheral PLAN.md Section 7.1):
  - [ ] Calendar spread: `w(k, T2) >= w(k, T1)` for `T2 > T1`
  - [ ] Butterfly: Durrleman condition `g(k) >= 0` for all k
  - [ ] Wing bounds: Roger Lee `lim sup w(k)/|k| <= 2`
- [ ] Credit curve bootstrapping produces valid survival probabilities (Gatheral PLAN.md Section 7.2):
  - [ ] `0 <= Q(t) <= 1`, `Q(0) = 1`
  - [ ] `Q(t2) <= Q(t1)` for `t2 > t1`
  - [ ] `lambda(t) >= 0`
- [ ] Collateral management: margin calls produce collateral transfer transactions (Section 3.5.1)
- [ ] Collateral substitution: atomic, balanced (Section 3.5.3)
- [ ] Pillar V stub contract verified for CDS and swaption types
- [ ] Derived confidence payloads complete for vol surfaces and credit curves
- [ ] Model Configuration Attestation for every calibrated surface and credit curve (Section 4.6)
- [ ] Replay test: Kafka log replay reproduces identical vol surfaces and credit curves
- [ ] All 9 new conservation laws (CL-C1 through CL-C9) verified (Section 6)
- [ ] All existing conservation laws (CL-A1 through CL-A9) still hold for Phase 4 transactions
- [ ] engine.py not modified (Principle V)

---

## Files That MUST NOT Be Modified

- `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/engine.py` (Principle V)
- `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/core/result.py` (foundation)
- `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/core/serialization.py` (foundation)
- `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/core/errors.py` (foundation -- extend only)
- `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/irs.py` (Phase 3 -- consumed by swaption exercise, not modified)
- `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/options.py` (Phase 2)
- `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/futures.py` (Phase 2)
- `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/fx_settlement.py` (Phase 3)

---

## Dependencies

Phase 3 must be fully passing (target ~1004 tests) before Phase 4 begins. No external library additions beyond what Phase 3 uses. Python stdlib `decimal`, `datetime`, `enum`, `dataclasses`, `typing`. The `dateutil` dependency continues. `scipy.optimize` is acceptable for L-BFGS-B in SVI/SSVI calibration (Oracle scope, covered by Gatheral PLAN.md).
