# ATTESTOR Phase 1 Execution Plan — Equity Cash Full Lifecycle

**Version:** 1.0
**Date:** 2026-02-15
**Governance:** Minsky chairs, Formalis veto, full committee review
**Prerequisite:** Phase 0 complete (341 tests, 1,996 production lines, all green)

---

## 1. Executive Summary

Phase 1 takes a cash equity trade through **all five pillars**: a raw order enters the Gateway, becomes a canonical instrument, books as a double-entry transaction in the Ledger, gets attested market prices from the Oracle, settles at T+2, processes dividends, and projects to an EMIR regulatory report — with the commutativity invariant proven end-to-end.

**Products:** Cash equities, ETFs.
**Lifecycle:** Order → Execution → Booking → Settlement (T+2) → Dividend → Position query.
**Pillar V:** Stub only — returns last Oracle price as "valuation".

### What Gets Built

| Pillar | New Modules | LOC Estimate |
|--------|------------|:---:|
| I — Gateway | `gateway/types.py`, `gateway/parser.py` | ~200 |
| II — Instrument | `instrument/types.py`, `instrument/lifecycle.py` | ~400 |
| II — Ledger | `ledger/engine.py`, `ledger/settlement.py`, `ledger/dividends.py` | ~600 |
| III — Oracle | `oracle/ingest.py` | ~150 |
| IV — Reporting | `reporting/emir.py` | ~200 |
| V — Pricing | Update `pricing/protocols.py` stub | ~30 |
| Infra | `infra/config.py` updates, 6 SQL DDLs | ~250 |
| **Total new production** | **12 new files + 3 updates** | **~1,830** |
| **Tests** | **~15 new test files** | **~4,000** |

### How to Prove Correctness

1. **Conservation:** Every `execute()` preserves `sigma(U)` for all units — property-based, 1000+ cases.
2. **Commutativity:** `report(normalize(raw)) == report(attest(normalize(raw)))` — the Master Square.
3. **Replay determinism:** Wipe state, replay transaction log, arrive at identical positions.
4. **T+2 settlement:** 4 balanced moves (cash debit/credit, securities debit/credit) net to zero.
5. **Type safety:** mypy --strict, zero Any in domain, all dataclasses frozen.

---

## 2. Phase 0 Foundation (What Already Exists)

### 2.1 Existing Modules (20 files, 1,996 LOC)

```
attestor/
├── core/
│   ├── __init__.py      (95)   Re-exports all core types
│   ├── errors.py        (142)  AttestorError + 7 @final subclasses
│   ├── identifiers.py   (93)   LEI, UTI, ISIN with Luhn
│   ├── money.py         (148)  Money, PositiveDecimal, NonZeroDecimal, NonEmptyStr
│   ├── result.py        (111)  Ok, Err, Result, unwrap, sequence, map_result
│   ├── serialization.py (92)   canonical_bytes, content_hash, derive_seed
│   └── types.py         (128)  UtcDatetime, FrozenMap, BitemporalEnvelope, IdempotencyKey
├── infra/
│   ├── __init__.py      (24)   Re-exports
│   ├── config.py        (151)  TopicConfig, Kafka/Postgres configs
│   ├── health.py        (78)   HealthStatus, SystemHealth, HealthCheckable
│   ├── memory_adapter.py(159)  InMemory* implementations of all 4 protocols
│   └── protocols.py     (103)  AttestationStore, EventBus, TransactionLog, StateStore
├── ledger/
│   ├── __init__.py      (17)   Re-exports
│   └── transactions.py  (173)  DeltaValue(6), StateDelta, DistinctAccountPair, Move,
│                                Transaction, LedgerEntry, Account, AccountType, Position
├── oracle/
│   ├── __init__.py      (9)    Re-exports
│   └── attestation.py   (251)  FirmConfidence, QuotedConfidence, DerivedConfidence,
│                                Attestation[T], create_attestation, QuoteCondition
└── pricing/
    ├── __init__.py      (8)    Re-exports
    ├── protocols.py     (96)   PricingEngine, RiskEngine, StubPricingEngine
    └── types.py         (118)  ValuationResult, Greeks, Scenario, ScenarioResult,
                                 VaRResult, PnLAttribution
```

### 2.2 Existing Types Phase 1 Builds On

| Type | Module | Phase 1 Usage |
|------|--------|---------------|
| `Result[T,E]`, `Ok`, `Err` | core.result | Every function that can fail |
| `Money` | core.money | Cash amounts in settlement/dividends |
| `PositiveDecimal` | core.money | Trade quantities, amounts |
| `NonEmptyStr` | core.money | All string identifiers |
| `FrozenMap[K,V]` | core.types | Order fields, market snapshots |
| `UtcDatetime` | core.types | All timestamps |
| `BitemporalEnvelope[T]` | core.types | Kafka messages, transaction log |
| `IdempotencyKey` | core.types | Transaction dedup |
| `Attestation[T]` | oracle.attestation | Market prices, reports |
| `FirmConfidence` | oracle.attestation | Exchange fills |
| `QuotedConfidence` | oracle.attestation | Market quotes |
| `create_attestation` | oracle.attestation | Factory for all attestations |
| `DistinctAccountPair` | ledger.transactions | Every ledger entry |
| `Move` | ledger.transactions | Atomic balance transfer |
| `Transaction` | ledger.transactions | Batch of moves |
| `Account`, `AccountType` | ledger.transactions | Chart of accounts |
| `Position` | ledger.transactions | Balance tracking |
| `LedgerEntry` | ledger.transactions | Double-entry record |
| `ValuationResult` | pricing.types | Stub pricing output |
| `PricingEngine` | pricing.protocols | Stub protocol |
| `AttestationStore` | infra.protocols | Store attestations |
| `TransactionLog` | infra.protocols | Append-only tx log |
| `InMemory*` | infra.memory_adapter | Test doubles |
| `content_hash` | core.serialization | Attestation identity |
| `canonical_bytes` | core.serialization | Deterministic serialization |
| All error types | core.errors | Structured error values |
| `LEI`, `UTI`, `ISIN` | core.identifiers | Party, trade, instrument IDs |

### 2.3 Existing Infrastructure

- **3 Kafka topics** configured: `attestor.events.raw`, `attestor.events.normalized`, `attestor.attestations`
- **3 Postgres tables** DDL: `attestations`, `event_log`, `schema_registry`
- **CI pipeline**: mypy strict, ruff, pytest, no-float check, all-frozen check, no-raise check, import smoke test
- **341 tests** all passing

---

## 3. New File Tree (Phase 1 Additions)

```
attestor/
├── gateway/                    # NEW — Pillar I
│   ├── __init__.py
│   ├── types.py                # CanonicalOrder, OrderSide, OrderType
│   └── parser.py               # parse_order(raw_dict) -> Result[CanonicalOrder, ValidationError]
├── instrument/                 # NEW — Instrument Model (Pillar II scope)
│   ├── __init__.py
│   ├── types.py                # Instrument, Product, EconomicTerms, EquityPayoutSpec, Party
│   └── lifecycle.py            # PositionStatusEnum, TRANSITIONS, check_transition, BusinessEvent
├── ledger/
│   ├── __init__.py             # UPDATE — add re-exports
│   ├── transactions.py         # EXISTING — no changes
│   ├── engine.py               # NEW — LedgerEngine: execute, get_balance, get_position, clone
│   ├── settlement.py           # NEW — create_settlement_transaction (T+2, 4 moves)
│   └── dividends.py            # NEW — create_dividend_transaction
├── oracle/
│   ├── __init__.py             # UPDATE — add re-exports
│   ├── attestation.py          # EXISTING — no changes
│   └── ingest.py               # NEW — ingest_equity_price, MarketDataPoint
├── reporting/                  # NEW — Pillar IV
│   ├── __init__.py
│   └── emir.py                 # EMIRTradeReport, project_emir_report
├── pricing/
│   ├── __init__.py             # EXISTING — no changes
│   ├── protocols.py            # UPDATE — StubPricingEngine returns Oracle price
│   └── types.py                # EXISTING — no changes
└── infra/
    ├── config.py               # UPDATE — add 5 Phase 1 topic configs

sql/
├── 004_accounts.sql            # NEW
├── 005_positions.sql           # NEW
├── 006_transactions.sql        # NEW
├── 007_instruments.sql         # NEW
├── 008_market_data.sql         # NEW
└── 009_reports_emir.sql        # NEW

tests/
├── test_gateway_types.py       # NEW
├── test_gateway_parser.py      # NEW
├── test_instrument_types.py    # NEW
├── test_lifecycle.py           # NEW
├── test_ledger_engine.py       # NEW — THE most important test file
├── test_settlement.py          # NEW
├── test_dividends.py           # NEW
├── test_oracle_ingest.py       # NEW
├── test_reporting_emir.py      # NEW
├── test_commutativity.py       # NEW — Master Square proof
├── test_conservation_laws.py   # NEW — property-based sigma(U) invariant
├── test_replay.py              # NEW — deterministic replay
├── test_integration_lifecycle.py # NEW — full order-to-report
├── conftest.py                 # UPDATE — add Phase 1 strategies
```

---

## 4. Type Specifications

### 4.1 Gateway Types (`attestor/gateway/types.py`)

```python
class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"

@final @dataclass(frozen=True, slots=True)
class CanonicalOrder:
    """Normalised equity order — output of Gateway, input to Ledger."""
    order_id: NonEmptyStr
    instrument_id: NonEmptyStr    # e.g. "AAPL", "SPY"
    isin: ISIN | None             # Optional ISIN for regulatory reporting
    side: OrderSide
    quantity: PositiveDecimal
    price: Decimal                # limit price or fill price
    currency: NonEmptyStr         # ISO 4217
    order_type: OrderType
    counterparty_lei: LEI
    executing_party_lei: LEI
    trade_date: date
    settlement_date: date         # trade_date + 2 business days
    venue: NonEmptyStr            # Exchange or OTC venue
    timestamp: UtcDatetime

    @staticmethod
    def create(...) -> Ok[CanonicalOrder] | Err[ValidationError]:
        """Validate all fields and return Result."""
```

**Invariants:**
- `settlement_date >= trade_date` (enforced by factory)
- `quantity.value > 0` (enforced by PositiveDecimal)
- `price` is finite Decimal (enforced by factory)
- All string fields non-empty (enforced by NonEmptyStr)

### 4.2 Instrument Types (`attestor/instrument/types.py`)

```python
@final @dataclass(frozen=True, slots=True)
class Party:
    party_id: NonEmptyStr
    name: NonEmptyStr
    lei: LEI

    @staticmethod
    def create(party_id: str, name: str, lei: str) -> Ok[Party] | Err[str]: ...

@final @dataclass(frozen=True, slots=True)
class EquityPayoutSpec:
    """Cash equity or ETF payout."""
    instrument_id: NonEmptyStr    # Ticker or ISIN
    currency: NonEmptyStr         # Settlement currency
    exchange: NonEmptyStr         # Primary exchange

@final @dataclass(frozen=True, slots=True)
class EconomicTerms:
    payout: EquityPayoutSpec      # Phase 1: equity only; Phase 2+ extends to Union
    effective_date: date
    termination_date: date | None  # None for perpetual equities

@final @dataclass(frozen=True, slots=True)
class Product:
    economic_terms: EconomicTerms

@final @dataclass(frozen=True, slots=True)
class Instrument:
    instrument_id: NonEmptyStr
    product: Product
    parties: tuple[Party, ...]
    trade_date: date
    status: PositionStatusEnum
```

**Design decision:** `EconomicTerms.payout` is `EquityPayoutSpec` in Phase 1, not yet the full `Payout` union type. Phase 2 introduces `OptionPayoutSpec | FuturesPayoutSpec` and the type becomes a union. This avoids building unused variants.

### 4.3 Lifecycle State Machine (`attestor/instrument/lifecycle.py`)

```python
class PositionStatusEnum(Enum):
    PROPOSED = "Proposed"
    FORMED = "Formed"
    SETTLED = "Settled"
    CANCELLED = "Cancelled"
    CLOSED = "Closed"

# Valid transitions for equity cash (subset of full 20-transition table)
EQUITY_TRANSITIONS: frozenset[tuple[PositionStatusEnum, PositionStatusEnum]] = frozenset({
    (PositionStatusEnum.PROPOSED, PositionStatusEnum.FORMED),      # Order accepted
    (PositionStatusEnum.PROPOSED, PositionStatusEnum.CANCELLED),   # Order rejected
    (PositionStatusEnum.FORMED, PositionStatusEnum.SETTLED),       # Settlement
    (PositionStatusEnum.FORMED, PositionStatusEnum.CANCELLED),     # Trade cancelled
    (PositionStatusEnum.SETTLED, PositionStatusEnum.CLOSED),       # Position closed
})

def check_transition(
    from_state: PositionStatusEnum,
    to_state: PositionStatusEnum,
) -> Ok[None] | Err[IllegalTransitionError]:
    """Validate state transition against the equity transition table."""

# PrimitiveInstruction variants needed for Phase 1
@final @dataclass(frozen=True, slots=True)
class ExecutePI:
    """Execute a new trade."""
    order: CanonicalOrder

@final @dataclass(frozen=True, slots=True)
class TransferPI:
    """Settlement transfer — cash and securities."""
    instrument_id: NonEmptyStr
    quantity: PositiveDecimal
    cash_amount: Money
    from_account: NonEmptyStr
    to_account: NonEmptyStr

@final @dataclass(frozen=True, slots=True)
class DividendPI:
    """Dividend payment."""
    instrument_id: NonEmptyStr
    amount_per_share: PositiveDecimal
    ex_date: date
    payment_date: date
    currency: NonEmptyStr

# Phase 1 instruction union (extended in Phase 2+)
PrimitiveInstruction = ExecutePI | TransferPI | DividendPI

@final @dataclass(frozen=True, slots=True)
class BusinessEvent:
    instruction: PrimitiveInstruction
    timestamp: UtcDatetime
    attestation_id: str | None = None  # Links to source attestation
```

### 4.4 Ledger Engine (`attestor/ledger/engine.py`)

```python
@final
class LedgerEngine:
    """Double-entry bookkeeping engine with conservation law enforcement.

    Core invariant (INV-L01): For every unit U,
        sigma(U) = sum_W beta(W, U) is unchanged by every execute().

    Position index: O(1) lookup by (account, instrument).
    """

    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}
        self._balances: dict[tuple[str, str], Decimal] = {}  # (account_id, instrument) -> qty
        self._transactions: list[Transaction] = []
        self._applied_tx_ids: set[str] = set()  # For idempotency (INV-X03)

    def register_account(self, account: Account) -> Ok[None] | Err[str]:
        """Register an account in the chart of accounts (INV-L06)."""

    def execute(self, tx: Transaction) -> Ok[ExecuteResult] | Err[ConservationViolationError]:
        """Execute a transaction atomically (INV-L05).

        1. Check idempotency (INV-X03): already applied -> Ok(ALREADY_APPLIED)
        2. Verify all accounts exist (INV-L06)
        3. Pre-compute sigma(U) for affected units
        4. Apply all moves: source balance -= qty, dest balance += qty
        5. Post-verify sigma(U) unchanged (INV-L01)
        6. Record transaction
        7. Return Ok(APPLIED)

        On any failure: revert ALL balance changes (INV-L05 atomicity).
        """

    def get_balance(self, account_id: str, instrument: str) -> Decimal:
        """O(1) balance lookup."""

    def get_position(self, account_id: str, instrument: str) -> Position:
        """Return Position for (account, instrument)."""

    def positions(self) -> tuple[Position, ...]:
        """All non-zero positions."""

    def total_supply(self, instrument: str) -> Decimal:
        """sigma(U) — sum of all balances for instrument across all accounts."""

    def clone(self) -> LedgerEngine:
        """Deep copy for time-travel (INV-L09)."""

    def transaction_count(self) -> int:
        """Number of applied transactions."""
```

**Conservation law enforcement (INV-L01):**
```python
# Inside execute():
# 1. Identify affected units
affected_units = {m.unit for m in tx.moves}
# 2. Pre-compute sigma
pre_sigma = {u: self.total_supply(u) for u in affected_units}
# 3. Apply moves
for move in tx.moves:
    self._balances[(move.source, move.unit)] -= move.quantity.value
    self._balances[(move.destination, move.unit)] += move.quantity.value
# 4. Post-verify
for u in affected_units:
    post = self.total_supply(u)
    if pre_sigma[u] != post:
        # REVERT and return Err
        return Err(ConservationViolationError(...))
```

### 4.5 Settlement (`attestor/ledger/settlement.py`)

```python
def create_settlement_transaction(
    order: CanonicalOrder,
    buyer_cash_account: str,
    buyer_securities_account: str,
    seller_cash_account: str,
    seller_securities_account: str,
    tx_id: str,
) -> Ok[Transaction] | Err[ValidationError]:
    """Create a T+2 settlement transaction with 4 balanced moves.

    Move 1: Cash from buyer_cash -> seller_cash (price * quantity)
    Move 2: Securities from seller_securities -> buyer_securities (quantity)

    INV-L04: cash_transferred + securities_transferred = 0 (net per settlement)
    The two Move pairs are balanced: what leaves one account enters another.
    """
```

**The 4-move pattern:**
```
Buyer Cash Account   ──[price * qty]──>  Seller Cash Account
Seller Securities    ──[qty]──>          Buyer Securities Account
```

This is a 2-move transaction (each Move has source → destination), creating 4 balance changes total. Conservation holds because each Move adds to destination exactly what it removes from source.

### 4.6 Dividend Processing (`attestor/ledger/dividends.py`)

```python
def create_dividend_transaction(
    instrument_id: str,
    amount_per_share: Decimal,
    currency: str,
    holder_accounts: tuple[tuple[str, Decimal], ...],  # (account_id, shares_held)
    issuer_account: str,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Create dividend payment transaction.

    For each holder: Move cash from issuer -> holder (amount_per_share * shares_held).
    Conservation: total cash out of issuer == sum of cash into all holders.
    """
```

### 4.7 Oracle Equity Ingestion (`attestor/oracle/ingest.py`)

```python
@final @dataclass(frozen=True, slots=True)
class MarketDataPoint:
    """A single equity price observation."""
    instrument_id: NonEmptyStr
    price: Decimal
    currency: NonEmptyStr
    timestamp: UtcDatetime

def ingest_equity_fill(
    instrument_id: str,
    price: Decimal,
    currency: str,
    exchange: str,
    timestamp: datetime,
    exchange_ref: str,
) -> Ok[Attestation[MarketDataPoint]] | Err[str]:
    """Ingest an exchange fill as a Firm attestation."""

def ingest_equity_quote(
    instrument_id: str,
    bid: Decimal,
    ask: Decimal,
    currency: str,
    venue: str,
    timestamp: datetime,
) -> Ok[Attestation[MarketDataPoint]] | Err[str]:
    """Ingest a market quote as a Quoted attestation (mid price)."""
```

### 4.8 EMIR Reporting (`attestor/reporting/emir.py`)

```python
@final @dataclass(frozen=True, slots=True)
class EMIRTradeReport:
    """EMIR trade report — pure projection from instrument + ledger state."""
    uti: UTI
    reporting_counterparty_lei: LEI
    other_counterparty_lei: LEI
    instrument_id: NonEmptyStr
    isin: ISIN | None
    direction: OrderSide
    quantity: PositiveDecimal
    price: Decimal
    currency: NonEmptyStr
    trade_date: date
    settlement_date: date
    venue: NonEmptyStr
    report_timestamp: UtcDatetime
    attestation_refs: tuple[str, ...]  # Input attestation hashes for provenance

def project_emir_report(
    order: CanonicalOrder,
    trade_attestation_id: str,
) -> Ok[Attestation[EMIRTradeReport]] | Err[str]:
    """Project an EMIR report from a canonical order.

    INV-R01: This is a PROJECTION, not a transformation.
    The report contains exactly the fields from the order, reformatted
    to EMIR schema. No new values are computed.
    """
```

---

## 5. Invariants Activated in Phase 1

### 5.1 From the Invariant Registry (PLAN.md Section 5)

| ID | Name | Phase 1 Test |
|----|------|-------------|
| INV-G01 | Parse Idempotency | `parse_order(parse_order(raw).to_dict()) == parse_order(raw)` |
| INV-G02 | Parse Totality | `parse_order(raw)` returns Ok or Err, never panics |
| INV-L01 | Balance Conservation | `sigma(U, after) == sigma(U, before)` for every `execute()` |
| INV-L02 | Position Conservation | No position created without an Attestation |
| INV-L04 | Settlement Conservation | `cash + securities = 0` per settlement |
| INV-L05 | Transaction Atomicity | Partial failure reverts ALL balance changes |
| INV-L06 | Chart of Accounts | Every move references a registered account |
| INV-L09 | Clone Independence | Cloned ledger mutations don't affect original |
| INV-L10 | Domain Function Totality | No raise in domain functions (CI AST scan) |
| INV-O01 | Attestation Immutability | No attestation modified after creation |
| INV-O04 | Confidence Exhaustiveness | Every attestation is Firm, Quoted, or Derived |
| INV-R01 | Regulatory Isomorphism | Reporting is projection, not transformation |
| INV-R02 | Commutativity (Point) | Master Square holds with stub V |
| INV-R04 | Reproducibility | Same inputs → same output across runs |
| INV-R05 | Content-Addressing | Same content → same attestation_id |
| INV-X03 | Idempotency | `execute(tx); execute(tx)` → ALREADY_APPLIED |
| INV-P06 | Append-Only | No UPDATE/DELETE on attestation tables |

### 5.2 Conservation Laws Tested

| Law | Property | Test |
|-----|----------|------|
| CL-A1 | `sigma(U)` unchanged by every `execute()` | Property-based, 1000+ cases |
| CL-A2 | `sum(debits) == sum(credits)` per transaction | Every transaction |
| CL-A3 | Event timestamps non-decreasing | Every PR |
| CL-A5 | Deterministic execution | Same inputs → same outputs, 100 runs |
| CL-A7 | Commutativity / path independence | Master Square |

### 5.3 The Commutativity Proof (Master Square)

```
                    parse_order
    Raw Order ─────────────────────> CanonicalOrder
         │                                 │
         │                                 │ book_trade (Ledger)
         │                                 │
         ▼                                 ▼
    Raw + Oracle ──────────────────> Ledger State
         │                                 │
         │ project_emir                    │ project_emir
         ▼                                 ▼
    EMIR Report A                    EMIR Report B
                                     (must equal A)
```

**Formal statement:**
```
project_emir(normalize(raw), attestation) == project_emir(book(normalize(raw)), attestation)
```

Both paths through the diagram must produce the same EMIR report. This tests:
1. Gateway normalization preserves all EMIR-relevant fields
2. Ledger booking doesn't alter instrument identity
3. Reporting projects the same fields regardless of processing path

**Test implementation:**
```python
def test_master_square_equity_cash():
    """CS-02: Booking then reporting == reporting the order directly."""
    raw = {...}  # Raw order dict
    order = unwrap(parse_order(raw))

    # Path A: report from order directly
    report_a = unwrap(project_emir_report(order, "att-001"))

    # Path B: book, then report from booked state
    tx = unwrap(create_settlement_transaction(order, ...))
    ledger.execute(tx)
    report_b = unwrap(project_emir_report(order, "att-001"))

    # Reports must match
    assert report_a.value.uti == report_b.value.uti
    assert report_a.value.quantity == report_b.value.quantity
    assert report_a.value.price == report_b.value.price
    assert report_a.content_hash == report_b.content_hash
```

---

## 6. Build Sequence (14 Steps)

**Protocol:** For each step: write source → mypy --strict → ruff check --fix → write tests → pytest → confirm green → next step. Never skip verification.

### Step 1: Gateway Types

**Create:** `attestor/gateway/__init__.py`, `attestor/gateway/types.py`

**Contents:**
- `OrderSide` enum (BUY, SELL)
- `OrderType` enum (MARKET, LIMIT)
- `CanonicalOrder` frozen dataclass with `create()` factory
- Validation: settlement_date >= trade_date, finite price, all strings non-empty

**Tests:** `tests/test_gateway_types.py`
- Valid CanonicalOrder creation
- Rejection of invalid fields (empty instrument, negative quantity, settlement < trade date)
- Serialization round-trip via canonical_bytes
- ISIN validation when present

**Expected:** ~80 LOC source, ~120 LOC tests, ~8 tests

### Step 2: Gateway Parser

**Create:** `attestor/gateway/parser.py`

**Contents:**
- `parse_order(raw: dict[str, object]) -> Ok[CanonicalOrder] | Err[ValidationError]`
- Extract and validate all fields from raw dict
- Compute settlement_date = trade_date + 2 business days (simple: skip weekends)
- Return structured ValidationError with FieldViolation list on failure

**Tests:** `tests/test_gateway_parser.py`
- Parse valid equity order
- Parse with missing fields → Err with FieldViolation
- Parse with invalid types → Err
- INV-G01: `parse_order(parse_order(raw).to_dict()) == parse_order(raw)` (idempotency)
- INV-G02: Hypothesis fuzz — parse never panics (totality)

**Expected:** ~100 LOC source, ~150 LOC tests, ~12 tests

### Step 3: Instrument Types

**Create:** `attestor/instrument/__init__.py`, `attestor/instrument/types.py`

**Contents:**
- `Party` with `create()` factory (validates party_id, name, LEI)
- `EquityPayoutSpec` (instrument_id, currency, exchange)
- `EconomicTerms` (payout, effective_date, termination_date)
- `Product` (economic_terms)
- `Instrument` (instrument_id, product, parties, trade_date, status)
- `create_equity_instrument(order: CanonicalOrder, ...) -> Ok[Instrument] | Err[str]`

**Tests:** `tests/test_instrument_types.py`
- Valid creation of all types
- Party with invalid LEI → Err
- Instrument serialization round-trip
- create_equity_instrument from CanonicalOrder

**Expected:** ~120 LOC source, ~150 LOC tests, ~10 tests

### Step 4: Lifecycle State Machine

**Create:** `attestor/instrument/lifecycle.py`

**Contents:**
- `PositionStatusEnum` (PROPOSED, FORMED, SETTLED, CANCELLED, CLOSED)
- `EQUITY_TRANSITIONS` frozenset of valid (from, to) pairs (5 transitions)
- `check_transition()` → Ok or Err[IllegalTransitionError]
- `ExecutePI`, `TransferPI`, `DividendPI` instruction variants
- `PrimitiveInstruction` union type
- `BusinessEvent` frozen dataclass

**Tests:** `tests/test_lifecycle.py`
- All 5 valid transitions succeed
- All invalid transitions return IllegalTransitionError
- Pattern match exhaustiveness on PrimitiveInstruction
- BusinessEvent with each variant

**Expected:** ~100 LOC source, ~120 LOC tests, ~15 tests

### Step 5: Ledger Engine

**Create:** `attestor/ledger/engine.py`

**Contents:**
- `LedgerEngine` class (NOT a frozen dataclass — it has mutable internal state)
- `register_account()` — add to chart of accounts
- `execute(tx)` — atomic transaction execution with conservation check
- `get_balance(account, instrument)` — O(1) lookup
- `get_position(account, instrument)` — returns Position
- `positions()` — all non-zero positions
- `total_supply(instrument)` — sigma(U)
- `clone()` — deep copy for INV-L09
- `transaction_count()` — count of applied transactions

**Invariants enforced:**
- INV-L01: sigma(U) verified before/after every execute
- INV-L05: atomic — revert on failure
- INV-L06: all accounts must exist
- INV-X03: idempotent (tx_id dedup)

**Tests:** `tests/test_ledger_engine.py` — **THE most critical test file**
- register_account and execute simple 1-move transaction
- Balance conservation: sigma before == sigma after (Hypothesis, 1000 cases)
- Atomicity: invalid move reverts all changes
- Idempotency: same tx_id applied twice → ALREADY_APPLIED
- Chart of accounts: move to unregistered account → Err
- Clone independence: clone.execute doesn't affect original
- Position tracking: get_balance, get_position, positions()
- total_supply computation
- Multi-move transaction (settlement pattern)
- Zero-balance positions excluded from positions()

**Expected:** ~200 LOC source, ~400 LOC tests, ~25 tests

### Step 6: Settlement T+2

**Create:** `attestor/ledger/settlement.py`

**Contents:**
- `create_settlement_transaction(order, buyer_cash, buyer_sec, seller_cash, seller_sec, tx_id) -> Ok[Transaction] | Err[ValidationError]`
- Creates Transaction with 2 Moves:
  - Move 1: cash from buyer → seller (price * quantity)
  - Move 2: securities from seller → buyer (quantity shares)
- Both amounts use PositiveDecimal (enforced > 0)

**Tests:** `tests/test_settlement.py`
- Valid settlement creates 2 balanced moves
- Cash amount = price * quantity (Decimal arithmetic under ATTESTOR_DECIMAL_CONTEXT)
- Execute settlement: 4 balance changes, sigma preserved
- Full lifecycle: register accounts → execute settlement → verify positions
- INV-L04: settlement is zero-sum (cash out + securities in = 0 for buyer, inverse for seller)
- Edge: zero-price order → Err (quantity must be positive)

**Expected:** ~80 LOC source, ~200 LOC tests, ~12 tests

### Step 7: Dividend Processing

**Create:** `attestor/ledger/dividends.py`

**Contents:**
- `create_dividend_transaction(instrument_id, amount_per_share, currency, holders, issuer, tx_id, timestamp) -> Ok[Transaction] | Err[ValidationError]`
- Creates one Move per holder: cash from issuer → holder (amount_per_share * shares)
- Total dividend = sum(amount_per_share * shares) for all holders

**Tests:** `tests/test_dividends.py`
- Valid dividend to single holder
- Valid dividend to multiple holders
- Total cash out of issuer == sum of cash into holders
- Execute dividend: sigma(cash_currency) preserved
- Edge: zero holders → Err

**Expected:** ~60 LOC source, ~120 LOC tests, ~8 tests

### Step 8: Oracle Equity Ingestion

**Create:** `attestor/oracle/ingest.py`

**Contents:**
- `MarketDataPoint` frozen dataclass (instrument_id, price, currency, timestamp)
- `ingest_equity_fill(instrument_id, price, currency, exchange, timestamp, exchange_ref) -> Ok[Attestation[MarketDataPoint]] | Err[str]`
  - Creates FirmConfidence attestation
- `ingest_equity_quote(instrument_id, bid, ask, currency, venue, timestamp) -> Ok[Attestation[MarketDataPoint]] | Err[str]`
  - Creates QuotedConfidence attestation (value = mid price)

**Tests:** `tests/test_oracle_ingest.py`
- Firm attestation from fill: correct confidence type, source, content_hash
- Quoted attestation from quote: mid price computed correctly
- Invalid inputs: negative price → Err, empty instrument → Err
- Content hash stability: same inputs → same hash
- Attestation_id differs for different sources (GAP-01)

**Expected:** ~80 LOC source, ~150 LOC tests, ~10 tests

### Step 9: EMIR Reporting

**Create:** `attestor/reporting/__init__.py`, `attestor/reporting/emir.py`

**Contents:**
- `EMIRTradeReport` frozen dataclass with all EMIR fields
- `project_emir_report(order: CanonicalOrder, trade_attestation_id: str) -> Ok[Attestation[EMIRTradeReport]] | Err[str]`
  - Pure projection: select and format order fields to EMIR schema
  - Generate UTI from content hash
  - Report is itself an Attestation with provenance pointing to trade attestation

**INV-R01:** Reporting is projection, not transformation. No new values computed.

**Tests:** `tests/test_reporting_emir.py`
- Valid projection from CanonicalOrder
- All EMIR fields match source order
- Report is an Attestation with correct provenance
- UTI format validation
- Idempotency: same order → same report content_hash
- INV-R01: report fields are strict subset of order fields (no new computation)

**Expected:** ~100 LOC source, ~150 LOC tests, ~10 tests

### Step 10: Stub Pricing Update

**Update:** `attestor/pricing/protocols.py`

**Contents:**
- Add `oracle_price` parameter to StubPricingEngine.price()
- Stub now returns the Oracle's attested price as the "valuation"
- This enables the Master Square test: stub_price(book(trade)) == book(stub_price(trade))

**Tests:** Update `tests/test_pricing_protocols.py`
- StubPricingEngine.price() with oracle price returns that price as NPV
- Protocol satisfaction still holds

**Expected:** ~30 LOC changes, ~30 LOC test changes, ~3 tests

### Step 11: Kafka Topics + SQL DDL

**Update:** `attestor/infra/config.py` — add 5 Phase 1 topic configs

**Create 6 SQL files:**

```sql
-- sql/004_accounts.sql
CREATE TABLE accounts (
    account_id TEXT PRIMARY KEY,
    account_type TEXT NOT NULL CHECK (account_type IN ('CASH','SECURITIES','DERIVATIVES','COLLATERAL','MARGIN','ACCRUALS','PNL')),
    owner_party_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Append-only: no UPDATE/DELETE
    CONSTRAINT accounts_no_update CHECK (TRUE)
);
CREATE TRIGGER accounts_append_only BEFORE UPDATE OR DELETE ON accounts
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();

-- sql/005_positions.sql (bitemporal)
CREATE TABLE positions (
    account_id TEXT NOT NULL REFERENCES accounts(account_id),
    instrument_id TEXT NOT NULL,
    quantity DECIMAL NOT NULL,
    valid_time TIMESTAMPTZ NOT NULL,
    system_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (account_id, instrument_id, valid_time)
);
CREATE INDEX idx_positions_instrument ON positions (instrument_id, valid_time);

-- sql/006_transactions.sql (append-only)
CREATE TABLE transactions (
    tx_id TEXT PRIMARY KEY,
    moves JSONB NOT NULL,
    state_deltas JSONB NOT NULL DEFAULT '[]'::jsonb,
    valid_time TIMESTAMPTZ NOT NULL,
    system_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    idempotency_key TEXT UNIQUE
);

-- sql/007_instruments.sql (bitemporal)
CREATE TABLE instruments (
    instrument_id TEXT NOT NULL,
    product JSONB NOT NULL,
    parties JSONB NOT NULL,
    trade_date DATE NOT NULL,
    status TEXT NOT NULL,
    valid_time TIMESTAMPTZ NOT NULL,
    system_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (instrument_id, valid_time)
);

-- sql/008_market_data.sql
CREATE TABLE market_data (
    snapshot_id TEXT PRIMARY KEY,
    instrument_id TEXT NOT NULL,
    value DECIMAL NOT NULL,
    confidence TEXT NOT NULL CHECK (confidence IN ('Firm','Quoted','Derived')),
    confidence_payload JSONB NOT NULL,
    attestation_ref TEXT NOT NULL,
    valid_time TIMESTAMPTZ NOT NULL,
    system_time TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_market_data_instrument ON market_data (instrument_id, valid_time DESC);

-- sql/009_reports_emir.sql
CREATE TABLE reports_emir (
    report_id TEXT PRIMARY KEY,
    uti TEXT NOT NULL,
    trade_ref TEXT NOT NULL,
    report_payload JSONB NOT NULL,
    attestation_ref TEXT NOT NULL,
    valid_time TIMESTAMPTZ NOT NULL,
    system_time TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Kafka topics (add to config.py):**

| Topic | Purpose | Partition Key |
|-------|---------|--------------|
| `attestor.gateway.orders` | Normalised equity orders | instrument_id |
| `attestor.ledger.transactions` | Committed transactions | tx_id |
| `attestor.oracle.equity_prices` | Equity price attestations | instrument_id |
| `attestor.reporting.emir` | EMIR report events | uti |
| `attestor.lifecycle.events` | Lifecycle state transitions | instrument_id |

**Tests:** Verify SQL syntax, verify topic configs

**Expected:** ~150 LOC SQL, ~50 LOC config changes, ~50 LOC tests, ~5 tests

### Step 12: Commutativity Tests

**Create:** `tests/test_commutativity.py`

**Contents:**
- **CS-02 (Master Square):** `stub_price(book(trade)) == book(stub_price(trade))` — booking then "pricing" (stub) equals "pricing" then booking. Both paths produce the same ledger state.
- **CS-04 (Reporting Naturality):** `report(lifecycle(I)) == report_update(report(I), lifecycle_event)` — EMIR report from booked trade equals EMIR report from raw order.
- **CS-05 (Lifecycle-Booking Naturality):** `book(f ; g) == book(f) ; book(g)` — booking the composition of two lifecycle events equals composing two bookings.
- **Property-based commutativity:** For random valid orders, both paths produce identical reports (Hypothesis).

**Tests:**
- test_master_square_equity_buy
- test_master_square_equity_sell
- test_reporting_naturality_equity
- test_lifecycle_booking_naturality
- test_commutativity_property_based (Hypothesis, 200 examples)

**Expected:** ~300 LOC tests, ~8 tests

### Step 13: Conservation Law Tests

**Create:** `tests/test_conservation_laws.py`

**Contents:**
- **CL-A1 (Balance Conservation):** Hypothesis — generate random transaction, execute, verify sigma(U) unchanged for all affected units.
- **CL-A2 (Double-Entry):** Every Transaction: sum(debits) == sum(credits) per unit.
- **CL-A5 (Deterministic Execution):** Same inputs produce same outputs across 100 runs.
- **Replay Determinism:** Execute sequence, clone, replay, compare positions.

**Create:** `tests/test_replay.py`

**Contents:**
- Replay from transaction log produces identical ledger state
- Clone at t, replay from log, states match

**Expected:** ~250 LOC tests, ~12 tests

### Step 14: Integration + CI Update

**Create:** `tests/test_integration_lifecycle.py`

**Contents:**
- Full lifecycle test: raw order → parse → book → settle → dividend → EMIR report
- Verify every step produces correct state
- Verify all conservation laws hold throughout
- Verify commutativity at each checkpoint

**Update:** `.github/workflows/ci.yml`
- Add Phase 1 import smoke test (all new types importable)
- Extend `no raise` allowed set if needed
- Extend `no float` exclusions if needed

**Update:** `tests/conftest.py`
- Add Hypothesis strategies for Phase 1 types: canonical_orders, instruments, parties, etc.

**Expected:** ~300 LOC tests, ~100 LOC conftest additions, ~10 tests

---

## 7. Acceptance Criteria (from PLAN.md Section 8)

All criteria from PLAN.md, with implementation mapping:

| # | Criterion | Test File | Invariant |
|---|-----------|-----------|-----------|
| 1 | Gateway: raw dict in, CanonicalOrder out, published to Kafka topic | test_gateway_parser | INV-G01, G02 |
| 2 | Ledger: equity trade booked as balanced double-entry transaction | test_ledger_engine | INV-L01, L05 |
| 3 | Ledger: T+2 settlement with cash and securities transfer (4 balance changes) | test_settlement | INV-L04 |
| 4 | Ledger: dividend processing (ex-date record, cash payment as transaction) | test_dividends | INV-L01 |
| 5 | Ledger: position queries by account and instrument in O(1) | test_ledger_engine | INV-L06 |
| 6 | Ledger: Clone + Unwind produces identical state at historical point | test_replay | INV-L09 |
| 7 | Oracle: equity price attestations with Firm (fill) or Quoted (market) | test_oracle_ingest | INV-O01, O04 |
| 8 | Reporting: EMIR trade report as projection from canonical instrument state | test_reporting_emir | INV-R01 |
| 9 | Reporting commutativity: `report(normalize(raw)) == report(attest(normalize(raw)))` | test_commutativity | INV-R02 |
| 10 | Conservation laws INV-L01 through INV-L05 with property-based tests | test_conservation_laws | CL-A1, A2 |
| 11 | Master Square with stub Pillar V | test_commutativity | CS-02 |
| 12 | Every attestation is content-hash verified | test_oracle_ingest | INV-R05 |
| 13 | Replay: wipe state, replay log, identical positions | test_replay | INV-R04 |
| 14 | mypy --strict, ruff clean, 0 Any in domain, all frozen | CI pipeline | INV-L10 |

---

## 8. Dependency Graph

```
Step 1: Gateway Types ──────────────> Step 2: Gateway Parser
                                          │
Step 3: Instrument Types ─────────────────┤
                                          │
Step 4: Lifecycle ────────────────────────┤
                                          │
                                          v
                               Step 5: Ledger Engine ──> Step 6: Settlement
                                          │                    │
                                          │                    v
                                          ├──────────> Step 7: Dividends
                                          │
Step 8: Oracle Ingest ────────────────────┤
                                          │
                               Step 9: EMIR Reporting ─> Step 10: Stub Update
                                          │
                                          v
                               Step 11: Kafka + SQL
                                          │
                                          v
                               Step 12: Commutativity Tests
                                          │
                                          v
                               Step 13: Conservation Tests
                                          │
                                          v
                               Step 14: Integration + CI
```

**Parallelizable:** Steps 1, 3, 8 can run concurrently. Steps 4 depends on 3. Step 5 depends on 1, 3, 4. Steps 6, 7 depend on 5. Step 9 depends on 1, 3. Steps 12-14 depend on all prior steps.

---

## 9. Estimated Test Counts

| Test File | Tests | Type |
|-----------|:---:|------|
| test_gateway_types | 8 | Unit |
| test_gateway_parser | 12 | Unit + property |
| test_instrument_types | 10 | Unit |
| test_lifecycle | 15 | Unit |
| test_ledger_engine | 25 | Unit + property |
| test_settlement | 12 | Unit + integration |
| test_dividends | 8 | Unit |
| test_oracle_ingest | 10 | Unit |
| test_reporting_emir | 10 | Unit |
| test_commutativity | 8 | Cross-pillar |
| test_conservation_laws | 12 | Property-based |
| test_replay | 5 | Integration |
| test_integration_lifecycle | 10 | End-to-end |
| conftest.py additions | 0 | (strategies only) |
| **Phase 1 new tests** | **~145** | |
| **Phase 0 existing** | **341** | |
| **Total** | **~486** | |

---

## 10. Non-Negotiable Constraints

1. **No float in domain.** All arithmetic is `Decimal` under `ATTESTOR_DECIMAL_CONTEXT`. CI enforces.
2. **No raise in domain.** All errors are `Result` values. CI AST scan enforces.
3. **All dataclasses frozen.** `@final @dataclass(frozen=True, slots=True)`. CI enforces.
4. **No Any in domain types.** mypy `--strict` enforces. `LedgerEngine` is NOT a dataclass (it has mutable internal state) — it's a `@final` class with typed `__init__`.
5. **Every attestation is content-addressed.** `attestation_id = SHA-256(canonical_bytes(full_identity))`.
6. **Append-only.** No transaction is ever modified. No attestation is ever deleted.
7. **Conservation law holds at every step.** `sigma(U)` checked before and after every `execute()`.

---

## 11. Open Design Decisions (Resolved Here)

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | LedgerEngine: class or frozen dataclass? | `@final` class with mutable `__init__` state | Engine needs mutable balance dict for O(1) lookups. Not a domain value — it's a service. |
| 2 | Settlement: 2 moves or 4 moves? | 2 Moves (each Move has source→dest, creating 4 balance changes) | Matches Move semantics: one Move = one transfer. Cash and securities are separate Moves. |
| 3 | PositionStatusEnum: in ledger/ or instrument/? | `instrument/lifecycle.py` | Status belongs to instrument lifecycle, not ledger accounting. |
| 4 | PrimitiveInstruction: full 9-variant or Phase 1 subset? | Phase 1 subset: ExecutePI, TransferPI, DividendPI | YAGNI. Phase 2 adds option/futures variants. |
| 5 | EconomicTerms.payout type: union or single? | Single `EquityPayoutSpec` in Phase 1 | Becomes `EquityPayoutSpec \| OptionPayoutSpec \| ...` in Phase 2. |
| 6 | Settlement date calculation: business day calendar? | Simple weekend skip for Phase 1 | Full business day calendar (holidays) deferred to Phase 2. |
| 7 | EMIR UTI generation: from content hash | `UTI.parse(content_hash[:52])` — deterministic from order content | Ensures same order always produces same UTI. |

---

## 12. Build Timeline

| Step | Description | Estimated Tests |
|------|-------------|:---:|
| 1 | Gateway Types | 8 |
| 2 | Gateway Parser | 12 |
| 3 | Instrument Types | 10 |
| 4 | Lifecycle State Machine | 15 |
| 5 | Ledger Engine | 25 |
| 6 | Settlement T+2 | 12 |
| 7 | Dividend Processing | 8 |
| 8 | Oracle Equity Ingestion | 10 |
| 9 | EMIR Reporting | 10 |
| 10 | Stub Pricing Update | 3 |
| 11 | Kafka Topics + SQL DDL | 5 |
| 12 | Commutativity Tests | 8 |
| 13 | Conservation Law Tests | 12 |
| 14 | Integration + CI | 10 |
| **Total** | | **~148** |

---

*"A type is a proposition. A value is a proof. The conservation law is the theorem. The test is the witness."*

*— Attestor Committee, Phase 1*

---

*End of Phase 1 Plan.*
