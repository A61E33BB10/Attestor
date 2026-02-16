# Phase 4 -- Credit and Structured Products: Collective Review

**Date:** 2026-02-16
**Status:** PASS_WITH_GAPS (all 7 agents)
**Build:** 1389 tests passing, mypy --strict clean, ruff clean

---

## Agent Verdicts

| Agent | Role | Verdict | CRITICAL | HIGH | MEDIUM | LOW |
|-------|------|---------|----------|------|--------|-----|
| **Minsky** | Type safety | PASS_WITH_GAPS | 0 | 1 | 3 | 5 |
| **Formalis** | Invariants (56) | PASS_WITH_GAPS | 0 | 0 | 3 | 4 |
| **Gatheral** | Financial math | PASS_WITH_GAPS | 0 | 2 | 4 | 3 |
| **FinOps** | Financial ops | PASS_WITH_GAPS | 2 | 3 | 4 | 4 |
| **TestCommittee** | Tests (1389) | PASS_WITH_GAPS | 3 | 4 | 3 | 2 |
| **Geohot** | Simplicity | PASS_WITH_GAPS | 0 | 2 | 3 | 3 |
| **Karpathy** | Build sequence | PASS_WITH_GAPS | 0 | 0 | 1 | 5 |

---

## CRITICAL Gaps (must fix)

### GAP-FO-01: CDS credit event settlement incomplete
**Source:** FinOps
**File:** `attestor/ledger/cds.py`
Only the protection payment Move is created. Missing: accrued premium leg (buyer->seller) and position close leg (buyer_position->seller_position). The spec mandates all three in a single atomic Transaction. Without the position close, the CDS position remains open after a credit event.

### GAP-FO-02: CDS trade booking function missing
**Source:** FinOps
**File:** `attestor/ledger/cds.py`
No `create_cds_trade_transaction` function exists. The spec requires a position-opening transaction at inception (seller->buyer). Without this, the CDS lifecycle cannot begin correctly.

### GAP-TC-01: Hypothesis test count 8/26 (69% shortfall)
**Source:** TestCommittee
18 planned property-based tests are missing. Only 8 `@given` tests exist across Phase 4. Missing: swaption conservation properties, SVI random input validation, credit curve monotonicity, gateway idempotency, decimal arithmetic round-trips.

### GAP-TC-02: max_examples=50 in test_cds_ledger.py
**Source:** TestCommittee
Both CDS Hypothesis tests use `max_examples=50` instead of the agreed 200.

### GAP-TC-03: Integration test shortfall (33/55)
**Source:** TestCommittee
Missing: multi-instrument portfolio lifecycle, error propagation across boundaries, cross-instrument conservation.

---

## HIGH Gaps (should fix)

### GAP-M-01: SwaptionExercisePI admits illegal states
**Source:** Minsky
`settlement_amount: Money | None` and `underlying_irs_id: NonEmptyStr | None` are independently optional, permitting 4 states (2 valid, 2 illegal). Should use a sum type `CashSettlement | PhysicalSettlement`.

### GAP-G-02: AF-CR-05 (ISDA re-pricing consistency) not implemented
**Source:** Gatheral
Plan specifies re-pricing verification within 0.5 bps tolerance. Not implemented; noted as deferred to Phase 5 in BUILD_SEQUENCE.md but listed as in-scope in CONSENSUS.md.

### GAP-G-04: implied_vol uses nearest-expiry snapping, not interpolation
**Source:** Gatheral
The function divides total variance from one expiry slice by a different requested expiry, which is mathematically incorrect for between-slice queries. Plan specifies linear interpolation in total variance.

### GAP-FO-03: Kafka topic retention/cleanup policy incorrect
**Source:** FinOps
vol_surfaces and credit_curves topics use 90-day retention with `compact` cleanup instead of spec's infinite retention with `delete`. Compact allows key deduplication, losing historical calibrations.

### GAP-FO-04: EMIR report missing CDS/swaption-specific fields
**Source:** FinOps
`project_emir_report` produces generic reports without the 10 CDS-specific ESMA RTS fields.

### GAP-FO-05: compute_margin_call function not implemented
**Source:** FinOps
Margin call computation logic (exposure - threshold, MTA, rounding) does not exist.

### GAP-FO-08: Dodd-Frank notional may be incorrect for CDS
**Source:** FinOps
`notional = order.quantity.value * order.price` may produce annual premium, not the regulatory notional.

### GAP-S-04: 8 unused parameters across ledger functions
**Source:** Geohot
`instrument_id` in 5 CDS/swaption functions and `agreement_id` in 3 collateral functions are accepted but never used.

### GAP-S-05: ValidationError boilerplate (53 instances)
**Source:** Geohot
Identical ~10-line wrapping pattern repeated 53 times across cds.py, swaption.py, collateral.py. Extract a shared helper.

### GAP-TC-H1: Missing commutativity square tests CS-C1 through CS-C4
**Source:** TestCommittee

### GAP-TC-H2: No calibrate_vol_surface function or test
**Source:** TestCommittee, Karpathy (GAP-K-01)
The build sequence specified a grid-search SVI calibration function. Neither function nor test exists.

### GAP-TC-H3: No Durrleman butterfly failure mode test
**Source:** TestCommittee

---

## MEDIUM Gaps

| ID | Source | Description |
|----|--------|-------------|
| GAP-M-02 | Minsky | CDSQuote has no smart constructor |
| GAP-M-03 | Minsky | CDSSpreadQuote has no smart constructor |
| GAP-M-05 | Minsky | CanonicalOrder.create match non-exhaustive (pre-existing) |
| GAP-M-11 | Minsky | decimal_math.py uses bare `raise ValueError` |
| GAP-G-01 | Gatheral | Credit curve uses zero-coupon approximation, not ISDA standard |
| GAP-G-06 | Gatheral | CDS credit event settlement missing accrued premium |
| GAP-G-08 | Gatheral | Roger Lee AF-VS-03/04 severity should be CRITICAL not HIGH |
| GAP-G-09 | Gatheral | ATM monotonicity AF-VS-06 severity should be CRITICAL not HIGH |
| GAP-G-10 | Gatheral | SSVI not implemented (agreed deferral per DR-2) |
| GAP-F-01 | Formalis | CL-C9 (value preservation) not tested |
| GAP-F-03 | Formalis | AF-CR-05 deferred but listed in scope |
| GAP-F-07 | Formalis | float usage in AF-YC-05 (pre-existing Phase 3) |
| GAP-FO-06 | FinOps | HaircutSchedule/CollateralItem types not implemented |
| GAP-FO-10 | FinOps | SQL 021_credit_events schema incomplete |
| GAP-FO-11 | FinOps | SQL 020_collateral missing quantity >= 0 CHECK |
| GAP-FO-13 | FinOps | MiFID II CDSReportFields missing restructuring_type |
| GAP-S-03 | Geohot | decimal_math.py 71% over line budget (257 vs ~150) |
| GAP-S-06 | Geohot | swaption exercise_close and expiry_close are identical |
| GAP-S-08 | Geohot | credit_ingest.py repetitive validation pattern |
| GAP-TC-M1 | TestCommittee | Pricing tests use StubPricingEngine only |
| GAP-TC-M2 | TestCommittee | No negative-path lifecycle integration |
| GAP-TC-M3 | TestCommittee | SQL tests are existence-only |

---

## LOW Gaps

| ID | Source | Description |
|----|--------|-------------|
| GAP-M-04 | Minsky | ScheduledCDSPremium no smart constructor |
| GAP-M-06 | Minsky | CreditEventPI.auction_price raw Decimal |
| GAP-M-07 | Minsky | CollateralCallPI uses NonEmptyStr not CollateralType |
| GAP-M-08 | Minsky | mifid2.py wildcard `case _:` for EquityDetail |
| GAP-M-09 | Minsky | AuctionResult/CreditEventRecord no smart constructors |
| GAP-F-02 | Formalis | CL-C10 phantom invariant (spec inconsistency) |
| GAP-F-04 | Formalis | CS-C1/C2 not explicitly tested |
| GAP-F-05 | Formalis | CS-C4 implicit only |
| GAP-F-06 | Formalis | CS-C7/C8/C9 phantom (spec inconsistency) |
| GAP-G-05 | Gatheral | auction_price convention inconsistency |
| GAP-G-07 | Gatheral | expm1_neg_d implemented but unused |
| GAP-G-11 | Gatheral | sqrt_d doesn't use guard digits |
| GAP-S-01 | Geohot | Dead code in decimal_math.py lines 232-234 |
| GAP-S-02 | Geohot | Dead variable _LN10_CACHE |
| GAP-S-07 | Geohot | Literal NonEmptyStr.parse in dodd_frank.py |
| GAP-S-09 | Geohot | expm1_neg_d docstring/code threshold mismatch |
| GAP-FO-07 | FinOps | CollateralType missing LETTER_OF_CREDIT |
| GAP-FO-09 | FinOps | Kafka partition counts reversed from spec |
| GAP-FO-12 | FinOps | SQL uses JSONB instead of typed arrays |
| GAP-K-03 | Karpathy | core/__init__.py missing decimal_math re-exports |
| GAP-K-05 | Karpathy | implied_vol nearest-expiry vs plan interpolation |
| GAP-K-06 | Karpathy | EMIR report unchanged (correct, plan was wrong) |
| GAP-K-07 | Karpathy | Pre-existing float in AF-YC-05 |
| GAP-TC-L1 | TestCommittee | Engine isolation test is substring-based |
| GAP-TC-L2 | TestCommittee | No mutation testing baseline |

---

## Strengths (unanimous)

1. **Conservation laws enforced** -- Every Phase 4 transaction satisfies sigma(unit)=0, verified by Hypothesis at max_examples=200 for the invariant tests
2. **engine.py untouched** -- Parametric polymorphism (Principle V) fully preserved; zero credit/swaption/collateral keywords
3. **Pure Decimal discipline** -- No float in any Phase 4 domain code; all arithmetic uses ATTESTOR_DECIMAL_CONTEXT
4. **SVI math correct** -- Formula, constraints, derivatives, Durrleman condition all analytically verified
5. **Swaption-to-IRS bridge** -- Clean composition of Phase 2 (options) and Phase 3 (IRS) via create_irs_instrument
6. **Collateral substitution atomic** -- Two Moves in one Transaction with independent sigma=0 per unit
7. **Type discipline** -- All types @final @dataclass(frozen=True, slots=True), smart constructors throughout
8. **471 Phase 4 tests** -- 22% above the 385 budget, with strong smart constructor rejection coverage

---

## Recommended Fix Priority

### Batch 1 (CRITICAL -- do now)
1. Fix `create_cds_credit_event_settlement` to include accrued premium + position close Moves
2. Add `create_cds_trade_transaction` function
3. Raise `test_cds_ledger.py` max_examples to 200
4. Add 18 missing Hypothesis property tests

### Batch 2 (HIGH -- do before commit)
5. Fix SwaptionExercisePI to use sum type (CashSettlement | PhysicalSettlement)
6. Fix `implied_vol` to use total variance interpolation
7. Remove 8 unused parameters from ledger functions
8. Extract ValidationError helper to reduce boilerplate
9. Add calibrate_vol_surface function
10. Fix Kafka retention to infinite + delete cleanup
11. Add CDS/swaption-specific EMIR fields

### Batch 3 (MEDIUM -- do in Phase 4.1)
12. Add smart constructors to CDSQuote, CDSSpreadQuote, ScheduledCDSPremium
13. Fix arbitrage gate severities (Roger Lee -> CRITICAL, ATM monotonicity -> CRITICAL)
14. Implement compute_margin_call function
15. Complete SQL schemas (credit_events columns, collateral CHECK)
16. Add MiFID II restructuring_type field

### Batch 4 (LOW -- defer to Phase 5)
17. Remaining cleanup items

---

## Metrics

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Tests passing | ~1389 | 1417 | PASS |
| Phase 4 tests | ~385 | 499 | +30% |
| mypy --strict | clean | clean | PASS |
| ruff | clean | clean | PASS |
| Source files (new) | 7 | 7+2 | PASS |
| Source files (modified) | 9 | 9 | PASS |
| SQL files | 4 | 4 | PASS |
| engine.py modified | NO | NO | PASS |
| Hypothesis tests | 26 | 26 | PASS |
| Invariants tested | 56 | ~53 | near |

### Batch 1 fixes applied (2026-02-16)

- **GAP-FO-01** FIXED: `create_cds_credit_event_settlement` now supports 3 atomic Moves (protection + accrued premium + position close)
- **GAP-FO-02** FIXED: Added `create_cds_trade_transaction` for CDS position opening at inception
- **GAP-TC-02** FIXED: `max_examples=50` raised to `200` in test_cds_ledger.py
- **GAP-TC-01** FIXED: 18 new Hypothesis property tests added (8 -> 26), covering:
  - CDS trade/maturity/full-settlement conservation
  - Swaption premium/exercise/cash-settle/expiry conservation
  - Collateral return/substitution/round-trip conservation
  - SVI total variance non-negativity, convexity, create round-trip, implied vol positivity
  - Credit curve survival probability monotonicity
  - CDS trade+close position round-trip
  - Swaption exercise close and cash settlement (invariants module)
