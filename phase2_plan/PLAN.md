# Attestor Phase 2 -- Listed Derivatives (Revised)

## Committee Review Status

| Reviewer | Verdict | Key conditions |
|----------|---------|----------------|
| Minsky (Chair) | CONDITIONAL PASS | EquityDetail marker; enums not strings; MiFIDII discriminated union |
| Formalis (Veto) | CONDITIONAL PASS | Position booking at trade time; remove settlement_price from physical exercise; zero margin returns Err |
| Geohot | SHIP with cuts | Merge files; kill scenarios.sql; one transition table |
| FinOps | APPROVED w/ conditions | OTM exercise guard; SQL schema prefix; GL trial balance |
| Gatheral | PASS w/ findings | settlement_type on PayoutSpec; last_trading_date on futures; optional implied vol |

All findings incorporated below.

---

## Scope

Equity options (calls/puts) and listed futures. Instrument model, lifecycle,
ledger booking, margin accounting, and reporting. NO pricing implementation --
Pillar V stubs return hard-coded or Oracle-observed values. Reporting extended
to MiFID II.

**Products:** Vanilla equity options (European/American calls and puts), listed
equity futures.

**Lifecycle stages:** Trade + position open, Premium exchange, Exercise/Assignment,
Expiry, Margin call, Settlement.

---

## Parametric Polymorphism Proof

Phase 2 proves Manifesto Principle V: adding options and futures does NOT modify
the core ledger engine. `LedgerEngine.execute()` operates on `Transaction` and
`Move` -- instrument-agnostic types.

**Files that MUST NOT be modified:** `attestor/ledger/engine.py`

---

## Phase 1 Cleanup (Step 0 prerequisite)

### Formalis HIGH findings
- **F-HIGH-01**: `Move.create()` factory returning `Err` when `source == destination`.
- **F-HIGH-02**: `Transaction.create()` factory returning `Err` when `moves` is empty.

### Minsky findings -- Promote bare `str` to `NonEmptyStr`
- `Move.source`, `Move.destination`, `Move.unit`, `Move.contract_id` -> `NonEmptyStr`
- `Transaction.tx_id` -> `NonEmptyStr`

### Lattner re-export gaps
- `attestor/reporting/__init__.py` -- re-export `EMIRTradeReport`, `project_emir_report`.
- `attestor/infra/__init__.py` -- re-export Phase 1 topic constants.
- `attestor/oracle/__init__.py` -- re-export `MarketDataPoint`, `ingest_equity_fill`, `ingest_equity_quote`.

### Gatheral findings
- **ISO 4217 validation**: `VALID_CURRENCIES` frozenset in `core/money.py`. Wire into `Money.create()`.
- **Money.abs()**: Add `abs() -> Money` method.

### Business day calendar
- New file: `attestor/core/calendar.py`
- `add_business_days(start: date, days: int) -> date` -- extract from `gateway/parser.py`.

### FinOps finding
- `sql/005_positions.sql`: Add `prevent_mutation()` trigger.

---

## Build Protocol (same as Phase 1)

1. Write source file(s)
2. `mypy --strict attestor/ tests/` -- clean
3. `ruff check attestor/ tests/` -- clean
4. Write test file(s)
5. `pytest tests/` -- green
6. Verify: no `float` in domain, no bare `raise` in domain
7. Next step

**Convention (Minsky F4):** Every `match` on `PrimitiveInstruction` in production
code must end with `case _ as unreachable: assert_never(unreachable)`.

---

## Step 1 -- Derivative Instrument Types

### New file: `attestor/instrument/derivative_types.py`

```python
class OptionType(Enum):
    CALL = "CALL"
    PUT = "PUT"

class OptionStyle(Enum):
    EUROPEAN = "EUROPEAN"
    AMERICAN = "AMERICAN"

class SettlementType(Enum):       # [Minsky F2, Formalis H-03, Gatheral G-HIGH-01]
    PHYSICAL = "PHYSICAL"
    CASH = "CASH"

class MarginType(Enum):           # [Minsky F2, Formalis H-03]
    VARIATION = "VARIATION"
    INITIAL = "INITIAL"

@final @dataclass(frozen=True, slots=True)
class OptionPayoutSpec:
    underlying_id: NonEmptyStr
    strike: PositiveDecimal
    expiry_date: date
    option_type: OptionType
    option_style: OptionStyle
    settlement_type: SettlementType  # [Gatheral G-HIGH-01: contract-level]
    currency: NonEmptyStr
    exchange: NonEmptyStr
    multiplier: PositiveDecimal      # typically 100

    @staticmethod
    def create(...) -> Ok[OptionPayoutSpec] | Err[str]: ...

@final @dataclass(frozen=True, slots=True)
class FuturesPayoutSpec:
    underlying_id: NonEmptyStr
    expiry_date: date
    last_trading_date: date          # [Gatheral G-HIGH-02]
    settlement_type: SettlementType  # [Gatheral G-HIGH-02]
    contract_size: PositiveDecimal   # point value (USD per unit of price)
    currency: NonEmptyStr
    exchange: NonEmptyStr

    @staticmethod
    def create(...) -> Ok[FuturesPayoutSpec] | Err[str]: ...
    # Validation: last_trading_date <= expiry_date

# [Minsky F1: explicit EquityDetail, not None]
@final @dataclass(frozen=True, slots=True)
class EquityDetail:
    """Marker type for equity orders. No extra fields needed."""
    pass

@final @dataclass(frozen=True, slots=True)
class OptionDetail:
    strike: PositiveDecimal
    expiry_date: date
    option_type: OptionType
    option_style: OptionStyle
    settlement_type: SettlementType
    underlying_id: NonEmptyStr
    multiplier: PositiveDecimal

    @staticmethod
    def create(...) -> Ok[OptionDetail] | Err[str]: ...

@final @dataclass(frozen=True, slots=True)
class FuturesDetail:
    expiry_date: date
    contract_size: PositiveDecimal
    settlement_type: SettlementType
    underlying_id: NonEmptyStr

    @staticmethod
    def create(...) -> Ok[FuturesDetail] | Err[str]: ...

InstrumentDetail = EquityDetail | OptionDetail | FuturesDetail
```

No separate `gateway/derivative_detail.py` -- [Geohot CUT 1: one file, no parallel hierarchy].

tick_size/tick_value removed from FuturesPayoutSpec -- [Geohot CUT 2: exchange microstructure, not economics].

### Modify: `attestor/instrument/types.py`

```python
Payout = EquityPayoutSpec | OptionPayoutSpec | FuturesPayoutSpec
```

Change `EconomicTerms.payout` from `EquityPayoutSpec` to `Payout`.

Add `create_option_instrument()` and `create_futures_instrument()` factories.

### Tests: `tests/test_derivative_types.py` (~15 tests)

---

## Step 2 -- Gateway Extension

### Modify: `attestor/gateway/types.py`

```python
# [Minsky F1: InstrumentDetail, not None]
instrument_detail: InstrumentDetail = EquityDetail()
```

Default `EquityDetail()` is backward compatible -- ALL existing tests and code
work without modification. Every `match` on `instrument_detail` handles three
explicit variants. mypy catches missing branches.

Update `CanonicalOrder.create()`:
- Accept `instrument_detail: InstrumentDetail = EquityDetail()`
- If `OptionDetail`: verify `expiry_date > trade_date`
- If `FuturesDetail`: verify `expiry_date > trade_date`

### Modify: `attestor/gateway/parser.py`

Add `parse_option_order()` and `parse_futures_order()`.
- Options: T+1 settlement (premium). Exercise settlement computed separately.
  [FinOps C3: CanonicalOrder.settlement_date = premium settlement. Exercise
  settlement date computed in create_exercise_transaction using core/calendar.]
- Futures: T+0 settlement.

### Tests: `tests/test_gateway_derivatives.py` (~12 tests)

---

## Step 3 -- Lifecycle Extension

### Modify: `attestor/instrument/lifecycle.py`

```python
@final @dataclass(frozen=True, slots=True)
class ExercisePI:
    order: CanonicalOrder
    # settlement_type comes from order.instrument_detail.settlement_type
    # [Gatheral: contract-level, not exercise-level]

@final @dataclass(frozen=True, slots=True)
class AssignPI:
    order: CanonicalOrder

@final @dataclass(frozen=True, slots=True)
class ExpiryPI:
    instrument_id: NonEmptyStr
    expiry_date: date

@final @dataclass(frozen=True, slots=True)
class MarginPI:
    instrument_id: NonEmptyStr
    margin_amount: Money
    margin_type: MarginType  # [enum, not str]

PrimitiveInstruction = (
    ExecutePI | TransferPI | DividendPI
    | ExercisePI | AssignPI | ExpiryPI | MarginPI
)
```

Transition table: [Geohot CUT 4: one table since edges are identical]
`check_transition()` gets optional `transitions` parameter defaulting to
`EQUITY_TRANSITIONS`. Body changes from hardcoded to parameterized.

### Tests: `tests/test_lifecycle_derivatives.py` (~15 tests)

---

## Step 4 -- Option Ledger (premium + position open)

### New file: `attestor/ledger/options.py`

[Geohot CUT 3: one file for all option ledger functions]

```python
def create_premium_transaction(
    order: CanonicalOrder,
    buyer_cash_account: str,
    seller_cash_account: str,
    buyer_position_account: str,     # [Formalis C-01, H-01: book position too]
    seller_position_account: str,
    tx_id: str,
) -> Ok[Transaction] | Err[ValidationError]:
    """Option trade: premium payment AND position opening.

    Premium = price * quantity * multiplier
    Move 1: Cash (premium) buyer -> seller
    Move 2: Option position (qty) seller -> buyer  [Formalis: derivative position]
    Unit for position Move = contract identifier (e.g. "OPT-AAPL-CALL-150-2025-09-19")
    """

def create_exercise_transaction(
    order: CanonicalOrder,
    holder_cash_account: str,
    holder_securities_account: str,
    writer_cash_account: str,
    writer_securities_account: str,
    holder_position_account: str,
    writer_position_account: str,
    tx_id: str,
    # [Formalis C-02: NO settlement_price for physical exercise]
) -> Ok[Transaction] | Err[ValidationError]:
    """Physical exercise: close option position + deliver underlying.

    Validation: [FinOps C1, Gatheral G-MEDIUM-02]
      - order.instrument_detail must be OptionDetail
      - order.instrument_detail.settlement_type must be PHYSICAL

    CALL exercise:
      Move 1: Cash (strike * qty * multiplier) holder -> writer
      Move 2: Securities (qty * multiplier) writer -> holder
      Move 3: Option position (qty) holder -> writer  [close position]

    PUT exercise:
      Move 1: Securities (qty * multiplier) holder -> writer
      Move 2: Cash (strike * qty * multiplier) writer -> holder
      Move 3: Option position (qty) holder -> writer  [close position]
    """

def create_cash_settlement_exercise_transaction(
    order: CanonicalOrder,
    holder_cash_account: str,
    writer_cash_account: str,
    holder_position_account: str,
    writer_position_account: str,
    tx_id: str,
    settlement_price: Decimal,
) -> Ok[Transaction] | Err[ValidationError]:
    """Cash-settled exercise.

    Validation: [FinOps C1, Gatheral G-MEDIUM-02]
      - CALL: reject if settlement_price <= strike (OTM)
      - PUT: reject if settlement_price >= strike (OTM)

    CALL: writer pays (settlement_price - strike) * qty * multiplier to holder
    PUT: writer pays (strike - settlement_price) * qty * multiplier to holder
    + Move to close option position (holder -> writer)
    """

def create_expiry_transaction(
    instrument_id: str,
    holder_position_account: str,
    writer_position_account: str,
    quantity: Decimal,
    contract_unit: str,        # e.g. "OPT-AAPL-CALL-150-2025-09-19"
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """OTM expiry: close derivative position, no cash movement.

    [Formalis C-01 resolved: position was opened in create_premium_transaction,
    now we reverse it]

    Move 1: Option position (qty) holder -> writer  [close position]
    sigma(contract_unit) returns to 0.
    """
```

### Tests: `tests/test_options.py` (~20 tests)

- Premium: cash + position opened (2 Moves)
- Premium conservation: sigma(cash) == 0, sigma(option_position) == 0
- Exercise CALL physical: holder gets shares, pays strike, position closed
- Exercise PUT physical: holder delivers shares, receives cash, position closed
- Exercise conservation: sigma(cash) == 0, sigma(securities) == 0, sigma(option) == 0
- Cash settlement CALL: holder receives intrinsic value, position closed
- Cash settlement PUT: holder receives intrinsic value, position closed
- OTM exercise rejected: CALL with settlement <= strike returns Err
- OTM exercise rejected: PUT with settlement >= strike returns Err
- Expiry: position closed, no cash, sigma(option) returns to 0
- Reject non-option order
- Property-based: random (price, qty, strike, multiplier) -> conservation holds

---

## Step 5 -- Futures Ledger

### New file: `attestor/ledger/futures.py`

```python
def create_futures_open_transaction(
    instrument_id: str,
    long_position_account: str,
    short_position_account: str,
    quantity: Decimal,
    contract_unit: str,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Open futures position at trade time.

    [Formalis H-02: explicit position opening]
    Move: position (qty) short -> long
    No cash exchange at trade time for futures.
    """

def create_variation_margin_transaction(
    instrument_id: str,
    long_margin_account: str,
    short_margin_account: str,
    settlement_price: Decimal,
    previous_settlement_price: Decimal,
    contract_size: Decimal,       # point value
    quantity: Decimal,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[str]:
    """Daily variation margin settlement.

    margin_flow = (settlement_price - previous_settlement_price) * contract_size * quantity

    If positive: short pays long.
    If negative: long pays short.

    [Formalis C-03: if margin_flow == 0, return Err("No margin flow: prices unchanged")]
    """

def create_futures_expiry_transaction(
    instrument_id: str,
    long_cash_account: str,
    short_cash_account: str,
    long_position_account: str,
    short_position_account: str,
    final_settlement_price: Decimal,
    last_margin_price: Decimal,
    contract_size: Decimal,
    quantity: Decimal,
    contract_unit: str,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Futures expiry: final margin settlement + close position.

    Move 1: Final margin (same formula as variation margin)
    Move 2: Position close (long -> short)
    [If final margin is zero, only position close Move is produced]
    """
```

### Tests: `tests/test_futures.py` (~15 tests)

- Futures open: position created (1 Move)
- Variation margin: price up -> short pays long
- Variation margin: price down -> long pays short
- Variation margin: price unchanged -> returns Err [Formalis C-03]
- Conservation: sigma(USD) == 0 after margin
- Futures expiry: final settlement + position closed
- Multi-day: 3 margins + expiry -> cumulative == (final - initial) * size * qty
- Property-based: random price sequences -> conservation holds

---

## Step 6 -- GL Projection

### New file: `attestor/ledger/gl_projection.py`

```python
class GLAccountType(Enum):  # [FinOps C5]
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"

@final @dataclass(frozen=True, slots=True)
class GLEntry:
    gl_account: NonEmptyStr
    gl_account_type: GLAccountType
    instrument_id: NonEmptyStr
    debit_total: Decimal
    credit_total: Decimal

@final @dataclass(frozen=True, slots=True)
class GLProjection:
    entries: tuple[GLEntry, ...]
    as_of: UtcDatetime

    def trial_balance(self) -> Ok[Decimal] | Err[str]:
        """INV-GL-01: sum(debits) == sum(credits). Returns Err if unbalanced."""

@final @dataclass(frozen=True, slots=True)
class GLAccountMapping:
    mappings: FrozenMap[str, tuple[str, GLAccountType]]
    # sub-ledger account_id -> (GL code, GL account type)

def project_gl(engine: LedgerEngine, mapping: GLAccountMapping) -> GLProjection:
    """INV-17: Pure projection. No state mutation."""
```

### Tests: `tests/test_gl_projection.py` (~10 tests)

- INV-17: sub-ledger totals == GL totals
- Trial balance: debits == credits
- Empty engine -> empty projection
- Multiple instruments: correct aggregation

---

## Step 7 -- Oracle Derivative Ingest

### New file: `attestor/oracle/derivative_ingest.py`

```python
@final @dataclass(frozen=True, slots=True)
class OptionQuote:
    instrument_id: NonEmptyStr
    underlying_id: NonEmptyStr
    strike: Decimal
    expiry_date: date
    option_type: OptionType
    bid: Decimal
    ask: Decimal
    implied_vol_bid: Decimal | None   # [Gatheral G-MEDIUM-01: forward compat]
    implied_vol_ask: Decimal | None
    currency: NonEmptyStr
    timestamp: UtcDatetime

@final @dataclass(frozen=True, slots=True)
class FuturesSettlement:
    instrument_id: NonEmptyStr
    settlement_price: Decimal
    currency: NonEmptyStr
    settlement_date: date
    timestamp: UtcDatetime

def ingest_option_quote(...) -> Ok[Attestation[OptionQuote]] | Err[str]:
    """QuotedConfidence (bid/ask spread)."""

def ingest_futures_settlement(...) -> Ok[Attestation[FuturesSettlement]] | Err[str]:
    """FirmConfidence."""
```

### Tests: `tests/test_oracle_derivatives.py` (~12 tests)

---

## Step 8 -- MiFID II Reporting

### New file: `attestor/reporting/mifid2.py`

```python
# [Minsky F3: discriminated union for instrument-specific fields]
@final @dataclass(frozen=True, slots=True)
class OptionReportFields:
    strike: Decimal
    expiry_date: date
    option_type: OptionType
    option_style: OptionStyle

@final @dataclass(frozen=True, slots=True)
class FuturesReportFields:
    expiry_date: date
    contract_size: Decimal

InstrumentReportFields = OptionReportFields | FuturesReportFields | None
# None = equity (no extra fields)

@final @dataclass(frozen=True, slots=True)
class MiFIDIIReport:
    transaction_ref: NonEmptyStr
    reporting_entity_lei: LEI
    counterparty_lei: LEI
    instrument_id: NonEmptyStr
    isin: ISIN | None
    instrument_fields: InstrumentReportFields  # [Minsky F3]
    direction: OrderSide
    quantity: PositiveDecimal
    price: Decimal
    currency: NonEmptyStr
    trade_date: date
    settlement_date: date
    venue: NonEmptyStr
    report_timestamp: UtcDatetime
    attestation_refs: tuple[str, ...]

def project_mifid2_report(
    order: CanonicalOrder,
    trade_attestation_id: str,
) -> Ok[Attestation[MiFIDIIReport]] | Err[str]:
    """INV-R01: pure projection from order. Booking does not affect report."""
```

### Tests: `tests/test_reporting_mifid2.py` (~10 tests)

---

## Step 9 -- Pricing Stub Extension

No changes needed to `StubPricingEngine` -- it already accepts any instrument_id.

### Tests: `tests/test_pricing_derivatives.py` (~6 tests)
- Stub returns oracle_price for option/futures IDs
- All-zero Greeks for derivatives
- Master Square stub holds

---

## Step 10 -- Infrastructure (Kafka + SQL)

### Modify: `attestor/infra/config.py`

5 new topics: `TOPIC_DERIVATIVE_ORDERS`, `TOPIC_OPTION_PRICES`,
`TOPIC_FUTURES_SETTLEMENTS`, `TOPIC_MIFID2_REPORTS`, `TOPIC_MARGIN_EVENTS`.

### New SQL files (3, not 4 -- [Geohot CUT 5: scenarios.sql cut])

All tables use `attestor.` schema prefix [FinOps C4].

**`sql/010_margin_accounts.sql`** -- append-only margin event log [FinOps C4b]:
```sql
CREATE TABLE attestor.margin_events (
    event_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    margin_type TEXT NOT NULL CHECK (margin_type IN ('INITIAL', 'VARIATION')),
    margin_flow DECIMAL NOT NULL,
    instrument_id TEXT NOT NULL,
    valid_time TIMESTAMPTZ NOT NULL,
    system_time TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER prevent_margin_events_mutation
    BEFORE UPDATE OR DELETE ON attestor.margin_events
    FOR EACH ROW EXECUTE FUNCTION prevent_mutation();
```

**`sql/011_gl_projection.sql`**:
```sql
CREATE TABLE attestor.gl_projection (
    gl_account TEXT NOT NULL,
    gl_account_type TEXT NOT NULL CHECK (gl_account_type IN ('ASSET','LIABILITY','EQUITY','REVENUE','EXPENSE')),
    instrument_id TEXT NOT NULL,
    debit_total DECIMAL NOT NULL DEFAULT 0,
    credit_total DECIMAL NOT NULL DEFAULT 0,
    valid_time TIMESTAMPTZ NOT NULL,
    system_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (gl_account, instrument_id, valid_time)
);
CREATE TRIGGER prevent_gl_projection_mutation
    BEFORE UPDATE OR DELETE ON attestor.gl_projection
    FOR EACH ROW EXECUTE FUNCTION prevent_mutation();
```

**`sql/012_reports_mifid2.sql`**:
```sql
CREATE TABLE attestor.reports_mifid2 (
    report_id TEXT PRIMARY KEY,
    trade_ref TEXT NOT NULL,
    instrument_type TEXT NOT NULL CHECK (instrument_type IN ('EQUITY', 'OPTION', 'FUTURE')),
    report_payload JSONB NOT NULL,
    content_hash TEXT NOT NULL,
    valid_time TIMESTAMPTZ NOT NULL,
    system_time TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER prevent_mifid2_mutation
    BEFORE UPDATE OR DELETE ON attestor.reports_mifid2
    FOR EACH ROW EXECUTE FUNCTION prevent_mutation();
```

### Tests: `tests/test_infra_phase2.py` (~10 tests)

---

## Step 11 -- Derivative Invariant Tests

### New file: `tests/test_invariants_derivatives.py`

[Geohot CUT 6: merged conservation + commutativity into one file]

Conservation laws:
- **CL-D1** (Hypothesis 200): premium -> sigma(cash) == 0, sigma(option_pos) == 0
- **CL-D2**: exercise -> sigma(cash) == 0, sigma(sec) == 0, sigma(option_pos) == 0
- **CL-D3**: expiry -> sigma(option_pos) returns to 0
- **CL-D4** (Hypothesis 200): variation margin -> sigma(USD) == 0
- **CL-D5**: full option lifecycle (premium + exercise) -> all sigmas == 0
- **CL-D6**: full futures lifecycle (open + 3 margins + expiry) -> cumulative correct
- **INV-17**: GL projection totals == sub-ledger totals

Commutativity:
- **CS-D1**: option Master Square (book then price == price then book)
- **CS-D2**: futures Master Square
- **CS-D3**: MiFID II naturality (report before/after booking identical)
- **CS-D4**: sequential option bookings compose
- **CS-D5**: sequential futures margins compose
- **Property-based** (Hypothesis 200): random (price, qty, strike) Master Square

**Expected test count: ~20**

---

## Step 12 -- Integration Tests + CI Green

### New file: `tests/test_integration_derivatives.py`

**Full option lifecycle (end-to-end):**
1. Parse option order (Gateway) with OptionDetail
2. Create option instrument with OptionPayoutSpec
3. Oracle attests option quote (QuotedConfidence)
4. Book premium + open position (2 Moves)
5. Lifecycle: PROPOSED -> FORMED -> SETTLED
6. Exercise option (physical: 3 Moves; or cash: 2 Moves)
7. Lifecycle: SETTLED -> CLOSED
8. Stub pricing returns oracle price
9. MiFID II report generated
10. All conservation laws hold
11. Idempotency: replay = ALREADY_APPLIED

**Full futures lifecycle (end-to-end):**
1. Parse futures order with FuturesDetail
2. Create futures instrument with FuturesPayoutSpec
3. Open position (1 Move)
4. Oracle attests settlement prices (FirmConfidence)
5. Day 1-2: variation margin settlements
6. Day 3: futures expiry (final margin + close position)
7. Lifecycle: SETTLED -> CLOSED
8. Conservation: cumulative margin == (final - initial) * size * qty
9. MiFID II report generated
10. Idempotency

**Import smoke tests** for all new types.

**Expected test count: ~20**

---

## File Summary

### New production files (10):
| # | File | Purpose |
|---|------|---------|
| 1 | `attestor/core/calendar.py` | Business day calendar |
| 2 | `attestor/instrument/derivative_types.py` | All derivative types + enums + InstrumentDetail |
| 3 | `attestor/ledger/options.py` | Premium, exercise, expiry |
| 4 | `attestor/ledger/futures.py` | Open, variation margin, futures expiry |
| 5 | `attestor/ledger/gl_projection.py` | Sub-ledger to GL projection |
| 6 | `attestor/oracle/derivative_ingest.py` | Option quotes, futures settlements |
| 7 | `attestor/reporting/mifid2.py` | MiFID II reporting |
| 8 | `sql/010_margin_events.sql` | Margin events DDL |
| 9 | `sql/011_gl_projection.sql` | GL projection DDL |
| 10 | `sql/012_reports_mifid2.sql` | MiFID II reports DDL |

### Modified production files (8):
| # | File | Change |
|---|------|--------|
| 1 | `attestor/ledger/transactions.py` | Move.create(), Transaction.create() (Step 0) |
| 2 | `attestor/core/money.py` | ISO 4217, Money.abs() (Step 0) |
| 3 | `attestor/instrument/types.py` | Payout union (Step 1) |
| 4 | `attestor/instrument/__init__.py` | Re-exports (Step 1) |
| 5 | `attestor/instrument/lifecycle.py` | New PIs, check_transition param (Step 3) |
| 6 | `attestor/gateway/types.py` | instrument_detail field (Step 2) |
| 7 | `attestor/gateway/parser.py` | calendar import + derivative parsers (Step 2) |
| 8 | `attestor/infra/config.py` | Phase 2 topics (Step 10) |

### Cleanup (Step 0, 5 files):
| # | File | Change |
|---|------|--------|
| 1 | `attestor/reporting/__init__.py` | Re-export EMIR types |
| 2 | `attestor/oracle/__init__.py` | Re-export ingest types |
| 3 | `attestor/infra/__init__.py` | Re-export Phase 1 topics |
| 4 | `attestor/gateway/parser.py` | Use core/calendar.py |
| 5 | `sql/005_positions.sql` | Add prevent_mutation() trigger |

### New test files (11):
| # | File | Expected |
|---|------|---------|
| 1 | `tests/test_derivative_types.py` | ~15 |
| 2 | `tests/test_gateway_derivatives.py` | ~12 |
| 3 | `tests/test_lifecycle_derivatives.py` | ~15 |
| 4 | `tests/test_options.py` | ~20 |
| 5 | `tests/test_futures.py` | ~15 |
| 6 | `tests/test_gl_projection.py` | ~10 |
| 7 | `tests/test_oracle_derivatives.py` | ~12 |
| 8 | `tests/test_reporting_mifid2.py` | ~10 |
| 9 | `tests/test_pricing_derivatives.py` | ~6 |
| 10 | `tests/test_infra_phase2.py` | ~10 |
| 11 | `tests/test_invariants_derivatives.py` | ~20 |
| 12 | `tests/test_integration_derivatives.py` | ~20 |

**Total new tests: ~165. Total target: ~659.**

---

## Invariant Registry -- Phase 2

| ID | Name | Tested by |
|----|------|-----------|
| CL-D1 | Option premium conservation | test_invariants_derivatives |
| CL-D2 | Exercise conservation | test_invariants_derivatives |
| CL-D3 | Expiry conservation | test_invariants_derivatives |
| CL-D4 | Margin conservation | test_invariants_derivatives |
| CL-D5 | Option lifecycle conservation | test_invariants_derivatives |
| CL-D6 | Futures lifecycle conservation | test_invariants_derivatives |
| INV-17 | GL projection invariant | test_gl_projection |
| INV-GL-01 | Trial balance | test_gl_projection |
| CS-D1 | Option Master Square | test_invariants_derivatives |
| CS-D2 | Futures Master Square | test_invariants_derivatives |
| CS-D3 | MiFID II naturality | test_invariants_derivatives |
| CS-D4 | Option lifecycle naturality | test_invariants_derivatives |
| CS-D5 | Futures lifecycle naturality | test_invariants_derivatives |

---

## Acceptance Criteria

- [ ] Option premium + position opening booked as balanced transaction (2 Moves)
- [ ] Exercise produces correct entries (securities + cash + position close)
- [ ] OTM exercise rejected (intrinsic value <= 0)
- [ ] Expiry closes position, no cash movement
- [ ] Futures position opening booked explicitly
- [ ] Variation margin booked correctly; zero flow returns Err
- [ ] GL projection: sub-ledger totals == GL totals (INV-17)
- [ ] Trial balance: debits == credits (INV-GL-01)
- [ ] MiFID II report generated as projection
- [ ] Stub pricing extended for derivatives
- [ ] Commutativity tested with stubs
- [ ] Conservation laws hold through all derivative lifecycles
- [ ] `attestor/ledger/engine.py` NOT MODIFIED (parametric polymorphism proof)
