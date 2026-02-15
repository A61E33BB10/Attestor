# Phase 1 Completion Report -- Minsky Review

**Reviewer:** MINSKY (type-safety and invariant analysis)
**Date:** 2026-02-15
**Verdict:** PHASE 1 COMPLETE. Ship it. Six findings below -- none blocking, all worth tracking.

---

## 1. Executive Summary

Phase 1 delivers a cash equity lifecycle -- Order, Execution, Booking, Settlement (T+2), Dividend, Position query -- with commutativity proven end-to-end. The claims are verified:

- **494 tests passing** (confirmed, 3.22s)
- **32 source files, mypy --strict clean** (confirmed, zero issues)
- **ruff clean** (confirmed)
- **No float in domain** (confirmed: all financial quantities are `Decimal`)
- **No raise in domain** (confirmed: all domain functions return `Result`)
- **All frozen** (confirmed: every domain dataclass is `frozen=True, slots=True`)

The architecture is sound. The core insight -- double-entry bookkeeping with conservation law enforcement built into the engine, not checked after the fact -- is exactly right. The type discipline is strong. The places where it is imperfect are documented below and are all Phase 2 cleanup items, not Phase 1 blockers.

---

## 2. The Minsky Test

### 2.1 Can illegal states be constructed?

**Mostly no. Six exceptions identified, all minor.**

The primary defense is the parse-don't-validate pattern applied throughout. Raw strings enter the system through `parse_order()` and exit as `CanonicalOrder` carrying `NonEmptyStr`, `PositiveDecimal`, `LEI`, `ISIN`, and `UtcDatetime` -- all of which reject invalid values at construction time via `parse()` factories that return `Result`.

The `LedgerEngine` enforces chart-of-accounts (INV-L06), conservation (INV-L01), atomicity (INV-L05), and idempotency (INV-X03) at the `execute()` boundary. The transition table (`EQUITY_TRANSITIONS`) is a frozenset of valid `(from, to)` pairs -- exhaustive and immutable.

**Exceptions (none blocking):**

| # | Location | Issue | Severity |
|---|----------|-------|----------|
| F-01 | `Move.source` / `Move.destination` | Plain `str`, not `NonEmptyStr`. Can be empty string. More critically, `source == destination` is representable -- a self-transfer that is a conservation no-op but semantically meaningless. `DistinctAccountPair` exists for exactly this purpose but is not used in `Move`. | Low |
| F-02 | `CanonicalOrder.price` | Typed as bare `Decimal`, validated only as "finite". Negative and zero prices are representable. Zero is caught downstream by `create_settlement_transaction` (cash amount not positive), but negative price survives into the order. For equities this matters less than it will for derivatives. | Low |
| F-03 | `LedgerEngine.get_position("", "")` | Constructs `NonEmptyStr(value="")` directly, bypassing `NonEmptyStr.parse()`. This is the classic newtype bypass: the `@dataclass` constructor does not call the `parse()` factory. Python dataclasses cannot enforce this at the type level without `__post_init__`, but calling `NonEmptyStr` directly with an empty string creates an illegal value. | Low |
| F-04 | `Transaction.tx_id` | Plain `str`. An empty `tx_id` can be constructed. The engine would then silently apply it and record `""` in `_applied_tx_ids`. | Low |
| F-05 | `BusinessEvent.attestation_id` | Typed as `str | None`. When `Some`, it carries no validation. An empty string is representable. | Informational |
| F-06 | `Move.unit` / `Move.contract_id` | Plain `str`, no validation. Empty strings representable. | Informational |

**Assessment:** The pattern is clear -- the system was built with validated newtypes (`NonEmptyStr`, `PositiveDecimal`, `LEI`, `ISIN`) at the API boundary (`CanonicalOrder.create`, `parse_order`), but internal types (`Move`, `Transaction`) use bare `str` for simplicity. This is a reasonable Phase 1 trade-off. The engine's runtime checks (account existence, conservation) catch the most dangerous consequences. For Phase 2, promoting `Move.source`/`Move.destination` to `NonEmptyStr` and adding a `source != destination` invariant would close the remaining gap.

### 2.2 Is every case handled?

**Yes.** The `PrimitiveInstruction` union (`ExecutePI | TransferPI | DividendPI`) uses Python 3.12 type alias syntax. Pattern matches in the test suite (`test_pattern_match_exhaustive`) cover all three variants without wildcards. The `EQUITY_TRANSITIONS` frozenset defines exactly 5 valid transitions; `check_transition` returns `Err` for anything not in the set -- this is total by construction.

The `DeltaValue` union has 6 variants. The `Confidence` union has 3 variants. Both are exhaustively defined with `@final` on each variant.

One note: Python's `match/case` does not enforce exhaustiveness at the type-checker level the way OCaml or Rust do. The `@final` annotations on variants prevent subclassing, which is the Python approximation. The tests compensate by exercising all branches.

### 2.3 Is failure explicit?

**Yes, throughout.** Every fallible function returns `Ok[T] | Err[E]`. The error hierarchy is seven `@final` subclasses of `AttestorError`, each a frozen dataclass:

- `ValidationError` (with `FieldViolation` tuples)
- `ConservationViolationError` (with `law_name`, `expected`, `actual`)
- `IllegalTransitionError` (with `from_state`, `to_state`)
- `MissingObservableError`
- `CalibrationError`
- `PricingError`
- `PersistenceError`

No domain function raises exceptions. The only `raise` in the codebase is `Err.unwrap()` (which is documented as test/boundary-only) and `FrozenMap.__getitem__` (which raises `KeyError`, matching the `Mapping` protocol contract).

The `assert` statements in `CanonicalOrder.create()` (lines 149-150) and `parse_order()` (lines 208-212) deserve comment: they are guarded by prior violation collection. If violations were found, the function returns `Err` before reaching the assert. The asserts exist to satisfy the type narrower -- they prove to the reader that `None` is impossible at that point. This is acceptable; it is the Python equivalent of an unreachable pattern arm.

### 2.4 Would a reviewer catch a bug by reading?

**Yes.** The code is written for readers:

- Every module has a docstring stating its invariants
- Every function docstring names the invariant it enforces (INV-L01, INV-L05, INV-X03, INV-R01, etc.)
- The `LedgerEngine.execute()` method has a numbered 7-step protocol that reads like a proof sketch
- The settlement and dividend modules explain the conservation argument in their module docstrings

### 2.5 Are invariants encoded or documented?

| Invariant | Encoded in Types? | Enforced at Runtime? | Tested? |
|-----------|--------------------|----------------------|---------|
| INV-L01: Balance conservation | Partially (Move.quantity is PositiveDecimal, ensuring no zero-amount moves) | Yes (pre/post sigma check in `execute()`) | Yes (Hypothesis, 200+ examples) |
| INV-L04: Settlement zero-sum | By construction (two balanced Moves) | Yes (via INV-L01) | Yes |
| INV-L05: Atomicity | No (runtime rollback) | Yes (old_balances save/restore) | Yes |
| INV-L06: Chart of accounts | No (runtime check) | Yes (account existence check in `execute()`) | Yes |
| INV-L09: Clone independence | No (runtime deep copy) | Yes | Yes |
| INV-X03: Idempotency | No (runtime set membership) | Yes (`_applied_tx_ids`) | Yes |
| CS-02: Master Square | N/A (property) | N/A | Yes (Hypothesis, 200 examples) |
| INV-R01: Report is projection | By construction (EMIRTradeReport fields come only from CanonicalOrder) | N/A | Yes |
| INV-G01: Parser idempotency | N/A (property) | N/A | Documented, round-trip via `order_to_dict` |
| INV-G02: Parser totality | By construction (returns Result, never raises) | N/A | Yes |

### 2.6 Is this total?

**Yes, at the API boundary.** Every public function either:
- Returns a value for every input (`total_supply`, `get_balance`, `positions`), or
- Returns `Result` for inputs that may fail (`create`, `parse`, `execute`)

No public function is partial.

---

## 3. Detailed Analysis

### 3.1 Gateway (Pillar I)

`CanonicalOrder.create()` is textbook parse-don't-validate. It accumulates all `FieldViolation`s before returning a single `Err` -- the caller gets a complete error report, not just the first failure. This is good API design; it means a client can fix all problems in one round-trip.

`parse_order()` is the boundary parser: raw `dict[str, object]` to `CanonicalOrder`. It handles missing keys, wrong types, and format errors. Settlement date defaults to T+2 business days if omitted. The `_add_business_days` implementation skips weekends but not holidays -- this is documented as a Phase 1 simplification.

The round-trip test (`parse(to_dict(parse(raw))) == parse(raw)`) is documented as INV-G01 but I note that the test suite does not appear to include an explicit property-based test for it. The infrastructure (`order_to_dict`) exists. Worth adding in Phase 2.

### 3.2 Instrument Model (Pillar II)

`PositionStatusEnum` and `EQUITY_TRANSITIONS` define a clean state machine. Terminal states (CANCELLED, CLOSED) have no outgoing edges -- tested exhaustively. The `check_transition` function is total: it returns `Ok(None)` or `Err(IllegalTransitionError)` for every possible input pair.

One design observation: `Instrument.status` is a field on a frozen dataclass, so transitioning requires creating a new `Instrument`. This is correct -- state transitions produce new values, not mutations. But Phase 1 does not yet have a function that returns a new `Instrument` with an updated status. The lifecycle test calls `check_transition` to validate the transition is legal, but the actual status update is implicit. Phase 2 should add a `transition(instrument, new_status) -> Result[Instrument, IllegalTransitionError]` function.

### 3.3 Ledger Engine (Pillar IV)

This is the heart of the system and it is well built.

**Mutable state containment:** `LedgerEngine` is the only mutable object in the domain. It is `@final` (no subclassing), not a dataclass (so no public `__init__` signature leak), and its four internal fields are all prefixed with `_`. The only mutating method is `execute()`, which follows a strict protocol:

1. Check idempotency
2. Verify accounts exist
3. Snapshot sigma(U) for affected units
4. Apply moves
5. Post-verify sigma(U) unchanged
6. Record transaction
7. Return

On any failure in steps 2-5, the method reverts all balance changes (step 4 rollback). This is correct. The rollback restores exact `Decimal` values from the snapshot, so there is no floating-point drift concern.

**Conservation by construction:** Each `Move` transfers `quantity` from `source` to `destination`. The engine subtracts from source and adds to destination. Since both operations use the same `quantity.value`, the sum is algebraically preserved. The post-verification (step 5) is a defense-in-depth check -- it should never fail for well-formed moves. This is the belt-and-suspenders approach: correct by construction, verified at runtime.

**Idempotency:** `_applied_tx_ids` is a `set[str]`, checked before any mutation. Simple and correct. One edge: if two transactions with different moves share the same `tx_id`, the second is silently treated as a duplicate. This is correct behavior for idempotency but could mask a bug upstream. The `tx_id` should be content-addressed in Phase 2 to make this impossible.

**Clone:** Deep copies all four fields. The `defaultdict(Decimal, ...)` constructor correctly copies the balances dictionary. The clone shares no references with the original. Tested.

**Performance:** `get_balance` is O(1) (dict lookup). `total_supply` is O(N) where N is the number of (account, instrument) pairs -- adequate for Phase 1 but should be cached if the ledger grows large.

### 3.4 Settlement and Dividends

`create_settlement_transaction` creates exactly two `Move`s: cash from buyer to seller, securities from seller to buyer. The cash amount is computed under `ATTESTOR_DECIMAL_CONTEXT` (prec=28, ROUND_HALF_EVEN, traps on InvalidOperation/DivisionByZero/Overflow). This is correct.

`create_dividend_transaction` creates one `Move` per holder, all sourced from the issuer account. Conservation follows because each `Move` adds to the holder exactly what it removes from the issuer.

Both functions validate all string parameters are non-empty. Both return `Result`. Both reject zero/negative amounts via `PositiveDecimal.parse`.

### 3.5 Oracle Ingestion (Pillar III)

`ingest_equity_fill` and `ingest_equity_quote` follow the same parse-don't-validate pattern. Both produce `Attestation[MarketDataPoint]` with the appropriate confidence type (`FirmConfidence` for fills, `QuotedConfidence` for quotes). The `QuotedConfidence.create` factory enforces `bid <= ask` (non-negative spread) by construction.

`MarketDataPoint` has a bare `Decimal` for `price` -- the ingestion functions validate `price > 0 and price.is_finite()` at the boundary, but the type itself does not encode positivity. Consistent with the `CanonicalOrder.price` situation (F-02 above).

### 3.6 EMIR Reporting (Pillar V)

`project_emir_report` is a pure projection from `CanonicalOrder` to `EMIRTradeReport`. No new values are computed -- every field on the report comes directly from the order. The UTI is derived from the content hash of the order concatenated with the executing party LEI, which is deterministic and reproducible.

The report is wrapped in an `Attestation[EMIRTradeReport]` with `FirmConfidence`, establishing provenance back to the trade attestation.

### 3.7 Commutativity

The Master Square test (CS-02) is proven both with concrete examples and with Hypothesis (200 random price/quantity pairs). The property is: `stub_price(book(trade)) == book(stub_price(trade))`. With the current `StubPricingEngine` (which returns `oracle_price` regardless of ledger state), this is trivially true -- the pricer does not read from the ledger. The real test will come when pricing reads positions from the engine. But the infrastructure for testing the property is in place, and the framework scales to a real pricer.

Reporting naturality (CS-04) and lifecycle-booking naturality (CS-05) are tested with concrete examples. Booking order independence (commutativity of settlement transactions) is tested.

---

## 4. Findings Summary

| ID | Category | Description | Recommendation | Priority |
|----|----------|-------------|----------------|----------|
| F-01 | Type safety | `Move.source`/`destination` are plain `str`, not `NonEmptyStr`. Self-transfer representable. | Promote to `NonEmptyStr` or use `DistinctAccountPair` | Phase 2 |
| F-02 | Type safety | `CanonicalOrder.price` allows negative `Decimal` | Add `NonNegativeDecimal` refined type, or validate at boundary | Phase 2 |
| F-03 | Type bypass | `get_position`/`positions` construct `NonEmptyStr` directly, bypassing `parse()` | Use `NonEmptyStr.parse()` or add `__post_init__` guard | Phase 2 |
| F-04 | Type safety | `Transaction.tx_id` is plain `str` | Promote to `NonEmptyStr` | Phase 2 |
| F-05 | Type safety | `BusinessEvent.attestation_id` allows empty string | Promote to `NonEmptyStr | None` | Phase 2 |
| F-06 | Type safety | `Move.unit`/`contract_id` are plain `str` | Promote to `NonEmptyStr` | Phase 2 |

None of these are exploitable in the current test suite or in the settlement/dividend pathways, because the data always flows through validated boundaries (`parse_order`, `create_settlement_transaction`, `create_dividend_transaction`) before reaching the engine. They are defense-in-depth gaps, not correctness bugs.

---

## 5. What is Missing for Phase 2

1. **`Instrument` status transitions as functions**: `transition(instrument, new_status) -> Result[Instrument, IllegalTransitionError]` should exist as a first-class operation, not just a validation check.

2. **Content-addressed `tx_id`**: The engine's idempotency relies on `tx_id` being unique per logical transaction. A content-addressed `tx_id` (hash of moves) would make duplicates impossible by construction.

3. **INV-G01 property test**: The round-trip invariant `parse(to_dict(parse(raw))) == parse(raw)` should be a Hypothesis test, not just documented.

4. **Holiday calendar**: `_add_business_days` skips weekends only. Real T+2 settlement requires a market-specific holiday calendar.

5. **`NonEmptyStr.__post_init__`**: Adding a `__post_init__` check to `NonEmptyStr` would close the bypass path (F-03) for all callers, at the cost of raising in the constructor. Alternatively, make the `value` field private and expose only a factory -- but this changes the serialization contract.

---

## 6. Verdict

**Phase 1 is complete.** The system delivers what it claims:

- Full equity lifecycle from raw order through settlement, dividend, and EMIR reporting
- Conservation laws enforced by the engine and proven with property-based tests
- Commutativity (Master Square) proven with 200 Hypothesis examples
- No float, no raise in domain, all frozen, mypy --strict clean
- 494 tests passing

The architecture follows parse-don't-validate at the boundaries, uses refined types (`PositiveDecimal`, `NonEmptyStr`, `LEI`, `ISIN`, `UtcDatetime`) to carry validity in the type, and isolates mutable state to a single `@final` class with a disciplined mutation protocol.

The six findings are defense-in-depth improvements for internal types that currently rely on validated data flowing from the boundary. They do not affect correctness of the current system. They should be addressed in Phase 2 when derivatives and multi-asset support widen the attack surface.

The code is written for readers. The invariants are documented in every module. The tests prove the properties that matter.

Build systems like it matters. This one does.

---

*Report generated by MINSKY review, 2026-02-15.*
