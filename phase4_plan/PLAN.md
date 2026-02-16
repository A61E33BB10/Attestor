# Phase 4 -- Credit and Structured Products: Financial Mathematics Specification

**Author:** Gatheral (Pillar III Mathematical Specification)
**Date:** 2026-02-15
**Status:** Draft -- For Committee Review
**Scope:** Oracle (Pillar III) calibration mathematics only. NO pricing models.

---

## Table of Contents

1. [SVI Parameterisation](#1-svi-parameterisation)
2. [SSVI Surface](#2-ssvi-surface)
3. [Credit Curve Bootstrap](#3-credit-curve-bootstrap)
4. [CDS Cashflow Mathematics](#4-cds-cashflow-mathematics)
5. [Swaption Exercise](#5-swaption-exercise)
6. [Collateral Valuation](#6-collateral-valuation)
7. [Arbitrage Gates](#7-arbitrage-gates)
8. [Numerical Considerations](#8-numerical-considerations)

---

## 1. SVI Parameterisation

### 1.1 Raw SVI Formula

The Stochastic Volatility Inspired (SVI) parameterisation gives total implied variance `w(k)` as a function of log-moneyness `k = ln(K/F)`, where `K` is the strike and `F` is the forward price.

**Raw SVI:**

```
w(k) = a + b * (rho * (k - m) + sqrt((k - m)^2 + sigma^2))
```

where `w(k) = sigma_BS^2(k) * T` is the total implied variance (implied Black-Scholes variance times time to expiry).

**Parameters (5):**

| Parameter | Domain | Economic Meaning |
|-----------|--------|-----------------|
| `a` | See constraint below | Overall variance level |
| `b` | `b >= 0` | Slope of the wings (controls how fast variance grows with moneyness) |
| `rho` | `-1 < rho < 1` | Skew (correlation between spot and vol; controls smile asymmetry) |
| `m` | `R` | Translation of the smile minimum along the log-moneyness axis |
| `sigma` | `sigma > 0` | Curvature at the vertex (controls smile width at the minimum) |

### 1.2 SVI Parameter Constraints

These constraints are necessary and sufficient for the SVI slice to be well-defined and to satisfy the Roger Lee moment formula bounds.

**C-SVI-01: Positive variance at the vertex.**

```
a + b * sigma * sqrt(1 - rho^2) >= 0
```

This ensures `w(k) >= 0` for all `k`. The minimum of `w(k)` is attained at `k = m - rho * sigma / sqrt(1 - rho^2)` and equals `a + b * sigma * sqrt(1 - rho^2)`.

**C-SVI-02: Non-negative slope.**

```
b >= 0
```

**C-SVI-03: Correlation bound.**

```
|rho| < 1
```

Strict inequality. At `rho = +/- 1` the parameterisation degenerates (the square root collapses to a piecewise linear function with a kink, and the minimum variance becomes `a` which may violate positivity without additional constraints).

**C-SVI-04: Positive curvature.**

```
sigma > 0
```

At `sigma = 0` the parameterisation becomes piecewise linear with a kink at `k = m`, which is non-differentiable and produces a Dirac mass in the implied density.

**C-SVI-05: Roger Lee wing bound.**

The asymptotic slope of `w(k)/|k|` as `k -> +/- infinity` must not exceed 2. For raw SVI:

```
lim_{k -> +inf} w(k) / k = b * (1 + rho)
lim_{k -> -inf} w(k) / |k| = b * (1 - rho)
```

Therefore:

```
b * (1 + |rho|) <= 2
```

This is a single constraint that covers both wings simultaneously.

### 1.3 SVI Derivatives

Required for the Durrleman condition (butterfly arbitrage check) and for Greeks computation.

**First derivative:**

```
w'(k) = dw/dk = b * (rho + (k - m) / sqrt((k - m)^2 + sigma^2))
```

**Second derivative:**

```
w''(k) = d^2w/dk^2 = b * sigma^2 / ((k - m)^2 + sigma^2)^(3/2)
```

Note that `w''(k) > 0` for all `k` when `b > 0` and `sigma > 0`, meaning the raw SVI slice is always convex. This is an important structural property.

### 1.4 Calibration Algorithm

**Input:** A set of `N` market-observed option prices for a single expiry `T`, each converted to total implied variance `w_i^mkt` at log-moneyness `k_i`. These arrive as `tuple[Attestation[OptionQuote], ...]`.

**Objective:** Minimise the weighted sum of squared errors:

```
L(a, b, rho, m, sigma) = sum_{i=1}^{N} omega_i * (w(k_i; a, b, rho, m, sigma) - w_i^mkt)^2
```

where `omega_i` are weights. Default weighting: `omega_i = 1 / vega_i^2` (vega-weighted, so that liquid ATM options contribute most).

**Constrained optimisation:** Subject to C-SVI-01 through C-SVI-05.

**Algorithm: Sequential Least Squares (two-stage).**

Stage 1: Fix `(m, sigma)` on a grid. For each grid point, the problem in `(a, b, rho)` is a linearly-constrained least squares problem (SVI is linear in `a`, and linear in `b*rho` and `b` given the square root term). Solve analytically or via a small QP.

Stage 2: Refine the best grid point using L-BFGS-B with box constraints:
- `a`: lower bound from C-SVI-01 (dependent on other params)
- `b`: `[0, 2 / (1 + |rho|)]`
- `rho`: `(-1 + eps, 1 - eps)` where `eps = 1e-6`
- `m`: `[k_min - 1, k_max + 1]` (bounded around the data)
- `sigma`: `[eps, 5 * max(|k_i - mean(k)|)]`

**Convergence criterion:** `|L_{n+1} - L_n| / max(|L_n|, 1) < 1e-12` (Decimal precision supports this).

**Fit quality metrics (stored in DerivedConfidence.fit_quality):**

```
rmse = sqrt(L / N)
max_abs_error = max_i |w(k_i) - w_i^mkt|
mean_abs_error = (1/N) * sum_i |w(k_i) - w_i^mkt|
```

Threshold: `rmse < 1e-4` in total variance units (roughly 0.5 vol point for 1Y options). If exceeded, calibration failure is raised and fallback to last-good surface applies (III-08 pattern).

### 1.5 SVI Data Type

```python
@final
@dataclass(frozen=True, slots=True)
class SVISlice:
    """Calibrated SVI parameters for a single expiry slice."""
    a: Decimal
    b: Decimal      # >= 0
    rho: Decimal     # (-1, 1)
    m: Decimal
    sigma: Decimal   # > 0
    expiry: Decimal  # T in year fractions, > 0

    @staticmethod
    def create(
        a: Decimal, b: Decimal, rho: Decimal,
        m: Decimal, sigma: Decimal, expiry: Decimal,
    ) -> Ok[SVISlice] | Err[str]:
        # Validate C-SVI-01 through C-SVI-05
        ...
```

The `create` factory enforces all five constraints. If any constraint fails, the SVI slice is not constructible. This is the "make illegal states unrepresentable" principle applied to volatility surfaces.

---

## 2. SSVI Surface

### 2.1 Motivation

Raw SVI calibrates each expiry slice independently. This does not guarantee calendar spread freedom across expiries. The Surface SVI (SSVI) parameterisation of Gatheral and Jacquier (2014) solves this by parameterising the entire surface jointly, with built-in conditions for calendar spread arbitrage freedom.

### 2.2 SSVI Formula

```
w(k, T) = (theta(T) / 2) * (1 + rho * phi(theta(T)) * k
           + sqrt((phi(theta(T)) * k + rho)^2 + (1 - rho^2)))
```

where:
- `theta(T) = sigma_ATM^2(T) * T` is the ATM total variance at expiry `T`
- `phi(theta)` is a function controlling how the smile shape varies with the ATM level
- `rho` is the global correlation parameter (`-1 < rho < 1`)

### 2.3 The Function phi(theta)

The standard choice (power-law):

```
phi(theta) = eta / (theta^gamma * (1 + theta)^(1 - gamma))
```

with `eta > 0` and `0 < gamma <= 1`. This gives two additional parameters beyond those in `theta(T)`.

Alternative (Heston-like):

```
phi(theta) = 1 / (lambda * theta) * (1 - (1 - exp(-lambda * theta)) / (lambda * theta))
```

We implement the power-law form. The `gamma = 0.5` case reduces to `phi(theta) = eta / sqrt(theta * (1 + theta))` which is particularly tractable.

### 2.4 ATM Total Variance: theta(T)

`theta(T)` is an input curve, not an SSVI parameter. It is interpolated from the market-observed ATM total variances at available expiries.

**Interpolation:** Piecewise linear in `theta` vs `T`, with the constraint that `theta(T)` is non-decreasing.

**Construction:**

1. For each market expiry `T_j`, compute `theta_j = sigma_ATM_j^2 * T_j` from the at-the-money implied volatility.
2. Verify monotonicity: `theta_{j+1} >= theta_j` for all `j`. If violated, flag as AF-VS-06 violation.
3. For intermediate `T`, interpolate linearly between adjacent `(T_j, theta_j)` pairs.
4. Extrapolation: flat beyond the last expiry (`theta(T) = theta_N` for `T > T_N`).

**Data type:**

```python
@final
@dataclass(frozen=True, slots=True)
class ThetaCurve:
    """ATM total variance curve, guaranteed non-decreasing."""
    expiries: tuple[Decimal, ...]   # T_1 < T_2 < ... < T_N, all > 0
    theta_values: tuple[Decimal, ...]  # theta_1 <= theta_2 <= ... <= theta_N, all > 0
```

### 2.5 SSVI Parameter Constraints

**C-SSVI-01: theta monotonicity.** `theta(T)` non-decreasing in `T`. (Already enforced in ThetaCurve construction.)

**C-SSVI-02: Butterfly sufficient condition.**

```
theta * phi(theta) * (1 + |rho|) < 4    for all theta in range
```

This is a sufficient condition for the absence of butterfly arbitrage under SSVI. It ensures `g(k) >= 0` for all `k`.

**C-SSVI-03: Calendar spread sufficient condition.**

```
theta * phi(theta)^2 * (1 + |rho|) <= 4    for all theta in range
```

This, combined with C-SSVI-01, is sufficient for the absence of calendar spread arbitrage.

**C-SSVI-04: Global parameter bounds.** `eta > 0`, `0 < gamma <= 1`, `-1 < rho < 1`.

### 2.6 SSVI Derivatives

**First derivative with respect to k:**

```
dw/dk = (theta / 2) * (rho * phi + phi * (phi * k + rho) / sqrt((phi * k + rho)^2 + (1 - rho^2)))
```

**Second derivative with respect to k:**

```
d^2w/dk^2 = (theta / 2) * phi^2 * (1 - rho^2) / ((phi * k + rho)^2 + (1 - rho^2))^(3/2)
```

Note: `d^2w/dk^2 > 0` for all `k` when `|rho| < 1`, confirming convexity of each SSVI slice.

### 2.7 SSVI Calibration

**Input:** ATM total variances `theta_j` at expiries `T_j`, plus option quotes across strikes and expiries.

**Parameters to calibrate:** `(rho, eta, gamma)` -- only 3 parameters for the entire surface.

**Objective:**

```
L(rho, eta, gamma) = sum_{j=1}^{M} sum_{i=1}^{N_j} omega_{ij} * (w_SSVI(k_{ij}, T_j) - w_{ij}^mkt)^2
```

**Algorithm:** L-BFGS-B with box constraints:
- `rho`: `(-1 + eps, 1 - eps)`
- `eta`: `(eps, 10)`
- `gamma`: `(eps, 1)`

At each evaluation, verify C-SSVI-02 and C-SSVI-03 for all `theta_j` values. If violated, impose a large penalty.

**Fit quality metrics:**

```
rmse = sqrt(L / sum(N_j))
max_slice_rmse = max_j sqrt(L_j / N_j)
calendar_spread_margin = min_{theta} (4 - theta * phi(theta) * (1 + |rho|))
butterfly_margin = min_{theta} (4 - theta * phi(theta)^2 * (1 + |rho|))
```

### 2.8 SSVI Data Type

```python
@final
@dataclass(frozen=True, slots=True)
class SSVISurface:
    """Calibrated SSVI volatility surface."""
    rho: Decimal         # (-1, 1)
    eta: Decimal         # > 0
    gamma: Decimal       # (0, 1]
    theta_curve: ThetaCurve
    underlying_id: NonEmptyStr
    as_of: date
    model_config_ref: str
```

### 2.9 VolSurface Wrapper

The Oracle publishes `Attestation[VolSurface]` where `VolSurface` is:

```python
@final
@dataclass(frozen=True, slots=True)
class VolSurface:
    """Attestable volatility surface. Union of representations."""
    underlying_id: NonEmptyStr
    as_of: date
    representation: SVISliceSet | SSVISurface
    model_config_ref: str

@final
@dataclass(frozen=True, slots=True)
class SVISliceSet:
    """Multiple calibrated SVI slices (one per expiry)."""
    slices: tuple[SVISlice, ...]  # Sorted by expiry
```

---

## 3. Credit Curve Bootstrap

### 3.1 The Reduced-Form Credit Model

We adopt the standard reduced-form (intensity) model. The reference entity defaults at a random time `tau` governed by a hazard rate process `lambda(t)`. The survival probability is:

```
Q(t) = P(tau > t) = exp(-integral_0^t lambda(s) ds)
```

### 3.2 Piecewise Constant Hazard Rate

For tractability and ISDA standard model alignment, we assume `lambda(t)` is piecewise constant on the intervals defined by the CDS tenor points.

Given CDS tenors `T_1 < T_2 < ... < T_N`, define:

```
lambda(t) = lambda_j    for T_{j-1} < t <= T_j
```

where `T_0 = 0`.

The survival probability at tenor `T_j` is then:

```
Q(T_j) = exp(-sum_{i=1}^{j} lambda_i * (T_i - T_{i-1}))
```

or equivalently, recursively:

```
Q(T_j) = Q(T_{j-1}) * exp(-lambda_j * (T_j - T_{j-1}))
```

with `Q(0) = 1`.

### 3.3 Bootstrap from CDS Spreads

**Input:** Par CDS spreads `s_1, s_2, ..., s_N` at tenors `T_1, T_2, ..., T_N`, a recovery rate `R` (typically `0.4` for senior unsecured), and a risk-free discount curve `D(t)` (from the yield curve bootstrap, Phase 3).

**The par CDS spread condition:** At inception, a par CDS has zero NPV. This means the premium leg PV equals the protection leg PV:

```
PremiumLeg(T_n) = ProtectionLeg(T_n)
```

**Premium Leg PV (with accrual):**

```
PremiumLeg(T_n) = s_n * sum_{j=1}^{n} Delta_j * D(T_j) * Q(T_j)
                + s_n * sum_{j=1}^{n} AccrualOnDefault_j
```

where `Delta_j = dcf(T_{j-1}, T_j)` is the day count fraction for the j-th premium period (ACT/360 per ISDA convention).

The accrual-on-default term for period j:

```
AccrualOnDefault_j = (Delta_j / 2) * D(T_j) * (Q(T_{j-1}) - Q(T_j))
```

This approximates the expected accrued premium at default as half the period premium, assuming uniform default within each period. This is the ISDA standard model approximation.

**Protection Leg PV:**

```
ProtectionLeg(T_n) = (1 - R) * sum_{j=1}^{n} D(T_j) * (Q(T_{j-1}) - Q(T_j))
```

This approximates the protection leg by assuming default occurs at the end of each period. For greater accuracy, one can assume mid-period default:

```
ProtectionLeg(T_n) = (1 - R) * sum_{j=1}^{n} D((T_{j-1} + T_j) / 2) * (Q(T_{j-1}) - Q(T_j))
```

We use mid-period default for ISDA standard model consistency.

### 3.4 Bootstrap Algorithm

**Sequential bootstrap:** Solve for `lambda_1, lambda_2, ..., lambda_N` one at a time, from shortest to longest tenor.

For tenor `T_n`, given that `Q(T_1), ..., Q(T_{n-1})` are already known:

1. The only unknown is `lambda_n`, which determines `Q(T_n) = Q(T_{n-1}) * exp(-lambda_n * (T_n - T_{n-1}))`.

2. Set `PremiumLeg(T_n) = ProtectionLeg(T_n)` and solve for `lambda_n`.

3. This is a single-variable root-finding problem. Use Brent's method on the interval `[0, lambda_max]` where `lambda_max` corresponds to `Q(T_n) = eps` (say `eps = 1e-15`), giving `lambda_max = -ln(eps / Q(T_{n-1})) / (T_n - T_{n-1})`.

**Convergence criterion:** `|PremiumLeg - ProtectionLeg| < 1e-12` in absolute PV terms.

**Fallback:** If Brent's method does not converge within 50 iterations, raise a calibration failure (III-08 pattern).

### 3.5 Interpolation of the Survival Curve

Between tenor points, `Q(t)` is exponentially interpolated:

```
Q(t) = Q(T_{j-1}) * exp(-lambda_j * (t - T_{j-1}))    for T_{j-1} < t <= T_j
```

Before the first tenor: `Q(t) = exp(-lambda_1 * t)` for `0 < t <= T_1`.

Beyond the last tenor: flat hazard rate extrapolation: `Q(t) = Q(T_N) * exp(-lambda_N * (t - T_N))`.

### 3.6 Re-pricing Verification (AF-CR-05)

After bootstrap, re-price each input CDS spread from the bootstrapped curve. The re-pricing error must satisfy:

```
|s_n^repriced - s_n^market| < 0.5 bps = 0.00005
```

for all `n`. This is the ISDA standard model consistency check. If any tenor fails, the bootstrap is rejected.

### 3.7 Credit Curve Data Type

```python
@final
@dataclass(frozen=True, slots=True)
class CreditCurve:
    """Bootstrapped credit curve -- survival probabilities at tenor points."""
    reference_entity: NonEmptyStr
    as_of: date
    tenors: tuple[Decimal, ...]            # T_1 < T_2 < ... < T_N, all > 0
    survival_probs: tuple[Decimal, ...]    # Q(T_1) >= Q(T_2) >= ... >= Q(T_N), all in (0, 1]
    hazard_rates: tuple[Decimal, ...]      # lambda_1, ..., lambda_N, all >= 0
    recovery_rate: Decimal                  # R in [0, 1)
    discount_curve_ref: str                 # attestation_id of the YieldCurve used
    model_config_ref: str

    @staticmethod
    def create(
        reference_entity: str,
        as_of: date,
        tenors: tuple[Decimal, ...],
        survival_probs: tuple[Decimal, ...],
        hazard_rates: tuple[Decimal, ...],
        recovery_rate: Decimal,
        discount_curve_ref: str,
        model_config_ref: str,
    ) -> Ok[CreditCurve] | Err[str]:
        # Enforce: len(tenors) == len(survival_probs) == len(hazard_rates)
        # Enforce: tenors sorted ascending, all > 0
        # Enforce: survival_probs non-increasing, all in (0, 1]
        # Enforce: hazard_rates all >= 0
        # Enforce: 0 <= recovery_rate < 1
        ...
```

### 3.8 CDS Instrument Inputs

```python
@final
@dataclass(frozen=True, slots=True)
class CDSQuote:
    """Market CDS par spread quote."""
    reference_entity: NonEmptyStr
    tenor: Decimal              # in year fractions
    spread: Decimal             # par spread in decimal (e.g., 0.01 = 100 bps)
    recovery_rate: Decimal      # assumed recovery, typically 0.4
    currency: NonEmptyStr
```

---

## 4. CDS Cashflow Mathematics

This section specifies the cashflow formulas for a traded CDS, which the Ledger (Pillar II) uses for premium leg booking and credit event settlement. These are accounting formulas, not pricing formulas.

### 4.1 CDS Structure

A single-name CDS has two legs:

- **Premium (fee) leg:** The protection buyer pays a periodic premium (the CDS spread) to the protection seller, accruing on the notional amount, until either maturity or credit event.

- **Protection (contingent) leg:** If the reference entity experiences a credit event before maturity, the protection seller pays `(1 - R) * Notional` to the protection buyer, where `R` is the recovery rate (determined at auction).

### 4.2 Premium Leg Cashflows

For a CDS with notional `N`, contractual spread `s`, and payment dates `T_1, T_2, ..., T_M`:

**Regular premium payment at T_j:**

```
Premium_j = N * s * dcf(T_{j-1}, T_j)
```

where `dcf` is the day count fraction under ACT/360 (ISDA standard).

**Accrued premium at credit event:** If a credit event occurs at time `tau` with `T_{j-1} < tau <= T_j`, the protection buyer owes accrued premium:

```
AccruedPremium = N * s * dcf(T_{j-1}, tau)
```

This is paid at settlement alongside the protection payment.

### 4.3 Protection Leg Settlement

Upon a credit event at time `tau`:

1. **ISDA auction process** determines the final price `P_auction` (the recovery rate, expressed as a percentage of par).

2. **Protection payment:**

```
ProtectionPayment = N * (1 - P_auction / 100)
```

(if `P_auction` is in percentage terms, e.g., `P_auction = 35` means 35 cents on the dollar, `R = 0.35`).

3. **Net settlement:**

```
NetSettlement = ProtectionPayment - AccruedPremium
```

The protection seller pays `ProtectionPayment` to the buyer. The buyer pays `AccruedPremium` to the seller. In practice these are netted.

### 4.4 CDS Premium Leg Booking

Each premium payment generates a Ledger transaction:

```
Move(source=buyer_account, destination=seller_account,
     unit=currency, quantity=Premium_j, contract_id=cds_id)
```

Conservation: the sum of all moves in the transaction is zero (double-entry).

### 4.5 Credit Event Settlement Booking

At credit event with auction price `P_auction`:

**Transaction 1: Protection payment.**

```
Move(source=seller_account, destination=buyer_account,
     unit=currency, quantity=N * (1 - P_auction / 100), contract_id=cds_id)
```

**Transaction 2: Accrued premium.**

```
Move(source=buyer_account, destination=seller_account,
     unit=currency, quantity=AccruedPremium, contract_id=cds_id)
```

These can be combined into a single netting transaction. Conservation: the total cash change across all accounts sums to zero.

### 4.6 CDS Schedule Generation

Identical in structure to the IRS fixed leg schedule (reuse `_generate_period_dates` from `attestor/ledger/irs.py`), with:
- Day count convention: ACT/360 (ISDA standard)
- Payment frequency: QUARTERLY (standard CDS payment dates: March 20, June 20, September 20, December 20)
- First period may be a stub (short first coupon)

**Standard CDS payment dates (IMM dates):**

```python
CDS_STANDARD_DATES = [(3, 20), (6, 20), (9, 20), (12, 20)]
```

The next IMM date after trade date is the first coupon date. The effective date is typically T+1 from trade date.

### 4.7 CDS Data Types

```python
class CreditEventType(Enum):
    BANKRUPTCY = "BANKRUPTCY"
    FAILURE_TO_PAY = "FAILURE_TO_PAY"
    RESTRUCTURING = "RESTRUCTURING"

@final
@dataclass(frozen=True, slots=True)
class CDSPayoutSpec:
    """Single-name CDS payout specification."""
    reference_entity: NonEmptyStr
    notional: PositiveDecimal
    spread: Decimal               # contractual spread (decimal, e.g. 0.01 = 100bps)
    currency: NonEmptyStr
    effective_date: date
    maturity_date: date
    payment_frequency: PaymentFrequency   # typically QUARTERLY
    day_count: DayCountConvention         # ACT/360
    recovery_rate: Decimal                # contractual assumed recovery

@final
@dataclass(frozen=True, slots=True)
class CreditEvent:
    """A credit event for a reference entity."""
    reference_entity: NonEmptyStr
    event_type: CreditEventType
    event_date: date
    determination_date: date
    auction_price: Decimal | None    # None until auction completes
    auction_date: date | None
```

---

## 5. Swaption Exercise

### 5.1 European Swaption Structure

A European swaption gives the holder the right (but not the obligation) to enter into an interest rate swap at a pre-agreed fixed rate on the exercise date.

- **Payer swaption:** Right to enter as fixed-rate payer (receive float).
- **Receiver swaption:** Right to enter as fixed-rate receiver (pay float).

### 5.2 Exercise Decision (Oracle Scope)

The Oracle does NOT make exercise decisions -- that is a Pillar V (pricing) concern. However, the Oracle attests:

1. The ATM swap rate at exercise date (from the yield curve, Phase 3).
2. The swaption volatility (from the vol surface, this phase).

These attested values are inputs to the exercise decision, which the stub Pillar V resolves as follows: exercise if intrinsic value is positive.

**Intrinsic value (payer swaption):**

```
IntrinsicPV = Annuity * max(SwapRate_exercise - K, 0)
```

**Intrinsic value (receiver swaption):**

```
IntrinsicPV = Annuity * max(K - SwapRate_exercise, 0)
```

where `K` is the swaption strike (fixed rate) and `Annuity = sum_j dcf_j * D(T_j)` is the present value of a basis point on the underlying swap.

### 5.3 Exercise into IRS Lifecycle

Upon exercise, the swaption ceases to exist and a new IRS instrument is created. The connection to Phase 3 is:

1. **Create IRSwapPayoutSpec** from the swaption's economic terms:
   - `fixed_rate` = swaption strike `K`
   - `float_index`, `day_count`, `payment_frequency` = from the underlying swap definition
   - `start_date` = exercise date (or next business day)
   - `end_date` = underlying swap maturity
   - `notional` = swaption notional

2. **Book the IRS** using the existing Phase 3 IRS booking machinery (ExecutePI with an IRSwapDetail).

3. **Close the swaption position** in the Ledger (transition to CLOSED state).

4. **Settlement type:**
   - Physical settlement: the IRS is actually created and continues its lifecycle.
   - Cash settlement: no IRS created; net PV exchanged as cash.

### 5.4 Swaption Data Types

```python
class SwaptionType(Enum):
    PAYER = "PAYER"       # right to pay fixed
    RECEIVER = "RECEIVER"  # right to receive fixed

@final
@dataclass(frozen=True, slots=True)
class SwaptionPayoutSpec:
    """European swaption payout specification."""
    swaption_type: SwaptionType
    strike: PositiveDecimal            # fixed rate K
    exercise_date: date
    underlying_swap: IRSwapPayoutSpec  # the IRS that exercise would create
    settlement_type: SettlementType    # PHYSICAL or CASH
    currency: NonEmptyStr
    notional: PositiveDecimal
```

### 5.5 Swaption Lifecycle Transitions

```
PROPOSED -> FORMED -> SETTLED -> EXERCISED -> CLOSED  (if exercised)
PROPOSED -> FORMED -> SETTLED -> EXPIRED    -> CLOSED  (if not exercised)
PROPOSED -> CANCELLED
FORMED   -> CANCELLED
```

Two new states are introduced: `EXERCISED` and `EXPIRED`. These extend `PositionStatusEnum`.

### 5.6 Swaption PrimitiveInstruction

```python
@final
@dataclass(frozen=True, slots=True)
class SwaptionExercisePI:
    """Swaption exercise instruction."""
    instrument_id: NonEmptyStr
    exercise_date: date
    settlement_amount: Money | None     # non-None for cash settlement
    underlying_irs_id: NonEmptyStr | None  # non-None for physical settlement
```

---

## 6. Collateral Valuation

### 6.1 Scope

Collateral management in Phase 4 covers:
- Cash collateral (in various currencies)
- Securities collateral (bonds, equities posted as margin)
- Haircuts (valuation adjustments for collateral quality)
- Substitution (replacing one collateral asset with another)
- Margin calls (threshold-based)

### 6.2 Collateral Value Computation

**Cash collateral:**

```
CollateralValue(cash) = Amount * FXRate_to_base_currency
```

No haircut for cash in the agreement currency. For cross-currency cash:

```
CollateralValue(foreign_cash) = Amount * FXRate * (1 - haircut_fx)
```

where `haircut_fx` is the FX volatility haircut (typically 8% for major currencies under standard CSA).

**Securities collateral:**

```
CollateralValue(security) = Quantity * MarketPrice * (1 - haircut)
```

where `haircut` depends on the security type:

| Collateral Type | Typical Haircut | Source |
|----------------|----------------|--------|
| Government bonds (< 1Y) | 0.5% - 2% | CSA schedule |
| Government bonds (1-5Y) | 2% - 5% | CSA schedule |
| Government bonds (> 5Y) | 5% - 8% | CSA schedule |
| Investment grade corporates | 10% - 15% | CSA schedule |
| Equities (major index) | 15% - 25% | CSA schedule |
| Cash (same currency) | 0% | N/A |
| Cash (other G10 currency) | 8% | Standard |

### 6.3 Haircut Application Formula

For a collateral basket with `M` items:

```
TotalCollateralValue = sum_{i=1}^{M} Q_i * P_i * (1 - h_i) * FX_i
```

where:
- `Q_i` = quantity of asset i
- `P_i` = market price of asset i (from Oracle attestation)
- `h_i` = haircut for asset i (from CSA schedule, stored as reference data)
- `FX_i` = FX rate from asset currency to agreement base currency

### 6.4 Margin Call Computation

Given a CSA (Credit Support Annex) with:
- `threshold_A` = threshold amount for party A
- `threshold_B` = threshold amount for party B
- `mta` = minimum transfer amount

**Exposure calculation:** The Oracle provides the mark-to-market exposure `E` (positive means A is owed by B). In Phase 4, this comes from the stub Pillar V, so `E` is the par/intrinsic value.

**Required collateral (from B to A):**

```
RequiredCollateral_B = max(E - threshold_B, 0)
```

**Current collateral posted by B:** `CurrentCollateral_B = TotalCollateralValue(B's posted collateral)`

**Margin call amount:**

```
MarginCall = RequiredCollateral_B - CurrentCollateral_B
```

If `MarginCall > mta`: issue margin call. If `MarginCall < -mta`: return excess collateral.

### 6.5 Substitution Mathematics

When a collateral giver substitutes asset X with asset Y:

```
CollateralValue(Y) * (1 - h_Y) >= CollateralValue(X) * (1 - h_X)
```

The substitution is only valid if the new collateral value (after haircut) is at least as large as the old collateral value (after haircut). This prevents the collateral giver from degrading protection through substitution.

**Ledger transactions for substitution:**

```
Transaction 1: Return X
  Move(source=holder_account, destination=giver_account,
       unit=X_id, quantity=Q_X, contract_id=csa_id)

Transaction 2: Deliver Y
  Move(source=giver_account, destination=holder_account,
       unit=Y_id, quantity=Q_Y, contract_id=csa_id)
```

Conservation: securities move between accounts; no securities are created or destroyed.

### 6.6 Collateral Data Types

```python
class CollateralType(Enum):
    CASH = "CASH"
    GOVERNMENT_BOND = "GOVERNMENT_BOND"
    CORPORATE_BOND = "CORPORATE_BOND"
    EQUITY = "EQUITY"

@final
@dataclass(frozen=True, slots=True)
class CollateralItem:
    """A single piece of collateral."""
    asset_id: NonEmptyStr
    collateral_type: CollateralType
    quantity: Decimal
    currency: NonEmptyStr
    haircut: Decimal          # in [0, 1)
    market_value_ref: str     # attestation_id of the price used

@final
@dataclass(frozen=True, slots=True)
class CollateralAgreement:
    """CSA terms governing collateral exchange."""
    agreement_id: NonEmptyStr
    party_a: NonEmptyStr
    party_b: NonEmptyStr
    base_currency: NonEmptyStr
    threshold_a: Decimal      # >= 0
    threshold_b: Decimal      # >= 0
    mta: Decimal              # minimum transfer amount, >= 0
    eligible_collateral: tuple[CollateralType, ...]
    haircut_schedule: FrozenMap[str, Decimal]  # collateral_type -> haircut

@final
@dataclass(frozen=True, slots=True)
class MarginCallPI:
    """Margin call primitive instruction."""
    agreement_id: NonEmptyStr
    call_date: date
    call_amount: Money
    direction: str            # "DELIVER" or "RETURN"
    collateral_items: tuple[CollateralItem, ...]

@final
@dataclass(frozen=True, slots=True)
class CollateralSubstitutionPI:
    """Collateral substitution primitive instruction."""
    agreement_id: NonEmptyStr
    substitution_date: date
    returned_items: tuple[CollateralItem, ...]
    delivered_items: tuple[CollateralItem, ...]
```

---

## 7. Arbitrage Gates

### 7.1 Volatility Surface Gates

All gates follow the existing `ArbitrageCheckResult` pattern from `attestor/oracle/arbitrage_gates.py`. A new `ArbitrageCheckType.VOL_SURFACE` enum value is added.

#### 7.1.1 AF-VS-01: Calendar Spread Arbitrage

**Check:** For every pair of consecutive expiries `(T_j, T_{j+1})` and for a grid of log-moneyness points `k_i`:

```
w(k_i, T_{j+1}) >= w(k_i, T_j)    for all i
```

**Implementation:**
- Grid: `k_i` from `-5` to `+5` in steps of `0.01` (1001 points). This covers approximately 5 standard deviations of moneyness.
- For SSVI: if C-SSVI-01 and C-SSVI-03 hold, this is guaranteed by construction. Run the grid check as verification.
- For raw SVI slices: no structural guarantee; must check explicitly on the grid.

**Severity:** CRITICAL. If any grid point violates, the surface is rejected.

**Tolerance:** `w(k, T_{j+1}) >= w(k, T_j) - epsilon` where `epsilon = 1e-10` (numerical tolerance for Decimal arithmetic).

#### 7.1.2 AF-VS-02: Butterfly Arbitrage (Durrleman Condition)

**Check:** For each slice at expiry `T`, the implied probability density must be non-negative. The Durrleman (2005) necessary and sufficient condition is:

```
g(k) = (1 - (k * w'(k)) / (2 * w(k)))^2
       - (w'(k))^2 / 4 * (1/w(k) + 1/4)
       + w''(k) / 2
       >= 0
```

for all `k`.

**Implementation:**
- Evaluate `g(k)` on a grid of `k_i` from `-5` to `+5` in steps of `0.01`.
- Use the analytic SVI/SSVI derivatives (Section 1.3 / 2.6) -- no finite differences.
- For raw SVI with `b > 0` and `sigma > 0`, the convexity term `w''(k)/2` is always positive, which helps, but does not guarantee `g(k) >= 0` in general.

**Severity:** CRITICAL. If any grid point yields `g(k) < -epsilon` where `epsilon = 1e-10`, the slice is rejected.

**Diagnostic output:** If the check fails, record `k_min = argmin g(k)` and `g_min = min g(k)` in the `ArbitrageCheckResult.details`.

#### 7.1.3 AF-VS-03 and AF-VS-04: Roger Lee Wing Bounds

**Check (right wing):**

```
lim sup_{k -> +inf} w(k) / k <= 2
```

For raw SVI: `b * (1 + rho) <= 2`. This is checked directly from parameters (C-SVI-05).

For SSVI: `theta * phi(theta) * (1 + rho) <= 2` as `theta -> inf`. Since `phi(theta) -> 0` for the power-law form, this is automatically satisfied. Verify by checking the slope at the largest `theta` value.

**Check (left wing):**

```
lim sup_{k -> -inf} w(k) / |k| <= 2
```

For raw SVI: `b * (1 - rho) <= 2`. Also covered by C-SVI-05.

**Severity:** CRITICAL. These are necessary conditions for the existence of finite moments of the underlying price distribution.

**Implementation:** For raw SVI, check the parameter constraint directly. For SSVI, evaluate `w(k_max, T) / k_max` and `w(-k_max, T) / k_max` at `k_max = 10` and verify both are below `2 + epsilon`.

#### 7.1.4 AF-VS-05: Positive Implied Variance

**Check:**

```
w(k, T) > 0    for all k, T
```

**Implementation:** For raw SVI, this is equivalent to C-SVI-01. For SSVI, the minimum of `w(k, T)` for fixed `T` occurs at `k* = -(rho / phi)` and equals `theta * (1 - rho^2) / 2`. Since `theta > 0` and `|rho| < 1`, this is automatically positive.

Verify on the grid: check that `w(k_i, T_j) > 0` for all grid points.

**Severity:** CRITICAL. Negative total variance is mathematically impossible.

#### 7.1.5 AF-VS-06: ATM Variance Monotonicity

**Check:**

```
w(0, T_{j+1}) >= w(0, T_j)    for all j
```

**Implementation:** Evaluate `w(0, T)` at each calibrated expiry. This is `theta(T)` for SSVI (direct from `ThetaCurve`). For raw SVI slices, evaluate `w(0) = a + b * (rho * (0 - m) + sqrt(m^2 + sigma^2))` at each slice.

**Severity:** CRITICAL. Non-monotone ATM variance implies negative forward ATM variance.

#### 7.1.6 AF-VS-07: ATM Skew Term Structure

**Check:** The ATM skew `psi(T) = dw/dk|_{k=0} / (2 * sqrt(w(0, T)))` should be finite and consistent with observed market behaviour.

For rough volatility models, `psi(T) ~ C * T^(H - 1/2)` as `T -> 0`, where `H` is the Hurst exponent. For typical equity markets, `H ~ 0.1`, giving `psi(T) ~ C * T^{-0.4}`, which means the skew blows up at short expiries.

**Implementation:**
- Compute `psi(T_j)` at each calibrated expiry.
- Verify that `|psi(T_j)|` is finite (not NaN, not Inf) for all `j`.
- Log-log regression of `|psi(T)|` vs `T` to estimate the exponent. If the exponent is outside `[-0.8, 0.2]`, flag a warning (this covers `H` in `[0.01, 0.7]`).

**Severity:** HIGH. An inconsistent skew term structure does not directly admit arbitrage but indicates a fundamentally flawed model.

### 7.2 Credit Curve Gates

A new `ArbitrageCheckType.CREDIT_CURVE` enum value is added.

#### 7.2.1 AF-CR-01: Survival Probability Bounds

**Check:**

```
0 < Q(T_j) <= 1    for all j
```

(Strict positivity: `Q = 0` means certain default, which is handled separately as a credit event, not a curve state.)

**Implementation:** Check each element of `survival_probs` tuple.

**Severity:** CRITICAL.

#### 7.2.2 AF-CR-02: Unit Survival at Zero

**Check:**

```
Q(0) = 1
```

**Implementation:** This is enforced by construction in the `CreditCurve.create` factory. The bootstrap algorithm starts from `Q(0) = 1` by definition.

**Severity:** CRITICAL.

#### 7.2.3 AF-CR-03: Monotone Survival

**Check:**

```
Q(T_{j+1}) <= Q(T_j)    for all j
```

**Implementation:** Check each consecutive pair.

**Severity:** CRITICAL. A survival probability that increases with time implies negative default probability over some interval, which is meaningless.

#### 7.2.4 AF-CR-04: Non-Negative Hazard Rate

**Check:**

```
lambda_j >= 0    for all j
```

Since `lambda_j = -ln(Q(T_j) / Q(T_{j-1})) / (T_j - T_{j-1})`, this is equivalent to AF-CR-03 (monotone survival). Both are checked independently for defence in depth.

**Severity:** CRITICAL.

#### 7.2.5 AF-CR-05: ISDA Standard Model Consistency

**Check:** After bootstrapping, re-price each input CDS:

```
|s_n^repriced - s_n^market| < 0.5 bps = 0.00005
```

**Implementation:**

1. For each input tenor `T_n`, compute `PremiumLeg(T_n)` and `ProtectionLeg(T_n)` using the bootstrapped survival probabilities and the input discount curve.
2. Compute `s_n^repriced = ProtectionLeg(T_n) / RiskyAnnuity(T_n)` where `RiskyAnnuity(T_n) = sum_j Delta_j * D(T_j) * Q(T_j) + accrual terms`.
3. Compare with market spread.

**Severity:** HIGH. A re-pricing error above 0.5 bps indicates a bootstrap error, not an arbitrage opportunity per se, but it means the curve is not self-consistent.

### 7.3 Gate Execution Flow

The gate execution follows the protocol defined in MASTER_PLAN Section 5.3.6:

```
1. Calibration produces candidate VolSurface or CreditCurve
2. Run all applicable AF-VS or AF-CR checks
3. Outcome routing:
   - CRITICAL fail: reject, fallback to last-good, publish RejectedCalibrationAttestation
   - HIGH fail: publish with ConstraintWarning in DerivedConfidence
   - MEDIUM fail: publish + log diagnostic
4. Gate results are attested and stored in arbitrage_check_log
```

**Function signature (mirrors existing pattern):**

```python
def check_vol_surface_arbitrage_freedom(
    surface: VolSurface,
    grid_step: Decimal = Decimal("0.01"),
    k_range: Decimal = Decimal("5"),
    tolerance: Decimal = Decimal("1e-10"),
) -> Ok[tuple[ArbitrageCheckResult, ...]] | Err[str]:
    """Run AF-VS-01 through AF-VS-07."""
    ...

def check_credit_curve_arbitrage_freedom(
    curve: CreditCurve,
    market_spreads: tuple[CDSQuote, ...],
    discount_curve: YieldCurve,
    repricing_tolerance: Decimal = Decimal("0.00005"),
) -> Ok[tuple[ArbitrageCheckResult, ...]] | Err[str]:
    """Run AF-CR-01 through AF-CR-05."""
    ...
```

---

## 8. Numerical Considerations

### 8.1 Decimal Precision

All financial computations use `ATTESTOR_DECIMAL_CONTEXT` with `prec=28`. This section analyses where precision is critical.

#### 8.1.1 SVI/SSVI Evaluation

The `sqrt` operation in SVI:

```
sqrt((k - m)^2 + sigma^2)
```

When `|k - m| >> sigma`, the square root is dominated by `|k - m|` and the `sigma^2` term contributes at order `sigma^2 / (2 * |k - m|)`. For `sigma = 0.01` and `k - m = 5`, this correction is `~ 1e-5`, well within 28-digit precision.

When `k = m` exactly, the result is `sigma`, which is exact.

**Recommendation:** Use Python's `decimal.Decimal.sqrt()` method, which respects the context precision. Do NOT convert to `float` for `math.sqrt`.

#### 8.1.2 Hazard Rate Exponentials

The survival probability:

```
Q(T_j) = Q(T_{j-1}) * exp(-lambda_j * delta_T)
```

For small `lambda_j * delta_T`, the exponential is near 1 and subtractive cancellation can lose precision. Specifically, `1 - exp(-x)` for small `x` loses `log10(1/x)` digits.

**Recommendation:** For `lambda * delta_T < 0.01`, use the Taylor expansion:

```
exp(-x) = 1 - x + x^2/2 - x^3/6 + ...
```

truncated to sufficient terms for 28-digit precision. This avoids computing `exp(-x)` and then subtracting from 1.

For `Q(T_{j-1}) - Q(T_j) = Q(T_{j-1}) * (1 - exp(-lambda_j * delta_T))`, use:

```
Q(T_{j-1}) - Q(T_j) = Q(T_{j-1}) * expm1_neg(lambda_j * delta_T)
```

where `expm1_neg(x) = 1 - exp(-x)` is computed via the Taylor series for small `x`.

#### 8.1.3 Decimal exp and ln

Python's `decimal` module does not provide `exp` and `ln` natively. We must implement them or use `mpmath` and convert.

**Approach:** Implement `decimal_exp(x: Decimal) -> Decimal` and `decimal_ln(x: Decimal) -> Decimal` using Taylor series with `ATTESTOR_DECIMAL_CONTEXT`:

```
exp(x) = sum_{n=0}^{N} x^n / n!
```

where `N` is chosen such that `|x^N / N!| < 10^{-28}`. For `|x| < 100`, `N = 120` suffices.

```
ln(x) = ln(m * 2^e) = e * ln(2) + ln(m)
```

where `m in [0.5, 1)`, and `ln(m)` is computed via the series `ln(1 + y) = y - y^2/2 + y^3/3 - ...` with `y = m - 1`.

**Alternative:** Use `math.log` / `math.exp` and convert through `Decimal(str(result))`. This gives only ~15 digits of precision (IEEE 754 double). For most financial purposes 15 digits is adequate, but for hash determinism we need exact reproducibility. Since `Decimal(str(float_value))` is not guaranteed to produce the same string across platforms, we MUST use pure-Decimal arithmetic.

**Recommendation:** Ship a `decimal_math.py` utility module with `exp_d`, `ln_d`, `sqrt_d`, `expm1_neg_d` functions, all operating in `ATTESTOR_DECIMAL_CONTEXT`. These are shared by yield curve bootstrap (Phase 3, currently using `math.log`) and all Phase 4 calibrations.

**Migration note:** The existing `calibration.py` uses `math.log(float(...))` for discount factor interpolation and forward rate computation. Phase 4 should migrate these to `ln_d` for full Decimal determinism, though this is a Phase 3 cleanup rather than a Phase 4 blocker.

### 8.2 Root-Finding for Credit Curve Bootstrap

Brent's method is the standard choice for one-dimensional root-finding: guaranteed convergence for continuous functions on a bracketing interval, superlinear convergence in practice.

**Specification:**

```python
def brent_solve(
    f: Callable[[Decimal], Decimal],
    a: Decimal,
    b: Decimal,
    tol: Decimal = Decimal("1e-12"),
    max_iter: int = 50,
) -> Ok[Decimal] | Err[str]:
    """Find x in [a, b] such that |f(x)| < tol.

    Requires: f(a) * f(b) < 0 (bracketing).
    Uses: Brent's method (inverse quadratic interpolation with bisection fallback).
    All arithmetic in ATTESTOR_DECIMAL_CONTEXT.
    """
```

**Convergence:** For the CDS bootstrap, the function `f(lambda) = PremiumLeg(lambda) - ProtectionLeg(lambda)` is continuous, monotone in `lambda`, and changes sign on `[0, lambda_max]`. Brent's method converges in O(log(1/tol)) iterations. With `tol = 1e-12`, expect ~40 iterations.

### 8.3 L-BFGS-B for SVI/SSVI Calibration

L-BFGS-B is the appropriate optimiser for the SVI/SSVI calibration problem: smooth objective, box constraints, moderate dimensionality (3--5 parameters).

**Specification:**

- Use `scipy.optimize.minimize(method='L-BFGS-B')` with bounds.
- Convert Decimal parameters to float64 for the optimiser, then convert the result back to Decimal. This is acceptable because the optimiser is a search algorithm -- determinism comes from the final evaluation at the found parameters, not from the search path.
- After L-BFGS-B converges, evaluate the objective and all constraints at the final parameters using full Decimal arithmetic.
- If any constraint is violated at the Decimal-precision level, project the parameters onto the feasible set (e.g., clamp `rho` to `(-1 + eps, 1 - eps)`).

**Gradient computation:** Analytic gradients of the SVI/SSVI objective with respect to parameters are straightforward. Always prefer analytic gradients over finite differences.

**SVI gradient (with respect to parameters):**

```
dL/da = 2 * sum_i omega_i * (w_i - w_i^mkt) * 1
dL/db = 2 * sum_i omega_i * (w_i - w_i^mkt) * (rho*(k_i - m) + sqrt((k_i - m)^2 + sigma^2))
dL/drho = 2 * sum_i omega_i * (w_i - w_i^mkt) * b * (k_i - m)
dL/dm = 2 * sum_i omega_i * (w_i - w_i^mkt) * b * (-rho + (-(k_i - m)) / sqrt((k_i - m)^2 + sigma^2))
dL/dsigma = 2 * sum_i omega_i * (w_i - w_i^mkt) * b * sigma / sqrt((k_i - m)^2 + sigma^2)
```

### 8.4 Interpolation Methods

#### 8.4.1 Total Variance Interpolation (Between Expiries)

For the SSVI surface, `theta(T)` interpolation is piecewise linear by construction. For arbitrary `(k, T)` queries to raw SVI slices:

**Method:** Linear interpolation in total variance.

Given SVI slices at `T_j` and `T_{j+1}` with `T_j < T < T_{j+1}`:

```
w(k, T) = (1 - alpha) * w_j(k) + alpha * w_{j+1}(k)
```

where `alpha = (T - T_j) / (T_{j+1} - T_j)`.

**Calendar spread freedom:** Linear interpolation in total variance preserves calendar spread freedom if `w_{j+1}(k) >= w_j(k)` for all `k` (which is checked by AF-VS-01). This is because the interpolant is a convex combination of two functions, both bounded below by `w_j(k)`.

#### 8.4.2 Survival Probability Interpolation (Between Tenors)

Between tenor points, use exponential interpolation (piecewise constant hazard rate), as specified in Section 3.5. This automatically preserves monotonicity and positivity.

#### 8.4.3 Discount Factor Interpolation (From Phase 3)

Log-linear interpolation, already implemented in `attestor/oracle/calibration.py`.

### 8.5 Numerical Stability at Extremes

#### 8.5.1 Short Maturities (T < 1 week)

At very short maturities:
- `theta(T)` is small, `phi(theta)` is large.
- The Durrleman condition must be checked with care: `w(k)` is small and `w'(k)/w(k)` can be large.
- Use analytic derivatives, never finite differences, for short maturity slices.

#### 8.5.2 Deep OTM Options (|k| > 3)

At extreme moneyness:
- SVI/SSVI variance grows linearly (by Roger Lee). The implied volatility is well-defined.
- However, the Black-Scholes price of a deep OTM option is exponentially small, so converting between price and implied vol is ill-conditioned.
- **Recommendation:** Always work in total variance space, never in price space, for calibration. Option prices are converted to implied variance at the Oracle boundary (ingest), and all internal calibration operates on total variance.

#### 8.5.3 Near-Zero Hazard Rate

If a CDS spread is very small (< 1 bp), the implied hazard rate is near zero. The bootstrap is well-conditioned in this regime: `lambda ~ s / (1 - R)` for small spreads.

#### 8.5.4 Inverted Credit Curves

If market CDS spreads are non-monotone in tenor (e.g., 5Y spread < 1Y spread), the bootstrapped hazard rates may be very small or very large in certain intervals. This is not a mathematical problem -- the bootstrap will produce valid (monotone, positive) survival probabilities -- but the hazard rates may exhibit large jumps.

**Recommendation:** Log the hazard rate term structure in the DerivedConfidence fit_quality metrics. Flag cases where `max(lambda) / min(lambda) > 100` as a warning (not an error).

---

## Appendix A: DerivedConfidence Payloads for Phase 4

### A.1 Vol Surface DerivedConfidence

```python
fit_quality = FrozenMap({
    "rmse": Decimal("..."),
    "max_abs_error": Decimal("..."),
    "mean_abs_error": Decimal("..."),
    "n_points": Decimal("..."),         # total calibration points
    "n_expiries": Decimal("..."),
    "calendar_spread_margin": Decimal("..."),  # min margin to AF-VS-01 violation
    "butterfly_margin": Decimal("..."),        # min g(k) value
    "roger_lee_right_slope": Decimal("..."),   # b*(1+rho) or equivalent
    "roger_lee_left_slope": Decimal("..."),    # b*(1-rho) or equivalent
})
```

### A.2 Credit Curve DerivedConfidence

```python
fit_quality = FrozenMap({
    "max_repricing_error_bps": Decimal("..."),
    "mean_repricing_error_bps": Decimal("..."),
    "n_tenors": Decimal("..."),
    "max_hazard_rate": Decimal("..."),
    "min_hazard_rate": Decimal("..."),
    "min_survival_prob": Decimal("..."),
    "recovery_rate": Decimal("..."),
})
```

---

## Appendix B: File Layout

The Phase 4 implementation should create the following files, consistent with the existing module structure:

```
attestor/
  oracle/
    calibration.py          # EXISTING: extend with credit curve bootstrap
    arbitrage_gates.py      # EXISTING: extend with AF-VS and AF-CR gates
    vol_surface.py          # NEW: SVISlice, SSVISurface, VolSurface, ThetaCurve
    credit_curve.py         # NEW: CreditCurve, CDSQuote, bootstrap_credit_curve
    decimal_math.py         # NEW: exp_d, ln_d, sqrt_d, expm1_neg_d
  instrument/
    derivative_types.py     # EXISTING: extend InstrumentDetail union
    credit_types.py         # NEW: CDSPayoutSpec, CreditEvent, CreditEventType
    swaption_types.py       # NEW: SwaptionPayoutSpec, SwaptionType
    lifecycle.py            # EXISTING: extend PrimitiveInstruction union, add CDS/swaption transitions
  ledger/
    cds.py                  # NEW: CDS premium leg booking, credit event settlement
    swaption.py             # NEW: swaption exercise -> IRS creation
    collateral.py           # NEW: collateral valuation, margin calls, substitution
  pricing/
    types.py                # EXISTING: no changes needed
    protocols.py            # EXISTING: extend stub for CDS/swaption types
```

---

## Appendix C: Cross-References to MASTER_PLAN

| This Spec Section | MASTER_PLAN Reference |
|-------------------|----------------------|
| 1 (SVI) | Section 5.3.2, III-05, AF-VS-01..07 |
| 2 (SSVI) | Section 5.3.2, III-05 |
| 3 (Credit Bootstrap) | Section 5.3.3, III-05, AF-CR-01..05 |
| 4 (CDS Cashflows) | Phase 4 scope (Section 8), II-08 |
| 5 (Swaption Exercise) | Phase 4 scope (Section 8), II-08 |
| 6 (Collateral) | Phase 4 scope (Section 8), II-08 |
| 7 (Arbitrage Gates) | Section 5.3, III-07 |
| 8 (Numerics) | Section 5.4 (Determinism Policy) |

---

## Appendix D: Conservation Laws for Phase 4

### D.1 CDS Settlement Conservation

```
ProtectionPayment(buyer) + AccruedPremium(seller) = NetSettlement
sum(all moves in settlement transaction) = 0
```

More precisely: protection seller pays `N * (1 - R)` to buyer, buyer pays accrued premium to seller. The net is `N * (1 - R) - AccruedPremium`. No value is created or destroyed.

### D.2 Collateral Conservation

```
sum(collateral, all accounts, before substitution)
  = sum(collateral, all accounts, after substitution)
```

Securities move between accounts but are not created or destroyed. Cash margin calls transfer cash but do not create it.

### D.3 Swaption Exercise Conservation

At physical exercise: the swaption position closes (value goes to zero) and an IRS position opens. No cash changes hands at exercise of a physically-settled swaption.

At cash exercise: the swaption position closes and cash equal to the net settlement amount is transferred. `sum(cash moves) = 0`.

---

## Appendix E: Summary of All New Types

| Type | Module | Purpose |
|------|--------|---------|
| `SVISlice` | `oracle/vol_surface.py` | Calibrated SVI parameters for one expiry |
| `SVISliceSet` | `oracle/vol_surface.py` | Collection of SVI slices |
| `ThetaCurve` | `oracle/vol_surface.py` | ATM total variance curve |
| `SSVISurface` | `oracle/vol_surface.py` | SSVI surface parameters |
| `VolSurface` | `oracle/vol_surface.py` | Attestable vol surface (union) |
| `CreditCurve` | `oracle/credit_curve.py` | Bootstrapped survival probabilities |
| `CDSQuote` | `oracle/credit_curve.py` | Market CDS spread quote |
| `CDSPayoutSpec` | `instrument/credit_types.py` | CDS economic terms |
| `CreditEvent` | `instrument/credit_types.py` | Credit event record |
| `CreditEventType` | `instrument/credit_types.py` | Enum: bankruptcy, failure to pay, restructuring |
| `SwaptionPayoutSpec` | `instrument/swaption_types.py` | European swaption economic terms |
| `SwaptionType` | `instrument/swaption_types.py` | Enum: payer, receiver |
| `CollateralItem` | `ledger/collateral.py` | Single collateral piece |
| `CollateralAgreement` | `ledger/collateral.py` | CSA terms |
| `CollateralType` | `ledger/collateral.py` | Enum: cash, govt bond, corp bond, equity |
| `SwaptionExercisePI` | `instrument/lifecycle.py` | Swaption exercise instruction |
| `CreditEventPI` | `instrument/lifecycle.py` | Credit event settlement instruction |
| `MarginCallPI` | `ledger/collateral.py` | Margin call instruction |
| `CollateralSubstitutionPI` | `ledger/collateral.py` | Collateral substitution instruction |
