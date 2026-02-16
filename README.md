# Attestor

Attestation-first cross-asset trading platform. Every fact carries structured
epistemic metadata. Every mutation is a content-addressed, append-only record.

## Architecture

Five pillars, each with its own Kafka topic namespace and Postgres schema:

| Pillar | Responsibility | Key Module |
|--------|---------------|------------|
| **I -- Gateway** | Raw-to-canonical normalization; all rejections are attestations | `gateway/` |
| **II -- Ledger** | Double-entry accounting with conservation laws | `ledger/` |
| **III -- Oracle** | Attested market data with confidence classes | `oracle/` |
| **IV -- Reporting** | Pure projection to EMIR, MiFID II, Dodd-Frank | `reporting/` |
| **V -- Pricing** | Interface-only pricing protocols | `pricing/` |

### Design Principles

- **Result types, not exceptions.** All domain functions return `Ok[T] | Err[E]`.
- **Immutable types.** Every domain type is `@final @dataclass(frozen=True, slots=True)`.
- **Smart constructors.** Illegal states are unrepresentable -- `T.create()` validates at construction.
- **Decimal only.** No `float` in domain code. `ATTESTOR_DECIMAL_CONTEXT` (precision 28) everywhere.
- **Parametric polymorphism.** The ledger engine processes generic `Transaction`/`Move` objects. It has never been modified across five phases and supports unlimited instrument types.
- **Conservation laws.** `sigma(unit) = 0` for every unit in every transaction, enforced atomically.
- **Attestation wrapping.** Oracle outputs are `Attestation[T]` with `FirmConfidence`, `QuotedConfidence`, or `DerivedConfidence`.

## Phases Delivered

### Phase 0 -- Foundation
Core type system (`Result`, `FrozenMap`, `UtcDatetime`, `NonEmptyStr`, `PositiveDecimal`),
content-addressed serialization, double-entry ledger engine, attestation framework.

### Phase 1 -- Equity Cash
Equity instrument types, gateway parsing with LEI/ISIN validation, trade booking,
settlement lifecycle (PROPOSED -> FORMED -> SETTLED -> CLOSED), EMIR reporting.

### Phase 2 -- Listed Derivatives
Vanilla options (European/American calls and puts), listed futures with margin,
option premium booking, exercise/assignment lifecycle, MiFID II reporting.

### Phase 3 -- FX and Rates
FX spot/forward/NDF with ISO 4217 currency pairs, vanilla IRS (fixed-float) with
day count conventions, yield curve bootstrapping, multi-currency conservation laws.

### Phase 4 -- Credit and Structured Products
CDS (trade, premium, credit event, auction settlement, maturity close),
swaptions (premium, physical/cash exercise, expiry), collateral management
(margin call, return, substitution). SVI volatility surface with calibration.
Credit curve bootstrap from CDS spreads. Arbitrage freedom gates (6 vol surface +
4 credit curve). Dodd-Frank swap reporting.

## Project Metrics

| Metric | Value |
|--------|-------|
| Tests passing | 1467 |
| Source files | 55 |
| Test files | 68 |
| Source LOC | ~10,900 |
| SQL migrations | 21 |
| mypy --strict | Clean (55 files) |
| ruff | Clean |
| Python | >= 3.12 |

## Directory Structure

```
attestor/
  core/          Result, Decimal math, FrozenMap, identifiers, serialization
  gateway/       CanonicalOrder, parsers (equity, FX, IRS, CDS, swaption)
  instrument/    Instrument types, derivative details, lifecycle state machine
  ledger/        Engine, transactions, settlement, CDS, swaption, collateral
  oracle/        Attestation, calibration, vol surface, credit curve, ingest
  pricing/       Protocols and stubs
  infra/         Kafka topics, Postgres schemas, metrics
  reporting/     EMIR, MiFID II, Dodd-Frank projections
tests/           68 test files (unit, property-based, invariant, integration)
sql/             21 migration files (bitemporal tables, append-only triggers)
```

## Running

```bash
python -m pytest tests/                  # 1429 tests
python -m mypy --strict attestor/        # type checking
ruff check attestor/ tests/              # linting
```

## Key Invariants

- **Conservation:** Every ledger transaction preserves `sigma(unit) = 0` per unit
- **Commutativity:** `Projection(Raw) == Projection(Normalized)` for all report types
- **Arbitrage freedom:** SVI surfaces pass calendar spread, Durrleman butterfly, Roger Lee wing, positive variance, and ATM monotonicity gates
- **Credit curve:** Survival probabilities in (0, 1], monotonically decreasing, non-negative hazard rates
- **Lifecycle:** State machine transitions enforced -- no skipping states, no reversals
- **Parametric polymorphism:** `engine.py` contains zero instrument-specific keywords

## Testing Strategy

- **Smart constructor tests:** Every `create()` method tested with valid inputs and every rejection path
- **Hypothesis property-based:** Conservation laws verified with `@given` at `max_examples=200`
- **Arbitrage gates:** Each gate tested with passing and failing surfaces/curves
- **Integration tests:** Full lifecycle scenarios (CDS, swaption physical/cash, collateral round-trip)
- **Invariant tests:** Dedicated test file per phase verifying all stated invariants

## Tech Stack

| Component | Choice |
|-----------|--------|
| Language | Python 3.12+ |
| Types | mypy strict mode |
| Linting | ruff |
| Testing | pytest + Hypothesis |
| Arithmetic | `decimal.Decimal` (precision 28) |
| Persistence | Kafka (event streams) + Postgres (bitemporal state) |
| Error handling | `Ok[T] \| Err[E]` sum type (zero exceptions) |
