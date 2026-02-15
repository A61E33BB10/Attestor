# Phase 3 Collective Review — FX and Rates / Multi-Currency Ledger

**Date:** 2026-02-15
**Reviewers:** Minsky, Formalis, FinOps, Gatheral, TestCommittee, Geohot
**Scope:** Phase 3 implementation vs `phase3_plan/PLAN.md`
**Test Suite:** 918 tests across 25+ files, all passing (4.40s); 242 new Phase 3 tests
**mypy --strict:** 11 Phase 3 source files, 0 issues

---

## Overall Verdict

| Agent | Verdict | Key Finding |
|-------|---------|-------------|
| **Geohot** | CONDITIONAL PASS | 3 CUTs pass; Minsky conditions fail (str vs enum/refined type) |
| **Minsky** | CONDITIONAL PASS | `FXDetail.currency_pair` is `str` not `CurrencyPair`; `IRSwapDetail` enums are strings |
| **Formalis** | CONDITIONAL PASS | 3 HIGH: Move bypass, float precision, `calibrate_and_gate` missing |
| **FinOps** | CONDITIONAL PASS | Float contamination in YC; FXDetail/IRSwapDetail type gaps; calibration pipeline incomplete |
| **Gatheral** | CONDITIONAL PASS | Bootstrap ignores `instrument_type`; FXDetail `str`; core financial math is correct |
| **TestCommittee** | CONDITIONAL PASS | 242/328 tests (73.8%); CS-F3 missing; `create_irs_maturity_transaction` untested |

**Collective Verdict: CONDITIONAL PASS** — Core financial mathematics, conservation laws, and parametric polymorphism are correct. All 918 tests pass. The engine remains untouched. Gaps are in type safety (`str` vs refined types), missing pipeline functions (`calibrate_and_gate`, `create_irs_maturity_transaction`), and test coverage shortfall.

---

## What Was Delivered

### Architecture (Unanimous PASS)
- **Parametric polymorphism preserved**: `engine.py` contains zero FX/IRS keywords. Verified by automated test (`TestEngineUntouched`).
- **`@final @dataclass(frozen=True, slots=True)`** on all new domain types
- **Smart constructors**: `FXSpotPayoutSpec.create()`, `FXForwardPayoutSpec.create()`, `NDFPayoutSpec.create()`, `IRSwapPayoutSpec.create()`, `FXDetail.create()`, `IRSwapDetail.create()`, `YieldCurve.create()`, `ModelConfig.create()` — all return `Ok[T] | Err[str]`
- **Enums not strings** at PayoutSpec level: `DayCountConvention`, `PaymentFrequency`, `SwapLegType` are proper `Enum` classes in `fx_types.py`
- **`CurrencyPair` refined type** exists in `money.py` with ISO 4217 validation

### FX Settlement (PASS — all conservation laws hold)
- **FX Spot**: 2 Moves (base + quote currencies), sigma(BASE)=0, sigma(QUOTE)=0
- **FX Forward**: Delegates to spot settlement at forward rate
- **NDF**: 1 Move (cash settled), formula `notional * (fixing_rate - forward_rate) / fixing_rate` (correct standard market convention)
- **Zero fixing rate** rejected; zero settlement amount handled as edge case

### IRS Cashflow Booking (PASS — conservation correct)
- **Fixed leg**: `amount = notional * rate * dcf` — standard formula
- **Float leg**: Amounts initially zero until `apply_rate_fixing()` applies
- **Day count fractions**: ACT/360, ACT/365, 30/360 — all match ISDA definitions
- **Negative rates permitted** — correct for European rates markets (EURIBOR, ECB deposit)

### Yield Curve & Arbitrage Gates (PASS with findings)
- **Bootstrap**: `D(t) = 1/(1 + r*t)` — correct for money market deposits
- **Log-linear interpolation**: Ensures positive interpolated discount factors (structural AF-YC-01)
- **Forward rate**: `f(t1,t2) = -ln(D(t2)/D(t1)) / (t2-t1)` — standard formula
- **7 arbitrage gates**: AF-YC-01 through AF-YC-05, AF-FX-01, AF-FX-02 — all implemented
- **CIP check**: `|F/S - D_dom/D_for| < tolerance` — textbook covered interest parity

### Oracle Ingestion (PASS)
- **FXRate** with `PositiveDecimal` rate and `QuotedConfidence` (bid/ask)
- **RateFixing** with plain `Decimal` rate (negative rates permitted)
- **Attestation provenance** fully populated (content_hash, source, timestamp)

### Lifecycle Extensions (PASS)
- **FixingPI, NettingPI, MaturityPI**: All frozen/final/slotted
- **PrimitiveInstruction**: 10-variant union
- **FX_TRANSITIONS, IRS_TRANSITIONS**: 5-edge tables matching equity pattern

### Reporting & Infrastructure (PASS)
- **MiFID II**: `FXReportFields`, `IRSwapReportFields` added to discriminated union
- **EMIR**: FX and IRS orders project correctly
- **SQL**: 5 files with `attestor.*` prefix, `prevent_mutation()` triggers, bitemporal columns
- **Kafka**: 5 Phase 3 topics with correct retention and replication
- **INV-R01 verified**: Reporting is projection, not transformation

### Test Coverage
- 242 new Phase 3 tests (plan target: ~328, delivery: 73.8%)
- 3 Hypothesis property-based tests with `max_examples=200` (CL-F1, CL-F4, FX spot conservation)
- All 6 conservation laws verified (CL-F1 through CL-F6)
- All 4 arbitrage-freedom invariants verified (INV-AF-01 through INV-AF-04)
- 4 of 5 commutativity squares verified (CS-F1, CS-F2, CS-F4, CS-F5)
- 3 full lifecycle integration tests (FX Spot, NDF, IRS)

---

## Consolidated Gaps

### CRITICAL (2)

**GAP-P3-C1: `FXDetail.currency_pair` is bare `str`, not `CurrencyPair`**
- *Raised by:* Minsky (CRITICAL), Gatheral (HIGH), FinOps (HIGH), Formalis (MEDIUM), Geohot (FAIL)
- *Location:* `derivative_types.py` line 263
- *Issue:* `CurrencyPair` refined type exists in `money.py` with ISO 4217 validation, but `FXDetail` stores currency pair as bare `str`. Downstream `fx_settlement.py` does fragile string splitting `cp.split("/")[0]`. A malformed string silently corrupts Move units.
- *Fix:* Change `FXDetail.currency_pair` to `CurrencyPair`. Update `.create()` to use `CurrencyPair.parse()`. Update `fx_settlement.py` to use `.base.value` and `.quote.value`.

**GAP-P3-C2: `IRSwapDetail.day_count` and `payment_frequency` are bare `str`, not enums**
- *Raised by:* Minsky (CRITICAL), FinOps (HIGH), Formalis (MEDIUM), Geohot (FAIL)
- *Location:* `derivative_types.py` lines 314-315
- *Issue:* `DayCountConvention` and `PaymentFrequency` enums exist in `fx_types.py`, but `IRSwapDetail` uses bare strings. An invalid `day_count` like `"ACT/720"` passes the smart constructor unchecked.
- *Fix:* Change `day_count: str` to `day_count: DayCountConvention`, `payment_frequency: str` to `payment_frequency: PaymentFrequency`.

### HIGH (5)

**GAP-P3-H1: Direct `Move()` and `Transaction()` constructor bypass**
- *Raised by:* Formalis (HIGH), Minsky (HIGH), FinOps (MEDIUM), Gatheral (MEDIUM), Geohot (FAIL)
- *Location:* `fx_settlement.py` lines 119-133, 253-273; `irs.py` lines 253-258
- *Issue:* `Move.create()` enforces `source != destination` and non-empty strings. All Phase 3 settlement code calls `Move(...)` directly. A Move with `source == destination` would be a silent no-op. NDF zero-settlement creates `Transaction(moves=())` which `Transaction.create()` would reject.
- *Fix:* Replace all direct `Move(...)` with `Move.create(...)` and `Transaction(...)` with `Transaction.create(...)`. Propagate `Err` cases.

**GAP-P3-H2: `calibrate_and_gate` pipeline function not implemented**
- *Raised by:* ALL 6 agents (Formalis HIGH, Minsky MEDIUM, FinOps HIGH, Gatheral MEDIUM, TestCommittee HIGH, Geohot FAIL)
- *Location:* Absent from `calibration.py`
- *Issue:* Plan Step 9 specifies `calibrate_and_gate()` composing bootstrap + arbitrage gates + publish/fallback into one atomic operation. Without it, callers must manually chain these steps.
- *Fix:* Implement `calibrate_and_gate` as specified.

**GAP-P3-H3: `CalibrationResult` missing `arbitrage_checks` field**
- *Raised by:* Minsky (MEDIUM), Formalis (MEDIUM), FinOps (HIGH), Geohot (FAIL)
- *Location:* `calibration.py` lines 297-303
- *Issue:* Plan specifies `arbitrage_checks: tuple[ArbitrageCheckResult, ...]`. Implementation omits it, breaking the auditability chain from calibration to gate results.
- *Fix:* Add the field.

**GAP-P3-H4: `FailedCalibrationRecord` missing `failed_checks` field**
- *Raised by:* Minsky (MEDIUM), Formalis (MEDIUM), FinOps (HIGH), Geohot (FAIL)
- *Location:* `calibration.py` lines 306-313
- *Issue:* Plan specifies `failed_checks: tuple[ArbitrageCheckResult, ...]`. Implementation omits it. Calibration failures lack forensic detail.
- *Fix:* Add the field. Ensure `handle_calibration_failure` creates a `FailedCalibrationRecord`.

**GAP-P3-H5: Bootstrap ignores `instrument_type` — simple interest for all instruments**
- *Raised by:* Gatheral (HIGH)
- *Location:* `calibration.py` line 218
- *Issue:* `D(t) = 1/(1 + r*t)` is correct for deposits (< 1Y), but applied to swaps (> 1Y). For a 5Y swap at 5%, this gives D(5) = 0.80 vs correct ~0.78 — a 2.5% error. The `RateInstrument.instrument_type` field is dead code.
- *Fix:* Implement instrument-type-aware bootstrapping (simple interest for deposits, par swap stripping for swaps), or document that only deposits are supported and validate.

### MEDIUM (12)

**GAP-P3-M1: `float()` contamination in yield curve interpolation**
- *Raised by:* Formalis (HIGH), Minsky (HIGH), FinOps (CRITICAL), Gatheral (LOW), Geohot (FAIL)
- *Location:* `calibration.py` lines 139-153, 176; `arbitrage_gates.py` lines 130-133
- *Issue:* `Decimal` → `float` → `math.log/exp` → `str` → `Decimal` round-trip introduces ~1e-16 relative error. Acceptable for stubs but architecturally inconsistent with the system's `Decimal` precision guarantee.
- *Fix:* Document as known exception, or use `mpmath` / pure-Decimal `ln()` helper.

**GAP-P3-M2: `create_irs_maturity_transaction` not implemented**
- *Raised by:* Formalis (MEDIUM), FinOps (MEDIUM), TestCommittee (HIGH), Geohot (FAIL)
- *Location:* Absent from `irs.py`
- *Issue:* Plan Step 6 specifies this function for closing IRS positions at maturity. The IRS lifecycle cannot formally terminate without it.
- *Fix:* Implement as zero-Move Transaction that records position closure.

**GAP-P3-M3: CS-F3 (Reporting naturality) not tested**
- *Raised by:* Formalis (MEDIUM), TestCommittee (HIGH)
- *Location:* Absent from `test_invariants_fx_irs.py`
- *Issue:* 1 of 5 commutativity squares missing: `project(lifecycle(I)) == project_update(project(I), event)`.
- *Fix:* Add CS-F3 test.

**GAP-P3-M4: `check_arbitrage_freedom` dispatch function not implemented**
- *Raised by:* Formalis (MEDIUM), Geohot (FAIL)
- *Location:* Absent from `arbitrage_gates.py`
- *Issue:* Plan specifies single-dispatch function routing by `ArbitrageCheckType`. Callers must currently know which specific check to call.

**GAP-P3-M5: AF-YC-05 computes first derivative, not second derivative**
- *Raised by:* Gatheral (MEDIUM), Geohot (FAIL)
- *Location:* `arbitrage_gates.py` lines 129-135
- *Issue:* Code computes `|f[i+1] - f[i]| / dt` (first derivative) but comments say "second derivative." For f''(t) you need `|f[i+2] - 2*f[i+1] + f[i]| / dt^2`.
- *Fix:* Implement actual second derivative, or rename to "gradient check."

**GAP-P3-M6: `dateutil` external dependency**
- *Raised by:* Formalis (MEDIUM), FinOps (LOW), Geohot (FAIL)
- *Location:* `irs.py` line 13
- *Issue:* Plan states "No external library additions. Python stdlib only." `dateutil` is third-party.
- *Fix:* Replace `relativedelta(months=N)` with stdlib date arithmetic.

**GAP-P3-M7: Flat extrapolation beyond last tenor**
- *Raised by:* Formalis (MEDIUM), FinOps (MEDIUM), Gatheral (MEDIUM)
- *Location:* `calibration.py` lines 142-144
- *Issue:* `D(T) = D(T_max)` for `T > T_max` implies zero forward rate beyond curve. Economically incorrect.
- *Fix:* Use log-linear or flat-forward extrapolation.

**GAP-P3-M8: `handle_calibration_failure` trivially thin**
- *Raised by:* Formalis (MEDIUM), FinOps (MEDIUM)
- *Location:* `calibration.py` lines 316-328
- *Issue:* Plan requires: create `FailedCalibrationRecord`, check staleness, degrade confidence. Implementation just returns `Ok(last_good)`.

**GAP-P3-M9: `bootstrap_curve` uses `datetime.now()` — non-deterministic**
- *Raised by:* Formalis (MEDIUM), Gatheral (LOW), Geohot (FAIL)
- *Location:* `calibration.py` line 257
- *Issue:* Attestation timestamp is generated internally, making function impure. Should be a parameter.

**GAP-P3-M10: Triangular arbitrage only checks sorted triplet direction**
- *Raised by:* Gatheral (MEDIUM), FinOps (MEDIUM)
- *Location:* `arbitrage_gates.py` lines 168-188
- *Issue:* Only finds cycles where quote directions match sorted order. In production, FX rates follow market convention (EUR/USD, USD/JPY), not alphabetical. Should check inverse rates.

**GAP-P3-M11: Zero-sentinel for unfixed IRS cashflows**
- *Raised by:* FinOps (MEDIUM)
- *Location:* `irs.py` line 168
- *Issue:* `amount == Decimal("0")` used as "unfixed" sentinel. A zero-rate fixing would produce zero amount, indistinguishable from unfixed. Should use `is_fixed: bool` or `amount: Decimal | None`.

**GAP-P3-M12: MiFID II and Gateway match statements non-exhaustive**
- *Raised by:* Minsky (HIGH for both)
- *Location:* `mifid2.py` line 138 (`case _:`), `gateway/types.py` lines 150-166
- *Issue:* MiFID II uses wildcard `case _:` instead of explicit `EquityDetail()` + `assert_never`. Gateway handles only 3 of 5 `InstrumentDetail` variants.
- *Fix:* Add explicit cases and `assert_never` terminators.

### LOW (9)

- **GAP-P3-L1:** `unwrap()` in production code (`arbitrage_gates.py` line 56) — should use match/case (Minsky)
- **GAP-P3-L2:** `assert_never` not used anywhere in production (Minsky)
- **GAP-P3-L3:** Test count 242/328 (73.8%) — shortfalls in `test_fx_settlement`, `test_irs`, `test_calibration`, `test_integration` (TestCommittee)
- **GAP-P3-L4:** CL-F2, CL-F3 conservation tests are example-based, not Hypothesis (TestCommittee, Formalis)
- **GAP-P3-L5:** `FXReportFields.currency_pair` is bare `str` — follows upstream `FXDetail` (Minsky)
- **GAP-P3-L6:** IRSwapPayoutSpec forces both legs to same day count and frequency (Gatheral)
- **GAP-P3-L7:** Unused `source_fn` parameter in `_validate_accounts` (Geohot)
- **GAP-P3-L8:** Missing `AF-FX-03` check (`F(0) = S` at t=0) (Gatheral)
- **GAP-P3-L9:** Missing `NETTING` account type (FinOps)

---

## Geohot Simplicity Report

All 3 Phase 3 CUTs respected:

| CUT | Rule | Status |
|-----|------|--------|
| CUT-1 | Merge FX spot/forward into one `FXDetail` | PASS |
| CUT-2 | One `calibration.py` not three files | PASS |
| CUT-3 | Oracle ingest in one file | PASS |

Line counts: 2,191 total Phase 3 lines vs ~1,890 budget (+301, 16% over). `fx_settlement.py` is 83% over its individual budget (275 vs 150) due to `ValidationError` boilerplate.

---

## Recommendations

### Must-fix before production
1. Change `FXDetail.currency_pair` from `str` to `CurrencyPair` (GAP-P3-C1)
2. Change `IRSwapDetail.day_count`/`payment_frequency` from `str` to enums (GAP-P3-C2)
3. Replace all direct `Move()`/`Transaction()` with validated factories (GAP-P3-H1)
4. Implement `calibrate_and_gate` pipeline (GAP-P3-H2)
5. Add `arbitrage_checks`/`failed_checks` fields (GAP-P3-H3, H4)

### Should-fix
6. Implement `create_irs_maturity_transaction` (GAP-P3-M2)
7. Add CS-F3 reporting naturality test (GAP-P3-M3)
8. Fix AF-YC-05 to compute actual second derivative (GAP-P3-M5)
9. Remove `dateutil` dependency (GAP-P3-M6)
10. Add explicit match branches + `assert_never` in MiFID/Gateway (GAP-P3-M12)
11. Document or remediate `float()` in calibration (GAP-P3-M1)
12. Fix flat extrapolation beyond last tenor (GAP-P3-M7)
