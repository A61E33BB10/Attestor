# Phase 0 -- Pass 2: Verification Layer

**Version:** 1.0
**Date:** 2026-02-15
**Authors:** Formalis (Invariant Enforcement), TESTCOMMITTEE (Beck, Hughes, Fowler, Feathers, Lamport)
**Input:** PHASE0_EXECUTION.md (Pass 1), PLAN.md Section 5/8/10, Manifesto

**Scope:** Review and extend Pass 1 with invariant enforcement verification, determinism audit, totality audit, and complete test specification.

---

## 1. Formalis Review

### 1.1 Veto Items (Blockers)

The following items **must be resolved before implementation begins**. Each violates a formally stated invariant.

---

#### V-01: `content_hash` Hashes Only the Value, Not the Full Attestation Identity

**Violated Property:** INV-R05 states `attestation_id = SHA256(canonical_serialize(payload))`. The word "payload" is ambiguous. Currently `create_attestation` computes `h = content_hash(value)` -- hashing only the `value` field.

**Consequence:** Two attestations with the same `value` but different `source`, `timestamp`, `confidence`, or `provenance` receive the same `content_hash`. The `AttestationStore` keys by `content_hash`, so the second attestation is silently dropped. A Firm observation of AAPL=$155.00 from NYSE at 10:00:00 and the same $155.00 from BATS at 10:00:01 would collide.

**Specific Location:** `create_attestation()` in `oracle/attestation.py` (Step 9).

**Required Fix:** Decide and document:
- **Option A (content = value only):** This is a dedup-by-value design. Document that two observations of the same value are intentionally collapsed. Add a `_make_content_hash(value: T) -> str` private function and rename to clarify intent. Add a separate `attestation_id` field that hashes ALL fields to serve as a unique row identifier in the attestation store. Use `attestation_id` as the store key, not `content_hash`.
- **Option B (content = full attestation):** Hash all fields except `content_hash` itself. Two observations of the same value from different sources are distinct attestations with distinct hashes. This is the more conservative interpretation and aligns with INV-O01 (every attestation is independently immutable).

**Recommendation:** Option B. Financial audit trails require that every observation is independently recorded, even if the observed value is the same.

---

#### V-02: Money Arithmetic Does Not Use `ATTESTOR_DECIMAL_CONTEXT`

**Violated Property:** INV-R04 (Reproducibility) -- `Same Attestations + same code version + same DecimalContext = same output`.

**Consequence:** `Money.add()`, `Money.subtract()`, and `Money.multiply()` use Python's thread-local decimal context (whatever `decimal.getcontext()` returns). If two environments have different default contexts (different precision or rounding), arithmetic produces different results. This directly violates reproducibility.

**Specific Location:** `Money.add/subtract/multiply` in `core/money.py` (Step 4).

**Required Fix:**
```python
from decimal import localcontext
from attestor.core.serialization import ATTESTOR_DECIMAL_CONTEXT

def add(self, other: Money) -> Result[Money, str]:
    if self.currency != other.currency:
        return Err(...)
    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        return Ok(Money(amount=self.amount + other.amount, currency=self.currency))
```

Apply to `subtract` and `multiply` as well.

---

#### V-03: Naive Datetimes Permitted in All Temporal Types

**Violated Property:** INV-R04 (Reproducibility) -- a naive `datetime` (no tzinfo) passed to `_serialize_value` triggers `obj.astimezone(timezone.utc)`, which assumes the **local system timezone**. Running the same code in UTC+0 vs UTC+5 produces different canonical serializations, different content hashes, and different attestation identities.

**Specific Location:** `EventTime.value`, `Attestation.timestamp`, `BitemporalEnvelope.event_time/knowledge_time`, `FirmConfidence.timestamp`, `Transaction.timestamp`, `LedgerEntry.timestamp`, `AttestorError.timestamp` -- all typed as bare `datetime`.

**Required Fix:** Add a refined type:
```python
@final
@dataclass(frozen=True, slots=True)
class UtcDatetime:
    """Timezone-aware UTC datetime. Use UtcDatetime.parse()."""
    value: datetime

    @staticmethod
    def parse(raw: datetime) -> Result[UtcDatetime, str]:
        if raw.tzinfo is None:
            return Err("UtcDatetime requires timezone-aware datetime, got naive")
        return Ok(UtcDatetime(value=raw.astimezone(timezone.utc)))
```

Replace `datetime` with `UtcDatetime` in all temporal fields. Alternatively, validate in `_serialize_value` and return an error on naive datetimes (less safe but less invasive).

---

#### V-04: `canonical_bytes` / `_serialize_value` Raise `TypeError` on Unknown Types

**Violated Property:** INV-L10 (Domain Function Totality) -- no domain function raises an exception.

**Consequence:** `create_attestation` calls `content_hash` which calls `canonical_bytes` which calls `_serialize_value`. If any field of the attested value is of an unsupported type, the entire call chain crashes with `TypeError`. This is a `raise` in a critical domain path.

**Specific Location:** `_serialize_value()` line 694 in `core/serialization.py`.

**Required Fix:** Return `Result[bytes, str]` from `canonical_bytes` and `Result[str, str]` from `content_hash`. Propagate to `create_attestation` which should return `Result[Attestation[T], str]`.

```python
def canonical_bytes(obj: object) -> Result[bytes, str]:
    try:
        serialized = _serialize_value(obj)
    except TypeError as e:
        return Err(str(e))
    return Ok(json.dumps(...).encode("utf-8"))

def create_attestation(...) -> Result[Attestation[T], str]:
    match content_hash(value):
        case Err(e): return Err(f"Cannot hash value: {e}")
        case Ok(h): return Ok(Attestation(..., content_hash=h))
```

---

### 1.2 Invariant Enforcement Matrix

| Invariant ID | Formal Statement | Enforced By | Enforcement Type | Gap? |
|---|---|---|---|---|
| INV-O01 | `frozen=True, slots=True` on all attestation/domain types; append-only stores | `@final @dataclass(frozen=True, slots=True)` on every type; CI frozen-check script; `prevent_mutation()` trigger on Postgres | Type system + CI scan + DB trigger | **None** |
| INV-O03 | Every Derived attestation references input attestation hashes; DAG is closed | `provenance: tuple[str, ...]` field on `Attestation`; `test_full_provenance_chain_walkable` integration test | Runtime test (DAG closure not enforced by type system) | **Gap: No compile-time enforcement.** A Derived attestation can be created with empty `provenance=()`. Consider: factory function `create_derived_attestation` that requires non-empty provenance. |
| INV-O04 | Every attestation carries exactly one of Firm, Quoted, Derived | `Confidence = FirmConfidence \| QuotedConfidence \| DerivedConfidence` (union type); `@final` on each variant | Type system (compile-time via mypy) | **None** |
| INV-O05 | Firm attestation carries: source, timestamp, attestation_ref | `FirmConfidence` dataclass with required fields (no defaults) | Type system | **Minor gap:** Fields accept empty strings. `source: str` and `attestation_ref: str` should use `NonEmptyStr`. `timestamp` should be `UtcDatetime` per V-03. |
| INV-O06 | Quoted carries: bid, ask, mid, spread, venue | `QuotedConfidence` has `bid, ask, venue` but **no `mid` or `spread` fields** | Type system (partial) | **Gap: PLAN requires `mid` and `spread` but Pass 1 omits them.** Either add computed properties `@property def mid`, `@property def spread` or add fields. See Section 3. |
| INV-O07 | Derived carries: method, config_ref, fit_quality, confidence_interval, confidence_level | `DerivedConfidence` has all 5 fields. `confidence_interval` and `confidence_level` are `Optional` | Type system (partial) | **Gap: PLAN says "carries" implying required, but Pass 1 makes them optional (`\| None`).** A Derived attestation without uncertainty bounds violates epistemic honesty. Consider making them required or adding a validation factory. |
| INV-R04 | Same inputs + same code version + same DecimalContext = same output | `ATTESTOR_DECIMAL_CONTEXT` (fixed); `FrozenMap` sorted entries; `canonical_bytes` with sorted keys | Determinism policy + convention | **VETO V-02, V-03:** Money arithmetic doesn't use the context; naive datetimes introduce platform dependence. |
| INV-R05 | `attestation_id = SHA256(canonical_serialize(payload))` | `content_hash()` -> SHA-256 of `canonical_bytes()`; `canonical_bytes()` sorts keys, normalizes Decimals | Code (runtime) | **VETO V-01:** Ambiguous scope of "payload" -- currently hashes value only, not full attestation. |
| INV-X03 | `f(f(x)) = f(x)` for idempotent operations | `InMemoryAttestationStore.store()` checks hash existence before insert; Postgres `ON CONFLICT DO NOTHING` | Runtime (store logic) | **None** |
| INV-L05 | Transaction either fully applies or fully rejects | `Transaction.moves: tuple[Move, ...]` is frozen; no partial modification possible | Type system (immutability of Transaction) | **None** (full enforcement requires ledger engine in Phase 1) |
| INV-L10 | No domain function raises an exception | `Result`-returning factories; `@final` dataclasses with no `__post_init__` raises | Convention + CI AST scan (`test_inv_l10_no_raise_in_domain`) | **VETO V-04:** `_serialize_value` raises `TypeError`; `FrozenMap.__getitem__` raises `KeyError`. Also: `AttestationStore.exists()` returns `bool` not `Result[bool, PersistenceError]` -- production Postgres adapter may raise connection errors. Module-level `unwrap()` helper raises `RuntimeError` on `Err` (documented as test-only, but still a domain export). |
| INV-P05 | Content-addressed IDs in Postgres | `content_hash TEXT PRIMARY KEY` on `attestor.attestations` table | Database schema | **None** |
| INV-P06 | Append-only attestation tables | `prevent_mutation()` trigger rejects UPDATE/DELETE | Database trigger | **None** |

---

### 1.3 Determinism Audit

| # | Finding | Location | Severity | Detail |
|---|---------|----------|----------|--------|
| D-01 | Money arithmetic uses thread-local decimal context | `Money.add/subtract/multiply` | **VETO** (= V-02) | Results depend on `decimal.getcontext()`, which is thread-local and environment-dependent |
| D-02 | Naive datetimes allowed in all temporal fields | `EventTime`, `Attestation.timestamp`, `BitemporalEnvelope`, `Transaction.timestamp`, `LedgerEntry.timestamp` | **VETO** (= V-03) | `astimezone(timezone.utc)` on naive datetime assumes local timezone |
| D-03 | `FrozenMap.create` sorts by key -- requires comparable keys | `FrozenMap.create()` | HIGH | `sorted(items, key=lambda kv: kv[0])` raises `TypeError` if keys are not orderable. With `ATTESTOR_DECIMAL_CONTEXT` trapping `InvalidOperation`, a `Decimal("NaN")` key also raises. Totality violation (INV-L10). |
| D-04 | `FrozenMap.create` silently accepts duplicate keys from Iterable input | `FrozenMap.create()` | **HIGH** | If input is `Iterable[tuple[K,V]]` with duplicate keys (e.g., `[("a",1), ("a",2)]`), both entries are stored. `get("a")` returns the first match via linear scan, but `items()` returns both. Two FrozenMaps semantically equal but constructed with different duplicate orderings produce different `canonical_bytes`, violating INV-R05 (content-addressing determinism). |
| D-05 | `Decimal` zero normalization is not canonical | `_serialize_value` | **MEDIUM** | `Decimal("0").normalize()` -> `"0"` but `Decimal("0E+2").normalize()` -> `"0E+2"`. `str()` of these are different (`"0"` vs `"0E+2"`), so two representations of zero produce different serializations and therefore different content hashes. Fix: special-case zero after `normalize()` -- `if obj == 0: return "0"`. |
| D-06 | No `dict` fields in domain types | All domain types | **PASS** | All mappings use `FrozenMap` with sorted tuples. |
| D-07 | No `set` usage in domain types | All domain types | **PASS** | No `set` or `frozenset` in any type definition. |
| D-08 | No `hash()` dependence for cross-process identity | Content addressing | **PASS** | SHA-256 of canonical JSON bytes used for identity, not Python `hash()`. |
| D-09 | No `float` in domain types | All domain types | **PASS** | CI script scans for `: float` annotations. All numeric fields are `Decimal`. |
| D-10 | `Decimal.normalize()` idempotent for non-zero values | `_serialize_value` | **PASS** | `str(Decimal("1.50").normalize())` -> `"1.5"` consistently. (See D-05 for zero edge case.) |
| D-11 | JSON serialization with sorted keys | `canonical_bytes` | **PASS** | `json.dumps(sort_keys=True, separators=(",",":"))` is deterministic. |
| D-12 | `_serialize_value` adds `_type` discriminator using `type(obj).__name__` | `_serialize_value` | LOW | Class renaming would change all content hashes. Document this as an invariant: type names are part of the canonical serialization contract and must never change. |
| D-13 | `derive_seed` sorts attestation refs | `derive_seed()` | **PASS** | `sorted_refs = tuple(sorted(attestation_refs))` ensures order independence. |
| D-14 | `InMemoryAttestationStore/EventBus/etc.` use mutable `dict`/`list` internally | `infra/memory_adapter.py` | **ACCEPTABLE** | These are test doubles at the infrastructure boundary, not domain types. Production adapters (Kafka/Postgres) provide their own ordering guarantees. |

---

### 1.4 Totality Audit

Every public function is checked: is it total over its declared input types?

| Function | Total? | Issue | Severity |
|---|---|---|---|
| `Ok.map(f)` | **Yes** (assuming `f` is total) | If `f` raises, `map` raises. Caller's responsibility. | -- |
| `Ok.bind(f)` | **Yes** (same caveat) | -- | -- |
| `Ok.unwrap()` | **Yes** on `Ok` | Not defined on `Err` -- this is by design (mypy catches) | -- |
| `Err.map(f)` | **Yes** | Returns `self`, ignores `f` | -- |
| `Err.bind(f)` | **Yes** | Returns `self`, ignores `f` | -- |
| `FrozenMap.create(items)` | **No** | `sorted()` raises `TypeError` if keys aren't comparable | MEDIUM |
| `FrozenMap.get(key, default)` | **Yes** | Linear scan, returns default | -- |
| `FrozenMap.__getitem__(key)` | **No** | Raises `KeyError` for missing keys | HIGH (but Python `__getitem__` protocol requires this) |
| `FrozenMap.to_dict()` | **Yes** | `dict(self._entries)` always succeeds | -- |
| `PositiveDecimal.parse(raw)` | **Yes** | Returns `Result` for all inputs | -- |
| `NonZeroDecimal.parse(raw)` | **Yes** | Returns `Result` for all inputs | -- |
| `NonEmptyStr.parse(raw)` | **Yes** | Returns `Result` for all inputs | -- |
| `IdempotencyKey.create(raw)` | **Yes** | Returns `Result` via `NonEmptyStr.parse` | -- |
| `Money.create(amount, currency)` | **Yes** | Returns `Result` for all inputs | -- |
| `Money.add(other)` | **Yes** | Returns `Result` (Err on currency mismatch) | -- |
| `Money.subtract(other)` | **Yes** | Returns `Result` (Err on currency mismatch) | -- |
| `Money.multiply(factor)` | **Yes** | Returns `Money` directly | -- |
| `Money.negate()` | **Yes** | Returns `Money` directly | -- |
| `DistinctAccountPair.create(d, c)` | **Yes** | Returns `Result` (Err on same/empty) | -- |
| `canonical_bytes(obj)` | **No** | Delegates to `_serialize_value` which raises `TypeError` | **HIGH** (= V-04) |
| `content_hash(obj)` | **No** | Delegates to `canonical_bytes` | **HIGH** (= V-04) |
| `derive_seed(refs, version)` | **Yes** | Pure function: sort, serialize, hash | -- |
| `create_attestation(...)` | **No** | Calls `content_hash` which can raise | **HIGH** (= V-04) |
| `EventBus.publish(...)` | **Yes** | Returns `Result` | -- |
| `AttestationStore.store(...)` | **Yes** | Returns `Result` | -- |
| `AttestationStore.retrieve(...)` | **Yes** | Returns `Result` (Err if not found) | -- |
| `TransactionLog.append(...)` | **Yes** | Returns `Result` | -- |
| `TransactionLog.replay(...)` | **Yes** | Returns `Result` | -- |
| `StateStore.get(...)` | **Yes** | Returns `Result[bytes \| None, ...]` | -- |
| `StateStore.put(...)` | **Yes** | Returns `Result` | -- |

**Summary:** 4 non-total functions identified, all rooted in V-04 (`_serialize_value` raises). One dunder method (`__getitem__`) raises by Python protocol convention -- acceptable but `.get()` should always be preferred in domain code.

---

## 2. Test Catalogue

## 2.1 Hypothesis Strategies (conftest.py)

The following `conftest.py` provides composable Hypothesis strategies for every Phase 0
domain type. Complex strategies are built from simpler ones. Edge cases (boundary
values, empty collections, None optionals) are covered by construction.

```python
"""Hypothesis strategies and pytest fixtures for Attestor Phase 0.

Every Phase 0 domain type has a corresponding Hypothesis strategy.
Strategies are composable: complex types are built from simpler types.
Edge cases (boundaries, empty collections, None optionals) are woven
into every generator -- they are not afterthoughts.

Usage in tests:
    from conftest import money, attestations, ledger_entries
    @given(m=money())
    def test_money_property(m): ...
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

import pytest
from hypothesis import strategies as st, settings, HealthCheck
from hypothesis.strategies import SearchStrategy

# ---------------------------------------------------------------------------
# Imports from attestor (all Phase 0 types)
# ---------------------------------------------------------------------------

from attestor.core.result import Ok, Err, Result, unwrap, map_result
from attestor.core.types import (
    FrozenMap,
    BitemporalEnvelope,
    IdempotencyKey,
    EventTime,
)
from attestor.core.money import (
    Money,
    PositiveDecimal,
    NonZeroDecimal,
    NonEmptyStr,
    ATTESTOR_DECIMAL_CONTEXT,
)
from attestor.core.errors import (
    AttestorError,
    FieldViolation,
    ValidationError,
    IllegalTransitionError,
    ConservationViolationError,
    MissingObservableError,
    CalibrationError,
    PricingError,
    PersistenceError,
)
from attestor.core.serialization import canonical_bytes, content_hash
from attestor.core.identifiers import LEI, UTI, ISIN
from attestor.oracle.attestation import (
    Attestation,
    FirmConfidence,
    QuotedConfidence,
    DerivedConfidence,
    Confidence,
    create_attestation,
)
from attestor.ledger.transactions import (
    DeltaDecimal,
    DeltaStr,
    DeltaBool,
    DeltaDate,
    DeltaDatetime,
    DeltaNull,
    DeltaValue,
    StateDelta,
    DistinctAccountPair,
    Move,
    Transaction,
    Account,
    AccountType,
    Position,
    LedgerEntry,
    ExecuteResult,
)
from attestor.pricing.types import (
    ValuationResult,
    Greeks,
    Scenario,
    ScenarioResult,
    VaRResult,
    PnLAttribution,
)
from attestor.pricing.protocols import PricingEngine, RiskEngine, StubPricingEngine
from attestor.infra.protocols import (
    EventBus,
    AttestationStore,
    TransactionLog,
    StateStore,
)
from attestor.infra.memory_adapter import (
    InMemoryEventBus,
    InMemoryAttestationStore,
    InMemoryTransactionLog,
    InMemoryStateStore,
)
from attestor.infra.config import PHASE0_TOPICS, TopicConfig, phase0_topic_configs


# ---------------------------------------------------------------------------
# Hypothesis global settings
# ---------------------------------------------------------------------------

settings.register_profile(
    "ci",
    max_examples=200,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
settings.register_profile(
    "dev",
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
settings.load_profile("dev")


# ===================================================================
# PRIMITIVE STRATEGIES
# ===================================================================

def finite_decimals(
    min_value: str = "-1000000",
    max_value: str = "1000000",
    places: int = 6,
) -> SearchStrategy[Decimal]:
    """Finite Decimal values, no NaN, no Infinity, no sNaN."""
    return st.decimals(
        min_value=Decimal(min_value),
        max_value=Decimal(max_value),
        places=places,
        allow_nan=False,
        allow_infinity=False,
    )


def positive_decimals(
    min_value: str = "0.000001",
    max_value: str = "1000000",
    places: int = 6,
) -> SearchStrategy[Decimal]:
    """Strictly positive Decimal values."""
    return st.decimals(
        min_value=Decimal(min_value),
        max_value=Decimal(max_value),
        places=places,
        allow_nan=False,
        allow_infinity=False,
    ).filter(lambda d: d > 0)


def nonzero_decimals(
    min_value: str = "-1000000",
    max_value: str = "1000000",
    places: int = 6,
) -> SearchStrategy[Decimal]:
    """Non-zero Decimal values."""
    return finite_decimals(min_value, max_value, places).filter(lambda d: d != 0)


def aware_datetimes(
    min_year: int = 2020,
    max_year: int = 2030,
) -> SearchStrategy[datetime]:
    """Timezone-aware UTC datetimes."""
    return st.datetimes(
        min_value=datetime(min_year, 1, 1),
        max_value=datetime(max_year, 12, 31, 23, 59, 59),
        timezones=st.just(timezone.utc),
    )


def dates_strategy(
    min_year: int = 2020,
    max_year: int = 2030,
) -> SearchStrategy[date]:
    """date objects for DeltaDate."""
    return st.dates(
        min_value=date(min_year, 1, 1),
        max_value=date(max_year, 12, 31),
    )


def nonempty_text(
    min_size: int = 1,
    max_size: int = 50,
) -> SearchStrategy[str]:
    """Non-empty printable ASCII strings (stripped)."""
    return st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
        min_size=min_size,
        max_size=max_size,
    ).map(str.strip).filter(bool)


CURRENCIES = ("USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "SEK")

def currency_codes() -> SearchStrategy[str]:
    """ISO 4217-ish currency codes."""
    return st.sampled_from(CURRENCIES)


# ===================================================================
# CORE TYPE STRATEGIES
# ===================================================================

# --- Result[T, E] ---

@st.composite
def ok_results(draw: st.DrawFn, value_strategy: SearchStrategy[Any] = st.integers()) -> Ok[Any]:
    """Generate Ok(...) wrapping an arbitrary value."""
    return Ok(draw(value_strategy))


@st.composite
def err_results(draw: st.DrawFn, error_strategy: SearchStrategy[Any] = nonempty_text()) -> Err[Any]:
    """Generate Err(...) wrapping an arbitrary error."""
    return Err(draw(error_strategy))


@st.composite
def results(draw: st.DrawFn) -> Result[int, str]:
    """Generate either Ok(int) or Err(str)."""
    if draw(st.booleans()):
        return Ok(draw(st.integers(min_value=-1000, max_value=1000)))
    return Err(draw(nonempty_text()))


# --- NonEmptyStr ---

@st.composite
def non_empty_strs(draw: st.DrawFn) -> NonEmptyStr:
    """Generate valid NonEmptyStr instances."""
    raw = draw(nonempty_text())
    result = NonEmptyStr.parse(raw)
    assert isinstance(result, Ok)
    return result.value


# --- PositiveDecimal ---

@st.composite
def positive_decimal_values(draw: st.DrawFn) -> PositiveDecimal:
    """Generate valid PositiveDecimal instances."""
    raw = draw(positive_decimals())
    result = PositiveDecimal.parse(raw)
    assert isinstance(result, Ok)
    return result.value


# --- NonZeroDecimal ---

@st.composite
def nonzero_decimal_values(draw: st.DrawFn) -> NonZeroDecimal:
    """Generate valid NonZeroDecimal instances."""
    raw = draw(nonzero_decimals())
    result = NonZeroDecimal.parse(raw)
    assert isinstance(result, Ok)
    return result.value


# --- FrozenMap[K, V] ---

@st.composite
def frozen_maps(
    draw: st.DrawFn,
    keys: SearchStrategy[str] = nonempty_text(max_size=10),
    values: SearchStrategy[Any] = st.integers(min_value=-100, max_value=100),
    min_size: int = 0,
    max_size: int = 10,
) -> FrozenMap[str, Any]:
    """Generate FrozenMap with sorted, unique keys."""
    entries = draw(
        st.dictionaries(keys, values, min_size=min_size, max_size=max_size)
    )
    return FrozenMap.create(entries)


@st.composite
def frozen_maps_str_decimal(
    draw: st.DrawFn,
    min_size: int = 0,
    max_size: int = 5,
) -> FrozenMap[str, Decimal]:
    """Generate FrozenMap[str, Decimal] -- used by DerivedConfidence.fit_quality."""
    entries = draw(
        st.dictionaries(
            nonempty_text(max_size=10),
            finite_decimals(min_value="0", max_value="1", places=4),
            min_size=min_size,
            max_size=max_size,
        )
    )
    return FrozenMap.create(entries)


# --- Money ---

@st.composite
def money(draw: st.DrawFn) -> Money:
    """Generate valid Money instances."""
    amount = draw(finite_decimals(min_value="-1000000", max_value="1000000", places=2))
    cur = draw(currency_codes())
    result = Money.create(amount, cur)
    assert isinstance(result, Ok)
    return result.value


@st.composite
def money_same_currency(
    draw: st.DrawFn,
    currency: str = "USD",
) -> tuple[Money, Money]:
    """Generate a pair of Money values with the same currency."""
    a1 = draw(finite_decimals(min_value="-1000000", max_value="1000000", places=2))
    a2 = draw(finite_decimals(min_value="-1000000", max_value="1000000", places=2))
    r1 = Money.create(a1, currency)
    r2 = Money.create(a2, currency)
    assert isinstance(r1, Ok) and isinstance(r2, Ok)
    return r1.value, r2.value


# --- IdempotencyKey ---

@st.composite
def idempotency_keys(draw: st.DrawFn) -> IdempotencyKey:
    """Generate valid IdempotencyKey instances."""
    raw = draw(nonempty_text())
    result = IdempotencyKey.create(raw)
    assert isinstance(result, Ok)
    return result.value


# --- EventTime ---

@st.composite
def event_times(draw: st.DrawFn) -> EventTime:
    """Generate EventTime wrapping a UTC datetime."""
    dt = draw(aware_datetimes())
    return EventTime(value=dt)


# --- BitemporalEnvelope ---

@st.composite
def bitemporal_envelopes(
    draw: st.DrawFn,
    payload_strategy: SearchStrategy[Any] = st.integers(),
) -> BitemporalEnvelope[Any]:
    """Generate BitemporalEnvelope with UTC timestamps."""
    payload = draw(payload_strategy)
    event_time = draw(aware_datetimes())
    knowledge_time = draw(aware_datetimes())
    return BitemporalEnvelope(
        payload=payload,
        event_time=event_time,
        knowledge_time=knowledge_time,
    )


# ===================================================================
# ERROR TYPE STRATEGIES
# ===================================================================

@st.composite
def field_violations(draw: st.DrawFn) -> FieldViolation:
    """Generate FieldViolation instances."""
    return FieldViolation(
        path=draw(nonempty_text(max_size=30)),
        constraint=draw(nonempty_text(max_size=50)),
        actual_value=draw(nonempty_text(max_size=20)),
    )


@st.composite
def attestor_errors(draw: st.DrawFn) -> AttestorError:
    """Generate base AttestorError instances."""
    return AttestorError(
        message=draw(nonempty_text()),
        code=draw(st.sampled_from(["E001", "E002", "E100", "E200"])),
        timestamp=draw(aware_datetimes()),
        source=draw(nonempty_text(max_size=40)),
    )


@st.composite
def validation_errors(draw: st.DrawFn) -> ValidationError:
    """Generate ValidationError with 1-5 FieldViolations."""
    base = draw(attestor_errors())
    fields = draw(st.lists(field_violations(), min_size=1, max_size=5))
    return ValidationError(
        message=base.message,
        code="VALIDATION",
        timestamp=base.timestamp,
        source=base.source,
        fields=tuple(fields),
    )


@st.composite
def persistence_errors(draw: st.DrawFn) -> PersistenceError:
    """Generate PersistenceError."""
    base = draw(attestor_errors())
    return PersistenceError(
        message=base.message,
        code="PERSISTENCE",
        timestamp=base.timestamp,
        source=base.source,
        operation=draw(st.sampled_from(["store", "retrieve", "append", "replay"])),
    )


@st.composite
def pricing_errors(draw: st.DrawFn) -> PricingError:
    """Generate PricingError."""
    base = draw(attestor_errors())
    return PricingError(
        message=base.message,
        code="PRICING",
        timestamp=base.timestamp,
        source=base.source,
        instrument=draw(nonempty_text(max_size=20)),
        reason=draw(nonempty_text(max_size=50)),
    )


# ===================================================================
# CONFIDENCE STRATEGIES
# ===================================================================

@st.composite
def firm_confidences(draw: st.DrawFn) -> FirmConfidence:
    """Generate FirmConfidence with all required fields."""
    return FirmConfidence(
        source=draw(st.sampled_from(["NYSE", "LCH", "ICE", "CME", "Eurex"])),
        timestamp=draw(aware_datetimes()),
        attestation_ref=draw(
            st.text(
                alphabet="0123456789abcdef",
                min_size=64,
                max_size=64,
            )
        ),
    )


@st.composite
def quoted_confidences(draw: st.DrawFn) -> QuotedConfidence:
    """Generate QuotedConfidence with bid <= ask."""
    bid = draw(positive_decimals(min_value="0.01", max_value="999999", places=4))
    spread = draw(positive_decimals(min_value="0.0001", max_value="10", places=4))
    ask = bid + spread
    size = draw(st.one_of(st.none(), positive_decimals(max_value="10000", places=0)))
    return QuotedConfidence(
        bid=bid,
        ask=ask,
        venue=draw(st.sampled_from(["Bloomberg", "ICE", "Reuters", "BGC"])),
        size=size,
        conditions=draw(st.sampled_from(["Indicative", "Firm", "RFQ"])),
    )


@st.composite
def derived_confidences(draw: st.DrawFn) -> DerivedConfidence:
    """Generate DerivedConfidence with fit_quality as FrozenMap."""
    fq = draw(frozen_maps_str_decimal(min_size=1, max_size=3))
    has_ci = draw(st.booleans())
    if has_ci:
        lower = draw(finite_decimals(min_value="0", max_value="100", places=4))
        upper = lower + draw(positive_decimals(min_value="0.001", max_value="50", places=4))
        ci = (lower, upper)
    else:
        ci = None
    cl = draw(st.one_of(
        st.none(),
        st.sampled_from([Decimal("0.90"), Decimal("0.95"), Decimal("0.99")]),
    ))
    return DerivedConfidence(
        method=draw(st.sampled_from(["BlackScholes", "SVI", "GPRegression", "SABR"])),
        config_ref=draw(
            st.text(alphabet="0123456789abcdef", min_size=64, max_size=64)
        ),
        fit_quality=fq,
        confidence_interval=ci,
        confidence_level=cl,
    )


@st.composite
def confidences(draw: st.DrawFn) -> Confidence:
    """Generate exactly one Confidence variant (Firm | Quoted | Derived)."""
    return draw(st.one_of(
        firm_confidences(),
        quoted_confidences(),
        derived_confidences(),
    ))


# ===================================================================
# ATTESTATION STRATEGIES
# ===================================================================

@st.composite
def attestations(
    draw: st.DrawFn,
    value_strategy: SearchStrategy[Any] | None = None,
) -> Attestation[Any]:
    """Generate Attestation[T] via create_attestation factory.

    Defaults to wrapping Decimal values. Pass value_strategy to customise.
    """
    if value_strategy is None:
        value_strategy = finite_decimals()
    value = draw(value_strategy)
    confidence = draw(confidences())
    source = draw(nonempty_text(max_size=30))
    timestamp = draw(aware_datetimes())
    num_provenance = draw(st.integers(min_value=0, max_value=3))
    provenance = tuple(
        draw(st.text(alphabet="0123456789abcdef", min_size=64, max_size=64))
        for _ in range(num_provenance)
    )
    return create_attestation(
        value=value,
        confidence=confidence,
        source=source,
        timestamp=timestamp,
        provenance=provenance,
    )


@st.composite
def firm_attestations(
    draw: st.DrawFn,
    value_strategy: SearchStrategy[Any] | None = None,
) -> Attestation[Any]:
    """Generate Attestation with FirmConfidence."""
    if value_strategy is None:
        value_strategy = finite_decimals()
    return create_attestation(
        value=draw(value_strategy),
        confidence=draw(firm_confidences()),
        source=draw(nonempty_text(max_size=30)),
        timestamp=draw(aware_datetimes()),
        provenance=(),
    )


@st.composite
def derived_attestations(
    draw: st.DrawFn,
    provenance_hashes: tuple[str, ...] = (),
) -> Attestation[Any]:
    """Generate Attestation with DerivedConfidence and explicit provenance."""
    return create_attestation(
        value=draw(finite_decimals()),
        confidence=draw(derived_confidences()),
        source=draw(nonempty_text(max_size=30)),
        timestamp=draw(aware_datetimes()),
        provenance=provenance_hashes,
    )


# ===================================================================
# LEDGER TYPE STRATEGIES
# ===================================================================

# --- DeltaValue (6 variants) ---

@st.composite
def delta_decimals(draw: st.DrawFn) -> DeltaDecimal:
    return DeltaDecimal(value=draw(finite_decimals()))

@st.composite
def delta_strs(draw: st.DrawFn) -> DeltaStr:
    return DeltaStr(value=draw(st.text(min_size=0, max_size=30)))

@st.composite
def delta_bools(draw: st.DrawFn) -> DeltaBool:
    return DeltaBool(value=draw(st.booleans()))

@st.composite
def delta_dates(draw: st.DrawFn) -> DeltaDate:
    return DeltaDate(value=draw(dates_strategy()))

@st.composite
def delta_datetimes(draw: st.DrawFn) -> DeltaDatetime:
    return DeltaDatetime(value=draw(aware_datetimes()))

@st.composite
def delta_nulls(draw: st.DrawFn) -> DeltaNull:
    return DeltaNull()

@st.composite
def delta_values(draw: st.DrawFn) -> DeltaValue:
    """Generate any of the 6 DeltaValue variants."""
    return draw(st.one_of(
        delta_decimals(),
        delta_strs(),
        delta_bools(),
        delta_dates(),
        delta_datetimes(),
        delta_nulls(),
    ))


# --- StateDelta ---

@st.composite
def state_deltas(draw: st.DrawFn) -> StateDelta:
    """Generate StateDelta with typed old/new values."""
    return StateDelta(
        unit=draw(nonempty_text(max_size=15)),
        field=draw(nonempty_text(max_size=15)),
        old_value=draw(delta_values()),
        new_value=draw(delta_values()),
    )


# --- DistinctAccountPair ---

ACCOUNT_IDS = (
    "trading_desk_A", "trading_desk_B", "settlement_pool",
    "collateral_vault", "margin_account", "pnl_realized",
    "accrual_interest", "suspense_holding", "treasury",
)

@st.composite
def distinct_account_pairs(draw: st.DrawFn) -> DistinctAccountPair:
    """Generate DistinctAccountPair where debit != credit."""
    ids = draw(
        st.lists(
            st.sampled_from(ACCOUNT_IDS),
            min_size=2,
            max_size=2,
            unique=True,
        )
    )
    result = DistinctAccountPair.create(ids[0], ids[1])
    assert isinstance(result, Ok)
    return result.value


# --- Account ---

@st.composite
def accounts(draw: st.DrawFn) -> Account:
    """Generate Account with valid AccountType."""
    return Account(
        account_id=draw(st.sampled_from(ACCOUNT_IDS)),
        account_type=draw(st.sampled_from(list(AccountType))),
    )


# --- Move ---

@st.composite
def moves(draw: st.DrawFn) -> Move:
    """Generate Move with PositiveDecimal quantity."""
    src, dst = draw(
        st.lists(st.sampled_from(ACCOUNT_IDS), min_size=2, max_size=2, unique=True)
    )
    return Move(
        source=src,
        destination=dst,
        unit=draw(st.sampled_from(["USD", "AAPL", "MSFT", "OPT_AAPL_150"])),
        quantity=draw(positive_decimal_values()),
        contract_id=draw(nonempty_text(max_size=20)),
    )


# --- Transaction ---

@st.composite
def transactions(draw: st.DrawFn) -> Transaction:
    """Generate Transaction with 1-5 moves."""
    mvs = draw(st.lists(moves(), min_size=1, max_size=5))
    deltas = draw(st.lists(state_deltas(), min_size=0, max_size=3))
    return Transaction(
        tx_id=draw(nonempty_text(max_size=20)),
        moves=tuple(mvs),
        timestamp=draw(aware_datetimes()),
        state_deltas=tuple(deltas),
    )


# --- Position ---

@st.composite
def positions(draw: st.DrawFn) -> Position:
    """Generate Position."""
    return Position(
        account=draw(st.sampled_from(ACCOUNT_IDS)),
        instrument=draw(st.sampled_from(["AAPL", "MSFT", "USD", "EUR"])),
        quantity=draw(finite_decimals()),
    )


# --- LedgerEntry ---

@st.composite
def ledger_entries(draw: st.DrawFn) -> LedgerEntry:
    """Generate LedgerEntry with valid DistinctAccountPair and PositiveDecimal amount."""
    pair = draw(distinct_account_pairs())
    amount = draw(positive_decimal_values())
    ts = draw(aware_datetimes())
    has_attestation = draw(st.booleans())
    att = draw(attestations()) if has_attestation else None
    return LedgerEntry(
        accounts=pair,
        instrument=draw(st.sampled_from(["AAPL", "MSFT", "USD"])),
        amount=amount,
        timestamp=ts,
        attestation=att,
    )


# ===================================================================
# PRICING TYPE STRATEGIES
# ===================================================================

@st.composite
def valuation_results(draw: st.DrawFn) -> ValuationResult:
    """Generate ValuationResult."""
    components = draw(frozen_maps_str_decimal(max_size=4))
    return ValuationResult(
        instrument_id=draw(nonempty_text(max_size=20)),
        npv=draw(finite_decimals()),
        currency=draw(currency_codes()),
        components=components,
        model_config_id=draw(nonempty_text(max_size=30)),
        market_snapshot_id=draw(nonempty_text(max_size=30)),
    )


@st.composite
def greeks_values(draw: st.DrawFn) -> Greeks:
    """Generate Greeks with all fields."""
    d = lambda: draw(finite_decimals(min_value="-10", max_value="10", places=8))
    return Greeks(
        delta=d(), gamma=d(), vega=d(), theta=d(), rho=d(),
        vanna=d(), volga=d(), charm=d(),
    )


@st.composite
def scenarios(draw: st.DrawFn) -> Scenario:
    """Generate Scenario via factory."""
    overrides_dict = draw(
        st.dictionaries(
            nonempty_text(max_size=15),
            finite_decimals(min_value="-100", max_value="100", places=4),
            min_size=1,
            max_size=5,
        )
    )
    return Scenario.create(
        label=draw(nonempty_text(max_size=20)),
        overrides=overrides_dict,
        base_snapshot_id=draw(nonempty_text(max_size=30)),
    )


@st.composite
def scenario_results(draw: st.DrawFn) -> ScenarioResult:
    """Generate ScenarioResult."""
    base = draw(finite_decimals())
    stressed = draw(finite_decimals())
    return ScenarioResult(
        scenario_label=draw(nonempty_text(max_size=20)),
        base_npv=base,
        stressed_npv=stressed,
        pnl_impact=stressed - base,
        instrument_impacts=draw(frozen_maps_str_decimal(max_size=3)),
    )


@st.composite
def var_results(draw: st.DrawFn) -> VaRResult:
    """Generate VaRResult."""
    return VaRResult(
        confidence_level=draw(
            st.sampled_from([Decimal("0.95"), Decimal("0.99"), Decimal("0.999")])
        ),
        horizon_days=draw(st.sampled_from([1, 5, 10, 21])),
        var_amount=draw(positive_decimals(max_value="100000", places=2)),
        currency=draw(currency_codes()),
        method=draw(st.sampled_from(["HistoricalSimulation", "MonteCarlo", "Parametric"])),
        component_var=draw(frozen_maps_str_decimal(max_size=5)),
    )


@st.composite
def pnl_attributions(draw: st.DrawFn) -> PnLAttribution:
    """Generate PnLAttribution where total = market + carry + trade + residual."""
    market = draw(finite_decimals(min_value="-10000", max_value="10000", places=2))
    carry = draw(finite_decimals(min_value="-10000", max_value="10000", places=2))
    trade = draw(finite_decimals(min_value="-10000", max_value="10000", places=2))
    residual = draw(finite_decimals(min_value="-10000", max_value="10000", places=2))
    total = market + carry + trade + residual
    return PnLAttribution(
        total_pnl=total,
        market_pnl=market,
        carry_pnl=carry,
        trade_pnl=trade,
        residual_pnl=residual,
        currency=draw(currency_codes()),
    )


# ===================================================================
# INFRASTRUCTURE STRATEGIES
# ===================================================================

@st.composite
def topic_configs(draw: st.DrawFn) -> TopicConfig:
    """Generate TopicConfig."""
    return TopicConfig(
        name=draw(nonempty_text(max_size=30)),
        partitions=draw(st.integers(min_value=1, max_value=64)),
        retention_ms=draw(st.sampled_from([-1, 86400000, 2592000000])),
        compaction=draw(st.booleans()),
    )


# ===================================================================
# IDENTIFIER STRATEGIES
# ===================================================================

@st.composite
def valid_leis(draw: st.DrawFn) -> LEI:
    """Generate valid 20-character alphanumeric LEI strings."""
    raw = draw(
        st.text(
            alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            min_size=20,
            max_size=20,
        )
    )
    result = LEI.parse(raw)
    assert isinstance(result, Ok)
    return result.value


# Known-good ISINs for testing (pre-validated check digits)
KNOWN_ISINS = ["US0378331005", "US5949181045", "GB0002634946", "DE0007236101"]

@st.composite
def valid_isins(draw: st.DrawFn) -> ISIN:
    """Generate from known-valid ISINs."""
    raw = draw(st.sampled_from(KNOWN_ISINS))
    result = ISIN.parse(raw)
    assert isinstance(result, Ok)
    return result.value


# ===================================================================
# COMPOSITE / INTEGRATION STRATEGIES
# ===================================================================

@st.composite
def bitemporal_transactions(draw: st.DrawFn) -> BitemporalEnvelope[Transaction]:
    """Generate BitemporalEnvelope wrapping a Transaction."""
    tx = draw(transactions())
    return BitemporalEnvelope(
        payload=tx,
        event_time=draw(aware_datetimes()),
        knowledge_time=draw(aware_datetimes()),
    )


# ===================================================================
# PYTEST FIXTURES (non-Hypothesis)
# ===================================================================

@pytest.fixture
def attestation_store() -> InMemoryAttestationStore:
    """Fresh in-memory attestation store."""
    return InMemoryAttestationStore()


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    """Fresh in-memory event bus."""
    return InMemoryEventBus()


@pytest.fixture
def transaction_log() -> InMemoryTransactionLog:
    """Fresh in-memory transaction log."""
    return InMemoryTransactionLog()


@pytest.fixture
def state_store() -> InMemoryStateStore:
    """Fresh in-memory state store."""
    return InMemoryStateStore()


@pytest.fixture
def sample_firm_confidence() -> FirmConfidence:
    """A fixed FirmConfidence for deterministic tests."""
    return FirmConfidence(
        source="NYSE",
        timestamp=datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        attestation_ref="a" * 64,
    )


@pytest.fixture
def sample_quoted_confidence() -> QuotedConfidence:
    """A fixed QuotedConfidence for deterministic tests."""
    return QuotedConfidence(
        bid=Decimal("154.90"),
        ask=Decimal("155.10"),
        venue="Bloomberg",
        size=Decimal("100"),
        conditions="Firm",
    )


@pytest.fixture
def sample_derived_confidence() -> DerivedConfidence:
    """A fixed DerivedConfidence for deterministic tests."""
    return DerivedConfidence(
        method="BlackScholes",
        config_ref="b" * 64,
        fit_quality=FrozenMap.create({"rmse": Decimal("0.0012"), "r2": Decimal("0.9987")}),
        confidence_interval=(Decimal("154.50"), Decimal("155.50")),
        confidence_level=Decimal("0.95"),
    )


@pytest.fixture
def sample_attestation(sample_firm_confidence: FirmConfidence) -> Attestation[Decimal]:
    """A fixed Attestation for deterministic tests."""
    return create_attestation(
        value=Decimal("155.00"),
        confidence=sample_firm_confidence,
        source="test_harness",
        timestamp=datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        provenance=(),
    )
```

---

## 2.2 Test Catalogue by File

Every test is listed with its type (Unit, Property, Integration, Static), the invariant
it covers (if any), and a precise description of what it checks.

**Naming convention:** `test_<subject>_<behaviour>` -- the subject is the type or function
under test; the behaviour is the property being verified.

---

### 2.2.1 test_result.py

Tests for `Ok[T]`, `Err[E]`, `Result`, `unwrap`, `map_result`.

| # | Test Name | Type | Invariant | What It Checks |
|---|-----------|------|-----------|----------------|
| 1 | `test_ok_holds_value` | Unit | -- | `Ok(42).value == 42` |
| 2 | `test_err_holds_error` | Unit | -- | `Err("fail").error == "fail"` |
| 3 | `test_ok_is_frozen` | Unit | INV-O01 | Assigning `Ok(1).value = 2` raises `FrozenInstanceError` |
| 4 | `test_err_is_frozen` | Unit | INV-O01 | Assigning `Err("x").error = "y"` raises `FrozenInstanceError` |
| 5 | `test_pattern_match_ok` | Unit | -- | `match Ok(42): case Ok(v): assert v == 42` |
| 6 | `test_pattern_match_err` | Unit | -- | `match Err("e"): case Err(e): assert e == "e"` |
| 7 | `test_unwrap_ok` | Unit | -- | `unwrap(Ok(42)) == 42` |
| 8 | `test_unwrap_err_raises` | Unit | -- | `unwrap(Err("fail"))` raises `RuntimeError` |
| 9 | `test_map_result_ok` | Unit | -- | `map_result(Ok(5), lambda x: x * 2) == Ok(10)` |
| 10 | `test_map_result_err_passthrough` | Unit | -- | `map_result(Err("e"), lambda x: x * 2) == Err("e")` |
| 11 | `test_result_type_alias_ok_is_not_err` | Unit | -- | `isinstance(Ok(1), Ok)` and `not isinstance(Ok(1), Err)` |
| 12 | `test_ok_equality` | Unit | -- | `Ok(42) == Ok(42)` and `Ok(42) != Ok(43)` |
| 13 | `test_err_equality` | Unit | -- | `Err("a") == Err("a")` and `Err("a") != Err("b")` |
| 14 | `test_map_result_identity_law` | Property | INV-R04 | `map_result(r, lambda x: x) == r` for all Ok/Err |
| 15 | `test_map_result_composition_law` | Property | INV-R04 | `map_result(map_result(r, f), g) == map_result(r, lambda x: g(f(x)))` |

**Total: 15 tests (13 Unit, 2 Property)**

---

### 2.2.2 test_types.py

Tests for `FrozenMap`, `BitemporalEnvelope`, `IdempotencyKey`, `EventTime`.

| # | Test Name | Type | Invariant | What It Checks |
|---|-----------|------|-----------|----------------|
| 1 | `test_frozen_map_create_from_dict_sorts_keys` | Unit | INV-R05 | `FrozenMap.create({"b": 2, "a": 1})._entries == (("a", 1), ("b", 2))` |
| 2 | `test_frozen_map_create_from_iterable_sorts_keys` | Unit | INV-R05 | Iterable input sorted by key |
| 3 | `test_frozen_map_get_existing_key` | Unit | -- | Returns the value for a present key |
| 4 | `test_frozen_map_get_missing_key_returns_default` | Unit | -- | Returns `None` or provided default |
| 5 | `test_frozen_map_getitem_existing` | Unit | -- | `fm["a"]` returns value |
| 6 | `test_frozen_map_getitem_missing_raises_keyerror` | Unit | -- | `fm["z"]` raises `KeyError` |
| 7 | `test_frozen_map_contains_true` | Unit | -- | `"a" in fm` is `True` |
| 8 | `test_frozen_map_contains_false` | Unit | -- | `"z" in fm` is `False` |
| 9 | `test_frozen_map_iter_yields_keys_sorted` | Unit | INV-R05 | `list(fm) == sorted(keys)` |
| 10 | `test_frozen_map_len` | Unit | -- | `len(fm)` matches entry count |
| 11 | `test_frozen_map_items_returns_sorted_tuples` | Unit | INV-R05 | `.items()` returns sorted tuples |
| 12 | `test_frozen_map_to_dict_roundtrip` | Unit | INV-R04 | `FrozenMap.create(d).to_dict() == d` |
| 13 | `test_frozen_map_empty` | Unit | -- | `FrozenMap.EMPTY` has len 0 |
| 14 | `test_frozen_map_is_frozen` | Unit | INV-O01 | Attribute assignment raises `FrozenInstanceError` |
| 15 | `test_frozen_map_equality_same_entries` | Unit | -- | Same entries are equal |
| 16 | `test_frozen_map_equality_different_entries` | Unit | -- | Different entries are not equal |
| 17 | `test_frozen_map_insertion_order_irrelevant` | Property | INV-R05 | Two dicts with same keys in different order produce equal FrozenMaps |
| 18 | `test_frozen_map_canonical_ordering_property` | Property | INV-R05 | For all FrozenMaps, `_entries` is sorted by key |
| 19 | `test_frozen_map_to_dict_create_roundtrip_property` | Property | INV-R04 | `FrozenMap.create(fm.to_dict()) == fm` for all fm |
| 20 | `test_bitemporal_envelope_wraps_payload` | Unit | -- | `envelope.payload == original` |
| 21 | `test_bitemporal_envelope_has_event_and_knowledge_time` | Unit | -- | Both timestamps accessible |
| 22 | `test_bitemporal_envelope_is_frozen` | Unit | INV-O01 | Attribute assignment raises `FrozenInstanceError` |
| 23 | `test_idempotency_key_create_valid` | Unit | INV-X03 | `IdempotencyKey.create("key-1")` returns `Ok` |
| 24 | `test_idempotency_key_create_empty_err` | Unit | INV-X03 | `IdempotencyKey.create("")` returns `Err` |
| 25 | `test_idempotency_key_is_frozen` | Unit | INV-O01 | Attribute assignment raises `FrozenInstanceError` |
| 26 | `test_event_time_wraps_datetime` | Unit | -- | `EventTime(dt).value == dt` |
| 27 | `test_event_time_is_frozen` | Unit | INV-O01 | Attribute assignment raises `FrozenInstanceError` |

**Total: 27 tests (22 Unit, 5 Property)**

---

### 2.2.3 test_money.py

Tests for `ATTESTOR_DECIMAL_CONTEXT`, `PositiveDecimal`, `NonZeroDecimal`, `NonEmptyStr`, `Money`.

| # | Test Name | Type | Invariant | What It Checks |
|---|-----------|------|-----------|----------------|
| 1 | `test_decimal_context_precision_is_28` | Unit | INV-R04 | `ATTESTOR_DECIMAL_CONTEXT.prec == 28` |
| 2 | `test_decimal_context_rounding_half_even` | Unit | INV-R04 | Banker's rounding mode |
| 3 | `test_decimal_context_traps_invalid_operation` | Unit | INV-L10 | Traps `InvalidOperation` |
| 4 | `test_decimal_context_traps_division_by_zero` | Unit | INV-L10 | Traps `DivisionByZero` |
| 5 | `test_decimal_context_traps_overflow` | Unit | INV-L10 | Traps `Overflow` |
| 6 | `test_positive_decimal_parse_positive_ok` | Unit | -- | `PositiveDecimal.parse(Decimal("1.5"))` returns `Ok` |
| 7 | `test_positive_decimal_parse_zero_err` | Unit | -- | `PositiveDecimal.parse(Decimal("0"))` returns `Err` |
| 8 | `test_positive_decimal_parse_negative_err` | Unit | -- | `PositiveDecimal.parse(Decimal("-1"))` returns `Err` |
| 9 | `test_positive_decimal_parse_non_decimal_err` | Unit | INV-L10 | `PositiveDecimal.parse(1.5)` returns `Err` (float rejected) |
| 10 | `test_positive_decimal_is_frozen` | Unit | INV-O01 | Attribute assignment raises |
| 11 | `test_nonzero_decimal_parse_positive_ok` | Unit | -- | Positive value returns `Ok` |
| 12 | `test_nonzero_decimal_parse_negative_ok` | Unit | -- | Negative value returns `Ok` |
| 13 | `test_nonzero_decimal_parse_zero_err` | Unit | -- | Zero returns `Err` |
| 14 | `test_nonempty_str_parse_valid_ok` | Unit | -- | `NonEmptyStr.parse("abc")` returns `Ok` |
| 15 | `test_nonempty_str_parse_empty_err` | Unit | -- | `NonEmptyStr.parse("")` returns `Err` |
| 16 | `test_money_create_valid_ok` | Unit | -- | `Money.create(Decimal("100"), "USD")` returns `Ok` |
| 17 | `test_money_create_empty_currency_err` | Unit | -- | Empty currency returns `Err` |
| 18 | `test_money_create_non_decimal_amount_err` | Unit | INV-L10 | Float amount returns `Err` |
| 19 | `test_money_add_same_currency_ok` | Unit | INV-L01 | Same currency addition returns `Ok` with correct sum |
| 20 | `test_money_add_different_currency_err` | Unit | INV-L01 | Different currencies returns `Err` |
| 21 | `test_money_sub_same_currency_ok` | Unit | INV-L01 | Same currency subtraction returns `Ok` |
| 22 | `test_money_sub_different_currency_err` | Unit | INV-L01 | Different currencies returns `Err` |
| 23 | `test_money_mul_by_decimal` | Unit | -- | Scalar multiplication preserves currency |
| 24 | `test_money_negate` | Unit | -- | Sign flipped, currency preserved |
| 25 | `test_money_amount_is_decimal_not_float` | Unit | -- | `type(m.amount) is Decimal` |
| 26 | `test_money_is_frozen` | Unit | INV-O01 | Attribute assignment raises |
| 27 | `test_positive_decimal_roundtrip_property` | Property | INV-R04 | `PositiveDecimal.parse(pd.value) == Ok(pd)` for all valid pd |
| 28 | `test_money_add_commutativity_property` | Property | INV-L01 | `a.add(b) == b.add(a)` for same-currency money |
| 29 | `test_money_add_associativity_property` | Property | INV-L01 | `(a+b)+c == a+(b+c)` for same-currency money |
| 30 | `test_money_negate_involution_property` | Property | -- | `m.negate().negate() == m` for all money |
| 31 | `test_money_add_negate_identity_property` | Property | INV-L01 | `m.add(m.negate()) == Money(0, m.currency)` |

**Total: 31 tests (26 Unit, 5 Property)**

---

### 2.2.4 test_errors.py

Tests for `AttestorError`, `FieldViolation`, and all 7 error subclasses.

| # | Test Name | Type | Invariant | What It Checks |
|---|-----------|------|-----------|----------------|
| 1 | `test_attestor_error_is_frozen` | Unit | INV-O01 | Attribute assignment raises |
| 2 | `test_field_violation_is_frozen` | Unit | INV-O01 | Attribute assignment raises |
| 3 | `test_validation_error_has_fields` | Unit | -- | `ValidationError.fields` is a tuple of `FieldViolation` |
| 4 | `test_validation_error_to_dict_json_serializable` | Unit | INV-R04 | `json.dumps(ve.to_dict())` does not raise |
| 5 | `test_illegal_transition_error_fields` | Unit | -- | `from_state` and `to_state` are accessible |
| 6 | `test_illegal_transition_error_to_dict` | Unit | INV-R04 | JSON serializable |
| 7 | `test_conservation_violation_error_fields` | Unit | INV-L01 | `law_name`, `expected`, `actual` accessible |
| 8 | `test_conservation_violation_error_to_dict` | Unit | INV-R04 | JSON serializable |
| 9 | `test_missing_observable_error_fields` | Unit | -- | `observable`, `as_of` accessible |
| 10 | `test_calibration_error_fields` | Unit | -- | `model` field accessible |
| 11 | `test_pricing_error_fields` | Unit | -- | `instrument`, `reason` accessible |
| 12 | `test_persistence_error_fields` | Unit | -- | `operation` field accessible |
| 13 | `test_all_errors_json_serializable` | Unit | INV-R04 | For each of 7 subclasses: `json.dumps(err.to_dict())` succeeds |
| 14 | `test_all_errors_inherit_from_attestor_error` | Unit | -- | `isinstance(err, AttestorError)` for each subclass |
| 15 | `test_all_errors_are_frozen` | Unit | INV-O01 | Attribute assignment raises for every subclass |
| 16 | `test_error_to_dict_roundtrip_property` | Property | INV-R04 | `json.loads(json.dumps(err.to_dict()))` preserves all fields |

**Total: 16 tests (15 Unit, 1 Property)**

---

### 2.2.5 test_serialization.py

Tests for `canonical_bytes`, `content_hash`, `derive_seed`.

| # | Test Name | Type | Invariant | What It Checks |
|---|-----------|------|-----------|----------------|
| 1 | `test_canonical_bytes_decimal_as_string` | Unit | INV-R05 | `Decimal("1.5")` serialized as `"1.5"` (string, not float) |
| 2 | `test_canonical_bytes_datetime_iso8601` | Unit | INV-R05 | Aware datetime -> ISO 8601 string with UTC offset |
| 3 | `test_canonical_bytes_none_is_null` | Unit | INV-R05 | `canonical_bytes(None) == b'null'` |
| 4 | `test_canonical_bytes_tuple_is_json_array` | Unit | INV-R05 | `(1, 2, 3)` -> `b'[1,2,3]'` |
| 5 | `test_canonical_bytes_frozen_map_sorted_keys` | Unit | INV-R05 | FrozenMap keys sorted in output JSON |
| 6 | `test_canonical_bytes_frozen_dataclass_has_type_field` | Unit | INV-R05 | Output includes `"_type":"ClassName"` field |
| 7 | `test_canonical_bytes_enum_serialized_as_value` | Unit | INV-R05 | Enum -> its `.value` string |
| 8 | `test_canonical_bytes_deterministic_same_input` | Unit | INV-R04 | Two calls with same input produce identical bytes |
| 9 | `test_canonical_bytes_dict_order_irrelevant` | Unit | INV-R05 | `{"b":2,"a":1}` and `{"a":1,"b":2}` produce same bytes |
| 10 | `test_content_hash_returns_64_char_hex` | Unit | INV-R05 | SHA-256 hex digest is 64 characters |
| 11 | `test_content_hash_deterministic` | Unit | INV-R04 | Same input, call twice, same hash |
| 12 | `test_content_hash_different_inputs_differ` | Unit | INV-R05 | Different objects produce different hashes |
| 13 | `test_canonical_bytes_roundtrip_consistency` | Unit | INV-R04 | `canonical_bytes(x) == canonical_bytes(x)` for structured types |
| 14 | `test_derive_seed_deterministic` | Unit | INV-R04 | `derive_seed(refs, v) == derive_seed(refs, v)` |
| 15 | `test_derive_seed_different_refs_differ` | Unit | INV-R04 | Different refs produce different seeds |
| 16 | `test_derive_seed_sorts_refs` | Unit | INV-R04 | `derive_seed(("b","a"), v) == derive_seed(("a","b"), v)` |
| 17 | `test_derive_seed_empty_refs` | Unit | INV-R04 | `derive_seed((), "v1.0")` succeeds |
| 18 | `test_derive_seed_returns_nonneg_int` | Unit | -- | Return value is int >= 0 |
| 19 | `test_canonical_bytes_deterministic_property` | Property | INV-R04 | For all domain types: two calls produce identical bytes |
| 20 | `test_content_hash_deterministic_property` | Property | INV-R05 | For all domain types: two calls produce identical hash |
| 21 | `test_canonical_bytes_frozen_map_order_property` | Property | INV-R05 | FrozenMap from shuffled dict order produces same bytes |
| 22 | `test_derive_seed_ref_order_property` | Property | INV-R04 | For all ref tuples: sorting does not change seed |

**Total: 22 tests (18 Unit, 4 Property)**

---

### 2.2.6 test_ledger_types.py

Tests for `DeltaValue` (6 variants), `StateDelta`, `DistinctAccountPair`, `Move`,
`Transaction`, `Account`, `AccountType`, `Position`, `LedgerEntry`, `ExecuteResult`.

| # | Test Name | Type | Invariant | What It Checks |
|---|-----------|------|-----------|----------------|
| 1 | `test_delta_decimal_holds_value` | Unit | -- | `DeltaDecimal(Decimal("1.5")).value == Decimal("1.5")` |
| 2 | `test_delta_str_holds_value` | Unit | -- | `DeltaStr("abc").value == "abc"` |
| 3 | `test_delta_bool_holds_value` | Unit | -- | `DeltaBool(True).value is True` |
| 4 | `test_delta_date_holds_value` | Unit | -- | `DeltaDate(date.today()).value` correct |
| 5 | `test_delta_datetime_holds_value` | Unit | -- | `DeltaDatetime(dt).value == dt` |
| 6 | `test_delta_null_exists` | Unit | -- | `DeltaNull()` constructs without error |
| 7 | `test_delta_value_pattern_match_exhaustive` | Unit | INV-O04 | `match/case` over all 6 variants with no default |
| 8 | `test_delta_value_all_variants_frozen` | Unit | INV-O01 | Attribute assignment raises for each variant |
| 9 | `test_distinct_account_pair_create_valid` | Unit | -- | Different accounts returns `Ok` |
| 10 | `test_distinct_account_pair_create_same_err` | Unit | INV-L05 | Same debit and credit returns `Err` |
| 11 | `test_distinct_account_pair_create_empty_debit_err` | Unit | INV-L10 | Empty debit returns `Err` |
| 12 | `test_distinct_account_pair_create_empty_credit_err` | Unit | INV-L10 | Empty credit returns `Err` |
| 13 | `test_distinct_account_pair_is_frozen` | Unit | INV-O01 | Attribute assignment raises |
| 14 | `test_state_delta_construction` | Unit | -- | All fields accessible |
| 15 | `test_state_delta_is_frozen` | Unit | INV-O01 | Attribute assignment raises |
| 16 | `test_move_has_required_fields` | Unit | -- | `source`, `destination`, `unit`, `quantity`, `contract_id` all set |
| 17 | `test_move_quantity_is_positive_decimal` | Unit | INV-L01 | `isinstance(m.quantity, PositiveDecimal)` |
| 18 | `test_move_is_frozen` | Unit | INV-O01 | Attribute assignment raises |
| 19 | `test_transaction_has_moves_and_timestamp` | Unit | -- | `moves` is non-empty tuple, `timestamp` is datetime |
| 20 | `test_transaction_state_deltas_default_empty` | Unit | -- | Default `state_deltas == ()` |
| 21 | `test_transaction_is_frozen` | Unit | INV-O01 | Attribute assignment raises |
| 22 | `test_account_has_type_and_id` | Unit | -- | `account_id` and `account_type` accessible |
| 23 | `test_account_type_enum_has_7_variants` | Unit | -- | `len(AccountType) == 7` |
| 24 | `test_account_is_frozen` | Unit | INV-O01 | Attribute assignment raises |
| 25 | `test_position_has_account_instrument_quantity` | Unit | -- | All 3 fields accessible |
| 26 | `test_position_is_frozen` | Unit | INV-O01 | Attribute assignment raises |
| 27 | `test_ledger_entry_with_valid_distinct_pair` | Unit | INV-L05 | Constructs successfully with valid pair |
| 28 | `test_ledger_entry_debit_account_property` | Unit | -- | `entry.debit_account == pair.debit` |
| 29 | `test_ledger_entry_credit_account_property` | Unit | -- | `entry.credit_account == pair.credit` |
| 30 | `test_ledger_entry_is_frozen` | Unit | INV-O01 | Attribute assignment raises |
| 31 | `test_ledger_entry_amount_is_positive_decimal` | Unit | INV-L01 | `isinstance(entry.amount, PositiveDecimal)` |
| 32 | `test_ledger_entry_optional_attestation_none` | Unit | -- | `entry.attestation is None` when not provided |
| 33 | `test_ledger_entry_optional_attestation_present` | Unit | INV-O03 | When provided, is an `Attestation` |
| 34 | `test_execute_result_enum_has_3_values` | Unit | -- | APPLIED, ALREADY_APPLIED, REJECTED |
| 35 | `test_distinct_account_pair_rejects_same_property` | Property | INV-L05 | For all strings s: `create(s, s)` returns `Err` |
| 36 | `test_delta_value_roundtrip_property` | Property | INV-R04 | Each variant survives `canonical_bytes` -> consistent hash |
| 37 | `test_ledger_entry_accounts_always_distinct_property` | Property | INV-L05 | `entry.debit_account != entry.credit_account` for all entries |
| 38 | `test_move_quantity_always_positive_property` | Property | INV-L01 | `move.quantity.value > 0` for all generated moves |

**Total: 38 tests (34 Unit, 4 Property)**

---

### 2.2.7 test_pricing_types.py

Tests for `ValuationResult`, `Greeks`, `Scenario`, `ScenarioResult`, `VaRResult`, `PnLAttribution`.

| # | Test Name | Type | Invariant | What It Checks |
|---|-----------|------|-----------|----------------|
| 1 | `test_valuation_result_construction` | Unit | -- | All fields accessible |
| 2 | `test_valuation_result_default_components_is_frozen_map_empty` | Unit | -- | Default `components == FrozenMap.EMPTY` |
| 3 | `test_valuation_result_is_frozen` | Unit | INV-O01 | Attribute assignment raises |
| 4 | `test_valuation_result_npv_is_decimal` | Unit | -- | `type(vr.npv) is Decimal` |
| 5 | `test_greeks_all_defaults_are_decimal_zero` | Unit | -- | All 8 fields default to `Decimal("0")` |
| 6 | `test_greeks_custom_values` | Unit | -- | Non-default values assigned correctly |
| 7 | `test_greeks_is_frozen` | Unit | INV-O01 | Attribute assignment raises |
| 8 | `test_greeks_all_fields_are_decimal` | Unit | -- | Every field `type(...) is Decimal` |
| 9 | `test_scenario_create_from_dict` | Unit | -- | `Scenario.create(...)` converts dict to FrozenMap |
| 10 | `test_scenario_overrides_is_frozen_map` | Unit | -- | `isinstance(s.overrides, FrozenMap)` |
| 11 | `test_scenario_is_frozen` | Unit | INV-O01 | Attribute assignment raises |
| 12 | `test_scenario_result_construction` | Unit | -- | All fields accessible |
| 13 | `test_scenario_result_pnl_impact_equals_stress_minus_base` | Unit | -- | `sr.pnl_impact == sr.stressed_npv - sr.base_npv` |
| 14 | `test_scenario_result_is_frozen` | Unit | INV-O01 | Attribute assignment raises |
| 15 | `test_var_result_construction` | Unit | -- | All fields accessible |
| 16 | `test_var_result_is_frozen` | Unit | INV-O01 | Attribute assignment raises |
| 17 | `test_var_result_component_var_is_frozen_map` | Unit | -- | `isinstance(vr.component_var, FrozenMap)` |
| 18 | `test_pnl_attribution_construction` | Unit | -- | All fields accessible |
| 19 | `test_pnl_attribution_decomposition_sums_to_total` | Unit | INV-L01 | `total == market + carry + trade + residual` |
| 20 | `test_pnl_attribution_is_frozen` | Unit | INV-O01 | Attribute assignment raises |
| 21 | `test_pnl_attribution_decomposition_property` | Property | INV-L01 | For all generated PnLAttributions: `total == sum(components)` |
| 22 | `test_greeks_zero_is_identity_property` | Property | -- | `Greeks()` has all fields == `Decimal("0")` |
| 23 | `test_all_pricing_types_frozen_property` | Property | INV-O01 | For all generated pricing types: attribute assignment raises |
| 24 | `test_valuation_result_serialization_roundtrip` | Property | INV-R04 | `canonical_bytes` is deterministic for all ValuationResults |

**Total: 24 tests (20 Unit, 4 Property)**

---

### 2.2.8 test_pricing_protocols.py

Tests for `PricingEngine`, `RiskEngine`, `StubPricingEngine`.

| # | Test Name | Type | Invariant | What It Checks |
|---|-----------|------|-----------|----------------|
| 1 | `test_pricing_engine_is_protocol` | Unit | -- | `PricingEngine` is a `Protocol` class |
| 2 | `test_risk_engine_is_protocol` | Unit | -- | `RiskEngine` is a `Protocol` class |
| 3 | `test_stub_price_returns_ok` | Unit | -- | `isinstance(result, Ok)` |
| 4 | `test_stub_price_npv_is_decimal` | Unit | -- | `type(result.value.npv) is Decimal` |
| 5 | `test_stub_price_npv_is_zero` | Unit | -- | `result.value.npv == Decimal("0")` |
| 6 | `test_stub_price_currency_is_usd` | Unit | -- | `result.value.currency == "USD"` |
| 7 | `test_stub_price_is_deterministic` | Unit | INV-R04 | Same inputs twice produce identical output |
| 8 | `test_stub_greeks_returns_ok` | Unit | -- | `isinstance(result, Ok)` |
| 9 | `test_stub_greeks_all_fields_are_decimal_zero` | Unit | -- | All 8 Greek fields == `Decimal("0")` |
| 10 | `test_stub_greeks_is_deterministic` | Unit | INV-R04 | Same inputs twice produce identical output |
| 11 | `test_stub_satisfies_pricing_engine_protocol` | Static | -- | mypy verifies structural subtyping (type annotation test) |
| 12 | `test_stub_price_deterministic_property` | Property | INV-R04 | For random inputs: two calls produce identical output |

**Total: 12 tests (10 Unit, 1 Property, 1 Static)**

---

### 2.2.9 test_infra_protocols.py

Tests for `EventBus`, `AttestationStore`, `TransactionLog`, `StateStore`, `TopicConfig`,
`PHASE0_TOPICS`, `phase0_topic_configs`.

| # | Test Name | Type | Invariant | What It Checks |
|---|-----------|------|-----------|----------------|
| 1 | `test_event_bus_is_protocol` | Unit | -- | `EventBus` is a `Protocol` class |
| 2 | `test_attestation_store_is_protocol` | Unit | -- | `AttestationStore` is a `Protocol` class |
| 3 | `test_transaction_log_is_protocol` | Unit | -- | `TransactionLog` is a `Protocol` class |
| 4 | `test_state_store_is_protocol` | Unit | -- | `StateStore` is a `Protocol` class |
| 5 | `test_phase0_topics_count` | Unit | -- | `len(PHASE0_TOPICS) == 3` |
| 6 | `test_phase0_topic_names_exact` | Unit | -- | Exact string match for all 3 topics |
| 7 | `test_phase0_topic_configs_count` | Unit | -- | `len(phase0_topic_configs()) == 3` |
| 8 | `test_attestations_topic_infinite_retention` | Unit | -- | `retention_ms == -1` for attestations topic |
| 9 | `test_raw_topic_30_day_retention` | Unit | -- | Correct retention_ms for raw events topic |
| 10 | `test_topic_config_is_frozen` | Unit | INV-O01 | Attribute assignment raises |
| 11 | `test_phase0_topics_are_strings` | Unit | -- | All items are `str` |

**Total: 11 tests (11 Unit)**

---

### 2.2.10 test_memory_adapters.py

Tests for `InMemoryEventBus`, `InMemoryAttestationStore`, `InMemoryTransactionLog`,
`InMemoryStateStore`.

| # | Test Name | Type | Invariant | What It Checks |
|---|-----------|------|-----------|----------------|
| 1 | `test_event_bus_publish_and_get_messages` | Unit | -- | Publish 3 messages, retrieve all 3 |
| 2 | `test_event_bus_publish_multiple_topics` | Unit | -- | Messages isolated per topic |
| 3 | `test_event_bus_get_messages_empty_topic` | Unit | -- | Returns empty list |
| 4 | `test_event_bus_subscribe_returns_ok` | Unit | -- | `isinstance(result, Ok)` |
| 5 | `test_attestation_store_store_and_retrieve` | Unit | INV-R05 | Store, retrieve by hash, values match |
| 6 | `test_attestation_store_store_idempotent` | Unit | INV-X03 | Same attestation stored twice, one copy |
| 7 | `test_attestation_store_retrieve_not_found` | Unit | -- | Returns `Err` for unknown hash |
| 8 | `test_attestation_store_exists_true` | Unit | -- | `exists()` returns `True` after store |
| 9 | `test_attestation_store_exists_false` | Unit | -- | `exists()` returns `False` before store |
| 10 | `test_transaction_log_append_and_replay` | Unit | INV-L05 | Append 3, replay returns 3 |
| 11 | `test_transaction_log_replay_preserves_insertion_order` | Unit | INV-L05 | Order matches append order |
| 12 | `test_transaction_log_replay_since_filters` | Unit | -- | Filters by `knowledge_time` |
| 13 | `test_transaction_log_replay_empty` | Unit | -- | Returns `Ok(())` when empty |
| 14 | `test_state_store_put_and_get` | Unit | -- | Store bytes, retrieve same bytes |
| 15 | `test_state_store_get_missing_returns_ok_none` | Unit | -- | Unknown key returns `Ok(None)` |
| 16 | `test_state_store_put_overwrites` | Unit | -- | Second put overwrites first value |
| 17 | `test_event_bus_satisfies_protocol` | Unit | -- | Can be assigned to `EventBus` typed variable |
| 18 | `test_attestation_store_satisfies_protocol` | Unit | -- | Can be assigned to `AttestationStore` typed variable |
| 19 | `test_transaction_log_satisfies_protocol` | Unit | -- | Can be assigned to `TransactionLog` typed variable |
| 20 | `test_state_store_satisfies_protocol` | Unit | -- | Can be assigned to `StateStore` typed variable |
| 21 | `test_attestation_store_idempotent_property` | Property | INV-X03 | For all attestations: `store(a); store(a)` returns same hash |
| 22 | `test_transaction_log_append_replay_roundtrip_property` | Property | INV-L05 | For all lists of envelopes: `append_all; replay()` returns all in order |
| 23 | `test_state_store_put_get_roundtrip_property` | Property | INV-R04 | For all (key, bytes) pairs: `put; get == bytes` |

**Total: 23 tests (20 Unit, 3 Property)**

---

### 2.2.11 test_integration_attestation_store.py

Integration tests exercising attestation creation, content hashing, storage, retrieval,
and provenance chain walking through the in-memory store.

| # | Test Name | Type | Invariant | What It Checks |
|---|-----------|------|-----------|----------------|
| 1 | `test_store_firm_attestation_and_retrieve` | Integration | INV-R05, INV-O05 | Create FirmConfidence attestation, store, retrieve by hash, values match |
| 2 | `test_store_quoted_attestation_and_retrieve` | Integration | INV-R05, INV-O06 | Same with QuotedConfidence |
| 3 | `test_store_derived_attestation_with_provenance` | Integration | INV-O03 | Two firm inputs, one derived output; provenance refs exist in store |
| 4 | `test_content_addressing_idempotent` | Integration | INV-X03 | Store twice, `hash_1 == hash_2`, only one entry in store |
| 5 | `test_retrieve_nonexistent_returns_err` | Integration | -- | `store.retrieve("nonexistent")` returns `Err` |
| 6 | `test_full_provenance_chain_walkable` | Integration | INV-O03 | `firm -> derived_1 -> derived_2`: walk chain from leaf to root, every hash resolves |
| 7 | `test_attestation_content_hash_stability_across_store_retrieve` | Integration | INV-R05 | Retrieved attestation has identical `content_hash` to original |
| 8 | `test_store_attestation_with_frozen_map_value` | Integration | INV-R05 | `FrozenMap` payload survives store/retrieve |

**Total: 8 tests (8 Integration)**

---

### 2.2.12 test_determinism.py

Cross-cutting determinism tests. These verify INV-R04 (Reproducibility) across the
entire Phase 0 type system.

| # | Test Name | Type | Invariant | What It Checks |
|---|-----------|------|-----------|----------------|
| 1 | `test_canonical_bytes_decimal_deterministic` | Property | INV-R04 | For all Decimals: two calls produce identical bytes |
| 2 | `test_canonical_bytes_attestation_deterministic` | Property | INV-R04 | For all Attestations: two calls produce identical bytes |
| 3 | `test_canonical_bytes_money_deterministic` | Property | INV-R04 | For all Money: two calls produce identical bytes |
| 4 | `test_canonical_bytes_frozen_map_deterministic` | Property | INV-R04 | For all FrozenMaps: two calls produce identical bytes |
| 5 | `test_canonical_bytes_transaction_deterministic` | Property | INV-R04 | For all Transactions: two calls produce identical bytes |
| 6 | `test_canonical_bytes_ledger_entry_deterministic` | Property | INV-R04 | For all LedgerEntries: two calls produce identical bytes |
| 7 | `test_canonical_bytes_valuation_result_deterministic` | Property | INV-R04 | For all ValuationResults: two calls produce identical bytes |
| 8 | `test_canonical_bytes_greeks_deterministic` | Property | INV-R04 | For all Greeks: two calls produce identical bytes |
| 9 | `test_content_hash_attestation_deterministic` | Property | INV-R05 | For all Attestations: two calls produce identical hash |
| 10 | `test_content_hash_money_deterministic` | Property | INV-R05 | For all Money: two calls produce identical hash |
| 11 | `test_derive_seed_deterministic_property` | Property | INV-R04 | For all (refs, version): same output |
| 12 | `test_derive_seed_sorted_refs_property` | Property | INV-R04 | `derive_seed(refs, v) == derive_seed(tuple(sorted(refs)), v)` |
| 13 | `test_frozen_map_creation_order_irrelevant` | Property | INV-R05 | Two dicts with same KV in different order produce same FrozenMap, same hash |
| 14 | `test_attestation_same_value_same_hash` | Property | INV-R05 | Two attestations with identical payloads have identical content_hash |
| 15 | `test_decimal_context_not_mutated_between_operations` | Unit | INV-R04 | After 100 Money operations, context unchanged |
| 16 | `test_stub_pricing_engine_deterministic_across_100_calls` | Unit | INV-R04 | 100 identical calls to stub produce identical output |

**Total: 16 tests (2 Unit, 14 Property)**

---

### 2.2.13 test_invariants.py

Cross-cutting invariant enforcement tests. One test per Phase 0 invariant.

| # | Test Name | Type | Invariant | What It Checks |
|---|-----------|------|-----------|----------------|
| 1 | `test_inv_o01_attestation_immutability` | Unit | INV-O01 | All frozen dataclass types reject attribute assignment |
| 2 | `test_inv_o01_attestation_immutability_property` | Property | INV-O01 | For all generated Attestations: attribute assignment raises |
| 3 | `test_inv_o03_provenance_completeness` | Integration | INV-O03 | Derived attestation references exist in store; DAG is closed |
| 4 | `test_inv_o04_confidence_exhaustiveness` | Unit | INV-O04 | Pattern match over Confidence covers exactly 3 variants |
| 5 | `test_inv_o04_confidence_exhaustiveness_property` | Property | INV-O04 | For all generated Confidences: exactly one variant matches |
| 6 | `test_inv_o05_firm_payload_completeness` | Property | INV-O05 | For all FirmConfidence: `source`, `timestamp`, `attestation_ref` present and non-empty |
| 7 | `test_inv_o06_quoted_payload_completeness` | Property | INV-O06 | For all QuotedConfidence: `bid`, `ask`, `venue` present |
| 8 | `test_inv_o07_derived_payload_completeness` | Property | INV-O07 | For all DerivedConfidence: `method`, `config_ref`, `fit_quality` present |
| 9 | `test_inv_r04_reproducibility` | Property | INV-R04 | For all domain objects: `canonical_bytes(x)` called twice yields same result |
| 10 | `test_inv_r05_content_addressing` | Property | INV-R05 | `content_hash(x) == SHA256(canonical_bytes(x))` verified by independent computation |
| 11 | `test_inv_x03_idempotency_store` | Integration | INV-X03 | `store(a); store(a)` -> idempotent (same hash, one entry) |
| 12 | `test_inv_l05_transaction_atomicity` | Unit | INV-L05 | Transaction has all-or-nothing semantics (tuple of moves is frozen) |
| 13 | `test_inv_l10_no_raise_in_domain` | Static | INV-L10 | AST scan of all `attestor/` modules: zero `raise` in domain functions (excluding `__post_init__` guards) |
| 14 | `test_inv_l10_all_public_functions_return_result` | Static | INV-L10 | AST scan: all public functions returning from domain modules have typed returns |
| 15 | `test_no_float_in_type_annotations` | Static | -- | Regex scan: no `: float` in any `attestor/*.py` |
| 16 | `test_all_dataclasses_are_frozen` | Static | INV-O01 | Regex scan: every `@dataclass(...)` has `frozen=True` |
| 17 | `test_all_domain_types_are_final` | Static | -- | Regex scan: every non-base dataclass has `@final` |

**Total: 17 tests (5 Unit, 6 Property, 3 Integration, 3 Static)**

---

### 2.2 Summary: Test Count by File

| File | Unit | Property | Integration | Static | Total |
|------|------|----------|-------------|--------|-------|
| `test_result.py` | 13 | 2 | 0 | 0 | **15** |
| `test_types.py` | 22 | 5 | 0 | 0 | **27** |
| `test_money.py` | 26 | 5 | 0 | 0 | **31** |
| `test_errors.py` | 15 | 1 | 0 | 0 | **16** |
| `test_serialization.py` | 18 | 4 | 0 | 0 | **22** |
| `test_ledger_types.py` | 34 | 4 | 0 | 0 | **38** |
| `test_pricing_types.py` | 20 | 4 | 0 | 0 | **24** |
| `test_pricing_protocols.py` | 10 | 1 | 0 | 1 | **12** |
| `test_infra_protocols.py` | 11 | 0 | 0 | 0 | **11** |
| `test_memory_adapters.py` | 20 | 3 | 0 | 0 | **23** |
| `test_integration_attestation_store.py` | 0 | 0 | 8 | 0 | **8** |
| `test_determinism.py` | 2 | 14 | 0 | 0 | **16** |
| `test_invariants.py` | 5 | 6 | 3 | 3 | **17** |
| **Total** | **196** | **49** | **11** | **4** | **260** |

---

## 2.3 Coverage Requirements

### 2.3.1 Coverage Targets

| Module Group | Line Coverage Target | Branch Coverage Target | Rationale |
|--------------|---------------------|----------------------|-----------|
| `attestor/core/` (result, types, money, errors, serialization, identifiers) | >= 95% | >= 90% | Foundation types: every path must be proven correct |
| `attestor/oracle/` (attestation) | >= 95% | >= 90% | Attestation creation and confidence types are the epistemic core |
| `attestor/ledger/` (transactions) | >= 95% | >= 90% | Ledger types enforce financial conservation by construction |
| `attestor/pricing/` (types, protocols) | >= 90% | >= 85% | Interface types and stub; lower threshold because stub is trivial |
| `attestor/infra/` (protocols, memory_adapter, config) | >= 90% | >= 85% | Protocols are mostly signatures; adapters are simple wrappers |
| **Phase 0 overall** | **>= 92%** | **>= 88%** | Per `pyproject.toml` `fail_under = 90` with margin |

### 2.3.2 Mutation Testing Targets

| Module | Mutation Score Target | Rationale |
|--------|----------------------|-----------|
| `attestor/core/result.py` | >= 90% | Foundation ADT: any semantic regression is catastrophic |
| `attestor/core/money.py` | >= 85% | Financial arithmetic: sign errors, currency checks must be caught |
| `attestor/core/serialization.py` | >= 85% | Content-addressing: hash changes break provenance chains |
| `attestor/oracle/attestation.py` | >= 85% | Confidence variant handling must be exhaustive |
| `attestor/ledger/transactions.py` | >= 80% | DistinctAccountPair and PositiveDecimal guards must be airtight |
| `attestor/infra/memory_adapter.py` | >= 80% | Idempotency and ordering logic must survive mutation |
| **Phase 0 overall** | **>= 82%** | Feathers: "Mutation score < 80% means tests would not catch regressions" |

### 2.3.3 Invariant Coverage Map

Every Phase 0 invariant is covered by at least one test. The table below maps each
invariant to the test files that cover it.

| Invariant | Description | Primary Test File(s) | Secondary Coverage |
|-----------|-------------|---------------------|-------------------|
| INV-O01 | Attestation Immutability | `test_invariants.py` (#1, #2) | `test_types.py` (#14, #22, #25, #27), `test_money.py` (#10, #26), `test_errors.py` (#1, #2, #15), `test_ledger_types.py` (#8, #13, #15, #18, #21, #24, #26, #30), `test_pricing_types.py` (#3, #7, #11, #14, #16, #20) |
| INV-O03 | Provenance Completeness | `test_invariants.py` (#3) | `test_integration_attestation_store.py` (#3, #6) |
| INV-O04 | Confidence Exhaustiveness | `test_invariants.py` (#4, #5) | `test_ledger_types.py` (#7) |
| INV-O05 | Firm Payload Completeness | `test_invariants.py` (#6) | `test_integration_attestation_store.py` (#1) |
| INV-O06 | Quoted Payload Completeness | `test_invariants.py` (#7) | `test_integration_attestation_store.py` (#2) |
| INV-O07 | Derived Payload Completeness | `test_invariants.py` (#8) | `test_integration_attestation_store.py` (#3) |
| INV-R04 | Reproducibility | `test_invariants.py` (#9) | `test_determinism.py` (all 16 tests), `test_serialization.py` (#8, #11, #13-22), `test_pricing_protocols.py` (#7, #10, #12) |
| INV-R05 | Content-Addressing | `test_invariants.py` (#10) | `test_serialization.py` (#1-12), `test_determinism.py` (#9, #10, #13, #14), `test_integration_attestation_store.py` (#4, #7) |
| INV-X03 | Idempotency | `test_invariants.py` (#11) | `test_memory_adapters.py` (#6, #21), `test_integration_attestation_store.py` (#4) |
| INV-L05 | Transaction Atomicity | `test_invariants.py` (#12) | `test_ledger_types.py` (#10, #35, #37), `test_memory_adapters.py` (#10, #11, #22) |
| INV-L10 | Domain Function Totality | `test_invariants.py` (#13, #14) | Enforced by `Result` return types across all modules |
| INV-L01 | Balance Conservation | -- (full enforcement in Phase 1 ledger engine) | `test_money.py` (#19-22, #28, #29, #31), `test_ledger_types.py` (#17, #31, #38), `test_pricing_types.py` (#19, #21) |

### 2.3.4 Test Pyramid Shape Verification

```
                     /\
                    /  \  4 Static (AST scans, mypy checks)
                   /----\
                  / 11   \  Integration (attestation store E2E)
                 /--------\
                / 49 Prop  \  Property (Hypothesis, 100+ examples each)
               /------------\
              / 196 Unit     \  Unit (< 100ms each, < 10s total)
             /________________\
```

The pyramid has 196 unit tests at the base (75%), 49 property tests in the middle (19%),
11 integration tests above (4%), and 4 static analysis tests at the apex (2%). This
matches the Fowler pyramid: broad scope tests are rare; fast, focused tests dominate.

### 2.3.5 Execution Time Budget

| Stage | Tests | Target Time | Gate |
|-------|-------|-------------|------|
| Unit tests | 196 | < 5 seconds | Blocks commit |
| Property tests | 49 (x 100 examples = 4,900 evaluations) | < 30 seconds | Blocks commit |
| Integration tests | 11 | < 15 seconds | Blocks PR merge |
| Static scans | 4 | < 5 seconds | Blocks PR merge |
| **Total Phase 0** | **260** | **< 55 seconds** | |

### 2.3.6 Completeness Checklist

The following completeness requirements are satisfied by the test catalogue above.

| Requirement | Satisfied By |
|-------------|-------------|
| Every public function gets at least one test | All `parse()`, `create()`, factory functions, `to_dict()`, `canonical_bytes()`, `content_hash()`, `derive_seed()`, `unwrap()`, `map_result()` tested |
| Every invariant gets at least one test | Section 2.3.3 maps all 12 Phase 0 invariants to tests |
| Every Result-returning function tested for BOTH Ok and Err paths | `test_result.py`, `test_money.py`, `test_types.py`, `test_ledger_types.py` all test both paths |
| Every frozen type tested for immutability | Every `test_*_is_frozen` test covers one type; `test_invariants.py` #1 covers all types collectively |
| Every sum type tested for exhaustive pattern matching | `test_result.py` (#5, #6), `test_ledger_types.py` (#7), `test_invariants.py` (#4, #5) |
| Every type gets a serialization round-trip test | `test_determinism.py` covers all Phase 0 types via `canonical_bytes` property tests |
| Every FrozenMap field tested for canonical ordering | `test_types.py` (#1, #2, #9, #11, #17, #18), `test_serialization.py` (#5, #21) |

---

*"Code without tests is bad code. It doesn't matter how well written it is; it doesn't
matter how pretty it is or how well structured it is. Without tests there is no way to
tell if the code is getting better or worse."*

-- Michael Feathers, Working Effectively with Legacy Code

*"The test suite is the specification. If someone can reimplement the system from the
tests alone, the tests are complete. If they cannot, the tests are incomplete."*

-- Kent Beck

*"Don't write tests. Generate them."*

-- John Hughes

*"If you're thinking without writing, you only think you're thinking."*

-- Leslie Lamport

---

## 3. Gaps Found in Pass 1

The following items **must be resolved in PHASE0_EXECUTION.md** before implementation begins. Each gap is assigned a severity and a concrete resolution. Gaps are grouped by origin.

---

### 3.1 VETO Resolutions (Blockers)

These correspond to Section 1.1 veto items. No code may be written until these are resolved in the execution plan.

| Gap ID | Source | Summary | Resolution Required |
|--------|--------|---------|---------------------|
| GAP-01 | V-01 | `content_hash` hashes only `value`, not the full attestation identity | Add `attestation_id` field = `SHA256(canonical_bytes(source, timestamp, confidence, value, provenance))`. Use `attestation_id` as the `AttestationStore` key and Postgres PK. Keep `content_hash` as a secondary index for dedup queries. Update `create_attestation` to compute both. Update Postgres schema: rename `content_hash` PK column to `attestation_id`, add `content_hash` column with index. |
| GAP-02 | V-02 | `Money` arithmetic ignores `ATTESTOR_DECIMAL_CONTEXT` | Wrap every arithmetic operation in `with localcontext(ATTESTOR_DECIMAL_CONTEXT):`. Add import of `ATTESTOR_DECIMAL_CONTEXT` from `core.serialization`. Apply to `add`, `subtract`, `multiply`. Add a test: compute `Money(Decimal("1") / Decimal("3")).multiply(Decimal("3"))` and verify the result is identical regardless of the thread-local context. |
| GAP-03 | V-03 | Naive `datetime` permitted in temporal fields | Add `UtcDatetime` refined type with `parse() -> Result[UtcDatetime, str]` factory that rejects naive datetimes. Replace `datetime` with `UtcDatetime` in: `EventTime.value`, `Attestation.timestamp`, `BitemporalEnvelope.event_time`, `BitemporalEnvelope.knowledge_time`, `FirmConfidence.timestamp`, `Transaction.timestamp`, `LedgerEntry.timestamp`, `AttestorError.timestamp`. Add CI scan: `grep -rn ': datetime' attestor/ --include='*.py'` should return zero hits in domain modules (only `UtcDatetime` allowed). |
| GAP-04 | V-04 | `canonical_bytes` / `_serialize_value` raise `TypeError` | Change signatures: `canonical_bytes(obj) -> Result[bytes, str]`, `content_hash(obj) -> Result[str, str]`, `create_attestation(...) -> Result[Attestation[T], str]`. Catch `TypeError` inside `canonical_bytes` and return `Err`. Propagate `Result` through `content_hash` and `create_attestation`. Update all call sites. |

---

### 3.2 Invariant Enforcement Gaps

These are gaps identified in Section 1.2 where the type system or runtime checks do not fully enforce a PLAN invariant.

| Gap ID | Invariant | Summary | Resolution Required |
|--------|-----------|---------|---------------------|
| GAP-05 | INV-O03 | Derived attestation can have empty `provenance=()` | Add a factory function `create_derived_attestation(value, source, confidence: DerivedConfidence, input_refs: tuple[str, ...])` that validates `len(input_refs) >= 1` and returns `Err` if empty. Make `Attestation.__init__` private (prefix `_`) or document that direct construction is forbidden for Derived. Add test: `create_derived_attestation(..., input_refs=())` returns `Err`. |
| GAP-06 | INV-O06 | `QuotedConfidence` missing `mid` and `spread` fields | Add computed properties: `@property def mid(self) -> Decimal: return (self.bid + self.ask) / 2` and `@property def spread(self) -> Decimal: return self.ask - self.bid`. Compute inside `ATTESTOR_DECIMAL_CONTEXT`. Add validation in factory: `bid <= ask` (return `Err` otherwise). Add tests for `mid` and `spread` computation and the `bid <= ask` invariant. |
| GAP-07 | INV-O07 | `DerivedConfidence.confidence_interval` and `confidence_level` are `Optional` | Make both fields **required** (remove `| None`). `DerivedConfidence` represents a model-derived value; epistemic honesty demands that every model output carries uncertainty bounds. If a model genuinely cannot produce bounds, use a sentinel like `confidence_interval=(Decimal("-inf"), Decimal("inf"))` and `confidence_level=Decimal("0")` to signal "unknown" explicitly. Add a factory `DerivedConfidence.create(...)` that validates `0 < confidence_level <= 1` and `interval_low < interval_high`. |

---

### 3.3 Determinism Audit Gaps

| Gap ID | Finding | Summary | Resolution Required |
|--------|---------|---------|---------------------|
| GAP-08 | D-03 | `FrozenMap.create()` raises `TypeError` on incomparable keys | Add type constraint: `FrozenMap[K, V]` where `K` must satisfy `__lt__`. In practice, restrict keys to `str` (the only key type used in Phase 0). Change `FrozenMap.create() -> Result[FrozenMap[K,V], str]` that catches `TypeError` from `sorted()` and returns `Err`. |
| GAP-09 | D-04 | `FrozenMap.create()` silently accepts duplicate keys from Iterable input | `FrozenMap.create([("a",1), ("a",2)])` stores both entries. `get("a")` returns first match, but `items()` returns both. Two semantically-equal FrozenMaps constructed with different duplicate orderings produce different `canonical_bytes`, violating INV-R05. **Fix:** In `FrozenMap.create`, deduplicate by key. If duplicate keys have different values, return `Err("Duplicate key with conflicting values: {key}")`. If same values, deduplicate silently. |
| GAP-10 | D-05 | `Decimal` zero normalization is not canonical | `Decimal("0E+2").normalize()` serializes as `"0E+2"` but `Decimal("0").normalize()` as `"0"`. Both represent zero but produce different content hashes. **Fix:** In `_serialize_value`, after `normalize()`, special-case zero: `if obj == 0: return "0"`. |
| GAP-11 | D-12 | `_serialize_value` uses `type(obj).__name__` as `_type` discriminator | Document in Pass 1 as a **canonical serialization contract**: "Type names participating in content-addressed hashing (`FirmConfidence`, `QuotedConfidence`, `DerivedConfidence`, `Money`, `FrozenMap`, etc.) are part of the serialization schema. Renaming any of these types is a breaking change that invalidates all existing content hashes. A CI test (`test_canonical_type_names`) must assert the expected set of `_type` values." |

---

### 3.4 Totality Audit Gaps

| Gap ID | Function | Summary | Resolution Required |
|--------|----------|---------|---------------------|
| GAP-12 | `FrozenMap.__getitem__` | Raises `KeyError` for missing keys | Acceptable per Python protocol, but: (a) add `get_result(key: K) -> Result[V, str]` as the primary access path for domain code; (b) add a code comment: "Prefer `.get(key, default)` or `.get_result(key)` in all domain code. `__getitem__` exists only for dict-protocol compatibility." Add a CI lint rule or convention doc. |
| GAP-13 | `AttestationStore.exists()` returns `bool` not `Result` | `exists(content_hash: str) -> bool` will raise connection errors in production Postgres adapter | Change protocol to `exists(content_hash: str) -> Result[bool, PersistenceError]`. Update `InMemoryAttestationStore.exists` and all call sites. |
| GAP-14 | Module-level `unwrap()` raises `RuntimeError` on `Err` | Exported from `result.py` as a public function, violates INV-L10 | Move to a `testing` subpackage or mark with `# test-only` comment and exclude from domain module `__init__.py` re-exports. Alternatively, gate with `if TYPE_CHECKING` to prevent runtime import from domain code. |

---

### 3.5 Test-Catalogue-Driven Gaps

Issues discovered while writing the test catalogue that reveal missing or inconsistent elements in Pass 1.

| Gap ID | Summary | Resolution Required |
|--------|---------|---------------------|
| GAP-15 | `map_result()` referenced in conftest.py but not defined in Pass 1's `result.py` | Either add `def map_result(f: Callable[[T], U], r: Result[T, E]) -> Result[U, E]` to `result.py`, or remove from conftest and use `.map()` method instead. Recommendation: omit `map_result` (use `.map()` method). |
| GAP-16 | Import paths in conftest.py assume `PositiveDecimal`, `NonZeroDecimal`, `NonEmptyStr` live in `attestor.core.money` | Verify the actual module location in Pass 1. If these types are in `core/types.py`, update conftest imports to `from attestor.core.types import PositiveDecimal, NonZeroDecimal, NonEmptyStr`. If they are in `core/money.py`, document this. Consistent module boundaries matter for the `__init__.py` re-exports in Step 8. |
| GAP-17 | `ATTESTOR_DECIMAL_CONTEXT` imported from `attestor.core.money` in conftest but defined in `attestor.core.serialization` in Pass 1 | Decide canonical location: `core/serialization.py` (current Pass 1) or `core/money.py` (where it's most used). Re-export from `core/__init__.py` regardless. Update all import references. |

---

### 3.6 Schema & Infrastructure Gaps

| Gap ID | Summary | Resolution Required |
|--------|---------|---------------------|
| GAP-18 | Postgres `attestations` table PK is `content_hash` | Per GAP-01, change PK to `attestation_id`. Add `content_hash` as a non-unique indexed column (multiple attestations may share the same observed value). Update `InMemoryAttestationStore` key to `attestation_id`. |
| GAP-19 | No `attestation_id` column in Postgres schema | Add `attestation_id TEXT PRIMARY KEY` to the `attestations` table DDL. Update `INSERT` and `SELECT` statements. |
| GAP-20 | `FirmConfidence.source` and `attestation_ref` accept empty strings | Use `NonEmptyStr` for `source` and `attestation_ref` fields in `FirmConfidence`. An empty source or reference violates the epistemic contract (INV-O05 requires a meaningful source identifier). |

---

### 3.7 Summary Table

| Priority | Count | Gap IDs |
|----------|-------|---------|
| **VETO (must fix before any code)** | 4 | GAP-01, GAP-02, GAP-03, GAP-04 |
| **HIGH (must fix before Phase 0 complete)** | 7 | GAP-05, GAP-06, GAP-07, GAP-09, GAP-12, GAP-13, GAP-20 |
| **MEDIUM (must fix before Phase 0 tests pass)** | 3 | GAP-08, GAP-10, GAP-11 |
| **LOW (must fix before implementation)** | 6 | GAP-14, GAP-15, GAP-16, GAP-17, GAP-18, GAP-19 |
| **Total** | **20** | |

---

### 3.8 Actionability Verdict

> **Can a developer read this document alongside PHASE0_EXECUTION.md and write every test file without asking a question?**

**Not yet.** The 4 VETO items (GAP-01 through GAP-04) change the signatures of `content_hash`, `canonical_bytes`, `create_attestation`, and all temporal fields. Every test that calls these functions depends on the resolution. The 7 HIGH gaps (GAP-05 through GAP-07, GAP-09, GAP-12, GAP-13, GAP-20) change the structure of `QuotedConfidence`, `DerivedConfidence`, `FrozenMap`, `AttestationStore`, and `FirmConfidence`, which affect ~60 tests in the catalogue.

**Once Pass 1 is amended with these 20 fixes**, the test catalogue in Section 2 is complete and self-contained. A developer can:

1. Copy conftest.py from Section 2.1 (updating imports per GAP-16/GAP-17)
2. Implement each test file from Section 2.2 in order
3. Verify coverage targets from Section 2.3
4. Run the CI pipeline from Step 18 of Pass 1

No additional clarification will be required.

---

*End of Pass 2 Review.*
