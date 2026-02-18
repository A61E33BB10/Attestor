# Namespace 02: cdm.base.staticdata.party -- Gap Analysis

**Source files**:
- `base-staticdata-party-type.rosetta`
- `base-staticdata-party-enum.rosetta`

**Attestor files examined**:
- `attestor/instrument/types.py` (Party class)
- `attestor/core/types.py` (CounterpartyRole, PayerReceiver)
- `attestor/gateway/types.py` (CanonicalOrder with party LEI refs)
- `attestor/instrument/lifecycle.py` (Trade, TradeState, PartyChangePI)
- `attestor/core/identifiers.py` (LEI, UTI, ISIN)
- `attestor/ledger/transactions.py` (Account, AccountType)

---

## 1. Rosetta Definitions

### 1.1 Types

#### Party
```
type Party:
    [metadata key]
    partyId         PartyIdentifier       (1..*)
    name            string                (0..1)  [metadata scheme]
    businessUnit    BusinessUnit          (0..*)
    person          NaturalPerson         (0..*)
    personRole      NaturalPersonRole     (0..*)
    account         Account               (0..1)
    contactInformation ContactInformation (0..1)
```
- **Metadata**: key (cross-referenceable)
- **No conditions**
- **No inheritance**

#### PartyIdentifier
```
type PartyIdentifier:
    [metadata key]
    identifier      string                    (1..1)  [metadata scheme]
    identifierType  PartyIdentifierTypeEnum   (0..1)
```

#### EntityIdentifier
```
type EntityIdentifier:
    [metadata key]
    identifier      string                        (1..1)  [metadata scheme]
    identifierType  EntityIdentifierTypeEnum       (0..1)
```

#### PersonIdentifier
```
type PersonIdentifier:
    [metadata key]
    identifier      string                        (1..1)  [metadata scheme]
    identifierType  PersonIdentifierTypeEnum       (0..1)
    country         string                         (0..1)  [metadata scheme]
```

#### Counterparty
```
type Counterparty:
    role            CounterpartyRoleEnum  (1..1)
    partyReference  Party                 (1..1)  [metadata reference]
```
- Maps abstract Party1/Party2 roles to actual Party references.

#### AncillaryParty
```
type AncillaryParty:
    role            AncillaryRoleEnum         (1..1)
    partyReference  Party                     (1..*)  [metadata reference]
    onBehalfOf      CounterpartyRoleEnum      (0..1)
```
- For non-principal parties (e.g. calculation agent, clearing org).

#### BuyerSeller
```
type BuyerSeller:
    buyer           CounterpartyRoleEnum  (1..1)
    seller          CounterpartyRoleEnum  (1..1)
```
- FpML BuyerSeller.model construct for option/equity direction.

#### PayerReceiver
```
type PayerReceiver:
    payer           CounterpartyRoleEnum  (1..1)
    receiver        CounterpartyRoleEnum  (1..1)
```
- For interest rate stream direction. Has `[docReference]` annotations for GMRA/ERCC.

#### PartyReferencePayerReceiver
```
type PartyReferencePayerReceiver:
    payerPartyReference     Party    (1..1)  [metadata reference]
    payerAccountReference   Account  (0..1)  [metadata reference]
    receiverPartyReference  Party    (1..1)  [metadata reference]
    receiverAccountReference Account (0..1)  [metadata reference]
```
- Direct party references (not via CounterpartyRoleEnum) with optional accounts.

#### PartyRole
```
type PartyRole:
    partyReference          Party          (1..1)  [metadata reference]
    role                    PartyRoleEnum  (1..1)
    ownershipPartyReference Party          (0..1)  [metadata reference]
```
- Associates a party with a role in a transaction.

#### RelatedParty
```
type RelatedParty:
    partyReference   Party          (1..1)  [metadata reference]
    accountReference Account        (0..1)  [metadata reference]
    role             PartyRoleEnum  (1..1)
```

#### NaturalPerson
```
type NaturalPerson:
    [metadata key]
    personId           PersonIdentifier     (0..*)  [metadata scheme]
    honorific          string               (0..1)
    firstName          string               (0..1)
    middleName         string               (0..*)
    initial            string               (0..*)
    surname            string               (0..1)
    suffix             string               (0..1)
    dateOfBirth        date                 (0..1)
    contactInformation ContactInformation   (0..1)

    condition NameOrIdChoice:
        (firstName exists and surname exists) or personId exists

    condition NaturalPersonChoice:
        optional choice middleName, initial
```
- Two conditions: must have (first+last name) OR personId; middleName and initial are mutually exclusive.

#### NaturalPersonRole
```
type NaturalPersonRole:
    personReference  NaturalPerson           (1..1)  [metadata reference]
    role             NaturalPersonRoleEnum   (0..*)  [metadata scheme]
```

#### Account
```
type Account:
    [metadata key]
    partyReference    Party            (0..1)  [metadata reference]
    accountNumber     string           (1..1)  [metadata scheme]
    accountName       string           (0..1)  [metadata scheme]
    accountType       AccountTypeEnum  (0..1)  [metadata scheme]
    accountBeneficiary Party           (0..1)  [metadata reference]
    servicingParty    Party            (0..1)  [metadata reference]
```

#### LegalEntity
```
type LegalEntity:
    [metadata key]
    name              string             (1..1)  [metadata scheme]
    entityIdentifier  EntityIdentifier   (0..*)
```

#### Address
```
type Address:
    street      string  (1..*)
    city        string  (0..1)
    state       string  (0..1)
    country     string  (0..1)  [metadata scheme]
    postalCode  string  (0..1)
```

#### ContactInformation
```
type ContactInformation:
    telephone  TelephoneNumber  (0..*)
    address    Address          (0..*)
    email      string           (0..*)
    webPage    string           (0..*)
```

#### TelephoneNumber
```
type TelephoneNumber:
    telephoneNumberType  TelephoneTypeEnum  (0..1)
    number               string             (1..1)
```

#### BusinessUnit
```
type BusinessUnit:
    [metadata key]
    name                string             (1..1)
    identifier          Identifier         (0..1)
    contactInformation  ContactInformation (0..1)
```

#### ReferenceBank
```
type ReferenceBank:
    referenceBankId    string  (1..1)  [metadata scheme]
    referenceBankName  string  (0..1)
```

#### ReferenceBanks
```
type ReferenceBanks:
    referenceBank  ReferenceBank  (1..*)
```

#### AncillaryEntity (choice type)
```
type AncillaryEntity:
    ancillaryParty  AncillaryRoleEnum  (0..1)
    legalEntity     LegalEntity        (0..1)

    condition: one-of
```
- **Choice type**: exactly one of `ancillaryParty` or `legalEntity` must be present.

### 1.2 Enums

#### CounterpartyRoleEnum
```
enum CounterpartyRoleEnum:
    Party1
    Party2
```

#### PartyIdentifierTypeEnum
```
enum PartyIdentifierTypeEnum:
    BIC
    LEI
    MIC
```

#### EntityIdentifierTypeEnum (extends PartyIdentifierTypeEnum)
```
enum EntityIdentifierTypeEnum extends PartyIdentifierTypeEnum:
    REDID
    CountryCode
    Other
```
- **Inherits**: BIC, LEI, MIC from PartyIdentifierTypeEnum, adds REDID, CountryCode, Other.

#### PersonIdentifierTypeEnum
```
enum PersonIdentifierTypeEnum:
    ARNU    -- Alien Registration Number
    CCPT    -- Passport Number
    CUST    -- Customer Identification Number
    DRLC    -- Drivers License Number
    EMPL    -- Employee Identification Number
    NIDN    -- National Identity Number
    SOSE    -- Social Security Number
    TXID    -- Tax Identification Number
    NPID    -- Natural Person Identifier
    PLID    -- Privacy Law Identifier
```

#### AccountTypeEnum
```
enum AccountTypeEnum:
    AggregateClient
    Client
    House
```

#### PayerReceiverEnum
```
enum PayerReceiverEnum:
    Payer
    Receiver
```
- Used to identify a single side of a payer/receiver pair.

#### NaturalPersonRoleEnum
```
enum NaturalPersonRoleEnum:
    Broker
    Buyer
    DecisionMaker
    ExecutionWithinFirm
    InvestmentDecisionMaker
    Seller
    Trader
```

#### PartyRoleEnum (57 values -- key subset for equity trade)
```
enum PartyRoleEnum:
    Accountant
    AgentLender
    AllocationAgent
    ArrangingBroker
    BarrierDeterminationAgent
    BeneficialOwner
    Beneficiary
    BookingParty
    Borrower
    Buyer
    BuyerDecisionMaker
    Chargor
    ClearingClient
    ClearingExceptionParty
    ClearingFirm
    ClearingOrganization
    Client
    ClientDecisionMaker
    ConfirmationPlatform
    ContractualParty
    CounterPartyAffiliate
    CounterPartyUltimateParent
    Counterparty
    CreditSupportProvider
    Custodian
    DataSubmitter
    DeterminingParty
    DisputingParty
    DocumentRepository
    ExecutingBroker
    ExecutingEntity
    ExecutionAgent
    ExecutionFacility
    Guarantor
    HedgingParty
    Lender
    MarginAffiliate
    OrderTransmitter
    Pledgor
    PrimeBroker
    PriorTradeRepository
    PTRRServiceProvider
    PublicationVenue
    ReportingParty
    ReportingPartyAffiliate
    ReportingPartyUltimateParent
    Seller
    SellerDecisionMaker
    SecuredParty
    SettlementAgent
    TradeRepository
    TradeSource
    TradingManager
    TradingPartner
    TripartyAgent
    ThirdPartyCustodian
```

#### AncillaryRoleEnum
```
enum AncillaryRoleEnum:
    DisruptionEventsDeterminingParty
    ExtraordinaryDividendsParty
    PredeterminedClearingOrganizationParty
    ExerciseNoticeReceiverPartyManual
    ExerciseNoticeReceiverPartyOptionalEarlyTermination
    ExerciseNoticeReceiverPartyCancelableProvision
    ExerciseNoticeReceiverPartyExtendibleProvision
    CalculationAgentIndependent
    CalculationAgentOptionalEarlyTermination
    CalculationAgentMandatoryEarlyTermination
    CalculationAgentFallback
```

#### TelephoneTypeEnum
```
enum TelephoneTypeEnum:
    Work
    Mobile
    Fax
    Personal
```

#### EntityTypeEnum
```
enum EntityTypeEnum:
    Asian
    AustralianAndNewZealand
    EuropeanEmergingMarkets
    Japanese
    NorthAmericanHighYield
    NorthAmericanInsurance
    NorthAmericanInvestmentGrade
    Singaporean
    WesternEuropean
    WesternEuropeanInsurance
```

---

## 2. Attestor Current State

### 2.1 Party (`attestor/instrument/types.py`)

```python
@final
@dataclass(frozen=True, slots=True)
class Party:
    party_id: NonEmptyStr       # single string, not typed
    name: NonEmptyStr           # required (CDM: 0..1)
    lei: LEI                    # exactly 20-char alphanumeric
```

**Factory**: `Party.create(party_id, name, lei)` -- all three required.

Key observations:
- `party_id` is a plain `NonEmptyStr`, not a `PartyIdentifier` with type enum.
- Only one identifier allowed (CDM: 1..*).
- `name` is required (CDM: optional).
- `lei` is a dedicated field; CDM puts LEI inside `PartyIdentifier.identifierType`.
- No support for: `businessUnit`, `person`, `personRole`, `account`, `contactInformation`.
- Not a metadata-key type (no cross-referencing support).

### 2.2 CounterpartyRole / PayerReceiver (`attestor/core/types.py`)

```python
type CounterpartyRole = Literal["PARTY1", "PARTY2"]

@final
@dataclass(frozen=True, slots=True)
class PayerReceiver:
    payer: CounterpartyRole
    receiver: CounterpartyRole
    # __post_init__: payer != receiver
```

- `CounterpartyRole` is a `Literal` type alias, not an enum. Functionally equivalent to CDM `CounterpartyRoleEnum`.
- `PayerReceiver` matches CDM structure. Invariant (payer != receiver) is enforced.
- No `BuyerSeller` type exists.

### 2.3 Party references in gateway (`attestor/gateway/types.py`)

```python
class CanonicalOrder:
    counterparty_lei: LEI
    executing_party_lei: LEI
```

- Parties are referenced by LEI only, not by `Party` reference.
- No `Counterparty` type wrapping (role + partyReference).
- No `PartyRole` assignments.

### 2.4 Trade / TradeState (`attestor/instrument/lifecycle.py`)

```python
class Trade:
    trade_id: NonEmptyStr
    trade_date: date
    payer_receiver: PayerReceiver
    product_id: NonEmptyStr
    currency: NonEmptyStr
    legal_agreement_id: NonEmptyStr | None
```

- No `party` field (CDM Trade has `party (0..*)` referencing Party objects).
- No `partyRole` field (CDM Trade has `partyRole (0..*)`).
- `payer_receiver` is present but Trade lacks the party list to resolve roles.

### 2.5 Account (`attestor/ledger/transactions.py`)

```python
class AccountType(Enum):
    CASH, SECURITIES, DERIVATIVES, COLLATERAL, MARGIN, ACCRUALS, PNL, NETTING

class Account:
    account_id: NonEmptyStr
    account_type: AccountType
```

- Ledger Account is a bookkeeping concept, not the CDM party-Account.
- CDM Account has: `partyReference`, `accountNumber`, `accountName`, `accountType` (Client/House/AggregateClient), `accountBeneficiary`, `servicingParty`.
- Attestor's AccountType enum values (CASH, SECURITIES, etc.) are ledger types; CDM's AccountTypeEnum values (Client, House, AggregateClient) are ownership types.
- These serve different purposes and should coexist.

### 2.6 LEI (`attestor/core/identifiers.py`)

```python
class LEI:
    value: str  # exactly 20 alphanumeric
```

- Valid identifier type, but only covers one of CDM's `PartyIdentifierTypeEnum` values (BIC, LEI, MIC).

---

## 3. Gap Analysis

### 3.1 Missing Types

| CDM Type | Priority | Notes |
|---|---|---|
| **PartyIdentifier** | HIGH | Party needs typed, multi-valued identifiers |
| **Counterparty** | HIGH | Needed to bind CounterpartyRoleEnum to actual Party refs at product level |
| **BuyerSeller** | HIGH | Needed for equity/option direction (buyer/seller vs. payer/receiver) |
| **PartyRole** | HIGH | Needed on Trade to assign roles (Buyer, Seller, ExecutingBroker, etc.) |
| **NaturalPerson** | MEDIUM | Needed for MiFID II regulatory reporting (trader, decision maker) |
| **NaturalPersonRole** | MEDIUM | Pairs with NaturalPerson |
| **PersonIdentifier** | MEDIUM | Supports NaturalPerson identification |
| **Account** (CDM version) | MEDIUM | Party-facing account (distinct from ledger account) |
| **LegalEntity** | MEDIUM | Formal legal entity with entity identifiers |
| **EntityIdentifier** | MEDIUM | Supports LegalEntity identification |
| **RelatedParty** | LOW | For guarantors, credit support providers |
| **AncillaryParty** | LOW | For calculation agents, clearing org on product |
| **AncillaryEntity** | LOW | Choice type for ancillary identification |
| **PartyReferencePayerReceiver** | LOW | Direct party refs (non-abstracted) for settlement |
| **Address** | LOW | Contact details |
| **ContactInformation** | LOW | Contact details |
| **TelephoneNumber** | LOW | Contact details |
| **BusinessUnit** | LOW | Organizational structure |
| **ReferenceBank** / **ReferenceBanks** | LOW | Rate polling (ISDA credit) |

### 3.2 Missing Enums

| CDM Enum | Priority | Notes |
|---|---|---|
| **PartyRoleEnum** | HIGH | 57 values; need at least equity-trade subset (~15 values) |
| **PartyIdentifierTypeEnum** | HIGH | BIC, LEI, MIC |
| **CounterpartyRoleEnum** | EXISTS | As `Literal["PARTY1","PARTY2"]`; consider promoting to Enum |
| **NaturalPersonRoleEnum** | MEDIUM | 7 values for trader/decision-maker roles |
| **PersonIdentifierTypeEnum** | MEDIUM | 10 values for person ID sources |
| **EntityIdentifierTypeEnum** | MEDIUM | Extends PartyIdentifierTypeEnum + 3 values |
| **AccountTypeEnum** (CDM) | MEDIUM | Client, House, AggregateClient (distinct from ledger AccountType) |
| **PayerReceiverEnum** | LOW | Payer/Receiver single-side identifier |
| **AncillaryRoleEnum** | LOW | 11 values for ancillary party roles |
| **TelephoneTypeEnum** | LOW | Work, Mobile, Fax, Personal |
| **EntityTypeEnum** | LOW | Credit-specific reference entity types |

### 3.3 Structural Misalignments

#### 3.3.1 Party -- Flat vs. Composed (CRITICAL)

**CDM**: Party is a rich aggregate with multi-valued `partyId: PartyIdentifier (1..*)`, optional name, nested business units, persons, and contact info.

**Attestor**: Party is a flat 3-field value object (`party_id`, `name`, `lei`). The `lei` is separated from `party_id` rather than being a typed identifier within a `PartyIdentifier` list.

**Impact**: Cannot represent a party with multiple identifiers (LEI + BIC), cannot attach persons or business units, cannot cross-reference via metadata key.

#### 3.3.2 Party.name cardinality mismatch

**CDM**: `name (0..1)` -- optional.
**Attestor**: `name: NonEmptyStr` -- required.

**Impact**: Minor. CDM allows anonymous parties identified only by ID. Attestor forces a name.

#### 3.3.3 CounterpartyRole -- Literal vs. Enum

**CDM**: `CounterpartyRoleEnum` is a proper enum with `Party1`, `Party2`.
**Attestor**: `type CounterpartyRole = Literal["PARTY1", "PARTY2"]` -- a type alias.

**Impact**: Functional equivalence but no `.name`, `.value` introspection or iteration. Cannot be used in match/case pattern matching on enum members. Inconsistent with other Attestor enums that use `class X(Enum)`.

#### 3.3.4 No Counterparty binding on product/trade

**CDM**: `Counterparty` type binds `CounterpartyRoleEnum` to actual `Party` references at the trade level. Products reference abstract `Party1`/`Party2`; the `Counterparty` list on Trade resolves these to real parties.

**Attestor**: `CanonicalOrder` has raw `counterparty_lei` and `executing_party_lei` fields. `Trade` has `payer_receiver` but no `party` or `counterparty` list. There is no mechanism to resolve `PARTY1`/`PARTY2` to actual `Party` objects.

**Impact**: Cannot associate PayerReceiver roles with actual parties. Cannot support the CDM pattern of product-agnostic party abstraction.

#### 3.3.5 Trade missing party and partyRole fields

**CDM Trade** has:
- `party (0..*)`
- `partyRole (0..*)`

**Attestor Trade** has neither. Party information is only on `Instrument.parties: tuple[Party, ...]` but not on `Trade`.

**Impact**: Trade cannot carry regulatory roles (Buyer, Seller, ExecutingBroker, ReportingParty, etc.). Regulatory reporting (MiFID II, Dodd-Frank) requires these.

#### 3.3.6 Account -- Different concepts

**CDM Account**: Party-facing account with `partyReference`, `accountNumber`, `accountName`, `accountType` (Client/House/AggregateClient), `accountBeneficiary`, `servicingParty`.

**Attestor Account** (ledger): Bookkeeping account with `account_id` and `account_type` (CASH, SECURITIES, etc.).

**Impact**: These are distinct concepts. CDM Account is needed at the party/trade level for FpML compliance. Ledger Account is internal. Both should exist.

#### 3.3.7 No BuyerSeller type for equity/option direction

**CDM**: `BuyerSeller` specifies which counterparty is buyer vs. seller.
**Attestor**: Uses `OrderSide` enum (BUY/SELL) on `CanonicalOrder` for direction, but has no typed `BuyerSeller` at the product/trade level.

**Impact**: Cannot express buyer/seller direction in CDM-canonical form on trades. OrderSide is an order concept, not a trade/product concept.

### 3.4 Extra (Attestor has, CDM does not need)

| Attestor Element | Status |
|---|---|
| `Party.lei` as dedicated field | Redundant if PartyIdentifier is adopted (LEI becomes one of the identifiers) |
| `CanonicalOrder.counterparty_lei` / `executing_party_lei` | Gateway-specific; fine for gateway layer but Trade should use Party refs |
| Ledger `AccountType` enum | Internal; not a CDM concept; keep as-is |

---

## 4. Recommended Changes

### Priority 1 -- Critical for Equity Trade Alignment

#### P1.1 Create `PartyIdentifierTypeEnum` and `PartyIdentifier`

```python
class PartyIdentifierTypeEnum(Enum):
    BIC = "BIC"
    LEI = "LEI"
    MIC = "MIC"

@final
@dataclass(frozen=True, slots=True)
class PartyIdentifier:
    identifier: NonEmptyStr
    identifier_type: PartyIdentifierTypeEnum | None = None  # 0..1
```

**Location**: `attestor/core/identifiers.py` or new `attestor/core/party.py`.

#### P1.2 Refactor `Party` to CDM structure

```python
@final
@dataclass(frozen=True, slots=True)
class Party:
    party_id: tuple[PartyIdentifier, ...]    # 1..*
    name: str | None = None                   # 0..1
    person: tuple[NaturalPerson, ...] = ()    # 0..*  (add when needed)
    person_role: tuple[NaturalPersonRole, ...] = ()  # 0..*
    account: Account | None = None            # 0..1  (CDM Account, not ledger)
    # businessUnit, contactInformation: defer to later phase
```

Keep `LEI` validator; use it inside `PartyIdentifier` validation when `identifier_type == LEI`.

**Breaking change**: All callers of `Party(party_id=..., name=..., lei=...)` must migrate. Provide a compatibility factory `Party.from_lei(name, lei) -> Party` to ease transition.

#### P1.3 Promote `CounterpartyRole` to enum

```python
class CounterpartyRoleEnum(Enum):
    PARTY1 = "PARTY1"
    PARTY2 = "PARTY2"
```

Replace `type CounterpartyRole = Literal["PARTY1", "PARTY2"]` in `core/types.py`. Update `PayerReceiver` to use the enum.

#### P1.4 Create `Counterparty` type

```python
@final
@dataclass(frozen=True, slots=True)
class Counterparty:
    role: CounterpartyRoleEnum               # 1..1
    party_reference: Party                    # 1..1 (or party_id for reference)
```

#### P1.5 Create `BuyerSeller` type

```python
@final
@dataclass(frozen=True, slots=True)
class BuyerSeller:
    buyer: CounterpartyRoleEnum    # 1..1
    seller: CounterpartyRoleEnum   # 1..1

    def __post_init__(self) -> None:
        if self.buyer == self.seller:
            raise TypeError("BuyerSeller: buyer must differ from seller")
```

#### P1.6 Create `PartyRoleEnum` (equity-trade subset)

```python
class PartyRoleEnum(Enum):
    BUYER = "Buyer"
    SELLER = "Seller"
    COUNTERPARTY = "Counterparty"
    EXECUTING_BROKER = "ExecutingBroker"
    EXECUTING_ENTITY = "ExecutingEntity"
    EXECUTION_FACILITY = "ExecutionFacility"
    CLEARING_ORGANIZATION = "ClearingOrganization"
    CLEARING_FIRM = "ClearingFirm"
    CLEARING_CLIENT = "ClearingClient"
    CUSTODIAN = "Custodian"
    REPORTING_PARTY = "ReportingParty"
    BENEFICIARY = "Beneficiary"
    CLIENT = "Client"
    SETTLEMENT_AGENT = "SettlementAgent"
    TRADE_SOURCE = "TradeSource"
```

Add remaining values later as asset classes require them.

#### P1.7 Create `PartyRole` type

```python
@final
@dataclass(frozen=True, slots=True)
class PartyRole:
    party_reference: Party              # 1..1 (or reference key)
    role: PartyRoleEnum                 # 1..1
    ownership_party_reference: Party | None = None  # 0..1
```

#### P1.8 Add `party` and `party_role` to `Trade`

```python
class Trade:
    trade_id: NonEmptyStr
    trade_date: date
    counterparty: tuple[Counterparty, ...]   # NEW: 2..2 (Party1 + Party2)
    party_role: tuple[PartyRole, ...]        # NEW: 0..*
    payer_receiver: PayerReceiver
    product_id: NonEmptyStr
    currency: NonEmptyStr
    legal_agreement_id: NonEmptyStr | None = None
```

The `counterparty` tuple should have exactly 2 entries binding PARTY1 and PARTY2 to actual parties. Add a `__post_init__` validation.

### Priority 2 -- Needed for Regulatory / MiFID II

#### P2.1 Create `NaturalPerson`

```python
@final
@dataclass(frozen=True, slots=True)
class NaturalPerson:
    person_id: tuple[PersonIdentifier, ...] = ()  # 0..*
    first_name: str | None = None                   # 0..1
    surname: str | None = None                      # 0..1
    date_of_birth: date | None = None               # 0..1
    # honorific, middleName, initial, suffix, contactInformation: defer

    def __post_init__(self) -> None:
        # CDM condition: (firstName and surname) or personId
        if not ((self.first_name and self.surname) or self.person_id):
            raise TypeError(
                "NaturalPerson: must have (firstName + surname) or personId"
            )
```

#### P2.2 Create `NaturalPersonRoleEnum` and `NaturalPersonRole`

```python
class NaturalPersonRoleEnum(Enum):
    BROKER = "Broker"
    BUYER = "Buyer"
    DECISION_MAKER = "DecisionMaker"
    EXECUTION_WITHIN_FIRM = "ExecutionWithinFirm"
    INVESTMENT_DECISION_MAKER = "InvestmentDecisionMaker"
    SELLER = "Seller"
    TRADER = "Trader"

@final
@dataclass(frozen=True, slots=True)
class NaturalPersonRole:
    person_reference: NaturalPerson           # 1..1
    role: tuple[NaturalPersonRoleEnum, ...]   # 0..*
```

#### P2.3 Create CDM-aligned `Account` (party-facing)

```python
class CdmAccountTypeEnum(Enum):
    AGGREGATE_CLIENT = "AggregateClient"
    CLIENT = "Client"
    HOUSE = "House"

@final
@dataclass(frozen=True, slots=True)
class PartyAccount:
    account_number: NonEmptyStr               # 1..1
    account_name: str | None = None           # 0..1
    account_type: CdmAccountTypeEnum | None = None  # 0..1
    party_reference: Party | None = None      # 0..1
    account_beneficiary: Party | None = None  # 0..1
    servicing_party: Party | None = None      # 0..1
```

Name it `PartyAccount` to avoid collision with ledger `Account`.

#### P2.4 Create `PersonIdentifierTypeEnum` and `PersonIdentifier`

```python
class PersonIdentifierTypeEnum(Enum):
    ARNU = "ARNU"
    CCPT = "CCPT"
    CUST = "CUST"
    DRLC = "DRLC"
    EMPL = "EMPL"
    NIDN = "NIDN"
    SOSE = "SOSE"
    TXID = "TXID"
    NPID = "NPID"
    PLID = "PLID"

@final
@dataclass(frozen=True, slots=True)
class PersonIdentifier:
    identifier: NonEmptyStr
    identifier_type: PersonIdentifierTypeEnum | None = None
    country: str | None = None  # ISO 3166
```

### Priority 3 -- Lower Priority / Deferred

#### P3.1 Create `LegalEntity` and `EntityIdentifier`

Needed when the model must distinguish between legal entities and natural persons at a structural level.

#### P3.2 Create `RelatedParty`

Needed for guarantor, credit support provider relationships.

#### P3.3 Create `AncillaryParty`, `AncillaryRoleEnum`, `AncillaryEntity`

Needed for calculation agent, clearing org designation on products.

#### P3.4 Create `PartyReferencePayerReceiver`

Needed for direct-party-reference settlement instructions (as opposed to role-based).

#### P3.5 Create contact detail types

`Address`, `ContactInformation`, `TelephoneNumber`, `BusinessUnit` -- needed when party master data management is in scope.

#### P3.6 Add remaining `PartyRoleEnum` values

Extend the enum as new asset classes or regulatory use cases demand additional roles (e.g., `HedgingParty`, `PrimeBroker`, `DataSubmitter`).

---

## 5. Migration Notes

### Breaking Changes

1. **`Party` refactor** (P1.2): Every file that creates `Party(party_id=..., name=..., lei=...)` must change. Provide `Party.from_lei()` factory for backward compatibility.
2. **`CounterpartyRole` to enum** (P1.3): All `Literal["PARTY1","PARTY2"]` references become `CounterpartyRoleEnum.PARTY1` / `.PARTY2`. Affects `PayerReceiver`, `BuyerSeller`, `Counterparty`.
3. **`Trade` gains new fields** (P1.8): All `Trade()` construction sites must supply `counterparty` and `party_role`.

### Suggested File Organization

- `attestor/core/party.py` -- NEW: `PartyIdentifier`, `PartyIdentifierTypeEnum`, `Party`, `Counterparty`, `CounterpartyRoleEnum`, `BuyerSeller`, `PayerReceiver` (moved from core/types.py), `PartyRole`, `PartyRoleEnum`, `NaturalPerson`, `NaturalPersonRole`, `NaturalPersonRoleEnum`, `PersonIdentifier`, `PersonIdentifierTypeEnum`, `PartyAccount`, `CdmAccountTypeEnum`.
- `attestor/core/types.py` -- Remove `CounterpartyRole`, `PayerReceiver`; re-export from `core/party.py` for backward compat.
- `attestor/core/identifiers.py` -- Keep `LEI`, `UTI`, `ISIN` as validator newtypes. `PartyIdentifier` uses `LEI` validator when `identifier_type == LEI`.

### Test Impact

The `Party` refactor and `Trade` enrichment will touch a large fraction of existing tests. Plan for a single atomic PR that:
1. Creates new party types.
2. Refactors Party with compat factory.
3. Adds party/partyRole to Trade.
4. Updates all tests.
