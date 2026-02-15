# Phase 0 --- Pass 4: Final Review, Build Sequence, and Sign-Off

**Date:** 2026-02-15
**Input:** PHASE0_EXECUTION.md (Pass 1), PASS2_REVIEW.md (Pass 2), PASS3_REVIEW.md (Pass 3), PLAN.md
**Output:** Final consolidated specification with actionable build sequence

**Actionability Test:** Can a developer follow the build sequence (Section 6), implement each step, run the specified test, and have a fully working Phase 0 at the end --- without asking anyone a question?

---

## 1. Mathematical Foundations [Henri Cartan]

### 1.1 Attestation Algebra

An **Attestation** is a 6-tuple `A = (v, c, s, t, p, h)` where:

- `v ∈ V` --- the attested value (generic over type `T`)
- `c ∈ C = Firm ⊔ Quoted ⊔ Derived` --- epistemic confidence (disjoint union)
- `s ∈ S` --- source identifier (non-empty string)
- `t ∈ T_UTC` --- timestamp (timezone-aware UTC datetime)
- `p ∈ ℙ(H)` --- provenance (finite tuple of attestation identity hashes)
- `h ∈ H` --- content hash, `h = SHA256(canonical(v))`

The **attestation identity** is defined as:

```
attestation_id(A) = SHA256(canonical(s, t, c, v, p))
```

Two attestations are **distinct** iff their attestation identities differ. Two attestations may share the same `content_hash` (same value, different source/time/confidence).

**Axiom A1 (Immutability):** Once constructed, no field of `A` may be modified. Enforced by `frozen=True`.

**Axiom A2 (Determinism):** `canonical` is a total function over the type universe `V`. For all `x, y ∈ V`: `x = y ⟹ canonical(x) = canonical(y)`.

**Axiom A3 (Content Addressing):** `attestation_id` is injective over distinct attestation tuples (collision-free under SHA-256).

### 1.2 Hashing Contract

The canonical serialization function `canonical: V → bytes` satisfies:

1. **Totality:** `canonical` is defined for every element of `V`. It returns `Result[bytes, str]` --- never raises.
2. **Determinism:** `canonical(x) = canonical(x)` for all `x ∈ V`, regardless of process, thread, or platform.
3. **Canonical Form:** For `Decimal`: `normalize()` then special-case zero to `"0"`. For `datetime`: UTC ISO 8601. For `FrozenMap`: sorted by key. For dataclasses: sorted fields with `_type` discriminator.
4. **Injectivity (semantic):** `canonical(x) = canonical(y) ⟹ x ≅ y` (semantically equal).

### 1.3 Bitemporal Ordering

Every persistent record carries two temporal axes:

- `valid_time` (`event_time`): when the event occurred in the real world
- `system_time` (`knowledge_time`): when the system learned about it

**Axiom T1 (Monotonicity):** `system_time` is monotonically non-decreasing within any single writer.

**Axiom T2 (UTC):** All temporal values are timezone-aware UTC. The `UtcDatetime` refined type enforces this at construction.

### 1.4 Money Module

The `Money` type forms a module over the ring `(ℤ[1/10^28], +, ×)`:

- `(Money_c, +)` is an abelian group for each currency `c` (commutativity, associativity, identity `0_c`, inverse via `negate`)
- Scalar multiplication by `Decimal` distributes over addition: `k · (m₁ + m₂) = k·m₁ + k·m₂`
- Cross-currency operations are undefined (return `Err`)

All arithmetic executes within `ATTESTOR_DECIMAL_CONTEXT` (prec=28, ROUND_HALF_EVEN).

---

## 2. Notation Standard [Halmos]

### 2.1 Type Naming Conventions

| Category | Convention | Example |
|----------|-----------|---------|
| Domain types | `PascalCase`, `@final @dataclass(frozen=True, slots=True)` | `Money`, `Attestation`, `LedgerEntry` |
| Refined types | `PascalCase`, factory returns `Result` | `PositiveDecimal`, `NonEmptyStr`, `UtcDatetime` |
| Sum types | Union of `@final` variants | `Confidence = FirmConfidence \| QuotedConfidence \| DerivedConfidence` |
| Protocols | `PascalCase`, `Protocol` suffix implied | `PricingEngine`, `AttestationStore` |
| Constants | `UPPER_SNAKE_CASE` | `ATTESTOR_DECIMAL_CONTEXT`, `PHASE0_TOPICS` |
| Factory methods | `create()` or `parse()`, returns `Result[T, str]` | `Money.create()`, `ISIN.parse()` |
| Modules | `snake_case.py` | `result.py`, `memory_adapter.py` |
| Test files | `test_<module>.py` | `test_money.py`, `test_attestation.py` |
| Test functions | `test_<subject>_<behaviour>` | `test_money_add_commutativity_property` |

### 2.2 Math-to-Code Mapping

| Mathematical Concept | Code Representation |
|---------------------|---------------------|
| `A = (v, c, s, t, p, h)` | `Attestation[T]` frozen dataclass |
| `C = Firm ⊔ Quoted ⊔ Derived` | `Confidence` type alias (union) |
| `canonical: V → bytes` | `canonical_bytes(obj) -> Result[bytes, str]` |
| `SHA256(·)` | `content_hash(obj) -> Result[str, str]` |
| `Result[T, E]` monad | `Ok[T] \| Err[E]` with `.map`, `.bind`, `.unwrap_or`, `.map_err` |
| `ℝ₊` (positive reals) | `PositiveDecimal` |
| `ℝ \ {0}` (nonzero reals) | `NonZeroDecimal` |
| `T_UTC` (UTC timestamps) | `UtcDatetime` |
| Immutable mapping `K → V` | `FrozenMap[K, V]` |

### 2.3 Docstring Format

```python
def function_name(param: Type) -> Result[ReturnType, ErrorType]:
    """One-line summary.

    Detailed explanation if non-obvious.

    Invariants preserved: INV-xxx, INV-yyy.
    """
```

No docstrings on self-evident types. No docstrings added to code you didn't write.

---

## 3. Conservation Laws [Noether]

### 3.1 Phase 0 Conservation Law Table

| Law | Symmetry | Formal Statement | Enforced By | Test |
|-----|----------|-----------------|-------------|------|
| **Balance Conservation** | Translation invariance of accounting entries | `∀ tx ∈ Transaction: Σ debits = Σ credits` | `DistinctAccountPair` (debit ≠ credit by construction); `PositiveDecimal` (quantity > 0); `Move` carries single quantity applied to both sides | `test_ledger_entry_accounts_always_distinct_property` |
| **Attestation Immutability** | Time-translation symmetry of recorded facts | `∀ a ∈ Attestation: a(t₁) = a(t₂)` for all system times t₁, t₂ | `frozen=True` on all domain types; append-only Postgres triggers; Kafka append-only logs | `test_inv_o01_attestation_immutability_property` |
| **Content Address Stability** | Permutation invariance of construction order | `canonical(x) = canonical(x)` regardless of dict insertion order | `FrozenMap` sorted entries; `json.dumps(sort_keys=True)` | `test_frozen_map_insertion_order_irrelevant` |
| **Decimal Context Conservation** | Invariance of arithmetic environment | `ATTESTOR_DECIMAL_CONTEXT` unchanged before and after any operation | `with localcontext(ATTESTOR_DECIMAL_CONTEXT)` in all Money operations | `test_decimal_context_not_mutated_between_operations` |
| **Provenance Chain Closure** | Graph closure of derivation DAG | `∀ h ∈ a.provenance: ∃ a' ∈ Store : a'.attestation_id = h` | Integration test; `create_derived_attestation` requires non-empty provenance | `test_full_provenance_chain_walkable` |
| **Idempotency** | Invariance under repeated application | `store(a); store(a) ≡ store(a)` --- same key, no duplicate | Content-addressed keys; `ON CONFLICT DO NOTHING` in Postgres | `test_attestation_store_idempotent_property` |
| **P&L Decomposition** | Additivity of attribution components | `total_pnl = market_pnl + carry_pnl + trade_pnl + residual_pnl` | `PnLAttribution.create()` factory computes total from components | `test_pnl_attribution_decomposition_property` |

### 3.2 Broken Symmetry Detection

If any of the following conditions are observed, a conservation law is broken:

| Symptom | Broken Law | Root Cause | Detection |
|---------|-----------|------------|-----------|
| Same value, different hash across processes | Content Address Stability | Naive datetime, non-canonical Decimal zero, unsorted keys | `test_canonical_bytes_deterministic_property` |
| Attestation store count grows on duplicate insert | Idempotency | Using `content_hash` as key instead of `attestation_id` | `test_attestation_store_store_idempotent` |
| Money arithmetic differs across threads | Decimal Context Conservation | Missing `with localcontext(...)` | `test_money_add_commutativity_property` |
| P&L residual grows without bound | P&L Decomposition | `total_pnl` not computed from components | `test_pnl_attribution_decomposition_sums_to_total` |

---

## 4. Unification Audit [Dirac]

### 4.1 Is the `Confidence` sum type minimal?

**Yes.** The three variants (`Firm`, `Quoted`, `Derived`) correspond to a fundamental epistemic partition: observed fact, bounded estimate, model output. No variant can be derived from the others. No two variants share the same information content. The `@final` annotation on each variant prevents subclassing, and the union type `Confidence = FirmConfidence | QuotedConfidence | DerivedConfidence` is exhaustive under mypy `assert_never`. Removing any variant would lose a distinct class of financial data.

### 4.2 Can the 6 `DeltaValue` variants be unified?

**No, but they can be parameterized.** The 6 variants (`DeltaDecimal`, `DeltaStr`, `DeltaBool`, `DeltaDate`, `DeltaDatetime`, `DeltaNull`) are the minimal type-safe representation of state changes across the ledger. Each variant carries a value of its specific type. A generic `DeltaValue[T]` would require `T` to be bounded, and Python's type system cannot express `T ∈ {Decimal, str, bool, date, datetime, NoneType}` as a type parameter. The 6-variant union is the Pythonic equivalent. Pattern matching is exhaustive. No simplification possible.

### 4.3 Is the `Result[T, E]` type carrying unnecessary weight?

**After Pass 3 additions, it is correctly minimal.** The full API (`.map`, `.bind`/`.and_then`, `.unwrap_or`, `.map_err` as methods; `sequence` as a free function) is the minimal set for monadic composition. `unwrap` is retained for test boundaries. `map_result` becomes redundant once `.map()` exists as a method --- it should be retained as a backward-compatible alias but marked as deprecated-by-convention. The type is two variants (`Ok`, `Err`), both `@final`, both `frozen=True`. No further simplification possible without losing essential composition patterns.

---

## 5. Dual-Path Verification [Feynman]

Every critical computation in Phase 0 must be verifiable by at least two independent paths.

| Operation | Path A | Path B | Agreement Test |
|-----------|--------|--------|---------------|
| Content hash | `content_hash(x)` via `canonical_bytes` → SHA-256 | Independent `hashlib.sha256(json.dumps(...).encode())` with manually sorted keys | `test_inv_r05_content_addressing` |
| Money addition | `m1.add(m2)` | `Money.create(m1.amount + m2.amount, m1.currency)` under `localcontext` | `test_money_add_commutativity_property` |
| FrozenMap canonical form | `FrozenMap.create(d1)` from dict `{"b":2,"a":1}` | `FrozenMap.create(d2)` from dict `{"a":1,"b":2}` | `test_frozen_map_insertion_order_irrelevant` |
| ISIN Luhn check | `ISIN.parse(code)` | Manual Luhn computation on character-to-digit expansion | `test_isin_valid_apple`, `test_isin_valid_microsoft` |
| Attestation identity | `attestation_id` computed via `canonical_bytes(source, timestamp, confidence, value, provenance)` | Independent construction from fields → same hash | `test_attestation_content_hash_stability_across_store_retrieve` |
| PnL decomposition | `total_pnl` from `PnLAttribution.create(market, carry, trade, residual)` | Manual sum `market + carry + trade + residual` | `test_pnl_attribution_decomposition_sums_to_total` |
| `derive_seed` order independence | `derive_seed(("b","a"), v)` | `derive_seed(("a","b"), v)` | `test_derive_seed_sorts_refs` |
| Decimal zero normalization | `canonical_bytes(Decimal("0"))` | `canonical_bytes(Decimal("0E+2"))` | Same output (both → `"0"`) |
| Stub determinism | `stub.price(x, y, z)` called 100 times | All outputs identical | `test_stub_pricing_engine_deterministic_across_100_calls` |

---

## 6. Build Sequence [Karpathy]

**This is the authoritative build specification.** It supersedes PHASE0_EXECUTION.md Steps 1-18 by incorporating all 41 gaps from Passes 2-3. Every gap resolution is marked with its GAP-ID.

**Scope:** 15 ordered, testable steps. ~2,100 production lines + ~1,200 test lines across 16 Python modules, 3 SQL files, 1 YAML file.

**Directory structure at completion:**

```
attestor/
    __init__.py
    core/
        __init__.py
        result.py           # Step 2: Result[T,E] with full monad API
        types.py             # Step 3: UtcDatetime, FrozenMap, BitemporalEnvelope, ...
        money.py             # Step 4: Money, ATTESTOR_DECIMAL_CONTEXT, refined types
        errors.py            # Step 5: Error hierarchy with .with_context()
        serialization.py     # Step 6: canonical_bytes -> Result[bytes, str]
        identifiers.py       # Step 7: LEI, UTI, ISIN
    oracle/
        __init__.py
        attestation.py       # Step 9: Attestation[T], Confidence, attestation_id
    ledger/
        __init__.py
        transactions.py      # Step 10: Move, Transaction, LedgerEntry, Account, Position
    pricing/
        __init__.py
        types.py             # Step 11: ValuationResult, Greeks, VaRResult (with CVaR), ...
        protocols.py         # Step 12: PricingEngine, RiskEngine (provisional + complete)
    infra/
        __init__.py
        protocols.py         # Step 13: AttestationStore, EventBus, TransactionLog, StateStore
        memory_adapter.py    # Step 13: In-memory test doubles
        config.py            # Step 13: Topic configs, KafkaProducerConfig, PostgresPoolConfig
        health.py            # Step 13: HealthCheckable, liveness, readiness
tests/
    __init__.py
    conftest.py              # Step 14: Hypothesis strategies for all types
    test_result.py
    test_types.py
    test_money.py
    test_errors.py
    test_serialization.py
    test_identifiers.py
    test_attestation.py
    test_transactions.py
    test_pricing_types.py
    test_pricing_protocols.py
    test_infra.py
    test_memory_adapter.py
    test_integration_attestation_store.py
    test_determinism.py
    test_invariants.py
sql/
    001_attestations.sql
    002_event_log.sql
    003_schema_registry.sql
.github/
    workflows/
        ci.yml
pyproject.toml
```

---

### Step 1: Project Scaffold (~30 lines)

**Prerequisites:** Python 3.12+, virtualenv with `pytest`, `mypy`, `ruff`, `hypothesis`.

**Files:** `pyproject.toml`, `attestor/__init__.py`, `attestor/core/__init__.py`, `tests/__init__.py`

**What to code:**

`pyproject.toml` --- identical to PHASE0_EXECUTION.md Step 1. Strict mypy, ruff with `["E","F","W","I","N","UP","B","A","SIM"]`, pytest with `-x --tb=short`, coverage >= 90.

Empty `__init__.py` files. `attestor/__init__.py` contains `__version__ = "0.1.0"`.

**Verify:**

```bash
mypy --strict attestor/ && ruff check attestor/ tests/ && pytest tests/
```

**Done when:** All three exit 0. mypy: 0 errors. ruff: 0 violations. pytest: 0 items collected.

---

### Step 2: Result[T, E] with Full Monad API (~100 lines)

**Prerequisites:** Step 1.
**File:** `attestor/core/result.py`
**Resolves:** GAP-21 (.map), GAP-22 (.bind/.and_then), GAP-23 (.unwrap_or), GAP-24 (.map_err), GAP-25 (sequence), GAP-15 (map_result retained as alias)

**What to code:**

Two `@final` frozen dataclasses and a type alias:

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar, final, Iterable

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E")
F = TypeVar("F")

@final
@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    value: T

    def map(self, f: Callable[[T], U]) -> Ok[U]:
        return Ok(f(self.value))

    def bind(self, f: Callable[[T], Result[U, E]]) -> Result[U, E]:
        return f(self.value)

    and_then = bind  # Rust-familiar alias

    def unwrap(self) -> T:
        return self.value

    def unwrap_or(self, default: T) -> T:
        return self.value

    def map_err(self, f: Callable[[object], object]) -> Ok[T]:
        return self


@final
@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
    error: E

    def map(self, f: Callable[[object], object]) -> Err[E]:
        return self

    def bind(self, f: Callable[[object], object]) -> Err[E]:
        return self

    and_then = bind

    def unwrap(self) -> object:
        raise RuntimeError(f"Called unwrap on Err: {self.error}")

    def unwrap_or(self, default: T) -> T:
        return default

    def map_err(self, f: Callable[[E], F]) -> Err[F]:
        return Err(f(self.error))


Result = Ok[T] | Err[E]


# --- Free functions ---

def unwrap(result: Result[T, E]) -> T:
    """Extract Ok value or raise. Test/boundary code only."""
    match result:
        case Ok(v): return v
        case Err(e): raise RuntimeError(f"unwrap on Err: {e}")


def map_result(result: Result[T, E], f: Callable[[T], U]) -> Result[U, E]:
    """Alias for result.map(f). Retained for backward compatibility."""
    return result.map(f)


def sequence(results: Iterable[Result[T, E]]) -> Result[list[T], E]:
    """Collect Results into a Result of list. Short-circuits on first Err."""
    values: list[T] = []
    for r in results:
        match r:
            case Ok(v): values.append(v)
            case Err(_): return r
    return Ok(values)
```

**Test file:** `tests/test_result.py`

**Tests (17 tests: 13 Unit, 2 Property, 2 for new methods):**

```python
# Core (from Pass 1):
# test_ok_holds_value, test_err_holds_error
# test_ok_is_frozen, test_err_is_frozen
# test_pattern_match_ok, test_pattern_match_err
# test_unwrap_ok, test_unwrap_err_raises
# test_result_type_alias_ok_is_not_err
# test_ok_equality, test_err_equality

# .map() (GAP-21):
# test_ok_map_applies_function -- Ok(5).map(lambda x: x*2) == Ok(10)
# test_err_map_passthrough -- Err("e").map(lambda x: x*2) == Err("e")

# .bind() (GAP-22):
# test_ok_bind_returns_ok -- Ok(5).bind(lambda x: Ok(x*2)) == Ok(10)
# test_ok_bind_returns_err -- Ok(5).bind(lambda x: Err("fail")) == Err("fail")
# test_err_bind_passthrough -- Err("e").bind(lambda x: Ok(x*2)) == Err("e")

# .unwrap_or() (GAP-23):
# test_ok_unwrap_or_returns_value -- Ok(42).unwrap_or(0) == 42
# test_err_unwrap_or_returns_default -- Err("e").unwrap_or(0) == 0

# .map_err() (GAP-24):
# test_ok_map_err_passthrough -- Ok(42).map_err(str.upper) == Ok(42)
# test_err_map_err_transforms -- Err("e").map_err(str.upper) == Err("E")

# sequence() (GAP-25):
# test_sequence_all_ok -- sequence([Ok(1), Ok(2), Ok(3)]) == Ok([1,2,3])
# test_sequence_first_err -- sequence([Ok(1), Err("e"), Ok(3)]) == Err("e")
# test_sequence_empty -- sequence([]) == Ok([])

# Properties:
# test_map_identity_law -- result.map(lambda x: x) == result
# test_map_composition_law -- result.map(f).map(g) == result.map(lambda x: g(f(x)))
# test_bind_left_identity -- Ok(x).bind(f) == f(x)
```

```bash
pytest -x tests/test_result.py && mypy --strict attestor/core/result.py
```

**Done when:** 25+ tests pass. `.map()`, `.bind()`, `.unwrap_or()`, `.map_err()` work on both Ok and Err. `sequence` short-circuits. mypy strict passes.

---

### Step 3: UtcDatetime, FrozenMap, BitemporalEnvelope (~150 lines)

**Prerequisites:** Step 2 (Result).
**File:** `attestor/core/types.py`
**Resolves:** GAP-03 (UtcDatetime), GAP-08 (FrozenMap.create totality), GAP-10 (duplicate key dedup)

**What to code:**

**UtcDatetime** (GAP-03 --- new refined type):
```python
@final
@dataclass(frozen=True, slots=True)
class UtcDatetime:
    """Timezone-aware UTC datetime. Naive datetimes are rejected."""
    value: datetime

    @staticmethod
    def parse(raw: datetime) -> Result[UtcDatetime, str]:
        if raw.tzinfo is None:
            return Err("UtcDatetime requires timezone-aware datetime, got naive")
        return Ok(UtcDatetime(value=raw.astimezone(timezone.utc)))

    @staticmethod
    def now() -> UtcDatetime:
        return UtcDatetime(value=datetime.now(tz=timezone.utc))
```

Replace bare `datetime` with `UtcDatetime` in all temporal fields throughout Phase 0:
- `BitemporalEnvelope.event_time`, `.knowledge_time`
- `EventTime.value`
- `Attestation.timestamp`
- `FirmConfidence.timestamp`
- `Transaction.timestamp`
- `LedgerEntry.timestamp`
- `AttestorError.timestamp`

**FrozenMap[K, V]** (GAP-08: totality, GAP-10: duplicate dedup):

`FrozenMap.create` must handle:
1. Duplicate keys from Iterable input: last value wins (like `dict()` constructor), then sort
2. Non-comparable keys: return `Result[FrozenMap, str]` wrapping a try/except on `sorted()`

```python
@staticmethod
def create(items: dict[K, V] | Iterable[tuple[K, V]]) -> Result[FrozenMap[K, V], str]:
    if isinstance(items, dict):
        d = items
    else:
        d = dict(items)  # deduplicates: last value wins (GAP-10)
    try:
        entries = tuple(sorted(d.items(), key=lambda kv: kv[0]))
    except TypeError as e:
        return Err(f"FrozenMap keys must be comparable: {e}")
    return Ok(FrozenMap(_entries=entries))
```

Note: `FrozenMap.EMPTY` changes to `FrozenMap(_entries=())` --- constructed directly, not via factory.

**BitemporalEnvelope[T]:** Now uses `UtcDatetime` for both temporal fields.

**IdempotencyKey:** Factory returns `Result[IdempotencyKey, str]`.

**EventTime:** Now wraps `UtcDatetime` instead of bare `datetime`.

**Test file:** `tests/test_types.py`

**Tests (30 tests: 24 Unit, 6 Property):**

All original tests from PHASE0_EXECUTION.md Step 3, plus:

```python
# UtcDatetime (GAP-03):
# test_utc_datetime_parse_aware_ok -- aware datetime -> Ok
# test_utc_datetime_parse_naive_err -- naive datetime -> Err
# test_utc_datetime_converts_to_utc -- EST input stored as UTC
# test_utc_datetime_now_is_aware -- UtcDatetime.now().value.tzinfo is not None
# test_utc_datetime_frozen

# FrozenMap (GAP-08, GAP-10):
# test_frozen_map_create_returns_result -- isinstance(result, Ok)
# test_frozen_map_create_deduplicates_keys -- [("a",1),("a",2)] -> {"a": 2}
# test_frozen_map_create_non_comparable_keys_err -- complex keys -> Err
```

```bash
pytest -x tests/test_types.py && mypy --strict attestor/core/types.py
```

**Done when:** All tests pass. UtcDatetime rejects naive datetimes. FrozenMap.create returns `Result` and deduplicates keys. mypy strict passes.

---

### Step 4: Money and Decimal Context (~160 lines)

**Prerequisites:** Step 2 (Result), Step 3 (UtcDatetime).
**File:** `attestor/core/money.py`
**Resolves:** GAP-02 (localcontext), GAP-26 (NaN/Inf rejection), GAP-27 (div), GAP-28 (round_to_minor_unit)

**What to code:**

**ATTESTOR_DECIMAL_CONTEXT** --- identical to Pass 1.

**Refined types:** `PositiveDecimal`, `NonZeroDecimal`, `NonEmptyStr` --- identical to Pass 1.

**Money** --- revised:

```python
@final
@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: NonEmptyStr

    @staticmethod
    def create(amount: Decimal, currency: str) -> Result[Money, str]:
        if not isinstance(amount, Decimal):
            return Err(f"Money.amount must be Decimal, got {type(amount).__name__}")
        # GAP-26: reject NaN and Infinity
        if not amount.is_finite():
            return Err(f"Money.amount must be finite, got {amount}")
        match NonEmptyStr.parse(currency):
            case Err(e): return Err(f"Money.currency: {e}")
            case Ok(c): return Ok(Money(amount=amount, currency=c))

    def add(self, other: Money) -> Result[Money, str]:
        if self.currency != other.currency:
            return Err(f"Currency mismatch: {self.currency} vs {other.currency}")
        # GAP-02: use ATTESTOR_DECIMAL_CONTEXT
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            return Ok(Money(amount=self.amount + other.amount, currency=self.currency))

    def sub(self, other: Money) -> Result[Money, str]:
        if self.currency != other.currency:
            return Err(f"Currency mismatch: {self.currency} vs {other.currency}")
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            return Ok(Money(amount=self.amount - other.amount, currency=self.currency))

    def mul(self, factor: Decimal) -> Money:
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            return Money(amount=self.amount * factor, currency=self.currency)

    def negate(self) -> Money:
        return Money(amount=-self.amount, currency=self.currency)

    # GAP-27: scalar division
    def div(self, divisor: NonZeroDecimal) -> Money:
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            return Money(amount=self.amount / divisor.value, currency=self.currency)

    # GAP-28: quantize to currency minor unit
    def round_to_minor_unit(self) -> Money:
        minor_units = _ISO4217_MINOR_UNITS.get(self.currency.value, 2)
        quantizer = Decimal(10) ** -minor_units
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            rounded = self.amount.quantize(quantizer)
        return Money(amount=rounded, currency=self.currency)


# GAP-28: ISO 4217 minor unit lookup (subset for Phase 0)
_ISO4217_MINOR_UNITS: dict[str, int] = {
    "USD": 2, "EUR": 2, "GBP": 2, "CHF": 2, "CAD": 2, "AUD": 2, "SEK": 2,
    "JPY": 0, "KRW": 0,
    "BHD": 3, "KWD": 3, "OMR": 3,
    "BTC": 8, "ETH": 18,
}
```

**Test file:** `tests/test_money.py`

**Tests (38 tests: 30 Unit, 8 Property):**

All original tests from Pass 1, plus:

```python
# GAP-02 (localcontext):
# test_money_add_uses_attestor_context -- temporarily change thread-local context,
#   verify Money.add still uses ATTESTOR_DECIMAL_CONTEXT
# test_money_sub_uses_attestor_context
# test_money_mul_uses_attestor_context

# GAP-26 (NaN/Inf rejection):
# test_money_create_nan_err -- Money.create(Decimal("NaN"), "USD") -> Err
# test_money_create_snan_err -- Money.create(Decimal("sNaN"), "USD") -> Err
# test_money_create_infinity_err -- Money.create(Decimal("Infinity"), "USD") -> Err
# test_money_create_neg_infinity_err -- Money.create(Decimal("-Infinity"), "USD") -> Err

# GAP-27 (div):
# test_money_div_by_nonzero -- Money(100, USD).div(NonZeroDecimal(4)) == Money(25, USD)
# test_money_div_preserves_currency

# GAP-28 (round_to_minor_unit):
# test_money_round_usd -- Money(Decimal("1.005"), USD).round_to_minor_unit().amount == Decimal("1.00")
# test_money_round_jpy -- Money(Decimal("100.5"), JPY).round_to_minor_unit().amount == Decimal("100")
# test_money_round_bhd -- 3 decimal places
# test_money_round_uses_half_even -- banker's rounding

# Properties:
# test_money_add_commutativity -- a.add(b) == b.add(a)
# test_money_add_associativity -- (a+b)+c == a+(b+c)
# test_money_negate_involution -- m.negate().negate() == m
# test_money_add_negate_identity -- m.add(m.negate()) has amount 0
# test_money_mul_distributivity -- k*(a+b) == k*a + k*b
```

```bash
pytest -x tests/test_money.py && mypy --strict attestor/core/money.py
```

**Done when:** All tests pass. Money arithmetic uses `localcontext`. NaN/Inf rejected at creation. `div()` and `round_to_minor_unit()` work. mypy strict passes.

---

### Step 5: Error Hierarchy (~140 lines)

**Prerequisites:** Step 2 (Result), Step 3 (UtcDatetime).
**File:** `attestor/core/errors.py`
**Resolves:** GAP-29 (.with_context), GAP-30 (to_dict key stability)

**What to code:**

Identical to PHASE0_EXECUTION.md Step 5, with these additions:

1. `AttestorError.timestamp` field type changes from `datetime` to `UtcDatetime` (GAP-03)

2. Add `.with_context()` method to `AttestorError` (GAP-29):
```python
from dataclasses import replace

@dataclass(frozen=True, slots=True)
class AttestorError:
    message: str
    code: str
    timestamp: UtcDatetime
    source: str

    def with_context(self, context: str) -> AttestorError:
        """Return a copy with context prepended to message."""
        return replace(self, message=f"{context}: {self.message}")

    def to_dict(self) -> dict[str, object]:
        return {
            "message": self.message,
            "code": self.code,
            "timestamp": self.timestamp.value.isoformat(),
            "source": self.source,
        }
```

Seven subclasses: same as Pass 1. Each `to_dict()` returns a dict with deterministic, documented keys.

**Test file:** `tests/test_errors.py`

**Tests (20 tests: 18 Unit, 2 Property):**

All original tests, plus:

```python
# GAP-29:
# test_with_context_prepends -- err.with_context("trade TX-1").message == "trade TX-1: original"
# test_with_context_preserves_subclass -- isinstance(ve.with_context("ctx"), ValidationError)
# test_with_context_preserves_fields -- ve.with_context("ctx").fields == ve.fields

# GAP-30:
# test_validation_error_to_dict_keys -- exact keys: {"message","code","timestamp","source","fields"}
# test_pricing_error_to_dict_keys -- exact keys: {"message","code","timestamp","source","instrument","reason"}
# (one test per subclass asserting exact key set)
```

```bash
pytest -x tests/test_errors.py && mypy --strict attestor/core/errors.py
```

**Done when:** All tests pass. `.with_context()` works on all subclasses. `to_dict()` keys are stable and tested. mypy strict passes.

---

### Step 6: Canonical Serialization (~120 lines)

**Prerequisites:** Steps 2-4 (Result, FrozenMap, Decimal types, UtcDatetime).
**File:** `attestor/core/serialization.py`
**Resolves:** GAP-04 (returns Result), GAP-05 (Decimal zero normalization), GAP-11 (type name stability), GAP-14 (naive datetime rejection)

**What to code:**

Two public functions --- both return `Result`:

```python
def canonical_bytes(obj: object) -> Result[bytes, str]:
    """Convert any domain type to canonical JSON bytes.

    Returns Err on unsupported types (GAP-04: never raises TypeError).
    Type names are part of the serialization contract: renaming a type
    changes all content hashes (GAP-11 / D-12).
    """
    try:
        serializable = _to_serializable(obj)
    except TypeError as e:
        return Err(f"Unsupported type in canonical serialization: {e}")
    return Ok(json.dumps(
        serializable, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8"))


def content_hash(obj: object) -> Result[str, str]:
    """SHA-256 hex digest of canonical_bytes(obj)."""
    match canonical_bytes(obj):
        case Err(e): return Err(e)
        case Ok(b): return Ok(hashlib.sha256(b).hexdigest())
```

**`_to_serializable` rules:**

- `None` → `None`
- `bool` → `bool` (before int check --- `bool` is subclass of `int`)
- `int` → `int`
- `str` → `str`
- `Decimal` → `str(obj.normalize())` with special case: `if obj == 0: return "0"` (GAP-05)
- `datetime` → must have `tzinfo`, convert to UTC ISO 8601 string; if naive, raise `TypeError` (caught by outer try/except → `Err`) (GAP-14)
- `UtcDatetime` → `obj.value.isoformat()`
- `date` → `obj.isoformat()`
- `tuple` / `list` → `[_to_serializable(x) for x in obj]`
- `FrozenMap` → `{k: _to_serializable(v) for k, v in obj.items()}`
- `Enum` → `obj.value`
- frozen dataclass → `{"_type": type(obj).__name__, **{f: _to_serializable(getattr(obj, f)) for f in sorted(field_names)}}`
- `dict` → `{k: _to_serializable(v) for k, v in sorted(obj.items())}` (boundary convenience)
- Other → `raise TypeError(f"Cannot serialize {type(obj).__name__}")`

The `derive_seed` function remains unchanged from Pass 1.

**Test file:** `tests/test_serialization.py`

**Tests (26 tests: 20 Unit, 6 Property):**

All original tests, plus:

```python
# GAP-04 (returns Result):
# test_canonical_bytes_returns_result -- isinstance(canonical_bytes(Ok(1)), Ok)
# test_canonical_bytes_unsupported_type_returns_err -- canonical_bytes(object()) -> Err
# test_content_hash_unsupported_type_returns_err

# GAP-05 (Decimal zero):
# test_decimal_zero_canonical -- canonical_bytes(Decimal("0")) == canonical_bytes(Decimal("0E+2"))
# test_decimal_zero_normalized_to_string_zero -- "0" not "0E+2"

# GAP-14 (naive datetime):
# test_naive_datetime_returns_err -- canonical_bytes(datetime(2026,1,1)) -> Err
```

```bash
pytest -x tests/test_serialization.py && mypy --strict attestor/core/serialization.py
```

**Done when:** All tests pass. `canonical_bytes` and `content_hash` return `Result`, never raise. Decimal zero is canonical. Naive datetimes are rejected. mypy strict passes.

---

### Step 7: Identifier Types (~100 lines)

**Prerequisites:** Step 2 (Result).
**File:** `attestor/core/identifiers.py`
**Resolves:** No new gaps. Unchanged from PHASE0_EXECUTION.md Step 7.

**What to code:** `LEI`, `UTI`, `ISIN` with validated `parse()` factories. Luhn algorithm for ISIN check digit.

**Tests:** Same as Pass 1 (14 tests).

```bash
pytest -x tests/test_identifiers.py && mypy --strict attestor/core/identifiers.py
```

**Done when:** LEI/UTI/ISIN validate correctly. Apple ISIN (US0378331005) and Microsoft ISIN (US5949181045) pass. mypy strict passes.

---

### Step 8: Core Package Re-exports (~20 lines)

**Prerequisites:** Steps 2-7 (all core modules).
**File:** `attestor/core/__init__.py`

**What to code:**

Re-export all public names including new types:

```python
from attestor.core.result import Ok, Err, Result, unwrap, map_result, sequence
from attestor.core.types import (
    FrozenMap, BitemporalEnvelope, IdempotencyKey, EventTime, UtcDatetime,
)
from attestor.core.money import (
    Money, PositiveDecimal, NonZeroDecimal, NonEmptyStr,
    ATTESTOR_DECIMAL_CONTEXT,
)
from attestor.core.errors import (
    AttestorError, ValidationError, IllegalTransitionError,
    ConservationViolationError, MissingObservableError,
    CalibrationError, PricingError, PersistenceError,
    FieldViolation,
)
from attestor.core.serialization import canonical_bytes, content_hash, derive_seed
from attestor.core.identifiers import LEI, UTI, ISIN

__all__ = [
    "Ok", "Err", "Result", "unwrap", "map_result", "sequence",
    "FrozenMap", "BitemporalEnvelope", "IdempotencyKey", "EventTime", "UtcDatetime",
    "Money", "PositiveDecimal", "NonZeroDecimal", "NonEmptyStr",
    "ATTESTOR_DECIMAL_CONTEXT",
    "AttestorError", "ValidationError", "IllegalTransitionError",
    "ConservationViolationError", "MissingObservableError",
    "CalibrationError", "PricingError", "PersistenceError",
    "FieldViolation",
    "canonical_bytes", "content_hash", "derive_seed",
    "LEI", "UTI", "ISIN",
]
```

**Verify:**

```bash
python -c "from attestor.core import Ok, Err, Result, Money, FrozenMap, UtcDatetime, \
    sequence, content_hash, ATTESTOR_DECIMAL_CONTEXT, LEI, ISIN"
mypy --strict attestor/core/
pytest -x tests/test_result.py tests/test_types.py tests/test_money.py \
    tests/test_errors.py tests/test_serialization.py tests/test_identifiers.py
```

**Done when:** All imports from `attestor.core` work. All prior tests pass together. mypy strict on `attestor/core/`.

---

### Step 9: Attestation and Confidence Types (~250 lines)

**Prerequisites:** Step 8 (all core types).
**Files:** `attestor/oracle/__init__.py`, `attestor/oracle/attestation.py`
**Resolves:** GAP-01 (attestation_id), GAP-06 (bid<=ask, mid/spread), GAP-07 (interval/level consistency), GAP-09 (Derived provenance non-empty), GAP-12 (UtcDatetime in FirmConfidence), GAP-20 (NonEmptyStr in FirmConfidence), GAP-31 (fit_quality non-empty), GAP-32 (conditions enum/validation)

**What to code:**

**QuoteCondition enum** (GAP-32):
```python
class QuoteCondition(Enum):
    INDICATIVE = "Indicative"
    FIRM = "Firm"
    RFQ = "RFQ"
```

**FirmConfidence** (GAP-12, GAP-20):
```python
@final
@dataclass(frozen=True, slots=True)
class FirmConfidence:
    source: NonEmptyStr       # GAP-20: not bare str
    timestamp: UtcDatetime    # GAP-12: not bare datetime
    attestation_ref: NonEmptyStr  # GAP-20

    @staticmethod
    def create(
        source: str, timestamp: datetime, attestation_ref: str,
    ) -> Result[FirmConfidence, str]:
        # Validate all three fields, return Err on any failure
        ...
```

**QuotedConfidence** (GAP-06: bid<=ask + mid/spread):
```python
@final
@dataclass(frozen=True, slots=True)
class QuotedConfidence:
    bid: Decimal
    ask: Decimal
    venue: NonEmptyStr
    size: Decimal | None
    conditions: QuoteCondition

    @staticmethod
    def create(
        bid: Decimal, ask: Decimal, venue: str,
        size: Decimal | None = None,
        conditions: QuoteCondition = QuoteCondition.INDICATIVE,
    ) -> Result[QuotedConfidence, str]:
        if bid > ask:
            return Err(f"QuotedConfidence: bid ({bid}) > ask ({ask}) implies negative spread")
        # validate venue is non-empty, bid/ask are finite, etc.
        ...

    @property
    def mid(self) -> Decimal:
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            return (self.bid + self.ask) / 2

    @property
    def spread(self) -> Decimal:
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            return self.ask - self.bid

    @property
    def half_spread(self) -> Decimal:
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            return self.spread / 2
```

**DerivedConfidence** (GAP-07: interval/level, GAP-09: provenance, GAP-31: fit_quality):
```python
@final
@dataclass(frozen=True, slots=True)
class DerivedConfidence:
    method: NonEmptyStr
    config_ref: NonEmptyStr
    fit_quality: FrozenMap[str, Decimal]  # GAP-31: must be non-empty
    confidence_interval: tuple[Decimal, Decimal] | None
    confidence_level: Decimal | None

    @staticmethod
    def create(
        method: str, config_ref: str,
        fit_quality: FrozenMap[str, Decimal],
        confidence_interval: tuple[Decimal, Decimal] | None = None,
        confidence_level: Decimal | None = None,
    ) -> Result[DerivedConfidence, str]:
        # GAP-31: reject empty fit_quality
        if len(fit_quality) == 0:
            return Err("DerivedConfidence: fit_quality must not be empty")
        # GAP-07: both or neither
        if (confidence_interval is None) != (confidence_level is None):
            return Err("confidence_interval and confidence_level must be both present or both absent")
        # If confidence_level present, must be in (0, 1)
        if confidence_level is not None and not (0 < confidence_level < 1):
            return Err(f"confidence_level must be in (0,1), got {confidence_level}")
        ...
```

**Attestation[T]** (GAP-01: attestation_id):
```python
@final
@dataclass(frozen=True, slots=True)
class Attestation(Generic[T]):
    value: T
    confidence: Confidence
    source: NonEmptyStr
    timestamp: UtcDatetime
    provenance: tuple[str, ...]
    content_hash: str        # SHA-256 of canonical_bytes(value)
    attestation_id: str      # GAP-01: SHA-256 of canonical_bytes(source, timestamp, confidence, value, provenance)
```

**Factory function:**
```python
def create_attestation(
    value: T,
    confidence: Confidence,
    source: str,
    timestamp: datetime,
    provenance: tuple[str, ...] = (),
) -> Result[Attestation[T], str]:
    # GAP-04: content_hash now returns Result
    match content_hash(value):
        case Err(e): return Err(f"Cannot hash value: {e}")
        case Ok(ch): pass

    # GAP-01: compute attestation_id from all identity fields
    identity_payload = {
        "source": source,
        "timestamp": timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp),
        "confidence": confidence,
        "value": value,
        "provenance": provenance,
    }
    match content_hash(identity_payload):
        case Err(e): return Err(f"Cannot compute attestation_id: {e}")
        case Ok(aid): pass

    match UtcDatetime.parse(timestamp):
        case Err(e): return Err(f"Attestation timestamp: {e}")
        case Ok(ts): pass

    match NonEmptyStr.parse(source):
        case Err(e): return Err(f"Attestation source: {e}")
        case Ok(src): pass

    return Ok(Attestation(
        value=value, confidence=confidence, source=src,
        timestamp=ts, provenance=provenance,
        content_hash=ch, attestation_id=aid,
    ))
```

**Test file:** `tests/test_attestation.py`

**Tests (35+ tests):**

```python
# FirmConfidence (GAP-12, GAP-20):
# test_firm_create_valid_ok
# test_firm_create_empty_source_err -- NonEmptyStr enforcement
# test_firm_timestamp_is_utc_datetime
# test_firm_frozen

# QuotedConfidence (GAP-06):
# test_quoted_create_valid_ok -- bid=154.90, ask=155.10
# test_quoted_create_bid_gt_ask_err -- bid=155.10, ask=154.90 -> Err
# test_quoted_create_bid_eq_ask_ok -- locked market is valid
# test_quoted_mid_property -- (bid+ask)/2
# test_quoted_spread_property -- ask - bid
# test_quoted_half_spread_property -- spread/2
# test_quoted_conditions_is_enum -- QuoteCondition.FIRM

# DerivedConfidence (GAP-07, GAP-31):
# test_derived_create_valid_ok
# test_derived_create_empty_fit_quality_err -- GAP-31
# test_derived_create_interval_without_level_err -- GAP-07
# test_derived_create_level_without_interval_err -- GAP-07
# test_derived_create_both_none_ok
# test_derived_create_both_present_ok
# test_derived_create_level_out_of_range_err -- 0 < level < 1

# Attestation (GAP-01, GAP-04):
# test_create_attestation_returns_result -- isinstance(result, Ok)
# test_attestation_has_attestation_id -- aid != content_hash
# test_attestation_id_differs_for_same_value_different_source -- GAP-01
# test_content_hash_same_for_same_value -- two attestations, same value, same content_hash
# test_create_attestation_unsupported_type_err -- GAP-04
# test_attestation_frozen
# test_attestation_id_deterministic -- same inputs -> same aid

# Properties:
# test_quoted_bid_leq_ask_property -- for all generated QuotedConfidence: bid <= ask
# test_derived_interval_level_consistency_property -- both or neither
# test_attestation_id_stability_property -- same inputs -> same id
```

```bash
pytest -x tests/test_attestation.py && mypy --strict attestor/oracle/attestation.py
```

**Done when:** All tests pass. QuotedConfidence rejects bid > ask. DerivedConfidence rejects empty fit_quality and inconsistent interval/level. Attestation has both `content_hash` and `attestation_id`. `create_attestation` returns `Result`. mypy strict passes.

---

### Step 10: Ledger Domain Types (~200 lines)

**Prerequisites:** Step 8 (core), Step 9 (Attestation).
**Files:** `attestor/ledger/__init__.py`, `attestor/ledger/transactions.py`
**Resolves:** GAP-33 (Account, AccountType, Position)

**What to code:**

All types from PHASE0_EXECUTION.md Step 10 (DeltaValue 6-variant union, StateDelta, DistinctAccountPair, Move, Transaction, LedgerEntry), with `datetime` → `UtcDatetime` in temporal fields.

**Add (GAP-33):**

```python
class AccountType(Enum):
    CASH = "CASH"
    SECURITIES = "SECURITIES"
    DERIVATIVES = "DERIVATIVES"
    COLLATERAL = "COLLATERAL"
    MARGIN = "MARGIN"
    ACCRUALS = "ACCRUALS"
    PNL = "PNL"


@final
@dataclass(frozen=True, slots=True)
class Account:
    account_id: NonEmptyStr
    account_type: AccountType


class ExecuteResult(Enum):
    APPLIED = "APPLIED"
    ALREADY_APPLIED = "ALREADY_APPLIED"
    REJECTED = "REJECTED"


@final
@dataclass(frozen=True, slots=True)
class Position:
    account: NonEmptyStr
    instrument: NonEmptyStr
    quantity: Decimal
```

**Test file:** `tests/test_transactions.py`

**Tests (42 tests: 36 Unit, 6 Property):**

All original tests plus:

```python
# GAP-33:
# test_account_type_has_7_variants
# test_account_creation
# test_account_frozen
# test_position_has_fields
# test_position_frozen
# test_execute_result_has_3_values
```

```bash
pytest -x tests/test_transactions.py && mypy --strict attestor/ledger/transactions.py
```

**Done when:** All tests pass. `Account`, `AccountType`, `Position`, `ExecuteResult` exist. All temporal fields use `UtcDatetime`. mypy strict passes.

---

### Step 11: Pricing Interface Types (~150 lines)

**Prerequisites:** Step 8 (core types).
**Files:** `attestor/pricing/__init__.py`, `attestor/pricing/types.py`
**Resolves:** GAP-34 (CVaR), GAP-35 (Greeks.additional), GAP-36 (valuation_date), GAP-37 (PnLAttribution factory)

**What to code:**

**ValuationResult** (GAP-36: add valuation_date):
```python
@final
@dataclass(frozen=True, slots=True)
class ValuationResult:
    instrument_id: str
    npv: Decimal
    currency: str
    valuation_date: UtcDatetime   # GAP-36
    components: FrozenMap[str, Decimal] = FrozenMap.EMPTY
    model_config_id: str = ""
    market_snapshot_id: str = ""
```

**Greeks** (GAP-35: extensible):
```python
@final
@dataclass(frozen=True, slots=True)
class Greeks:
    delta: Decimal = Decimal("0")
    gamma: Decimal = Decimal("0")
    vega: Decimal = Decimal("0")
    theta: Decimal = Decimal("0")
    rho: Decimal = Decimal("0")
    vanna: Decimal = Decimal("0")
    volga: Decimal = Decimal("0")
    charm: Decimal = Decimal("0")
    additional: FrozenMap[str, Decimal] = FrozenMap.EMPTY  # GAP-35
```

**VaRResult** (GAP-34: Expected Shortfall):
```python
@final
@dataclass(frozen=True, slots=True)
class VaRResult:
    confidence_level: Decimal
    horizon_days: int
    var_amount: Decimal
    es_amount: Decimal            # GAP-34: Expected Shortfall / CVaR
    currency: str
    method: str
    component_var: FrozenMap[str, Decimal] = FrozenMap.EMPTY
```

**PnLAttribution** (GAP-37: factory enforces decomposition):
```python
@final
@dataclass(frozen=True, slots=True)
class PnLAttribution:
    total_pnl: Decimal
    market_pnl: Decimal
    carry_pnl: Decimal
    trade_pnl: Decimal
    residual_pnl: Decimal
    currency: str

    @staticmethod
    def create(
        market_pnl: Decimal, carry_pnl: Decimal,
        trade_pnl: Decimal, residual_pnl: Decimal,
        currency: str,
    ) -> PnLAttribution:
        """Compute total from components. Invariant unbreakable by construction."""
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            total = market_pnl + carry_pnl + trade_pnl + residual_pnl
        return PnLAttribution(
            total_pnl=total, market_pnl=market_pnl,
            carry_pnl=carry_pnl, trade_pnl=trade_pnl,
            residual_pnl=residual_pnl, currency=currency,
        )
```

`Scenario` and `ScenarioResult` --- unchanged from Pass 1.

**Test file:** `tests/test_pricing_types.py`

**Tests (28 tests: 22 Unit, 6 Property):**

All original tests plus:

```python
# GAP-34: test_var_result_has_es_amount
# GAP-35: test_greeks_additional_default_is_empty, test_greeks_additional_custom
# GAP-36: test_valuation_result_has_valuation_date
# GAP-37: test_pnl_create_computes_total, test_pnl_create_decomposition_property
```

```bash
pytest -x tests/test_pricing_types.py && mypy --strict attestor/pricing/types.py
```

**Done when:** All tests pass. VaRResult has `es_amount`. Greeks has `additional`. ValuationResult has `valuation_date`. PnLAttribution.create() computes total. mypy strict passes.

---

### Step 12: Pricing Protocols and Stubs (~120 lines)

**Prerequisites:** Step 9 (Attestation), Step 11 (pricing types).
**File:** `attestor/pricing/protocols.py`
**Resolves:** GAP-38 (provisional documentation), GAP-39 (var + pnl_attribution)

**What to code:**

```python
"""Pricing and Risk Engine protocols for Attestor Phase 0.

IMPORTANT: These signatures are PROVISIONAL for Phase 0. The target
signatures from PLAN Section 3.4.3 use rich typed inputs:
  - instrument: Instrument (not yet defined)
  - market: Attestation[MarketDataSnapshot] (not yet defined)
  - model_config: Attestation[ModelConfig] (not yet defined)
  - returns: Result[Attestation[ValuationResult], PricingError]

Phase 1 will introduce these types and migrate the protocols.
See PLAN Section 3.4.3 for the definitive contract.
"""


class PricingEngine(Protocol):
    def price(
        self, instrument_id: str, market_snapshot_id: str, model_config_id: str,
    ) -> Result[ValuationResult, PricingError]: ...

    def greeks(
        self, instrument_id: str, market_snapshot_id: str, model_config_id: str,
    ) -> Result[Greeks, PricingError]: ...

    # GAP-39: add var and pnl_attribution
    def var(
        self, portfolio: tuple[str, ...], market_snapshot_id: str,
        confidence_level: Decimal, horizon_days: int, method: str,
    ) -> Result[VaRResult, PricingError]: ...

    def pnl_attribution(
        self, portfolio: tuple[str, ...],
        start_snapshot_id: str, end_snapshot_id: str,
    ) -> Result[PnLAttribution, PricingError]: ...


class RiskEngine(Protocol):
    def scenario_pnl(
        self, portfolio: tuple[str, ...], scenarios: tuple[Scenario, ...],
        market_snapshot_id: str,
    ) -> Result[tuple[ScenarioResult, ...], PricingError]: ...


@final
class StubPricingEngine:
    """Test double. Returns deterministic Ok values. Not production code."""

    def price(self, instrument_id: str, market_snapshot_id: str,
              model_config_id: str) -> Result[ValuationResult, PricingError]:
        return Ok(ValuationResult(
            instrument_id=instrument_id, npv=Decimal("0"), currency="USD",
            valuation_date=UtcDatetime.now(),
        ))

    def greeks(self, instrument_id: str, market_snapshot_id: str,
               model_config_id: str) -> Result[Greeks, PricingError]:
        return Ok(Greeks())

    def var(self, portfolio: tuple[str, ...], market_snapshot_id: str,
            confidence_level: Decimal, horizon_days: int,
            method: str) -> Result[VaRResult, PricingError]:
        return Ok(VaRResult(
            confidence_level=confidence_level, horizon_days=horizon_days,
            var_amount=Decimal("0"), es_amount=Decimal("0"),
            currency="USD", method=method,
        ))

    def pnl_attribution(self, portfolio: tuple[str, ...],
                        start_snapshot_id: str,
                        end_snapshot_id: str) -> Result[PnLAttribution, PricingError]:
        return Ok(PnLAttribution.create(
            Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), "USD",
        ))
```

**Test file:** `tests/test_pricing_protocols.py`

**Tests (16 tests):**

Original tests plus:

```python
# GAP-39:
# test_stub_var_returns_ok
# test_stub_var_es_amount_is_decimal
# test_stub_pnl_attribution_returns_ok
# test_stub_pnl_attribution_total_is_zero
# test_stub_implements_full_pricing_engine_protocol
```

```bash
pytest -x tests/test_pricing_protocols.py && mypy --strict attestor/pricing/protocols.py
```

**Done when:** All tests pass. StubPricingEngine implements all 4 methods. Protocol comments cite PLAN 3.4.3 as target. mypy strict passes.

---

### Step 13: Infrastructure Protocols + Memory Adapters + Config (~400 lines)

**Prerequisites:** Step 8 (core), Step 9 (Attestation), Step 10 (Transaction).
**Files:**
- `attestor/infra/__init__.py`
- `attestor/infra/protocols.py` (GAP-13, GAP-41)
- `attestor/infra/memory_adapter.py` (GAP-01: key by attestation_id)
- `attestor/infra/config.py` (GAP-40: full topic configs, Kafka/Postgres config types)
- `attestor/infra/health.py` (GAP-40: health check protocol)

**Resolves:** GAP-01 (store key = attestation_id), GAP-13 (exists returns Result), GAP-40 (adopt full infra spec from PASS3), GAP-41 (D-07 clarification)

**What to code:**

**protocols.py** --- exactly as specified in PASS3_REVIEW.md Section 2.3.1:
- `AttestationStore.store()` returns `Result[str, PersistenceError]` (attestation_id)
- `AttestationStore.retrieve()` takes `attestation_id: str`
- `AttestationStore.exists()` returns `Result[bool, PersistenceError]` (GAP-13)
- `EventBus`, `TransactionLog`, `StateStore` --- as specified

Module docstring includes D-07 clarification (GAP-41): "`infra/protocols.py` may import domain types from any pillar for protocol signatures. `infra/` implementation modules import only `core/` and `infra/protocols`."

**memory_adapter.py** --- exactly as specified in PASS3_REVIEW.md Section 2.3.2:
- `InMemoryAttestationStore` keyed by `attestation_id` (GAP-01)
- `exists()` returns `Result[bool, PersistenceError]` (GAP-13)
- All four `@final` adapters

**config.py** --- from PASS3_REVIEW.md Sections 2.1 + 2.4 + 2.5:
- `TopicConfig` with `replication_factor`, `cleanup_policy`, `min_insync_replicas`
- `phase0_topic_configs()` returns 3 configs with correct retention
- `KafkaProducerConfig` (frozen, all settings documented)
- `KafkaConsumerConfig` (frozen, at-least-once with manual commit)
- `PostgresPoolConfig` (frozen, with `dsn` property, password from env var)

**health.py** --- from PASS3_REVIEW.md Section 2.4.3:
- `HealthStatus`, `SystemHealth` frozen dataclasses
- `HealthCheckable` protocol
- `liveness_check()`, `readiness_check(dependencies)` functions

**Test files:** `tests/test_infra.py`, `tests/test_memory_adapter.py`

**Tests (35 tests):**

```python
# Protocols:
# test_attestation_store_is_protocol
# test_event_bus_is_protocol
# test_transaction_log_is_protocol
# test_state_store_is_protocol
# test_health_checkable_is_protocol

# Memory adapters:
# test_attestation_store_store_and_retrieve
# test_attestation_store_keyed_by_attestation_id -- GAP-01
# test_attestation_store_idempotent
# test_attestation_store_retrieve_not_found_err
# test_attestation_store_exists_returns_result -- GAP-13
# test_event_bus_publish_and_get
# test_event_bus_multi_topic_isolation
# test_transaction_log_append_replay_order
# test_transaction_log_replay_since
# test_state_store_put_get_roundtrip
# test_state_store_missing_returns_ok_none
# (+ structural subtyping tests)

# Config:
# test_phase0_topics_count_3
# test_attestations_topic_infinite_retention
# test_topic_config_has_replication_factor
# test_kafka_producer_config_frozen
# test_kafka_consumer_config_auto_commit_false
# test_postgres_pool_config_dsn

# Health:
# test_liveness_check_returns_healthy
# test_readiness_check_all_healthy
# test_readiness_check_one_unhealthy

# Properties:
# test_attestation_store_idempotent_property
# test_transaction_log_roundtrip_property
# test_state_store_roundtrip_property
```

```bash
pytest -x tests/test_infra.py tests/test_memory_adapter.py
mypy --strict attestor/infra/
```

**Done when:** All tests pass. Attestation store keys by `attestation_id`. `exists()` returns `Result`. Config types include replication factor and min ISR. Health checks work. mypy strict passes.

---

### Step 14: Integration Tests + SQL DDL + Kafka Config (~180 lines)

**Prerequisites:** Steps 9, 13 (attestation types + infrastructure).
**Files:**
- `tests/test_integration_attestation_store.py`
- `tests/conftest.py` (Hypothesis strategies)
- `sql/001_attestations.sql` (GAP-01/18/19: attestation_id PK)
- `sql/002_event_log.sql`
- `sql/003_schema_registry.sql`

**Resolves:** GAP-18 (attestation_id PK), GAP-19 (attestation_id column)

**What to code:**

**Integration tests** --- from PASS2 Section 2.2.11, updated for attestation_id:

```python
# test_store_firm_attestation_and_retrieve -- store, retrieve by attestation_id
# test_store_quoted_attestation_and_retrieve
# test_store_derived_attestation_with_provenance
# test_content_addressing_idempotent -- same attestation_id, one copy
# test_retrieve_nonexistent_returns_err
# test_full_provenance_chain_walkable
# test_same_value_different_source_distinct_attestation_ids -- GAP-01
# test_attestation_content_hash_stability_across_store_retrieve
```

**conftest.py** --- from PASS2 Section 2.1, updated for factory methods (QuotedConfidence.create, DerivedConfidence.create, FirmConfidence.create), UtcDatetime, and attestation_id.

**SQL DDL** --- exactly as specified in PASS3_REVIEW.md Section 2.2:
- `001_attestations.sql`: `attestation_id TEXT PRIMARY KEY`, `content_hash TEXT NOT NULL` (indexed, non-unique), append-only trigger, GIN index on provenance_refs
- `002_event_log.sql`: `idempotency_key TEXT UNIQUE`, `kafka_ref TEXT`, append-only trigger
- `003_schema_registry.sql`: composite PK `(type_name, version)`, `schema_json JSONB`, append-only trigger

**Verify SQL syntax:**

```bash
python -c "
import pathlib
for f in sorted(pathlib.Path('sql').glob('*.sql')):
    text = f.read_text()
    assert 'CREATE TABLE' in text or 'CREATE SCHEMA' in text, f'{f.name}: missing CREATE'
    print(f'{f.name}: {len(text)} bytes, OK')
"
```

```bash
pytest -x tests/test_integration_attestation_store.py
```

**Done when:** All 8 integration tests pass. Provenance chain walkable. Same value from different sources produces distinct attestation_ids. 3 SQL files exist with correct DDL. conftest provides valid strategies for all types.

---

### Step 15: CI Pipeline + Full Verification (~100 lines YAML)

**Prerequisites:** Steps 1-14. Capstone.
**File:** `.github/workflows/ci.yml`

**What to code:**

GitHub Actions CI with three stages: lint → test → verify.

```yaml
name: Attestor CI
on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install mypy ruff
      - run: mypy --strict attestor/
      - run: ruff check attestor/ tests/

  test:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install pytest hypothesis
      - run: pytest tests/ -x --tb=short -v

  verify:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: No float in domain type annotations
        run: |
          python -c "
          import pathlib, re, sys
          violations = []
          for f in pathlib.Path('attestor').rglob('*.py'):
              for i, line in enumerate(f.read_text().splitlines(), 1):
                  if re.search(r':\s*float\b', line) and 'noqa' not in line:
                      violations.append(f'{f}:{i}: {line.strip()}')
          if violations:
              for v in violations: print(v, file=sys.stderr)
              sys.exit(1)
          print('No float in type annotations. PASS.')
          "
      - name: All dataclasses are frozen
        run: |
          python -c "
          import pathlib, re, sys
          for f in pathlib.Path('attestor').rglob('*.py'):
              for m in re.finditer(r'@dataclass\((.*?)\)', f.read_text()):
                  if 'frozen=True' not in m.group(1):
                      print(f'FAIL {f}: {m.group(0)}', file=sys.stderr)
                      sys.exit(1)
          print('All dataclasses frozen. PASS.')
          "
      - name: No raise in domain functions
        run: |
          python -c "
          import ast, pathlib, sys
          ALLOWED = {'__post_init__', 'unwrap'}
          violations = []
          for f in pathlib.Path('attestor').rglob('*.py'):
              tree = ast.parse(f.read_text())
              for node in ast.walk(tree):
                  if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                      if node.name in ALLOWED: continue
                      for child in ast.walk(node):
                          if isinstance(child, ast.Raise):
                              violations.append(f'{f}:{child.lineno}: raise in {node.name}')
          if violations:
              for v in violations: print(v, file=sys.stderr)
              sys.exit(1)
          print('No raise in domain functions. PASS.')
          "
      - name: Import smoke test
        run: |
          python -c "
          from attestor.core import (
              Ok, Err, Result, Money, FrozenMap, BitemporalEnvelope,
              AttestorError, ValidationError, LEI, UTI, ISIN,
              content_hash, ATTESTOR_DECIMAL_CONTEXT, PositiveDecimal,
              UtcDatetime, sequence,
          )
          from attestor.oracle.attestation import (
              Attestation, FirmConfidence, QuotedConfidence, DerivedConfidence,
              create_attestation, QuoteCondition,
          )
          from attestor.ledger.transactions import (
              Move, Transaction, StateDelta, LedgerEntry, DistinctAccountPair,
              DeltaValue, DeltaDecimal, DeltaNull, Account, AccountType, Position,
          )
          from attestor.pricing.types import (
              ValuationResult, Greeks, Scenario, ScenarioResult, VaRResult, PnLAttribution,
          )
          from attestor.pricing.protocols import PricingEngine, RiskEngine, StubPricingEngine
          from attestor.infra.protocols import (
              EventBus, AttestationStore, TransactionLog, StateStore,
          )
          from attestor.infra.memory_adapter import (
              InMemoryEventBus, InMemoryAttestationStore,
              InMemoryTransactionLog, InMemoryStateStore,
          )
          from attestor.infra.config import PHASE0_TOPICS, phase0_topic_configs
          print('All 50+ types importable. PASS.')
          "
```

**Full local verification:**

```bash
# Stage 1: Lint
mypy --strict attestor/
ruff check attestor/ tests/

# Stage 2: Test
pytest tests/ -x --tb=short -v

# Stage 3: Verify
# (run each verify script from the CI YAML above)
```

**Done when:** All verification stages pass locally. CI YAML exists. All 50+ types importable. No float, no unfrozen dataclass, no raise in domain functions.

---

### Build Sequence Summary

| Step | Module(s) | Prod Lines | Test Lines | Gaps Resolved |
|------|-----------|-----------|------------|---------------|
| 1 | pyproject.toml, `__init__.py` | ~35 | 0 | --- |
| 2 | `core/result.py` | ~100 | ~100 | GAP-21,22,23,24,25,15 |
| 3 | `core/types.py` | ~150 | ~100 | GAP-03,08,10 |
| 4 | `core/money.py` | ~160 | ~120 | GAP-02,26,27,28 |
| 5 | `core/errors.py` | ~140 | ~80 | GAP-29,30 |
| 6 | `core/serialization.py` | ~120 | ~90 | GAP-04,05,11,14 |
| 7 | `core/identifiers.py` | ~100 | ~70 | --- |
| 8 | `core/__init__.py` | ~20 | 0 | --- |
| 9 | `oracle/attestation.py` | ~250 | ~120 | GAP-01,06,07,09,12,20,31,32 |
| 10 | `ledger/transactions.py` | ~200 | ~110 | GAP-33 |
| 11 | `pricing/types.py` | ~150 | ~90 | GAP-34,35,36,37 |
| 12 | `pricing/protocols.py` | ~120 | ~60 | GAP-38,39 |
| 13 | `infra/*.py` (4 files) | ~400 | ~120 | GAP-13,40,41 |
| 14 | Integration + SQL + conftest | ~180 | ~160 | GAP-18,19 |
| 15 | CI YAML | ~100 | 0 | --- |
| **Total** | **16 modules + 3 SQL + 1 YAML** | **~2,225** | **~1,220** | **41/41** |

### Dependency Graph

```
Step 1: Scaffold
  |
  v
Step 2: Result[T, E] (full monad API) --------+
  |                                             |
  v                                             v
Step 3: UtcDatetime, FrozenMap,              Step 5: Error
  BitemporalEnvelope,                          hierarchy
  IdempotencyKey, EventTime                    |
  |                                             |
  v                                             v
Step 4: Money,                               Step 7: Identifiers
  Decimal context                                |
  |                                             |
  v                                             v
Step 6: Serialization  <------------------------+
  (returns Result)                              |
  |                                             |
  +---------------------------------------------+
  |
  v
Step 8: Core re-exports (Steps 2-7)
  |
  +----------+----------+----------+
  |          |          |          |
  v          v          v          v
Step 9:   Step 10:   Step 11:   Step 13:
Oracle    Ledger     Pricing    Infra
          types      types      protocols +
  |          |          |        adapters +
  |          |          v        config
  |          |       Step 12:      |
  |          |       Pricing       |
  |          |       protocols     |
  +----+-----+----------+---------+
       |
       v
Step 14: Integration tests + SQL DDL + conftest
       |
       v
Step 15: CI pipeline + full verification
```

### Estimated Schedule

| Day | Steps | Deliverable |
|-----|-------|-------------|
| **Monday AM** | 1, 2, 3 | Scaffold + Result (full API) + UtcDatetime + FrozenMap |
| **Monday PM** | 4, 5 | Money (with div, round, NaN rejection) + Errors (with_context) |
| **Tuesday AM** | 6, 7 | Serialization (returns Result) + Identifiers |
| **Tuesday PM** | 8 | Core package assembled, all modules tested |
| **Wednesday AM** | 9 | Attestation + Confidence (attestation_id, bid<=ask, fit_quality) |
| **Wednesday PM** | 10 | Ledger types (with Account, Position) |
| **Thursday AM** | 11, 12 | Pricing types (CVaR, Greeks.additional) + Protocols (var, pnl_attribution) |
| **Thursday PM** | 13 | Infrastructure (protocols, adapters, config, health) |
| **Friday AM** | 14 | Integration tests + SQL DDL + conftest |
| **Friday PM** | 15 | CI pipeline green. **Phase 0 COMPLETE.** |

---

## 7. Production Readiness [Jane Street CTO]

### 7.1 CI Pipeline Completeness

The CI pipeline (Step 15) enforces the following invariants on every push:

| Check | What It Catches | Stage |
|-------|----------------|-------|
| `mypy --strict` | Type errors, missing annotations, Any leaks | lint |
| `ruff check` | Style violations, import ordering, unused imports | lint |
| `pytest -x` | Logic errors, property violations, integration failures | test |
| No-float scan | `float` in domain type annotations | verify |
| All-frozen scan | `@dataclass` without `frozen=True` | verify |
| No-raise scan | `raise` in domain functions (except `unwrap`) | verify |
| Import smoke test | Missing re-exports, circular imports | verify |

**Missing from Phase 0 CI (acceptable, Phase 1 additions):**
- Coverage threshold enforcement (`--cov --cov-fail-under=90`)
- Hypothesis CI profile (`--hypothesis-profile=ci` with 200 examples)
- SQL DDL syntax validation against a Postgres instance
- Mutation testing (mutmut)

### 7.2 Failure Mode Catalogue

| Component | Failure Mode | Detection | Recovery | Blast Radius |
|-----------|-------------|-----------|----------|-------------|
| `canonical_bytes` | Unsupported type | Returns `Err` (GAP-04) | Caller handles `Err` | Single attestation rejected |
| `Money.create` | NaN/Infinity | Returns `Err` (GAP-26) | Caller handles `Err` | Single money creation rejected |
| `FrozenMap.create` | Non-comparable keys | Returns `Err` (GAP-08) | Caller handles `Err` | Single map creation rejected |
| `UtcDatetime.parse` | Naive datetime | Returns `Err` (GAP-03) | Caller handles `Err` | Single temporal field rejected |
| `QuotedConfidence.create` | bid > ask | Returns `Err` (GAP-06) | Caller handles `Err` | Single quote rejected |
| `DerivedConfidence.create` | Empty fit_quality | Returns `Err` (GAP-31) | Caller handles `Err` | Single derived attestation rejected |
| `AttestationStore.retrieve` | Key not found | Returns `Err(PersistenceError)` | Caller handles `Err` | Single lookup fails |
| `AttestationStore.exists` | Connection error (production) | Returns `Err(PersistenceError)` (GAP-13) | Circuit breaker, retry | Store temporarily unavailable |
| Kafka producer | Broker timeout | Retry 3x with backoff, then DLQ | Page on-call if DLQ fills | Messages delayed |
| Postgres write | Connection timeout | Retry 1x, skip materialization | Projection catches up on next batch | Projection temporarily stale |
| Content hash collision | SHA-256 collision | **HALT** (probability ≈ 0) | Page on-call, investigate data corruption | **System-wide** |

### 7.3 The 3am Test

> *Can an on-call engineer, woken at 3am by an alert, diagnose a problem by reading the code and error messages?*

**Verdict: YES**, with the following justification:

1. **Every error is a value.** No exceptions in domain code. The `AttestorError` hierarchy with `message`, `code`, `timestamp`, `source` plus subclass-specific fields tells the engineer exactly what failed, where, and when.

2. **Error context chaining.** The `.with_context()` method (GAP-29) allows each layer to annotate errors: `"while processing trade TX-12345: while parsing Money: NonEmptyStr requires non-empty string"`. The full path from root cause to symptom is in the message.

3. **Content-addressed identity.** Every attestation has a unique `attestation_id`. Given an ID, the engineer can look it up in the Postgres projection or find it in the Kafka topic. Provenance chains are walkable.

4. **Deterministic replay.** Same attestations + same code version = same output. The engineer can reproduce the issue locally by replaying the same inputs.

5. **Single-writer ledger.** No lock contention, no deadlocks, no race conditions. If the ledger-writer is down, the issue is always "process not running" --- never "state corrupted by concurrent writes."

6. **Append-only everything.** No data is ever deleted or modified. The engineer can always see the full history. Postgres triggers reject UPDATE/DELETE.

**Remaining concern:** Structured logging and distributed tracing are Phase 1 deliverables. For Phase 0, error values carry enough context. In production (Phase 1+), add OpenTelemetry trace IDs to `AttestorError`.

---

## 8. Consolidated Changes

### 8.1 Complete Gap Registry

All 41 gaps from Passes 2-4, organized by resolution step:

| Gap ID | Description | Severity | Resolved In |
|--------|-------------|----------|-------------|
| GAP-01 | Add `attestation_id`, use as store key and Postgres PK | **VETO** | Steps 9, 13, 14 |
| GAP-02 | Money arithmetic must use `ATTESTOR_DECIMAL_CONTEXT` | **VETO** | Step 4 |
| GAP-03 | Naive datetimes → `UtcDatetime` refined type | **VETO** | Step 3 |
| GAP-04 | `canonical_bytes` / `content_hash` return `Result` | **VETO** | Step 6 |
| GAP-05 | Decimal zero normalization (`"0"` not `"0E+2"`) | HIGH | Step 6 |
| GAP-06 | `QuotedConfidence`: `bid <= ask` + mid/spread/half_spread | HIGH | Step 9 |
| GAP-07 | `DerivedConfidence`: interval/level both-or-neither | HIGH | Step 9 |
| GAP-08 | `FrozenMap.create` returns `Result`, handles non-comparable keys | MEDIUM | Step 3 |
| GAP-09 | `DerivedConfidence` provenance non-empty | HIGH | Step 9 |
| GAP-10 | `FrozenMap.create` deduplicates keys from Iterable input | MEDIUM | Step 3 |
| GAP-11 | Type names part of serialization contract (document) | MEDIUM | Step 6 |
| GAP-12 | `FirmConfidence.timestamp` → `UtcDatetime` | HIGH | Step 9 |
| GAP-13 | `AttestationStore.exists()` returns `Result[bool, PersistenceError]` | HIGH | Step 13 |
| GAP-14 | Naive datetime in `_serialize_value` → return Err | LOW | Step 6 |
| GAP-15 | `map_result` redundant once `.map()` exists (retain as alias) | LOW | Step 2 |
| GAP-16 | Minor config items | LOW | Step 13 |
| GAP-17 | Minor config items | LOW | Step 13 |
| GAP-18 | Postgres `attestations` PK = `attestation_id` | LOW | Step 14 |
| GAP-19 | Add `attestation_id` column to Postgres schema | LOW | Step 14 |
| GAP-20 | `FirmConfidence`: `NonEmptyStr` for source/attestation_ref | MEDIUM | Step 9 |
| GAP-21 | `.map(f)` method on `Ok`/`Err` | **VETO** | Step 2 |
| GAP-22 | `.bind(f)` / `.and_then(f)` method | **VETO** | Step 2 |
| GAP-23 | `.unwrap_or(default)` method | HIGH | Step 2 |
| GAP-24 | `.map_err(f)` method | HIGH | Step 2 |
| GAP-25 | `sequence(results)` free function | MEDIUM | Step 2 |
| GAP-26 | `Money.create()` rejects NaN/Infinity | HIGH | Step 4 |
| GAP-27 | `Money.div(divisor: NonZeroDecimal)` | HIGH | Step 4 |
| GAP-28 | `Money.round_to_minor_unit()` with ISO 4217 | HIGH | Step 4 |
| GAP-29 | `AttestorError.with_context(ctx)` via `dataclasses.replace` | MEDIUM | Step 5 |
| GAP-30 | Test `to_dict()` exact keys per error subclass | LOW | Step 5 |
| GAP-31 | `DerivedConfidence`: `fit_quality` must be non-empty | HIGH | Step 9 |
| GAP-32 | `QuotedConfidence.conditions` → `QuoteCondition` enum | MEDIUM | Step 9 |
| GAP-33 | `Account`, `AccountType`, `Position` types specified | MEDIUM | Step 10 |
| GAP-34 | `VaRResult.es_amount` (Expected Shortfall / CVaR) | HIGH | Step 11 |
| GAP-35 | `Greeks.additional: FrozenMap[str, Decimal]` | MEDIUM | Step 11 |
| GAP-36 | `ValuationResult.valuation_date: UtcDatetime` | MEDIUM | Step 11 |
| GAP-37 | `PnLAttribution.create()` factory computes total | MEDIUM | Step 11 |
| GAP-38 | Pillar V protocol signatures documented as provisional | HIGH | Step 12 |
| GAP-39 | Add `var()` and `pnl_attribution()` to `PricingEngine` | HIGH | Step 12 |
| GAP-40 | Adopt full infrastructure spec from PASS3 Section 2 | HIGH | Step 13 |
| GAP-41 | Clarify PLAN rule D-07 for `infra/protocols.py` | LOW | Step 13 |

### 8.2 Gap Resolution Summary

| Priority | Count | All Resolved? |
|----------|-------|---------------|
| VETO | 6 | Yes (Steps 2,3,4,6,9,13) |
| HIGH | 16 | Yes (Steps 2,4,6,9,11,12,13) |
| MEDIUM | 10 | Yes (Steps 3,5,9,10,11,13) |
| LOW | 9 | Yes (Steps 2,5,6,13,14) |
| **Total** | **41** | **41/41 resolved** |

---

## 9. Agent Sign-Off

### 9.1 Individual Verdicts

| Agent | Role | Verdict | Notes |
|-------|------|---------|-------|
| **Minsky** (Chair) | Type safety, illegal state prevention | **APPROVED** | All 41 gaps resolved. UtcDatetime prevents naive datetime leakage. QuotedConfidence.create rejects bid > ask. DerivedConfidence.create rejects empty fit_quality and inconsistent interval/level. Result monad complete. No illegal states constructible without bypassing factory methods. |
| **Formalis** (Veto Authority) | Formal verification, invariants | **APPROVED** | All 6 VETO items resolved. canonical_bytes is total (returns Result). Decimal context is explicit. Content addressing distinguishes attestation_id from content_hash. See Section 11 for full certification. |
| **Grothendieck** | Category theory, architecture | **APPROVED** | Five-pillar categorical structure preserved. Attestation functor correctly defined with attestation_id as morphism identity. Giry monad integration point (DerivedConfidence with confidence_interval) is well-typed. |
| **Henri Cartan** | Mathematical foundations | **APPROVED** | Attestation algebra axioms (A1-A3) stated and enforced. Hashing contract formalized. Bitemporal ordering axioms (T1-T2) stated. Money module structure verified. |
| **Halmos** | Notation, exposition | **APPROVED** | Naming conventions consistent (PascalCase types, snake_case modules, UPPER_SNAKE constants). Math-to-code mapping documented. Define-before-use ordering in build sequence. |
| **Noether** | Conservation laws, symmetries | **APPROVED** | Seven conservation laws identified with symmetry, enforcement mechanism, and test. Broken symmetry detection table provided. All conservation laws testable in CI. |
| **Dirac** | Unification, elegance | **APPROVED** | Confidence type is minimal (3 variants, no redundancy). DeltaValue is minimal (6 variants, not unifiable). Result API is minimal (5 methods + 2 free functions). No unnecessary abstractions. |
| **Feynman** | Dual-path verification | **APPROVED** | Nine critical operations verified via two independent computation paths. Content hash has independent verification. Money addition verified by commutativity. |
| **Gatheral** | Volatility, pricing, market reality | **APPROVED** | Money rejects NaN/Infinity. QuotedConfidence enforces bid <= ask. DerivedConfidence requires non-empty fit_quality. VaRResult includes Expected Shortfall. Pillar V protocols documented as provisional. Division and rounding added to Money. |
| **Geohot** | Radical simplicity | **APPROVED** | ~2,225 production lines for a cross-asset foundation is lean. No unnecessary layers. 16 modules is acceptable for the scope. Every type earns its place. `map_result` kept as alias (not deleted) --- acceptable. |
| **Karpathy** | Build from scratch, verify every step | **APPROVED** | 15 ordered steps, each independently testable. Dependency DAG is acyclic. Monday-to-Friday schedule is realistic. A developer can follow this without asking questions. |
| **Karpathy (Code Review)** | Readability, file minimalism | **APPROVED** | Each module is small enough to read in under an hour. File count (16 modules) is justified by pillar separation. No file has more than ~250 lines of production code. |
| **Chris Lattner** | Infrastructure, progressive disclosure | **APPROVED** | Progressive disclosure achieved: `Money.create(Decimal("100"), "USD")` is one line. `.unwrap_or()` handles the common case. Import path is clean (`from attestor.core import ...`). Error diagnostics are first-class. |
| **Jane Street CTO** | Production rigour | **APPROVED** | Pure functions at the core. Side effects at infrastructure boundary. Every failure is explicit (Result, not exceptions). Single-writer ledger. Append-only everything. 3am test passes. |
| **FinOps Architect** | Financial operations, compliance | **APPROVED** | Double-entry enforced by DistinctAccountPair. Decimal-only arithmetic. Append-only audit trail. Bitemporal columns on all persistence. Kafka + Postgres provisioning fully specified. |
| **Test Committee** | Testing strategy | **APPROVED** | ~1,220 test lines. Hypothesis strategies for all types. Property-based tests for algebraic laws. Static analysis in CI. Integration tests for attestation store. Determinism tests. Invariant tests. |

### 9.2 Reservations

| Agent | Reservation | Impact | Resolution |
|-------|------------|--------|------------|
| Gatheral | Pillar V protocol signatures are provisional (string IDs, not typed objects) | Phase 1 will need protocol migration | Documented in Step 12 comment block. Stub works for Phase 0 testing. |
| Lattner | `FrozenMap.create` returning `Result` adds ceremony for the common case (string keys always comparable) | Slightly worse ergonomics | Acceptable trade-off for totality. Consider `FrozenMap.of()` shorthand for string keys in Phase 1. |
| Geohot | `_ISO4217_MINOR_UNITS` dict is a mini-database in code | Could grow unwieldy | Phase 1 should externalize to a config file or use a library. Phase 0 subset (12 currencies) is fine. |

---

## 10. Minsky Certification

### 10.1 Illegal State Analysis

| Question | Answer |
|----------|--------|
| Can a `Money` with NaN be constructed? | **No.** `Money.create` checks `amount.is_finite()` (GAP-26). |
| Can a `QuotedConfidence` with negative spread be constructed? | **No.** `QuotedConfidence.create` checks `bid <= ask` (GAP-06). |
| Can a naive datetime enter an `Attestation`? | **No.** `UtcDatetime.parse` rejects naive datetimes (GAP-03). All temporal fields use `UtcDatetime`. |
| Can `canonical_bytes` raise an exception? | **No.** Returns `Result[bytes, str]` (GAP-04). TypeError caught internally. |
| Can `DerivedConfidence` have empty fit_quality? | **No.** Factory rejects `FrozenMap.EMPTY` (GAP-31). |
| Can `DerivedConfidence` have interval without level? | **No.** Factory enforces both-or-neither (GAP-07). |
| Can the attestation store confuse two different observations? | **No.** Store keys by `attestation_id` (hash of all fields), not `content_hash` (GAP-01). |
| Can a `DistinctAccountPair` have debit == credit? | **No.** Factory returns `Err` (unchanged from Pass 1). |
| Can domain code raise exceptions? | **No** (except `unwrap`, documented test-only). CI AST scan enforces. |
| Can `FrozenMap` produce non-deterministic serialization? | **No.** Entries sorted by key. Duplicates deduplicated (GAP-10). |

### 10.2 Exhaustiveness Check

Every manifesto requirement for Phase 0 scope has a corresponding deliverable in the build sequence:

| Manifesto Requirement | Build Step | Deliverable |
|----------------------|-----------|-------------|
| Attestation framework | Step 9 | `Attestation[T]`, `create_attestation`, confidence types |
| Content-addressed identity | Steps 6, 9 | `canonical_bytes`, `content_hash`, `attestation_id` |
| Epistemic confidence | Step 9 | `FirmConfidence`, `QuotedConfidence`, `DerivedConfidence` |
| Double-entry bookkeeping types | Step 10 | `Move`, `Transaction`, `LedgerEntry`, `DistinctAccountPair` |
| Pricing interface contracts | Steps 11, 12 | `ValuationResult`, `Greeks`, `VaRResult`, `PricingEngine` protocol |
| Infrastructure protocols | Step 13 | `AttestationStore`, `EventBus`, `TransactionLog`, `StateStore` |
| Persistence schemas | Step 14 | 3 SQL DDL files, Kafka topic configs |
| CI pipeline | Step 15 | GitHub Actions: lint → test → verify |

### 10.3 Chair's Ruling

**APPROVED.** The build sequence covers the full Phase 0 scope as defined in the manifesto and PLAN.md. All 41 identified gaps are resolved. Illegal states are unrepresentable via factory methods and refined types. Every failure mode is explicit. The plan is exhaustive and implementable.

---

## 11. Formalis Certification

### 11.1 Invariant Coverage

| Invariant | Formally Stated? | Component Assigned? | Test Specified? | Enforcement Type |
|-----------|-----------------|--------------------|-----------------|--------------------|
| INV-O01 (Immutability) | Yes | All types | `test_inv_o01_attestation_immutability_property` | Type system (`frozen=True`) + CI scan |
| INV-O03 (Provenance closure) | Yes | `create_attestation`, AttestationStore | `test_full_provenance_chain_walkable` | Integration test |
| INV-O04 (Confidence exhaustiveness) | Yes | `Confidence` union type | `test_inv_o04_confidence_exhaustiveness_property` | Type system (mypy `assert_never`) |
| INV-O05 (Firm payload completeness) | Yes | `FirmConfidence.create` | `test_inv_o05_firm_payload_completeness` | Factory validation (GAP-20) |
| INV-O06 (Quoted payload completeness) | Yes | `QuotedConfidence.create` | `test_inv_o06_quoted_payload_completeness` | Factory validation (GAP-06) |
| INV-O07 (Derived payload completeness) | Yes | `DerivedConfidence.create` | `test_inv_o07_derived_payload_completeness` | Factory validation (GAP-07, GAP-31) |
| INV-R04 (Reproducibility) | Yes | All determinism-sensitive code | `test_inv_r04_reproducibility` | `localcontext`, `UtcDatetime`, sorted keys |
| INV-R05 (Content addressing) | Yes | `canonical_bytes`, `content_hash` | `test_inv_r05_content_addressing` | Canonical serialization rules |
| INV-X03 (Idempotency) | Yes | `AttestationStore.store` | `test_inv_x03_idempotency_store` | Content-addressed keys, `ON CONFLICT DO NOTHING` |
| INV-L05 (Transaction atomicity) | Yes | `Transaction` (frozen tuple of moves) | `test_inv_l05_transaction_atomicity` | Type system (immutable transaction) |
| INV-L10 (No domain raises) | Yes | All domain functions | `test_inv_l10_no_raise_in_domain` | AST scan in CI |
| INV-P05 (Content-addressed Postgres) | Yes | `001_attestations.sql` | DDL inspection | `attestation_id TEXT PRIMARY KEY` |
| INV-P06 (Append-only Postgres) | Yes | All 3 SQL tables | DDL inspection | `prevent_mutation()` trigger |

### 11.2 Specification Gaps

**None remaining.** All 41 gaps from Passes 2-3 are resolved in the build sequence. Every interface is formally specified with types, preconditions, and postconditions via factory methods that return `Result`.

### 11.3 Determinism Audit (Final)

| Item | Status | Resolution |
|------|--------|------------|
| D-01: Money thread-local context | **RESOLVED** | `with localcontext(ATTESTOR_DECIMAL_CONTEXT)` (GAP-02) |
| D-02: Naive datetimes | **RESOLVED** | `UtcDatetime` refined type (GAP-03) |
| D-03: FrozenMap non-comparable keys | **RESOLVED** | Returns `Result` (GAP-08) |
| D-04: FrozenMap duplicate keys | **RESOLVED** | `dict()` dedup before sort (GAP-10) |
| D-05: Decimal zero normalization | **RESOLVED** | Special case in `_to_serializable` (GAP-05) |
| D-06 to D-14 | **PASS** | No changes needed |

### 11.4 Totality Audit (Final)

All previously non-total functions are now total:

| Function | Was | Now |
|----------|-----|-----|
| `canonical_bytes(obj)` | Raises `TypeError` | Returns `Result[bytes, str]` (GAP-04) |
| `content_hash(obj)` | Raises `TypeError` | Returns `Result[str, str]` (GAP-04) |
| `create_attestation(...)` | Calls raising `content_hash` | Returns `Result[Attestation[T], str]` |
| `FrozenMap.create(items)` | Raises `TypeError` on non-comparable | Returns `Result[FrozenMap, str]` (GAP-08) |

`FrozenMap.__getitem__` still raises `KeyError` (Python `__getitem__` protocol). Domain code must use `.get()`. This is documented and acceptable.

### 11.5 Formal Certification

**APPROVED.** All invariants are stated, assigned to components, and have corresponding tests. Every interface is formally specified. The correctness guarantee (commutativity of the pillar diagram) is testable at Phase 0 scope via the stub pricing engine. No specification gap remains that would prevent formal verification of a critical path.

The build sequence is **complete**, **consistent**, and **implementable**.

---

*End of Pass 4: Final Review, Build Sequence, and Sign-Off.*
*All 41 gaps resolved. All 16 committee members approve. Phase 0 is ready for implementation.*
