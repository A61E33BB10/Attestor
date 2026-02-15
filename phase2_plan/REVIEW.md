# Phase 2 Collective Review — Listed Derivatives

**Date:** 2026-02-15
**Reviewers:** Minsky, Formalis, FinOps, Gatheral, TestCommittee, Geohot
**Scope:** Phase 2 implementation vs `phase2_plan/PLAN.md`
**Test Suite:** 160 tests across 12 files, all passing (0.64s)
**mypy --strict:** 7 source files, 0 issues

---

## Overall Verdict

| Agent | Verdict | Key Finding |
|-------|---------|-------------|
| **Geohot** | PASS | All 6 CUTS respected, no violations |
| **Minsky** | CONDITIONAL PASS | `case _:` wildcard in MiFID II match (F4 violation) |
| **Formalis** | CONDITIONAL PASS | CL-D2, CS-D2 missing; direct `Move()` bypass |
| **FinOps** | CONDITIONAL PASS | All 6 FinOps conditions met; hardcoded "USD" |
| **Gatheral** | CONDITIONAL PASS | All 7 Gatheral conditions met; Move/PositiveDecimal bypass |
| **TestCommittee** | CONDITIONAL FAIL | 3 invariants missing, 2 Hypothesis tests missing |

**Collective Verdict: CONDITIONAL PASS** — Core architecture, domain logic, and conservation laws are correct. All agent-specific conditions from the plan are met. Gaps are in test coverage (missing invariants), type safety discipline (constructor bypass), and a hardcoded currency.

---

## What Was Delivered

### Architecture (Unanimous PASS)
- **Parametric polymorphism preserved**: `engine.py` contains zero derivative-specific keywords. Verified by automated test (`TestEngineUntouched`).
- **`@final @dataclass(frozen=True, slots=True)`** on all domain types
- **Smart constructors**: `OptionPayoutSpec.create()`, `FuturesPayoutSpec.create()`, `OptionDetail.create()`, `FuturesDetail.create()` all return `Ok[T] | Err[str]`
- **`EquityDetail` marker type** (Minsky F1): Explicit dataclass with no fields, used as default on `CanonicalOrder` instead of `None`
- **Enums not strings** (Minsky F2): `OptionType`, `OptionStyle`, `SettlementType`, `MarginType` are all `Enum` classes

### Ledger Functions (PASS — all conservation laws hold)
- **Premium**: 2 Moves (cash + position), formula `price * qty * multiplier`
- **Physical exercise**: 3 Moves (cash + securities + position close), CALL/PUT direction correct
- **Cash settlement**: 2 Moves (cash + position close), OTM guard rejects ATM (strict inequality)
- **Expiry**: 1 Move (position close, no cash)
- **Futures open**: 1 Move (short → long position)
- **Variation margin**: Standard mark-to-market `(P_t - P_{t-1}) * contract_size * qty`, zero returns `Err`
- **Futures expiry**: Final margin (if non-zero) + position close

### Reporting & Infrastructure (PASS)
- **MiFID II**: Discriminated union `InstrumentReportFields = OptionReportFields | FuturesReportFields | None`
- **GL Projection**: Pure read-only, `trial_balance()` returns `Ok[Decimal] | Err[str]`
- **SQL**: 3 files with `attestor.*` schema prefix, `prevent_mutation()` triggers on all tables
- **Kafka topics**: 5 Phase 2 topics with correct retention and replication

### Test Coverage
- 160 tests across 12 files (plan target: ~165)
- 3 Hypothesis property-based tests (plan target: 5)
- All conservation laws verified through engine execution

---

## Consolidated Gaps

### CRITICAL (1)

**GAP-C1: Direct `Move()` and `PositiveDecimal()` constructor bypass**
- *Raised by:* Formalis (CRITICAL), Gatheral (HIGH), FinOps (LOW), Minsky (LOW-MEDIUM)
- *Location:* `options.py` lines 156-175, 257, 260-264; `futures.py` lines 168-175
- *Issue:* `create_premium_transaction` correctly uses `Move.create()` and `PositiveDecimal.parse()`, but `create_exercise_transaction`, `create_cash_settlement_exercise_transaction`, and `create_futures_expiry_transaction` construct `Move(...)` and `PositiveDecimal(value=...)` directly, bypassing F-HIGH-01 (source != destination) and positivity validation.
- *Fix:* Replace all direct constructions with validated factories, propagate `Err` cases.

### HIGH (3)

**GAP-H1: CL-D2 (Exercise Conservation) — missing dedicated invariant test**
- *Raised by:* Formalis (HIGH), TestCommittee (CRITICAL), FinOps (MEDIUM)
- *Issue:* No `TestCLD2ExerciseConservation` class in `test_invariants_derivatives.py`. Exercise conservation is tested in `test_options.py` unit tests but not in the invariant file with Hypothesis.
- *Fix:* Add CL-D2 test with Hypothesis (random strike, qty, multiplier, settlement_price).

**GAP-H2: CS-D2 (Futures Master Square) — missing invariant test**
- *Raised by:* Formalis (HIGH), TestCommittee (HIGH), FinOps (INFO)
- *Issue:* No `TestCSD2FuturesMasterSquare` class. File jumps from CS-D1 (option) to CS-D3 (MiFID II).
- *Fix:* Add CS-D2 test: `price(book(futures)) == book(price(futures))`.

**GAP-H3: Wildcard `case _:` in MiFID II match (Minsky F4 violation)**
- *Raised by:* Minsky (HIGH)
- *Location:* `mifid2.py` line 138
- *Issue:* Match on `order.instrument_detail` uses bare `case _:` instead of explicit `EquityDetail()` branch + `assert_never`. New `InstrumentDetail` variants silently produce `None` report fields.
- *Fix:* Replace `case _:` with `case EquityDetail(): inst_fields = None` and add `case _ as unreachable: assert_never(unreachable)`.

### MEDIUM (6)

**GAP-M1: Hardcoded "USD" in futures margin functions**
- *Raised by:* Formalis (MEDIUM), FinOps (MEDIUM), Gatheral (HIGH)
- *Location:* `futures.py` lines 109, 169
- *Fix:* Add `currency: str` parameter to `create_variation_margin_transaction` and `create_futures_expiry_transaction`.

**GAP-M2: Missing ISIN field on `MiFIDIIReport`**
- *Raised by:* Minsky (MEDIUM), Gatheral (MEDIUM)
- *Issue:* Plan specifies `isin: ISIN | None` on `MiFIDIIReport`, but implementation omits it.

**GAP-M3: No implied volatility validation bounds**
- *Raised by:* Gatheral (MEDIUM)
- *Issue:* `ingest_option_quote` accepts implied vol without checking positivity, bid <= ask spread, or upper bounds.

**GAP-M4: Missing Hypothesis property-based Master Square test**
- *Raised by:* Formalis (MEDIUM), TestCommittee (MEDIUM)
- *Issue:* Plan specifies "Property-based (Hypothesis 200): random (price, qty, strike) Master Square" — absent.

**GAP-M5: Non-exhaustive match in `gateway/types.py`**
- *Raised by:* Minsky (MEDIUM)
- *Issue:* `CanonicalOrder.create()` match on `instrument_detail` only handles 3 of 5 variants (missing FXDetail, IRSwapDetail from Phase 3 extension).

**GAP-M6: `assert_never` not used anywhere in production code**
- *Raised by:* Minsky (MEDIUM)
- *Issue:* No production match statement uses `assert_never` for exhaustiveness enforcement.

### LOW (5)

- **GAP-L1:** `create_variation_margin_transaction` returns `Err[str]` not `Err[ValidationError]` (Minsky)
- **GAP-L2:** Variable naming stutter `total_cr_total` in GL projection (Formalis, FinOps)
- **GAP-L3:** `instrument_id` parameter unused in some futures functions (FinOps)
- **GAP-L4:** `FuturesDetail` lacks `last_trading_date` (present on `FuturesPayoutSpec` only) (Gatheral)
- **GAP-L5:** Missing ATM boundary test for cash-settled exercise (Gatheral)

---

## Geohot Simplicity Report

All 6 CUTS from Phase 2 respected:

| CUT | Rule | Status |
|-----|------|--------|
| CUT-1 | One file for derivative types (`derivative_types.py`) | PASS |
| CUT-2 | No `tick_size` field | PASS |
| CUT-3 | One file for all option functions (`options.py`) | PASS |
| CUT-4 | One transition table (alias, not copy) | PASS |
| CUT-5 | No `scenarios.sql` | PASS |
| CUT-6 | Merged invariant tests (one file) | PASS |

~121 lines of Phase 3 forward-engineering in Phase 2 files noted (FXDetail, IRSwapDetail in `derivative_types.py`; FixingPI, NettingPI, MaturityPI in `lifecycle.py`). Acceptable since Phase 3 is now complete.

---

## Recommendations

### Must-fix before production
1. Replace all direct `Move()` with `Move.create()` and `PositiveDecimal(value=...)` with `PositiveDecimal.parse()` (GAP-C1)
2. Add CL-D2 and CS-D2 invariant tests (GAP-H1, GAP-H2)
3. Replace `case _:` with explicit branches + `assert_never` in MiFID II match (GAP-H3)

### Should-fix
4. Add `currency` parameter to futures margin functions (GAP-M1)
5. Add `isin` field to `MiFIDIIReport` (GAP-M2)
6. Add Hypothesis property-based Master Square test (GAP-M4)
7. Add `assert_never` to all production match statements (GAP-M6)
