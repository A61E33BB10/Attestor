# Phase 0 --- Pass 3: Practitioner + Infrastructure + API

**Date:** 2026-02-15
**Input:** PHASE0_EXECUTION.md (all 18 steps), PASS2_REVIEW.md (20 gaps), PLAN.md (Sections 3.4, 11, 15)
**Output:** Three specialist reviews + consolidated change list

---

## 1. Financial Practitioner Review [Gatheral]

### 1.1 Money Type

**APPROVED items:**

- **Decimal-only arithmetic (INV-M02).** The specification correctly mandates `type(money.amount) is Decimal` and bans `float` at the CI level. The `ATTESTOR_DECIMAL_CONTEXT` with `prec=28` provides more than sufficient precision for all financial arithmetic: 28 significant digits covers notional amounts up to the quadrillions with sub-cent precision and leaves a wide margin for intermediate calculations in multi-leg structures. For FX, which commonly requires 6--8 decimal places, and for crypto, which may require up to 18 (Ethereum wei), 28 significant digits is adequate. This is correct.

- **ROUND_HALF_EVEN (banker's rounding) (INV-M04).** Eliminates systematic rounding bias in large portfolios. This is the standard for financial systems and settlement platforms. Correct.

- **Trap configuration.** `InvalidOperation`, `DivisionByZero`, and `Overflow` are trapped. This means `Decimal("NaN")` and `Decimal("Infinity")` will raise `InvalidOperation` when used in arithmetic under the context. However -- see REQUIRED CHANGE below regarding explicit rejection at construction time.

- **Same-currency arithmetic enforcement (INV-M03).** `add` and `sub` return `Err` on currency mismatch. This is mathematically correct: `M_USD` and `M_EUR` are distinct modules with no canonical morphism between them. Cross-currency operations require an explicit FX rate attestation, which is the right design.

- **Sign freedom (INV-M05).** Negative amounts are permitted. This is essential for representing short positions, liabilities, debit balances, and mark-to-market losses. Zero is permitted. Correct.

- **Immutability (INV-M07).** All operations return new `Money` instances. `frozen=True, slots=True`. Correct.

**REQUIRED CHANGES:**

1. **[HIGH] NaN and Infinity rejection at `Money.create()` -- PLAN Section 15.1.5 requires it, Pass 1 does not specify it.** The PLAN explicitly states: *"`Money.create(Decimal("NaN"), "USD")` must return `Err`. `Decimal("Infinity")` must return `Err`."* The Pass 1 specification (Step 4) does not include this validation in the `create()` factory. Relying on the context traps alone is insufficient because a `Decimal("NaN")` can be stored in a `Money` instance without performing arithmetic -- the trap only fires on operations, not on construction. The `create()` factory must explicitly check `amount.is_finite()` and return `Err` for NaN, sNaN, and Infinity. This is INV-M02 enforcement at the boundary.

2. **[HIGH] Missing `div()` method -- PLAN Section 15.1.3 specifies it, Pass 1 omits it.** The PLAN specifies `div(m: Money, divisor: NonZeroDecimal) -> Money` for scalar division. Pass 1 Step 4 lists `add`, `sub`, `mul`, `negate` but not `div`. A derivatives desk needs division constantly: computing average cost basis, per-unit P&L, allocation across counterparties, and unit notional Greeks. The type `NonZeroDecimal` already exists to make this operation total. This must be added.

3. **[HIGH] Missing `round_to_minor_unit()` -- PLAN Section 15.1.3 specifies it, Pass 1 omits it.** Settlement, reporting, and regulatory projection all require quantization to currency minor units. The PLAN specifies this as a boundary operation using banker's rounding and ISO 4217 minor unit tables (USD=2, JPY=0, BHD=3). Pass 1 does not include it. Without this method, every downstream consumer must implement its own rounding, which guarantees inconsistency. This must be added to the Money type, or at minimum, a standalone function `round_to_minor_unit(m: Money) -> Money` must be specified with the ISO 4217 lookup table.

4. **[MEDIUM] No ISO 4217 currency code validation.** `Money.create()` accepts any non-empty string as a currency code. The PLAN (Section 15.1.2, INV-M06) states that the canonical form is uppercase ISO 4217, and that normalization happens at the Gateway boundary. This is a defensible design choice -- validation at the boundary, not in the core type -- but the consequence is that `Money.create(Decimal("100"), "ZZZZ")` silently succeeds. For Phase 0 this is acceptable, but Phase 1 MUST introduce either: (a) a `CurrencyCode` refined type that validates against the ISO 4217 table, or (b) a Gateway-level validation that rejects non-standard codes before they reach the core.

5. **[CRITICAL -- already identified as V-02] Money arithmetic does not use `ATTESTOR_DECIMAL_CONTEXT`.** PASS2_REVIEW V-02 correctly flags this. I confirm this is a blocking issue from a practitioner perspective. If two processes have different thread-local Decimal contexts (e.g., one set by a third-party library), identical trades produce different P&L. This is the financial equivalent of a broken hedging model: the numbers you compute depend on the environment, not on the inputs. Every `Decimal` operation in `Money.add`, `Money.sub`, and `Money.mul` must execute within `with localcontext(ATTESTOR_DECIMAL_CONTEXT)`.

**RECOMMENDATIONS for Phase 1:**

- Add a `Money.abs() -> Money` method. Absolute value is needed constantly for exposure calculations, margin computations, and concentration limits.
- Consider whether `Money.__eq__` should compare both amount and currency, or amount only. The current specification (frozen dataclass) compares all fields, which is correct. But document explicitly that `Money(Decimal("0"), "USD") != Money(Decimal("0"), "EUR")` -- zero in different currencies is not the same zero.
- The algebraic laws in PLAN Section 15.1.4 (commutativity, associativity, distributivity of scalar multiplication) should be tested as Hypothesis properties. This is specified in the PLAN but not in the Pass 1 test catalogue.

---

### 1.2 Confidence Payloads

**APPROVED items:**

- **Three-class epistemic partition.** `FirmConfidence`, `QuotedConfidence`, `DerivedConfidence` as a sum type is the right abstraction. The ordering `Firm > Quoted > Derived` correctly reflects the epistemic hierarchy of financial data. An exchange fill is fact; a market quote is a bounded estimate; a model output is a derived quantity with quantified uncertainty. This is the foundation of honest risk reporting.

- **`DerivedConfidence` carries fit quality as `FrozenMap[str, Decimal]`.** This is exactly what a quant needs for model audit. The PLAN correctly specifies RMSE in vol units, R-squared, max error, and log-likelihood as example metrics. These are the metrics I would inspect before trusting a calibrated vol surface or a bootstrapped yield curve.

- **Provenance DAG via `tuple[str, ...]` on `Attestation`.** Every derived value can be traced back to its firm sources. This is auditable and reproducible. The integration test (Step 15) correctly tests walkability of the provenance chain.

- **Content-addressed identity via SHA-256.** Correct choice for integrity. Deterministic across processes.

**REQUIRED CHANGES:**

1. **[CRITICAL] `QuotedConfidence` is missing `bid <= ask` enforcement (INV-QC01).** Pass 1 Step 9 defines `QuotedConfidence` with `bid: Decimal`, `ask: Decimal`, `venue: str`, `size: Decimal | None`, `conditions: str` -- but does not specify a validating factory that enforces `bid <= ask`. A `QuotedConfidence` with `bid=155.10, ask=154.90` represents a negative spread -- an immediate arbitrage opportunity from corrupted data. This must be rejected at construction time. The construction should be a factory method `create(bid, ask, venue, size, conditions) -> Result[QuotedConfidence, str]` that returns `Err` when `bid > ask`. The PLAN (Section 15.3.3, INV-QC01) states: *"A negative spread implies arbitrage is available. If `bid > ask`, the quote is corrupted and MUST be rejected."* This is non-negotiable. *(Strengthens PASS2 GAP-06.)*

2. **[HIGH] `QuotedConfidence` is missing `mid` and `spread` computed properties (INV-O06).** PASS2_REVIEW Section 1.2 flags this as a gap. The PLAN (Section 15.3.3) explicitly specifies `mid`, `spread`, and `half_spread` as `@property` computed values. Pass 1 omits all three. A market maker's desk requires mid-price for position marking and spread for transaction cost analysis. These must be added as computed properties, not stored fields, because they are derived from `bid` and `ask` and must be computed under `ATTESTOR_DECIMAL_CONTEXT`. *(Confirms PASS2 GAP-06.)*

3. **[HIGH] `DerivedConfidence` -- `confidence_interval` and `confidence_level` optionality vs. the PLAN.** The PLAN (INV-DC06) specifies that these two fields must be either both present or both absent. Pass 1 makes them independently optional (`| None`). A confidence interval without a confidence level is meaningless (is it 90%? 95%? 99%?), and a confidence level without an interval is vacuous. The factory must enforce: either both are `None` or both are provided. Furthermore, when `confidence_level` is not `None`, INV-DC05 requires `0 < confidence_level < 1`. *(Confirms PASS2 GAP-07.)*

4. **[HIGH] `DerivedConfidence` -- `fit_quality` must be non-empty (INV-DC03).** The PLAN states: *"An empty `fit_quality` means the model was not calibrated, which is unacceptable for a Derived attestation."* Pass 1 does not enforce this. The factory must reject construction when `fit_quality` is `FrozenMap.EMPTY`.

5. **[MEDIUM] `FirmConfidence` fields accept empty strings (INV-FC01, INV-FC03).** PASS2_REVIEW flags this. Pass 1 defines `source: str` and `attestation_ref: str` as bare strings. The PLAN requires both to be non-empty. These should use `NonEmptyStr` or be validated in a factory method. *(Confirms PASS2 GAP-20.)*

6. **[MEDIUM] `QuotedConfidence.conditions` is not validated against the controlled vocabulary (INV-QC04).** The PLAN specifies that `conditions` must be one of `"Indicative"`, `"Firm"`, `"RFQ"`. Pass 1 accepts any string. This should be an `Enum` or validated at construction.

7. **[MEDIUM] No `depth` field on `QuotedConfidence`.** For a market maker, quoted depth (number of lots at the bid/ask) is essential context. The `size` field captures the quoted size for one level, but for a full book, depth at multiple levels would be needed. For Phase 0, the single `size: Decimal | None` is acceptable, but Phase 1 should consider extending this for multi-level book data, or at minimum document that `size` represents top-of-book only.

8. **[MEDIUM] `FirmConfidence` is missing fields that a desk needs from an exchange fill.** The current fields are `source`, `timestamp`, and `attestation_ref`. For a fill, a desk also needs: (a) a venue-specific sequence ID, (b) the execution venue (which may differ from the authoritative source), and (c) execution conditions (e.g., auction, continuous). For Phase 0, the current set is minimal but sufficient. Phase 1 should extend this when Gateway (Pillar I) processes real fills.

**RECOMMENDATIONS for Phase 1:**

- Add a `QuotedConfidence.is_locked() -> bool` property (returns `bid == ask`). Locked markets require special handling in valuation.
- Add a `DerivedConfidence.is_well_calibrated(rmse_threshold: Decimal) -> bool` convenience method.
- Consider whether `DerivedConfidence.method` should be an `Enum` of approved model names rather than a free string.

---

### 1.3 Pillar V Contracts

**APPROVED items:**

- **Protocol-based interface (structural subtyping).** `PricingEngine(Protocol)` is the correct design. Any class that implements the required methods satisfies the protocol without inheritance. This allows swapping between stub, Black-Scholes, Heston, local vol, or rough Bergomi engines without modifying any consumer code.

- **`Greeks` type includes second-order sensitivities.** Delta, gamma, vega, theta, rho (first order) plus vanna, volga, charm (second order) are all present as `Decimal` fields with default `Decimal("0")`. For equity options, these eight Greeks cover the essential risk sensitivities. Vanna and volga are particularly important for exotic options and for understanding the P&L of delta-vega hedged positions.

- **`PnLAttribution` decomposition.** `total_pnl = market_pnl + carry_pnl + trade_pnl + residual_pnl`. This is the standard desk-level P&L attribution. The test (`test_pnl_attribution_decomposition`) correctly verifies that the sum holds. The `residual_pnl` field captures the unexplained P&L -- which should be small if the model and hedging are correct.

- **`VaRResult` type is present.** Includes `confidence_level`, `horizon_days`, `var_amount`, `currency`, `method`, and `component_var`. Sufficient for a basic VaR report.

- **`Scenario` and `ScenarioResult` types.** `Scenario` carries `label`, `overrides: FrozenMap[str, Decimal]`, and `base_snapshot_id`. The right shape for stress testing: take a base state, apply overrides, compute the impact.

- **`StubPricingEngine` for testing.** Returns hard-coded `Ok` values. Allows the rest of the platform to develop against Pillar V contracts without a real pricing engine.

**REQUIRED CHANGES:**

1. **[CRITICAL] Pillar V Protocol signatures in Pass 1 diverge from PLAN Section 3.4.3.** The PLAN specifies:
   ```python
   def price(self, instrument: Instrument, market: Attestation[MarketDataSnapshot],
             model_config: Attestation[ModelConfig]) -> Result[Attestation[ValuationResult], PricingError]
   ```
   But Pass 1 Step 12 specifies:
   ```python
   def price(self, instrument_id: str, market_snapshot_id: str,
             model_config_id: str) -> Result[ValuationResult, PricingError]
   ```
   These are fundamentally different contracts. The PLAN version passes rich typed objects with full provenance and epistemic context. The Pass 1 version passes opaque string IDs. Furthermore, the PLAN version returns `Attestation[ValuationResult]` (the output is itself attested), while Pass 1 returns a bare `ValuationResult`.

   From a practitioner perspective, the PLAN version is correct. A pricing engine needs the actual instrument definition (strike, maturity, exercise style) to price. And the output must be an `Attestation` because every valuation must carry its provenance for audit.

   However, Pass 1 intentionally simplifies because `Instrument`, `MarketDataSnapshot`, and `ModelConfig` types do not yet exist. **The fix:** Document explicitly that the Pass 1 signatures are provisional and will be replaced by the PLAN Section 3.4.3 signatures when the corresponding types are built. Add a comment block in `protocols.py` citing PLAN 3.4.3 as the target interface.

2. **[HIGH] Missing `var()` and `pnl_attribution()` methods on `PricingEngine`.** The PLAN Section 3.4.3 specifies five methods: `price`, `greeks`, `scenario_pnl`, `var`, and `pnl_attribution`. Pass 1 Step 12 only implements `price` and `greeks` on `PricingEngine`, with `scenario_pnl` on a separate `RiskEngine`. The `var` and `pnl_attribution` methods are missing entirely. These should at minimum appear as protocol method signatures even if the stub returns placeholder values.

3. **[HIGH] Missing Expected Shortfall / CVaR.** The PLAN Section 3.4.2 mentions `VaR / CVaR` as an output type. The `VaRResult` type has no field for Expected Shortfall (Conditional VaR). CVaR is the coherent risk measure required by Basel III/IV for market risk capital. Add `es_amount: Decimal` (Expected Shortfall) to `VaRResult`, or create a separate `RiskMeasure` type.

4. **[HIGH] Missing cross-Greeks.** Missing are: (a) **veta** (d(vega)/d(time)) -- important for calendar spread management, (b) **speed** (d(gamma)/d(spot)) -- important for barrier options. For Phase 0, the current eight are a reasonable starting set, but the type should be designed for extensibility. **Recommendation:** Add an `additional: FrozenMap[str, Decimal]` field for non-standard Greeks, defaulting to `FrozenMap.EMPTY`.

5. **[MEDIUM] `PnLAttribution` does not enforce the decomposition invariant by construction.** The test checks `total == market + carry + trade + residual` at the test level, but the type itself accepts any five `Decimal` values. Consider computing `total_pnl` from the components in a factory method, making the invariant unbreakable.

6. **[MEDIUM] `ValuationResult` lacks a `valuation_date: datetime` field.** Every NPV is as-of a specific date. Without this field, the `ValuationResult` is ambiguous -- is it today's value? Yesterday's close? The `ValuationResult` itself should state the as-of date explicitly for self-documenting risk reports.

7. **[LOW] `Scenario.overrides` uses `FrozenMap[str, Decimal]` with opaque string keys.** For a quant implementing a stress test, there is no type-level guidance on what override keys are valid. Acceptable for Phase 0 but should be documented with a naming convention.

**RECOMMENDATIONS for Phase 1:**

- Introduce `Instrument`, `MarketDataSnapshot`, and `ModelConfig` types and migrate protocols to PLAN Section 3.4.3 signatures.
- Add a `RiskMeasure` type that unifies VaR and CVaR with a method discriminator (Historical, Parametric, Monte Carlo).
- The `Greeks` type should carry the bump sizes used for finite-difference computation (e.g., `delta_bump: Decimal = Decimal("0.01")`). Without knowing the bump size, a Greek is uninterpretable.

---

### 1.4 Missing Financial Types

1. **[HIGH] No `InstrumentRef` or `InstrumentIdentifier` type.** The `ISIN`, `LEI`, and `UTI` identifier types exist in `core/identifiers.py`, which is good. But there is no unified `InstrumentRef` type that can hold an ISIN, a CUSIP, a SEDOL, a Bloomberg ticker, or a RIC. The `instrument_id: str` used throughout `ValuationResult`, `Move`, and `LedgerEntry` is an opaque string with no validation. Phase 1 must introduce a discriminated union of identifier types.

2. **[HIGH] No `MarketDataSnapshot` type.** The PLAN Section 3.4.1 lists `Attestation[MarketDataSnapshot]` as an input to Pillar V, but no `MarketDataSnapshot` type is defined in Phase 0. This type should carry: (a) an as-of timestamp, (b) a `FrozenMap[str, Decimal]` of observables, (c) source metadata.

3. **[MEDIUM] No FX rate handling.** There is no `FXRate` type, no `CurrencyPair` type, and no mechanism for converting between `Money` in different currencies. The Money type correctly rejects cross-currency arithmetic, but the platform provides no facility for resolving the cross-currency case. Phase 1 must introduce an `FXRate` attested type and a `convert(m: Money, target_currency: str, rate: Attestation[FXRate]) -> Result[Money, str]` function.

4. **[MEDIUM] No `Position` type in Phase 0.** The PLAN Section 3.4.1 lists `list[Position]` as an input to Pillar V, and PASS2_REVIEW's conftest imports `Position` and `Account` types, but these are not defined in PHASE0_EXECUTION.md Steps 1-18.

5. **[LOW] No calendar or day count convention types.** For interest rate products (Phase 3), day count fractions (ACT/360, ACT/365, 30/360) and holiday calendars are essential. Not needed for Phase 0, but the Oracle layer should anticipate these in its architecture.

---

### 1.5 Financial Verdict

**Overall Assessment:** The Phase 0 foundation is architecturally sound. The core design decisions -- Decimal-only arithmetic, frozen immutable types, Result-based error handling, content-addressed attestations, the three-class epistemic partition -- are all correct and well-motivated.

However, there is a significant gap between what the PLAN (Section 15) specifies and what Pass 1 (PHASE0_EXECUTION.md) implements. Several invariants that the PLAN declares as "MUST" are not enforced in Pass 1. The most serious are the missing `bid <= ask` validation on `QuotedConfidence` (a no-arbitrage condition), the missing NaN/Infinity rejection on `Money.create`, and the divergence between the Pillar V protocol signatures.

**Required changes before implementation (blocking):**

| # | Item | Severity | Reference |
|---|------|----------|-----------|
| 1 | Money arithmetic must use `ATTESTOR_DECIMAL_CONTEXT` | CRITICAL | V-02, INV-M04 |
| 2 | `Money.create()` must reject NaN and Infinity | HIGH | INV-M02, PLAN 15.1.5 |
| 3 | Add `Money.div()` method | HIGH | PLAN 15.1.3 |
| 4 | Add `Money.round_to_minor_unit()` | HIGH | PLAN 15.1.3 |
| 5 | `QuotedConfidence` must enforce `bid <= ask` at construction | CRITICAL | INV-QC01 |
| 6 | `QuotedConfidence` must have `mid`, `spread`, `half_spread` properties | HIGH | INV-O06, PLAN 15.3.3 |
| 7 | `DerivedConfidence` must enforce non-empty `fit_quality` | HIGH | INV-DC03 |
| 8 | `DerivedConfidence` must enforce interval-level consistency | HIGH | INV-DC06 |
| 9 | Document that Pillar V protocol signatures are provisional (PLAN 3.4.3 is target) | HIGH | PLAN 3.4.3 |
| 10 | Add `var` and `pnl_attribution` method signatures to PricingEngine protocol | HIGH | PLAN 3.4.3 |
| 11 | Add Expected Shortfall field to `VaRResult` (or introduce `RiskMeasure` type) | HIGH | PLAN 3.4.2 |

**Recommendations for Phase 1 (non-blocking):**

| # | Item | Priority |
|---|------|----------|
| 1 | Introduce `CurrencyCode` refined type with ISO 4217 validation | HIGH |
| 2 | Introduce `InstrumentRef` discriminated union of identifier types | HIGH |
| 3 | Define `MarketDataSnapshot` type in Oracle layer | HIGH |
| 4 | Add `FXRate` attested type and cross-currency conversion | HIGH |
| 5 | Add `Position` type to Ledger or Oracle layer | HIGH |
| 6 | Add `Greeks.additional: FrozenMap[str, Decimal]` for extensible sensitivities | MEDIUM |
| 7 | Add `PnLAttribution` factory that computes `total` from components | MEDIUM |
| 8 | Add `ValuationResult.valuation_date` field | MEDIUM |
| 9 | Test Money algebraic laws via Hypothesis | MEDIUM |
| 10 | Add day count conventions and holiday calendar types in Oracle | LOW |

*The foundation types are a proposition about the financial world. The proposition is close to correct, but it has gaps where financially meaningless states are representable -- a QuotedConfidence with a negative spread, a Money containing NaN, a DerivedConfidence with an empty fit quality metric set. Each of these gaps is a place where bad data can enter the system unchallenged. Close them before building on top of them.*

---

---

## 2. Infrastructure Specification [FinOps]

**Scope:** Complete, provisionable infrastructure specification for Attestor Phase 0. Three Kafka topics, three Postgres tables, four Python persistence protocols with in-memory reference implementations, connection management, and health checks.

---

### 2.0 Design Principles (Non-Negotiable)

1. **Kafka is source of truth. Postgres is a derived projection.** If they disagree, Kafka wins. Rebuild Postgres by replaying the Kafka log. This is why attestation and transaction topics have infinite retention.
2. **All protocols return `Result[T, PersistenceError]`, never exceptions.** Infrastructure failures are visible values in the type system, not invisible control flow that blows up the call stack at 3am.
3. **Domain code never imports `kafka` or `psycopg`.** The domain defines protocol interfaces. Infrastructure implements them. The two meet only in `orchestration/`.
4. **Single-writer for the ledger.** The `ledger-writer` consumer group has exactly one instance. No locks, no deadlocks, no lock contention, trivially correct conservation laws.
5. **Immutability at every layer.** Kafka topics are append-only logs. Postgres tables reject UPDATE and DELETE via triggers. Python domain types are frozen dataclasses. There is no pencil in this system, only pens.

---

### 2.1 Kafka Topics

#### 2.1.1 `attestor.events.raw`

```yaml
topic_name: attestor.events.raw
partitions: 6
replication_factor: 3
retention_ms: 2592000000           # 30 days (30 * 24 * 3600 * 1000)
cleanup_policy: delete
min_insync_replicas: 2

key_schema:
  type: string
  description: |
    source_id -- identifies the upstream data source (e.g., "bloomberg",
    "ice", "internal-oms"). All messages from the same source land in
    the same partition, preserving per-source ordering.
  example: "bloomberg-equity-feed"

value_schema:
  type: json
  fields:
    source_id:
      type: string
      required: true
      description: "Upstream system identifier"
    raw_payload:
      type: string
      required: true
      description: "Opaque payload bytes, base64-encoded"
    content_type:
      type: string
      required: true
      enum: ["application/json", "application/xml", "text/csv", "application/octet-stream"]
      description: "MIME type of raw_payload before encoding"
    received_at:
      type: string
      format: "ISO 8601 UTC (YYYY-MM-DDTHH:MM:SS.ffffffZ)"
      required: true
      description: "Wall-clock time the gateway received this message"
    idempotency_key:
      type: string
      required: true
      description: "Source-assigned unique key for exactly-once ingestion"
    schema_version:
      type: string
      required: true
      description: "Version of the raw envelope schema (e.g., '1.0.0')"

idempotency: |
  Producer-side: Kafka idempotent producer (enable.idempotence=true) prevents
  duplicate writes from retries. Consumer-side: idempotency_key is persisted
  in the event_log table with a UNIQUE constraint. INSERT ... ON CONFLICT
  (idempotency_key) DO NOTHING. If the consumer restarts and re-processes a
  message, the DB write is a no-op.

ordering_guarantee: |
  Total order per source_id (same partition key). No global ordering across
  sources -- this is correct because raw events from different sources have
  no causal dependency.
```

**Partition count justification (6):** Phase 0 targets fewer than 6 data sources. One partition per source gives per-source total ordering. Six partitions allow up to 6 parallel `gateway-normalizer` consumers. If source count exceeds 6, increase partitions (Kafka allows increasing but never decreasing partition count).

**Retention justification (30 days):** Raw events are ephemeral ingestion artefacts. After normalization, the normalized topic and the attestation topic are the durable records. Thirty days provides sufficient runway for debugging ingestion failures and replaying normalization bugs without paying infinite storage cost for opaque blobs.

---

#### 2.1.2 `attestor.events.normalized`

```yaml
topic_name: attestor.events.normalized
partitions: 6
replication_factor: 3
retention_ms: 7776000000           # 90 days (90 * 24 * 3600 * 1000)
cleanup_policy: delete
min_insync_replicas: 2

key_schema:
  type: string
  description: |
    instrument_id -- the canonical instrument identifier after normalization
    (e.g., ISIN, internal symbol). All events for the same instrument are
    ordered within a partition. This is the partition key strategy from
    PLAN 11.3.2: observable-level ordering for downstream consumers.
  example: "US0378331005"

value_schema:
  type: json
  fields:
    instrument_id:
      type: string
      required: true
      description: "Canonical instrument identifier (ISIN or internal)"
    event_type:
      type: string
      required: true
      enum: ["TRADE", "QUOTE", "CORPORATE_ACTION", "REFERENCE_DATA"]
      description: "Normalized event classification"
    payload:
      type: object
      required: true
      description: "Canonical JSON payload -- schema varies by event_type"
    source_id:
      type: string
      required: true
      description: "Original source identifier, preserved from raw"
    event_time:
      type: string
      format: "ISO 8601 UTC"
      required: true
      description: "When the event occurred in the real world (valid_time axis)"
    normalized_at:
      type: string
      format: "ISO 8601 UTC"
      required: true
      description: "When normalization completed (system_time axis)"
    idempotency_key:
      type: string
      required: true
      description: "Propagated from raw event -- same key, same event"
    raw_event_ref:
      type: string
      required: true
      description: "Topic:partition:offset of the originating raw event"
    schema_version:
      type: string
      required: true
      description: "Version of the normalized message schema"

idempotency: |
  Same mechanism as raw: idempotency_key propagated end-to-end from source
  through raw through normalized. Downstream consumers (ledger-writer,
  oracle-ingester) use idempotency_key for dedup at the Postgres layer.

ordering_guarantee: |
  Total order per instrument_id (same partition key). The ledger-writer
  consumer reads this topic and processes all events for a given instrument
  in the order they were normalized. Cross-instrument ordering is not
  guaranteed and not needed -- the ledger engine processes instruments
  independently.
```

**Partition count justification (6):** Matched to `attestor.events.raw` for Phase 0. Normalization is a stateless map operation -- each raw event produces exactly one normalized event. In production (PLAN 11.3.2 specifies 24 for `normalized.*`), this scales by increasing partitions.

**Retention justification (90 days):** Normalized events are the canonical representation used for audit trails and replay. Ninety days covers a full quarter, sufficient for regulatory lookback on T+1 settlement breaks, reconciliation investigations, and end-of-quarter reporting. Beyond 90 days, the attestation topic (infinite retention) serves as the permanent record.

---

#### 2.1.3 `attestor.attestations`

```yaml
topic_name: attestor.attestations
partitions: 6
replication_factor: 3
retention_ms: -1                   # Infinite retention -- attestations are never deleted
cleanup_policy: delete
min_insync_replicas: 2

key_schema:
  type: string
  description: |
    attestation_id -- the SHA-256 hash of the full attestation identity
    (source + timestamp + confidence + value + provenance). Per V-01 /
    GAP-01: this is NOT content_hash (which hashes only the value).
    Two observations of the same value from different sources produce
    different attestation_ids. Keying by attestation_id means writing
    the same attestation twice is a no-op (same key, same value).
  example: "a3f2b8c91d...64-char-hex"

value_schema:
  type: json
  fields:
    attestation_id:
      type: string
      required: true
      description: "SHA-256 of canonical_bytes(source, timestamp, confidence, value, provenance)"
    content_hash:
      type: string
      required: true
      description: "SHA-256 of canonical_bytes(value) -- for dedup-by-value queries"
    value_type:
      type: string
      required: true
      description: "Fully qualified type name of the attested value"
    value_json:
      type: object
      required: true
      description: "Canonical JSON serialization of the attested value"
    confidence_type:
      type: string
      required: true
      enum: ["FIRM", "QUOTED", "DERIVED"]
      description: "Epistemic confidence classification"
    confidence_json:
      type: object
      required: true
      description: "Full confidence payload (source, bid/ask, method, etc.)"
    source:
      type: string
      required: true
      description: "Attestation source identifier"
    provenance:
      type: array
      items:
        type: string
      required: true
      description: "Ordered list of input attestation_ids (empty for Firm)"
    event_time:
      type: string
      format: "ISO 8601 UTC"
      required: true
      description: "When the attested event occurred (valid_time axis)"
    system_time:
      type: string
      format: "ISO 8601 UTC"
      required: true
      description: "When the attestation was created (system_time axis)"
    schema_version:
      type: string
      required: true
      description: "Version of the attestation envelope schema"

idempotency: |
  Producer: Kafka idempotent producer. Content-level: attestation_id is a
  deterministic hash of all fields. Publishing the same attestation twice
  produces the same key and the same value -- Kafka appends a duplicate
  message, but downstream consumers dedup on attestation_id via Postgres
  UNIQUE constraint (INSERT ... ON CONFLICT (attestation_id) DO NOTHING).

ordering_guarantee: |
  No global ordering required. Attestations are content-addressed and
  independently immutable (INV-O01). Provenance chains are resolved by
  hash lookup, not by offset ordering.
```

**Partition count justification (6):** Attestations are write-once, read-many. Six partitions provide adequate parallelism for the `attestation-signer` consumer group (PLAN 11.3.3) while keeping partition count low. Matches the `attested.*` tier from PLAN 11.3.2.

**Retention justification (infinite):** Attestations are the permanent, immutable truth store. Every derived value, every position, every P&L number traces back to attestations via provenance chains. Deleting an attestation would sever the audit trail and violate INV-O01. Regulatory requirements (MiFID II: 5 years; Dodd-Frank: 5 years; SOX: 7 years) mandate long retention. Infinite retention eliminates the risk of accidentally aging out critical provenance data.

---

#### 2.1.4 Consumer Group Design (Phase 0)

| Consumer Group | Reads From | Writes To | Instances | Notes |
|---|---|---|---|---|
| `gateway-normalizer` | `attestor.events.raw` | `attestor.events.normalized` | Up to 6 (stateless) | Parallel normalization. Stateless -- no local state, no coordination. |
| `ledger-writer` | `attestor.events.normalized` | `attestor.attestations` + Postgres | **Exactly 1** | Single-writer invariant (PLAN 11.6.1, INV-L08). All accounting mutations flow through this single consumer. |
| `snapshot-materializer` | `attestor.attestations` | Postgres (derived projection) | 1 | Reads attestations, writes to Postgres `attestations` table. Single instance to avoid write conflicts. |

**Ordering guarantees summary:**
- Within `attestor.events.raw`: total order per `source_id`
- Within `attestor.events.normalized`: total order per `instrument_id`
- Within `attestor.attestations`: no ordering dependency (content-addressed, independently immutable)
- `ledger-writer` processes partitions sequentially within its single instance, providing total order for all accounting mutations

---

### 2.2 Postgres DDL

**Schema:** `attestor`
**Naming convention:** lowercase, snake_case, singular table names
**Time columns:** All temporal columns use `TIMESTAMPTZ` (never `TIMESTAMP`). All default to `NOW()` in UTC.
**Numeric columns:** All financial quantities use `NUMERIC` (never `FLOAT` or `DOUBLE PRECISION`).
**Mutation policy:** Every table has a `BEFORE UPDATE OR DELETE` trigger that raises an exception. These tables are append-only.

#### 2.2.1 Attestations Table

This incorporates the V-01 / GAP-01 / GAP-18 / GAP-19 fix: `attestation_id` is the PK, `content_hash` is a non-unique indexed column.

```sql
-- =============================================================================
-- 001_attestations.sql
-- Attestation store: content-addressed, append-only, bitemporal.
--
-- Design decisions:
--   PK = attestation_id (hash of full attestation identity, per V-01/GAP-01)
--   content_hash = hash of value only (indexed, non-unique)
--   Kafka is source of truth; this table is a derived, queryable projection.
--   No UPDATE. No DELETE. Enforced by trigger.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS attestor;

-- ---------------------------------------------------------------------------
-- Immutability enforcement function (shared by all attestor tables)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION attestor.prevent_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'Table attestor.% is append-only: % operations are forbidden. '
        'Financial ledgers use pens, not pencils.',
        TG_TABLE_NAME, TG_OP;
    RETURN NULL;  -- never reached, but required by plpgsql
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ---------------------------------------------------------------------------
-- attestor.attestations
-- ---------------------------------------------------------------------------
CREATE TABLE attestor.attestations (
    -- Primary identity: SHA-256 of canonical_bytes(source, timestamp,
    -- confidence, value, provenance). Two observations of the same value
    -- from different sources produce different attestation_ids.
    attestation_id      TEXT            NOT NULL,

    -- Value identity: SHA-256 of canonical_bytes(value) only. Multiple
    -- attestations may share the same content_hash if they attest the
    -- same value from different sources. Used for dedup-by-value queries.
    content_hash        TEXT            NOT NULL,

    -- Fully qualified Python type name of the attested value.
    -- Part of the canonical serialization contract (PASS2 D-12/GAP-11).
    -- Renaming a type is a breaking change.
    value_type          TEXT            NOT NULL
                        CHECK (length(value_type) > 0),

    -- Canonical JSON serialization of the attested value.
    -- Stored as JSONB for queryability.
    value_json          JSONB           NOT NULL,

    -- Epistemic confidence classification.
    confidence_type     TEXT            NOT NULL
                        CHECK (confidence_type IN ('FIRM', 'QUOTED', 'DERIVED')),

    -- Full confidence payload as JSONB. Schema depends on confidence_type.
    confidence_json     JSONB           NOT NULL,

    -- Attestation source identifier. NonEmptyStr in Python (GAP-20).
    source              TEXT            NOT NULL
                        CHECK (length(source) > 0),

    -- Ordered array of input attestation_ids. Empty for Firm attestations.
    provenance_refs     TEXT[]          NOT NULL DEFAULT '{}',

    -- BITEMPORAL COLUMNS --

    -- valid_time: when the attested event occurred in the real world.
    valid_time          TIMESTAMPTZ     NOT NULL,

    -- system_time: when this row was inserted into the database.
    system_time         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- CONSTRAINTS --
    CONSTRAINT pk_attestations
        PRIMARY KEY (attestation_id),

    CONSTRAINT chk_attestation_id_length
        CHECK (length(attestation_id) = 64),  -- SHA-256 hex digest

    CONSTRAINT chk_content_hash_length
        CHECK (length(content_hash) = 64)
);

-- Immutability trigger: reject UPDATE and DELETE
CREATE TRIGGER trg_attestations_immutable
    BEFORE UPDATE OR DELETE ON attestor.attestations
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();

COMMENT ON TABLE attestor.attestations IS
    'Content-addressed attestation store. PK is attestation_id (hash of full '
    'identity). Append-only: UPDATE and DELETE are rejected by trigger. '
    'Insert pattern: INSERT INTO attestor.attestations (...) VALUES (...) '
    'ON CONFLICT (attestation_id) DO NOTHING;';

-- INDEXES --

-- content_hash: non-unique index for dedup-by-value queries.
CREATE INDEX idx_attestations_content_hash
    ON attestor.attestations (content_hash);

-- valid_time: bitemporal query axis.
CREATE INDEX idx_attestations_valid_time
    ON attestor.attestations (valid_time);

-- system_time: bitemporal query axis.
CREATE INDEX idx_attestations_system_time
    ON attestor.attestations (system_time);

-- confidence_type: filter by epistemic class.
CREATE INDEX idx_attestations_confidence_type
    ON attestor.attestations (confidence_type);

-- source: filter by data source.
CREATE INDEX idx_attestations_source
    ON attestor.attestations (source);

-- provenance_refs: GIN index for array containment queries.
CREATE INDEX idx_attestations_provenance_refs
    ON attestor.attestations USING GIN (provenance_refs);
```

---

#### 2.2.2 Event Log Table

```sql
-- =============================================================================
-- 002_event_log.sql
-- Append-only ordered event log. Every state change is recorded here as an
-- immutable event. This is the Postgres projection of the Kafka event stream.
-- =============================================================================

CREATE TABLE attestor.event_log (
    -- Monotonically increasing sequence number.
    sequence_id         BIGSERIAL       NOT NULL,

    -- Event type discriminator.
    event_type          TEXT            NOT NULL
                        CHECK (length(event_type) > 0),

    -- Full event payload as JSONB.
    payload             JSONB           NOT NULL,

    -- Source-assigned idempotency key. UNIQUE constraint ensures that
    -- reprocessing the same Kafka message does not create duplicate events.
    idempotency_key     TEXT            NOT NULL,

    -- Kafka provenance: "topic:partition:offset"
    kafka_ref           TEXT,

    -- BITEMPORAL COLUMNS --
    valid_time          TIMESTAMPTZ     NOT NULL,
    system_time         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- CONSTRAINTS --
    CONSTRAINT pk_event_log
        PRIMARY KEY (sequence_id),

    CONSTRAINT uq_event_log_idempotency_key
        UNIQUE (idempotency_key)
);

-- Immutability trigger
CREATE TRIGGER trg_event_log_immutable
    BEFORE UPDATE OR DELETE ON attestor.event_log
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();

COMMENT ON TABLE attestor.event_log IS
    'Append-only event log. Idempotency enforced by UNIQUE on idempotency_key. '
    'Insert pattern: INSERT ... ON CONFLICT (idempotency_key) DO NOTHING;';

-- INDEXES --
CREATE INDEX idx_event_log_valid_time
    ON attestor.event_log (valid_time);

CREATE INDEX idx_event_log_system_time
    ON attestor.event_log (system_time);

CREATE INDEX idx_event_log_event_type
    ON attestor.event_log (event_type);

CREATE INDEX idx_event_log_type_valid_time
    ON attestor.event_log (event_type, valid_time);
```

---

#### 2.2.3 Schema Registry Table

```sql
-- =============================================================================
-- 003_schema_registry.sql
-- Type version tracking for canonical serialization schemas.
-- =============================================================================

CREATE TABLE attestor.schema_registry (
    -- Fully qualified Python type name.
    type_name           TEXT            NOT NULL
                        CHECK (length(type_name) > 0),

    -- Monotonically increasing version number per type_name.
    version             INTEGER         NOT NULL
                        CHECK (version > 0),

    -- SHA-256 hash of the canonical JSON Schema definition.
    schema_hash         TEXT            NOT NULL
                        CHECK (length(schema_hash) = 64),

    -- JSON Schema document for this type at this version.
    schema_json         JSONB           NOT NULL,

    -- BITEMPORAL COLUMNS --
    valid_time          TIMESTAMPTZ     NOT NULL,
    registered_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- CONSTRAINTS --
    CONSTRAINT pk_schema_registry
        PRIMARY KEY (type_name, version),

    CONSTRAINT uq_schema_registry_hash
        UNIQUE (type_name, schema_hash)
);

-- Immutability trigger
CREATE TRIGGER trg_schema_registry_immutable
    BEFORE UPDATE OR DELETE ON attestor.schema_registry
    FOR EACH ROW EXECUTE FUNCTION attestor.prevent_mutation();

COMMENT ON TABLE attestor.schema_registry IS
    'Type version tracking for canonical serialization schemas. Append-only. '
    'A new version creates a new row. Existing versions are never modified.';

-- INDEXES --
CREATE INDEX idx_schema_registry_type_name
    ON attestor.schema_registry (type_name);

CREATE INDEX idx_schema_registry_registered_at
    ON attestor.schema_registry (registered_at);
```

---

### 2.3 Persistence Protocols (Python)

#### 2.3.1 Protocol Definitions

File: `attestor/infra/protocols.py`

```python
"""Infrastructure protocol definitions for Attestor Phase 0.

Domain code depends on these abstractions. Infrastructure code implements them.
The two never meet except in orchestration/.

All protocols return Result[T, PersistenceError]. Infrastructure failures are
visible values in the type system, never invisible exceptions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from attestor.core.result import Result
from attestor.core.types import BitemporalEnvelope
from attestor.core.errors import PersistenceError
from attestor.oracle.attestation import Attestation
from attestor.ledger.transactions import Transaction


@runtime_checkable
class AttestationStore(Protocol):
    """Content-addressed attestation storage.

    Keyed by attestation_id (hash of full attestation identity, per V-01/GAP-01).
    content_hash is a secondary attribute for dedup-by-value queries.

    Invariants:
      - store() is idempotent: storing the same attestation twice returns
        the same attestation_id without creating a duplicate (INV-X03).
      - retrieve() returns Err if the attestation_id is not found.
      - exists() returns Result[bool, PersistenceError] (GAP-13).
    """

    def store(
        self, attestation: Attestation[object],
    ) -> Result[str, PersistenceError]:
        """Store an attestation. Returns Ok(attestation_id) on success.

        If an attestation with the same attestation_id already exists,
        returns Ok(attestation_id) without creating a duplicate.
        """
        ...

    def retrieve(
        self, attestation_id: str,
    ) -> Result[Attestation[object], PersistenceError]:
        """Retrieve an attestation by its attestation_id.

        Returns Err(PersistenceError) if not found or if the underlying
        storage is unreachable.
        """
        ...

    def exists(
        self, attestation_id: str,
    ) -> Result[bool, PersistenceError]:
        """Check whether an attestation_id exists in the store.

        Returns Result[bool, PersistenceError] -- NOT bare bool -- because
        the production Postgres adapter may raise connection errors (GAP-13).
        """
        ...


@runtime_checkable
class EventBus(Protocol):
    """Append-only event transport (Kafka in production).

    Messages are keyed for deterministic partitioning. Values are opaque
    bytes -- serialization is the caller's responsibility.
    """

    def publish(
        self, topic: str, key: str, value: bytes,
    ) -> Result[None, PersistenceError]:
        """Publish a message to a topic.

        The key determines partition assignment.
        Returns Err on publish failure (timeout, broker unavailable).
        """
        ...

    def subscribe(
        self, topic: str, group: str,
    ) -> Result[None, PersistenceError]:
        """Subscribe to a topic as part of a consumer group.

        Returns Err if subscription fails.
        """
        ...


@runtime_checkable
class TransactionLog(Protocol):
    """Append-only transaction log for deterministic replay.

    Every accounting mutation is recorded as a BitemporalEnvelope[Transaction].
    """

    def append(
        self, envelope: BitemporalEnvelope[Transaction],
    ) -> Result[None, PersistenceError]:
        """Append a transaction to the log. Returns Err on write failure."""
        ...

    def replay(
        self,
    ) -> Result[tuple[BitemporalEnvelope[Transaction], ...], PersistenceError]:
        """Replay the entire transaction log from the beginning."""
        ...

    def replay_since(
        self, since: datetime,
    ) -> Result[tuple[BitemporalEnvelope[Transaction], ...], PersistenceError]:
        """Replay transactions with knowledge_time >= since."""
        ...


@runtime_checkable
class StateStore(Protocol):
    """Key-value state store for derived projections.

    Used by consumers for checkpoint offsets and materialized view metadata.
    NOT the accounting state (which lives in TransactionLog).
    """

    def get(
        self, key: str,
    ) -> Result[bytes | None, PersistenceError]:
        """Get a value by key. Returns Ok(None) if key does not exist."""
        ...

    def put(
        self, key: str, value: bytes,
    ) -> Result[None, PersistenceError]:
        """Put a value by key. Overwrites any existing value."""
        ...
```

---

#### 2.3.2 In-Memory Reference Implementations

File: `attestor/infra/memory_adapter.py`

```python
"""In-memory implementations of all four infrastructure protocols.

Test doubles that let the entire test suite run without Kafka or Postgres.
All classes are @final. None of them are production code.
"""

from __future__ import annotations

from datetime import datetime
from typing import final

from attestor.core.result import Ok, Err, Result
from attestor.core.types import BitemporalEnvelope
from attestor.core.errors import PersistenceError
from attestor.oracle.attestation import Attestation
from attestor.ledger.transactions import Transaction


def _persistence_error(operation: str, detail: str) -> PersistenceError:
    """Helper to construct PersistenceError with consistent formatting."""
    return PersistenceError(
        message=detail,
        code="PERSISTENCE_ERROR",
        timestamp=datetime.now(tz=__import__("datetime").timezone.utc),
        source=f"memory_adapter.{operation}",
        operation=operation,
    )


@final
class InMemoryAttestationStore:
    """In-memory attestation store keyed by attestation_id.

    Per V-01/GAP-01: the store key is attestation_id (hash of full
    attestation identity), NOT content_hash (hash of value only).
    """

    def __init__(self) -> None:
        self._store: dict[str, Attestation[object]] = {}

    def store(
        self, attestation: Attestation[object],
    ) -> Result[str, PersistenceError]:
        """Store. Idempotent: duplicate attestation_id is a no-op."""
        aid = attestation.attestation_id
        if aid not in self._store:
            self._store[aid] = attestation
        return Ok(aid)

    def retrieve(
        self, attestation_id: str,
    ) -> Result[Attestation[object], PersistenceError]:
        """Retrieve by attestation_id. Returns Err if not found."""
        if attestation_id in self._store:
            return Ok(self._store[attestation_id])
        return Err(_persistence_error(
            "retrieve",
            f"Attestation not found: {attestation_id}",
        ))

    def exists(
        self, attestation_id: str,
    ) -> Result[bool, PersistenceError]:
        """Check existence. Returns Result[bool, ...] per GAP-13."""
        return Ok(attestation_id in self._store)

    # -- Test-only helpers (not part of the Protocol) --

    def count(self) -> int:
        return len(self._store)

    def all_ids(self) -> tuple[str, ...]:
        return tuple(self._store.keys())


@final
class InMemoryEventBus:
    """In-memory event bus. Messages are stored per-topic as (key, value) pairs."""

    def __init__(self) -> None:
        self._topics: dict[str, list[tuple[str, bytes]]] = {}

    def publish(
        self, topic: str, key: str, value: bytes,
    ) -> Result[None, PersistenceError]:
        if topic not in self._topics:
            self._topics[topic] = []
        self._topics[topic].append((key, value))
        return Ok(None)

    def subscribe(
        self, topic: str, group: str,
    ) -> Result[None, PersistenceError]:
        return Ok(None)

    # -- Test-only helpers --

    def get_messages(self, topic: str) -> list[tuple[str, bytes]]:
        return list(self._topics.get(topic, []))

    def topic_count(self) -> int:
        return len(self._topics)


@final
class InMemoryTransactionLog:
    """In-memory append-only transaction log."""

    def __init__(self) -> None:
        self._log: list[BitemporalEnvelope[Transaction]] = []

    def append(
        self, envelope: BitemporalEnvelope[Transaction],
    ) -> Result[None, PersistenceError]:
        self._log.append(envelope)
        return Ok(None)

    def replay(
        self,
    ) -> Result[tuple[BitemporalEnvelope[Transaction], ...], PersistenceError]:
        return Ok(tuple(self._log))

    def replay_since(
        self, since: datetime,
    ) -> Result[tuple[BitemporalEnvelope[Transaction], ...], PersistenceError]:
        filtered = tuple(
            e for e in self._log if e.knowledge_time >= since
        )
        return Ok(filtered)

    # -- Test-only helpers --

    def count(self) -> int:
        return len(self._log)


@final
class InMemoryStateStore:
    """In-memory key-value state store."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def get(
        self, key: str,
    ) -> Result[bytes | None, PersistenceError]:
        return Ok(self._store.get(key))

    def put(
        self, key: str, value: bytes,
    ) -> Result[None, PersistenceError]:
        self._store[key] = value
        return Ok(None)

    # -- Test-only helpers --

    def count(self) -> int:
        return len(self._store)

    def keys(self) -> tuple[str, ...]:
        return tuple(self._store.keys())
```

---

#### 2.3.3 Structural Subtyping Verification

```python
"""Test that in-memory adapters satisfy infrastructure protocols."""

from attestor.infra.protocols import (
    AttestationStore, EventBus, TransactionLog, StateStore,
)
from attestor.infra.memory_adapter import (
    InMemoryAttestationStore, InMemoryEventBus,
    InMemoryTransactionLog, InMemoryStateStore,
)


def test_attestation_store_satisfies_protocol() -> None:
    store: AttestationStore = InMemoryAttestationStore()
    assert isinstance(store, AttestationStore)


def test_event_bus_satisfies_protocol() -> None:
    bus: EventBus = InMemoryEventBus()
    assert isinstance(bus, EventBus)


def test_transaction_log_satisfies_protocol() -> None:
    log: TransactionLog = InMemoryTransactionLog()
    assert isinstance(log, TransactionLog)


def test_state_store_satisfies_protocol() -> None:
    store: StateStore = InMemoryStateStore()
    assert isinstance(store, StateStore)
```

---

### 2.4 Connection Management

#### 2.4.1 Kafka Producer Configuration

```python
"""Kafka producer configuration for Attestor Phase 0.

Configuration DATA only -- no kafka-python or confluent-kafka import.
The production orchestration layer reads these values at startup.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import final


@final
@dataclass(frozen=True, slots=True)
class KafkaProducerConfig:
    """Configuration for Kafka producers.

    Designed for exactly-once semantics and durability. Every setting
    is justified by a production failure mode it prevents.
    """

    bootstrap_servers: str = "localhost:9092"
    key_serializer: str = "utf-8"
    value_serializer: str = "raw"

    # Durability: acks=all means leader AND all in-sync replicas must ack.
    acks: str = "all"

    # Idempotent producer: Kafka deduplicates retries.
    enable_idempotence: bool = True

    # Strict ordering even during retries.
    max_in_flight_requests_per_connection: int = 1

    retries: int = 3
    retry_backoff_ms: int = 100

    # Batch: linger 5ms to batch messages. For T+1, 5ms is negligible.
    linger_ms: int = 5
    batch_size: int = 16384            # 16 KB

    # LZ4: best trade-off for financial JSON payloads.
    compression_type: str = "lz4"

    request_timeout_ms: int = 30000    # 30 seconds
    delivery_timeout_ms: int = 120000  # 2 minutes


@final
@dataclass(frozen=True, slots=True)
class KafkaConsumerConfig:
    """Configuration for Kafka consumers.

    At-least-once delivery with application-level dedup via idempotency_key.
    """

    bootstrap_servers: str = "localhost:9092"
    key_deserializer: str = "utf-8"
    value_deserializer: str = "raw"
    group_id: str = "attestor-default"

    # Start from earliest on first join. "latest" silently skips messages.
    auto_offset_reset: str = "earliest"

    # Manual commit after processing + Postgres write = at-least-once.
    enable_auto_commit: bool = False

    max_poll_records: int = 100
    session_timeout_ms: int = 30000
    max_poll_interval_ms: int = 300000  # 5 minutes

    fetch_min_bytes: int = 1
    fetch_max_wait_ms: int = 500
```

---

#### 2.4.2 Postgres Connection Pool Configuration

```python
"""Postgres connection pool configuration for Attestor Phase 0.

Configuration DATA only -- no psycopg or asyncpg import.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import final


@final
@dataclass(frozen=True, slots=True)
class PostgresPoolConfig:
    """Configuration for the Postgres connection pool."""

    host: str = "localhost"
    port: int = 5432
    database: str = "attestor"
    user: str = "attestor_app"
    # password: loaded from env var ATTESTOR_DB_PASSWORD. NEVER in config.

    min_size: int = 2
    max_size: int = 10
    connection_timeout_s: int = 5
    statement_timeout_ms: int = 30000
    idle_timeout_s: int = 300          # 5 minutes
    search_path: str = "attestor,public"
    ssl_mode: str = "prefer"
    application_name: str = "attestor-phase0"

    @property
    def dsn(self) -> str:
        """Construct a connection string (without password)."""
        return (
            f"host={self.host} port={self.port} dbname={self.database} "
            f"user={self.user} sslmode={self.ssl_mode} "
            f"application_name={self.application_name} "
            f"options='-c search_path={self.search_path} "
            f"-c statement_timeout={self.statement_timeout_ms}'"
        )
```

---

#### 2.4.3 Health Check Protocol

```python
"""Health check protocol for Attestor infrastructure dependencies.

Kubernetes probes:
  livenessProbe  -> GET /health/live   -> liveness_check()
  readinessProbe -> GET /health/ready  -> readiness_check()
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, final

from attestor.core.result import Ok, Err, Result
from attestor.core.errors import PersistenceError


@final
@dataclass(frozen=True, slots=True)
class HealthStatus:
    healthy: bool
    component: str
    message: str
    checked_at: datetime
    latency_ms: float


@final
@dataclass(frozen=True, slots=True)
class SystemHealth:
    overall_healthy: bool
    checks: tuple[HealthStatus, ...]
    checked_at: datetime


class HealthCheckable(Protocol):
    def health_check(self) -> Result[HealthStatus, PersistenceError]: ...


def liveness_check() -> HealthStatus:
    return HealthStatus(
        healthy=True, component="process", message="alive",
        checked_at=datetime.now(tz=timezone.utc), latency_ms=0.0,
    )


def readiness_check(
    dependencies: tuple[HealthCheckable, ...],
) -> SystemHealth:
    checks: list[HealthStatus] = []
    all_healthy = True
    for dep in dependencies:
        result = dep.health_check()
        match result:
            case Ok(status):
                checks.append(status)
                if not status.healthy:
                    all_healthy = False
            case Err(error):
                checks.append(HealthStatus(
                    healthy=False, component="unknown",
                    message=f"Health check failed: {error.message}",
                    checked_at=datetime.now(tz=timezone.utc), latency_ms=0.0,
                ))
                all_healthy = False
    return SystemHealth(
        overall_healthy=all_healthy,
        checks=tuple(checks),
        checked_at=datetime.now(tz=timezone.utc),
    )
```

---

#### 2.4.4 Error Handling at Infrastructure Boundaries

**Retry Policy:**

```python
@final
@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_retries: int = 3
    base_delay_ms: int = 100
    max_delay_ms: int = 5000
    jitter_factor: float = 0.1  # float OK: infra config, not financial arithmetic
    retry_on_persistence_error: bool = True
```

**Dead Letter Queue:**

```yaml
dlq_topic_pattern: "attestor.dlq.{original_topic}"
partitions: 1                      # Human review, no parallelism needed
replication_factor: 3
retention_ms: 7776000000           # 90 days
cleanup_policy: delete

dlq_message_schema:
  original_topic: string
  original_key: string
  original_value: bytes
  error_type: string
  error_message: string
  error_code: string
  attempt_count: int
  first_failure_at: ISO8601_UTC
  last_failure_at: ISO8601_UTC
  consumer_group: string
  consumer_instance: string
```

**Circuit Breaker:**

```python
@final
class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@final
@dataclass(frozen=True, slots=True)
class CircuitBreakerConfig:
    component: str
    failure_threshold: int = 5
    reset_timeout_ms: int = 30000      # 30 seconds
    success_threshold: int = 1
    half_open_max_requests: int = 1
```

**Error handling decision matrix:**

| Failure Mode | Retry? | DLQ? | Circuit Breaker? | Action |
|---|---|---|---|---|
| Kafka producer timeout | Yes, 3x exponential | Yes, after exhausting | Yes, on broker | Write to local WAL, alert ops |
| Kafka consumer lag | N/A | N/A | N/A | Scale consumers. Alert if lag > 1000. |
| Postgres write timeout | Yes, 1x immediate | No (projection only) | Yes, on Postgres | Skip materialization, catch up next batch |
| Postgres read timeout | No | No | Yes, on Postgres | Return `Err` immediately |
| Content hash collision | **NEVER** | **NEVER** | **HALT** | SHA-256 collision = data corruption. Page on-call. |
| Attestation store full | No | No | N/A | Alert before it happens (monitor disk). |

---

### 2.5 Topic Configuration Module

File: `attestor/infra/config.py`

```python
"""Kafka topic definitions and infrastructure configuration for Phase 0.

No Kafka client library is imported. Pure configuration data.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import final


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
    replication_factor: int
    retention_ms: int              # -1 for infinite retention
    cleanup_policy: str
    min_insync_replicas: int


def phase0_topic_configs() -> tuple[TopicConfig, ...]:
    return (
        TopicConfig(
            name=TOPIC_EVENTS_RAW,
            partitions=6, replication_factor=3,
            retention_ms=30 * 24 * 3600 * 1000,
            cleanup_policy="delete", min_insync_replicas=2,
        ),
        TopicConfig(
            name=TOPIC_EVENTS_NORMALIZED,
            partitions=6, replication_factor=3,
            retention_ms=90 * 24 * 3600 * 1000,
            cleanup_policy="delete", min_insync_replicas=2,
        ),
        TopicConfig(
            name=TOPIC_ATTESTATIONS,
            partitions=6, replication_factor=3,
            retention_ms=-1,
            cleanup_policy="delete", min_insync_replicas=2,
        ),
    )
```

---

### 2.6 Gap Resolution Traceability

| Gap ID | PASS2 Description | Resolution in This Specification |
|---|---|---|
| **V-01** | `content_hash` hashes only value, not full attestation identity | `attestation_id` is PK in Postgres (2.2.1), store key in `AttestationStore` (2.3.1), partition key in `attestor.attestations` (2.1.3). `content_hash` retained as non-unique indexed column. |
| **GAP-01** | Add `attestation_id` field, use as PK | Postgres DDL uses `attestation_id TEXT PRIMARY KEY` (2.2.1). `InMemoryAttestationStore` keys by `attestation_id` (2.3.2). |
| **GAP-13** | `AttestationStore.exists()` returns `bool` not `Result` | `exists()` signature is `Result[bool, PersistenceError]` (2.3.1). In-memory adapter returns `Ok(bool)` (2.3.2). |
| **GAP-18** | Postgres `attestations` table PK is `content_hash` | Changed to `attestation_id TEXT PRIMARY KEY`. `content_hash` is non-unique indexed column (2.2.1). |
| **GAP-19** | No `attestation_id` column in Postgres schema | `attestation_id` column added as first column in DDL (2.2.1). |

---

### 2.7 Provisioning Checklist

| Step | Action | Verification |
|---|---|---|
| 1 | Create Kafka cluster (3 brokers min) | `kafka-broker-api-versions.sh --bootstrap-server localhost:9092` |
| 2 | Create `attestor.events.raw` | `kafka-topics.sh --describe --topic attestor.events.raw` confirms 6 partitions, RF=3 |
| 3 | Create `attestor.events.normalized` | `kafka-topics.sh --describe` confirms 6 partitions, RF=3, retention=90d |
| 4 | Create `attestor.attestations` | `kafka-topics.sh --describe` confirms 6 partitions, RF=3, retention=-1 |
| 5 | Set `min.insync.replicas=2` on all topics | `kafka-configs.sh --describe` confirms |
| 6 | Create Postgres database `attestor` | `psql -c "SELECT 1" -d attestor` |
| 7 | Run `sql/001_attestations.sql` | `psql -c "\d attestor.attestations"` shows attestation_id PK |
| 8 | Run `sql/002_event_log.sql` | `psql -c "\d attestor.event_log"` shows sequence_id PK |
| 9 | Run `sql/003_schema_registry.sql` | `psql -c "\d attestor.schema_registry"` shows composite PK |
| 10 | Verify immutability triggers | `UPDATE attestor.attestations SET source='x' WHERE false` raises exception |
| 11 | Create `attestor_app` user | INSERT succeeds, UPDATE fails |
| 12 | Run Python test suite | `pytest tests/ -x --tb=short -v` -- all green (in-memory, no Kafka/Postgres required) |

---

### 2.8 Kafka Topic Creation Commands

```bash
#!/usr/bin/env bash
# Phase 0 Kafka topic provisioning script

BOOTSTRAP="localhost:9092"

kafka-topics.sh --create \
  --bootstrap-server "$BOOTSTRAP" \
  --topic attestor.events.raw \
  --partitions 6 \
  --replication-factor 3 \
  --config retention.ms=2592000000 \
  --config cleanup.policy=delete \
  --config min.insync.replicas=2

kafka-topics.sh --create \
  --bootstrap-server "$BOOTSTRAP" \
  --topic attestor.events.normalized \
  --partitions 6 \
  --replication-factor 3 \
  --config retention.ms=7776000000 \
  --config cleanup.policy=delete \
  --config min.insync.replicas=2

kafka-topics.sh --create \
  --bootstrap-server "$BOOTSTRAP" \
  --topic attestor.attestations \
  --partitions 6 \
  --replication-factor 3 \
  --config retention.ms=-1 \
  --config cleanup.policy=delete \
  --config min.insync.replicas=2

echo "--- Verifying topics ---"
for TOPIC in attestor.events.raw attestor.events.normalized attestor.attestations; do
  echo ""
  echo "=== $TOPIC ==="
  kafka-topics.sh --describe --bootstrap-server "$BOOTSTRAP" --topic "$TOPIC"
done
```

---

### 2.9 Infrastructure Actionability Verdict

> **Can a DevOps engineer read this section and provision Kafka + Postgres without asking a question?**

**Yes.** This section provides:
- Complete topic YAML with key/value schemas, retention justifications, and idempotency strategy
- Copy-paste SQL DDL with all constraints, indexes, triggers, and comments
- Copy-paste bash provisioning script
- Verification commands for every step
- Complete Python protocol definitions and in-memory test doubles
- Connection configuration with every setting justified
- Error handling matrix with explicit actions per failure mode

No additional clarification is required.

---

---

## 3. API Design Review [Lattner]

### 3.1 Result Composition Patterns

The Phase 0 `Result` type as specified in Step 2 of `PHASE0_EXECUTION.md` provides:

- `Ok[T]` -- frozen dataclass wrapping a success value
- `Err[E]` -- frozen dataclass wrapping an error value
- `unwrap(result)` -- module-level function, raises `RuntimeError` on `Err`
- `map_result(result, fn)` -- module-level function, applies `fn` to `Ok`, passes `Err` through

The PLAN (Section 4.1) additionally mentions `.map(f)` and `.bind(f)` as methods on both `Ok` and `Err`, and Pass 2 audits `Ok.map(f)`, `Ok.bind(f)`, `Err.map(f)`, and `Err.bind(f)` as if they exist. But Step 2 only specifies `unwrap` and `map_result` as free functions. **Pass 2 assumes methods that Pass 1 never defines.** This must be reconciled.

**Can the target composition pattern work?**

```python
result = (
    parse_amount(raw_amount)
    .and_then(lambda amt: parse_currency(raw_currency).map(lambda cur: (amt, cur)))
    .and_then(lambda pair: Money.parse(*pair))
)
```

The answer is **no**, not with the current spec. Here is what is missing:

**GAP-API-01: No `.map()` method on Ok/Err.** [VETO] The execution plan specifies `map_result` as a free function, not a method. This forces:

```python
map_result(map_result(parse_amount(raw), lambda a: ...), lambda b: ...)
```

This is unreadable. The method form `.map(f)` is essential for fluent chaining. Pass 2 assumes `.map()` exists as a method; Step 2 must specify it explicitly.

Required addition to `Ok[T]`:
```python
def map(self, f: Callable[[T], U]) -> Ok[U]:
    return Ok(f(self.value))
```

Required addition to `Err[E]`:
```python
def map(self, f: Callable[[Any], Any]) -> Err[E]:
    return self
```

**GAP-API-02: No `.bind()` / `.and_then()` method.** [VETO] Pass 2 audits `Ok.bind(f)` and `Err.bind(f)` as existing, but Step 2 never specifies them. Without `bind`, you cannot chain operations that themselves return `Result`. This is the monadic bind -- the single most important combinator for `Result`-returning code.

Required addition to `Ok[T]`:
```python
def bind(self, f: Callable[[T], Result[U, E]]) -> Result[U, E]:
    return f(self.value)

and_then = bind  # alias for Rust-familiar developers
```

Required addition to `Err[E]`:
```python
def bind(self, f: Callable[[Any], Any]) -> Err[E]:
    return self

and_then = bind
```

**Naming decision:** `.bind` as canonical name (category-theoretic, matches this project's vocabulary), `.and_then` as alias (meets Rust developers where they are).

**GAP-API-03: No `unwrap_or(default)`.** [HIGH] Every `Result`-returning factory (at least 12: `Money.create`, `PositiveDecimal.parse`, `NonZeroDecimal.parse`, `NonEmptyStr.parse`, `IdempotencyKey.create`, `DistinctAccountPair.create`, `LEI.parse`, `UTI.parse`, `ISIN.parse`, `FrozenMap.create`, `canonical_bytes`, `content_hash`) forces the caller to destructure. For boundary code where a default is acceptable, `unwrap_or` eliminates a `match` block.

Required additions:
```python
# On Ok[T]:
def unwrap_or(self, default: T) -> T:
    return self.value

# On Err[E]:
def unwrap_or(self, default: T) -> T:
    return default
```

**GAP-API-04: No `map_err(f)` for error context chaining.** [HIGH] When `Money.create` returns `Err("Money currency: NonEmptyStr requires non-empty string")`, calling code often wants to add context: "while parsing trade TX-12345". Without `map_err`, every call site needs a `match` block just to decorate the error.

Required additions:
```python
# On Ok[T]:
def map_err(self, f: Callable[[E], F]) -> Ok[T]:
    return self

# On Err[E]:
def map_err(self, f: Callable[[E], F]) -> Err[F]:
    return Err(f(self.error))
```

**GAP-API-05: No `sequence` for batch collection.** [MEDIUM] The system processes batches of trades, market data points, and attestations. Without `sequence`, collecting Results from a batch requires a manual loop.

```python
def sequence(results: Iterable[Result[T, E]]) -> Result[list[T], E]:
    """Collect a list of Results into a Result of list.
    Short-circuits on first Err."""
    values: list[T] = []
    for r in results:
        match r:
            case Ok(v): values.append(v)
            case Err(_): return r
    return Ok(values)
```

This is a module-level function in `result.py`, re-exported from `core/__init__.py`.

The `map_result` free function (Step 2) becomes redundant once `.map()` is a method. Keep for backward compatibility or remove -- the method form is strictly better.

**Summary of Result gaps:**

| Gap | What | Priority | Impact |
|-----|------|----------|--------|
| API-01 | `.map(f)` method on Ok/Err | VETO | Fluent chaining impossible; Pass 2 assumes it exists |
| API-02 | `.bind(f)` / `.and_then(f)` method | VETO | Monadic chaining impossible; Pass 2 assumes it exists |
| API-03 | `.unwrap_or(default)` | HIGH | Forces match blocks at every boundary |
| API-04 | `.map_err(f)` | HIGH | Error context chaining requires manual match blocks |
| API-05 | `sequence(list[Result])` | MEDIUM | Batch processing requires manual loops |

---

### 3.2 Progressive Disclosure Assessment

**Test 1: Can a newcomer create a `Money` value in one line?**

Per Step 4, the API is:
```python
Money.create(Decimal("100"), "USD")  # -> Result[Money, str]
```

This returns a `Result`, not a `Money`. Three lines of ceremony for the simplest use case. Assessment: **correctly strict for production but hostile to newcomers**. Acceptable trade-off for a financial system -- beginners should encounter `Decimal` discipline immediately -- but the missing `.unwrap_or()` (GAP-API-03) makes it worse than necessary.

With `.unwrap_or()`:
```python
m = Money.create(Decimal("100"), "USD").unwrap_or(ZERO_USD)
```

One line. Progressive disclosure achieved.

**Test 2: Can they create an `Attestation` without understanding `BitemporalEnvelope`?**

Yes. The factory `create_attestation(value, confidence, source, timestamp, provenance=())` does not require a `BitemporalEnvelope`. The envelope is only used for storage. Correct separation.

However, per GAP-04, `create_attestation` should return `Result[Attestation[T], str]`. This is defensible -- needed because `content_hash` can fail on unsupported types. But the common case (wrapping a `Decimal`) will never fail. Consider adding a type-level guarantee that `content_hash` succeeds for all types in the type universe.

**Test 3: Can they use `FrozenMap.create({"a": 1})` without understanding sorted tuples?**

Yes. Dict-like interface (`get`, `__contains__`, `__getitem__`, `items`, `to_dict`) hides the sorted-tuple internals. Good progressive disclosure.

However, per GAP-08, `FrozenMap.create` should return `Result`. For the `str`-keyed case (100% of Phase 0 usage), the `Result` wrapping is pure ceremony. Consider keeping `FrozenMap.create` returning `FrozenMap` directly for `str` keys (always comparable), and adding `FrozenMap.try_create` for generic keys. Don't penalize the common case for an edge case Phase 0 never encounters.

**Test 4: Is the import path clean?**

```python
from attestor.core import Money, Ok, Err
```

Yes. Step 8 re-exports all 26 public names. One level deep. Clean.

However, `Attestation` and the `Confidence` types live in `attestor.oracle.attestation`. Users constructing attestations need:
```python
from attestor.core import Money, Ok, Err, FrozenMap, content_hash
from attestor.oracle.attestation import Attestation, FirmConfidence, create_attestation
```

Two import lines from two packages. Architecturally correct (`oracle/` is a separate pillar), but consider a convenience re-export in `attestor/__init__.py` for the 5 most common cross-pillar types.

**Progressive disclosure verdict:** Reasonably simple for a financial domain library where type safety is non-negotiable. Main friction: (a) `Result` wrapping on `FrozenMap.create` post-GAP-08 and (b) missing `.unwrap_or()`. Both fixable without architectural changes.

---

### 3.3 Phase 1 Extension Points

**Pillar I -- Gateway:** Phase 0 provides `Result`, `ValidationError`, `LEI`/`UTI`/`ISIN`, `Money`, `NonEmptyStr`, `BitemporalEnvelope`. `CanonicalOrder` and `NormalizedMessage` are Phase 1 deliverables that compose Phase 0 types. **Clean extension. No Phase 0 modification required.**

**Pillar II -- Ledger Engine:** Phase 0 provides `Move`, `Transaction`, `StateDelta`, `DistinctAccountPair`, `PositiveDecimal`, `LedgerEntry`, `BitemporalEnvelope[Transaction]`, `InMemoryTransactionLog`. `LedgerState`, `PositionIndex`, `LedgerView`, `SmartContract`, `LifecycleEngine`, `clone_at()` are all Phase 1.

However, `Account`, `AccountType`, and `Position` are imported in the Pass 2 conftest but NOT specified in Step 10. **Three types are assumed but unspecified.** Either add them to Phase 0 Step 10 or explicitly defer and update the conftest.

**Pillar III -- Oracle:** Phase 0 provides `Attestation[T]`, confidence types, `FrozenMap`, `content_hash`, `InMemoryAttestationStore`. `MarketDataSnapshot`, `YieldCurve`, `VolSurface`, `CreditCurve`, `ModelConfig` are Phase 1+ types. Clean extension, **contingent on resolving GAP-07** (DerivedConfidence interval/level). If GAP-07 is deferred, every Phase 1 Oracle consumer pays a tax for optional fields.

**Pillar IV -- Reporting:** Entirely Phase 1+. Phase 0 provides sufficient base types. **Clean extension.**

**Pillar V -- Pricing & Risk Engine:** The Phase 0 protocol is insufficient for a real pricing engine:

| Aspect | Phase 0 (Step 12) | PLAN (Section 3.4.3) |
|--------|-------------------|----------------------|
| `price()` input | `instrument_id: str, market_snapshot_id: str, model_config_id: str` | `instrument: Instrument, market: Attestation[MarketDataSnapshot], model_config: Attestation[ModelConfig]` |
| `price()` output | `Result[ValuationResult, PricingError]` | `Result[Attestation[ValuationResult], PricingError]` |
| `var()` | Not present | Full signature |
| `pnl_attribution()` | Not present | Full signature |

The Phase 0 protocol uses string IDs where the PLAN uses rich typed inputs, and returns bare values where the PLAN returns `Attestation`-wrapped outputs. When Phase 1 implements real pricing, it will need to either modify the Phase 0 protocol (violates stability) or create a confusing `PricingEngineV2`.

**The root cause:** Step 12 was designed stub-first (the `StubPricingEngine` with hardcoded values), not contract-first. The protocol is infrastructure, not application code. Design it for the real use case. The `Instrument`, `Position`, `MarketDataSnapshot`, and `ModelConfig` types can be stubs or forward references in Phase 0; the protocol signature must be correct.

**Required fix:** Replace the Phase 0 `PricingEngine` protocol with the PLAN Section 3.4.3 signature. The stub implementation can remain trivial.

---

### 3.4 Error Diagnostics

**Error message quality:** Solid. The `AttestorError` base with `message`, `code`, `timestamp`, `source` fields is well-structured. The 7 specialized subclasses add domain-specific context:
- `ValidationError.fields: tuple[FieldViolation, ...]` -- exactly which fields failed
- `IllegalTransitionError.from_state / .to_state` -- the attempted state machine transition
- `ConservationViolationError.expected / .actual` -- the conservation law breach
- `MissingObservableError.observable / .as_of` -- what was missing and when
- `PricingError.instrument / .reason` -- what instrument and why

Error messages as UI, done correctly.

**Error context chaining:** No `map_err` on `Result` (GAP-API-04). Without it, adding context like "while processing trade TX-12345" requires manual pattern matching. **Preferred fix:** Add `map_err` (GAP-API-04) plus a `.with_context(context: str) -> AttestorError` method:

```python
@dataclass(frozen=True, slots=True)
class AttestorError:
    # ... existing fields ...

    def with_context(self, context: str) -> AttestorError:
        """Return a copy with context prepended to message."""
        return replace(self, message=f"{context}: {self.message}")
```

Then chaining becomes:
```python
validate_trade(raw).map_err(lambda e: e.with_context(f"trade {trade_id}"))
```

The `dataclasses.replace` function works on frozen dataclasses and preserves subclass fields.

**Error serialization:** Each subclass has `to_dict() -> dict[str, object]`. Add a test for each subclass that asserts the exact keys in `to_dict()` output (serialization contract stability, same principle as GAP-11).

**Error hierarchy sufficiency for Phase 0:** Yes. Missing for Phase 1: `AuthorizationError`, `ConcurrencyError`, `ReportingError`. The base `AttestorError` is not `@final`, so these can be added as new subclasses without modifying existing code. **Correctly extensible.**

---

### 3.5 Module Boundary Assessment

**Re-export completeness (`core/__init__.py`, Step 8):** All 26 names defined in Steps 2-7 are exported. If `UtcDatetime` (GAP-03) or `sequence` (GAP-API-05) are added, they must be added to re-exports.

**Cyclic dependency risk:** The dependency graph is a strict DAG:

```
result.py
  |
  v
types.py, money.py, errors.py, identifiers.py
  |
  v
serialization.py
  |
  v
core/__init__.py
  |
  v
oracle/attestation.py
ledger/transactions.py
pricing/types.py, pricing/protocols.py
infra/protocols.py, infra/memory_adapter.py
```

**No cycles.** The `core/` package has zero external dependencies (stdlib only). Correct.

**`infra/protocols.py` boundary concern:** This module imports from `oracle/` and `ledger/`, which technically violates PLAN rule D-07 ("`infra/` imports only `core/` and `infra/protocols`"). This is inherent to its role as the domain-infrastructure interface -- protocol definitions necessarily reference domain types from multiple pillars.

**Recommended clarification of D-07:** "`infra/` implementation modules import only `core/` and `infra/protocols`. `infra/protocols.py` itself may import domain types from any pillar for protocol signatures." This distinguishes the protocol definition (must reference domain types) from the implementation (must not know domain specifics).

**Module boundary verdict:** Acyclic, well-structured, zero external dependencies in core. One rule clarification needed for D-07.

---

---

## 4. Required Changes to PHASE0_EXECUTION.md

This section consolidates all required changes from all three reviewers into a single actionable list. Changes are organized by PHASE0_EXECUTION.md step number. Items already identified in PASS2_REVIEW are cross-referenced; genuinely new items are assigned IDs starting at GAP-21.

---

### 4.1 Changes to Step 2 (Result Type)

| ID | Change | Severity | Source |
|----|--------|----------|--------|
| **GAP-21** | Add `.map(f)` method to `Ok[T]` and `Err[E]` | **VETO** | Lattner API-01 |
| **GAP-22** | Add `.bind(f)` / `.and_then(f)` method to `Ok[T]` and `Err[E]` | **VETO** | Lattner API-02 |
| **GAP-23** | Add `.unwrap_or(default)` method to `Ok[T]` and `Err[E]` | HIGH | Lattner API-03 |
| **GAP-24** | Add `.map_err(f)` method to `Ok[T]` and `Err[E]` | HIGH | Lattner API-04 |
| **GAP-25** | Add `sequence(results: Iterable[Result]) -> Result[list, E]` free function | MEDIUM | Lattner API-05 |
| *GAP-15* | *(existing)* `map_result()` -- redundant once `.map()` exists. Remove or keep as alias. | LOW | PASS2 |

---

### 4.2 Changes to Step 4 (Money Type)

| ID | Change | Severity | Source |
|----|--------|----------|--------|
| *GAP-02* | *(existing)* Money arithmetic must use `ATTESTOR_DECIMAL_CONTEXT` | **VETO** | PASS2 V-02, Gatheral 1.1.5 |
| **GAP-26** | `Money.create()` must reject NaN and Infinity via `amount.is_finite()` | HIGH | Gatheral 1.1.1 |
| **GAP-27** | Add `Money.div(divisor: NonZeroDecimal) -> Money` method | HIGH | Gatheral 1.1.2 |
| **GAP-28** | Add `Money.round_to_minor_unit() -> Money` with ISO 4217 lookup | HIGH | Gatheral 1.1.3 |

---

### 4.3 Changes to Step 5 (Error Types)

| ID | Change | Severity | Source |
|----|--------|----------|--------|
| **GAP-29** | Add `AttestorError.with_context(context: str) -> AttestorError` method using `dataclasses.replace` | MEDIUM | Lattner 3.4 |
| **GAP-30** | Add test for each error subclass asserting exact `to_dict()` keys (serialization contract) | LOW | Lattner 3.4 |

---

### 4.4 Changes to Step 9 (Attestation + Confidence Types)

| ID | Change | Severity | Source |
|----|--------|----------|--------|
| *GAP-06* | *(existing)* `QuotedConfidence`: add `bid <= ask` validation in factory, add `mid`/`spread`/`half_spread` properties | **CRITICAL** | PASS2, Gatheral 1.2.1-2 |
| *GAP-07* | *(existing)* `DerivedConfidence`: enforce interval-level consistency (both or neither) | HIGH | PASS2, Gatheral 1.2.3 |
| **GAP-31** | `DerivedConfidence`: enforce `fit_quality` non-empty (`!= FrozenMap.EMPTY`) | HIGH | Gatheral 1.2.4 |
| **GAP-32** | `QuotedConfidence.conditions`: validate against controlled vocabulary (`"Indicative"` / `"Firm"` / `"RFQ"`) or use Enum | MEDIUM | Gatheral 1.2.6 |
| *GAP-20* | *(existing)* `FirmConfidence`: use `NonEmptyStr` for `source` and `attestation_ref` | MEDIUM | PASS2, Gatheral 1.2.5 |

---

### 4.5 Changes to Step 10 (Ledger Types)

| ID | Change | Severity | Source |
|----|--------|----------|--------|
| **GAP-33** | Specify `Account`, `AccountType`, and `Position` types (or explicitly defer to Phase 1 and update Pass 2 conftest) | MEDIUM | Lattner 3.3 |

---

### 4.6 Changes to Step 11 (Pricing/Risk Types)

| ID | Change | Severity | Source |
|----|--------|----------|--------|
| **GAP-34** | Add `es_amount: Decimal` (Expected Shortfall / CVaR) to `VaRResult` | HIGH | Gatheral 1.3.3 |
| **GAP-35** | Add `additional: FrozenMap[str, Decimal]` to `Greeks` for extensible sensitivities | MEDIUM | Gatheral 1.3.4 |
| **GAP-36** | Add `valuation_date: datetime` to `ValuationResult` | MEDIUM | Gatheral 1.3.6 |
| **GAP-37** | `PnLAttribution`: compute `total_pnl` from components in factory (enforce decomposition invariant by construction) | MEDIUM | Gatheral 1.3.5 |

---

### 4.7 Changes to Step 12 (Protocols)

| ID | Change | Severity | Source |
|----|--------|----------|--------|
| **GAP-38** | Document that `PricingEngine` / `RiskEngine` protocol signatures are provisional; PLAN 3.4.3 is the target. Add comment block citing PLAN 3.4.3. | HIGH | Gatheral 1.3.1, Lattner 3.3 |
| **GAP-39** | Add `var()` and `pnl_attribution()` method signatures to `PricingEngine` protocol (stub returns placeholder) | HIGH | Gatheral 1.3.2 |

---

### 4.8 Changes to Steps 13-17 (Infrastructure)

| ID | Change | Severity | Source |
|----|--------|----------|--------|
| *GAP-01* | *(existing)* Use `attestation_id` as store key and Postgres PK | **VETO** | PASS2, FinOps 2.6 |
| *GAP-13* | *(existing)* `AttestationStore.exists()` returns `Result[bool, PersistenceError]` | HIGH | PASS2, FinOps 2.3.1 |
| *GAP-18, GAP-19* | *(existing)* Postgres DDL: `attestation_id` PK, `content_hash` indexed | LOW | PASS2, FinOps 2.2.1 |
| **GAP-40** | Adopt full infrastructure artefacts from Section 2: Kafka topic configs (2.1), Postgres DDL (2.2), persistence protocols (2.3), connection configs (2.4), health checks (2.4.3), error handling (2.4.4), topic config module (2.5) | HIGH | FinOps 2.0-2.8 |
| **GAP-41** | Clarify PLAN rule D-07: `infra/protocols.py` may import domain types from any pillar for protocol signatures; `infra/` implementation modules import only `core/` and `infra/protocols` | LOW | Lattner 3.5 |

---

### 4.9 Summary

| Priority | Count | Gap IDs |
|----------|-------|---------|
| **VETO (must fix before any code)** | 6 | GAP-01, GAP-02, GAP-03, GAP-04, GAP-21, GAP-22 |
| **HIGH** | 15 | GAP-05, GAP-06, GAP-07, GAP-09, GAP-12, GAP-13, GAP-20, GAP-23, GAP-24, GAP-26, GAP-27, GAP-28, GAP-34, GAP-38, GAP-39, GAP-40 |
| **MEDIUM** | 10 | GAP-08, GAP-10, GAP-11, GAP-25, GAP-29, GAP-32, GAP-33, GAP-35, GAP-36, GAP-37 |
| **LOW** | 10 | GAP-14, GAP-15, GAP-16, GAP-17, GAP-18, GAP-19, GAP-30, GAP-41 |
| **Total** | **41** | |

*(Pass 2 identified 20 gaps. Pass 3 adds 21 new gaps: GAP-21 through GAP-41.)*

---

### 4.10 Actionability Verdict

> **Can a developer read PHASE0_EXECUTION.md + PASS2_REVIEW.md + PASS3_REVIEW.md and implement every module without asking a question?**

**Almost.** The 6 VETO items (GAP-01 through GAP-04, GAP-21, GAP-22) must be resolved first -- they change core signatures that cascade through every downstream module. The 2 new VETOs from Pass 3 (`.map()` and `.bind()` on `Result`) are particularly impactful because Pass 2's test catalogue assumes these methods exist.

**Once all 41 gaps are resolved in PHASE0_EXECUTION.md:**

1. A developer can implement all 14 Python modules in the order specified by Steps 1-18
2. A DevOps engineer can provision Kafka + Postgres using Section 2 without additional clarification
3. A quant can confirm the financial types are fit for purpose per Section 1
4. The CI pipeline from Step 18 will have complete invariant coverage

**Recommended resolution order:**

1. Step 2: Add `.map()`, `.bind()`, `.unwrap_or()`, `.map_err()`, `sequence()` to Result (GAP-21 through GAP-25)
2. Step 4: Fix Money (GAP-02, GAP-26, GAP-27, GAP-28)
3. Step 5: Add `.with_context()` to AttestorError (GAP-29)
4. Step 9: Fix confidence types (GAP-06, GAP-07, GAP-20, GAP-31, GAP-32)
5. Step 9: Fix attestation identity (GAP-01, GAP-03, GAP-04)
6. Steps 10-12: Ledger + pricing type additions (GAP-33 through GAP-39)
7. Steps 13-17: Adopt infrastructure specification (GAP-40, GAP-41)
8. Remaining MEDIUM/LOW items

---

*End of Pass 3 Review.*
