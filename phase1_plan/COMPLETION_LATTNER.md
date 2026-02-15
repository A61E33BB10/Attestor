# Phase 1 Completion Report -- Architecture Review

**Reviewer:** Chris Lattner
**Date:** 2026-02-15
**Scope:** All new Phase 1 modules (32 source files, 494 tests, mypy --strict clean, ruff clean)

---

## Executive Verdict

This is well-designed financial infrastructure. The architecture is right,
and that means it can be improved forever. The module structure is clean,
the APIs are designed for extension, the one mutable class is properly
encapsulated, and Phase 2 additions (options, futures) will require new
files, not refactoring.

I have a handful of observations that range from "fix before Phase 2" to
"monitor as the system grows," but nothing that undermines the structural
integrity of what was built here.

---

## 1. Module Structure

### 1.1 What Is Right

The dependency graph flows in one direction:

```
core/  <--  gateway/  <--  instrument/  <--  ledger/  <--  oracle/  <--  reporting/
                                                              ^
                                                              |
                                                          infra/protocols
```

No cycles. No diamond dependencies. Each pillar depends only on core/ and
the pillars logically upstream of it. This is the most important property
a modular system can have. When I built LLVM, the single hardest thing to
maintain over two decades was the layering discipline between libraries --
MC should not depend on CodeGen, CodeGen should not depend on the
optimizer. The moment you allow a single backward edge, you have
unlocked a world of pain. This codebase does not have that problem.

The file tree follows a consistent pattern:

```
pillar/
  __init__.py    -- re-exports public API
  types.py       -- frozen value types
  <function>.py  -- pure functions over those types
```

This is the right decomposition. Types are data. Functions are behavior.
They live in separate files so you can understand the data model without
reading the algorithms. When you need to add a new instrument type in
Phase 2, you open `instrument/types.py` and add a dataclass. You do not
need to understand `lifecycle.py` to do this.

### 1.2 One Import Worth Watching

`attestor/instrument/lifecycle.py` imports from `attestor.gateway.types`
to use `CanonicalOrder` inside `ExecutePI`. This creates a dependency from
Pillar II (instrument) to Pillar I (gateway). It is justified today --
`ExecutePI` wraps an order, and the order is the gateway's output. But
monitor this edge. If instrument/ starts importing more gateway internals,
the boundary between these pillars is eroding.

An alternative for Phase 2: define a `TradeTerms` type in `instrument/`
that captures the fields `ExecutePI` actually needs, and map from
`CanonicalOrder` at the boundary. This would decouple the instruction
types from the gateway parser entirely. Not urgent, but worth considering
when options and futures bring their own order shapes.

### 1.3 SQL Migrations

The six new DDLs (004-009) are clean:

- Append-only enforcement via `prevent_mutation()` triggers on accounts,
  transactions, orders, emir_reports, and market_data.
- Bitemporal positions table with (valid_time, system_time) and the
  correct composite primary key.
- CHECK constraints mirror the Python-side validation: `side IN ('BUY',
  'SELL')`, `quantity > 0`, `length(lei) = 20`.

Minor note: `sql/007_orders.sql` stores orders, not instruments.
`sql/006_transactions.sql` uses `executed_at` while the plan called for
`valid_time`. Both are fine -- the schema is internally consistent and
the column names are clear. The plan was aspirational; the implementation
is correct.

---

## 2. API Design

### 2.1 The Result Pattern

Every function that can fail returns `Ok[T] | Err[E]`. No exceptions in
the domain layer. This is the single most important design decision in the
entire codebase, and it is applied with total consistency.

The `match` statement usage is particularly clean:

```python
match CanonicalOrder.create(...):
    case Ok(order):
        ...
    case Err(e):
        ...
```

This is Python's structural pattern matching used exactly as it should be.
The exhaustiveness is enforced by mypy --strict, which means if someone
adds a third Result variant (they should not), the compiler tells you
everywhere you need to handle it.

### 2.2 Factory Functions Over Constructors

Every validated type uses a `@staticmethod create()` or `parse()` factory
that returns `Result`. The raw `__init__` is still available (frozen
dataclass), but the convention is clear: use the factory. This is the
same pattern Swift uses for failable initializers, and it works well.

The `CanonicalOrder.create()` factory in `gateway/types.py` is
particularly well done. It collects all field violations into a list
before returning, rather than failing on the first error. This is
essential for user-facing validation -- when someone submits a bad order,
they want to know about ALL the problems, not discover them one at a time.

I have seen systems that fail on the first validation error, and users
hate them. Error messages are UI. Batch validation is the right call.

### 2.3 Progressive Disclosure of Complexity

A user who wants to parse an order writes:

```python
from attestor.gateway import parse_order
result = parse_order(raw_dict)
```

A user who needs to construct an order directly writes:

```python
from attestor.gateway import CanonicalOrder, OrderSide, OrderType
result = CanonicalOrder.create(order_id=..., side=OrderSide.BUY, ...)
```

A user who needs to build a custom settlement writes:

```python
from attestor.ledger.transactions import Move, Transaction
from attestor.core.money import PositiveDecimal
```

The simple path is simple. The power path is available. This is exactly
right.

### 2.4 Re-Exports Form a Coherent Public API

Each `__init__.py` re-exports the types and functions that constitute the
module's public API. The re-export style uses explicit `as` aliases, which
ensures mypy treats them as public:

```python
from attestor.gateway.types import CanonicalOrder as CanonicalOrder
from attestor.gateway.parser import parse_order as parse_order
```

The gateway `__init__.py` exports 5 symbols. The instrument `__init__.py`
exports 5 symbols. The ledger `__init__.py` exports 18 symbols (the full
transaction vocabulary). These are the right sizes -- small enough to
understand at a glance, comprehensive enough that you rarely need to reach
into submodules.

One gap: `attestor/reporting/__init__.py` is empty (just a docstring).
`EMIRTradeReport` and `project_emir_report` are not re-exported. This
means users must write `from attestor.reporting.emir import ...` instead
of `from attestor.reporting import ...`. Minor inconsistency -- should be
fixed for completeness before Phase 2 adds more report types.

Similarly, `oracle/ingest.py` types (`MarketDataPoint`, `ingest_equity_fill`,
`ingest_equity_quote`) are not re-exported from `oracle/__init__.py`. The
oracle `__init__.py` only re-exports the attestation types. This is
arguably intentional (ingest is an implementation detail), but it creates
an asymmetry with the gateway module. Worth deciding on a consistent
policy.

The `infra/__init__.py` does not re-export Phase 1 topics
(`PHASE1_TOPICS`, `phase1_topic_configs`, `TOPIC_ORDERS`, etc.). The
Phase 0 topics are re-exported but the Phase 1 ones are not. This should
be fixed for consistency.

---

## 3. LedgerEngine -- The One Mutable Class

### 3.1 Encapsulation

`LedgerEngine` is the only class in the domain that holds mutable state.
It is `@final` (cannot be subclassed), all internal state is underscore-
prefixed (`_accounts`, `_balances`, `_transactions`, `_applied_tx_ids`),
and the public API is exclusively through well-typed methods.

The internal state is:
- `_accounts: dict[str, Account]` -- chart of accounts
- `_balances: dict[tuple[str, str], Decimal]` -- balance by (account, instrument)
- `_transactions: list[Transaction]` -- append-only transaction log
- `_applied_tx_ids: set[str]` -- idempotency guard

This is the minimum state needed for a double-entry ledger. No extra
fields, no optional state, no configuration knobs. Clean.

### 3.2 Conservation Law Enforcement

The `execute()` method implements a pre/post sigma check:

1. Compute `sigma(U) = sum of all balances for unit U` before the transaction
2. Apply all moves
3. Recompute sigma(U) after the transaction
4. If any sigma changed, REVERT all balance changes and return `Err`

This is a belt-and-suspenders approach. The conservation law *should* hold
by construction (every Move subtracts from source and adds to destination).
The post-check is a runtime assertion that the invariant held. This costs
O(N) per execute where N is the number of balances, but for the current
in-memory implementation that is fine.

When this moves to Postgres, the conservation check will be a SQL
constraint or trigger, not a Python scan. The architecture supports this
transition because `LedgerEngine` is behind a clean interface -- you can
replace the implementation without changing any caller.

### 3.3 Atomicity

On any failure during `execute()`, the old balances are restored:

```python
old_balances: dict[tuple[str, str], Decimal] = {}
for move in tx.moves:
    # save old values
    ...
# on failure:
for key, val in old_balances.items():
    self._balances[key] = val
```

This is the correct approach for an in-memory implementation. When moving
to a database, this becomes a SQL transaction with ROLLBACK. The pattern
is right for both cases.

### 3.4 Clone for Time-Travel

`clone()` creates a deep copy by reconstructing all internal state:

```python
def clone(self) -> LedgerEngine:
    new = LedgerEngine()
    new._accounts = dict(self._accounts)
    new._balances = defaultdict(Decimal, self._balances)
    new._transactions = list(self._transactions)
    new._applied_tx_ids = set(self._applied_tx_ids)
    return new
```

This enables point-in-time queries and replay testing. The test suite
verifies clone independence -- mutations to the clone do not affect the
original (INV-L09). This is the right pattern for the in-memory case.

### 3.5 Performance Note

`total_supply()` does a linear scan of all balances:

```python
def total_supply(self, instrument: str) -> Decimal:
    total = Decimal(0)
    for (_, inst), qty in self._balances.items():
        if inst == instrument:
            total += qty
    return total
```

This is O(N) where N is the number of (account, instrument) pairs. For
Phase 1 with small numbers of accounts, this is fine. For Phase 3+ with
thousands of accounts and instruments, this should be optimized to
maintain a running `_supply: dict[str, Decimal]` that is updated in
`execute()`. The current implementation is correct and optimizable later
without API changes -- which is the right ordering of concerns.

---

## 4. Type Design

### 4.1 Value Semantics by Default

Every domain type is `@final @dataclass(frozen=True, slots=True)`. This
means:

- **Immutable**: no field can be modified after construction
- **Value equality**: two instances with the same fields are equal
- **Hashable**: can be used as dict keys or set members
- **Memory efficient**: `slots=True` avoids `__dict__` overhead
- **Sealed**: `@final` prevents subclassing

This eliminates entire categories of bugs. You cannot accidentally mutate
a `CanonicalOrder` after it has been validated. You cannot create a
`Monkey`-patched subclass of `Money` that breaks arithmetic invariants.
The types enforce their contracts at construction time via factories, and
nothing can violate those contracts afterward.

### 4.2 Newtype Pattern for Domain Primitives

`NonEmptyStr`, `PositiveDecimal`, `LEI`, `UTI`, `ISIN` -- each wraps a
raw Python type with validation at the boundary. Once you have a `LEI`,
you know it is exactly 20 alphanumeric characters. You do not need to
check again. This pushes validation to the edges and makes the core
logic clean.

The `ISIN` validation includes a full Luhn check digit algorithm. This
is the kind of detail that prevents subtle data quality issues from
propagating through the system.

### 4.3 Union Types for Extensibility

```python
PrimitiveInstruction = ExecutePI | TransferPI | DividendPI
Confidence = FirmConfidence | QuotedConfidence | DerivedConfidence
```

These union types are the extension points for Phase 2. Adding an
`OptionExercisePI` to `PrimitiveInstruction` is a one-line change to the
type alias plus a new `@final` dataclass. mypy will then flag every
`match` statement that does not handle the new variant. This is exactly
how Swift enums work, and it is the right pattern for closed
discriminated unions.

### 4.4 EconomicTerms.payout Extensibility

The plan explicitly notes that `EconomicTerms.payout` is `EquityPayoutSpec`
today and will become `EquityPayoutSpec | OptionPayoutSpec | FuturesPayoutSpec`
in Phase 2. This transition requires changing exactly one type annotation
and adding the new payout spec dataclasses. No existing code needs to
change -- it already handles `EquityPayoutSpec` and will simply not
match the new variants until you add handlers.

This is the library-over-language principle in action: the type system
does the work, not ad-hoc runtime checks.

---

## 5. Testing Architecture

### 5.1 Test Coverage

494 tests covering:

- **Unit tests**: Every type factory, every validation path, every error case
- **Property-based tests** (Hypothesis): Conservation laws with 200+ random
  transactions, parse totality (never panics on arbitrary input),
  commutativity across random (price, qty) pairs
- **Integration tests**: Full lifecycle from raw order dict to EMIR report,
  passing through all five pillars
- **Invariant tests**: Conservation (CL-A1), double-entry (CL-A2),
  deterministic execution (CL-A5), replay determinism

The property-based testing is particularly strong. The conservation law
test generates random transaction amounts and random units, executes them,
and verifies `sigma(U) == 0` for all units. This is how you catch
numerical edge cases that no human would think to write as explicit test
cases.

### 5.2 The Master Square

The commutativity test (`test_commutativity.py`) verifies that booking then
pricing equals pricing then booking. With a stub pricer this is almost
tautological, but the test infrastructure is in place for Phase 2 when
the pricer becomes real. The property-based variant runs 200 random
(price, qty) combinations.

The reporting naturality test (CS-04) verifies that `project_emir_report`
produces the same output regardless of whether the order has been booked
into the ledger. This proves INV-R01: reporting is projection, not
transformation.

### 5.3 Test Helpers

Each test file defines its own `_acct()`, `_order()`, `_move()`, `_tx()`
helpers. There is some duplication here. Consider extracting common
test fixtures into `conftest.py` for Phase 2 -- not because DRY is
sacred, but because when you add options, you will want the same
test scaffolding patterns.

---

## 6. Phase 2 Readiness Assessment

The critical question: **Will Phase 2 additions require refactoring or
just new files?**

### 6.1 Adding Options (Phase 2)

Required changes:
1. **New file**: `instrument/option_types.py` with `OptionPayoutSpec`
2. **One-line change**: `EconomicTerms.payout: EquityPayoutSpec | OptionPayoutSpec`
3. **New file**: `instrument/option_lifecycle.py` with `OPTION_TRANSITIONS`
4. **New variant**: `ExercisePI` added to `PrimitiveInstruction` union
5. **New file**: `ledger/exercise.py` with `create_exercise_transaction()`
6. **New file**: `oracle/option_ingest.py` for vol surface attestations

No existing file requires structural changes. The union types widen. The
transition tables grow. The ledger engine is untouched -- it operates on
`Transaction` and `Move`, which are instrument-agnostic.

### 6.2 Adding Futures (Phase 2)

Same pattern as options:
1. `FuturesPayoutSpec` in `instrument/`
2. `MarkToMarketPI` in `lifecycle.py`
3. `create_margin_transaction()` in `ledger/`

### 6.3 Adding Real Pricing (Phase 2+)

The `PricingEngine` protocol already defines the interface. The
`StubPricingEngine` test double satisfies it. A real implementation (Black-
Scholes, local vol, whatever) implements the same protocol. The ledger,
gateway, and reporting modules do not care -- they never import from
`pricing/` except for the protocol types.

### 6.4 Verdict

Phase 2 requires new files and union type widening. No refactoring.
This is the hallmark of a well-factored system.

---

## 7. Specific Findings

### 7.1 Should Fix Before Phase 2

**F-01. Incomplete re-exports in reporting/__init__.py.**

`attestor/reporting/__init__.py` contains only a docstring. It should
re-export `EMIRTradeReport` and `project_emir_report` so users can write
`from attestor.reporting import EMIRTradeReport`.

**F-02. Phase 1 topic configs not re-exported from infra/__init__.py.**

`PHASE1_TOPICS`, `phase1_topic_configs`, and the five individual topic
constants are defined in `infra/config.py` but not re-exported from
`infra/__init__.py`. Phase 0 topics are re-exported.

**F-03. Oracle ingest types not re-exported from oracle/__init__.py.**

`MarketDataPoint`, `ingest_equity_fill`, and `ingest_equity_quote` are
accessible only via `from attestor.oracle.ingest import ...`. Either
re-export them from `oracle/__init__.py` or document that `ingest` is
a submodule users import directly. Choose one pattern and apply it
consistently.

### 7.2 Worth Monitoring

**M-01. total_supply() linear scan.**

`LedgerEngine.total_supply()` iterates all balances. O(N) per call,
called twice per `execute()` per affected unit. Not a problem today.
Will need a running supply index when account counts grow past ~10k.
The fix is local to `LedgerEngine` internals and does not change the API.

**M-02. get_position() bypasses NonEmptyStr validation.**

`LedgerEngine.get_position()` constructs `NonEmptyStr(value=account_id)`
directly without going through `NonEmptyStr.parse()`. This is safe
because the account_id was validated when the account was registered,
but it is a departure from the factory-everywhere pattern. If someone
calls `get_position("", "USD")`, they get a `Position` with an empty
account name that should not exist.

**M-03. Gateway-to-Instrument coupling via ExecutePI.**

`instrument/lifecycle.py` imports `CanonicalOrder` from gateway. This is
the one cross-pillar dependency that is not strictly core-to-downstream.
Acceptable for Phase 1; consider introducing a `TradeTerms` abstraction
if options and futures bring different order shapes.

**M-04. LedgerEntry.attestation typed as Any.**

`LedgerEntry.attestation` is typed `Any | None` with a comment about
avoiding circular imports. This is the one `Any` in the domain layer.
It should be resolved in Phase 2 -- either by introducing a protocol
type or by restructuring imports. The comment acknowledges the debt.

### 7.3 Commendations

**C-01. Error collection, not error short-circuiting.**

Both `CanonicalOrder.create()` and `parse_order()` collect all validation
errors before returning. This is the right UX for validation.

**C-02. Conservation law is belt-and-suspenders.**

The pre/post sigma check in `execute()` is mathematically unnecessary
(the Move semantics guarantee conservation by construction), but it
catches implementation bugs. This is defense in depth applied correctly.

**C-03. Content-addressed attestation identity.**

`attestation_id = SHA-256(canonical_bytes(full_identity))` gives you
deterministic, reproducible identity for every attested value. Same
inputs always produce the same attestation_id. Different inputs always
produce different ids. This is the foundation that makes audit trails
trustworthy.

**C-04. Hypothesis property tests for the hard invariants.**

Conservation, totality, commutativity -- these are the properties that
matter most, and they are tested with random inputs, not just happy-path
examples. This catches edge cases that humans miss.

**C-05. Append-only enforced at every layer.**

Python domain: frozen dataclasses, no mutation methods.
SQL: `prevent_mutation()` triggers blocking UPDATE and DELETE.
Kafka: topic configs with appropriate retention.
Three layers of enforcement for the same invariant. This is how you
build financial infrastructure that auditors trust.

---

## 8. Metrics

| Metric | Target (from Plan) | Actual | Delta |
|--------|:---:|:---:|:---:|
| New production files | 12 new + 3 updates | 12 new + 3 updates | On target |
| New test files | ~15 | 13 new | Close (some tests consolidated) |
| Total tests | ~486 | 494 | +8 over target |
| New SQL DDLs | 6 | 6 | On target |
| mypy --strict | Clean | Clean | Pass |
| ruff | Clean | Clean | Pass |
| Property-based test examples | 1000+ | 200/test x multiple tests | Pass |
| Conservation law violations | 0 | 0 | Pass |
| Domain `Any` usage | 0 | 1 (LedgerEntry.attestation) | Known debt |
| Cross-pillar imports (non-core) | Minimal | 1 (lifecycle -> gateway) | Acceptable |

---

## 9. Architectural Assessment

### What This System Got Right

1. **The dependency graph is acyclic and layered.** This is the single
   most important property. Everything else can be fixed if this holds.

2. **Value semantics are the default.** Frozen dataclasses everywhere.
   The one mutable class (LedgerEngine) is identified, encapsulated,
   and `@final`.

3. **Error handling is in the type system.** `Ok | Err`, not try/except.
   Every error is a value that can be inspected, serialized, and tested.

4. **Extension is additive.** Phase 2 adds files. It does not modify
   the architecture.

5. **The invariants are machine-checked.** Conservation, commutativity,
   totality, idempotency -- all verified by tests, many with random
   inputs. The invariants are not documentation. They are executable
   specifications.

### The Lattner Test

When I evaluate infrastructure, I ask: "What happens when someone uses
this system in a way nobody anticipated?"

- Can someone add a new instrument type without modifying the ledger?
  **Yes.** The ledger operates on Move and Transaction, which are
  instrument-agnostic.

- Can someone add a new regulatory report without modifying the gateway?
  **Yes.** Reports are projections from CanonicalOrder, which is
  gateway output.

- Can someone replace the in-memory ledger with a Postgres-backed one
  without changing any domain code? **Yes.** The TransactionLog protocol
  defines the interface.

- Can someone add a sixth conservation law without touching existing
  tests? **Yes.** Add a new test class that exercises execute().

This system is designed for extension by people who were not in the room
when the architecture was decided. That is what infrastructure means.

---

## 10. Conclusion

Phase 1 is complete and architecturally sound. The module structure is
clean, the APIs are designed for extension, and the test suite proves
the invariants that matter. The three findings (F-01 through F-03) are
minor re-export gaps that should be fixed before Phase 2 for API
consistency. The four monitoring items (M-01 through M-04) are technical
debt that is acknowledged, bounded, and non-blocking.

Ship it. Build Phase 2 on this foundation.

---

*"The measure of good infrastructure is not how well it serves today's*
*requirements, but how gracefully it accommodates tomorrow's surprises."*

*-- Phase 1 Architecture Review, 2026-02-15*
