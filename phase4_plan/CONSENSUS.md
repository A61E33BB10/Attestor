# Phase 4 -- Credit and Structured Products: Consensus Plan

**Date:** 2026-02-15
**Status:** AGREED -- All 7 agents reached consensus
**Scope:** CDS (single-name), European swaptions (physical only), collateral management (cash), vol surface (SVI), credit curve bootstrapping

---

## Committee Review Status

| Agent | Role | Verdict |
|-------|------|---------|
| **Minsky** | Type system design | AGREED with resolutions |
| **Formalis** | Invariant registry (56 invariants) | AGREED |
| **Gatheral** | Financial mathematics specification | AGREED -- wrote PLAN.md |
| **FinOps** | Financial operations + infrastructure | AGREED -- wrote FINOPS_SPEC.md |
| **TestCommittee** | Test strategy (385 tests, 26 Hypothesis) | AGREED |
| **Geohot** | Simplicity audit (7 CUTs) | AGREED with file count compromise |
| **Karpathy** | Build sequence (17 steps) | AGREED -- wrote BUILD_SEQUENCE.md |

---

## Companion Documents

| Document | Author | Content |
|----------|--------|---------|
| `PLAN.md` | Gatheral | Financial mathematics: SVI, credit curve bootstrap, CDS cashflows, swaption exercise, collateral valuation, arbitrage gates, numerical considerations |
| `BUILD_SEQUENCE.md` | Karpathy | 17-step build plan with dependency graph, test budgets per step, source line budgets |
| `FINOPS_SPEC.md` | FinOps | Ledger booking patterns, regulatory reporting, Kafka + Postgres infrastructure, conservation laws |

---

## Disagreement Resolutions

### DR-1: File Structure

**Geohot** proposed 2 new source files (aggressively minimal).
**Minsky** proposed ~15 new types across 6+ files.
**Karpathy** proposed 7 new source files with clear build sequence.

**Resolution: Karpathy's 7 new files.** The vol surface math (SVI calibration, derivatives, Durrleman condition) and credit curve math (bootstrap, Brent solver, hazard rates) are each substantial enough (~250-350 lines) to warrant their own files. Geohot's 2-file approach would push `calibration.py` to 800+ lines, violating the established ~350 line ceiling for non-types files. Minsky's approach creates too many small files.

### DR-2: SSVI Scope

**Gatheral** specified both SVI and SSVI in the math spec.
**Geohot** proposed deferring SSVI entirely.
**Karpathy** proposed implementing SVI first, SSVI later.

**Resolution: SVI only in Phase 4.** SSVI adds calendar-spread arbitrage freedom across expiries, but this can be layered on top of SVI slices later. The PLAN.md retains the full SSVI specification for future reference, but the build sequence implements SVI only. This saves ~100 lines of source and ~30 lines of arbitrage gates.

### DR-3: PositionStatusEnum

**Minsky** proposed adding CREDIT_EVENT_TRIGGERED, IN_AUCTION, DEFAULTED.
**Formalis** proposed adding EXERCISED.
**Geohot** proposed no new states.

**Resolution: No new lifecycle states.** CDS uses the same PROPOSED -> FORMED -> SETTLED -> CLOSED lifecycle as all other products. A credit event is a business event (the `CreditEventPI` primitive instruction), not a lifecycle state. Swaption exercise transitions to CLOSED (the swaption ceases to exist; the IRS begins its own lifecycle). This preserves the simplicity of the state machine and follows the parametric polymorphism principle -- the lifecycle engine is generic over products.

### DR-4: Collateral Complexity

**Minsky** proposed full `CollateralAgreement`, `CollateralSpec`, `CollateralType` types in a dedicated `collateral_types.py`.
**Geohot** proposed collateral as 3 functions (~50 lines) in `cds.py`.
**Karpathy/FinOps** proposed `ledger/collateral.py` with types and functions together.

**Resolution: `ledger/collateral.py` with minimal types.** Cash collateral only in Phase 4. `CollateralType` enum (CASH, GOVERNMENT_BOND, CORPORATE_BOND, EQUITY), `CollateralAgreement` type with smart constructor, and 3 transaction functions (delivery, return, substitution). Securities collateral with haircut schedules deferred to Phase 5. This gives us the correct structure without premature complexity.

### DR-5: Swaption File Placement

**Geohot** proposed swaption exercise in `cds.py`.
**Karpathy/FinOps** proposed separate `swaption.py`.

**Resolution: Separate `ledger/swaption.py`.** The swaption-to-IRS bridge (5 functions: premium, exercise, IRS derivation, cash settlement, expiry) is ~250 lines and semantically distinct from CDS booking. Keeping them separate follows the Phase 2/3 pattern where each instrument family has its own ledger file.

### DR-6: Reporting Files

**FinOps** proposed 3 new reporting files (dodd_frank.py, collateral_report.py, model_governance.py).
**Geohot** proposed extending existing emir.py and mifid2.py only.
**Karpathy** proposed dodd_frank.py as new, extend existing for others.

**Resolution: One new file (`reporting/dodd_frank.py`), extend existing for the rest.** Dodd-Frank is a distinct regulatory regime from EMIR/MiFID II, warranting its own file. CDS/swaption MiFID II fields go in existing `mifid2.py`. CDS/swaption EMIR fields go in existing `emir.py`. Collateral and model governance reporting deferred per DR-4 trimming.

### DR-7: Decimal Math Module Location

**Karpathy** proposed `core/decimal_math.py`.
**FinOps** proposed `oracle/decimal_math.py`.

**Resolution: `core/decimal_math.py`.** These are foundational mathematical utilities (exp, ln, sqrt) used by multiple pillars (Oracle calibration, potentially Pricing in future phases). They belong in `core/`.

### DR-8: Swaption Cash Settlement

**FinOps** specified both physical and cash-settled swaption exercise.
**Geohot** proposed physical only.

**Resolution: Both physical and cash settlement.** The cash-settled path is structurally identical to `create_cash_settlement_exercise_transaction` in `options.py` (~30 additional lines). The marginal cost is trivial and the completeness value is high. Both paths are included.

---

## Agreed Scope

### Products
- CDS (single-name) -- premium leg, protection leg, credit event settlement
- European swaptions -- physical exercise into IRS, cash settlement
- Collateral management -- cash collateral delivery, return, substitution

### Oracle (Pillar III)
- SVI vol surface calibration (per-slice, no SSVI)
- Credit curve bootstrap (piecewise constant hazard rate)
- Arbitrage gates: AF-VS-01..06 (vol surface), AF-CR-01..05 (credit curve)
- Pure-Decimal math utilities (exp_d, ln_d, sqrt_d, expm1_neg_d)

### Ledger (Pillar II)
- CDS: trade booking, premium payments, credit event settlement, maturity close
- Swaption: premium, physical exercise (creates IRS), cash settlement, expiry
- Collateral: margin call delivery, return, substitution

### Reporting (Pillar IV)
- CDS EMIR/MiFID II fields (extend existing)
- CDS Dodd-Frank reporting (new file)
- Swaption EMIR/MiFID II fields (extend existing)

### Infrastructure
- 4 Kafka topics (vol_surfaces, credit_curves, collateral, credit_events)
- 4 Postgres tables (018-021)

### Explicitly Deferred to Phase 5
- SSVI vol surface parameterization
- Securities collateral with haircut schedules
- Collateral reporting
- Model governance reporting
- CDS index products
- AF-VS-07 (ATM skew term structure -- HIGH severity, not CRITICAL)

---

## Agreed File Layout

### New Source Files (7)

| File | Lines (est.) | Content |
|------|-------------|---------|
| `attestor/core/decimal_math.py` | ~150 | exp_d, ln_d, sqrt_d, expm1_neg_d |
| `attestor/instrument/credit_types.py` | ~250 | CDS/swaption enums, CDSPayoutSpec, SwaptionPayoutSpec |
| `attestor/oracle/credit_curve.py` | ~250 | CreditCurve, CDSQuote, bootstrap, Brent solver |
| `attestor/oracle/vol_surface.py` | ~300 | SVIParameters, VolSurface, SVI math, calibration |
| `attestor/ledger/cds.py` | ~300 | CDS booking (trade, premium, credit event, maturity) |
| `attestor/ledger/swaption.py` | ~250 | Swaption booking (premium, exercise, cash settlement, expiry) |
| `attestor/ledger/collateral.py` | ~200 | CollateralAgreement, delivery, return, substitution |

### Modified Source Files (9)

| File | Changes |
|------|---------|
| `attestor/instrument/derivative_types.py` | +CDSDetail, +SwaptionDetail, InstrumentDetail union |
| `attestor/instrument/types.py` | +Payout union, +create_cds_instrument, +create_swaption_instrument |
| `attestor/instrument/lifecycle.py` | +CreditEventPI, +SwaptionExercisePI, +CollateralCallPI, +transitions |
| `attestor/oracle/arbitrage_gates.py` | +AF-VS gates, +AF-CR gates, +ArbitrageCheckType variants |
| `attestor/oracle/credit_ingest.py` (new) | CDSSpreadQuote, CreditEventRecord, AuctionResult ingest |
| `attestor/gateway/parser.py` | +parse_cds_order, +parse_swaption_order |
| `attestor/reporting/emir.py` | +CDS/swaption EMIR fields |
| `attestor/reporting/mifid2.py` | +CDSReportFields, +SwaptionReportFields |
| `attestor/reporting/dodd_frank.py` (new) | Dodd-Frank CDS/swaption reporting |

### New Test Files (~13)

Per BUILD_SEQUENCE.md Steps 0-15.

### Infrastructure Files (4 SQL)

| File | Table |
|------|-------|
| `sql/018_vol_surfaces.sql` | Calibrated vol surface store |
| `sql/019_credit_curves.sql` | Credit curve store |
| `sql/020_collateral_balances.sql` | Collateral positions per agreement |
| `sql/021_credit_events.sql` | Credit event history |

---

## Agreed Invariants (56)

Per Formalis registry:

| Category | Count | IDs |
|----------|-------|-----|
| Conservation Laws | 10 | CL-C1..CL-C10 |
| Commutativity Squares | 9 | CS-C1..CS-C9 |
| Arbitrage Freedom | 12 | AF-VS-01..06, AF-CR-01..05, AF-VS-07(deferred) |
| Type Safety | 9 | TS-C1..TS-C9 |
| Lifecycle | 4 | LC-C1..LC-C4 |
| Parametric Polymorphism | 4 | PP-C1..PP-C4 |
| Cross-Phase | 8 | XP-C1..XP-C8 |

---

## Agreed Test Budget

| Step | Tests |
|------|-------|
| 0: Decimal math | ~20 |
| 1: CDS/swaption types | ~35 |
| 2: Lifecycle | ~20 |
| 3: Credit curve | ~22 |
| 4: Vol surface | ~25 |
| 5: Arbitrage gates | ~28 |
| 6: Credit ingest | ~18 |
| 7: Gateway parsers | ~20 |
| 8: CDS ledger | ~25 |
| 9: Swaption ledger | ~22 |
| 10: Collateral | ~25 |
| 11: Reporting | ~20 |
| 12: Pricing stubs | ~8 |
| 13: Infrastructure | ~14 |
| 14: Invariant tests | ~28 |
| 15: Integration tests | ~55 |
| **Total new** | **~385** |
| **Running total** | **~1389** |

26 Hypothesis property-based tests at max_examples=200.

---

## Agreed Build Sequence

Follow Karpathy's BUILD_SEQUENCE.md exactly (17 steps, 0-16).

**Build protocol per step:**
1. Write source file(s)
2. `mypy --strict attestor/ tests/` -- clean
3. `ruff check attestor/ tests/` -- clean
4. Write test file(s)
5. `pytest tests/` -- green
6. Verify: no `float` in domain, no bare `raise`, `Move.create()` used everywhere
7. Next step

**Files that MUST NOT be modified:**
- `attestor/ledger/engine.py` (Principle V: parametric polymorphism)
- `attestor/core/result.py` (foundation)
- `attestor/core/serialization.py` (foundation)

---

## Geohot CUTs (Simplicity Constraints)

| CUT | Rule | Status |
|-----|------|--------|
| CUT-1 | One `credit_types.py` for CDS + Swaption types | AGREED |
| CUT-2 | Collateral in `ledger/collateral.py`, not a separate types file | AGREED (with types in same file) |
| CUT-3 | Vol surface and credit curve get own files (not crammed into calibration.py) | OVERRIDE (files separate, not in calibration.py) |
| CUT-4 | Transition tables as aliases, same pattern | AGREED |
| CUT-5 | No new PositionStatusEnum variants | AGREED |
| CUT-6 | Defer SSVI | AGREED |
| CUT-7 | Defer securities collateral | AGREED |

---

## Acceptance Criteria

From MASTER_PLAN Phase 4, verified against all agent specifications:

- [ ] CDS trade booked with premium and protection legs
- [ ] Credit event triggers settlement -- auction price from Oracle, recovery payment booked
- [ ] Swaption exercise produces IRS instrument and lifecycle continues from Phase 3
- [ ] Vol surface calibration produces SVI slices passing AF-VS-01..06
- [ ] Credit curve bootstrapping produces valid survival probabilities passing AF-CR-01..05
- [ ] Collateral management: margin calls produce collateral transfer transactions
- [ ] Collateral substitution: atomic, balanced
- [ ] Pillar V stub contract verified for CDS and swaption types
- [ ] Derived confidence payloads complete for vol surfaces and credit curves
- [ ] All conservation laws (CL-C1..CL-C10) verified
- [ ] All existing conservation laws still hold for Phase 4 transactions
- [ ] engine.py not modified (Principle V)
- [ ] ~385 new tests, total ~1389
- [ ] mypy --strict clean
- [ ] All 56 invariants covered by tests
