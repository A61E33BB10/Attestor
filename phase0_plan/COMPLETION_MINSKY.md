# Phase 0 Completion Report -- Minsky Review

**Reviewer:** Yaron Minsky (type safety, illegal state prevention)
**Date:** 2026-02-15
**Verdict:** READY FOR PHASE 1

---

## 1. Illegal States Made Unrepresentable

The foundational types are well-constructed. `DistinctAccountPair` (transactions.py:116) enforces `debit != credit` at construction via a `create()` smart constructor returning `Ok | Err` -- you literally cannot hold a self-transfer. `PositiveDecimal` (money.py:40) and `NonZeroDecimal` (money.py:56) make it impossible to represent a `Move` with zero or negative quantity, since `Move.quantity` is typed as `PositiveDecimal`, not `Decimal`. `NonEmptyStr` (money.py:72) eliminates the entire class of empty-identifier bugs. These are not validation checks -- they are parse-don't-validate types that carry their validity proof in their structure.

The `DeltaValue` sum type (transactions.py:59) is a proper tagged union of six variants. No `Any`, no stringly-typed dispatch. Pattern matching on it is exhaustive by construction.

`Confidence` (attestation.py:176) as `FirmConfidence | QuotedConfidence | DerivedConfidence` is the right design: each variant carries structurally distinct data, and `QuotedConfidence.create()` enforces `bid <= ask` at line 95, making negative spreads unrepresentable.

## 2. Explicit Failure Modes

`Result[T, E] = Ok[T] | Err[E]` (result.py:81) is used pervasively. Every domain smart constructor returns `Ok | Err`. The error hierarchy (errors.py) is seven `@final` frozen dataclasses -- values, not exceptions. The `"no raise in domain functions"` invariant means callers cannot forget to handle failure; the type signature forces it.

The `sequence` combinator (result.py:103) enables clean short-circuit collection. The `map`/`bind` methods on both `Ok` and `Err` maintain the monad laws. This is textbook.

## 3. Invariants Encoded in Types

- All 50+ dataclasses are `frozen=True` -- mutation is structurally impossible.
- `FrozenMap` (types.py:34) stores sorted tuples for deterministic serialization and content-addressing. No dict drift.
- `UtcDatetime` (types.py:15) rejects naive datetimes; timezone correctness is a type-level property.
- `PnLAttribution.create()` (pricing/types.py:106) computes `total_pnl` from components, making the decomposition invariant unbreakable.
- `Money.div()` takes `NonZeroDecimal`, making division by zero a type error, not a runtime trap.
- All financial arithmetic runs under `ATTESTOR_DECIMAL_CONTEXT` with traps for `InvalidOperation`, `DivisionByZero`, and `Overflow`. No silent NaN propagation.

## 4. Minor Observations

`FrozenMap.__getitem__` (types.py:71) raises `KeyError` -- one of the few places a domain type can throw. This is acceptable for `dict`-protocol compatibility, but Phase 1 should consider a `get_result()` method returning `Ok[V] | Err[str]` for domain code paths.

`Scenario.create()` (pricing/types.py:58) calls `unwrap()` internally, which can raise. This is a pragmatic shortcut for a test-oriented factory, but it violates totality. Flag for Phase 1.

## 5. Final Assessment

The type system does real work here. Invalid account pairs, non-positive amounts, empty identifiers, naive datetimes, currency mismatches -- none of these are runtime "oops" scenarios. They are compile-time (mypy --strict) or construction-time rejections. The `Result` monad eliminates exception-based control flow from the domain layer entirely.

This is a sound foundation. Phase 1 can build on it with confidence.
