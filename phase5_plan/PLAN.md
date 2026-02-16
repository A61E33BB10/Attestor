# Phase 5 -- Hardening and Gap Closure

**Scope:** Close all remaining HIGH/MEDIUM gaps from Phase 4 review, expand test
coverage to plan targets, upgrade severity classifications, add smart constructors.

**Constraint:** No new instrument types. No new Kafka topics. No new SQL tables.
Engine.py remains untouched. Pure Decimal discipline continues.

---

## Deliverables

### D1: Smart Constructors (Minsky gaps)

Add `create()` smart constructors returning `Ok[T] | Err[str]` to:
- `CDSQuote` (GAP-M-02): validate tenor > 0, spread >= 0, recovery_rate in [0, 1)
- `CDSSpreadQuote` (GAP-M-03): validate tenor > 0, bid >= 0, ask >= bid, recovery_rate in [0, 1)
- `AuctionResult` (GAP-M-09): validate auction_price in [0, 1]
- `CreditEventRecord` (GAP-M-09): validate entity non-empty, event_type valid

### D2: Severity Upgrades (Gatheral gaps)

In `arbitrage_gates.py`:
- AF-VS-03 (Roger Lee right wing): HIGH -> CRITICAL (GAP-G-08)
- AF-VS-04 (Roger Lee left wing): HIGH -> CRITICAL (GAP-G-08)
- AF-VS-06 (ATM variance monotonicity): HIGH -> CRITICAL (GAP-G-09)

### D3: Margin Call Computation (FinOps gap)

New function `compute_margin_call` in `ledger/collateral.py` (GAP-FO-05):
- Input: current_exposure, threshold, minimum_transfer_amount
- Output: Ok[Decimal] | Err[str] with the call amount (0 if below MTA)
- Pure computation, no ledger side effects

### D4: Dodd-Frank Notional Fix (FinOps gap)

Fix `project_dodd_frank_report` CDS notional to use `order.quantity.value` directly
(the contract notional), not `quantity * price` (GAP-FO-08).

### D5: SQL Schema Completion (FinOps gaps)

- `021_credit_events.sql`: add missing columns (auction_price, settlement_date, recovery_rate) (GAP-FO-10)
- `020_collateral_balances.sql`: add `CHECK (quantity >= 0)` (GAP-FO-11)

### D6: Test Coverage Expansion (TestCommittee gaps)

- Add integration tests to reach ~50 in `test_integration_credit.py` (GAP-TC-03):
  - Multi-CDS portfolio lifecycle
  - Cross-instrument conservation (CDS + swaption + collateral sigma=0)
  - Error propagation across boundaries
  - Negative-path lifecycle (GAP-TC-M2)
- Add commutativity square tests CS-C1..C4 (GAP-TC-H1)
- Add Durrleman butterfly failure mode test (GAP-TC-H3)

### D7: Cleanup

- Fix Dodd-Frank literal `NonEmptyStr.parse` calls to module-level constants (GAP-S-07)
- Fix `decimal_math.py` dead code: remove unused `_LN10_CACHE`, dead assignments (GAP-S-01/S-02)
- Fix `expm1_neg_d` docstring threshold (GAP-S-09)
- Add `CollateralReportFields` type to mifid2.py (GAP-K-02)

---

## Build Sequence

| Step | Deliverable | Files | Est. Tests |
|------|-------------|-------|------------|
| 1 | D1: Smart constructors | credit_curve.py, credit_ingest.py | +8 |
| 2 | D2: Severity upgrades | arbitrage_gates.py | +3 |
| 3 | D3: Margin call | collateral.py | +5 |
| 4 | D4: Dodd-Frank fix | dodd_frank.py | +2 |
| 5 | D5: SQL schemas | 2 SQL files | +2 |
| 6 | D6: Test expansion | test_integration_credit.py + test_invariants_credit.py | +20 |
| 7 | D7: Cleanup | various | +3 |
| **Total** | | | **~43** |

## Exit Criteria

- All tests pass (target: ~1472)
- mypy --strict clean
- ruff clean
- Zero CRITICAL gaps remaining
- Zero HIGH gaps remaining (except ISDA standard model, deferred to Phase 6)
- engine.py untouched
