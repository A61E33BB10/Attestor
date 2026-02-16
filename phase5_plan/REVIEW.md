# Phase 5 Review — Hardening and Gap Closure

## Verification

| Check | Result |
|-------|--------|
| Tests passing | 1467 (was 1429, +38) |
| mypy --strict | Clean (55 files) |
| ruff | Clean |
| engine.py | Untouched |

## Deliverable Status

### D1: Smart Constructors — DONE

Added `create()` returning `Ok[T] | Err[str]` to:
- `CDSQuote.create()` — validates tenor > 0, spread >= 0, recovery_rate in [0, 1), non-empty strings
- `CDSSpreadQuote.create()` — validates tenor > 0, spread_bps >= 0, recovery_rate in [0, 1)
- `AuctionResult.create()` — validates auction_price in [0, 1], non-empty reference entity

Tests: 7 smart constructor tests in test_credit_curve.py, 9 in test_credit_ingest.py (+16 total)

### D2: Severity Upgrades — DONE

In `arbitrage_gates.py`:
- AF-VS-03 (Roger Lee right wing): HIGH → CRITICAL
- AF-VS-04 (Roger Lee left wing): HIGH → CRITICAL
- AF-VS-06 (ATM variance monotonicity): HIGH → CRITICAL

Tests: Updated assertions in test_arbitrage_gates_phase4.py

### D3: Margin Call Computation — DONE

Added `compute_margin_call(current_exposure, threshold, minimum_transfer_amount)` to `collateral.py`:
- Pure computation, no ledger side effects
- Returns `max(0, exposure - threshold)` if above MTA, else 0
- Validates all inputs >= 0 and finite Decimal

Tests: 8 tests in test_collateral.py (TestComputeMarginCall)

### D4: Dodd-Frank Notional Fix — DONE

Fixed `project_dodd_frank_report`: CDS/swaption notional now uses `order.quantity.value`
(the contract notional) instead of `quantity * price`.

Tests: 2 tests in test_integration_credit.py (TestDoddFrankNotional)

### D5: SQL Schema Completion — DONE

- `021_credit_events.sql`: added `settlement_date DATE` and `recovery_rate NUMERIC(10,6) CHECK` columns
- `020_collateral_balances.sql`: added `CHECK (quantity >= 0)` to quantity column

### D6: Test Coverage Expansion — DONE

New tests added:
- TestMultiCDSPortfolio: multi-CDS shared engine conservation (+1)
- TestCrossInstrumentConservation: CDS + collateral sigma=0 (+1)
- TestNegativePathLifecycle: 4 error propagation tests (+4)
- TestCSC1..C4: commutativity square tests (+4)
- TestDurrlemanButterflyFailure: Durrleman g(k) < 0 detection (+1)
- TestDoddFrankNotional: CDS and swaption notional validation (+2)

### D7: Cleanup — DONE

- Removed unused `_LN10_CACHE` from decimal_math.py (GAP-S-01)
- Fixed `expm1_neg_d` docstring: threshold is `|x| < 1`, not `|x| < 0.1` (GAP-S-09)
- Replaced 4 literal `NonEmptyStr.parse("CREDIT")` etc. calls in dodd_frank.py with module-level constants (GAP-S-07)
- Added `CollateralReportFields` type to mifid2.py (GAP-K-02)

## Gap Closure Summary

| Gap ID | Description | Status |
|--------|-------------|--------|
| GAP-M-02 | CDSQuote smart constructor | CLOSED |
| GAP-M-03 | CDSSpreadQuote smart constructor | CLOSED |
| GAP-M-09 | AuctionResult/CreditEventRecord smart constructors | CLOSED |
| GAP-G-08 | Roger Lee wing severity upgrade | CLOSED |
| GAP-G-09 | ATM monotonicity severity upgrade | CLOSED |
| GAP-FO-05 | compute_margin_call | CLOSED |
| GAP-FO-08 | Dodd-Frank CDS notional fix | CLOSED |
| GAP-FO-10 | credit_events.sql missing columns | CLOSED |
| GAP-FO-11 | collateral_balances.sql CHECK constraint | CLOSED |
| GAP-TC-03 | Integration test expansion | CLOSED |
| GAP-TC-H1 | Commutativity square tests | CLOSED |
| GAP-TC-H3 | Durrleman butterfly failure test | CLOSED |
| GAP-TC-M2 | Negative-path lifecycle tests | CLOSED |
| GAP-S-01 | Dead code in decimal_math.py | CLOSED |
| GAP-S-07 | Dodd-Frank literal NonEmptyStr.parse | CLOSED |
| GAP-S-09 | expm1_neg_d docstring threshold | CLOSED |
| GAP-K-02 | CollateralReportFields type | CLOSED |

## Exit Criteria

- [x] All 1467 tests pass
- [x] mypy --strict clean (55 files)
- [x] ruff clean
- [x] Zero CRITICAL gaps remaining
- [x] Zero HIGH gaps remaining (except ISDA standard model, deferred to Phase 6)
- [x] engine.py untouched
