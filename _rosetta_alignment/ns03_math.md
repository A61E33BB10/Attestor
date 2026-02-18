# Namespace 03: cdm.base.math -- Rosetta Alignment Analysis

Generated: 2026-02-17
CDM source files:
- `rosetta-source/src/main/rosetta/base-math-type.rosetta`
- `rosetta-source/src/main/rosetta/base-math-enum.rosetta`

Focus: Types needed for equity trades -- Quantity, NonNegativeQuantitySchedule,
UnitType, FinancialUnitEnum, QuantitySchedule, Rounding, RoundingDirectionEnum,
RoundingModeEnum.

---

## Rosetta Definitions

### Types (base-math-type.rosetta)

#### UnitType
Discriminated unit for price, quantity, or other purposes.

| Field | Type | Cardinality | Description |
|-------|------|-------------|-------------|
| capacityUnit | CapacityUnitEnum | 0..1 | Commodity capacity unit |
| weatherUnit | WeatherUnitEnum | 0..1 | Weather derivative unit |
| financialUnit | FinancialUnitEnum | 0..1 | Financial securities unit (Share, Contract, etc.) |
| currency | string | 0..1 | Currency code [metadata scheme] |

**Condition `UnitType`**: `one-of` -- exactly one of the four fields must be set.

---

#### MeasureBase (abstract)
Abstract base: a number associated to a unit.

| Field | Type | Cardinality | Description |
|-------|------|-------------|-------------|
| value | number | 0..1 | Numeric value (optional -- may be omitted in schedule context) |
| unit | UnitType | 0..1 | Unit qualifier (optional -- may be unit-less for ratios) |

No conditions.

---

#### Measure (extends MeasureBase)
Concrete measure requiring value to be present.

| Field | Type | Cardinality | Description |
|-------|------|-------------|-------------|
| *(inherited)* value | number | 0..1 | Numeric value |
| *(inherited)* unit | UnitType | 0..1 | Unit qualifier |

**Condition `ValueExists`**: `value exists`

---

#### MeasureSchedule (extends MeasureBase)
Set of measures in the same unit with a schedule of steps.

| Field | Type | Cardinality | Description |
|-------|------|-------------|-------------|
| *(inherited)* value | number | 0..1 | Initial/single value |
| *(inherited)* unit | UnitType | 0..1 | Unit qualifier |
| datedValue | DatedValue | 0..* | Step date/value pairs |

**Condition `ValueExists`**: `value exists or datedValue exists` -- at least one of single value or step schedule must be present.

---

#### QuantitySchedule (extends MeasureSchedule)
Quantity with optional multiplier and frequency, used for financial product trade amounts.

| Field | Type | Cardinality | Description |
|-------|------|-------------|-------------|
| *(inherited)* value | number | 0..1 | Base quantity value |
| *(inherited)* unit | UnitType | 0..1 | Quantity unit |
| *(inherited)* datedValue | DatedValue | 0..* | Step schedule |
| multiplier | Measure | 0..1 | Multiplier with unit (e.g. 1,000 MT per contract) |
| frequency | Frequency | 0..1 | Frequency for per-period quantities (e.g. barrels/day) |

**Condition `Quantity_multiplier`**: `if multiplier exists then multiplier -> value >= 0.0`
**Condition `UnitOfAmountExists`**: `unit exists` -- unit is mandatory at this level.

---

#### Quantity (extends QuantitySchedule)
Single-value quantity (no step schedule).

| Field | Type | Cardinality | Description |
|-------|------|-------------|-------------|
| *(all inherited from QuantitySchedule)* | | | |

**Condition `AmountOnlyExists`**: `value exists and datedValue is absent` -- must be a single value, not a schedule.

---

#### NonNegativeQuantity (extends Quantity)
Quantity constrained to be non-negative.

| Field | Type | Cardinality | Description |
|-------|------|-------------|-------------|
| *(all inherited from Quantity)* | | | |

**Condition `NonNegativeQuantity_amount`**: `value >= 0.0`

---

#### NonNegativeQuantitySchedule (extends QuantitySchedule)
Quantity schedule constrained to non-negative values.

| Field | Type | Cardinality | Description |
|-------|------|-------------|-------------|
| *(all inherited from QuantitySchedule)* | | | |

**Condition `NonNegativeQuantity_value`**: `if value exists then value >= 0.0`
**Condition `NonNegativeQuantity_datedValue`**: `if datedValue exists then datedValue -> value all >= 0.0`

---

#### NonNegativeStep
Step date and non-negative step value pair. `[metadata key]`.

| Field | Type | Cardinality | Description |
|-------|------|-------------|-------------|
| stepDate | date | 1..1 | Date when step value becomes effective |
| stepValue | number | 1..1 | Non-negative rate or amount |

**Condition `StepValue`**: `stepValue >= 0.0`

---

#### Rounding
Rules for rounding a number.

| Field | Type | Cardinality | Description |
|-------|------|-------------|-------------|
| roundingDirection | RoundingDirectionEnum | 1..1 | Up, Down, or Nearest |
| precision | int | 0..1 | Number of decimal places |

No additional conditions.

---

#### Schedule
Step schedule with an initial value and dated step pairs.

| Field | Type | Cardinality | Description |
|-------|------|-------------|-------------|
| value | number | 1..1 | Initial rate or amount |
| datedValue | DatedValue | 0..* | Step date/value pairs (optional -- flat if omitted) |

No explicit conditions beyond field cardinality.

---

#### DatedValue
Date and value pair for schedule steps. `[metadata key]`.

| Field | Type | Cardinality | Description |
|-------|------|-------------|-------------|
| date | date | 1..1 | Effective date |
| value | number | 1..1 | Rate or amount |

No conditions.

---

#### NumberRange
Number range with optional inclusive/exclusive bounds.

| Field | Type | Cardinality | Description |
|-------|------|-------------|-------------|
| lowerBound | NumberBound | 0..1 | Lower bound |
| upperBound | NumberBound | 0..1 | Upper bound |

**Condition `AtLeastOneOf`**: `lowerBound exists or upperBound exists`

---

#### NumberBound
Bound specification: number + inclusive flag.

| Field | Type | Cardinality | Description |
|-------|------|-------------|-------------|
| number | number | 1..1 | Bound value |
| inclusive | boolean | 1..1 | Whether bound is inclusive |

No conditions.

---

#### MoneyRange
Money amount range with bounds.

| Field | Type | Cardinality | Description |
|-------|------|-------------|-------------|
| lowerBound | MoneyBound | 0..1 | Lower money bound |
| upperBound | MoneyBound | 0..1 | Upper money bound |

**Condition `AtLeastOneOf`**: `lowerBound exists or upperBound exists`

---

#### MoneyBound
Money amount bound specification.

| Field | Type | Cardinality | Description |
|-------|------|-------------|-------------|
| money | Money | 1..1 | Money amount for bound |
| inclusive | boolean | 1..1 | Whether bound is inclusive |

No conditions.

---

#### AveragingCalculationMethod
Aggregation method for multiple values.

| Field | Type | Cardinality | Description |
|-------|------|-------------|-------------|
| isWeighted | boolean | 1..1 | Weighted vs unweighted |
| calculationMethod | AveragingCalculationMethodEnum | 1..1 | Pythagorean mean type |

No conditions.

---

### Enums (base-math-enum.rosetta)

#### RoundingDirectionEnum
Rounding rule for precision-based rounding.

| Value | Description |
|-------|-------------|
| Up | Round up (5.21 -> 5.3 at 1dp) |
| Down | Round down (5.29 -> 5.2 at 1dp) |
| Nearest | Round to nearest (5.24 -> 5.2, 5.25 -> 5.3 at 1dp) |

---

#### RoundingModeEnum
Rounding direction for round-to-nearest function.

| Value | Description |
|-------|-------------|
| Down | Round down to nearest (529 -> 520 at nearest 10) |
| Up | Round up to nearest (521 -> 530 at nearest 10) |

---

#### FinancialUnitEnum
Financial quantity units for securities.

| Value | Description |
|-------|-------------|
| Contract | Listed futures/options contracts |
| ContractualProduct | Whole product (e.g. premium as cash amount) |
| IndexUnit | Price in index points (stock index) |
| LogNormalVolatility | Log-normal vol in %/month (decimal) |
| Share | Number of stock shares |
| ValuePerDay | Sensitivity to 1-day passage (theta) |
| ValuePerPercent | Sensitivity to 1% underlying change (vega) |
| Weight | Decimal weight in a basket |

---

#### CapacityUnitEnum
~65 commodity capacity units: ALW, BBL, BCF, BDFT, CBM, CER, CRT, DAG, DAY, DMTU, ENVCRD, ENVOFST, FEU, G, GBBSH, GBBTU, GBCWT, GBGAL, GBMBTU, GBMMBTU, GBT, GBTHM, GJ, GW, GWH, HL, HOGB, ISOBTU, ISOMBTU, ISOMMBTU, ISOTHM, J, KG, KL, KW, KWD, KWH, KWM, KWMIN, KWY, L, LB, MB, MBF, MJ, MMBF, MMBBL, MSF, MT, MW, MWD, MWH, MWM, MWMIN, MWY, OZT, SGB, TEU, USBSH, USBTU, USCWT, USGAL, USMBTU, USMMBTU, UST, USTHM.

---

#### WeatherUnitEnum
Weather derivative units.

| Value | Description |
|-------|-------------|
| CDD | Cooling Degree Days |
| CPD | Critical Precipitation Day |
| HDD | Heating Degree Day |

---

#### AveragingWeightingMethodEnum

| Value | Description |
|-------|-------------|
| Unweighted | Arithmetic mean of relevant rates |
| Weighted | Weighted arithmetic mean by days in effect |

---

#### AveragingCalculationMethodEnum

| Value | Description |
|-------|-------------|
| Arithmetic | Sum / count |
| Geometric | Nth root of product |
| Harmonic | Reciprocal of arithmetic mean of reciprocals |

---

#### QuantifierEnum

| Value | Description |
|-------|-------------|
| All | True for every member |
| Any | True for at least one member |

---

#### CompareOp

| Value |
|-------|
| GreaterThan |
| GreaterThanOrEquals |
| Equals |
| LessThanOrEquals |
| LessThan |

---

#### ArithmeticOperationEnum

| Value | Description |
|-------|-------------|
| Add | Addition |
| Subtract | Subtraction |
| Multiply | Multiplication |
| Divide | Division |
| Max | Maximum |
| Min | Minimum |

---

#### QuantityChangeDirectionEnum

| Value | Description |
|-------|-------------|
| Increase | Quantity goes up |
| Decrease | Quantity goes down |
| Replace | Quantity is replaced entirely |

---

### Inheritance Hierarchy Summary

```
MeasureBase (abstract)
  +-- Measure (requires value)
  +-- MeasureSchedule (adds datedValue steps)
        +-- QuantitySchedule (adds multiplier, frequency; requires unit)
              +-- Quantity (single value only, no steps)
              |     +-- NonNegativeQuantity (value >= 0)
              +-- NonNegativeQuantitySchedule (all values >= 0)
```

Standalone types: Schedule, DatedValue, NonNegativeStep, Rounding, UnitType, NumberRange, NumberBound, MoneyRange, MoneyBound, AveragingCalculationMethod.

---

## Attestor Current State

### Existing Types That Map to Math Namespace

| Attestor Type | Location | CDM Equivalent | Notes |
|--------------|----------|---------------|-------|
| `Money` | `core/money.py` | Partial `Measure` (currency unit only) | amount: Decimal + currency: NonEmptyStr. Arithmetic methods (add/sub/mul/div/negate/abs). ISO 4217 rounding. |
| `NonNegativeDecimal` | `core/money.py` | `NonNegativeQuantity` condition | value: Decimal, enforces >= 0. Smart constructor `parse()`. |
| `PositiveDecimal` | `core/money.py` | No direct CDM equivalent (stricter) | value: Decimal, enforces > 0. CDM has no "strictly positive" constraint. |
| `NonZeroDecimal` | `core/money.py` | No direct CDM equivalent | value: Decimal, enforces != 0. Used for safe division. |
| `NonEmptyStr` | `core/money.py` | No direct CDM equivalent | Refined string type. |
| `DatedValue` | `core/types.py` | `DatedValue` | date: date + value: Decimal. Enforces finite Decimal. |
| `Schedule` | `core/types.py` | `Schedule` (partial) | entries: tuple[DatedValue, ...]. Enforces non-empty + strict date monotonicity. Differs from CDM: no separate initial `value` field; all values are in entries. |
| `Frequency` | `core/types.py` | `Frequency` (partial) | period: Period + roll_convention: RollConventionEnum. |
| `Period` | `core/types.py` | `Period` | multiplier: int + unit: PeriodUnit. Enforces multiplier > 0. |
| `PriceQuantity` | `oracle/observable.py` | `PriceQuantity` (simplified) | price: Price + quantity: PositiveDecimal + observable: Observable. Quantity is a bare PositiveDecimal -- no UnitType. |
| `QuantityChangePI` | `instrument/lifecycle.py` | `QuantityChangePrimitive` (simplified) | instrument_id + quantity_change: Decimal + effective_date. No QuantityChangeDirectionEnum -- uses sign of Decimal. |
| `ATTESTOR_DECIMAL_CONTEXT` | `core/money.py` | N/A | prec=28, ROUND_HALF_EVEN. Global arithmetic context. |
| `Money.round_to_minor_unit()` | `core/money.py` | `Rounding` (hardcoded variant) | Rounds to ISO 4217 minor units with ROUND_HALF_EVEN. Not configurable. |

### What Is NOT Present

- **UnitType**: No discriminated unit type. Currency is a string on Money; no FinancialUnitEnum, CapacityUnitEnum, or WeatherUnitEnum.
- **MeasureBase / Measure / MeasureSchedule**: No generic measure hierarchy. Money covers the currency case; raw Decimal covers everything else.
- **QuantitySchedule**: No quantity schedule with multiplier/frequency.
- **Quantity**: No standalone Quantity type with explicit UnitType. PriceQuantity.quantity is a bare PositiveDecimal.
- **NonNegativeQuantity**: NonNegativeDecimal provides the >= 0 constraint but without unit association.
- **NonNegativeQuantitySchedule**: No quantity schedule at all.
- **NonNegativeStep**: No dedicated non-negative step type (DatedValue allows any finite Decimal).
- **Rounding**: No configurable rounding type. Only hardcoded ROUND_HALF_EVEN via ATTESTOR_DECIMAL_CONTEXT.
- **RoundingDirectionEnum**: No enum. Only ROUND_HALF_EVEN is used globally.
- **RoundingModeEnum**: Not present.
- **FinancialUnitEnum**: Not present. Quantity units are implicit from context.
- **CapacityUnitEnum**: Not present (out of scope -- commodity).
- **WeatherUnitEnum**: Not present (out of scope -- weather derivatives).
- **NumberRange / NumberBound**: Not present.
- **MoneyRange / MoneyBound**: Not present.
- **AveragingCalculationMethod / AveragingCalculationMethodEnum / AveragingWeightingMethodEnum**: Not present.
- **QuantifierEnum / CompareOp / ArithmeticOperationEnum**: Not present (CDM DSL infrastructure, not trade representation).
- **QuantityChangeDirectionEnum**: Not present. QuantityChangePI uses signed Decimal instead.

---

## Gap Analysis

### EQUITY TRADE CRITICAL PATH

For a basic equity trade, the CDM PriceQuantity type requires:
1. A `NonNegativeQuantitySchedule` (0..*) for quantity, which is a `QuantitySchedule` with non-negativity constraints
2. Each quantity has a `UnitType` (with `financialUnit = Share` or `currency`)
3. The `Quantity` type (single-value case of QuantitySchedule) is the most common for equity spot trades

Attestor's current `PriceQuantity.quantity` is a `PositiveDecimal` -- a bare number with no unit. This creates three specific gaps for equity trade alignment:

### Gap M-01: UnitType not modeled (MEDIUM)

**CDM**: UnitType is a one-of choice of capacityUnit | weatherUnit | financialUnit | currency. Every quantity in CDM carries its unit explicitly.

**Attestor**: Currency is stored as a string on Money. Financial units (Share, Contract) are implicit from context (EquityPayoutSpec implies Share; FuturesPayoutSpec implies Contract). No explicit UnitType.

**Impact on equity trades**: When constructing a CDM-compliant equity trade, the quantity must carry `financialUnit = Share` and the price must carry `currency = "USD"` (or similar). Without UnitType, round-trip serialization to CDM JSON will lose unit information.

**Recommendation**: Add a `UnitType` dataclass to `core/money.py` or a new `core/quantity.py`. For Attestor's scope, model it as:
```python
@final
@dataclass(frozen=True, slots=True)
class UnitType:
    capacity_unit: CapacityUnitEnum | None = None
    weather_unit: WeatherUnitEnum | None = None
    financial_unit: FinancialUnitEnum | None = None
    currency: NonEmptyStr | None = None

    def __post_init__(self) -> None:
        # Enforce one-of
        count = sum(1 for f in (self.capacity_unit, self.weather_unit,
                                self.financial_unit, self.currency) if f is not None)
        if count != 1:
            raise TypeError(f"UnitType requires exactly one field set, got {count}")
```

Pragmatic option: Since Attestor is focused on financial instruments, a simplified union type would also work:
```python
type UnitType = FinancialUnit | CurrencyUnit
```

### Gap M-02: FinancialUnitEnum not modeled (MEDIUM)

**CDM**: 8 values -- Contract, ContractualProduct, IndexUnit, LogNormalVolatility, Share, ValuePerDay, ValuePerPercent, Weight.

**Attestor**: Not present. Shares and contracts are implied by payout type context.

**Impact on equity trades**: Equity trade quantities need `FinancialUnitEnum.Share`. Without this, CDM JSON serialization cannot correctly populate the `unit.financialUnit` field.

**Recommendation**: Add `FinancialUnitEnum` to a new `core/quantity.py` or to `core/money.py`. For equity trades, minimum needed values: Share, Contract, IndexUnit, Weight.

### Gap M-03: Quantity type not modeled (MEDIUM)

**CDM**: Quantity = value (number) + unit (UnitType). Extends the full QuantitySchedule chain but for equity spot trades, it is simply a number with a unit.

**Attestor**: `PriceQuantity.quantity` is `PositiveDecimal` -- no unit association.

**Impact on equity trades**: Every equity trade quantity should be `Quantity(value=100, unit=UnitType(financial_unit=FinancialUnitEnum.Share))`. Without Quantity, the unit is lost.

**Recommendation**: Add a `Quantity` dataclass:
```python
@final
@dataclass(frozen=True, slots=True)
class Quantity:
    value: Decimal
    unit: UnitType

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise TypeError(...)
```

Do NOT replicate CDM's 6-level inheritance chain. One flat dataclass with a smart constructor for NonNegativeQuantity is sufficient.

### Gap M-04: NonNegativeQuantitySchedule not modeled (LOW-MEDIUM)

**CDM**: QuantitySchedule with non-negative constraints on all values (both initial and step values). Used in CDM's PriceQuantity as the type for the quantity field.

**Attestor**: No quantity schedule at all. Simple equity trades do not need scheduled quantities.

**Impact on equity trades**: Minimal for spot equity. Becomes relevant for equity forwards or structured products with varying notional.

**Recommendation**: Defer full QuantitySchedule implementation. For Phase A equity alignment, a `NonNegativeQuantity` (flat value + unit) is sufficient. Model schedule support when amortizing/varying-notional instruments are needed.

### Gap M-05: Rounding type not modeled (LOW)

**CDM**: Rounding = roundingDirection (Up/Down/Nearest) + precision (int). Used in price/quantity rounding specifications per instrument.

**Attestor**: `Money.round_to_minor_unit()` uses ROUND_HALF_EVEN with ISO 4217 precision. `ATTESTOR_DECIMAL_CONTEXT` uses ROUND_HALF_EVEN globally. No per-instrument configurable rounding.

**Impact on equity trades**: Equity settlement amounts typically use currency-specific rounding (2 decimal places for USD). The current hardcoded approach works for most cases. Custom rounding is rare for equities but required for some bonds and commodity contracts.

**Recommendation**: Add `Rounding` dataclass and `RoundingDirectionEnum` but keep `ATTESTOR_DECIMAL_CONTEXT` as the default. Rounding should be an optional field on price/quantity specifications, not a global replacement.

### Gap M-06: RoundingDirectionEnum not modeled (LOW)

**CDM**: Up, Down, Nearest.

**Attestor**: Only ROUND_HALF_EVEN is used (a specific variant of "Nearest" with banker's tie-breaking).

**Impact on equity trades**: Low. ROUND_HALF_EVEN is the standard for financial calculations.

**Recommendation**: Add as part of Rounding type (M-05). Map values: Up -> ROUND_CEILING, Down -> ROUND_FLOOR, Nearest -> ROUND_HALF_EVEN.

### Gap M-07: RoundingModeEnum not modeled (LOW)

**CDM**: Down, Up -- used specifically by the `RoundToNearest` function for rounding to a nearest number (e.g. nearest 10, nearest 0.25).

**Attestor**: Not present.

**Impact on equity trades**: Negligible. Equity quantities are whole shares; equity prices use decimal precision.

**Recommendation**: Add only if implementing CDM's `RoundToNearest` function. Not needed for equity trade representation.

### Gap M-08: MeasureBase / Measure / MeasureSchedule hierarchy not modeled (LOW)

**CDM**: 6-level inheritance chain: MeasureBase -> Measure -> MeasureSchedule -> QuantitySchedule -> Quantity -> NonNegativeQuantity.

**Attestor**: Money covers the currency case. Decimal covers non-monetary values. No generic measure abstraction.

**Impact on equity trades**: None. The hierarchy is a Rosetta DSL artifact for code generation. Python dataclasses with flat structure and smart constructors are more idiomatic.

**Recommendation**: Do NOT replicate this hierarchy. Use flat Quantity + NonNegativeQuantity + QuantitySchedule types. The Rosetta inheritance chain exists because the DSL requires explicit extension chains; Python does not.

### Gap M-09: QuantityChangeDirectionEnum not modeled (LOW)

**CDM**: Increase, Decrease, Replace.

**Attestor**: `QuantityChangePI.quantity_change` uses signed Decimal (negative = decrease, positive = increase). Replace is not modeled.

**Impact on equity trades**: Partial close (decrease) is the most common lifecycle event. Replace is rare (used in restructuring).

**Recommendation**: Add the enum if Replace semantics are needed. Otherwise, the signed-Decimal approach is cleaner and less error-prone (cannot accidentally specify Decrease with a positive number).

### Gap M-10: NumberRange / NumberBound not modeled (LOW)

**CDM**: Range with inclusive/exclusive bounds. Used in collateral eligibility and digital payoff conditions.

**Attestor**: Not present.

**Impact on equity trades**: None for standard equity.

**Recommendation**: Defer. Add when modeling digital options or collateral eligibility.

### Gap M-11: MoneyRange / MoneyBound not modeled (LOW)

**CDM**: Money-typed range with bounds.

**Attestor**: Not present.

**Impact on equity trades**: None.

**Recommendation**: Defer.

### Gap M-12: Schedule / DatedValue structural mismatch (LOW)

**CDM Schedule**: `value` (1..1) + `datedValue` (0..*) -- has a mandatory initial value plus optional steps.

**Attestor Schedule**: `entries: tuple[DatedValue, ...]` -- all values (including initial) are in entries. No separate initial value field.

**CDM DatedValue**: `date` (1..1) + `value` (1..1) -- matches Attestor.

**Impact**: The structural difference means CDM JSON round-trip requires transformation. CDM's Schedule has an explicit initial value that is not paired with a date, while Attestor requires every value to have a date.

**Recommendation**: This is a deliberate design choice in Attestor (every value has a date for strict ordering). Document the serialization mapping: CDM `Schedule.value` maps to `entries[0].value` with `entries[0].date` being the effective date. Low priority since the difference is handled in serialization.

### Gap M-13: CapacityUnitEnum / WeatherUnitEnum not modeled (OUT OF SCOPE)

**CDM**: ~65 commodity capacity units, 3 weather units.

**Attestor**: Not present.

**Impact on equity trades**: None.

**Recommendation**: Out of scope. Add only if commodity/weather derivative support is needed.

### Gap M-14: AveragingCalculationMethod / enum types not modeled (OUT OF SCOPE)

**CDM**: Averaging method (weighted/unweighted, arithmetic/geometric/harmonic).

**Attestor**: Not present.

**Impact on equity trades**: None for standard equity. Relevant for Asian equity options.

**Recommendation**: Defer until Asian option support is needed.

### Gap M-15: QuantifierEnum / CompareOp / ArithmeticOperationEnum not modeled (OUT OF SCOPE)

**CDM**: DSL infrastructure enums for functional expressions and validation.

**Attestor**: Python's native operators and `all()`/`any()` builtins serve the same purpose.

**Impact on equity trades**: None. These are Rosetta DSL constructs, not trade representation types.

**Recommendation**: Do not implement. These are CDM DSL internals with no mapping to Python application code.

---

## Recommended Changes

### Priority 1 -- Equity Trade Alignment (implement now)

**Create `attestor/core/quantity.py`** with:

1. **`FinancialUnitEnum`** (Enum): Share, Contract, ContractualProduct, IndexUnit, LogNormalVolatility, ValuePerDay, ValuePerPercent, Weight. All 8 CDM values.

2. **`UnitType`** (frozen dataclass): One-of discriminated union with `financial_unit: FinancialUnitEnum | None`, `currency: NonEmptyStr | None`. Omit `capacity_unit` and `weather_unit` for now (out of scope). Enforce exactly-one-set condition in `__post_init__`. Add factory methods:
   - `UnitType.of_currency(code: str) -> UnitType`
   - `UnitType.of_financial(unit: FinancialUnitEnum) -> UnitType`

3. **`Quantity`** (frozen dataclass): `value: Decimal`, `unit: UnitType`. Enforce finite Decimal. Condition: `value exists` (always required -- this is CDM's Measure level constraint). Factory:
   - `Quantity.of_shares(n: Decimal) -> Quantity`
   - `Quantity.of_currency(amount: Decimal, ccy: str) -> Quantity`

4. **`NonNegativeQuantity`** (frozen dataclass): Same fields as Quantity, with `value >= 0` enforced. Smart constructor `NonNegativeQuantity.create(value, unit) -> Ok[...] | Err[str]`.

5. **Update `PriceQuantity`** in `oracle/observable.py`: Change `quantity: PositiveDecimal` to `quantity: NonNegativeQuantity`. This is the single most impactful change for CDM alignment.

### Priority 2 -- Rounding Support (implement when needed)

6. **`RoundingDirectionEnum`** (Enum): Up, Down, Nearest.

7. **`Rounding`** (frozen dataclass): `direction: RoundingDirectionEnum`, `precision: int | None`. Add a `round_value(self, value: Decimal) -> Decimal` method that dispatches to the appropriate Python `decimal` rounding mode.

### Priority 3 -- Schedule Quantities (defer)

8. **`QuantitySchedule`** -- Only when amortizing/step-notional equity-linked products are needed.
9. **`NonNegativeQuantitySchedule`** -- Same trigger as above.
10. **`QuantityChangeDirectionEnum`** -- Only if Replace semantics are needed for lifecycle events.
11. **`CapacityUnitEnum` / `WeatherUnitEnum`** -- Only if commodity support is added.

### Do NOT Implement

- **MeasureBase / Measure / MeasureSchedule** hierarchy: Rosetta DSL artifact. Python flat dataclasses with smart constructors are superior.
- **QuantifierEnum / CompareOp / ArithmeticOperationEnum**: CDM DSL infrastructure with no Python analog needed.
- **NumberRange / NumberBound / MoneyRange / MoneyBound**: Not needed for equity trades.

### Migration Path

The key breaking change is `PriceQuantity.quantity: PositiveDecimal` -> `NonNegativeQuantity`. Migration steps:

1. Add `quantity.py` with UnitType, FinancialUnitEnum, Quantity, NonNegativeQuantity.
2. Update `PriceQuantity` to use `NonNegativeQuantity`.
3. Update all call sites that construct PriceQuantity (tests, equity payout, observable).
4. NonNegativeQuantity allows zero (>= 0) which is correct for CDM but different from current PositiveDecimal (> 0). Verify that no business logic relies on quantity being strictly positive.
