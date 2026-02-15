# FORMALIS Committee -- Phase 0 Completion Review

**Date:** 2026-02-15
**Verdict:** CERTIFIED FOR PHASE 1

## 1. Content-Addressing and Attestation Immutability

The content-addressing chain is sound. `content_hash` in `core/serialization.py` computes SHA-256 over canonical bytes of the value alone, while `attestation_id` hashes the full identity payload (source, timestamp, confidence, value, provenance) in `oracle/attestation.py:222-233`. Both derive from the same `canonical_bytes` function, ensuring a single serialization path. All attestation fields live on a `frozen=True, slots=True` dataclass marked `@final` -- mutation is structurally impossible. The `InMemoryAttestationStore` is correctly keyed by `attestation_id` with idempotent `store()`.

## 2. Deterministic Serialization

`canonical_bytes` produces deterministic output through three mechanisms: `json.dumps(sort_keys=True, separators=(",",":"))` for JSON canonicalization, `sorted(f.name for f in dataclasses.fields(obj))` for dataclass field ordering with an explicit `_type` discriminator tag, and `Decimal.normalize()` with zero mapped to `"0"` (line 35-37). `FrozenMap` stores entries as a sorted tuple at construction time (`types.py:59`), so iteration order is deterministic by construction, not convention. Naive datetimes are rejected at both the `UtcDatetime.parse` boundary and inside `_to_serializable` (line 42-44).

## 3. Result Types and Exception Discipline

`Ok[T] | Err[E]` is used uniformly across all domain functions. `canonical_bytes` catches the internal `TypeError` from `_to_serializable` and returns `Err` (line 74-75). Validation constructors (`LEI.parse`, `Money.create`, `QuotedConfidence.create`, `DerivedConfidence.create`) all return `Ok | Err` without raising. Infrastructure protocols (`AttestationStore`, `TransactionLog`, `StateStore`, `EventBus`) return `Ok[T] | Err[PersistenceError]`. The error hierarchy in `core/errors.py` consists of frozen dataclasses, not exception classes -- errors are values.

## 4. Soundness for Phase 1

The foundation is compositionally correct. Types encode invariants: `DistinctAccountPair` enforces debit != credit at construction, `PositiveDecimal` enforces > 0, `NonEmptyStr` rejects empty strings, `QuotedConfidence` enforces bid <= ask. `PnLAttribution.create` computes `total` from components, making the conservation law `total == market + carry + trade + residual` unbreakable by construction (`pricing/types.py:112-113`). Infrastructure is cleanly separated behind protocols with in-memory test doubles. `Money` arithmetic uses `localcontext(ATTESTOR_DECIMAL_CONTEXT)` consistently, preventing global decimal context contamination.

## 5. Noted Observations (MEDIUM)

`Scenario.create` (`pricing/types.py:59`) calls `unwrap` on `FrozenMap.create`, which will raise on non-comparable keys rather than returning `Err`. This is acceptable for Phase 0 given it is a convenience constructor for tests, but Phase 1 should convert it to return `Result`.

---

*Leroy (Chair):* The serialization path from domain object to SHA-256 digest is a single, auditable pipeline. Correctness of content-addressing follows by inspection. Certified.
