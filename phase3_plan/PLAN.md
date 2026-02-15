# Attestor Phase 3 -- FX and Rates (Multi-Currency Ledger)

## Committee Review Status

| Reviewer | Verdict | Key conditions |
|----------|---------|----------------|
| Minsky (Chair) | CONDITIONAL PASS | CurrencyPair refined type; DayCountConvention enum not string; IRS legs as sum type; no bare `dict` in YieldCurve |
| Formalis (Veto) | CONDITIONAL PASS | Yield curve D(0)=1 enforced at construction; arbitrage gates before release; cashflow conservation as Hypothesis property |
| Geohot | SHIP with cuts | Merge FX spot/forward detail into one FXDetail; one calibration.py not three files; oracle ingest in one file |
| FinOps | APPROVED w/ conditions | Multi-currency sigma per-unit conservation; NDF fixing at settlement; T+1 for FX spot; cashflow table with bitemporal columns |
| Gatheral | PASS w/ findings | Yield curve bootstrapping must pass AF-YC-01..05; triangular arbitrage tolerance configurable; DerivedConfidence on all calibrated outputs |

All findings incorporated below.

---

## Scope

FX spot/forward, NDF, and vanilla IRS (fixed-float). Multi-currency ledger
booking with per-currency conservation. Oracle extended with yield curve
bootstrapping and derived observables. NO pricing models -- yield curves are
Oracle (Pillar III) outputs consumed by Pillar V stubs.

**Products:** FX spot, FX forward, NDF (non-deliverable forward), vanilla IRS
(fixed-float).

**Lifecycle stages:** Trade, Fixing (FX/rate resets), Netting, Settlement,
Maturity.

**Deliverables:** II-06, II-07, III-04, III-06, III-07, III-08

---

## Parametric Polymorphism Proof

Phase 3 continues to prove Manifesto Principle V: adding FX and rates instruments
does NOT modify the core ledger engine. `LedgerEngine.execute()` operates on
`Transaction` and `Move` -- instrument-agnostic types. Multi-currency support
already works because `Move.unit` is a string that can be any currency code.

**Files that MUST NOT be modified:** `attestor/ledger/engine.py`

---

## Phase 2 Cleanup (Step 0 prerequisite)

### Gatheral finding -- CurrencyPair validation
- `attestor/core/money.py`: Add `CurrencyPair` refined type with ISO 4217
  validation on both legs. Format: `"EUR/USD"` (base/quote, slash-separated).
  Smart constructor: `CurrencyPair.parse(raw: str) -> Ok[CurrencyPair] | Err[str]`.

### FinOps finding -- Calendar T+1 for FX
- `attestor/core/calendar.py`: Ensure `add_business_days` supports T+1 (already
  does via `days=1`). No code change needed, just verify in tests.

### Minsky finding -- AccountType extension
- `attestor/ledger/transactions.py`: Add `ACCRUALS` to `AccountType` if not
  present (already present). Add `NETTING` account type for FX netting.

---

## Build Protocol (same as Phase 1/2)

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

## Step 1 -- FX and IRS Instrument Types

### New file: `attestor/instrument/fx_types.py`

```python
class DayCountConvention(Enum):
    ACT_360 = "ACT/360"
    ACT_365 = "ACT/365"
    THIRTY_360 = "30/360"

class PaymentFrequency(Enum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    SEMI_ANNUAL = "SEMI_ANNUAL"
    ANNUAL = "ANNUAL"

class SwapLegType(Enum):
    FIXED = "FIXED"
    FLOAT = "FLOAT"

@final @dataclass(frozen=True, slots=True)
class FXSpotPayoutSpec:
    """FX spot payout: exchange base_notional of base currency for quote amount."""
    currency_pair: CurrencyPair   # e.g. EUR/USD
    base_notional: PositiveDecimal
    settlement_type: SettlementType  # always PHYSICAL for spot
    currency: NonEmptyStr         # settlement currency (quote currency)

    @staticmethod
    def create(...) -> Ok[FXSpotPayoutSpec] | Err[str]: ...

@final @dataclass(frozen=True, slots=True)
class FXForwardPayoutSpec:
    """FX forward: exchange at agreed forward rate on future date."""
    currency_pair: CurrencyPair
    base_notional: PositiveDecimal
    forward_rate: PositiveDecimal  # agreed FX rate
    settlement_date: date
    settlement_type: SettlementType  # PHYSICAL or CASH (NDF)
    currency: NonEmptyStr

    @staticmethod
    def create(...) -> Ok[FXForwardPayoutSpec] | Err[str]: ...

@final @dataclass(frozen=True, slots=True)
class NDFPayoutSpec:
    """Non-deliverable forward: cash settled at fixing."""
    currency_pair: CurrencyPair
    base_notional: PositiveDecimal
    forward_rate: PositiveDecimal
    fixing_date: date
    settlement_date: date
    fixing_source: NonEmptyStr    # e.g. "WMR", "ECB"
    currency: NonEmptyStr         # settlement currency (freely tradeable leg)

    @staticmethod
    def create(...) -> Ok[NDFPayoutSpec] | Err[str]: ...

@final @dataclass(frozen=True, slots=True)
class FixedLeg:
    fixed_rate: PositiveDecimal   # e.g. 0.035 for 3.5%
    day_count: DayCountConvention
    payment_frequency: PaymentFrequency
    currency: NonEmptyStr
    notional: PositiveDecimal

@final @dataclass(frozen=True, slots=True)
class FloatLeg:
    float_index: NonEmptyStr      # e.g. "SOFR", "EURIBOR_3M"
    spread: Decimal               # basis point spread over index (can be 0)
    day_count: DayCountConvention
    payment_frequency: PaymentFrequency
    currency: NonEmptyStr
    notional: PositiveDecimal

@final @dataclass(frozen=True, slots=True)
class IRSwapPayoutSpec:
    """Vanilla IRS (fixed-float) payout specification."""
    fixed_leg: FixedLeg
    float_leg: FloatLeg
    start_date: date
    end_date: date
    currency: NonEmptyStr         # primary currency

    @staticmethod
    def create(...) -> Ok[IRSwapPayoutSpec] | Err[str]: ...
```

### Modify: `attestor/core/money.py`

Add `CurrencyPair` refined type:

```python
@final @dataclass(frozen=True, slots=True)
class CurrencyPair:
    """Validated FX currency pair, e.g. EUR/USD. base/quote format."""
    base: NonEmptyStr
    quote: NonEmptyStr

    @staticmethod
    def parse(raw: str) -> Ok[CurrencyPair] | Err[str]:
        parts = raw.split("/")
        if len(parts) != 2:
            return Err(f"CurrencyPair must be BASE/QUOTE, got '{raw}'")
        base_str, quote_str = parts[0].strip(), parts[1].strip()
        if not validate_currency(base_str):
            return Err(f"Invalid base currency: {base_str}")
        if not validate_currency(quote_str):
            return Err(f"Invalid quote currency: {quote_str}")
        if base_str == quote_str:
            return Err(f"Base and quote currencies must differ: {base_str}")
        # parse NonEmptyStr for both
        ...
        return Ok(CurrencyPair(base=..., quote=...))

    @property
    def value(self) -> str:
        return f"{self.base.value}/{self.quote.value}"
```

### Modify: `attestor/instrument/derivative_types.py`

Add gateway-level detail types:

```python
@final @dataclass(frozen=True, slots=True)
class FXDetail:
    """FX order detail — covers spot, forward, and NDF."""
    currency_pair: CurrencyPair
    forward_rate: PositiveDecimal | None  # None for spot
    settlement_date: date
    settlement_type: SettlementType
    fixing_source: NonEmptyStr | None     # non-None for NDF
    fixing_date: date | None              # non-None for NDF

    @staticmethod
    def create(...) -> Ok[FXDetail] | Err[str]: ...

@final @dataclass(frozen=True, slots=True)
class IRSwapDetail:
    """IRS order detail on a CanonicalOrder."""
    fixed_rate: PositiveDecimal
    float_index: NonEmptyStr
    day_count: DayCountConvention
    payment_frequency: PaymentFrequency
    tenor_months: int              # e.g. 60 for 5Y
    start_date: date
    end_date: date

    @staticmethod
    def create(...) -> Ok[IRSwapDetail] | Err[str]: ...

# Updated union:
type InstrumentDetail = EquityDetail | OptionDetail | FuturesDetail | FXDetail | IRSwapDetail
```

### Modify: `attestor/instrument/types.py`

Extend Payout union:

```python
type Payout = (
    EquityPayoutSpec | OptionPayoutSpec | FuturesPayoutSpec
    | FXSpotPayoutSpec | FXForwardPayoutSpec | NDFPayoutSpec | IRSwapPayoutSpec
)
```

Add factory functions: `create_fx_spot_instrument()`, `create_fx_forward_instrument()`,
`create_ndf_instrument()`, `create_irs_instrument()`.

### Tests: `tests/test_fx_types.py`

- CurrencyPair.parse valid/invalid
- FXSpotPayoutSpec.create valid/invalid
- FXForwardPayoutSpec.create valid/invalid
- NDFPayoutSpec.create valid/invalid, fixing_date <= settlement_date
- FixedLeg / FloatLeg construction
- IRSwapPayoutSpec.create valid/invalid, start_date < end_date
- FXDetail.create valid/invalid
- IRSwapDetail.create valid/invalid
- InstrumentDetail union exhaustiveness
- Payout union exhaustiveness
- Instrument factories: create_fx_spot_instrument, create_fx_forward_instrument, etc.
- All types frozen, slots, immutable

**Expected tests: ~40**

---

## Step 2 -- FX and IRS Lifecycle

### Modify: `attestor/instrument/lifecycle.py`

Add new PrimitiveInstruction variants:

```python
@final @dataclass(frozen=True, slots=True)
class FixingPI:
    """Rate fixing instruction (FX NDF fixing or IRS rate reset)."""
    instrument_id: NonEmptyStr
    fixing_date: date
    fixing_rate: Decimal           # observed fixing rate
    fixing_source: NonEmptyStr     # e.g. "WMR", "SOFR"

@final @dataclass(frozen=True, slots=True)
class NettingPI:
    """Netting instruction — aggregate offsetting FX positions."""
    instrument_ids: tuple[NonEmptyStr, ...]
    netting_date: date
    net_amount: Money

@final @dataclass(frozen=True, slots=True)
class MaturityPI:
    """Maturity instruction — IRS or FX forward reaching end of life."""
    instrument_id: NonEmptyStr
    maturity_date: date
```

Updated `PrimitiveInstruction`:

```python
PrimitiveInstruction = (
    ExecutePI | TransferPI | DividendPI
    | ExercisePI | AssignPI | ExpiryPI | MarginPI
    | FixingPI | NettingPI | MaturityPI
)
```

Add transition tables:

```python
FX_TRANSITIONS: TransitionTable = frozenset({
    (PositionStatusEnum.PROPOSED, PositionStatusEnum.FORMED),
    (PositionStatusEnum.PROPOSED, PositionStatusEnum.CANCELLED),
    (PositionStatusEnum.FORMED, PositionStatusEnum.SETTLED),
    (PositionStatusEnum.FORMED, PositionStatusEnum.CANCELLED),
    (PositionStatusEnum.SETTLED, PositionStatusEnum.CLOSED),
})

IRS_TRANSITIONS: TransitionTable = frozenset({
    (PositionStatusEnum.PROPOSED, PositionStatusEnum.FORMED),
    (PositionStatusEnum.PROPOSED, PositionStatusEnum.CANCELLED),
    (PositionStatusEnum.FORMED, PositionStatusEnum.SETTLED),     # active (formed -> settled on first payment)
    (PositionStatusEnum.FORMED, PositionStatusEnum.CANCELLED),
    (PositionStatusEnum.SETTLED, PositionStatusEnum.CLOSED),     # maturity
})
```

### Tests: `tests/test_lifecycle_fx_irs.py`

- FixingPI, NettingPI, MaturityPI frozen
- FX_TRANSITIONS: valid transitions pass, invalid fail
- IRS_TRANSITIONS: valid transitions pass, invalid fail
- PrimitiveInstruction union covers all 10 variants
- check_transition with FX_TRANSITIONS and IRS_TRANSITIONS

**Expected tests: ~20**

---

## Step 3 -- Gateway Parsers for FX and IRS

### Modify: `attestor/gateway/parser.py`

Add parsing functions:

```python
def parse_fx_spot_order(raw: dict[str, str]) -> Ok[CanonicalOrder] | Err[ValidationError]:
    """Parse raw FX spot order. Settlement default: T+2."""
    # Extract currency_pair, validate both currencies
    # Inject FXDetail(forward_rate=None, fixing_source=None, fixing_date=None)
    ...

def parse_fx_forward_order(raw: dict[str, str]) -> Ok[CanonicalOrder] | Err[ValidationError]:
    """Parse raw FX forward order. Settlement date from forward contract."""
    # Extract forward_rate, settlement_date
    # Inject FXDetail(forward_rate=..., fixing_source=None, fixing_date=None)
    ...

def parse_ndf_order(raw: dict[str, str]) -> Ok[CanonicalOrder] | Err[ValidationError]:
    """Parse raw NDF order. Fixing date + settlement date required."""
    # Extract fixing_source, fixing_date
    # Inject FXDetail(settlement_type=CASH, fixing_source=..., fixing_date=...)
    ...

def parse_irs_order(raw: dict[str, str]) -> Ok[CanonicalOrder] | Err[ValidationError]:
    """Parse raw IRS order."""
    # Extract fixed_rate, float_index, day_count, payment_frequency, tenor
    # Inject IRSwapDetail(...)
    ...
```

### Tests: `tests/test_gateway_fx_irs.py`

- parse_fx_spot_order: valid, settlement T+2, currency pair validation
- parse_fx_forward_order: valid, forward_rate, custom settlement_date
- parse_ndf_order: valid, fixing_source, fixing_date <= settlement_date
- parse_irs_order: valid, fixed_rate, float_index, day_count, tenor
- All parsers: idempotent (INV-G01), total (INV-G02) -- never raise
- Rejection cases: invalid currency pair, missing fields

**Expected tests: ~25**

---

## Step 4 -- Oracle: FX Rate and Rate Fixing Ingestion

### New file: `attestor/oracle/fx_ingest.py`

```python
@final @dataclass(frozen=True, slots=True)
class FXRate:
    """Observed FX rate for a currency pair."""
    currency_pair: CurrencyPair
    rate: PositiveDecimal
    timestamp: UtcDatetime

@final @dataclass(frozen=True, slots=True)
class RateFixing:
    """Official rate fixing (e.g. SOFR, EURIBOR)."""
    index_name: NonEmptyStr       # "SOFR", "EURIBOR_3M"
    rate: Decimal                 # can be negative (negative rates)
    fixing_date: date
    source: NonEmptyStr           # "FED", "ECB"
    timestamp: UtcDatetime

def ingest_fx_rate(
    currency_pair: str,
    bid: Decimal,
    ask: Decimal,
    venue: str,
    timestamp: datetime,
) -> Ok[Attestation[FXRate]] | Err[str]:
    """Ingest FX rate quote with QuotedConfidence."""
    ...

def ingest_fx_rate_firm(
    currency_pair: str,
    rate: Decimal,
    source: str,
    timestamp: datetime,
    attestation_ref: str,
) -> Ok[Attestation[FXRate]] | Err[str]:
    """Ingest firm FX rate (e.g. ECB fixing) with FirmConfidence."""
    ...

def ingest_rate_fixing(
    index_name: str,
    rate: Decimal,
    fixing_date: date,
    source: str,
    timestamp: datetime,
    attestation_ref: str,
) -> Ok[Attestation[RateFixing]] | Err[str]:
    """Ingest official rate fixing with FirmConfidence."""
    ...
```

### Tests: `tests/test_oracle_fx_irs.py`

- ingest_fx_rate: valid quote, bid <= ask, QuotedConfidence, content_hash
- ingest_fx_rate_firm: valid firm rate, FirmConfidence
- ingest_rate_fixing: valid SOFR fixing, negative rate allowed
- Attestation provenance populated
- Invalid inputs return Err

**Expected tests: ~18**

---

## Step 5 -- Multi-Currency FX Settlement

### New file: `attestor/ledger/fx_settlement.py`

```python
def create_fx_spot_settlement(
    order: CanonicalOrder,
    buyer_base_account: str,
    buyer_quote_account: str,
    seller_base_account: str,
    seller_quote_account: str,
    spot_rate: Decimal,
    tx_id: str,
) -> Ok[Transaction] | Err[ValidationError]:
    """Create FX spot settlement with 2 Moves (one per currency).

    Move 1: base_notional of BASE currency from seller -> buyer
    Move 2: base_notional * spot_rate of QUOTE currency from buyer -> seller

    Conservation: each currency unit is conserved independently.
    sigma(BASE) unchanged, sigma(QUOTE) unchanged.
    """
    ...

def create_fx_forward_settlement(
    order: CanonicalOrder,
    buyer_base_account: str,
    buyer_quote_account: str,
    seller_base_account: str,
    seller_quote_account: str,
    tx_id: str,
) -> Ok[Transaction] | Err[ValidationError]:
    """Create FX forward settlement at the agreed forward rate."""
    ...

def create_ndf_settlement(
    order: CanonicalOrder,
    buyer_cash_account: str,
    seller_cash_account: str,
    fixing_rate: Decimal,
    tx_id: str,
) -> Ok[Transaction] | Err[ValidationError]:
    """Create NDF cash settlement.

    Settlement amount = notional * (fixing_rate - forward_rate) / fixing_rate
    Single Move in settlement currency.
    """
    ...
```

### Tests: `tests/test_fx_settlement.py`

- FX spot settlement: 2 Moves, correct units (base + quote currencies)
- FX spot conservation: sigma(BASE) == 0, sigma(QUOTE) == 0
- FX forward settlement: uses forward_rate from contract
- NDF settlement: single cash Move, amount = notional * (fixing - forward) / fixing
- NDF conservation: cash currency sigma unchanged
- All settlements produce valid Transactions consumed by LedgerEngine
- Validation: empty accounts -> Err
- LedgerEngine.execute() accepts FX settlements, conservation holds
- Hypothesis: random FX spots + rates -> conservation (200 examples)

**Expected tests: ~22**

---

## Step 6 -- IRS Cashflow Booking

### New file: `attestor/ledger/irs.py`

```python
@final @dataclass(frozen=True, slots=True)
class CashflowSchedule:
    """Scheduled cashflows for one leg of an IRS."""
    cashflows: tuple[ScheduledCashflow, ...]

@final @dataclass(frozen=True, slots=True)
class ScheduledCashflow:
    """A single scheduled cashflow."""
    payment_date: date
    amount: Decimal                # positive = receive, negative = pay
    currency: NonEmptyStr
    leg_type: SwapLegType          # FIXED or FLOAT
    period_start: date
    period_end: date
    day_count_fraction: Decimal    # year fraction for this period

def generate_fixed_leg_schedule(
    notional: Decimal,
    fixed_rate: Decimal,
    start_date: date,
    end_date: date,
    day_count: DayCountConvention,
    payment_frequency: PaymentFrequency,
    currency: str,
) -> Ok[CashflowSchedule] | Err[str]:
    """Generate fixed leg cashflow schedule."""
    ...

def generate_float_leg_schedule(
    notional: Decimal,
    start_date: date,
    end_date: date,
    day_count: DayCountConvention,
    payment_frequency: PaymentFrequency,
    currency: str,
) -> Ok[CashflowSchedule] | Err[str]:
    """Generate float leg schedule (amounts TBD until fixing)."""
    ...

def apply_rate_fixing(
    schedule: CashflowSchedule,
    fixing_rate: Decimal,
    fixing_date: date,
) -> Ok[CashflowSchedule] | Err[str]:
    """Apply a rate fixing to the float leg, computing cashflow amounts."""
    ...

def create_irs_cashflow_transaction(
    instrument_id: str,
    payer_account: str,
    receiver_account: str,
    cashflow: ScheduledCashflow,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Create a transaction for a single IRS cashflow exchange.

    Move: cash from payer -> receiver (or vice versa depending on sign).
    Conservation: sigma(currency) unchanged.
    """
    ...

def create_irs_maturity_transaction(
    instrument_id: str,
    position_account: str,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Close IRS position at maturity. No notional exchange for vanilla IRS."""
    ...
```

### Day count fraction helper in `attestor/core/calendar.py`:

```python
def day_count_fraction(
    start: date, end: date, convention: DayCountConvention,
) -> Decimal:
    """Compute year fraction between two dates under a day count convention."""
    ...
```

### Tests: `tests/test_irs.py`

- generate_fixed_leg_schedule: correct number of periods, amounts
- generate_float_leg_schedule: amounts initially zero
- apply_rate_fixing: computes float amount = notional * rate * dcf
- create_irs_cashflow_transaction: single Move, correct direction
- IRS cashflow conservation: sigma(currency) unchanged
- create_irs_maturity_transaction: closes position
- day_count_fraction: ACT/360, ACT/365, 30/360 examples
- Full IRS lifecycle: trade -> fixings -> cashflows -> maturity
- Hypothesis: random fixings -> cashflow conservation (200 examples)

**Expected tests: ~28**

---

## Step 7 -- Oracle: Yield Curve Bootstrapping (III-04)

### New file: `attestor/oracle/calibration.py`

```python
@final @dataclass(frozen=True, slots=True)
class YieldCurve:
    """Bootstrapped yield curve — discount factors at tenor points."""
    currency: NonEmptyStr
    as_of: date
    tenors: tuple[Decimal, ...]          # year fractions, sorted ascending
    discount_factors: tuple[Decimal, ...]  # D(t) for each tenor
    model_config_ref: str                # reference to ModelConfig attestation

    @staticmethod
    def create(
        currency: str,
        as_of: date,
        tenors: tuple[Decimal, ...],
        discount_factors: tuple[Decimal, ...],
        model_config_ref: str,
    ) -> Ok[YieldCurve] | Err[str]:
        """Validate yield curve construction.

        Enforced at construction:
        - len(tenors) == len(discount_factors)
        - tenors sorted ascending
        - D(0) implied = 1 (first tenor > 0, or if tenor[0]==0 then df[0]==1)
        """
        ...

def discount_factor(curve: YieldCurve, tenor: Decimal) -> Ok[Decimal] | Err[str]:
    """Interpolate discount factor at arbitrary tenor (log-linear)."""
    ...

def forward_rate(
    curve: YieldCurve, t1: Decimal, t2: Decimal,
) -> Ok[Decimal] | Err[str]:
    """Compute forward rate f(t1, t2) = -ln(D(t2)/D(t1)) / (t2 - t1)."""
    ...

@final @dataclass(frozen=True, slots=True)
class RateInstrument:
    """Input instrument for bootstrapping (deposit, swap, future)."""
    instrument_type: NonEmptyStr    # "DEPOSIT", "FRA", "SWAP"
    tenor: Decimal                  # year fraction
    rate: Decimal                   # observed market rate
    currency: NonEmptyStr

def bootstrap_curve(
    instruments: tuple[RateInstrument, ...],
    config: ModelConfig,
    as_of: date,
    currency: str,
) -> Ok[Attestation[YieldCurve]] | Err[str]:
    """Bootstrap a yield curve from market instruments.

    Uses piecewise log-linear interpolation on discount factors.
    Full provenance: input instrument attestation hashes + model config hash.

    Returns Attestation[YieldCurve] with DerivedConfidence.
    """
    ...
```

### Tests: `tests/test_calibration.py`

- YieldCurve.create: valid curve, sorted tenors, matching lengths
- YieldCurve.create: reject unsorted tenors, mismatched lengths
- discount_factor: interpolation at exact and intermediate points
- forward_rate: correct computation, positive for normal curve
- RateInstrument construction
- bootstrap_curve: simple 3-point curve (deposit, FRA, swap)
- bootstrap_curve: returns DerivedConfidence with fit_quality
- bootstrap_curve: provenance chain populated
- bootstrap_curve: invalid instruments -> Err

**Expected tests: ~20**

---

## Step 8 -- Oracle: Arbitrage-Freedom Gates (III-07)

### New file: `attestor/oracle/arbitrage_gates.py`

```python
class ArbitrageCheckType(Enum):
    YIELD_CURVE = "YIELD_CURVE"
    FX_TRIANGULAR = "FX_TRIANGULAR"
    FX_SPOT_FORWARD = "FX_SPOT_FORWARD"

class CheckSeverity(Enum):
    CRITICAL = "CRITICAL"     # reject + fallback
    HIGH = "HIGH"             # publish with warning
    MEDIUM = "MEDIUM"         # publish + log

@final @dataclass(frozen=True, slots=True)
class ArbitrageCheckResult:
    check_id: str
    check_type: ArbitrageCheckType
    passed: bool
    severity: CheckSeverity
    details: FrozenMap[str, str]

def check_yield_curve_arbitrage_freedom(
    curve: YieldCurve,
) -> Ok[tuple[ArbitrageCheckResult, ...]] | Err[str]:
    """Run yield curve arbitrage-freedom gates.

    AF-YC-01: D(t) > 0 for all t                              (CRITICAL)
    AF-YC-02: D(0) = 1 (enforced at construction)             (CRITICAL)
    AF-YC-03: D(t2) <= D(t1) for t2 > t1 (monotone)           (CRITICAL)
    AF-YC-04: f(t1, t2) >= governed_floor                      (HIGH)
    AF-YC-05: |f''(t)| < smoothness_bound                      (MEDIUM)
    """
    ...

def check_fx_triangular_arbitrage(
    rates: tuple[tuple[CurrencyPair, Decimal], ...],
    tolerance: Decimal = Decimal("0.001"),
) -> Ok[tuple[ArbitrageCheckResult, ...]] | Err[str]:
    """Check triangular arbitrage condition for FX crosses.

    AF-FX-01: |FX(A/B) * FX(B/C) * FX(C/A) - 1| < tolerance  (CRITICAL)
    """
    ...

def check_fx_spot_forward_consistency(
    spot_rate: Decimal,
    forward_rate: Decimal,
    domestic_df: Decimal,
    foreign_df: Decimal,
    tolerance: Decimal = Decimal("0.001"),
) -> Ok[ArbitrageCheckResult] | Err[str]:
    """Check covered interest rate parity.

    AF-FX-03: F(0) = S (at t=0)                               (CRITICAL)
    AF-FX-02: |F(T)/S - D_domestic(T)/D_foreign(T)| < tol     (HIGH)
    """
    ...

def check_arbitrage_freedom(
    attestation: Attestation[YieldCurve] | tuple[tuple[CurrencyPair, Decimal], ...],
    check_type: ArbitrageCheckType,
) -> Ok[tuple[ArbitrageCheckResult, ...]] | Err[str]:
    """Dispatch to appropriate arbitrage check based on type."""
    ...
```

### Tests: `tests/test_arbitrage_gates.py`

- AF-YC-01: positive discount factors pass; negative/zero fail (CRITICAL)
- AF-YC-02: D(0)=1 pass (enforced at construction)
- AF-YC-03: monotone discount factors pass; non-monotone fail (CRITICAL)
- AF-YC-04: forward rate above floor pass; below fail (HIGH)
- AF-YC-05: smooth forward curve pass; oscillatory fail (MEDIUM)
- AF-FX-01: triangular arbitrage within tolerance pass; outside fail (CRITICAL)
- AF-FX-02: CIP within tolerance pass; outside fail (HIGH)
- AF-FX-03: F(0) = S pass; F(0) != S fail (CRITICAL)
- Integration: bootstrap_curve -> check_arbitrage_freedom pipeline
- CheckSeverity routing: CRITICAL -> reject, HIGH -> warn, MEDIUM -> log

**Expected tests: ~25**

---

## Step 9 -- Model Configuration Attestation (III-06) & Calibration Failure (III-08)

### Modify: `attestor/oracle/calibration.py`

Add calibration failure handling:

```python
@final @dataclass(frozen=True, slots=True)
class CalibrationResult:
    """Result of a calibration attempt."""
    curve: YieldCurve | None                 # None if failed
    model_config: ModelConfig
    arbitrage_checks: tuple[ArbitrageCheckResult, ...]
    passed: bool

@final @dataclass(frozen=True, slots=True)
class FailedCalibrationAttestation:
    """Published when calibration fails. Records the failure reason."""
    model_class: NonEmptyStr
    reason: NonEmptyStr
    failed_checks: tuple[ArbitrageCheckResult, ...]
    fallback_config_ref: str | None           # ref to last-good curve
    timestamp: UtcDatetime

def create_model_config_attestation(
    config: ModelConfig,
    source: str,
    timestamp: datetime,
) -> Ok[Attestation[ModelConfig]] | Err[str]:
    """Create an immutable ModelConfig attestation.

    INV-O02: ModelConfig attestations are never modified after creation.
    """
    ...

def calibrate_and_gate(
    instruments: tuple[RateInstrument, ...],
    config: ModelConfig,
    as_of: date,
    currency: str,
    last_good: Attestation[YieldCurve] | None = None,
) -> Ok[Attestation[YieldCurve]] | Err[str]:
    """Full calibration pipeline: bootstrap -> gate -> publish or fallback.

    1. bootstrap_curve(instruments, config, as_of, currency)
    2. check_yield_curve_arbitrage_freedom(curve)
    3. If all CRITICAL checks pass: publish curve with DerivedConfidence
    4. If CRITICAL check fails: fallback to last_good, publish
       FailedCalibrationAttestation
    """
    ...

def handle_calibration_failure(
    error_reason: str,
    failed_checks: tuple[ArbitrageCheckResult, ...],
    model_config: ModelConfig,
    last_good: Attestation[YieldCurve] | None,
    timestamp: datetime,
) -> Ok[Attestation[YieldCurve]] | Err[str]:
    """Handle calibration failure with fallback to last-good curve.

    III-08: Publishes FailedCalibrationAttestation. Staleness threshold
    configurable per observable. Falls back to last-good snapshot with
    degraded confidence tag.
    """
    ...
```

### Tests: `tests/test_calibration_failure.py`

- create_model_config_attestation: valid ModelConfig, immutable
- calibrate_and_gate: successful calibration path
- calibrate_and_gate: failed calibration -> fallback to last_good
- calibrate_and_gate: failed calibration with no last_good -> Err
- handle_calibration_failure: FailedCalibrationAttestation populated
- handle_calibration_failure: fallback curve retains DerivedConfidence
- CalibrationResult captures arbitrage check results
- ModelConfig attestation provenance chain complete

**Expected tests: ~18**

---

## Step 10 -- Reporting Extensions

### Modify: `attestor/reporting/mifid2.py`

Add FX and IRS report fields:

```python
@final @dataclass(frozen=True, slots=True)
class FXReportFields:
    """FX-specific reporting fields for MiFID II."""
    currency_pair: str
    forward_rate: Decimal | None    # None for spot
    settlement_type: str

@final @dataclass(frozen=True, slots=True)
class IRSwapReportFields:
    """IRS-specific reporting fields for MiFID II."""
    fixed_rate: Decimal
    float_index: str
    day_count: str
    tenor_months: int
    notional_currency: str

# Updated union:
type InstrumentReportFields = (
    OptionReportFields | FuturesReportFields
    | FXReportFields | IRSwapReportFields | None
)
```

Extend `project_mifid2_report` to handle FXDetail and IRSwapDetail:

```python
def project_mifid2_report(
    order: CanonicalOrder,
    trade_attestation_id: str,
) -> Ok[Attestation[MiFIDIIReport]] | Err[str]:
    # pattern match on order.instrument_detail
    # FXDetail -> FXReportFields
    # IRSwapDetail -> IRSwapReportFields
    ...
```

### Modify: `attestor/reporting/emir.py`

Extend `project_emir_report` to handle FX/IRS orders (same projection pattern,
no new values computed, just different field mapping).

### Tests: `tests/test_reporting_fx_irs.py`

- MiFID II report with FXDetail -> FXReportFields populated
- MiFID II report with IRSwapDetail -> IRSwapReportFields populated
- EMIR report with FX order: correct field mapping
- EMIR report with IRS order: correct field mapping
- INV-R01: projection only, no new values computed
- Report attestation provenance complete
- Reporting naturality: project then lifecycle = lifecycle then project

**Expected tests: ~16**

---

## Step 11 -- Pricing Stub Extension

### Modify: `attestor/pricing/protocols.py`

Extend StubPricingEngine to handle FX and IRS instrument IDs:

```python
# No protocol changes needed -- PricingEngine already accepts any instrument_id.
# StubPricingEngine already returns oracle_price for any ID.
# Just verify in tests.
```

### Modify: `attestor/pricing/types.py`

ValuationResult already has `fixed_leg_pv` and `floating_leg_pv` fields
(from Master Plan). If not present, add them:

```python
@final @dataclass(frozen=True, slots=True)
class ValuationResult:
    instrument_id: str
    npv: Decimal
    currency: str
    valuation_date: date | None = None
    components: FrozenMap[str, Decimal] = FrozenMap.EMPTY
    model_config_id: str = ""
    market_snapshot_id: str = ""
    fixed_leg_pv: Decimal = Decimal("0")
    floating_leg_pv: Decimal = Decimal("0")
```

### Tests: `tests/test_pricing_fx_irs.py`

- StubPricingEngine.price with FX instrument_id -> Ok
- StubPricingEngine.price with IRS instrument_id -> Ok
- StubPricingEngine.greeks with FX instrument_id -> Ok
- ValuationResult with fixed_leg_pv and floating_leg_pv
- Master Square: price(id) deterministic for FX/IRS stubs

**Expected tests: ~8**

---

## Step 12 -- Infrastructure (Kafka Topics + Postgres Tables)

### Modify: `attestor/infra/config.py`

```python
# Phase 3 topic constants
TOPIC_FX_RATES = "attestor.oracle.fx_rates"
TOPIC_YIELD_CURVES = "attestor.oracle.yield_curves"
TOPIC_RATE_FIXINGS = "attestor.oracle.rate_fixings"
TOPIC_CALIBRATION_EVENTS = "attestor.oracle.calibration_events"
TOPIC_MODEL_CONFIGS = "attestor.oracle.model_configs"

PHASE3_TOPICS = frozenset({
    TOPIC_FX_RATES, TOPIC_YIELD_CURVES, TOPIC_RATE_FIXINGS,
    TOPIC_CALIBRATION_EVENTS, TOPIC_MODEL_CONFIGS,
})

def phase3_topic_configs() -> tuple[TopicConfig, ...]:
    """Return topic configs for the five Phase 3 topics."""
    return (
        TopicConfig(name=TOPIC_FX_RATES, partitions=6, replication_factor=3,
                    retention_ms=90 * 24 * 3600 * 1000, cleanup_policy="delete",
                    min_insync_replicas=2),
        TopicConfig(name=TOPIC_YIELD_CURVES, partitions=3, replication_factor=3,
                    retention_ms=-1, cleanup_policy="delete",
                    min_insync_replicas=2),
        TopicConfig(name=TOPIC_RATE_FIXINGS, partitions=3, replication_factor=3,
                    retention_ms=-1, cleanup_policy="delete",
                    min_insync_replicas=2),
        TopicConfig(name=TOPIC_CALIBRATION_EVENTS, partitions=3, replication_factor=3,
                    retention_ms=-1, cleanup_policy="delete",
                    min_insync_replicas=2),
        TopicConfig(name=TOPIC_MODEL_CONFIGS, partitions=3, replication_factor=3,
                    retention_ms=-1, cleanup_policy="delete",
                    min_insync_replicas=2),
    )
```

### Modify: `attestor/infra/__init__.py`

Re-export Phase 3 topic constants and `phase3_topic_configs`.

### New SQL files:

**`sql/013_yield_curves.sql`**
```sql
CREATE TABLE IF NOT EXISTS attestor.yield_curves (
    curve_id        TEXT        PRIMARY KEY,
    currency        TEXT        NOT NULL,
    as_of           DATE        NOT NULL,
    tenors          DECIMAL[]   NOT NULL,
    discount_factors DECIMAL[]  NOT NULL,
    confidence_payload JSONB    NOT NULL DEFAULT '{}',
    model_config_ref TEXT       NOT NULL,
    valid_time      TIMESTAMPTZ NOT NULL,
    system_time     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER prevent_mutation_yield_curves
    BEFORE UPDATE OR DELETE ON attestor.yield_curves
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();
```

**`sql/014_fx_rates.sql`**
```sql
CREATE TABLE IF NOT EXISTS attestor.fx_rates (
    rate_id         TEXT        PRIMARY KEY,
    pair            TEXT        NOT NULL,
    rate            DECIMAL     NOT NULL,
    confidence      TEXT        NOT NULL CHECK (confidence IN ('firm', 'quoted')),
    valid_time      TIMESTAMPTZ NOT NULL,
    system_time     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER prevent_mutation_fx_rates
    BEFORE UPDATE OR DELETE ON attestor.fx_rates
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();
```

**`sql/015_model_configs.sql`**
```sql
CREATE TABLE IF NOT EXISTS attestor.model_configs (
    config_id           TEXT        NOT NULL,
    model_class         TEXT        NOT NULL,
    parameters          JSONB       NOT NULL,
    code_version        TEXT        NOT NULL,
    calibration_timestamp TIMESTAMPTZ NOT NULL,
    fit_quality         JSONB       NOT NULL DEFAULT '{}',
    attestation_ref     TEXT,
    valid_time          TIMESTAMPTZ NOT NULL,
    system_time         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (config_id, code_version, calibration_timestamp)
);
CREATE TRIGGER prevent_mutation_model_configs
    BEFORE UPDATE OR DELETE ON attestor.model_configs
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();
```

**`sql/016_calibration_failures.sql`**
```sql
CREATE TABLE IF NOT EXISTS attestor.calibration_failures (
    failure_id      TEXT        PRIMARY KEY,
    model_class     TEXT        NOT NULL,
    reason          TEXT        NOT NULL,
    failed_checks   JSONB       NOT NULL DEFAULT '[]',
    fallback_config_ref TEXT,
    valid_time      TIMESTAMPTZ NOT NULL,
    system_time     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER prevent_mutation_calibration_failures
    BEFORE UPDATE OR DELETE ON attestor.calibration_failures
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();
```

**`sql/017_cashflows.sql`**
```sql
CREATE TABLE IF NOT EXISTS attestor.cashflows (
    cashflow_id     TEXT        PRIMARY KEY,
    instrument_id   TEXT        NOT NULL,
    direction       TEXT        NOT NULL CHECK (direction IN ('PAY', 'RECEIVE')),
    amount          DECIMAL     NOT NULL,
    currency        TEXT        NOT NULL,
    payment_date    DATE        NOT NULL,
    leg_type        TEXT        NOT NULL CHECK (leg_type IN ('FIXED', 'FLOAT')),
    period_start    DATE        NOT NULL,
    period_end      DATE        NOT NULL,
    status          TEXT        NOT NULL CHECK (status IN ('SCHEDULED', 'FIXED', 'SETTLED')),
    valid_time      TIMESTAMPTZ NOT NULL,
    system_time     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER prevent_mutation_cashflows
    BEFORE UPDATE OR DELETE ON attestor.cashflows
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();
```

### Tests: `tests/test_infra_phase3.py`

- Phase 3 topic constants: all 5 defined, no duplicates
- PHASE3_TOPICS frozenset has 5 elements
- phase3_topic_configs: 5 configs, valid names, correct retention
- Yield curves SQL: table exists, prevent_mutation trigger
- FX rates SQL: table exists, prevent_mutation trigger
- Model configs SQL: composite PK, prevent_mutation trigger
- Calibration failures SQL: prevent_mutation trigger
- Cashflows SQL: status enum, prevent_mutation trigger

**Expected tests: ~14**

---

## Step 13 -- Invariant Tests

### New file: `tests/test_invariants_fx_irs.py`

**Conservation Laws:**

```
CL-F1: FX Spot Conservation (Hypothesis, 200 examples)
    For every FX spot settlement: sigma(BASE) unchanged AND sigma(QUOTE) unchanged.

CL-F2: FX Forward Conservation
    Same as CL-F1 but at forward settlement.

CL-F3: NDF Settlement Conservation
    sigma(settlement_currency) unchanged after NDF cash settlement.

CL-F4: IRS Cashflow Conservation (Hypothesis, 200 examples)
    For every IRS cashflow exchange: sigma(currency) unchanged.

CL-F5: IRS Full Lifecycle Conservation
    Trade -> multiple fixings -> cashflows -> maturity: sigma(currency) == 0 throughout.

CL-F6: Multi-Currency Conservation
    Multiple FX + IRS trades: sigma(U) == 0 for EVERY currency U, independently.
```

**Arbitrage-Freedom Invariants:**

```
INV-AF-01: Yield curve positive discount factors (AF-YC-01)
INV-AF-02: Yield curve monotonicity (AF-YC-03)
INV-AF-03: FX triangular arbitrage (AF-FX-01)
INV-AF-04: FX spot-forward consistency (AF-FX-03)
```

**Commutativity Squares:**

```
CS-F1: Master Square for FX — book then stub-price == stub-price then book
CS-F2: Master Square for IRS — same
CS-F3: Reporting naturality for FX — project(lifecycle(I)) == project_update(project(I), event)
CS-F4: Oracle-Ledger consistency — FX rate from Oracle matches settlement rate
CS-F5: Calibration commutativity — same inputs produce same curve
```

**Expected tests: ~24**

---

## Step 14 -- Integration Tests

### New file: `tests/test_integration_fx_irs.py`

**Full FX Spot Lifecycle (10 steps):**
1. Parse FX spot order -> CanonicalOrder with FXDetail
2. Create FX instrument -> Instrument with FXSpotPayoutSpec
3. Ingest FX rate -> Attestation[FXRate]
4. Book FX spot trade -> LedgerEngine.execute()
5. Verify multi-currency positions (2 currencies)
6. Create FX settlement -> Transaction with 2 Moves
7. Execute settlement -> verify conservation per currency
8. Project EMIR report -> Attestation[EMIRTradeReport]
9. Project MiFID II report -> FXReportFields populated
10. Verify idempotency -> re-execute returns AlreadyApplied

**Full NDF Lifecycle (8 steps):**
1. Parse NDF order -> CanonicalOrder with FXDetail (settlement_type=CASH)
2. Create NDF instrument -> Instrument with NDFPayoutSpec
3. Ingest fixing rate -> Attestation[RateFixing]
4. Book NDF trade -> execute()
5. Apply fixing -> compute settlement amount
6. Create NDF settlement -> single cash Move
7. Execute settlement -> verify conservation
8. Project reports -> correct NDF fields

**Full IRS Lifecycle (12 steps):**
1. Parse IRS order -> CanonicalOrder with IRSwapDetail
2. Create IRS instrument -> Instrument with IRSwapPayoutSpec
3. Generate fixed leg schedule -> CashflowSchedule
4. Generate float leg schedule -> CashflowSchedule (amounts TBD)
5. Ingest SOFR fixing -> Attestation[RateFixing]
6. Apply rate fixing to float leg -> amounts computed
7. Create cashflow transaction (period 1) -> execute()
8. Repeat for multiple periods
9. Create maturity transaction -> execute()
10. Verify lifecycle: PROPOSED -> FORMED -> SETTLED -> CLOSED
11. Verify conservation: sigma(currency) == 0 throughout
12. Project EMIR/MiFID reports -> IRSwapReportFields populated

**Full Yield Curve Calibration Pipeline (8 steps):**
1. Create RateInstruments (deposit, FRA, swap)
2. Create ModelConfig attestation
3. Bootstrap yield curve -> Attestation[YieldCurve]
4. Run arbitrage-freedom gates -> all CRITICAL pass
5. Verify discount factor interpolation
6. Inject bad instrument -> calibration failure
7. Handle failure -> fallback to last_good curve
8. Verify FailedCalibrationAttestation published

**Import smoke tests:**
- All new modules importable
- All new types constructible
- All new functions callable

**Engine untouched verification:**
- engine.py has zero FX/IRS keywords (excluding `__future__`)

**Expected tests: ~50**

---

## Step 15 -- Re-exports and Package Init Updates

### Modify: `attestor/instrument/__init__.py`

Re-export all new FX/IRS types and factories.

### Modify: `attestor/oracle/__init__.py`

Re-export FXRate, RateFixing, YieldCurve, RateInstrument, calibration functions,
arbitrage gates.

### Modify: `attestor/reporting/__init__.py`

Re-export FXReportFields, IRSwapReportFields.

### Modify: `attestor/ledger/__init__.py`

Re-export FX settlement and IRS functions.

---

## Test Budget

| Step | Description | Expected tests |
|------|------------|---------------|
| 1 | FX/IRS instrument types | ~40 |
| 2 | FX/IRS lifecycle | ~20 |
| 3 | Gateway parsers | ~25 |
| 4 | Oracle FX/rate ingestion | ~18 |
| 5 | Multi-currency FX settlement | ~22 |
| 6 | IRS cashflow booking | ~28 |
| 7 | Yield curve bootstrapping | ~20 |
| 8 | Arbitrage-freedom gates | ~25 |
| 9 | Model config + calibration failure | ~18 |
| 10 | Reporting extensions | ~16 |
| 11 | Pricing stub extension | ~8 |
| 12 | Infrastructure | ~14 |
| 13 | Invariant tests | ~24 |
| 14 | Integration tests | ~50 |
| 15 | Re-exports | ~0 (covered by smoke tests) |
| **Total new** | | **~328** |
| **Running total** | 676 + 328 | **~1004** |

---

## Source Line Budget (Geohot)

| File | Est. lines | Notes |
|------|-----------|-------|
| `instrument/fx_types.py` | ~250 | FX/IRS PayoutSpecs + smart constructors |
| `instrument/derivative_types.py` (extend) | +80 | FXDetail, IRSwapDetail |
| `instrument/types.py` (extend) | +80 | Payout union, 4 factory functions |
| `instrument/lifecycle.py` (extend) | +50 | 3 new PI variants, 2 transition tables |
| `gateway/parser.py` (extend) | +120 | 4 new parser functions |
| `oracle/fx_ingest.py` | ~120 | FXRate, RateFixing, 3 ingest functions |
| `oracle/calibration.py` | ~300 | YieldCurve, bootstrap, ModelConfig attestation, failure handling |
| `oracle/arbitrage_gates.py` | ~200 | 3 gate functions, ArbitrageCheckResult |
| `ledger/fx_settlement.py` | ~150 | 3 FX settlement functions |
| `ledger/irs.py` | ~250 | Cashflow types, schedule generation, rate fixing, settlement |
| `core/money.py` (extend) | +30 | CurrencyPair |
| `core/calendar.py` (extend) | +40 | day_count_fraction |
| `reporting/mifid2.py` (extend) | +50 | FXReportFields, IRSwapReportFields |
| `reporting/emir.py` (extend) | +20 | FX/IRS field mapping |
| `pricing/types.py` (extend) | +10 | fixed_leg_pv, floating_leg_pv |
| `infra/config.py` (extend) | +40 | 5 topics, phase3_topic_configs |
| SQL files (5 new) | ~100 | Postgres tables |
| **Total new source** | **~1890** | Under 5,000 line budget |

---

## Key Invariants to Verify

| ID | Property | Test mechanism |
|----|----------|---------------|
| INV-L01 | sigma(U) = 0 for every currency U, per execute | Hypothesis property-based |
| AF-YC-01 | D(t) > 0 for all t | Construction + gate |
| AF-YC-02 | D(0) = 1 | Construction |
| AF-YC-03 | D(t2) <= D(t1) for t2 > t1 | Gate check |
| AF-FX-01 | Triangular arbitrage < tolerance | Gate check |
| AF-FX-03 | F(0) = S | Gate check |
| INV-O02 | ModelConfig immutable after creation | Frozen dataclass |
| INV-R01 | Reporting is projection only | Test: no new values |
| III-08 | Calibration failure -> fallback | Integration test |
| Parametric | engine.py unchanged | SHA-256 or keyword check |

---

## Files That MUST NOT Be Modified

- `attestor/ledger/engine.py` (Principle V: parametric polymorphism)
- `attestor/core/result.py` (foundation)
- `attestor/core/serialization.py` (foundation)
- `attestor/core/errors.py` (foundation — may extend with new error subclasses only)

---

## Dependencies

Phase 2 must be fully passing (676 tests) before Phase 3 begins.
No external library additions. Python stdlib `decimal`, `datetime`, `enum`,
`dataclasses`, `typing` only.
