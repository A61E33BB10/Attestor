# Phase 1 Completion Report -- Financial Mathematics and Market Practice Review

**Reviewer:** GATHERAL (Financial Mathematics & Market Practice)
**Date:** 2026-02-15
**Scope:** Cash equity lifecycle: order ingestion, T+2 settlement, dividend payment, oracle attestation, EMIR reporting, stub pricing

---

## Executive Assessment

Phase 1 delivers a structurally sound cash equity lifecycle engine. The double-entry
bookkeeping is conservation-law-correct by construction. The settlement and dividend
arithmetic use Python `Decimal` under a controlled context with precision 28 and
`ROUND_HALF_EVEN` -- the right choices. The type system enforces invariants at
construction time rather than through runtime assertions, which is the correct
architectural posture for financial infrastructure.

There are no CRITICAL findings. The system does not admit arbitrage within its scope.
There are several HIGH and MEDIUM observations that must be addressed before Phase 2
extends into derivatives, where the stakes around numerical precision and model
consistency become substantially higher.

---

## 1. Settlement Arithmetic

**File:** `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/settlement.py`

### 1.1 Cash Amount Computation -- CORRECT

```python
with localcontext(ATTESTOR_DECIMAL_CONTEXT):
    cash_amount = order.price * order.quantity.value
```

The settlement amount `cash_amount = price * quantity` is computed under
`ATTESTOR_DECIMAL_CONTEXT` (precision=28, `ROUND_HALF_EVEN`). This is correct for
cash equities where the settlement amount is simply the traded price times the
quantity. The `localcontext` scoping ensures that the multiplication inherits the
correct rounding mode and precision, and that no global state is polluted.

**Observation (MEDIUM):** The raw `cash_amount` is not quantized to the currency's
ISO 4217 minor unit before being wrapped in `PositiveDecimal`. The `Money` type has a
`round_to_minor_unit()` method using `_ISO4217_MINOR_UNITS`, but settlement does not
invoke it. For a trade at price `175.333` and quantity `3`, the cash amount would be
`525.999` -- a value no CSD would accept. In production, settlement amounts must be
rounded to the currency's minor units (2 decimal places for USD/EUR/GBP, 0 for JPY).
This is acceptable for Phase 1 since orders arrive with already-rounded prices, but
must be enforced before any instrument type where fractional prices are possible.

### 1.2 Double-Entry Conservation -- CORRECT

The settlement creates exactly two `Move` objects:
1. Cash: `buyer_cash` -> `seller_cash` (amount = `price * quantity`)
2. Securities: `seller_securities` -> `buyer_securities` (amount = `quantity`)

Each `Move` subtracts from source and adds to destination, so net supply per unit is
unchanged. The `LedgerEngine.execute()` method independently verifies this with pre/post
`total_supply()` comparison per affected unit. This is belt-and-suspenders enforcement
of the conservation law, which is appropriate.

### 1.3 Negative Balance Allowance -- OBSERVATION (MEDIUM)

The ledger allows balances to go negative. This is intentional (no check in
`LedgerEngine.execute()`) and is appropriate for a general-purpose double-entry system
where short selling is permitted. However, for settlement specifically, the system does
not verify that the seller actually holds the securities or that the buyer has sufficient
cash. This is a Phase 2 concern (credit/inventory checks), not a Phase 1 defect.

### 1.4 Price Allows Zero and Negative -- OBSERVATION (HIGH)

In `CanonicalOrder.create()`, the price field is validated only as a "finite Decimal":

```python
if not isinstance(price, Decimal) or not price.is_finite():
    violations.append(...)
```

A price of `Decimal("0")` or `Decimal("-50")` passes validation. The settlement then
rejects zero/negative `cash_amount` via the `PositiveDecimal.parse()` check, so
`price=0` with `quantity>0` correctly fails. However, `price=-100` with `quantity>0`
produces `cash_amount=-100` which also fails -- but the error message says "Cash amount
must be positive" rather than "Price must be non-negative", which is confusing. The
price validation should be tightened at the gateway level.

For limit orders, price must be strictly positive. For market orders, price may be zero
(filled at market) -- but then settlement should not occur until a fill price is
assigned. The current design does not distinguish these cases.

---

## 2. Dividend Arithmetic

**File:** `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/dividends.py`

### 2.1 Payment Computation -- CORRECT

```python
with localcontext(ATTESTOR_DECIMAL_CONTEXT):
    payment = amount_per_share * shares_held
```

Standard dividend calculation. Each holder receives `amount_per_share * shares_held`.
Conservation holds because all cash flows from the single `issuer_account` to the
individual holder accounts.

### 2.2 Missing Minor-Unit Rounding -- OBSERVATION (HIGH)

Same issue as settlement: the per-holder payment is not rounded to the currency's
minor unit. For a dividend of `USD 0.33` per share with a holder owning `7` shares,
the payment is `USD 2.31` (exact). But for `USD 0.333` per share with `7` shares, the
payment is `USD 2.331`, which is not a valid cash amount in USD. In real dividend
processing, the per-holder payment is rounded (typically to 2 decimal places for USD),
and the rounding residual is handled through a balancing entry or absorbed by the
issuer. This rounding logic must be added before production use.

### 2.3 Withholding Tax -- NOT IN SCOPE

Dividends in practice are subject to withholding tax (typically 15-30% depending on
jurisdiction and tax treaty). The current model has no tax deduction. This is
documented as Phase 1 scope exclusion and is acceptable.

### 2.4 Ex-Date vs Record Date vs Payment Date

The `DividendPI` instruction has `ex_date` and `payment_date` but there is no
`record_date`. In practice, the record date (typically ex_date + 1 business day) is
when the registrar determines who is entitled to the dividend. The current code
passes `holder_accounts` as an explicit parameter, so this is handled externally,
which is acceptable for Phase 1.

---

## 3. Oracle and Mid-Price Calculation

**File:** `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/oracle/ingest.py`
**File:** `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/oracle/attestation.py`

### 3.1 Mid-Price Computation -- CORRECT

```python
@property
def mid(self) -> Decimal:
    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        return (self.bid + self.ask) / 2
```

The arithmetic mean of bid and ask is the standard mid-price definition for cash
equities. For this asset class, it is unambiguous. The `ATTESTOR_DECIMAL_CONTEXT`
ensures precision 28 and `ROUND_HALF_EVEN` for the division, which is correct.

**Note for Phase 2:** When the system extends to options, "mid-price" becomes
ambiguous. The naive (bid + ask) / 2 is acceptable for linear instruments but for
options the mid should be computed in implied volatility space (average the bid and
ask implied vols, then convert back to price). This is a known subtlety that must
be addressed when derivatives are introduced.

### 3.2 Bid-Ask Spread Validation -- CORRECT

```python
if bid > ask:
    return Err(f"QuotedConfidence: bid ({bid}) > ask ({ask}) implies negative spread")
```

This correctly enforces `bid <= ask`. A locked market (`bid == ask`) is correctly
accepted, which matches real-world behavior (crossed quotes should be rejected, but
locked quotes are valid in some venues).

### 3.3 Confidence Model: Firm vs Quoted -- WELL-DESIGNED

The epistemic distinction between `FirmConfidence` (exchange fills -- observed
transaction prices with certainty) and `QuotedConfidence` (bid/ask quotes with
inherent spread uncertainty) is the correct categorization for cash equities:

- **Firm**: An exchange fill is an observed fact. The price is exact. The confidence
  carries the exchange reference ID for audit trail.
- **Quoted**: A quote carries uncertainty equal to the half-spread. The `half_spread`
  property is provided. The `QuoteCondition` enum distinguishes Indicative, Firm (in
  the quote sense), and RFQ.
- **Derived**: For model outputs (Phase 2). Carries `fit_quality` metrics and optional
  confidence intervals.

This three-tier confidence model is appropriate and well-structured. The fact that
`ingest_equity_fill` produces `FirmConfidence` and `ingest_equity_quote` produces
`QuotedConfidence` is correct.

### 3.4 Missing Staleness Check -- OBSERVATION (MEDIUM)

Neither `ingest_equity_fill` nor `ingest_equity_quote` checks whether the timestamp
is stale relative to a reference clock. In production, a quote with a timestamp from
yesterday should be rejected or flagged. This is a data quality concern that should be
addressed in Phase 2.

### 3.5 No Volume Weighting -- OBSERVATION (LOW)

For fills, the system ingests individual fill prices. There is no VWAP (volume-weighted
average price) aggregation. For an oracle serving as a pricing reference, VWAP over a
time window is typically more robust than a single last-trade price. This is a Phase 2
enhancement.

---

## 4. EMIR Reporting and UTI Generation

**File:** `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/reporting/emir.py`

### 4.1 UTI Structure -- OBSERVATION (HIGH)

The UTI is generated as:

```python
uti_value = order.executing_party_lei.value + ch[:32]
```

where `ch` is the SHA-256 hex digest of the canonical serialization of the order.
This produces a UTI of `20 + 32 = 52` characters with the LEI as prefix.

**EMIR REFIT (EU 2024/2901) compliance assessment:**

The UTI format under ISO 23897:2020 requires:
1. Maximum 52 characters -- **SATISFIED** (exactly 52)
2. Alphanumeric plus a limited set of special characters -- The LEI prefix is
   alphanumeric (20 chars). The SHA-256 hex suffix is `[0-9a-f]` (32 chars). Since
   the `UTI.parse()` validator only requires the first 20 characters to be alphanumeric
   (and does not constrain the remaining characters), this passes validation.
   **SATISFIED** but only because hex digits are alphanumeric.
3. The UTI should be prefixed with the LEI of the entity responsible for UTI
   generation -- **SATISFIED** (uses `executing_party_lei`).
4. The UTI must be unique -- Uniqueness relies on the SHA-256 hash of the canonical
   order being collision-free, which is effectively guaranteed for practical volumes.
   **SATISFIED**.

**Concern:** The UTI uses `executing_party_lei` as the prefix. Under EMIR REFIT,
the UTI-generating entity can be either counterparty (or a third party). The choice
of `executing_party_lei` is a policy decision that should be configurable, not
hardcoded. If the counterparty is the UTI-generating entity (as is sometimes the case
for buy-side / sell-side reporting), this would produce an incorrect UTI prefix.

### 4.2 Projection Purity -- CORRECT

The EMIR report is a pure projection from `CanonicalOrder`. No new values are computed
(only the UTI is derived, deterministically, from the order content hash). This is the
correct design: the report should never introduce information that was not in the trade.

```python
report = EMIRTradeReport(
    uti=uti,
    reporting_counterparty_lei=order.executing_party_lei,
    other_counterparty_lei=order.counterparty_lei,
    ...
)
```

All fields are direct copies from the order. The `attestation_refs` tuple provides
the provenance chain. This is clean.

### 4.3 Missing EMIR Fields -- OBSERVATION (MEDIUM)

For full EMIR REFIT compliance, the report would need additional fields including:
- Action type (New, Modify, Correct, Cancel, Terminate)
- Asset class and sub-asset class
- Notional amount (price * quantity for equities)
- Up-front payment (if any)
- Clearing obligation flag
- Intragroup flag
- Execution timestamp (distinct from trade date)

These are correctly deferred to Phase 2 but should be on the roadmap.

---

## 5. Stub Pricing Engine

**File:** `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/pricing/protocols.py`

### 5.1 Design -- APPROPRIATE FOR PHASE 1

The `StubPricingEngine` returns a deterministic `oracle_price` as the NPV. This is
explicitly a test double, not a pricing model. For cash equities, the "price" of a
position is indeed simply the market price per share times the quantity -- there is no
optionality, no discounting, no model dependence. The stub correctly captures this:
the NPV of a cash equity position is the oracle (market) price.

### 5.2 Greeks Stub -- CORRECT

```python
def greeks(self, ...) -> Ok[Greeks]:
    return Ok(Greeks())
```

Returns all-zero Greeks. For a cash equity position:
- delta = 1 per share (not 0) -- but this is a stub, not a real model
- gamma = 0 -- correct for linear instruments
- vega = 0 -- correct, no volatility exposure for spot equity
- theta = 0 -- acceptable (no time decay for equity, ignoring carry)

The zero delta is technically wrong for equities but acceptable in a test stub. The
`Greeks` dataclass is well-structured for Phase 2 derivatives with vanna, volga, and
charm -- the right second-order sensitivities for a volatility surface practitioner.

### 5.3 VaR and PnL Attribution Stubs -- APPROPRIATE PLACEHOLDERS

These return zeros. They exist to define the interface contract for Phase 2. The
`PnLAttribution.create()` factory enforces `total = market + carry + trade + residual`
by construction, which is the correct decomposition.

---

## 6. Position Lifecycle State Machine

**File:** `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/instrument/lifecycle.py`

### 6.1 Transition Table -- CORRECT

```python
EQUITY_TRANSITIONS = frozenset({
    (PROPOSED, FORMED),
    (PROPOSED, CANCELLED),
    (FORMED, SETTLED),
    (FORMED, CANCELLED),
    (SETTLED, CLOSED),
})
```

This is a DAG (directed acyclic graph) with no cycles, which is correct for a trade
lifecycle. The transitions encode:
- PROPOSED -> FORMED: Trade is agreed/confirmed
- PROPOSED -> CANCELLED: Trade rejected before confirmation
- FORMED -> SETTLED: T+2 settlement completes (DVP)
- FORMED -> CANCELLED: Trade fails/cancelled before settlement
- SETTLED -> CLOSED: Position fully unwound

**Observation (MEDIUM):** There is no SETTLED -> SETTLED transition, which means
partial closes are not modeled. In practice, a position of 1000 shares settled, then
selling 500 shares, creates a new SETTLED position of 500. The current model would
need to close the original and create a new position, or introduce a PARTIALLY_CLOSED
state. This is a Phase 2 concern for position management.

### 6.2 Missing Failed Settlement State -- OBSERVATION (MEDIUM)

There is no FORMED -> FAILED_SETTLEMENT transition. In practice, settlement can fail
(insufficient securities at CSD, credit limit breach, etc.). The failed settlement
should be a distinct state from CANCELLED (which implies a voluntary cancellation).
CSDR penalty regime (EU) distinguishes between these cases.

---

## 7. Hypothesis Property Tests

**File:** `/home/renaud/A61E33BB10/ISDA/Attestor/tests/test_commutativity.py`

### 7.1 Master Square (CS-02) -- WELL-CONCEIVED BUT INCOMPLETE

The test verifies: `stub_price(book(trade)) == book(stub_price(trade))`.

Both paths produce the same NPV and the same ledger balances. The conservation law
`total_supply("USD") == 0` is verified. This is the correct commutativity property
for a system where pricing and booking are independent operations.

**Observation (HIGH):** The test is vacuous because the `StubPricingEngine` does not
read from the ledger. In Path A, `pricer_a.price("AAPL", "snap", "cfg")` returns
`oracle_price` regardless of what was booked. In Path B, the same call returns the
same value regardless of booking. The test passes by construction because the stub
ignores the ledger state entirely. The real Master Square property -- that pricing a
booked position equals booking a priced position -- requires the pricing engine to
actually query the ledger for positions. This must be tested properly in Phase 2 when
the pricing engine consumes real positions.

The test is still valuable because it verifies that:
1. Booking does not corrupt the ledger
2. The conservation law holds
3. The NPV is deterministic

But it does not test the commutativity of the pricing-booking diagram in the
categorical sense.

### 7.2 Reporting Naturality (CS-04) -- CORRECT

```
report(book(order)) == report(order)
```

This verifies that EMIR reporting is a pure projection: it does not depend on ledger
state. Since `project_emir_report` takes a `CanonicalOrder` (not a ledger position),
the test correctly verifies that booking does not affect the report. The content hash
stability test is a good addition.

### 7.3 Lifecycle-Booking Naturality (CS-05) -- CORRECT

```
book(f ; g) == book(f) ; book(g)
```

Two sequential settlements produce the same result regardless of whether they are
conceptualized as one composed operation or two separate bookings. This is the
functorial property of the booking functor. The test correctly verifies both sequential
composition and order independence (commutativity of independent settlements affecting
the same accounts).

### 7.4 Property-Based Test (Hypothesis) -- WELL-DESIGNED

```python
@given(
    price=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("10000"), places=2, ...),
    qty=st.decimals(min_value=Decimal("1"), max_value=Decimal("100000"), places=0, ...),
)
@settings(max_examples=200)
def test_master_square_property(self, price, qty):
```

The parameter ranges are realistic for cash equities:
- Price: 0.01 to 10,000 with 2 decimal places (covers penny stocks to Berkshire A)
- Quantity: 1 to 100,000 with 0 decimal places (integer shares)
- 200 examples gives reasonable coverage

**Observation (MEDIUM):** The test does not cover:
- Fractional shares (increasingly common on retail platforms)
- Very large quantities (institutional block trades can be millions of shares)
- Extreme prices (BRK.A trades above $600,000)
- Different currencies (JPY with 0 minor units, BHD with 3)

Adding strategies for these edge cases would strengthen the property tests.

---

## 8. Decimal Context and Numerical Precision

**File:** `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/core/money.py`

### 8.1 ATTESTOR_DECIMAL_CONTEXT -- CORRECT

```python
ATTESTOR_DECIMAL_CONTEXT = Context(
    prec=28,
    rounding=ROUND_HALF_EVEN,
    Emin=-999999, Emax=999999,
    traps=[InvalidOperation, DivisionByZero, Overflow],
)
```

- Precision 28 matches Python's default `Decimal` precision and exceeds the 18-digit
  requirement for most financial calculations.
- `ROUND_HALF_EVEN` (banker's rounding) is the correct choice for financial
  arithmetic -- it eliminates systematic rounding bias.
- Trapping `InvalidOperation`, `DivisionByZero`, and `Overflow` ensures that
  pathological inputs cause immediate failure rather than silent NaN/Infinity
  propagation.
- `Underflow` is not trapped, which is acceptable -- underflow to zero is harmless
  for financial amounts.

### 8.2 Consistent Context Usage -- CORRECT

Every arithmetic operation across settlement, dividends, mid-price calculation, and
Money operations uses `with localcontext(ATTESTOR_DECIMAL_CONTEXT)`. This is consistent
and prevents context leakage between threads.

---

## 9. Type System and Validation

### 9.1 Refined Types -- EXCELLENT

The use of `PositiveDecimal`, `NonEmptyStr`, `NonZeroDecimal`, `LEI`, `ISIN`, `UTI`
as validated newtypes that can only be constructed through `parse()` returning
`Ok | Err` is the correct pattern. It makes illegal states unrepresentable.

### 9.2 ISIN Luhn Check -- CORRECT

The `_isin_luhn_check` implementation correctly expands letters to their numeric
values (A=10, B=11, ..., Z=35) and applies the standard Luhn algorithm. This matches
the ISO 6166 specification.

### 9.3 LEI Validation -- MINIMAL BUT ACCEPTABLE

The LEI validation checks length (20) and alphanumeric characters. A complete
implementation would verify the LEI check digits (positions 19-20) using ISO 17442
MOD 97-10 (same algorithm as IBAN). This is a MEDIUM observation for Phase 2.

---

## 10. Findings Summary

### CRITICAL -- None

### HIGH

| # | Finding | Location | Recommendation |
|---|---------|----------|----------------|
| H1 | Price validation allows zero/negative | `gateway/types.py:126` | Reject non-positive prices for limit orders; require explicit fill price for market orders |
| H2 | No minor-unit rounding on dividend payments | `ledger/dividends.py:71` | Quantize to ISO 4217 minor units; handle rounding residual |
| H3 | UTI generating entity is hardcoded | `reporting/emir.py:66` | Make UTI prefix LEI configurable per reporting relationship |
| H4 | Master Square test is vacuous | `tests/test_commutativity.py:70` | Phase 2 must test with a pricing engine that reads ledger positions |

### MEDIUM

| # | Finding | Location | Recommendation |
|---|---------|----------|----------------|
| M1 | No minor-unit rounding on settlement amount | `ledger/settlement.py:73` | Quantize cash_amount before PositiveDecimal.parse |
| M2 | No staleness check on oracle data | `oracle/ingest.py` | Add configurable staleness threshold |
| M3 | No FAILED_SETTLEMENT lifecycle state | `instrument/lifecycle.py` | Add for CSDR penalty compliance |
| M4 | No partial close modeled | `instrument/lifecycle.py` | Add PARTIALLY_CLOSED or position split logic |
| M5 | Hypothesis ranges miss edge cases | `tests/test_commutativity.py` | Add fractional shares, extreme prices, multi-currency |
| M6 | LEI check digits not verified | `core/identifiers.py` | Add MOD 97-10 verification |
| M7 | Missing EMIR REFIT fields | `reporting/emir.py` | Add action type, notional, clearing flags |

---

## 11. Overall Verdict

**Phase 1 is APPROVED for merge with the above observations tracked.**

The arithmetic is correct. The conservation laws are enforced by construction and
verified at runtime. The type system prevents illegal states. The Decimal handling is
precise and consistent. The epistemic confidence model is well-designed for the asset
class. The property tests verify the right algebraic properties, even if the Master
Square test needs strengthening when a real pricing engine arrives.

The architecture is sound for extension to derivatives in Phase 2. The `Greeks`
dataclass already carries vanna, volga, and charm. The `DerivedConfidence` type with
fit quality metrics and confidence intervals is ready for model calibration outputs.
The `PnLAttribution` decomposition is correct.

The two areas requiring immediate attention before Phase 2 are:
1. **Minor-unit rounding** -- this is a regulatory requirement for any cash movement
2. **Price validation** -- zero/negative prices must be caught at the gateway, not
   discovered downstream as "cash amount must be positive"

Everything else can be addressed as Phase 2 progresses.

---

*"In financial infrastructure, as in volatility modeling, the constraints are not
obstacles -- they are the structure. A system that enforces conservation laws by
construction, rather than by testing, has the same relationship to correctness that
an arbitrage-free parameterization has to the volatility surface: the impossible states
are simply not representable."*
