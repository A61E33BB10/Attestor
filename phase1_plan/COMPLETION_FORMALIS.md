# FORMALIS Committee -- Phase 1 Completion Report

**System:** Attestor -- Cash Equity Lifecycle Management
**Phase:** 1 -- Full lifecycle: Order, Execution, Booking, Settlement (T+2), Dividend, Position Query
**Date:** 2026-02-15
**Committee:** Xavier Leroy (Chair), Thierry Coquand, Gerard Huet, Christine Paulin-Mohring, Leonardo de Moura, Jeremy Avigad
**Artefacts reviewed:** 32 source files, 25 test files, 494 tests passing

---

## 1. EXECUTIVE VERDICT

**Phase 1 is COMPLETE and the formal argument is SOUND within its stated scope.**

The conservation law proof is correct by construction. The commutativity
diagrams are valid for the tested morphisms. The type-level refinements
prevent a meaningful class of invalid states. The system demonstrates a
level of formal discipline that is uncommon in financial infrastructure
code.

We identify 3 HIGH findings and 5 MEDIUM findings, none of which
invalidate the core proof, but which represent gaps that should be
closed before Phase 2 extends the domain.

---

## 2. THE CONSERVATION LAW PROOF

### 2.1 Statement

**INV-L01 (Balance Conservation):** For every unit U and every transaction T
applied to ledger state sigma:

```
sigma'(U) = sigma(U)
```

where `sigma(U) = sum_{W in Accounts} beta(W, U)` and `sigma'` is the
state after executing T.

### 2.2 Proof Structure

The proof is **constructive** and proceeds by the following argument:

**Lemma 1 (Move Conservation).** For every `Move(source, destination, unit, quantity)`:

```
delta(source, unit) = -quantity.value
delta(destination, unit) = +quantity.value
sum of deltas for unit = 0
```

This holds by inspection of `LedgerEngine.execute()` lines 105-106
(`/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/engine.py`):

```python
self._balances[src_key] -= move.quantity.value
self._balances[dst_key] += move.quantity.value
```

The quantity is of type `PositiveDecimal` (value > 0 by construction),
and the same `move.quantity.value` is both subtracted and added.
Since `Decimal` subtraction and addition are exact (no rounding), the
net contribution of each Move to `sigma(unit)` is exactly zero. QED.

**Lemma 2 (Transaction Conservation).** A `Transaction` is a tuple of
Moves. Since `sigma` is a linear functional (sum of balances), and each
Move contributes zero to `sigma(unit)`, the entire transaction
contributes zero. QED.

**Lemma 3 (Post-verification).** Even though the proof is structural,
`LedgerEngine.execute()` performs a runtime verification (lines 109-123):
`total_supply(u)` is computed before and after, and any discrepancy
triggers atomic rollback. This is a **belt-and-suspenders** guard -- the
structural argument proves it will never trigger, but it serves as a
machine-checked assertion.

### 2.3 Assessment

**Leroy:** The proof is sound. The structure mirrors CompCert's approach:
prove the property structurally, then add a runtime check as a
certified monitor. The key insight is that `Decimal` arithmetic is exact
for addition and subtraction (no IEEE 754 rounding), so the algebraic
argument transfers directly to the implementation.

**Coquand:** The type `PositiveDecimal` prevents the degenerate case
of zero-quantity moves, which would be semantically vacuous but not
harmful to conservation. This is a sound design choice.

**de Moura:** I verified the `Decimal` precision argument. Python's
`decimal.Decimal` uses arbitrary-precision arithmetic for `+` and `-`.
The `ATTESTOR_DECIMAL_CONTEXT` (prec=28, ROUND_HALF_EVEN) only applies
to multiplication and division. Since `LedgerEngine.execute()` uses
only `+=` and `-=` on `Decimal`, conservation is exact. The settlement
and dividend modules use `localcontext(ATTESTOR_DECIMAL_CONTEXT)` for
`price * quantity` multiplication, but this value becomes a
`PositiveDecimal` that is then moved as an atomic unit -- the rounding
happens before the conservation-critical operation, not during it. This
is correct.

### 2.4 Test Coverage of the Proof

| Test ID | Property | Method | Location |
|---------|----------|--------|----------|
| CL-A1 | sigma(U) == 0 after arbitrary transactions | Hypothesis (200 examples) | `test_conservation_laws.py:55-83` |
| CL-A2 | Every move: source debit == destination credit | Direct assertion | `test_conservation_laws.py:112-142` |
| CL-A5 | Same inputs -> same outputs (100 runs) | Deterministic replay | `test_conservation_laws.py:150-165` |
| INV-L01 | sigma preserved after settlement | Direct | `test_settlement.py:89-111` |
| INV-L01 | sigma preserved after dividend | Direct | `test_dividends.py:91-112` |
| INV-L01 | sigma preserved in full lifecycle | Integration | `test_integration_lifecycle.py:110-111, 139-140, 167-168` |

**Avigad:** The Hypothesis tests (200 random examples for CL-A1) provide
strong probabilistic evidence but are not a formal proof. However,
combined with the structural argument in Section 2.2, the overall
assurance is equivalent to a pen-and-paper proof with machine-checked
examples. For a production system, this is excellent.

---

## 3. THE COMMUTATIVITY DIAGRAMS

### 3.1 CS-02: Master Square

**Statement:**

```
price(book(order)) == book(price(order))
```

More precisely: given a `StubPricingEngine` with oracle price p, the NPV
and final ledger positions are the same regardless of whether pricing
precedes or follows booking.

**Assessment:** The diagram is **trivially valid** in Phase 1 because
`StubPricingEngine.price()` is a pure function that does not read ledger
state. It returns `oracle_price` regardless of what has been booked.
Therefore the two paths produce identical results by the independence of
the two operations.

**Huet:** This is correct but weak. The diagram becomes non-trivial only
when the pricing engine reads positions from the ledger (e.g., to compute
portfolio Greeks). In Phase 1, pricing and booking operate on disjoint
state, so commutativity is a consequence of independence, not of a deep
structural property. The Hypothesis test (200 random price/qty pairs in
`test_commutativity.py:210-242`) confirms this.

**Severity: MEDIUM (M-01).** The Master Square will need to be re-proved
when pricing reads ledger state in Phase 2. The current proof structure
is a scaffold, not the final argument. This is acceptable for Phase 1.

### 3.2 CS-04: Reporting Naturality

**Statement:**

```
report(book(order)) == report(order)
```

The EMIR report is a **pure projection** from the `CanonicalOrder`,
independent of ledger state.

**Assessment:** This is **sound by construction.** The function
`project_emir_report` at `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/reporting/emir.py`
takes a `CanonicalOrder` and a `trade_attestation_id` as inputs. It does
not accept or access any ledger state. Every field of `EMIRTradeReport`
is derived from the order:

```python
report = EMIRTradeReport(
    uti=uti,                                    # derived from content_hash(order)
    reporting_counterparty_lei=order.executing_party_lei,
    other_counterparty_lei=order.counterparty_lei,
    instrument_id=order.instrument_id,
    isin=order.isin,
    direction=order.side,
    quantity=order.quantity,
    price=order.price,
    currency=order.currency,
    trade_date=order.trade_date,
    settlement_date=order.settlement_date,
    venue=order.venue,
    report_timestamp=order.timestamp,
    attestation_refs=(trade_attestation_id,),
)
```

Since the function's type signature `CanonicalOrder -> Attestation[EMIRTradeReport]`
does not include ledger state, booking cannot affect the result. The
commutativity is a consequence of the type-level separation.

**Paulin-Mohring:** This is the strongest commutativity result. The
naturality follows from the type structure alone -- one could extract
this directly from a Coq proof. The content hash stability test
(`test_commutativity.py:144-149`) confirms determinism.

### 3.3 CS-05: Lifecycle-Booking Naturality

**Statement:**

```
book(f ; g) == book(f) ; book(g)
```

Sequential settlements compose: applying two settlements to one engine
produces the same result as applying them separately.

**Assessment:** This is **sound** because:

1. Each settlement is an independent Transaction with a unique `tx_id`.
2. `LedgerEngine.execute()` applies moves atomically and records the
   `tx_id` for idempotency.
3. Two settlements on the same instrument and same accounts commute
   because `Decimal` addition is commutative and associative.
4. The test `test_booking_order_independence` (`test_commutativity.py:183-202`)
   explicitly verifies order independence by swapping execution order.

**de Moura:** The commutativity of booking operations is a consequence
of the commutativity and associativity of `Decimal.__add__`. Two
transactions T1 and T2 that operate on the same (account, unit) pair
produce the same final balance regardless of order because:

```
balance + delta1 + delta2 == balance + delta2 + delta1
```

This holds for all `Decimal` values. The argument extends to disjoint
(account, unit) pairs trivially (they do not interact). QED.

---

## 4. INVARIANT AUDIT

### 4.1 Invariants Stated and Verified

| ID | Invariant | Stated | Tested | Structurally Enforced |
|----|-----------|--------|--------|-----------------------|
| INV-L01 | Balance conservation | Yes | Yes (Hypothesis + direct) | Yes (Move structure) |
| INV-L04 | Settlement zero-sum | Yes | Yes | Yes (2 balanced Moves) |
| INV-L05 | Atomicity (rollback) | Yes | Yes | Yes (old_balances snapshot) |
| INV-L06 | Chart of accounts | Yes | Yes | Yes (pre-check) |
| INV-L09 | Clone independence | Yes | Yes | Yes (deep copy) |
| INV-X03 | Idempotency | Yes | Yes | Yes (tx_id set) |
| INV-G01 | Parse idempotency | Yes | Yes (roundtrip) | Structural |
| INV-G02 | Parse totality | Yes | Yes (Hypothesis fuzz) | By Result type |
| INV-R01 | Report is projection | Yes | Yes | By type signature |
| INV-R05 | Content-addressed | Yes | Yes | SHA-256 of canonical bytes |

### 4.2 Invariants Implied But Not Explicitly Stated

| ID | Missing Invariant | Severity |
|----|-------------------|----------|
| (new) | Move.source != Move.destination | MEDIUM |
| (new) | Transaction.moves is non-empty | MEDIUM |
| (new) | Dividend holder shares_held > 0 | MEDIUM |

---

## 5. FINDINGS

### FINDING H-01: Move Does Not Enforce source != destination [HIGH]

**Location:** `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/transactions.py:134-142`

```python
@final
@dataclass(frozen=True, slots=True)
class Move:
    source: str
    destination: str
    unit: str
    quantity: PositiveDecimal
    contract_id: str
```

**Violated Property:** A `Move` where `source == destination` is
semantically vacuous (transfers from A to A), does not violate
conservation, but represents an invalid business operation. The type
`DistinctAccountPair` exists in the same file and enforces `debit != credit`,
but `Move` uses raw strings instead of `DistinctAccountPair`.

**Impact:** Conservation is NOT affected (the self-transfer cancels out).
However, a self-transfer inflates the transaction log without economic
substance, which could mask errors or be exploited in audit trails.

**Remediation:** Either use `DistinctAccountPair` in `Move`, or add a
validation check in `create_settlement_transaction` and
`create_dividend_transaction`. Note that the dividend case naturally
prevents this (issuer != holder), but no type-level enforcement exists.

---

### FINDING H-02: Transaction Allows Empty Moves Tuple [HIGH]

**Location:** `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/transactions.py:146-153`

```python
@final
@dataclass(frozen=True, slots=True)
class Transaction:
    tx_id: str
    moves: tuple[Move, ...]
    timestamp: UtcDatetime
    state_deltas: tuple[StateDelta, ...] = ()
```

**Violated Property:** `tuple[Move, ...]` admits the empty tuple `()`.
An empty transaction trivially preserves sigma but consumes a `tx_id`
in the idempotency set, permanently preventing that ID from being
reused. This is a state-space pollution issue.

**Formal Statement:** The type should be `NonEmpty[tuple[Move, ...]]`
or, in Python, enforced by a smart constructor. Currently,
`LedgerEngine.execute()` will accept an empty transaction, record it,
and return `APPLIED`.

**Remediation:** Add a check in `LedgerEngine.execute()` or introduce a
validated `Transaction.create()` constructor.

---

### FINDING H-03: NonEmptyStr Constructor Bypass [HIGH]

**Location:** `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/core/money.py:72-81`

```python
@final
@dataclass(frozen=True, slots=True)
class NonEmptyStr:
    value: str

    @staticmethod
    def parse(raw: str) -> Ok[NonEmptyStr] | Err[str]:
        if not raw:
            return Err("NonEmptyStr requires non-empty string")
        return Ok(NonEmptyStr(value=raw))
```

**Violated Property:** The dataclass constructor `NonEmptyStr(value="")`
bypasses the `parse()` validation. This is used intentionally in
production code -- for example, `LedgerEngine.get_position()` at
`/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/engine.py:138-142`:

```python
def get_position(self, account_id: str, instrument: str) -> Position:
    return Position(
        account=NonEmptyStr(value=account_id),
        instrument=NonEmptyStr(value=instrument),
        quantity=self.get_balance(account_id, instrument),
    )
```

If `account_id` or `instrument` is the empty string, a `Position` with
an invalid `NonEmptyStr` is silently created.

**Formal Statement:** The refined type `NonEmptyStr` does not form a
proper subtype because its constructor does not enforce the refinement
predicate. In type-theoretic terms, the injection from `str` to
`NonEmptyStr` is not validated.

**Impact:** This does not affect conservation (balance keys are strings,
not NonEmptyStr), but it weakens the type-level guarantees. Any code
path that constructs `NonEmptyStr` directly (without `parse()`) can
introduce phantom values.

**Remediation:** Add `__post_init__` validation:

```python
def __post_init__(self) -> None:
    if not self.value:
        raise ValueError("NonEmptyStr requires non-empty string")
```

The same pattern applies to `PositiveDecimal`, `LEI`, `ISIN`, and `UTI`.

---

### FINDING M-01: Master Square Commutativity is Vacuously True [MEDIUM]

**Location:** `/home/renaud/A61E33BB10/ISDA/Attestor/tests/test_commutativity.py:70-96`

**Assessment:** As discussed in Section 3.1, the Master Square holds
because `StubPricingEngine` does not read ledger state. The commutativity
is a consequence of independence, not a structural property of the
pricing-booking interaction.

**Remediation:** Document this limitation. When Phase 2 introduces a
pricing engine that reads positions, the Master Square test must be
re-derived. Consider adding a comment:

```python
# NOTE: This commutativity holds because StubPricingEngine is state-independent.
# Phase 2 must re-prove when pricing reads ledger positions.
```

---

### FINDING M-02: Lifecycle State Machine Not Wired to Ledger [MEDIUM]

**Location:**
- `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/instrument/lifecycle.py:24-30`
- `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/engine.py:50-130`

**Assessment:** The lifecycle state machine (`EQUITY_TRANSITIONS`,
`check_transition`) is defined and tested in isolation, but it is not
enforced by `LedgerEngine.execute()`. A settlement transaction can be
booked without first verifying that the instrument is in the `FORMED`
state. The integration test (`test_integration_lifecycle.py`) calls
`check_transition` as a side assertion, but the ledger does not reject
a settlement for an instrument in `PROPOSED` state.

**Formal Statement:** The state machine and the ledger are
**not composed** -- they are verified independently. The commutativity
diagram assumes the composition `check_transition ; book`, but the
code does not enforce this sequencing.

**Remediation:** Either:
(a) Introduce a higher-level `settle()` function that composes
    `check_transition` and `LedgerEngine.execute()`, or
(b) Add instrument state tracking to `LedgerEngine` and enforce
    transition validation in `execute()`.

This is acceptable for Phase 1 (stated as a simplification) but must
be addressed in Phase 2.

---

### FINDING M-03: _add_business_days Skips Weekends Only [MEDIUM]

**Location:** `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/gateway/parser.py:19-27`

```python
def _add_business_days(start: date, days: int) -> date:
    """Add business days (skip weekends only -- Phase 1 simplification)."""
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current
```

**Assessment:** Documented as a Phase 1 simplification. Settlement date
computation ignores market holidays. For US equities, this means T+2
may land on a holiday (e.g., July 4th), producing an incorrect
settlement date.

**Formal Statement:** The function is total and deterministic (good), but
its specification does not match the real-world T+2 convention. This is
a **specification gap**, not an implementation bug.

**Remediation:** Phase 2 should inject a holiday calendar. The function
signature should become:

```python
def _add_business_days(start: date, days: int, holidays: frozenset[date]) -> date:
```

---

### FINDING M-04: Dividend Accepts Zero shares_held Without Error [MEDIUM]

**Location:** `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/dividends.py:69-91`

```python
for account_id, shares_held in holder_accounts:
    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        payment = amount_per_share * shares_held
    match PositiveDecimal.parse(payment):
        case Err(_):
            return Err(...)
```

**Assessment:** If `shares_held == 0`, then `payment == 0`, and
`PositiveDecimal.parse(0)` returns `Err`. This correctly rejects the
zero case. However, the error message says "payment must be > 0" without
indicating that the root cause is zero shares. More importantly, if
`shares_held < 0` (negative position), the payment would be negative,
which is also caught by `PositiveDecimal`. The function is effectively
total and correct, but the input type `Decimal` for `shares_held`
should be `PositiveDecimal` to express the precondition.

**Remediation:** Change the type of `holder_accounts` to
`tuple[tuple[str, PositiveDecimal], ...]` to encode the invariant at
the type level.

---

### FINDING M-05: total_supply Has O(n) Complexity [MEDIUM]

**Location:** `/home/renaud/A61E33BB10/ISDA/Attestor/attestor/ledger/engine.py:156-162`

```python
def total_supply(self, instrument: str) -> Decimal:
    total = Decimal(0)
    for (_, inst), qty in self._balances.items():
        if inst == instrument:
            total += qty
    return total
```

**Assessment:** This is called in the critical path of every
`execute()` -- once per affected unit, both before and after applying
moves. With N total (account, unit) pairs, the cost is O(N) per call.
For Phase 1 volumes this is acceptable, but it is called at least
twice per unit per transaction.

**Formal Statement:** The function is correct (it computes the sum
exactly), but its use in the verification loop creates an O(k * N)
overhead per transaction, where k is the number of affected units.
Since the structural proof (Section 2.2) guarantees conservation, the
runtime check is redundant from a correctness standpoint.

**Remediation:** Consider maintaining a running `_total_supply` dict
that is updated incrementally in O(1). Alternatively, since the proof
is structural, the post-verification could be gated behind a
`DEBUG` flag for production performance.

---

## 6. DETERMINISM AUDIT

**Requirement:** Same inputs must produce same outputs.

| Component | Deterministic? | Evidence |
|-----------|---------------|----------|
| `parse_order` | Yes | Pure function, no randomness |
| `CanonicalOrder.create` | Yes | Pure validation |
| `LedgerEngine.execute` | Yes | Sequential mutation, no concurrency |
| `create_settlement_transaction` | Yes | Pure function |
| `create_dividend_transaction` | Yes | Pure function |
| `project_emir_report` | Yes | Pure function, `content_hash` via SHA-256 |
| `ingest_equity_fill` | Yes | Pure function |
| `content_hash` | Yes | Sorted keys, canonical JSON, SHA-256 |
| `positions()` | Yes | `sorted(self._balances.items())` -- deterministic |
| `FrozenMap.create` | Yes | Sorted entries |
| `UtcDatetime.now()` | **NO** | Reads system clock |

**de Moura:** The system is deterministic modulo `UtcDatetime.now()`,
which is used only in error construction paths (never in the
conservation-critical code path). The `check_transition` function calls
`UtcDatetime.now()` for the error timestamp, but this is in the `Err`
branch only. The `Ok` paths are entirely deterministic.

CL-A5 (100-run determinism test) confirms this for the ledger engine.

---

## 7. TOTALITY AUDIT

**Requirement:** Functions should be defined for all valid inputs.

| Function | Total? | Domain | Notes |
|----------|--------|--------|-------|
| `parse_order` | Yes | `dict[str, object]` | Hypothesis-fuzzed (200 random dicts) |
| `CanonicalOrder.create` | Yes | All parameter combinations | Returns `Ok` or `Err` |
| `LedgerEngine.execute` | Yes | Any `Transaction` | Returns `Ok` or `Err` |
| `create_settlement_transaction` | Yes | Any `CanonicalOrder` + strings | Returns `Ok` or `Err` |
| `create_dividend_transaction` | Yes | Parameter combinations | Returns `Ok` or `Err` |
| `check_transition` | Yes | All `PositionStatusEnum` pairs | Exhaustive test in `test_lifecycle.py` |
| `project_emir_report` | Yes | Any `CanonicalOrder` + string | Returns `Ok` or `Err` |
| `content_hash` | Yes | Any serializable object | Returns `Ok` or `Err` |

**Paulin-Mohring:** The consistent use of `Ok[T] | Err[E]` return types
throughout the codebase is the Python equivalent of Coq's `sum` type.
No domain function raises exceptions. The `unwrap()` free function is
used only in tests, never in production code. This is a sound approach
to totality in a dynamically-typed language.

---

## 8. TYPE-LEVEL GUARANTEES

### 8.1 Refined Types in Use

| Type | Refinement | Enforced by |
|------|-----------|-------------|
| `PositiveDecimal` | `value > 0` | `parse()` smart constructor |
| `NonEmptyStr` | `value != ""` | `parse()` smart constructor |
| `LEI` | 20 alphanumeric chars | `parse()` with length + charset check |
| `ISIN` | 12 chars, Luhn check | `parse()` with full validation |
| `UTI` | 1-52 chars, prefix alnum | `parse()` with constraints |
| `UtcDatetime` | timezone-aware | `parse()` rejects naive datetimes |
| `Money` | finite Decimal + currency | `create()` smart constructor |
| `DistinctAccountPair` | debit != credit | `create()` smart constructor |
| `FrozenMap` | sorted, immutable | `create()` with sorted entries |
| `CanonicalOrder` | 14-field validated aggregate | `create()` with multi-field validation |

### 8.2 Assessment

**Coquand:** The refined types form a reasonable approximation of
dependent types in Python. The `@final` and `frozen=True` annotations
prevent subclassing and mutation, which are the two main escape hatches
in Python's type system. The `slots=True` annotation prevents dynamic
attribute addition. This is as close to a sealed, immutable type as
Python permits.

**Gap (Finding H-03):** The raw dataclass constructors bypass validation.
This is a fundamental limitation of Python -- there is no way to make
the constructor private while keeping `frozen=True`. The
`__post_init__` approach is the standard mitigation.

---

## 9. COMPOSITIONALITY

### 9.1 Module Dependency Graph

```
gateway.parser -> gateway.types -> core.{identifiers, money, result, types}
instrument.types -> core.{identifiers, money, result}
instrument.lifecycle -> gateway.types, instrument.types, core.*
ledger.transactions -> core.{money, result, types}
ledger.engine -> ledger.transactions, core.{errors, money, result}
ledger.settlement -> gateway.types, ledger.transactions, core.*
ledger.dividends -> ledger.transactions, core.*
oracle.ingest -> oracle.attestation, core.*
oracle.attestation -> core.{money, result, serialization, types}
reporting.emir -> gateway.types, oracle.attestation, core.*
pricing.protocols -> pricing.types, core.{errors, result, types}
```

### 9.2 Assessment

**Leroy:** The dependency graph is a DAG (no cycles). Each module can be
verified independently, and the composition follows from interface
compatibility. The `core` layer provides shared types; the `gateway`,
`instrument`, `ledger`, `oracle`, `reporting`, and `pricing` modules
are siblings that interact through the `core` types.

The key composition is:

```
parse_order: dict -> Ok[CanonicalOrder]
create_settlement_transaction: CanonicalOrder -> Ok[Transaction]
LedgerEngine.execute: Transaction -> Ok[ExecuteResult]
project_emir_report: CanonicalOrder -> Ok[Attestation[EMIRTradeReport]]
```

Each function takes the output type of the previous as input
(or a subset thereof). The end-to-end integration test
(`test_integration_lifecycle.py:38-188`) verifies this full composition.

---

## 10. END-TO-END LIFECYCLE VERIFICATION

The integration test at `/home/renaud/A61E33BB10/ISDA/Attestor/tests/test_integration_lifecycle.py`
exercises all 5 pillars in sequence:

1. **Gateway (Pillar I):** Raw dict -> `parse_order` -> `CanonicalOrder`
2. **Instrument (Pillar II):** `create_equity_instrument`, `check_transition`
3. **Oracle (Pillar III):** `ingest_equity_fill` -> `Attestation[MarketDataPoint]`
4. **Ledger (Pillar IV):** `create_settlement_transaction` + `execute`, then `create_dividend_transaction` + `execute`
5. **Reporting/Pricing (Pillar V):** `StubPricingEngine.price`, `project_emir_report`

**Post-conditions verified:**
- INV-L01: `total_supply("USD") == 0`, `total_supply("AAPL") == 0`
- INV-X03: Replay returns `ALREADY_APPLIED`
- INV-L09: Clone produces identical positions
- INV-R05: Content hash is stable across invocations
- Transaction count: 2 (settlement + dividend)
- Position count: >= 4 non-zero positions

**Avigad:** The integration test is the mathematical equivalent of
checking that the composition of verified lemmas produces the main
theorem. Each pillar is tested in isolation (unit tests) and then
composed (integration test). This is sound methodology.

---

## 11. PROPERTY-BASED TESTING ASSESSMENT

The project uses Hypothesis for property-based testing in 4 critical areas:

| Test | Property | Examples | Scope |
|------|----------|----------|-------|
| `test_sigma_invariant_random_transactions` | sigma(U) == 0 | 200 | Random amounts, random units |
| `test_sigma_preserved_hypothesis` | sigma(U) == 0 | 200 | Random amounts, fixed 2 accounts |
| `test_master_square_property` | NPV_A == NPV_B, positions match | 200 | Random price x qty |
| `test_never_panics` | parse_order returns Ok or Err | 200 | Random dicts |

**de Moura:** 200 examples per property is a reasonable default for
Hypothesis. The search space is well-bounded (Decimal with 2 decimal
places, max 6 digits). For the conservation law, the property is
universally quantified over all valid transactions, and the structural
proof (Section 2.2) covers the general case. The Hypothesis tests serve
as additional confidence, not as the primary proof.

---

## 12. SUMMARY TABLE

| Criterion | Status | Notes |
|-----------|--------|-------|
| Specification complete | **PASS** | All invariants stated |
| Types prevent invalid states | **PASS with caveats** | H-03: constructor bypass |
| Invariants stated and preserved | **PASS** | 10 invariants verified |
| Functions total | **PASS** | All return Ok or Err |
| Behavior deterministic | **PASS** | Modulo UtcDatetime.now() in error paths |
| Correctness compositional | **PASS** | DAG dependency, integration test |
| Conservation law correct | **PASS** | Structural proof + runtime check |
| Commutativity diagrams sound | **PASS with caveats** | M-01: Master Square vacuously true |
| End-to-end lifecycle verified | **PASS** | Full 5-pillar integration test |

---

## 13. RECOMMENDATIONS FOR PHASE 2

1. **Close H-01, H-02, H-03** before extending the domain. These are
   type-level gaps that become more dangerous with more complex
   instruments.

2. **Wire the lifecycle state machine to the ledger** (M-02). The
   current architecture verifies transitions and bookings independently;
   Phase 2 derivatives will require composed verification.

3. **Re-derive the Master Square** when pricing reads ledger state.
   The current proof is vacuously true and will not survive the
   introduction of position-dependent pricing.

4. **Inject holiday calendar** for T+2 computation (M-03).

5. **Consider incremental sigma tracking** for performance (M-05),
   especially when the number of (account, unit) pairs grows with
   multi-asset support.

---

## 14. CONCLUSION

Phase 1 of Attestor achieves what it set out to prove: the conservation
law holds end-to-end for the cash equity lifecycle, the commutativity
diagrams are valid within their stated scope, and the system is
deterministic and total.

The 3 HIGH findings relate to type-level enforcement gaps that do not
invalidate the core proofs but should be closed. The 5 MEDIUM findings
are documented limitations appropriate for Phase 1 scope.

The codebase demonstrates unusual discipline: frozen immutable types,
monadic error handling without exceptions, property-based testing,
explicit invariant statements, and constructive proofs by code structure.
This is a sound foundation for the more complex instruments in Phase 2.

*"The verification of the compiler guarantees that safety properties
proved on the source code hold for the executable. Here, the properties
proved on the types hold for the transactions."*

-- Xavier Leroy, Chair, FORMALIS Committee
