# PHASE 0 -- Build Sequence

**Author:** Karpathy
**Date:** 2026-02-15
**Scope:** Foundation deliverables F-01 through F-07, IV-01 (attestation store), Pillar V
interface types + stubs, 3 Kafka topics, 3 Postgres tables, CI pipeline.
**Prerequisite:** Python 3.12+ installed. No external dependencies beyond stdlib for
domain code. `pytest`, `mypy`, `ruff`, `hypothesis` installed in virtualenv.

---

## Before You Start

```bash
# 1. Create project root and virtualenv
mkdir -p /path/to/attestor
cd /path/to/attestor
python3.12 -m venv .venv
source .venv/bin/activate

# 2. Install dev tools
pip install pytest mypy ruff hypothesis

# 3. Verify
python --version   # >= 3.12
mypy --version     # any recent
pytest --version   # any recent
ruff --version     # any recent
```

The build sequence below produces 18 steps. Each step creates one testable
artifact. Each step is verified before the next begins.

The directory structure at the end of Phase 0:

```
attestor/
    __init__.py
    core/
        __init__.py
        result.py
        types.py
        money.py
        errors.py
        serialization.py
        identifiers.py
    oracle/
        __init__.py
        attestation.py
    ledger/
        __init__.py
        transactions.py
    pricing/
        __init__.py
        types.py
        protocols.py
    infra/
        __init__.py
        protocols.py
        memory_adapter.py
        config.py
tests/
    __init__.py
    conftest.py
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
    test_infra_protocols.py
    test_memory_adapter.py
    test_integration_attestation_store.py
pyproject.toml
sql/
    001_attestations.sql
    002_event_log.sql
    003_schema_registry.sql
.github/
    workflows/
        ci.yml
```

---

## Step 1: Project Scaffold + pyproject.toml (~30 lines)

**Prerequisites:** None. This is the absolute starting point.

**Files:**
- `pyproject.toml`
- `attestor/__init__.py`
- `attestor/core/__init__.py`
- `tests/__init__.py`

**What to code:**

Create `pyproject.toml` with project metadata and tool configuration. This file
governs mypy strict mode, ruff rules, pytest settings, and coverage thresholds.
Every subsequent step depends on these settings being correct.

```toml
[project]
name = "attestor"
version = "0.1.0"
description = "Attestor -- attestation-first cross-asset trading platform"
requires-python = ">=3.12"

[tool.mypy]
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
show_error_codes = true
disallow_any_explicit = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-x --tb=short"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "SIM"]

[tool.coverage.run]
source = ["attestor"]
branch = true

[tool.coverage.report]
fail_under = 90
show_missing = true
```

Create empty `__init__.py` files:
- `attestor/__init__.py` -- contains `__version__ = "0.1.0"`
- `attestor/core/__init__.py` -- empty
- `tests/__init__.py` -- empty

**What to test:**

```bash
# All three must pass with zero errors, zero tests collected:
mypy --strict attestor/
ruff check attestor/ tests/
pytest tests/
```

**Done when:** All three commands exit 0. mypy reports 0 errors. ruff reports 0
violations. pytest reports "0 items collected" (not an error -- just no tests yet).

---

## Step 2: Result Type (F-01 partial) (~60 lines)

**Prerequisites:** Step 1.

**File:** `attestor/core/result.py`

**What to code:**

The `Result` type is the absolute foundation. Every function in Attestor that can
fail returns `Result[T, E]` instead of raising an exception. This is the single most
important type in the system.

Build three things:
1. `Ok[T]` -- a frozen dataclass wrapping a success value
2. `Err[E]` -- a frozen dataclass wrapping an error value
3. `Result` type alias: `Result = Ok[T] | Err[E]`

Both `Ok` and `Err` are `@final`, `frozen=True`, `slots=True`. They support
structural pattern matching via `match/case`.

Additionally, implement two helper functions:
- `unwrap(result: Result[T, E]) -> T` -- returns the value if Ok, raises
  `RuntimeError` if Err. This is for test code and boundaries only.
- `map_result(result: Result[T, E], fn: Callable[[T], U]) -> Result[U, E]` --
  applies fn to the Ok value, passes Err through unchanged.

**Test file:** `tests/test_result.py`

**What to test:**

```python
# test_ok_holds_value
# test_err_holds_error
# test_ok_is_frozen (cannot assign .value -- raises FrozenInstanceError)
# test_err_is_frozen (cannot assign .error -- raises FrozenInstanceError)
# test_pattern_match_ok -- match Ok(v): assert v == expected
# test_pattern_match_err -- match Err(e): assert e == expected
# test_unwrap_ok -- unwrap(Ok(42)) == 42
# test_unwrap_err -- unwrap(Err("fail")) raises RuntimeError
# test_map_result_ok -- map_result(Ok(5), lambda x: x * 2) == Ok(10)
# test_map_result_err -- map_result(Err("e"), lambda x: x * 2) == Err("e")
# test_result_type_alias -- isinstance(Ok(1), Ok) and not isinstance(Ok(1), Err)
```

```bash
pytest -x tests/test_result.py
mypy --strict attestor/core/result.py
```

**Done when:** 11 tests pass. mypy strict passes with 0 errors.

---

## Step 3: FrozenMap and BitemporalEnvelope (F-03, F-07) (~100 lines)

**Prerequisites:** Step 2 (uses Result for IdempotencyKey).

**File:** `attestor/core/types.py`

**What to code:**

Two foundational generic types, plus two small helper types.

**FrozenMap[K, V]:** An immutable mapping. Replaces every `dict` in domain types.
Stores entries as a `tuple[tuple[K, V], ...]`, sorted by key. This guarantees:
(a) immutability, (b) deterministic iteration order for hashing, (c) canonical
serialization.

Implement:
- `FrozenMap.create(items: dict[K, V] | Iterable[tuple[K, V]]) -> FrozenMap[K, V]`
  -- static method, canonical constructor
- `FrozenMap.EMPTY` -- class variable, empty instance
- `get(key, default=None)`, `__getitem__`, `__contains__`, `__iter__`, `__len__`
- `items() -> tuple[tuple[K, V], ...]` -- returns the sorted entries
- `to_dict() -> dict[K, V]` -- boundary conversion for serialization
- `__eq__` -- value equality based on `_entries`

Why sorted entries? When we hash a FrozenMap for content-addressing, the hash must
be identical regardless of the insertion order of the original dict. Sorting by key
makes the canonical form unique.

**BitemporalEnvelope[T]:** Wraps any payload with two timestamps:
- `event_time: datetime` -- when the event occurred in the real world
- `knowledge_time: datetime` -- when the system learned about it
Both should be timezone-aware (UTC). The type itself does not enforce this --
enforcement happens at the boundary (factory function or runtime check).

**IdempotencyKey:** Wraps a non-empty string. Factory `create()` returns
`Result[IdempotencyKey, str]`. Implemented with a simple length check inline
(no dependency on NonEmptyStr, which comes in Step 4).

```python
@staticmethod
def create(raw: str) -> Result[IdempotencyKey, str]:
    if not raw:
        return Err("IdempotencyKey requires non-empty string")
    return Ok(IdempotencyKey(value=raw))
```

**EventTime:** Simple datetime wrapper for temporal ordering. `value: datetime`.

All types: `@final`, `frozen=True`, `slots=True`.

**Test file:** `tests/test_types.py`

**What to test:**

```python
# FrozenMap tests:
# test_create_from_dict -- FrozenMap.create({"b": 2, "a": 1})._entries == (("a", 1), ("b", 2))
# test_create_from_iterable -- FrozenMap.create([("z", 3), ("a", 1)])._entries sorted by key
# test_get_existing_key -- returns the value
# test_get_missing_key_returns_default -- returns None (or provided default)
# test_getitem_existing -- returns value
# test_getitem_missing_raises_keyerror
# test_contains_true
# test_contains_false
# test_iter_yields_keys_sorted
# test_len
# test_items_returns_sorted_tuples
# test_to_dict_round_trip -- FrozenMap.create(d).to_dict() == d for a given dict
# test_empty_frozen_map -- FrozenMap.EMPTY has len 0
# test_frozen -- assigning attribute raises FrozenInstanceError
# test_equality -- same entries == equal; different entries != equal

# BitemporalEnvelope tests:
# test_wraps_payload -- envelope.payload == original
# test_has_event_time_and_knowledge_time
# test_frozen -- cannot assign attributes

# IdempotencyKey tests:
# test_create_valid -- returns Ok
# test_create_empty -- returns Err

# EventTime tests:
# test_wraps_datetime
# test_frozen
```

```bash
pytest -x tests/test_types.py
mypy --strict attestor/core/types.py
```

**Done when:** All tests pass. mypy strict passes. FrozenMap entries
are provably sorted (inspecting `._entries` in tests). FrozenMap.EMPTY exists
and has length 0.

---

## Step 4: Money and Decimal Context (F-01 partial) (~120 lines)

**Prerequisites:** Step 2 (Result).

**File:** `attestor/core/money.py`

**What to code:**

The Decimal context and Money type. Financial arithmetic must use Decimal, never
float. This step establishes that invariant for the entire project.

**ATTESTOR_DECIMAL_CONTEXT:**
```python
from decimal import Context, ROUND_HALF_EVEN, InvalidOperation, DivisionByZero, Overflow

ATTESTOR_DECIMAL_CONTEXT = Context(
    prec=28,
    rounding=ROUND_HALF_EVEN,
    Emin=-999999,
    Emax=999999,
    capitals=1,
    clamp=0,
    flags=[],
    traps=[InvalidOperation, DivisionByZero, Overflow],
)
```

Why these parameters? `prec=28` gives 28 significant digits -- more than enough for
any financial quantity (15 sig digits covers USD amounts up to $999 trillion with
cent precision, plus 13 digits of margin for intermediate calculations).
`ROUND_HALF_EVEN` (banker's rounding) eliminates systematic rounding bias.

**Refined types (all with Result-returning factories):**

- `PositiveDecimal` -- `value: Decimal`, must be > 0.
  `parse(raw: Decimal) -> Result[PositiveDecimal, str]`
  Rejects zero, negative, and non-Decimal inputs.

- `NonZeroDecimal` -- `value: Decimal`, must be != 0.
  `parse(raw: Decimal) -> Result[NonZeroDecimal, str]`

- `NonEmptyStr` -- `value: str`, must be non-empty.
  `parse(raw: str) -> Result[NonEmptyStr, str]`

- `Money` -- `amount: Decimal`, `currency: NonEmptyStr`.
  `create(amount: Decimal, currency: str) -> Result[Money, str]`
  Arithmetic methods that enforce same-currency:
  - `add(other: Money) -> Result[Money, str]` -- Err if currencies differ
  - `sub(other: Money) -> Result[Money, str]` -- Err if currencies differ
  - `mul(factor: Decimal) -> Money` -- scalar multiplication, currency preserved
  - `negate() -> Money` -- flip sign, currency preserved

All types: `@final`, `frozen=True`, `slots=True`.

**Test file:** `tests/test_money.py`

**What to test:**

```python
# ATTESTOR_DECIMAL_CONTEXT:
# test_precision_is_28
# test_rounding_is_half_even
# test_traps_invalid_operation
# test_traps_division_by_zero
# test_traps_overflow

# PositiveDecimal:
# test_parse_positive -- Ok
# test_parse_zero -- Err
# test_parse_negative -- Err
# test_parse_non_decimal_type -- Err (pass int or float, get Err)
# test_frozen

# NonZeroDecimal:
# test_parse_nonzero_positive -- Ok
# test_parse_nonzero_negative -- Ok
# test_parse_zero -- Err

# NonEmptyStr:
# test_parse_nonempty -- Ok
# test_parse_empty -- Err

# Money:
# test_create_valid -- Ok(Money(...))
# test_create_empty_currency -- Err
# test_create_non_decimal_amount -- Err
# test_add_same_currency -- Ok with correct sum
# test_add_different_currency -- Err
# test_sub_same_currency -- Ok
# test_sub_different_currency -- Err
# test_mul_by_decimal -- correct product, currency preserved
# test_negate -- amount sign flipped, currency preserved
# test_amount_is_decimal_not_float -- type(m.amount) is Decimal
# test_frozen
```

```bash
pytest -x tests/test_money.py
mypy --strict attestor/core/money.py
```

**Done when:** All tests pass. mypy strict passes. No `float` appears in any type
annotation in `money.py`.

---

## Step 5: Error Hierarchy (F-02) (~120 lines)

**Prerequisites:** Step 2 (Result).

**File:** `attestor/core/errors.py`

**What to code:**

The error value hierarchy. No domain function raises exceptions. Every error is a
frozen dataclass value that can be pattern-matched, serialized, and stored.

Base class (NOT `@final` because it has subclasses):
```python
@dataclass(frozen=True, slots=True)
class AttestorError:
    message: str
    code: str
    timestamp: datetime
    source: str  # "module.function" that produced this error
```

Helper type for ValidationError:
```python
@final
@dataclass(frozen=True, slots=True)
class FieldViolation:
    path: str         # e.g. "trade.notional"
    constraint: str   # e.g. "must be positive"
    actual_value: str  # e.g. "-100"
```

Seven subclasses (each `@final`, `frozen=True`, `slots=True`):

1. `ValidationError(AttestorError)` -- extra field: `fields: tuple[FieldViolation, ...]`
2. `IllegalTransitionError(AttestorError)` -- extra: `from_state: str`, `to_state: str`
3. `ConservationViolationError(AttestorError)` -- extra: `law_name: str`, `expected: str`, `actual: str`
4. `MissingObservableError(AttestorError)` -- extra: `observable: str`, `as_of: str`
5. `CalibrationError(AttestorError)` -- extra: `model: str`
6. `PricingError(AttestorError)` -- extra: `instrument: str`, `reason: str`
7. `PersistenceError(AttestorError)` -- extra: `operation: str`

Each error type must have a `to_dict()` method returning `dict[str, object]`
that is JSON-serializable via `json.dumps()`.

**Test file:** `tests/test_errors.py`

**What to test:**

```python
# test_attestor_error_is_frozen
# test_field_violation_is_frozen
# test_validation_error_has_fields -- construct with FieldViolation tuple
# test_validation_error_to_dict -- json.dumps does not raise
# test_illegal_transition_error_fields
# test_illegal_transition_error_to_dict
# test_conservation_violation_error_fields
# test_missing_observable_error_fields
# test_calibration_error_fields
# test_pricing_error_fields
# test_persistence_error_fields
# test_all_errors_json_serializable -- for each subclass: json.dumps(err.to_dict())
# test_all_errors_inherit_from_attestor_error -- isinstance check
```

```bash
pytest -x tests/test_errors.py
mypy --strict attestor/core/errors.py
```

**Done when:** 13 tests pass. All 7 error subclasses are frozen, slotted, final,
and JSON-serializable. mypy strict passes.

---

## Step 6: Canonical Serialization (F-01 partial) (~80 lines)

**Prerequisites:** Step 2 (Result), Step 3 (FrozenMap), Step 4 (Decimal types).

**File:** `attestor/core/serialization.py`

**What to code:**

Content-addressed hashing requires canonical serialization. Every domain type must
have exactly one byte representation for hashing. Two functions:

1. `canonical_bytes(obj: object) -> bytes`
   Converts any domain type to canonical JSON bytes (UTF-8). Rules:
   - Keys sorted lexicographically
   - No whitespace between tokens (compact form: `separators=(",", ":")`)
   - `Decimal` values serialized as strings (`"123.45"`, not `123.45`)
   - `datetime` serialized as ISO 8601 with explicit UTC offset
   - `None` becomes JSON `null`
   - `tuple` becomes JSON array
   - `Enum` serialized as its `.value` string
   - `FrozenMap` becomes JSON object with sorted keys
   - Frozen dataclass becomes JSON object with `"_type": "ClassName"` field,
     then all fields alphabetically

   Implementation approach: write a recursive `_to_serializable(obj)` function
   that returns a JSON-compatible Python object (str, int, list, dict, None),
   then call `json.dumps(result, sort_keys=True, separators=(",", ":"))`.

2. `content_hash(obj: object) -> str`
   Returns `hashlib.sha256(canonical_bytes(obj)).hexdigest()`.

The key property: `canonical_bytes(x) == canonical_bytes(y)` if and only if
`x` and `y` are semantically equal. This is what makes content-addressing work.

**Test file:** `tests/test_serialization.py`

**What to test:**

```python
# test_canonical_bytes_decimal -- Decimal("1.5") serialized as string "1.5"
# test_canonical_bytes_datetime -- aware datetime -> ISO 8601 string
# test_canonical_bytes_none -- None -> b'null'
# test_canonical_bytes_tuple -- (1, 2, 3) -> b'[1,2,3]'
# test_canonical_bytes_frozen_map -- keys sorted in output
# test_canonical_bytes_frozen_dataclass -- includes _type field
# test_canonical_bytes_deterministic -- same input, call twice, same output
# test_canonical_bytes_dict_order_irrelevant -- {"b":2,"a":1} and {"a":1,"b":2} produce same bytes
# test_content_hash_returns_64_char_hex -- SHA-256 hex digest is 64 chars
# test_content_hash_deterministic -- same input, call twice, same hash
# test_content_hash_different_inputs_differ -- different objects, different hash
# test_round_trip_consistency -- canonical_bytes of equal objects produces equal bytes
```

```bash
pytest -x tests/test_serialization.py
mypy --strict attestor/core/serialization.py
```

**Done when:** All tests pass. `content_hash` is deterministic. Dict ordering
does not affect output. mypy strict passes.

---

## Step 7: Identifier Types (F-01 partial) (~100 lines)

**Prerequisites:** Step 2 (Result).

**File:** `attestor/core/identifiers.py`

**What to code:**

Validated identifier newtypes for financial instruments. Each wraps a string
that has been validated at construction time. The raw dataclass constructor is
private-by-convention; all external construction goes through `parse()`.

1. **LEI** (Legal Entity Identifier):
   - Exactly 20 alphanumeric characters
   - `parse(raw: str) -> Result[LEI, str]`
   - Rejects: wrong length, non-alphanumeric chars

2. **UTI** (Unique Transaction Identifier):
   - Between 1 and 52 characters
   - First 20 chars must be a valid LEI prefix (all alphanumeric)
   - `parse(raw: str) -> Result[UTI, str]`

3. **ISIN** (International Securities Identification Number):
   - Exactly 12 characters: 2 uppercase alpha + 9 alphanumeric + 1 check digit
   - Check digit validated via the Luhn algorithm applied to the numeric
     conversion of the full string (A=10, B=11, ..., Z=35), then standard
     Luhn on the resulting digit string
   - `parse(raw: str) -> Result[ISIN, str]`

The Luhn algorithm for ISIN:
1. Convert each character to digits: A=10, B=11, ..., Z=35, 0-9 stay as-is
2. Concatenate all digits into a single string
3. Apply Luhn check: working from right to left, double every second digit,
   subtract 9 if result > 9, sum all digits, total mod 10 must be 0

All types: `@final`, `frozen=True`, `slots=True`.

**Test file:** `tests/test_identifiers.py`

**What to test:**

```python
# LEI:
# test_lei_valid_20_alphanumeric -- Ok
# test_lei_too_short_19 -- Err
# test_lei_too_long_21 -- Err
# test_lei_non_alphanumeric -- Err (contains hyphen or space)
# test_lei_frozen

# UTI:
# test_uti_valid_52_chars -- Ok (max length)
# test_uti_valid_21_chars -- Ok (min meaningful: 20 LEI prefix + 1)
# test_uti_too_long_53_chars -- Err
# test_uti_empty -- Err
# test_uti_invalid_prefix -- Err (first 20 chars contain non-alphanumeric)

# ISIN:
# test_isin_valid_apple -- "US0378331005" -> Ok
# test_isin_valid_microsoft -- "US5949181045" -> Ok
# test_isin_wrong_check_digit -- change last digit -> Err
# test_isin_too_short_11 -- Err
# test_isin_too_long_13 -- Err
# test_isin_lowercase -- "us0378331005" -> Err (must be uppercase)
# test_isin_non_alpha_country -- "120378331005" -> Err
# test_isin_frozen
```

```bash
pytest -x tests/test_identifiers.py
mypy --strict attestor/core/identifiers.py
```

**Done when:** All tests pass. ISIN Luhn check correctly validates known-good
ISINs (Apple: US0378331005, Microsoft: US5949181045) and rejects corrupted ones.
mypy strict passes.

---

## Step 8: Core Package Re-exports (~15 lines)

**Prerequisites:** Steps 2-7 (all core modules complete).

**File:** `attestor/core/__init__.py`

**What to code:**

Update `attestor/core/__init__.py` to re-export all public types from the core
submodules. This is the public API of the core package. Downstream modules
import from `attestor.core`, not from `attestor.core.result` directly.

```python
from attestor.core.result import Ok, Err, Result, unwrap, map_result
from attestor.core.types import (
    FrozenMap, BitemporalEnvelope, IdempotencyKey, EventTime,
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
from attestor.core.serialization import canonical_bytes, content_hash
from attestor.core.identifiers import LEI, UTI, ISIN

__all__ = [
    "Ok", "Err", "Result", "unwrap", "map_result",
    "FrozenMap", "BitemporalEnvelope", "IdempotencyKey", "EventTime",
    "Money", "PositiveDecimal", "NonZeroDecimal", "NonEmptyStr",
    "ATTESTOR_DECIMAL_CONTEXT",
    "AttestorError", "ValidationError", "IllegalTransitionError",
    "ConservationViolationError", "MissingObservableError",
    "CalibrationError", "PricingError", "PersistenceError",
    "FieldViolation",
    "canonical_bytes", "content_hash",
    "LEI", "UTI", "ISIN",
]
```

**What to test:**

```bash
# 1. Verify all imports work from the package level:
python -c "from attestor.core import Ok, Err, Result, Money, FrozenMap, \
    BitemporalEnvelope, AttestorError, ValidationError, LEI, UTI, ISIN, \
    content_hash, canonical_bytes, ATTESTOR_DECIMAL_CONTEXT, PositiveDecimal"

# 2. Run full mypy on attestor/core/:
mypy --strict attestor/core/

# 3. Run ALL core tests together:
pytest -x tests/test_result.py tests/test_types.py tests/test_money.py \
    tests/test_errors.py tests/test_serialization.py tests/test_identifiers.py
```

**Done when:** All imports succeed from `attestor.core`. mypy strict passes on
the entire `attestor/core/` package. All prior tests still pass when run together.

---

## Step 9: Attestation and Confidence Types (F-01 partial) (~180 lines)

**Prerequisites:** Step 8 (all core types available via `attestor.core`).

**Files:**
- `attestor/oracle/__init__.py` (empty)
- `attestor/oracle/attestation.py`

**What to code:**

The Attestation type with structured epistemic payloads. Every value in Attestor
has provenance, confidence, and a content-addressed identity. This is the
epistemological foundation.

**Confidence sum type (3 variants):**

Each variant is a `@final` frozen dataclass carrying structured metadata about
how the value was obtained and how certain it is.

1. `FirmConfidence` -- exact value from authoritative source
   - `source: str` (e.g., "NYSE", "LCH")
   - `timestamp: datetime` (when the source observed it)
   - `attestation_ref: str` (content hash of the source attestation)

2. `QuotedConfidence` -- bounded value from a quoted market
   - `bid: Decimal`
   - `ask: Decimal`
   - `venue: str` (e.g., "Bloomberg", "ICE")
   - `size: Decimal | None` (quoted size, None if unavailable)
   - `conditions: str` (e.g., "Indicative", "Firm", "RFQ")

3. `DerivedConfidence` -- model output with quantified uncertainty
   - `method: str` (e.g., "BlackScholes", "SVI", "GPRegression")
   - `config_ref: str` (content hash of ModelConfig attestation)
   - `fit_quality: FrozenMap[str, Decimal]` (e.g., {"rmse": ..., "r2": ...})
   - `confidence_interval: tuple[Decimal, Decimal] | None` (lower, upper)
   - `confidence_level: Decimal | None` (e.g., Decimal("0.95"))

`Confidence = FirmConfidence | QuotedConfidence | DerivedConfidence`

Pattern matching over `Confidence` is exhaustive: all three variants must be
handled. This is enforced by mypy when you use `assert_never` in the default branch.

**Attestation[T]:**
```python
@final
@dataclass(frozen=True, slots=True)
class Attestation(Generic[T]):
    value: T
    confidence: Confidence
    source: str
    timestamp: datetime
    provenance: tuple[str, ...]     # Content hashes of input attestations
    content_hash: str               # SHA-256 of canonical serialization of value
```

Factory function (not a method, because we need to compute the hash before
constructing the frozen object):
```python
def create_attestation(
    value: T,
    confidence: Confidence,
    source: str,
    timestamp: datetime,
    provenance: tuple[str, ...] = (),
) -> Attestation[T]:
    h = content_hash(value)
    return Attestation(
        value=value, confidence=confidence, source=source,
        timestamp=timestamp, provenance=provenance, content_hash=h,
    )
```

**Test file:** `tests/test_attestation.py`

**What to test:**

```python
# FirmConfidence:
# test_firm_has_source_timestamp_ref
# test_firm_frozen

# QuotedConfidence:
# test_quoted_has_bid_ask_venue
# test_quoted_frozen

# DerivedConfidence:
# test_derived_has_method_config_ref_fit_quality
# test_derived_frozen
# test_derived_fit_quality_is_frozen_map

# Confidence sum type:
# test_pattern_match_firm -- match case FirmConfidence(...): pass
# test_pattern_match_quoted
# test_pattern_match_derived

# Attestation:
# test_create_attestation_firm -- content_hash is non-empty hex string
# test_create_attestation_quoted
# test_create_attestation_derived
# test_attestation_frozen
# test_content_hash_deterministic -- create twice with same value -> same hash
# test_content_hash_differs_for_different_values
# test_provenance_is_tuple_of_strings
# test_attestation_with_decimal_value -- wraps Decimal correctly
# test_attestation_with_frozen_map_value -- wraps FrozenMap correctly
```

```bash
pytest -x tests/test_attestation.py
mypy --strict attestor/oracle/attestation.py
```

**Done when:** All tests pass. Confidence pattern matching covers all three variants.
Content hash is deterministic. mypy strict passes.

---

## Step 10: Ledger Domain Types (F-05 partial) (~180 lines)

**Prerequisites:** Step 8 (core types), Step 9 (Attestation for LedgerEntry).

**Files:**
- `attestor/ledger/__init__.py` (empty)
- `attestor/ledger/transactions.py`

**What to code:**

The types that enforce double-entry bookkeeping invariants by construction.
No `Any` fields. No mutable dicts. No exceptions in constructors.

**DeltaValue sum type (6 variants):**
These are the only types that can appear in StateDelta old/new values. This
replaces the `Any`-typed fields from Ledger v0.1.

- `DeltaDecimal(value: Decimal)`
- `DeltaStr(value: str)`
- `DeltaBool(value: bool)`
- `DeltaDate(value: date)`
- `DeltaDatetime(value: datetime)`
- `DeltaNull()` -- represents absence of a value

`DeltaValue = DeltaDecimal | DeltaStr | DeltaBool | DeltaDate | DeltaDatetime | DeltaNull`

Each variant: `@final`, `frozen=True`, `slots=True`.

**StateDelta:** Records a field-level change for replay/unwind.
- `unit: str`, `field: str`, `old_value: DeltaValue`, `new_value: DeltaValue`

**DistinctAccountPair:** Enforces debit != credit by construction.
- `debit: str`, `credit: str`
- Factory: `create(debit: str, credit: str) -> Result[DistinctAccountPair, str]`
  Returns Err if `debit == credit` or either is empty.

**Move:** An atomic balance transfer (one leg of a transaction).
- `source: str` (account ID), `destination: str` (account ID)
- `unit: str` (instrument/currency ID)
- `quantity: PositiveDecimal` (enforced > 0 by type)
- `contract_id: str` (links to instrument)

**Transaction:** An atomic batch of moves.
- `tx_id: str`, `moves: tuple[Move, ...]`, `timestamp: datetime`
- `state_deltas: tuple[StateDelta, ...] = ()` (optional, for replay)

**LedgerEntry:** Double-entry enforced by types, not runtime checks.
- `accounts: DistinctAccountPair` (debit != credit by construction)
- `instrument: str`
- `amount: PositiveDecimal` (> 0 by construction)
- `timestamp: datetime`
- `attestation: Attestation[object] | None = None`
- Properties: `debit_account -> str`, `credit_account -> str`

All types: `@final`, `frozen=True`, `slots=True`.

**Test file:** `tests/test_transactions.py`

**What to test:**

```python
# DeltaValue:
# test_delta_decimal_holds_value
# test_delta_str_holds_value
# test_delta_bool_holds_value
# test_delta_date_holds_value
# test_delta_datetime_holds_value
# test_delta_null_exists -- DeltaNull() constructs successfully
# test_delta_value_pattern_match -- exhaustive match over all 6 variants

# DistinctAccountPair:
# test_create_valid_different_accounts -- Ok
# test_create_same_account -- Err
# test_create_empty_debit -- Err
# test_create_empty_credit -- Err
# test_frozen

# StateDelta:
# test_state_delta_construction
# test_state_delta_frozen

# Move:
# test_move_has_required_fields
# test_move_quantity_is_positive_decimal
# test_move_frozen

# Transaction:
# test_transaction_has_moves_and_timestamp
# test_transaction_state_deltas_default_empty
# test_transaction_frozen

# LedgerEntry:
# test_ledger_entry_with_valid_distinct_pair
# test_debit_account_property
# test_credit_account_property
# test_ledger_entry_frozen
# test_ledger_entry_amount_is_positive_decimal
# test_ledger_entry_optional_attestation
```

```bash
pytest -x tests/test_transactions.py
mypy --strict attestor/ledger/transactions.py
```

**Done when:** All tests pass. `DistinctAccountPair.create` rejects debit == credit.
DeltaValue pattern matching covers all 6 variants. No `Any` in any field. mypy
strict passes.

---

## Step 11: Pricing Interface Types (Pillar V types) (~120 lines)

**Prerequisites:** Step 8 (core types -- FrozenMap, Decimal).

**Files:**
- `attestor/pricing/__init__.py` (empty)
- `attestor/pricing/types.py`

**What to code:**

Output types that Pillar V will produce. These are interface contracts -- no pricing
logic. All numeric fields are `Decimal`. All mappings are `FrozenMap`. These types
exist so that Pillars I-IV can code against them now, before Pillar V is implemented.

1. **ValuationResult:**
   - `instrument_id: str`, `npv: Decimal`, `currency: str`
   - `components: FrozenMap[str, Decimal]` (default: `FrozenMap.EMPTY`)
   - `model_config_id: str`, `market_snapshot_id: str`

2. **Greeks:**
   - First order: `delta`, `gamma`, `vega`, `theta`, `rho` (all `Decimal`, default `Decimal("0")`)
   - Second order: `vanna`, `volga`, `charm` (all `Decimal`, default `Decimal("0")`)

3. **Scenario:**
   - `label: str`, `overrides: FrozenMap[str, Decimal]`, `base_snapshot_id: str`
   - Factory: `create(label, overrides: dict[str, Decimal], base_snapshot_id) -> Scenario`

4. **ScenarioResult:**
   - `scenario_label: str`, `base_npv: Decimal`, `stressed_npv: Decimal`
   - `pnl_impact: Decimal`, `instrument_impacts: FrozenMap[str, Decimal]`

5. **VaRResult:**
   - `confidence_level: Decimal`, `horizon_days: int`, `var_amount: Decimal`
   - `currency: str`, `method: str`
   - `component_var: FrozenMap[str, Decimal]`

6. **PnLAttribution:**
   - `total_pnl: Decimal`, `market_pnl: Decimal`, `carry_pnl: Decimal`
   - `trade_pnl: Decimal`, `residual_pnl: Decimal`, `currency: str`

All types: `@final`, `frozen=True`, `slots=True`.

**Test file:** `tests/test_pricing_types.py`

**What to test:**

```python
# ValuationResult:
# test_valuation_result_construction
# test_valuation_result_default_components_is_frozen_map_empty
# test_valuation_result_frozen

# Greeks:
# test_greeks_all_defaults_are_decimal_zero
# test_greeks_custom_values
# test_greeks_frozen

# Scenario:
# test_scenario_create_from_dict -- overrides converted to FrozenMap
# test_scenario_overrides_is_frozen_map
# test_scenario_frozen

# ScenarioResult:
# test_scenario_result_construction
# test_scenario_result_frozen

# VaRResult:
# test_var_result_construction
# test_var_result_frozen

# PnLAttribution:
# test_pnl_attribution_construction
# test_pnl_attribution_decomposition -- total == market + carry + trade + residual
# test_pnl_attribution_frozen
```

```bash
pytest -x tests/test_pricing_types.py
mypy --strict attestor/pricing/types.py
```

**Done when:** All tests pass. No `float` in any type annotation. All defaults are
`Decimal("0")` or `FrozenMap.EMPTY`. mypy strict passes.

---

## Step 12: Pricing Protocols and Stub (Pillar V interface) (~80 lines)

**Prerequisites:** Step 9 (Attestation), Step 11 (pricing types).

**File:** `attestor/pricing/protocols.py`

**What to code:**

Protocol definitions for Pillar V plus a stub implementation for testing.

1. **PricingEngine(Protocol):**
   ```python
   def price(
       self,
       instrument_id: str,
       market_snapshot_id: str,
       model_config_id: str,
   ) -> Result[ValuationResult, PricingError]: ...

   def greeks(
       self,
       instrument_id: str,
       market_snapshot_id: str,
       model_config_id: str,
   ) -> Result[Greeks, PricingError]: ...
   ```

2. **RiskEngine(Protocol):**
   ```python
   def scenario_pnl(
       self,
       portfolio: tuple[str, ...],
       scenarios: tuple[Scenario, ...],
       market_snapshot_id: str,
   ) -> Result[tuple[ScenarioResult, ...], PricingError]: ...
   ```

3. **StubPricingEngine:**
   A `@final` class that implements `PricingEngine`. Returns hard-coded `Ok` values:
   - `price()` returns `Ok(ValuationResult(instrument_id=..., npv=Decimal("0"), currency="USD", ...))`
   - `greeks()` returns `Ok(Greeks())` (all zeros)

   This stub exists so that commutativity tests can run against Pillar V without
   implementing real pricing. It is explicitly not production code.

**Test file:** `tests/test_pricing_protocols.py`

**What to test:**

```python
# test_pricing_engine_is_protocol -- verify it is a Protocol class
# test_risk_engine_is_protocol
# test_stub_price_returns_ok -- isinstance(result, Ok)
# test_stub_price_npv_is_decimal -- type(result.value.npv) is Decimal
# test_stub_price_currency_is_usd
# test_stub_price_is_deterministic -- same inputs -> same output
# test_stub_greeks_returns_ok
# test_stub_greeks_all_fields_are_decimal_zero
# test_stub_greeks_is_deterministic
```

```bash
pytest -x tests/test_pricing_protocols.py
mypy --strict attestor/pricing/protocols.py
```

**Done when:** All tests pass. StubPricingEngine satisfies PricingEngine protocol
(verified by mypy structural subtyping). Stub is deterministic. mypy strict passes.

---

## Step 13: Infrastructure Protocols (F-04 partial) (~120 lines)

**Prerequisites:** Step 8 (core types), Step 9 (Attestation), Step 10 (Transaction).

**Files:**
- `attestor/infra/__init__.py` (empty)
- `attestor/infra/protocols.py`

**What to code:**

Protocol definitions for infrastructure. Domain code depends on these abstractions,
never on concrete implementations. This is dependency inversion: the domain defines
the interface, the infrastructure implements it.

Four protocols:

1. **EventBus(Protocol):**
   ```python
   def publish(self, topic: str, key: str, value: bytes) -> Result[None, PersistenceError]: ...
   def subscribe(self, topic: str, group: str) -> Result[None, PersistenceError]: ...
   ```

2. **AttestationStore(Protocol):**
   ```python
   def store(self, attestation: Attestation[object]) -> Result[str, PersistenceError]: ...
   def retrieve(self, content_hash: str) -> Result[Attestation[object], PersistenceError]: ...
   def exists(self, content_hash: str) -> bool: ...
   ```

3. **TransactionLog(Protocol):**
   ```python
   def append(self, envelope: BitemporalEnvelope[Transaction]) -> Result[None, PersistenceError]: ...
   def replay(self) -> Result[tuple[BitemporalEnvelope[Transaction], ...], PersistenceError]: ...
   def replay_since(self, since: datetime) -> Result[tuple[BitemporalEnvelope[Transaction], ...], PersistenceError]: ...
   ```

4. **StateStore(Protocol):**
   ```python
   def get(self, key: str) -> Result[bytes | None, PersistenceError]: ...
   def put(self, key: str, value: bytes) -> Result[None, PersistenceError]: ...
   ```

**Test file:** `tests/test_infra_protocols.py`

**What to test:**

```python
# test_event_bus_is_protocol -- verify runtime_checkable or Protocol metaclass
# test_attestation_store_is_protocol
# test_transaction_log_is_protocol
# test_state_store_is_protocol
```

These tests verify the Protocol definitions exist and are well-formed. The actual
behavior tests come in Step 14 with the in-memory implementations.

```bash
pytest -x tests/test_infra_protocols.py
mypy --strict attestor/infra/protocols.py
```

**Done when:** All 4 protocol definitions compile under mypy strict. Tests confirm
the classes are Protocols.

---

## Step 14: In-Memory Adapters (F-04 complete) (~220 lines)

**Prerequisites:** Step 13 (infrastructure protocols).

**File:** `attestor/infra/memory_adapter.py`

**What to code:**

In-memory implementations of all four infrastructure protocols. These are test
doubles that let all tests run without Kafka or Postgres. The production adapters
will implement the same protocols later and can be swapped in with zero changes
to domain code.

1. **InMemoryEventBus:**
   Internal storage: `dict[str, list[tuple[str, bytes]]]` keyed by topic.
   - `publish()` appends `(key, value)` to the topic's list; returns `Ok(None)`
   - `subscribe()` is a no-op; returns `Ok(None)`
   - Extra test method: `get_messages(topic: str) -> list[tuple[str, bytes]]`

2. **InMemoryAttestationStore:**
   Internal storage: `dict[str, Attestation[object]]` keyed by content_hash.
   - `store()` inserts; if hash already exists, returns existing hash (idempotent)
   - `retrieve()` looks up by hash; returns `Err(PersistenceError(...))` if not found
   - `exists()` returns `content_hash in self._store`

3. **InMemoryTransactionLog:**
   Internal storage: `list[BitemporalEnvelope[Transaction]]`
   - `append()` appends; returns `Ok(None)`
   - `replay()` returns `Ok(tuple(self._log))` (all entries)
   - `replay_since(since)` filters entries by `e.knowledge_time >= since`

4. **InMemoryStateStore:**
   Internal storage: `dict[str, bytes]`
   - `get(key)` returns `Ok(self._store.get(key))` (Ok(None) if missing)
   - `put(key, value)` stores and returns `Ok(None)`

All four classes are `@final`.

**Test file:** `tests/test_memory_adapter.py`

**What to test:**

```python
# InMemoryEventBus:
# test_publish_and_get_messages -- publish 3 messages, retrieve all 3
# test_publish_multiple_topics -- messages isolated per topic
# test_get_messages_empty_topic -- returns empty list
# test_subscribe_returns_ok

# InMemoryAttestationStore:
# test_store_and_retrieve -- store attestation, retrieve by hash, values match
# test_store_idempotent -- same attestation stored twice, only one copy
# test_retrieve_not_found -- returns Err
# test_exists_true -- after store
# test_exists_false -- before store

# InMemoryTransactionLog:
# test_append_and_replay -- append 3, replay returns 3 in order
# test_replay_preserves_insertion_order
# test_replay_since_filters_by_knowledge_time
# test_replay_empty -- returns Ok(empty tuple)

# InMemoryStateStore:
# test_put_and_get -- store bytes, retrieve same bytes
# test_get_missing_returns_ok_none
# test_put_overwrites_existing

# Protocol compliance (structural subtyping):
# test_event_bus_satisfies_protocol
# test_attestation_store_satisfies_protocol
# test_transaction_log_satisfies_protocol
# test_state_store_satisfies_protocol
```

```bash
pytest -x tests/test_memory_adapter.py
mypy --strict attestor/infra/memory_adapter.py
```

**Done when:** All tests pass. All four in-memory implementations satisfy their
respective protocols (mypy verifies). Attestation store is idempotent: storing
the same attestation twice returns the same hash without creating a duplicate.
Transaction log replay preserves insertion order.

---

## Step 15: Attestation Store Integration Test (IV-01) (~80 lines)

**Prerequisites:** Step 9 (Attestation types), Step 14 (InMemoryAttestationStore).

**File:** `tests/test_integration_attestation_store.py`

**What to code:**

An integration test that exercises the attestation store (deliverable IV-01)
through a realistic workflow. This test proves that all the pieces -- attestation
creation, content hashing, storage, retrieval, and provenance chains -- work
together end-to-end.

**What to test:**

```python
# test_store_firm_attestation_and_retrieve:
#   1. Create a FirmConfidence attestation wrapping a Decimal("155.00")
#   2. Store it in InMemoryAttestationStore
#   3. Retrieve by content_hash
#   4. Assert retrieved.value == Decimal("155.00")
#   5. Assert retrieved.content_hash == original.content_hash

# test_store_quoted_attestation_and_retrieve:
#   Similar with QuotedConfidence (bid=154.90, ask=155.10)

# test_store_derived_attestation_with_provenance:
#   1. Create two Firm attestations (price observations), store them
#   2. Create a Derived attestation (model output) whose provenance
#      references the two Firm attestation hashes
#   3. Store the Derived attestation
#   4. Retrieve it and verify provenance[0] and provenance[1] are valid
#   5. Verify store.exists(provenance[0]) and store.exists(provenance[1])

# test_content_addressing_idempotent:
#   1. Create an attestation
#   2. Store it -- get hash_1
#   3. Store it again -- get hash_2
#   4. Assert hash_1 == hash_2
#   5. Assert only one entry in the store (not duplicated)

# test_retrieve_nonexistent_returns_err:
#   store.retrieve("nonexistent_hash") returns Err

# test_full_provenance_chain_walkable:
#   1. Create and store: firm_1 (Firm)
#   2. Create and store: derived_1 (Derived, provenance=[firm_1.content_hash])
#   3. Create and store: derived_2 (Derived, provenance=[derived_1.content_hash])
#   4. Starting from derived_2, walk the provenance chain:
#      - derived_2.provenance[0] -> retrieve derived_1
#      - derived_1.provenance[0] -> retrieve firm_1
#      - firm_1.provenance is empty (terminal node)
#   5. Every hash in the chain resolves to a stored attestation
```

```bash
pytest -x tests/test_integration_attestation_store.py
```

**Done when:** All 6 tests pass. The provenance chain is walkable from any
derived attestation back to its firm sources. Content addressing is idempotent.
This proves IV-01 (universal attestation store) works correctly.

---

## Step 16: Postgres DDL (3 tables) (~60 lines SQL)

**Prerequisites:** Step 15 (attestation store tested against in-memory adapter).

**Files:**
- `sql/001_attestations.sql`
- `sql/002_event_log.sql`
- `sql/003_schema_registry.sql`

**What to code:**

SQL DDL for the three Phase 0 Postgres tables. These are schema definitions that
document the production persistence layer. No Postgres server is required at this
step -- these files are validated syntactically.

**`sql/001_attestations.sql`:**
```sql
CREATE SCHEMA IF NOT EXISTS attestor;

CREATE TABLE attestor.attestations (
    content_hash    TEXT PRIMARY KEY,
    confidence      TEXT NOT NULL CHECK (confidence IN ('FIRM', 'QUOTED', 'DERIVED')),
    source          TEXT NOT NULL,
    payload         JSONB NOT NULL,
    provenance_refs TEXT[] NOT NULL DEFAULT '{}',
    valid_time      TIMESTAMPTZ NOT NULL,
    system_time     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Append-only: reject UPDATE and DELETE
CREATE OR REPLACE FUNCTION attestor.prevent_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Table % is append-only: % not allowed', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER attestations_no_update
    BEFORE UPDATE OR DELETE ON attestor.attestations
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();

CREATE INDEX idx_attestations_valid_time ON attestor.attestations (valid_time);
CREATE INDEX idx_attestations_system_time ON attestor.attestations (system_time);
CREATE INDEX idx_attestations_confidence ON attestor.attestations (confidence);
```

**`sql/002_event_log.sql`:**
```sql
CREATE TABLE attestor.event_log (
    sequence_id     BIGSERIAL PRIMARY KEY,
    event_type      TEXT NOT NULL,
    payload         JSONB NOT NULL,
    idempotency_key TEXT UNIQUE,
    valid_time      TIMESTAMPTZ NOT NULL,
    system_time     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER event_log_no_update
    BEFORE UPDATE OR DELETE ON attestor.event_log
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();

CREATE INDEX idx_event_log_valid_time ON attestor.event_log (valid_time);
CREATE INDEX idx_event_log_event_type ON attestor.event_log (event_type);
```

**`sql/003_schema_registry.sql`:**
```sql
CREATE TABLE attestor.schema_registry (
    type_name       TEXT NOT NULL,
    version         INTEGER NOT NULL,
    schema_hash     TEXT NOT NULL,
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (type_name, version)
);
```

**What to test:**

Syntactic validation only (no Postgres required):
```bash
python -c "
import pathlib
for f in sorted(pathlib.Path('sql').glob('*.sql')):
    text = f.read_text()
    assert 'CREATE TABLE' in text or 'CREATE SCHEMA' in text, f'{f.name}: missing CREATE'
    print(f'{f.name}: {len(text)} bytes, OK')
"
```

Verify content:
- `attestations` table has `content_hash TEXT PRIMARY KEY`
- `attestations` table has append-only trigger
- `event_log` table has `idempotency_key TEXT UNIQUE`
- `schema_registry` table has composite PK `(type_name, version)`

**Done when:** Three SQL files exist in `sql/`. Each contains the specified
table with correct columns, constraints, and indexes.

---

## Step 17: Kafka Topic Definitions (~40 lines)

**Prerequisites:** Step 13 (infra protocols).

**File:** `attestor/infra/config.py`

**What to code:**

Defines the three Phase 0 Kafka topics as constants and a configuration function.
No Kafka client library is imported -- this is pure configuration data.

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import final

# Phase 0 Kafka topics
TOPIC_EVENTS_RAW: str = "attestor.events.raw"
TOPIC_EVENTS_NORMALIZED: str = "attestor.events.normalized"
TOPIC_ATTESTATIONS: str = "attestor.attestations"

PHASE0_TOPICS: tuple[str, ...] = (
    TOPIC_EVENTS_RAW,
    TOPIC_EVENTS_NORMALIZED,
    TOPIC_ATTESTATIONS,
)

@final
@dataclass(frozen=True, slots=True)
class TopicConfig:
    name: str
    partitions: int
    retention_ms: int  # -1 for infinite retention
    compaction: bool

def phase0_topic_configs() -> tuple[TopicConfig, ...]:
    return (
        TopicConfig(
            name=TOPIC_EVENTS_RAW,
            partitions=6,
            retention_ms=30 * 24 * 3600 * 1000,  # 30 days
            compaction=False,
        ),
        TopicConfig(
            name=TOPIC_EVENTS_NORMALIZED,
            partitions=6,
            retention_ms=90 * 24 * 3600 * 1000,  # 90 days
            compaction=False,
        ),
        TopicConfig(
            name=TOPIC_ATTESTATIONS,
            partitions=6,
            retention_ms=-1,  # Infinite: attestations are never deleted
            compaction=False,
        ),
    )
```

**What to test (add to `tests/test_infra_protocols.py` or a new file):**

```python
# test_phase0_topics_count -- len(PHASE0_TOPICS) == 3
# test_phase0_topic_names -- exact string match for all three
# test_phase0_topic_configs_count -- len(phase0_topic_configs()) == 3
# test_attestations_topic_infinite_retention -- retention_ms == -1
# test_raw_topic_30_day_retention
# test_topic_config_frozen -- cannot assign attributes
```

```bash
pytest -x tests/test_infra_protocols.py
mypy --strict attestor/infra/config.py
```

**Done when:** All tests pass. Three topic configs returned with correct retention
policies. Attestation topic has infinite retention. mypy strict passes.

---

## Step 18: CI Pipeline + Full Verification (~80 lines YAML)

**Prerequisites:** Steps 1-17. This is the capstone step.

**File:** `.github/workflows/ci.yml`

**What to code:**

A GitHub Actions CI pipeline with three stages: lint, test, and verify.

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
              for v in violations:
                  print(v, file=sys.stderr)
              sys.exit(1)
          print('No float in type annotations. PASS.')
          "
      - name: All dataclasses are frozen
        run: |
          python -c "
          import pathlib, re, sys
          for f in pathlib.Path('attestor').rglob('*.py'):
              text = f.read_text()
              for m in re.finditer(r'@dataclass\((.*?)\)', text):
                  args = m.group(1)
                  if 'frozen=True' not in args:
                      print(f'FAIL {f}: @dataclass without frozen=True: {m.group(0)}', file=sys.stderr)
                      sys.exit(1)
          print('All dataclasses frozen. PASS.')
          "
      - name: Import smoke test
        run: |
          python -c "
          from attestor.core import (
              Ok, Err, Result, Money, FrozenMap, BitemporalEnvelope,
              AttestorError, ValidationError, LEI, UTI, ISIN,
              content_hash, ATTESTOR_DECIMAL_CONTEXT, PositiveDecimal,
          )
          from attestor.oracle.attestation import (
              Attestation, FirmConfidence, QuotedConfidence, DerivedConfidence,
              create_attestation,
          )
          from attestor.ledger.transactions import (
              Move, Transaction, StateDelta, LedgerEntry, DistinctAccountPair,
              DeltaValue, DeltaDecimal, DeltaNull,
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
          print('All 40+ types importable. PASS.')
          "
```

**What to test (locally, before pushing):**

Run every verification step from the CI pipeline locally:

```bash
# Stage 1: Lint
mypy --strict attestor/
ruff check attestor/ tests/

# Stage 2: Test
pytest tests/ -x --tb=short -v

# Stage 3: Verify
# 3a. No float
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
print('No float. PASS.')
"

# 3b. All frozen
python -c "
import pathlib, re, sys
for f in pathlib.Path('attestor').rglob('*.py'):
    for m in re.finditer(r'@dataclass\((.*?)\)', f.read_text()):
        if 'frozen=True' not in m.group(1):
            print(f'FAIL {f}: {m.group(0)}', file=sys.stderr); sys.exit(1)
print('All frozen. PASS.')
"

# 3c. All imports
python -c "
from attestor.core import Ok, Err, Money, FrozenMap, LEI, ISIN, content_hash
from attestor.oracle.attestation import Attestation, FirmConfidence
from attestor.ledger.transactions import Move, Transaction, LedgerEntry
from attestor.pricing.types import ValuationResult, Greeks
from attestor.pricing.protocols import StubPricingEngine
from attestor.infra.memory_adapter import InMemoryAttestationStore
from attestor.infra.config import PHASE0_TOPICS
print('All imports. PASS.')
"
```

**Done when:** All five local verification commands pass. CI YAML file exists
at `.github/workflows/ci.yml` and defines lint -> test -> verify stages.

---

## Phase 0 Completion Checklist

Run these checks in sequence. All must pass for Phase 0 to be declared complete.

| # | Check | Command | Expected |
|---|-------|---------|----------|
| 1 | mypy strict, 0 errors | `mypy --strict attestor/` | Exit 0, "Success" |
| 2 | ruff clean | `ruff check attestor/ tests/` | Exit 0, 0 violations |
| 3 | All tests pass | `pytest tests/ -v` | All green |
| 4 | No `float` in type annotations | Float check script | "PASS" |
| 5 | All dataclasses frozen | Frozen check script | "PASS" |
| 6 | All types importable | Import smoke test | "PASS" |
| 7 | Result type works | `pytest tests/test_result.py` | 11+ pass |
| 8 | FrozenMap sorted + immutable | `pytest tests/test_types.py` | All pass |
| 9 | Money uses Decimal only | `pytest tests/test_money.py` | All pass |
| 10 | Errors JSON-serializable | `pytest tests/test_errors.py` | All pass |
| 11 | Content hash deterministic | `pytest tests/test_serialization.py` | All pass |
| 12 | LEI/UTI/ISIN validate | `pytest tests/test_identifiers.py` | All pass |
| 13 | Attestation content-addressed | `pytest tests/test_attestation.py` | All pass |
| 14 | Ledger types enforce invariants | `pytest tests/test_transactions.py` | All pass |
| 15 | Pricing types all Decimal | `pytest tests/test_pricing_types.py` | All pass |
| 16 | Stub satisfies Protocol | `pytest tests/test_pricing_protocols.py` | All pass |
| 17 | Memory adapters work | `pytest tests/test_memory_adapter.py` | All pass |
| 18 | Attestation store E2E | `pytest tests/test_integration_attestation_store.py` | All pass |
| 19 | 3 SQL DDL files exist | `ls sql/*.sql` | 3 files |
| 20 | 3 Kafka topics defined | Topic config tests | 3 topics |
| 21 | CI YAML exists | `ls .github/workflows/ci.yml` | File exists |

**Phase 0 is COMPLETE when all 21 checks pass.**

---

## Dependency Graph

```
Step 1: Scaffold (pyproject.toml + empty packages)
  |
  v
Step 2: Result[T, E]  --------+
  |                             |
  v                             v
Step 3: FrozenMap,           Step 5: Error
  BitemporalEnvelope,          hierarchy
  IdempotencyKey,              |
  EventTime                    |
  |                             |
  v                             v
Step 4: Money,               Step 7: Identifiers
  Decimal context,              (LEI, UTI, ISIN)
  PositiveDecimal,              |
  NonEmptyStr                   |
  |                             |
  v                             v
Step 6: Serialization  <--------+
  (canonical_bytes,              |
   content_hash)                 |
  |                             |
  +-----------------------------+
  |
  v
Step 8: Core __init__.py re-exports (ALL of Steps 2-7)
  |
  +----------+----------+----------+
  |          |          |          |
  v          v          v          v
Step 9:   Step 10:   Step 11:   Step 13:
Oracle/   Ledger/    Pricing/   Infra/
Attesta-  transac-   types.py   protocols.py
tion.py   tions.py     |          |
  |          |          v          v
  |          |       Step 12:   Step 14:
  |          |       Pricing/   Memory
  |          |       protocols  adapter
  |          |          |          |
  +----+-----+----------+----------+
       |
       v
Step 15: Attestation store integration test
       |
       v
Step 16: Postgres DDL (3 SQL files)
       |
       v
Step 17: Kafka topic config
       |
       v
Step 18: CI pipeline + full verification
```

---

## Estimated Line Counts

| Step | File | Production Lines | Test Lines |
|------|------|-----------------|------------|
| 1 | pyproject.toml + __init__.py | ~35 | 0 |
| 2 | core/result.py | ~60 | ~60 |
| 3 | core/types.py | ~100 | ~80 |
| 4 | core/money.py | ~120 | ~90 |
| 5 | core/errors.py | ~120 | ~70 |
| 6 | core/serialization.py | ~80 | ~60 |
| 7 | core/identifiers.py | ~100 | ~70 |
| 8 | core/__init__.py | ~15 | 0 |
| 9 | oracle/attestation.py | ~180 | ~90 |
| 10 | ledger/transactions.py | ~180 | ~100 |
| 11 | pricing/types.py | ~120 | ~70 |
| 12 | pricing/protocols.py | ~80 | ~50 |
| 13 | infra/protocols.py | ~120 | ~30 |
| 14 | infra/memory_adapter.py | ~220 | ~100 |
| 15 | (test only) | 0 | ~80 |
| 16 | sql/ (3 files) | ~60 | 0 |
| 17 | infra/config.py | ~40 | ~30 |
| 18 | .github/workflows/ci.yml | ~80 | 0 |
| **Total** | | **~1,710** | **~980** |

Production code: ~1,710 lines across 14 Python modules + 3 SQL files + 1 YAML.
Test code: ~980 lines across 14 test files.
Test:production ratio: ~0.57 for foundation types. (The ratio grows substantially
as property-based tests and integration tests are added in Phase 1.)

---

## The Monday-to-Friday Schedule

| Day | Steps | What You Have at End of Day |
|-----|-------|-----------------------------|
| **Monday AM** | 1, 2, 3 | Scaffold + Result type + FrozenMap + BitemporalEnvelope |
| **Monday PM** | 4, 5 | Money with Decimal context + full error hierarchy |
| **Tuesday AM** | 6, 7 | Content-addressed serialization + LEI/UTI/ISIN identifiers |
| **Tuesday PM** | 8 | Core package fully assembled, all 6 core modules tested |
| **Wednesday AM** | 9 | Attestation with 3 structured confidence types |
| **Wednesday PM** | 10 | Ledger domain types (Move, Transaction, LedgerEntry, StateDelta) |
| **Thursday AM** | 11, 12 | Pricing interface types + protocols + stub engine |
| **Thursday PM** | 13, 14 | Infrastructure protocols + all 4 in-memory adapters |
| **Friday AM** | 15, 16, 17 | Attestation store integration test + DDL + Kafka config |
| **Friday PM** | 18 | CI pipeline green. Phase 0 COMPLETE. |

A senior Python developer follows this sequence step by step, running tests at
every checkpoint. By Friday afternoon they have:

- 14 Python modules with every type frozen, slotted, and final
- Every fallible function returns Result, not exceptions
- No float in any type annotation
- No dict in any domain type (FrozenMap everywhere)
- Content-addressed attestations with structured epistemic payloads
- In-memory adapters for all infrastructure protocols
- Provenance chains walkable from derived attestations to firm sources
- 3 Postgres table schemas (append-only with triggers)
- 3 Kafka topic configurations (attestations with infinite retention)
- A CI pipeline that enforces all invariants on every push

Phase 1 (Equity Cash -- full lifecycle) can begin Monday of the following week.
