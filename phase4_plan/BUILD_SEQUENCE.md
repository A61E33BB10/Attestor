# Attestor Phase 4 -- Credit and Structured Products: Build Sequence

**Date:** 2026-02-15
**Math Spec:** `phase4_plan/PLAN.md` (Gatheral)
**Pattern:** Same as Phase 2 (12 steps) and Phase 3 (15 steps)

---

## Scope

Credit instrument model (CDS single-name), European swaption instrument model,
Oracle extended with credit curve bootstrapping and vol surface calibration
(SVI/SSVI), collateral management in the Ledger. NO pricing -- no CDS pricing,
no swaption pricing, no Monte Carlo. Pillar V stubs extended for credit and
vol surface types.

**Products:** CDS (single-name), swaptions (European), collateral (cash and
securities).

**Lifecycle stages:**
- CDS: trade, premium/protection leg, credit event, auction, settlement
- Swaption: trade, exercise, underlying IRS lifecycle (reuses Phase 3)
- Collateral: margin call, delivery, substitution, return

**Deliverables:** II-08, III-05, IV-09

---

## Parametric Polymorphism Proof

Phase 4 continues to prove Manifesto Principle V: adding CDS, swaptions, and
collateral does NOT modify the core ledger engine. `LedgerEngine.execute()`
operates on `Transaction` and `Move` -- instrument-agnostic types. Collateral
movements are ordinary balanced transactions with collateral-typed account IDs.

**Files that MUST NOT be modified:** `attestor/ledger/engine.py`

---

## Build Protocol (same as Phase 1/2/3)

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

## Step 0 -- Phase 3 Cleanup: Decimal Math Utilities

The math spec (PLAN.md Section 8.1) identifies that Phase 3's `calibration.py`
uses `math.log(float(...))` for discount factor interpolation. Phase 4 requires
pure-Decimal `exp` and `ln` for credit curve bootstrapping and SVI calibration.
Build this utility first, as it is consumed by Steps 3, 4, and 8.

### New file: `attestor/core/decimal_math.py`

```python
def exp_d(x: Decimal) -> Decimal:
    """Compute exp(x) in pure Decimal arithmetic.

    Uses Taylor series: exp(x) = sum_{n=0}^N x^n / n!
    Converges for all x. For |x| > 50, use range reduction:
    exp(x) = exp(x/2^k)^(2^k) where k chosen so |x/2^k| < 1.
    All arithmetic in ATTESTOR_DECIMAL_CONTEXT.
    """
    ...

def ln_d(x: Decimal) -> Decimal:
    """Compute ln(x) in pure Decimal arithmetic.

    Requires x > 0. Uses range reduction to [0.5, 2) and then
    the series ln(1+y) = y - y^2/2 + y^3/3 - ...
    """
    ...

def sqrt_d(x: Decimal) -> Decimal:
    """Compute sqrt(x) using Decimal.sqrt() in ATTESTOR_DECIMAL_CONTEXT."""
    ...

def expm1_neg_d(x: Decimal) -> Decimal:
    """Compute 1 - exp(-x) without subtractive cancellation.

    For small x (< 0.01): Taylor series x - x^2/2 + x^3/6 - ...
    For large x: 1 - exp_d(-x).
    """
    ...
```

### Tests: `tests/test_decimal_math.py`

- exp_d(0) == 1
- exp_d(1) matches e to 20+ digits
- exp_d(-1) == 1/e to 20+ digits
- exp_d(50) matches known value (large argument range reduction)
- ln_d(1) == 0
- ln_d(e) == 1 to 20+ digits
- ln_d(exp_d(x)) == x round-trip for several x values
- exp_d(ln_d(x)) == x round-trip for several x values
- ln_d(0) -> Err or appropriate handling
- ln_d(-1) -> Err
- sqrt_d(4) == 2
- sqrt_d(2) matches known value
- expm1_neg_d(0) == 0
- expm1_neg_d(small) matches 1-exp(-small) but more precise
- expm1_neg_d(large) matches 1-exp(-large)
- All functions operate in ATTESTOR_DECIMAL_CONTEXT (deterministic)
- No float used internally

**Expected tests: ~20**

**Invariants verified:**
- INV-08 (Reproducibility): same inputs produce identical Decimal outputs
- No float contamination in any code path

---

## Step 1 -- CDS and Swaption Instrument Types

### New file: `attestor/instrument/credit_types.py`

Types defined per math spec (PLAN.md Sections 4.7, 5.4):

```python
class CreditEventType(Enum):
    BANKRUPTCY = "BANKRUPTCY"
    FAILURE_TO_PAY = "FAILURE_TO_PAY"
    RESTRUCTURING = "RESTRUCTURING"

class SeniorityLevel(Enum):
    SENIOR_UNSECURED = "SENIOR_UNSECURED"
    SUBORDINATED = "SUBORDINATED"
    SENIOR_SECURED = "SENIOR_SECURED"

class ProtectionSide(Enum):
    BUYER = "BUYER"      # pays premium, receives protection
    SELLER = "SELLER"    # receives premium, pays on credit event

class SwaptionType(Enum):
    PAYER = "PAYER"      # right to enter as fixed-rate payer
    RECEIVER = "RECEIVER" # right to receive fixed

@final @dataclass(frozen=True, slots=True)
class CDSPayoutSpec:
    """CDS single-name payout specification.

    Premium leg: periodic spread payments from protection buyer to seller.
    Protection leg: on credit event, seller pays (1 - recovery) * notional.

    Per math spec Section 4.1.
    """
    reference_entity: NonEmptyStr
    notional: PositiveDecimal
    spread: Decimal               # contractual spread as decimal (e.g. 0.01 = 100bps)
    currency: NonEmptyStr
    effective_date: date
    maturity_date: date
    payment_frequency: PaymentFrequency  # typically QUARTERLY
    day_count: DayCountConvention        # ACT/360 per ISDA standard
    recovery_rate: Decimal               # contractual assumed recovery (e.g. 0.40)

    @staticmethod
    def create(...) -> Ok[CDSPayoutSpec] | Err[str]:
        # Validate: effective_date < maturity_date
        # Validate: 0 <= recovery_rate < 1
        # Validate: spread > 0
        ...

@final @dataclass(frozen=True, slots=True)
class SwaptionPayoutSpec:
    """European swaption payout specification.

    Per math spec Section 5.4. The underlying_swap field contains
    the full IRSwapPayoutSpec that exercise would create.
    """
    swaption_type: SwaptionType
    strike: PositiveDecimal            # fixed rate K
    exercise_date: date
    underlying_swap: IRSwapPayoutSpec  # the IRS that exercise would create
    settlement_type: SettlementType    # PHYSICAL or CASH
    currency: NonEmptyStr
    notional: PositiveDecimal

    @staticmethod
    def create(...) -> Ok[SwaptionPayoutSpec] | Err[str]:
        # Validate: exercise_date <= underlying_swap.start_date
        # Validate: underlying_swap.start_date < underlying_swap.end_date
        ...
```

### Modify: `attestor/instrument/derivative_types.py`

Add gateway-level detail types for CDS and swaption orders:

```python
@final @dataclass(frozen=True, slots=True)
class CDSDetail:
    """CDS order detail on a CanonicalOrder."""
    reference_entity: NonEmptyStr
    spread_bps: PositiveDecimal
    seniority: SeniorityLevel
    protection_side: ProtectionSide
    start_date: date
    maturity_date: date

    @staticmethod
    def create(...) -> Ok[CDSDetail] | Err[str]: ...

@final @dataclass(frozen=True, slots=True)
class SwaptionDetail:
    """Swaption order detail on a CanonicalOrder."""
    swaption_type: SwaptionType
    expiry_date: date
    underlying_fixed_rate: PositiveDecimal
    underlying_float_index: NonEmptyStr
    underlying_tenor_months: int
    settlement_type: SettlementType

    @staticmethod
    def create(...) -> Ok[SwaptionDetail] | Err[str]: ...

# Updated union:
type InstrumentDetail = (
    EquityDetail | OptionDetail | FuturesDetail
    | FXDetail | IRSwapDetail
    | CDSDetail | SwaptionDetail
)
```

### Modify: `attestor/instrument/types.py`

Extend Payout union and add factories:

```python
type Payout = (
    EquityPayoutSpec | OptionPayoutSpec | FuturesPayoutSpec
    | FXSpotPayoutSpec | FXForwardPayoutSpec | NDFPayoutSpec | IRSwapPayoutSpec
    | CDSPayoutSpec | SwaptionPayoutSpec
)
```

Add `create_cds_instrument()` and `create_swaption_instrument()`.

### Tests: `tests/test_credit_types.py`

- CreditEventType, SeniorityLevel, ProtectionSide, SwaptionType enum values
- CDSPayoutSpec.create valid: all fields, spread > 0, 0 <= recovery < 1
- CDSPayoutSpec.create invalid: effective >= maturity, recovery >= 1, spread <= 0
- SwaptionPayoutSpec.create valid: exercise <= swap start < swap end
- SwaptionPayoutSpec.create invalid: exercise > swap start
- CDSDetail.create valid/invalid
- SwaptionDetail.create valid/invalid (tenor_months > 0, etc.)
- InstrumentDetail union covers all 7 variants (exhaustive match test)
- Payout union covers all 9 variants (exhaustive match test)
- create_cds_instrument: produces Instrument with CDSPayoutSpec
- create_swaption_instrument: produces Instrument with SwaptionPayoutSpec
- All types frozen, slots, immutable

**Expected tests: ~35**

**Invariants verified:**
- All domain types use Decimal, never float
- All smart constructors return Ok | Err, never raise

---

## Step 2 -- CDS and Swaption Lifecycle

### Modify: `attestor/instrument/lifecycle.py`

Add new PrimitiveInstruction variants per math spec (PLAN.md Sections 5.6, 6.6):

```python
@final @dataclass(frozen=True, slots=True)
class CreditEventPI:
    """Credit event declaration -- triggers protection leg."""
    instrument_id: NonEmptyStr
    event_type: CreditEventType
    determination_date: date
    auction_price: Decimal | None   # None before auction, populated after

@final @dataclass(frozen=True, slots=True)
class SwaptionExercisePI:
    """Swaption exercise -- converts swaption into underlying IRS."""
    instrument_id: NonEmptyStr
    exercise_date: date
    settlement_amount: Money | None     # non-None for cash settlement
    underlying_irs_id: NonEmptyStr | None  # non-None for physical settlement

@final @dataclass(frozen=True, slots=True)
class CollateralCallPI:
    """Collateral margin call instruction."""
    agreement_id: NonEmptyStr
    call_amount: Money
    call_date: date
    collateral_type: NonEmptyStr   # "CASH" or instrument ID
```

Updated `PrimitiveInstruction`:

```python
PrimitiveInstruction = (
    ExecutePI | TransferPI | DividendPI
    | ExercisePI | AssignPI | ExpiryPI | MarginPI
    | FixingPI | NettingPI | MaturityPI
    | CreditEventPI | SwaptionExercisePI | CollateralCallPI
)
```

Add transition tables:

```python
CDS_TRANSITIONS: TransitionTable = frozenset({
    (PositionStatusEnum.PROPOSED, PositionStatusEnum.FORMED),
    (PositionStatusEnum.PROPOSED, PositionStatusEnum.CANCELLED),
    (PositionStatusEnum.FORMED, PositionStatusEnum.SETTLED),     # active
    (PositionStatusEnum.FORMED, PositionStatusEnum.CANCELLED),
    (PositionStatusEnum.SETTLED, PositionStatusEnum.CLOSED),     # maturity or credit event
})

SWAPTION_TRANSITIONS: TransitionTable = frozenset({
    (PositionStatusEnum.PROPOSED, PositionStatusEnum.FORMED),
    (PositionStatusEnum.PROPOSED, PositionStatusEnum.CANCELLED),
    (PositionStatusEnum.FORMED, PositionStatusEnum.SETTLED),     # exercise
    (PositionStatusEnum.FORMED, PositionStatusEnum.CANCELLED),   # expiry (unexercised)
    (PositionStatusEnum.SETTLED, PositionStatusEnum.CLOSED),     # underlying IRS matured
})
```

### Tests: `tests/test_lifecycle_credit.py`

- CreditEventPI, SwaptionExercisePI, CollateralCallPI frozen and immutable
- CDS_TRANSITIONS: all 5 valid transitions pass
- CDS_TRANSITIONS: 3+ invalid transitions (e.g. SETTLED -> FORMED) fail
- SWAPTION_TRANSITIONS: all 5 valid transitions pass
- SWAPTION_TRANSITIONS: 3+ invalid transitions fail
- PrimitiveInstruction union covers all 13 variants
- check_transition with CDS_TRANSITIONS works correctly
- check_transition with SWAPTION_TRANSITIONS works correctly
- CreditEventType enum used in CreditEventPI

**Expected tests: ~20**

**Invariants verified:**
- Transition tables are complete (no missing valid transitions)
- PI union is exhaustive (mypy catches missing match arms)

---

## Step 3 -- Oracle: Credit Curve Types and Bootstrapping

### New file: `attestor/oracle/credit_curve.py`

Types and bootstrap per math spec (PLAN.md Sections 3.1-3.8):

```python
@final @dataclass(frozen=True, slots=True)
class CreditCurve:
    """Bootstrapped credit curve -- survival probabilities at tenor points.

    Construction enforces (math spec Section 3.7):
    - len(tenors) == len(survival_probs) == len(hazard_rates)
    - tenors sorted ascending, all > 0
    - 0 < Q(t) <= 1 for all t
    - Q(t2) <= Q(t1) for t2 > t1 (monotone decreasing)
    - hazard_rates all >= 0
    - 0 <= recovery_rate < 1
    """
    reference_entity: NonEmptyStr
    as_of: date
    tenors: tuple[Decimal, ...]
    survival_probs: tuple[Decimal, ...]
    hazard_rates: tuple[Decimal, ...]
    recovery_rate: Decimal
    discount_curve_ref: str
    model_config_ref: str

    @staticmethod
    def create(...) -> Ok[CreditCurve] | Err[str]: ...

def survival_probability(
    curve: CreditCurve, tenor: Decimal,
) -> Ok[Decimal] | Err[str]:
    """Interpolate survival probability at arbitrary tenor.

    Per math spec Section 3.5: exponential interpolation using
    piecewise constant hazard rates. Q(0) = 1 by convention.
    Uses exp_d from decimal_math (no float).
    """
    ...

def hazard_rate(
    curve: CreditCurve, t1: Decimal, t2: Decimal,
) -> Ok[Decimal] | Err[str]:
    """Compute piecewise-constant hazard rate.

    Per math spec Section 3.2:
    lambda = -ln(Q(t2)/Q(t1)) / (t2-t1)
    Uses ln_d from decimal_math (no float).
    """
    ...

@final @dataclass(frozen=True, slots=True)
class CDSQuote:
    """Market CDS par spread quote for bootstrapping.

    Per math spec Section 3.8.
    """
    reference_entity: NonEmptyStr
    tenor: Decimal
    spread: Decimal              # par spread in decimal (0.01 = 100bps)
    recovery_rate: Decimal       # typically 0.4
    currency: NonEmptyStr

def bootstrap_credit_curve(
    quotes: tuple[CDSQuote, ...],
    discount_curve: YieldCurve,
    config: ModelConfig,
    as_of: date,
    reference_entity: str,
) -> Ok[Attestation[CreditCurve]] | Err[str]:
    """Bootstrap survival probabilities from CDS spread quotes.

    Per math spec Section 3.4: Sequential bootstrap using Brent's method.
    For each tenor, solve PremiumLeg(T_n) = ProtectionLeg(T_n) for lambda_n.

    Simplified initial implementation: Q(t) = 1 / (1 + spread * t / (1 - R))
    which is the zero-coupon approximation. Full ISDA standard model with
    accrual-on-default and mid-period default (math spec Sections 3.3-3.4)
    deferred to later in Phase 4 once Brent solver is proven.

    Returns Attestation[CreditCurve] with DerivedConfidence.
    """
    ...
```

### Tests: `tests/test_credit_curve.py`

- CreditCurve.create: valid curve with 3 tenors, monotone, bounds respected
- CreditCurve.create: reject survival > 1
- CreditCurve.create: reject survival <= 0
- CreditCurve.create: reject non-monotone survival
- CreditCurve.create: reject unsorted tenors
- CreditCurve.create: reject mismatched lengths
- CreditCurve.create: reject negative hazard rate
- CreditCurve.create: reject recovery_rate >= 1
- survival_probability: Q(0) = 1 by convention
- survival_probability: exact interpolation at tenor points
- survival_probability: between tenors uses exponential interpolation
- survival_probability: beyond last tenor uses flat hazard extrapolation
- hazard_rate: correct computation, non-negative for valid curve
- hazard_rate: t2 <= t1 -> Err
- CDSQuote: construction with all fields
- bootstrap_credit_curve: 3-point curve (1Y, 3Y, 5Y)
- bootstrap_credit_curve: DerivedConfidence populated
- bootstrap_credit_curve: provenance chain contains config ref
- bootstrap_credit_curve: empty quotes -> Err
- bootstrap_credit_curve: single quote -> valid 1-point curve
- All arithmetic uses Decimal (no float)

**Expected tests: ~22**

**Invariants verified:**
- AF-CR-01: 0 < Q(t) <= 1 (enforced at construction)
- AF-CR-02: Q(0) = 1 (enforced by interpolation function)
- AF-CR-03: monotone survival (enforced at construction)
- AF-CR-04: non-negative hazard (enforced at construction)

---

## Step 4 -- Oracle: Vol Surface Types and SVI Calibration

### New file: `attestor/oracle/vol_surface.py`

Types and calibration per math spec (PLAN.md Sections 1.1-1.5, 2.8-2.9):

```python
@final @dataclass(frozen=True, slots=True)
class SVIParameters:
    """SVI raw parameterization for a single expiry slice.

    w(k) = a + b * (rho * (k - m) + sqrt((k - m)^2 + sigma^2))

    Per math spec Section 1.1. Constraints C-SVI-01 through C-SVI-05
    enforced at construction.
    """
    a: Decimal
    b: Decimal      # >= 0                         (C-SVI-02)
    rho: Decimal    # (-1, 1)                      (C-SVI-03)
    m: Decimal
    sigma: Decimal  # > 0                          (C-SVI-04)
    expiry: Decimal # > 0

    @staticmethod
    def create(...) -> Ok[SVIParameters] | Err[str]:
        # C-SVI-01: a + b * sigma * sqrt(1 - rho^2) >= 0
        # C-SVI-02: b >= 0
        # C-SVI-03: |rho| < 1
        # C-SVI-04: sigma > 0
        # C-SVI-05: b * (1 + |rho|) <= 2  (Roger Lee)
        ...

def svi_total_variance(params: SVIParameters, k: Decimal) -> Decimal:
    """Compute total implied variance w(k) from SVI parameters.

    w(k) = a + b * (rho * (k - m) + sqrt((k - m)^2 + sigma^2))

    Uses sqrt_d from decimal_math (no float).
    """
    ...

def svi_first_derivative(params: SVIParameters, k: Decimal) -> Decimal:
    """w'(k) = b * (rho + (k - m) / sqrt((k - m)^2 + sigma^2))

    Per math spec Section 1.3.
    """
    ...

def svi_second_derivative(params: SVIParameters, k: Decimal) -> Decimal:
    """w''(k) = b * sigma^2 / ((k - m)^2 + sigma^2)^(3/2)

    Per math spec Section 1.3.
    """
    ...

@final @dataclass(frozen=True, slots=True)
class VolSurface:
    """Calibrated volatility surface -- SVI parameters per expiry.

    Per math spec Section 2.9.
    """
    underlying: NonEmptyStr
    as_of: date
    expiries: tuple[Decimal, ...]           # year fractions, sorted ascending
    slices: tuple[SVIParameters, ...]       # one per expiry
    model_config_ref: str

    @staticmethod
    def create(...) -> Ok[VolSurface] | Err[str]:
        # Validate: same length, sorted, positive expiries
        ...

def implied_vol(
    surface: VolSurface, log_moneyness: Decimal, expiry: Decimal,
) -> Ok[Decimal] | Err[str]:
    """Interpolate implied volatility at (k, T).

    sigma(k, T) = sqrt(w(k, T) / T)

    Between expiries: linear interpolation in total variance.
    Per math spec Section 8.4.1.
    Uses sqrt_d from decimal_math (no float).
    """
    ...

def calibrate_vol_surface(
    quotes: tuple[tuple[Decimal, Decimal, Decimal], ...],
    # Each: (log_moneyness, expiry, market_total_variance)
    config: ModelConfig,
    as_of: date,
    underlying: str,
) -> Ok[Attestation[VolSurface]] | Err[str]:
    """Calibrate SVI vol surface from total variance quotes.

    Groups quotes by expiry, fits SVI parameters per slice using
    simplified least-squares (Stage 1 from math spec Section 1.4).

    Full L-BFGS-B refinement (Stage 2) deferred to production.
    This implementation uses grid search over (m, sigma) with
    analytical solution for (a, b, rho) at each grid point.

    Returns Attestation[VolSurface] with DerivedConfidence.
    """
    ...
```

### Tests: `tests/test_vol_surface.py`

- SVIParameters.create: valid parameters satisfying all 5 constraints
- SVIParameters.create: reject b < 0 (C-SVI-02)
- SVIParameters.create: reject |rho| >= 1 (C-SVI-03)
- SVIParameters.create: reject sigma <= 0 (C-SVI-04)
- SVIParameters.create: reject b*(1+|rho|) > 2 (C-SVI-05, Roger Lee)
- SVIParameters.create: reject negative minimum variance (C-SVI-01)
- svi_total_variance: correct at k=0 (ATM)
- svi_total_variance: correct at k=m (minimum)
- svi_total_variance: always >= 0 for valid params (spot check grid)
- svi_total_variance: symmetric when rho=0 and m=0
- svi_first_derivative: matches numerical difference (spot check)
- svi_second_derivative: always > 0 for b > 0 and sigma > 0
- VolSurface.create: valid surface with 2 expiries
- VolSurface.create: reject mismatched lengths, unsorted, non-positive expiries
- implied_vol: interpolation at exact expiry
- implied_vol: interpolation between expiries (linear in total variance)
- implied_vol: result is positive for valid surface
- calibrate_vol_surface: simple 2-expiry surface from synthetic quotes
- calibrate_vol_surface: DerivedConfidence with fit_quality metrics
- calibrate_vol_surface: empty quotes -> Err
- calibrate_vol_surface: single expiry produces valid 1-slice surface
- All arithmetic uses Decimal via decimal_math (no float in core path)

**Expected tests: ~25**

**Invariants verified:**
- All 5 SVI constraints enforced at construction
- AF-VS-05 (positive variance) follows from C-SVI-01
- AF-VS-03/04 (Roger Lee) follows from C-SVI-05

---

## Step 5 -- Oracle: Credit Curve and Vol Surface Arbitrage Gates

### Modify: `attestor/oracle/arbitrage_gates.py`

Extend the existing gate framework per math spec (PLAN.md Section 7):

```python
class ArbitrageCheckType(Enum):
    YIELD_CURVE = "YIELD_CURVE"
    FX_TRIANGULAR = "FX_TRIANGULAR"
    FX_SPOT_FORWARD = "FX_SPOT_FORWARD"
    VOL_SURFACE = "VOL_SURFACE"       # NEW
    CREDIT_CURVE = "CREDIT_CURVE"     # NEW

def check_vol_surface_arbitrage_freedom(
    surface: VolSurface,
    grid_step: Decimal = Decimal("0.1"),  # coarser than spec for unit tests
    k_range: Decimal = Decimal("5"),
    tolerance: Decimal = Decimal("1e-10"),
) -> Ok[tuple[ArbitrageCheckResult, ...]] | Err[str]:
    """Run vol surface arbitrage-freedom gates.

    AF-VS-01: Calendar spread (math spec 7.1.1)
    AF-VS-02: Durrleman butterfly condition (math spec 7.1.2)
    AF-VS-03: Roger Lee right wing (math spec 7.1.3)
    AF-VS-04: Roger Lee left wing (math spec 7.1.3)
    AF-VS-05: Positive implied variance (math spec 7.1.4)
    AF-VS-06: ATM variance monotonicity (math spec 7.1.5)
    """
    ...

def check_credit_curve_arbitrage_freedom(
    curve: CreditCurve,
) -> Ok[tuple[ArbitrageCheckResult, ...]] | Err[str]:
    """Run credit curve arbitrage-freedom gates.

    AF-CR-01: Survival probability bounds (math spec 7.2.1)
    AF-CR-02: Q(0) = 1 (math spec 7.2.2)
    AF-CR-03: Monotone survival (math spec 7.2.3)
    AF-CR-04: Non-negative hazard rate (math spec 7.2.4)
    """
    ...
```

Note: AF-CR-05 (ISDA re-pricing consistency) requires the full ISDA model from
the bootstrap. Defer to Step 8 or integration tests where both the curve and
the discount curve are available together.

### Tests: `tests/test_arbitrage_gates_phase4.py`

- AF-VS-01: adjacent slices with w2(k) >= w1(k) pass; violation at one k fails
- AF-VS-02: well-behaved SVI (large sigma, small b) passes Durrleman
- AF-VS-02: pathological SVI (extreme rho near boundary) fails Durrleman
- AF-VS-03: b*(1+rho) <= 2 pass (covered by construction, verify via gate)
- AF-VS-04: b*(1-rho) <= 2 pass (same)
- AF-VS-05: positive variance pass for valid surface; injected zero fails
- AF-VS-06: ATM variance non-decreasing pass; non-monotone fails
- AF-CR-01: survival in (0, 1] pass; 0 or >1 would fail (caught at construction)
- AF-CR-02: Q(0)=1 pass (always, by construction)
- AF-CR-03: monotone pass; non-monotone fail (caught at construction, but verify)
- AF-CR-04: non-negative hazard pass; negative would fail
- Integration: calibrate_vol_surface -> check_vol_surface_arbitrage_freedom
- Integration: bootstrap_credit_curve -> check_credit_curve_arbitrage_freedom
- Gate results carry correct ArbitrageCheckType enum
- All check_ids follow naming convention (AF-VS-01, AF-CR-01, etc.)

**Expected tests: ~28**

**Invariants verified:**
- AF-VS-01 through AF-VS-06
- AF-CR-01 through AF-CR-04
- Gate results are immutable ArbitrageCheckResult dataclasses

---

## Step 6 -- Oracle: Credit and Vol Ingestion

### New file: `attestor/oracle/credit_ingest.py`

```python
@final @dataclass(frozen=True, slots=True)
class CDSSpreadQuote:
    """Observed CDS spread from the market."""
    reference_entity: NonEmptyStr
    tenor: Decimal
    spread_bps: Decimal
    recovery_rate: Decimal
    currency: NonEmptyStr
    timestamp: UtcDatetime

def ingest_cds_spread(
    reference_entity: str,
    tenor: Decimal,
    bid_bps: Decimal,
    ask_bps: Decimal,
    recovery_rate: Decimal,
    currency: str,
    venue: str,
    timestamp: datetime,
) -> Ok[Attestation[CDSSpreadQuote]] | Err[str]:
    """Ingest CDS spread quote with QuotedConfidence (bid/ask)."""
    ...

@final @dataclass(frozen=True, slots=True)
class CreditEventRecord:
    """Oracle record of a credit event declaration."""
    reference_entity: NonEmptyStr
    event_type: CreditEventType
    determination_date: date

def ingest_credit_event(
    reference_entity: str,
    event_type: str,
    determination_date: date,
    source: str,
    timestamp: datetime,
    attestation_ref: str,
) -> Ok[Attestation[CreditEventRecord]] | Err[str]:
    """Ingest credit event declaration with FirmConfidence."""
    ...

@final @dataclass(frozen=True, slots=True)
class AuctionResult:
    """Final auction price after a credit event."""
    reference_entity: NonEmptyStr
    event_type: CreditEventType
    determination_date: date
    auction_price: Decimal          # recovery price in [0, 1]

def ingest_auction_result(
    reference_entity: str,
    event_type: str,
    determination_date: date,
    auction_price: Decimal,
    source: str,
    timestamp: datetime,
    attestation_ref: str,
) -> Ok[Attestation[AuctionResult]] | Err[str]:
    """Ingest auction result with FirmConfidence.

    Validation: 0 <= auction_price <= 1.
    """
    ...
```

### Tests: `tests/test_credit_ingest.py`

- ingest_cds_spread: valid, bid <= ask, QuotedConfidence populated
- ingest_cds_spread: bid > ask -> Err
- ingest_cds_spread: negative spread -> Err
- ingest_credit_event: valid, FirmConfidence populated
- ingest_credit_event: invalid event_type string -> Err
- CreditEventRecord construction, frozen
- ingest_auction_result: valid, price in [0, 1], FirmConfidence
- ingest_auction_result: price > 1 -> Err
- ingest_auction_result: price < 0 -> Err
- All attestations have provenance populated
- All attestations have content_hash computed

**Expected tests: ~18**

**Invariants verified:**
- INV-06: Attestation immutability (frozen dataclass)
- INV-16: Provenance populated on all attestations

---

## Step 7 -- Gateway: CDS and Swaption Parsers

### Modify: `attestor/gateway/parser.py`

```python
def parse_cds_order(
    raw: dict[str, str],
) -> Ok[CanonicalOrder] | Err[ValidationError]:
    """Parse raw CDS order into CanonicalOrder with CDSDetail.

    Required fields: reference_entity, spread_bps, seniority,
    protection_side, start_date, maturity_date.
    """
    ...

def parse_swaption_order(
    raw: dict[str, str],
) -> Ok[CanonicalOrder] | Err[ValidationError]:
    """Parse raw swaption order into CanonicalOrder with SwaptionDetail.

    Required fields: swaption_type, expiry_date, underlying_fixed_rate,
    underlying_float_index, underlying_tenor_months, settlement_type.
    """
    ...
```

### Tests: `tests/test_gateway_credit.py`

- parse_cds_order: valid order produces CanonicalOrder with CDSDetail
- parse_cds_order: missing reference_entity -> Err
- parse_cds_order: invalid seniority string -> Err
- parse_cds_order: maturity_date <= start_date -> Err
- parse_cds_order: negative spread -> Err
- parse_swaption_order: valid order produces CanonicalOrder with SwaptionDetail
- parse_swaption_order: invalid swaption_type -> Err
- parse_swaption_order: negative underlying_fixed_rate -> Err
- parse_swaption_order: tenor_months <= 0 -> Err
- Both parsers: idempotent (INV-G01) -- parsing twice gives same result
- Both parsers: total (INV-G02) -- never raise, always return Ok or Err
- CDSDetail and SwaptionDetail correctly injected into order.instrument_detail

**Expected tests: ~20**

**Invariants verified:**
- INV-G01: Idempotent parsing
- INV-G02: Total function (no exceptions)

---

## Step 8 -- Ledger: CDS Premium and Protection Leg Booking

### New file: `attestor/ledger/cds.py`

CDS cashflow booking per math spec (PLAN.md Sections 4.2-4.6):

```python
@final @dataclass(frozen=True, slots=True)
class ScheduledCDSPremium:
    """A single scheduled CDS premium payment.

    Per math spec Section 4.2:
    Premium_j = N * s * dcf(T_{j-1}, T_j)
    """
    payment_date: date
    amount: Decimal
    currency: NonEmptyStr
    period_start: date
    period_end: date
    day_count_fraction: Decimal

def generate_cds_premium_schedule(
    notional: Decimal,
    spread: Decimal,
    effective_date: date,
    maturity_date: date,
    day_count: DayCountConvention,
    payment_frequency: PaymentFrequency,
    currency: str,
) -> Ok[tuple[ScheduledCDSPremium, ...]] | Err[str]:
    """Generate the CDS premium payment schedule.

    Per math spec Section 4.6: uses _generate_period_dates
    (shared with IRS from Phase 3). Day count = ACT/360 per ISDA.
    """
    ...

def create_cds_premium_transaction(
    instrument_id: str,
    buyer_account: str,     # protection buyer pays premium
    seller_account: str,    # protection seller receives premium
    premium: ScheduledCDSPremium,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Book a single CDS premium payment.

    Per math spec Section 4.4:
    Move(source=buyer, destination=seller, unit=currency, quantity=Premium)
    Conservation: sigma(currency) unchanged.
    """
    ...

def create_cds_credit_event_settlement(
    instrument_id: str,
    buyer_account: str,
    seller_account: str,
    notional: Decimal,
    auction_price: Decimal,
    currency: str,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Book credit event settlement after auction.

    Per math spec Section 4.3:
    Protection payment = notional * (1 - auction_price)
    Move: seller -> buyer (protection payment)

    Validation: 0 <= auction_price <= 1.
    """
    ...

def create_cds_maturity_close(
    instrument_id: str,
    buyer_position_account: str,
    seller_position_account: str,
    contract_unit: str,
    quantity: Decimal,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Close CDS position at maturity (no credit event).

    Move: position from buyer -> seller (close out).
    Conservation: sigma(contract_unit) returns to 0.
    """
    ...
```

### Tests: `tests/test_cds_ledger.py`

- Premium transaction: single Move, buyer -> seller, correct amount
- Premium conservation: sigma(currency) unchanged after execution
- Credit event settlement: protection_payment = notional * (1 - auction_price)
- Credit event conservation: sigma(currency) unchanged
- Credit event validation: auction_price > 1 -> Err
- Credit event validation: auction_price < 0 -> Err
- Credit event: 100% recovery (auction=1) -> zero payment
- Credit event: 0% recovery (auction=0) -> full notional payment
- Maturity close: position returned, sigma(contract_unit) == 0
- generate_cds_premium_schedule: quarterly, ACT/360 day count
- generate_cds_premium_schedule: correct number of periods
- generate_cds_premium_schedule: amount = notional * spread * dcf for each period
- All transactions accepted by LedgerEngine.execute()
- Hypothesis: random (notional, spread, auction_price) -> conservation (200 examples)

**Expected tests: ~25**

**Invariants verified:**
- CL-C1: CDS premium conservation (sigma(currency) == 0)
- CL-C2: CDS credit event conservation (sigma(currency) == 0)
- D.1 from math spec: sum of all moves in settlement = 0

---

## Step 9 -- Ledger: Swaption Exercise into IRS

### New file: `attestor/ledger/swaption.py`

Swaption booking per math spec (PLAN.md Sections 5.1-5.6):

```python
def create_swaption_premium_transaction(
    order: CanonicalOrder,
    buyer_cash_account: str,
    seller_cash_account: str,
    buyer_position_account: str,
    seller_position_account: str,
    tx_id: str,
) -> Ok[Transaction] | Err[ValidationError]:
    """Book swaption premium payment + position opening.

    Move 1: Cash (premium) buyer -> seller
    Move 2: Swaption position seller -> buyer (position opened)
    Conservation: sigma(cash) == 0, sigma(swaption_position) == 0
    """
    ...

def exercise_swaption_into_irs(
    swaption_payout: SwaptionPayoutSpec,
    exercise_date: date,
    parties: tuple[Party, ...],
    irs_instrument_id: str,
) -> Ok[Instrument] | Err[str]:
    """Create the underlying IRS instrument from swaption terms.

    Per math spec Section 5.3:
    - fixed_rate = swaption strike K
    - float_index, day_count, payment_frequency from underlying_swap
    - start_date = exercise_date (or next business day)
    - end_date = underlying swap maturity
    - notional = swaption notional

    The resulting IRS enters the Phase 3 lifecycle.
    """
    ...

def create_swaption_exercise_close(
    instrument_id: str,
    holder_position_account: str,
    writer_position_account: str,
    contract_unit: str,
    quantity: Decimal,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Close swaption position upon physical exercise.

    Move: position holder -> writer (close position)
    No cash movement for physical settlement.
    Conservation: sigma(swaption_position) returns to 0.
    """
    ...

def create_swaption_cash_settlement(
    instrument_id: str,
    holder_cash_account: str,
    writer_cash_account: str,
    holder_position_account: str,
    writer_position_account: str,
    settlement_amount: Decimal,
    currency: str,
    contract_unit: str,
    quantity: Decimal,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Cash-settled swaption exercise.

    Move 1: Cash (writer -> holder if ITM)
    Move 2: Close position (holder -> writer)
    Conservation: sigma(cash) == 0, sigma(position) == 0

    Per math spec Section 5.4: settlement_amount > 0.
    """
    ...

def create_swaption_expiry_close(
    instrument_id: str,
    holder_position_account: str,
    writer_position_account: str,
    contract_unit: str,
    quantity: Decimal,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Expire unexercised swaption. Close position, no cash movement."""
    ...
```

### Tests: `tests/test_swaption_ledger.py`

- Premium: cash + position opened (2 Moves)
- Premium conservation: sigma(cash) == 0, sigma(swaption_position) == 0
- exercise_swaption_into_irs: payer swaption -> valid IRS instrument
- exercise_swaption_into_irs: receiver swaption -> valid IRS instrument
- exercise_swaption_into_irs: IRS fixed_rate matches swaption strike
- exercise_swaption_into_irs: IRS start_date matches exercise_date
- exercise_swaption_into_irs: IRS end_date matches underlying_swap end
- Physical exercise close: position returned, sigma(position) == 0
- Cash settlement: 2 Moves (cash + position close)
- Cash settlement conservation: sigma(cash) == 0, sigma(position) == 0
- Expiry close: position returned, no cash, sigma(position) == 0
- Reject non-swaption payout in exercise_swaption_into_irs
- IRS from exercise accepted by Phase 3 IRS lifecycle (smoke test)

**Expected tests: ~22**

**Invariants verified:**
- CL-C4: Swaption premium conservation
- CL-C5: Swaption exercise conservation
- CL-C6: Swaption cash settlement conservation
- D.3 from math spec: swaption exercise conservation

---

## Step 10 -- Ledger: Collateral Management

### New file: `attestor/ledger/collateral.py`

Collateral booking per math spec (PLAN.md Section 6):

```python
class CollateralType(Enum):
    CASH = "CASH"
    GOVERNMENT_BOND = "GOVERNMENT_BOND"
    CORPORATE_BOND = "CORPORATE_BOND"
    EQUITY = "EQUITY"

@final @dataclass(frozen=True, slots=True)
class CollateralAgreement:
    """CSA/ISDA collateral agreement parameters.

    Per math spec Section 6.4.
    """
    agreement_id: NonEmptyStr
    party_a: NonEmptyStr
    party_b: NonEmptyStr
    eligible_collateral: tuple[CollateralType, ...]
    threshold_a: Decimal          # >= 0
    threshold_b: Decimal          # >= 0
    minimum_transfer_amount: Decimal  # >= 0
    currency: NonEmptyStr

    @staticmethod
    def create(...) -> Ok[CollateralAgreement] | Err[str]: ...

def create_margin_call_transaction(
    agreement_id: str,
    caller_account: str,
    poster_account: str,
    collateral_unit: str,
    quantity: Decimal,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Book collateral delivery after margin call.

    Move: collateral from poster -> caller.
    Conservation: sigma(collateral_unit) unchanged.
    """
    ...

def create_collateral_return_transaction(
    agreement_id: str,
    returner_account: str,
    receiver_account: str,
    collateral_unit: str,
    quantity: Decimal,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Book collateral return (exposure decreased).

    Move: collateral from returner -> receiver.
    Conservation: sigma(collateral_unit) unchanged.
    """
    ...

def create_collateral_substitution_transaction(
    agreement_id: str,
    poster_account: str,
    holder_account: str,
    old_collateral_unit: str,
    old_quantity: Decimal,
    new_collateral_unit: str,
    new_quantity: Decimal,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Book collateral substitution.

    Per math spec Section 6.5:
    Move 1: old collateral holder -> poster (return)
    Move 2: new collateral poster -> holder (delivery)
    Conservation: sigma(old_unit) unchanged, sigma(new_unit) unchanged.
    """
    ...
```

### Tests: `tests/test_collateral.py`

- CollateralAgreement.create: valid, all fields populated
- CollateralAgreement.create: reject negative thresholds
- CollateralAgreement.create: reject negative MTA
- CollateralType enum: all 4 values
- Margin call: single Move, poster -> caller
- Margin call conservation: sigma(collateral_unit) unchanged
- Collateral return: single Move, returner -> receiver
- Return conservation: sigma(collateral_unit) unchanged
- Substitution: 2 Moves, old returned and new delivered
- Substitution conservation: sigma(old_unit) unchanged AND sigma(new_unit) unchanged
- Margin call with zero quantity -> Err
- All transactions accepted by LedgerEngine.execute()
- Hypothesis: random collateral amounts -> conservation (200 examples)

**Expected tests: ~25**

**Invariants verified:**
- CL-C7: Collateral conservation per unit
- CL-C8: Collateral substitution conservation
- D.2 from math spec: collateral securities not created or destroyed

---

## Step 11 -- Reporting Extensions

### Modify: `attestor/reporting/mifid2.py`

Add CDS and swaption report fields and extend pattern match:

```python
@final @dataclass(frozen=True, slots=True)
class CDSReportFields:
    """CDS-specific reporting fields."""
    reference_entity: str
    spread_bps: Decimal
    seniority: str
    protection_side: str

@final @dataclass(frozen=True, slots=True)
class SwaptionReportFields:
    """Swaption-specific reporting fields."""
    swaption_type: str
    expiry_date: date
    underlying_fixed_rate: Decimal
    underlying_tenor_months: int
    settlement_type: str

@final @dataclass(frozen=True, slots=True)
class CollateralReportFields:
    """Collateral-specific reporting fields."""
    agreement_id: str
    collateral_type: str
    quantity: Decimal
    currency: str

# Updated union:
type InstrumentReportFields = (
    OptionReportFields | FuturesReportFields
    | FXReportFields | IRSwapReportFields
    | CDSReportFields | SwaptionReportFields
    | CollateralReportFields | None
)
```

### New file: `attestor/reporting/dodd_frank.py`

```python
@final @dataclass(frozen=True, slots=True)
class DoddFrankSwapReport:
    """Dodd-Frank swap data report -- covers CDS and swaptions."""
    usi: NonEmptyStr                     # Unique Swap Identifier
    reporting_counterparty_lei: LEI
    non_reporting_counterparty_lei: LEI
    instrument_id: NonEmptyStr
    asset_class: NonEmptyStr             # "CREDIT" or "INTEREST_RATE"
    product_type: NonEmptyStr            # "CDS" or "SWAPTION"
    notional: Decimal
    currency: NonEmptyStr
    effective_date: date
    maturity_date: date
    report_timestamp: UtcDatetime
    attestation_refs: tuple[str, ...]
    reference_entity: NonEmptyStr | None  # CDS only
    spread_bps: Decimal | None            # CDS only
    expiry_date: date | None              # Swaption only
    underlying_fixed_rate: Decimal | None  # Swaption only

def project_dodd_frank_report(
    order: CanonicalOrder,
    trade_attestation_id: str,
) -> Ok[Attestation[DoddFrankSwapReport]] | Err[str]:
    """Project Dodd-Frank report from CDS or swaption order.

    INV-R01: pure projection, no new values computed.
    Returns Err for non-CDS/non-swaption orders.
    """
    ...
```

### Modify: `attestor/reporting/emir.py`

Extend `project_emir_report` pattern match to handle CDSDetail and SwaptionDetail.

### Tests: `tests/test_reporting_credit.py`

- MiFID II with CDSDetail -> CDSReportFields populated
- MiFID II with SwaptionDetail -> SwaptionReportFields populated
- Dodd-Frank CDS report: all CDS fields populated, swaption fields None
- Dodd-Frank swaption report: all swaption fields populated, CDS fields None
- Dodd-Frank: non-CDS/non-swaption order -> Err
- Dodd-Frank: USI generated from content hash
- EMIR with CDS order: accepted, correct field mapping
- EMIR with swaption order: accepted, correct field mapping
- INV-R01: projection only, no new values computed
- Report attestation provenance contains trade_attestation_id
- CollateralReportFields construction and immutability

**Expected tests: ~20**

**Invariants verified:**
- INV-R01: Reporting is projection only
- INV-07: Regulatory isomorphism

---

## Step 12 -- Pricing Stub Extension

### Modify: `attestor/pricing/types.py`

Add credit-specific PV components:

```python
@final @dataclass(frozen=True, slots=True)
class ValuationResult:
    instrument_id: str
    npv: Decimal
    currency: str
    valuation_date: UtcDatetime
    components: FrozenMap[str, Decimal] = FrozenMap.EMPTY
    model_config_id: str = ""
    market_snapshot_id: str = ""
    fixed_leg_pv: Decimal = Decimal("0")
    floating_leg_pv: Decimal = Decimal("0")
    # Phase 4 additions:
    premium_leg_pv: Decimal = Decimal("0")     # CDS premium leg
    protection_leg_pv: Decimal = Decimal("0")  # CDS protection leg
```

### Tests: `tests/test_pricing_credit.py`

- StubPricingEngine.price with CDS instrument_id -> Ok
- StubPricingEngine.price with swaption instrument_id -> Ok
- StubPricingEngine.greeks with CDS instrument_id -> Ok (all zero)
- ValuationResult with premium_leg_pv and protection_leg_pv fields
- Master Square: price(id) deterministic for CDS/swaption stubs

**Expected tests: ~8**

**Invariants verified:**
- CS-C1, CS-C2: Master Square holds for stubs

---

## Step 13 -- Infrastructure (Kafka Topics + Postgres Tables)

### Modify: `attestor/infra/config.py`

Per MASTER_PLAN Phase 4 scope:

```python
# Phase 4 topics
TOPIC_VOL_SURFACES: str = "attestor.oracle.vol_surfaces"
TOPIC_CREDIT_CURVES: str = "attestor.oracle.credit_curves"
TOPIC_COLLATERAL: str = "attestor.ledger.collateral"
TOPIC_CREDIT_EVENTS: str = "attestor.lifecycle.credit_events"

PHASE4_TOPICS: frozenset[str] = frozenset({
    TOPIC_VOL_SURFACES, TOPIC_CREDIT_CURVES,
    TOPIC_COLLATERAL, TOPIC_CREDIT_EVENTS,
})

def phase4_topic_configs() -> tuple[TopicConfig, ...]:
    """Return topic configs for the four Phase 4 topics."""
    ...
```

### SQL files (4 new):

**`sql/018_vol_surfaces.sql`** -- calibrated vol surface store
**`sql/019_credit_curves.sql`** -- credit curve store
**`sql/020_collateral_balances.sql`** -- collateral positions per agreement
**`sql/021_credit_events.sql`** -- credit event history

All tables: `attestor.` schema prefix, `prevent_mutation` trigger, bitemporal
(`valid_time`, `system_time`).

### Tests: `tests/test_infra_phase4.py`

- Phase 4 topic constants: all 4 defined, no duplicates
- PHASE4_TOPICS frozenset has 4 elements
- phase4_topic_configs: 4 configs, valid names, correct retention
- No overlap with Phase 0/1/2/3 topic names
- Vol surfaces SQL: table definition consistent with VolSurface type
- Credit curves SQL: table definition consistent with CreditCurve type
- Collateral balances SQL: CHECK constraint on collateral_type
- Credit events SQL: CHECK constraint on event_type

**Expected tests: ~14**

---

## Step 14 -- Invariant Tests

### New file: `tests/test_invariants_credit.py`

**Conservation Laws:**

```
CL-C1: CDS Premium Conservation (Hypothesis, 200 examples)
    For every CDS premium payment: sigma(currency) unchanged.
    Strategy: random (notional in [1k, 100M], spread in [1bp, 500bp]) -> book premium -> verify.

CL-C2: CDS Credit Event Settlement Conservation (Hypothesis, 200 examples)
    For every credit event settlement: sigma(currency) unchanged.
    Strategy: random (notional, auction_price in [0, 1]) -> book settlement -> verify.

CL-C3: CDS Full Lifecycle Conservation
    Trade -> 4 quarterly premiums -> credit event -> settlement.
    sigma(currency) == 0 at each step. Fixed example with known amounts.

CL-C4: Swaption Premium Conservation (Hypothesis, 200 examples)
    sigma(cash) == 0, sigma(swaption_position) == 0 after premium.

CL-C5: Swaption Exercise Conservation
    sigma(swaption_position) returns to 0 after exercise.
    Physical: verify IRS enters Phase 3 lifecycle.

CL-C6: Swaption Cash Settlement Conservation
    sigma(cash) == 0, sigma(position) == 0 after cash-settled exercise.

CL-C7: Collateral Conservation (Hypothesis, 200 examples)
    For every collateral movement (call, return):
    sigma(collateral_unit) unchanged per unit.

CL-C8: Collateral Substitution Conservation
    Old returned AND new delivered:
    sigma(old_unit) unchanged AND sigma(new_unit) unchanged.
```

**Arbitrage-Freedom Invariants:**

```
INV-AF-VS: Vol surface from calibrate_vol_surface passes all AF-VS gates
INV-AF-CR: Credit curve from bootstrap_credit_curve passes all AF-CR gates
```

**Commutativity Squares:**

```
CS-C1: CDS Master Square -- book then stub-price == stub-price then book
CS-C2: Swaption Master Square -- same
CS-C3: CDS reporting naturality -- project then lifecycle == lifecycle then project
CS-C4: Swaption exercise commutativity -- exercise then IRS lifecycle is deterministic
CS-C5: Calibration commutativity -- same CDS quotes produce same credit curve
CS-C6: Calibration commutativity -- same vol quotes produce same VolSurface
```

**Expected tests: ~28**

---

## Step 15 -- Integration Tests

### New file: `tests/test_integration_credit.py`

**Full CDS Lifecycle (12 steps):**

1. Parse CDS order -> CanonicalOrder with CDSDetail
2. Create CDS instrument -> Instrument with CDSPayoutSpec
3. Generate premium schedule -> scheduled premium payments
4. Ingest CDS spread quote -> Attestation[CDSSpreadQuote]
5. Book CDS trade (open position) -> LedgerEngine.execute()
6. Book premium payment (period 1) -> execute(), verify sigma(currency)==0
7. Ingest credit event -> Attestation[CreditEventRecord]
8. Ingest auction result -> Attestation[AuctionResult]
9. Book credit event settlement -> execute(), verify sigma(currency)==0
10. Close CDS position -> execute(), verify sigma(contract_unit)==0
11. Verify lifecycle: PROPOSED -> FORMED -> SETTLED -> CLOSED
12. Project reports: EMIR + Dodd-Frank + MiFID II all produce valid reports

**Full Swaption Lifecycle -- Physical (10 steps):**

1. Parse swaption order -> CanonicalOrder with SwaptionDetail
2. Create swaption instrument -> Instrument with SwaptionPayoutSpec
3. Book swaption premium (cash + position) -> execute()
4. Exercise swaption (physical) -> close swaption position
5. exercise_swaption_into_irs -> creates valid IRS with correct terms
6. Verify IRS fixed_rate == swaption strike
7. IRS rate fixing -> apply_rate_fixing (Phase 3 machinery)
8. IRS cashflow exchange -> execute()
9. IRS maturity -> execute()
10. Full lifecycle conservation verified at every step

**Full Collateral Lifecycle (6 steps):**

1. Create CollateralAgreement
2. Margin call -> collateral delivery transaction -> execute()
3. Additional margin call -> second delivery -> execute()
4. Collateral return -> execute()
5. Collateral substitution (bonds for cash) -> execute()
6. All units balanced: sigma == 0 per unit per step

**Full Credit Curve Calibration Pipeline (6 steps):**

1. Create CDSQuote instruments (1Y, 3Y, 5Y, 7Y, 10Y)
2. Bootstrap credit curve -> Attestation[CreditCurve]
3. Run credit curve arbitrage gates -> all CRITICAL pass
4. Verify survival probability interpolation at 2Y, 4Y
5. Inject invalid quote -> calibration produces curve with bad properties
6. Handle failure (re-use Phase 3 fallback pattern)

**Full Vol Surface Calibration Pipeline (6 steps):**

1. Create synthetic total variance quotes at 2 expiries
2. Calibrate vol surface -> Attestation[VolSurface]
3. Run vol surface arbitrage gates -> all pass
4. Verify implied vol interpolation between expiries
5. Inject pathological quotes (extreme skew) -> gate failure
6. Handle failure via fallback

**Import smoke tests:**
- All new modules importable
- All new types constructible
- All new functions callable with minimal valid inputs

**Engine untouched verification:**
- engine.py has zero CDS/swaption/collateral keywords (excluding `__future__`)

**Expected tests: ~55**

---

## Step 16 -- Re-exports and Package Init Updates

### Modify: `attestor/instrument/__init__.py`

Re-export: CreditEventType, SeniorityLevel, ProtectionSide, SwaptionType,
CDSPayoutSpec, SwaptionPayoutSpec, CDSDetail, SwaptionDetail,
create_cds_instrument, create_swaption_instrument.

### Modify: `attestor/oracle/__init__.py`

Re-export: CreditCurve, CDSQuote, survival_probability, hazard_rate,
bootstrap_credit_curve, VolSurface, SVIParameters, svi_total_variance,
implied_vol, calibrate_vol_surface, CDSSpreadQuote, CreditEventRecord,
AuctionResult, ingest functions, check_vol_surface_arbitrage_freedom,
check_credit_curve_arbitrage_freedom.

### Modify: `attestor/reporting/__init__.py`

Re-export: CDSReportFields, SwaptionReportFields, CollateralReportFields,
DoddFrankSwapReport, project_dodd_frank_report.

### Modify: `attestor/ledger/__init__.py`

Re-export: CDS ledger functions, swaption ledger functions,
exercise_swaption_into_irs, collateral types and functions.

### Modify: `attestor/infra/__init__.py`

Re-export Phase 4 topic constants and phase4_topic_configs.

### Modify: `attestor/core/__init__.py`

Re-export decimal_math functions.

---

## Test Budget

| Step | Description | Expected tests |
|------|------------|---------------|
| 0 | Decimal math utilities | ~20 |
| 1 | CDS/swaption instrument types | ~35 |
| 2 | CDS/swaption lifecycle | ~20 |
| 3 | Credit curve types + bootstrapping | ~22 |
| 4 | Vol surface types + SVI calibration | ~25 |
| 5 | Vol + credit arbitrage gates | ~28 |
| 6 | Credit and vol ingestion | ~18 |
| 7 | Gateway CDS/swaption parsers | ~20 |
| 8 | CDS premium + protection ledger | ~25 |
| 9 | Swaption exercise into IRS | ~22 |
| 10 | Collateral management | ~25 |
| 11 | Reporting extensions | ~20 |
| 12 | Pricing stub extension | ~8 |
| 13 | Infrastructure | ~14 |
| 14 | Invariant tests | ~28 |
| 15 | Integration tests | ~55 |
| 16 | Re-exports | ~0 (covered by smoke) |
| **Total new** | | **~385** |
| **Running total** | 1004 + 385 | **~1389** |

---

## Source Line Budget

| File | Est. lines | Notes |
|------|-----------|-------|
| `core/decimal_math.py` | ~150 | exp_d, ln_d, sqrt_d, expm1_neg_d |
| `instrument/credit_types.py` | ~200 | CDSPayoutSpec, SwaptionPayoutSpec + enums |
| `instrument/derivative_types.py` (extend) | +100 | CDSDetail, SwaptionDetail |
| `instrument/types.py` (extend) | +80 | Payout union, 2 factory functions |
| `instrument/lifecycle.py` (extend) | +60 | 3 new PI variants, 2 transition tables |
| `gateway/parser.py` (extend) | +80 | 2 new parser functions |
| `oracle/credit_curve.py` | ~250 | CreditCurve, bootstrap, CDSQuote |
| `oracle/vol_surface.py` | ~350 | SVIParameters, VolSurface, SVI math, calibrate |
| `oracle/arbitrage_gates.py` (extend) | +200 | AF-VS and AF-CR gates |
| `oracle/credit_ingest.py` | ~150 | CDSSpreadQuote, CreditEventRecord, AuctionResult |
| `ledger/cds.py` | ~200 | Premium, credit event, maturity, schedule |
| `ledger/swaption.py` | ~250 | Premium, exercise, IRS creation, cash settlement, expiry |
| `ledger/collateral.py` | ~200 | Agreement, margin call, return, substitution |
| `reporting/mifid2.py` (extend) | +60 | CDS/Swaption/CollateralReportFields |
| `reporting/dodd_frank.py` | ~120 | DoddFrankSwapReport, projection function |
| `reporting/emir.py` (extend) | +10 | CDS/swaption pattern match |
| `pricing/types.py` (extend) | +10 | premium_leg_pv, protection_leg_pv |
| `infra/config.py` (extend) | +30 | 4 topics, phase4_topic_configs |
| SQL files (4 new) | ~80 | Postgres tables |
| **Total new source** | **~2580** | Under 5,000 line budget |

---

## Dependency Graph

```
Step 0  (decimal_math)
  |
  +-> Step 3  (credit curve -- uses ln_d, exp_d)
  |     |
  |     +-> Step 5  (arbitrage gates -- credit)
  |     +-> Step 6  (credit ingest)
  |
  +-> Step 4  (vol surface -- uses sqrt_d)
        |
        +-> Step 5  (arbitrage gates -- vol)

Step 1  (types)
  |
  +-> Step 2  (lifecycle)
  |     |
  |     +-> Step 7  (gateway parsers)
  |     +-> Step 8  (CDS ledger)
  |     +-> Step 9  (swaption ledger)
  |     +-> Step 10 (collateral)
  |
  +-> Step 3  (credit curve uses CDSPayoutSpec day_count/freq)
  +-> Step 4  (vol surface types)

Steps 5-10 complete
  |
  +-> Step 11 (reporting -- needs all detail types)
  +-> Step 12 (pricing stubs)
  +-> Step 13 (infrastructure)
  |
  +-> Step 14 (invariant tests -- needs all ledger + oracle)
  +-> Step 15 (integration tests -- needs everything)
  +-> Step 16 (re-exports)
```

---

## Key Invariants to Verify

| ID | Property | Test mechanism |
|----|----------|---------------|
| INV-L01 | sigma(U) = 0 for every unit U per execute | Hypothesis |
| AF-VS-01 | Calendar spread: w(k,T2) >= w(k,T1) | Grid check |
| AF-VS-02 | Durrleman: g(k) >= 0 | Grid check with analytic derivatives |
| AF-VS-03 | Roger Lee (right): b*(1+rho) <= 2 | SVI parameter constraint |
| AF-VS-04 | Roger Lee (left): b*(1-rho) <= 2 | SVI parameter constraint |
| AF-VS-05 | Positive variance: w(k,T) > 0 | Grid check |
| AF-VS-06 | ATM monotonicity | Sequential comparison |
| AF-CR-01 | 0 < Q(t) <= 1 | Construction + gate |
| AF-CR-02 | Q(0) = 1 | Construction |
| AF-CR-03 | Monotone survival | Construction + gate |
| AF-CR-04 | Non-negative hazard | Construction + gate |
| CL-C2 | protection + recovery = notional | Ledger test |
| D.2 | Collateral conservation | Hypothesis |
| D.3 | Swaption exercise conservation | Ledger test |
| INV-O02 | ModelConfig immutable | Frozen dataclass |
| INV-R01 | Reporting is projection only | No-new-value test |
| Parametric | engine.py unchanged | Keyword check |

---

## Files That MUST NOT Be Modified

- `attestor/ledger/engine.py` (Principle V: parametric polymorphism)
- `attestor/core/result.py` (foundation)
- `attestor/core/serialization.py` (foundation)
- `attestor/core/errors.py` (foundation -- may extend with new error subclasses only)

---

## Dependencies

Phase 3 must be fully passing (~1004 tests) before Phase 4 begins.
No new external library additions beyond what Phase 3 uses.
Python stdlib `decimal`, `datetime`, `enum`, `dataclasses`, `typing` only
(plus `dateutil.relativedelta` already in use from Phase 3).
