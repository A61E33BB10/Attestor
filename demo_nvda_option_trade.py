"""
demo_nvda_option_trade.py -- An educational walkthrough of Attestor's CDM building blocks.

This file builds an OTC equity call option trade on NVIDIA (NVDA) from first principles,
using Attestor's CDM-aligned type system. Every line teaches something.

The ISDA Common Domain Model (CDM) is a standardized digital representation of trade
lifecycle events. It answers the question: "How do we represent a financial trade so that
every bank, regulator, and CCP in the world means exactly the same thing?"

Attestor implements CDM concepts as Python dataclasses with compile-time and runtime
validation. The key insight: illegal states are structurally unrepresentable.

We will build:
  1. NVDA as a CDM Security (with ISIN, CUSIP, exchange listing)
  2. Two counterparties (Goldman Sachs, JP Morgan) as CDM Parties with LEIs
  3. An OTC call option on NVDA with full CDM terms
  4. A CanonicalOrder representing the trade
  5. The lifecycle: ExecutePI -> BusinessEvent -> Trade -> TradeState

Run this:  .venv/bin/python demo_nvda_option_trade.py
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

# We import only what we need, but we'll explain every type as we use it.
#
# NOTE ON IMPORT ORDER: Attestor's package __init__.py files re-export types
# for convenience, which creates circular import chains (gateway -> instrument
# -> lifecycle -> gateway). We break this by importing derivative_types before
# gateway.types, ensuring the module is already initialized when lifecycle.py
# needs gateway.types. This is a standard Python pattern for large codebases.

from attestor.core.identifiers import ISIN, LEI
from attestor.core.money import Money, NonEmptyStr
from attestor.core.party import CounterpartyRoleEnum
from attestor.core.result import Ok, Err
from attestor.core.types import PayerReceiver, UtcDatetime

# Instrument-layer types (imported BEFORE gateway to break circular import)
from attestor.instrument.derivative_types import (
    OptionDetail,
    OptionExerciseStyleEnum,
    OptionPayoutSpec,
    OptionTypeEnum,
    SettlementTypeEnum,
)
from attestor.instrument.asset import (
    AssetIdentifier,
    AssetIdTypeEnum,
    EquityClassification,
    EquityType,
    EquityTypeEnum,
    Security,
    create_equity_security,
)
from attestor.instrument.types import (
    EconomicTerms,
    Instrument,
    Party,
    Product,
    create_option_instrument,
)

# Gateway and lifecycle (safe now that derivative_types is loaded)
from attestor.gateway.types import CanonicalOrder, OrderSide, OrderType
from attestor.instrument.lifecycle import (
    ActionEnum,
    BusinessEvent,
    EventIntentEnum,
    ExecutePI,
    ExecutionTypeEnum,
    PositionStatusEnum,
    Trade,
    TradeState,
)
from attestor.instrument.qualification import AssetClassEnum, qualify_asset_class


def sep(title: str) -> None:
    """Print a section separator."""
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print(f"{'=' * 72}\n")


# ============================================================================
#  STEP 1: CREATE NVDA AS A CDM SECURITY
# ============================================================================
#
# In CDM, the asset taxonomy is:
#   Asset = Cash | Commodity | DigitalAsset | Instrument
#   Instrument = Security | Loan | ListedDerivative
#   Security = identifiers + classification + exchange info
#
# A Security must have:
#   - At least one AssetIdentifier (ISIN, CUSIP, SEDOL, etc.)
#   - A SecurityClassification (EquityClassification or FundClassification)
#   - Currency and exchange listing info
#
# This makes illegal states structurally unrepresentable:
#   - You can't create a Security with no identifiers (runtime check)
#   - You can't mix equity and fund classifications (sum type)
#   - If exchange is set, is_exchange_listed must be True (CDM condition)

sep("STEP 1: Create NVDA as a CDM Security")

# --- Method A: Using the factory function (recommended for common cases) ---
# create_equity_security() handles ISIN validation (Luhn check), CUSIP format
# validation, exchange MIC validation (ISO 10383), and wires up the classification.

nvda_result = create_equity_security(
    isin="US67066G1040",       # NVIDIA's real ISIN (12 chars, Luhn-verified)
    cusip="67066G104",         # NVIDIA's real CUSIP (9 alphanumeric chars)
    equity_type=EquityTypeEnum.ORDINARY,  # Common stock (not preferred, not ADR)
    exchange="XNAS",           # NASDAQ (ISO 10383 MIC code)
    currency="USD",            # ISO 4217 currency code
)

# Attestor uses Result types (Ok/Err) instead of exceptions for validation.
# This is monadic error handling -- the caller decides how to handle errors.
match nvda_result:
    case Ok(nvda):
        print("NVDA Security created successfully.")
    case Err(e):
        raise RuntimeError(f"Failed to create NVDA: {e}")

# Let's inspect what was built:
print(f"  Identifiers:        {len(nvda.identifiers)} identifiers")
for aid in nvda.identifiers:
    print(f"    {aid.identifier_type.value:6s} = {aid.identifier.value}")

print(f"  Instrument type:    {nvda.instrument_type.value}")  # Derived from classification
eq_cls = nvda.classification
assert isinstance(eq_cls, EquityClassification)
print(f"  Classification:     {eq_cls.equity_type.equity_type.value} equity")
print(f"  Exchange-listed:    {nvda.is_exchange_listed}")
print(f"  Exchange MIC:       {nvda.exchange.value if nvda.exchange else 'None'}")
print(f"  Currency:           {nvda.currency.value}")

# --- Method B: Building from primitives (for understanding) ---
# The factory above does the same as this, but this shows every layer:

print("\n--- Building from primitives (for understanding) ---")

# Step 1a: Create validated identifiers
isin_id = AssetIdentifier.create("US67066G1040", AssetIdTypeEnum.ISIN)
cusip_id = AssetIdentifier.create("67066G104", AssetIdTypeEnum.CUSIP)
assert isinstance(isin_id, Ok) and isinstance(cusip_id, Ok)

# Step 1b: Compose the classification sum type
#   EquityClassification wraps EquityType wraps EquityTypeEnum
#   This layering exists because CDM distinguishes:
#     - The broad instrument type (EQUITY vs FUND vs DEBT)
#     - The equity sub-type (ORDINARY vs PREFERRED vs ADR)
#     - The depositary receipt type (only if ADR)
equity_cls = EquityClassification(
    equity_type=EquityType(
        equity_type=EquityTypeEnum.ORDINARY,
        depositary_receipt=None,  # Would be ADR/GDR/etc. if DEPOSITARY_RECEIPT
    )
)

# Step 1c: Create the Security from primitives
nvda_manual = Security.create(
    identifiers=(isin_id.value, cusip_id.value),
    classification=equity_cls,
    currency="USD",
    exchange="XNAS",
    # is_exchange_listed is auto-derived from exchange when not explicit
)
assert isinstance(nvda_manual, Ok)
print(f"  Manual Security matches factory: {nvda == nvda_manual.value}")


# ============================================================================
#  STEP 2: CREATE COUNTERPARTIES
# ============================================================================
#
# In CDM, a Party has:
#   - party_id: one or more PartyIdentifiers (LEI, BIC, MIC, or untyped)
#   - name: optional human-readable name
#
# LEI (Legal Entity Identifier) is a 20-character alphanumeric code
# assigned to every legal entity involved in financial transactions.
# It's the global answer to "who is this counterparty?"
#
# Attestor validates LEI format at construction time. You cannot create
# a Party with an invalid LEI -- the type system prevents it.

sep("STEP 2: Create Counterparties (Goldman Sachs and JP Morgan)")

# Party.from_lei() creates a Party with both an untyped party_id
# and a typed LEI PartyIdentifier. This matches CDM's partyId (1..*)
# cardinality -- every party needs at least one identifier.

gs_result = Party.from_lei(
    party_id="GS",                          # Short alias for internal reference
    name="Goldman Sachs",                   # Human-readable name
    lei="784F5XWPLTWKTBV3E584",             # Goldman Sachs real LEI
)
match gs_result:
    case Ok(gs):
        print(f"  Bank1: {gs.name.value}")
        for pid in gs.party_id:
            id_type = pid.identifier_type.value if pid.identifier_type else "ALIAS"
            print(f"    {id_type:6s} = {pid.identifier.value}")
    case Err(e):
        raise RuntimeError(f"Failed to create GS: {e}")

jpm_result = Party.from_lei(
    party_id="JPM",
    name="JP Morgan",
    lei="7H6GLXDRUGQFU57RNE97",             # JP Morgan real LEI
)
match jpm_result:
    case Ok(jpm):
        print(f"  Bank2: {jpm.name.value}")
        for pid in jpm.party_id:
            id_type = pid.identifier_type.value if pid.identifier_type else "ALIAS"
            print(f"    {id_type:6s} = {pid.identifier.value}")
    case Err(e):
        raise RuntimeError(f"Failed to create JPM: {e}")


# ============================================================================
#  STEP 3: CREATE THE OTC CALL OPTION ON NVDA
# ============================================================================
#
# An option in CDM is modeled as:
#   Instrument
#     -> Product
#       -> EconomicTerms
#         -> Payout (OptionPayoutSpec in this case)
#
# The OptionPayoutSpec contains:
#   - underlying_id:    what the option is on (NVDA's ISIN)
#   - strike:           the price at which you can buy (NonNegativeDecimal >= 0)
#   - expiry_date:      when the option expires
#   - option_type:      CALL or PUT (also PAYER/RECEIVER for swaptions)
#   - option_style:     EUROPEAN (single date), AMERICAN (any time), BERMUDA (specific dates)
#   - settlement_type:  CASH, PHYSICAL, ELECTION, or CASH_OR_PHYSICAL
#   - currency:         premium/settlement currency
#   - exchange:         where it's traded/quoted
#   - multiplier:       contract size (typically 100 shares per contract)
#
# The layering is deliberate:
#   OptionPayoutSpec  = "What are the cashflow rules?"
#   EconomicTerms     = "What dates and payouts define this product?"
#   Product           = "Wrapper for EconomicTerms"
#   Instrument        = "Product + parties + lifecycle status"

sep("STEP 3: Create OTC Call Option on NVDA")

# We'll use the high-level factory first, then show the primitives.

trade_date = date(2025, 6, 15)
expiry_date = date(2025, 12, 19)   # Dec 2025 expiry (third Friday)
strike_price = Decimal("150")       # Strike at $150
multiplier = Decimal("100")         # Standard: 100 shares per contract

option_instrument_result = create_option_instrument(
    instrument_id="NVDA-C-150-20251219",  # Descriptive: ticker-type-strike-expiry
    underlying_id="US67066G1040",          # NVDA's ISIN ties this to the underlying
    strike=strike_price,
    expiry_date=expiry_date,
    option_type=OptionTypeEnum.CALL,               # Right to BUY the underlying
    option_style=OptionExerciseStyleEnum.AMERICAN,  # Can exercise any time before expiry
    settlement_type=SettlementTypeEnum.PHYSICAL,    # Delivers actual shares, not cash
    currency="USD",
    exchange="XNAS",
    parties=(gs, jpm),               # Both counterparties
    trade_date=trade_date,
    multiplier=multiplier,
)

match option_instrument_result:
    case Ok(option_instrument):
        print("Option Instrument created successfully.")
    case Err(e):
        raise RuntimeError(f"Failed to create option instrument: {e}")

# Inspect the layered structure:
print(f"  Instrument ID:      {option_instrument.instrument_id.value}")
print(f"  Trade date:         {option_instrument.trade_date}")
print(f"  Status:             {option_instrument.status.value}")
print(f"  Parties:            {[p.name.value for p in option_instrument.parties]}")

# Drill into the Product -> EconomicTerms -> Payout:
terms = option_instrument.product.economic_terms
print(f"  Effective date:     {terms.effective_date}")
print(f"  Termination date:   {terms.termination_date}")
print(f"  Number of payouts:  {len(terms.payouts)}")

payout = terms.payouts[0]
assert isinstance(payout, OptionPayoutSpec)
print(f"  Payout type:        {type(payout).__name__}")
print(f"    Underlying:       {payout.underlying_id.value}")
print(f"    Strike:           ${payout.strike.value}")
print(f"    Expiry:           {payout.expiry_date}")
print(f"    Option type:      {payout.option_type.value}")
print(f"    Exercise style:   {payout.option_style.value}")
print(f"    Settlement:       {payout.settlement_type.value}")
print(f"    Multiplier:       {payout.multiplier.value} shares/contract")
print(f"    Currency:         {payout.currency.value}")
print(f"    Exchange:         {payout.exchange.value}")


# ============================================================================
#  STEP 4: CREATE THE CANONICAL ORDER (Gateway representation)
# ============================================================================
#
# In Attestor's architecture, a trade enters the system through the Gateway
# as a CanonicalOrder. This is the single canonical representation that
# every downstream component consumes.
#
# A CanonicalOrder is like an FpML trade message normalized into one type:
#   - order_id:              unique identifier for this order
#   - instrument_id:         what is being traded
#   - isin:                  ISIN (optional, Luhn-validated)
#   - side:                  BUY or SELL
#   - quantity:              how much (must be > 0)
#   - price:                 at what price (finite Decimal)
#   - currency:              ISO 4217
#   - order_type:            MARKET or LIMIT
#   - counterparty_lei:      who is on the other side (LEI-validated)
#   - executing_party_lei:   who is executing (LEI-validated)
#   - trade_date:            when
#   - settlement_date:       when settlement occurs (must be >= trade_date)
#   - venue:                 where
#   - timestamp:             precise UTC time
#   - instrument_detail:     discriminated union (EquityDetail | OptionDetail | ...)
#
# The instrument_detail is the key CDM alignment: it carries product-specific
# fields in a type-safe discriminated union. For options, it's OptionDetail.

sep("STEP 4: Create the CanonicalOrder (Bank1 buys the call from Bank2)")

# First, build the OptionDetail for the order.
# This mirrors the OptionPayoutSpec but is the gateway-level representation.
option_detail_result = OptionDetail.create(
    strike=strike_price,
    expiry_date=expiry_date,
    option_type=OptionTypeEnum.CALL,
    option_style=OptionExerciseStyleEnum.AMERICAN,
    settlement_type=SettlementTypeEnum.PHYSICAL,
    underlying_id="US67066G1040",   # NVDA ISIN
    multiplier=multiplier,
)
match option_detail_result:
    case Ok(option_detail):
        print("OptionDetail created.")
    case Err(e):
        raise RuntimeError(f"Failed to create OptionDetail: {e}")

# Now create the full order.
# Goldman Sachs (executing party) is BUYING the call FROM JP Morgan (counterparty).
# The premium is $12.50 per share, or $1,250 per contract.

now = UtcDatetime(value=datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC))
settlement_date = date(2025, 6, 18)  # T+3 settlement for OTC options

order_result = CanonicalOrder.create(
    order_id="ORD-2025-NVDA-001",
    instrument_id="NVDA-C-150-20251219",
    isin="US67066G1040",
    side=OrderSide.BUY,                          # GS is buying the call
    quantity=Decimal("10"),                        # 10 contracts = 1,000 shares notional
    price=Decimal("12.50"),                        # Premium: $12.50 per share
    currency="USD",
    order_type=OrderType.LIMIT,                    # Limit order at $12.50
    counterparty_lei="7H6GLXDRUGQFU57RNE97",      # JP Morgan (seller)
    executing_party_lei="784F5XWPLTWKTBV3E584",   # Goldman Sachs (buyer)
    trade_date=trade_date,
    settlement_date=settlement_date,
    venue="XNAS",
    timestamp=now,
    instrument_detail=option_detail,
)

match order_result:
    case Ok(order):
        print("CanonicalOrder created successfully.")
    case Err(e):
        raise RuntimeError(f"Failed to create order: {e}")

print(f"  Order ID:           {order.order_id.value}")
print(f"  Instrument:         {order.instrument_id.value}")
print(f"  ISIN:               {order.isin.value}")
print(f"  Side:               {order.side.value}")
print(f"  Quantity:           {order.quantity.value} contracts")
print(f"  Price:              ${order.price} per share (premium)")
print(f"  Total premium:      ${order.price * order.quantity.value * multiplier}")
print(f"  Order type:         {order.order_type.value}")
print(f"  Trade date:         {order.trade_date}")
print(f"  Settlement date:    {order.settlement_date}")
print(f"  Venue:              {order.venue.value}")
print(f"  Counterparty LEI:   {order.counterparty_lei.value}")
print(f"  Executing LEI:      {order.executing_party_lei.value}")

# Use CDM qualification to verify asset class:
asset_class = qualify_asset_class(order)
print(f"  CDM Asset Class:    {asset_class.value if asset_class else 'Unknown'}")


# ============================================================================
#  STEP 5: THE TRADE LIFECYCLE -- ExecutePI -> BusinessEvent -> TradeState
# ============================================================================
#
# CDM models trade lifecycle as state transitions:
#
#   PROPOSED -> FORMED -> SETTLED -> CLOSED
#              \-> CANCELLED    \-> CANCELLED
#
# Each transition is triggered by a BusinessEvent, which wraps a
# PrimitiveInstruction. The instruction types are:
#
#   ExecutePI:   Execute a new trade (order -> trade)
#   TransferPI:  Settlement transfer (cash + securities)
#   ExercisePI:  Option exercise
#   ExpiryPI:    Option/futures expiry
#   DividendPI:  Dividend payment
#   MarginPI:    Margin call/return
#   ...and more (QuantityChangePI, PartyChangePI, SplitPI, etc.)
#
# The key CDM concept here is:
#   BusinessEvent = instruction + before (TradeState) + after (TradeState[])
#   This captures the complete state transition with full audit trail.

sep("STEP 5: Trade Lifecycle -- From Order to Formed Trade")

# Step 5a: Create the "Execute" primitive instruction.
# An ExecutePI wraps a CanonicalOrder -- it says "make this order into a trade."

execute_instruction = ExecutePI(order=order)
print(f"  PrimitiveInstruction: {type(execute_instruction).__name__}")
print(f"    Wraps order:       {execute_instruction.order.order_id.value}")

# Step 5b: Create the Trade object.
# A Trade in CDM is:
#   trade_id + trade_date + payer_receiver + product_id + currency
#   + legal_agreement_id + execution_type + execution_venue + cleared_date
#
# PayerReceiver uses abstract roles (PARTY1/PARTY2) rather than specific names.
# This is a CDM design pattern: the trade structure is role-based, and the
# mapping from role to actual party is done separately.
#
# For our option: GS (PARTY1) pays premium, JPM (PARTY2) receives premium.

payer_receiver = PayerReceiver(
    payer=CounterpartyRoleEnum.PARTY1,     # GS pays premium
    receiver=CounterpartyRoleEnum.PARTY2,  # JPM receives premium
)

trade = Trade(
    trade_id=NonEmptyStr(value="TRD-2025-NVDA-001"),
    trade_date=trade_date,
    payer_receiver=payer_receiver,
    product_id=NonEmptyStr(value="NVDA-C-150-20251219"),
    currency=NonEmptyStr(value="USD"),
    legal_agreement_id=NonEmptyStr(value="ISDA-MA-GS-JPM-2023"),
    execution_type=ExecutionTypeEnum.OFF_FACILITY,  # OTC, not on exchange
    # execution_venue is None for OFF_FACILITY (not required)
    # cleared_date is None (bilateral, not cleared through CCP)
)

print(f"\n  Trade created:")
print(f"    Trade ID:          {trade.trade_id.value}")
print(f"    Trade date:        {trade.trade_date}")
print(f"    Product ID:        {trade.product_id.value}")
print(f"    Currency:          {trade.currency.value}")
print(f"    Payer (premium):   {trade.payer_receiver.payer.value} (GS)")
print(f"    Receiver:          {trade.payer_receiver.receiver.value} (JPM)")
print(f"    Legal agreement:   {trade.legal_agreement_id.value}")
print(f"    Execution type:    {trade.execution_type.value}")
print(f"    Cleared:           {'Yes' if trade.cleared_date else 'No (bilateral OTC)'}")

# Step 5c: Create the initial TradeState.
# TradeState is an immutable snapshot: (Trade, PositionStatusEnum).
# Each lifecycle event produces a new TradeState (functional state machine).

initial_state = TradeState(
    trade=trade,
    status=PositionStatusEnum.PROPOSED,
    # closed_state must be None when not CLOSED (enforced by __post_init__)
    # reset_history, transfer_history start empty
)

print(f"\n  Initial TradeState:")
print(f"    Status:            {initial_state.status.value}")
print(f"    Closed state:      {initial_state.closed_state}")
print(f"    Reset history:     {len(initial_state.reset_history)} entries")
print(f"    Transfer history:  {len(initial_state.transfer_history)} entries")

# Step 5d: Create the BusinessEvent for execution.
# A BusinessEvent wraps:
#   instruction:  what happened (ExecutePI)
#   before:       state before the event (PROPOSED)
#   after:        state(s) after the event (FORMED)
#   event_intent: CDM classification of what this event means
#   action:       NEW, CANCEL, or CORRECT

formed_state = TradeState(
    trade=trade,
    status=PositionStatusEnum.FORMED,
)

execution_event = BusinessEvent(
    instruction=execute_instruction,
    timestamp=now,
    attestation_id="ATT-2025-001",
    before=initial_state,
    after=(formed_state,),
    event_intent=EventIntentEnum.CONTRACT_FORMATION,
    action=ActionEnum.NEW,
    event_date=trade_date,
    effective_date=trade_date,
    event_qualifier=NonEmptyStr(value="ContractFormation"),
)

print(f"\n  BusinessEvent (Execution):")
print(f"    Instruction:       {type(execution_event.instruction).__name__}")
print(f"    Timestamp:         {execution_event.timestamp.value.isoformat()}")
print(f"    Attestation ID:    {execution_event.attestation_id}")
print(f"    Before status:     {execution_event.before.status.value}")
print(f"    After status:      {execution_event.after[0].status.value}")
print(f"    Event intent:      {execution_event.event_intent.value}")
print(f"    Action:            {execution_event.action.value}")
print(f"    Event date:        {execution_event.event_date}")
print(f"    Event qualifier:   {execution_event.event_qualifier.value}")


# ============================================================================
#  STEP 6: VERIFY STATE TRANSITIONS
# ============================================================================
#
# CDM defines valid state transitions as a finite-state machine.
# Attestor implements this as a frozenset of (from, to) tuples.
# This is the EQUITY_TRANSITIONS / DERIVATIVE_TRANSITIONS table:
#
#   PROPOSED -> FORMED      (trade accepted)
#   PROPOSED -> CANCELLED   (trade rejected)
#   FORMED   -> SETTLED     (settlement complete)
#   FORMED   -> CANCELLED   (cancelled after formation)
#   SETTLED  -> CLOSED      (trade closed / expired / exercised)
#
# Any transition not in this set is an illegal state transition.

sep("STEP 6: Verify State Transition Rules")

from attestor.instrument.lifecycle import check_transition, DERIVATIVE_TRANSITIONS

# Valid transitions:
for from_s, to_s in [
    (PositionStatusEnum.PROPOSED, PositionStatusEnum.FORMED),
    (PositionStatusEnum.FORMED, PositionStatusEnum.SETTLED),
    (PositionStatusEnum.SETTLED, PositionStatusEnum.CLOSED),
]:
    result = check_transition(from_s, to_s, DERIVATIVE_TRANSITIONS)
    status = "VALID" if isinstance(result, Ok) else "INVALID"
    print(f"  {from_s.value:10s} -> {to_s.value:10s}  [{status}]")

# Invalid transitions:
for from_s, to_s in [
    (PositionStatusEnum.PROPOSED, PositionStatusEnum.SETTLED),   # Can't skip FORMED
    (PositionStatusEnum.CLOSED, PositionStatusEnum.FORMED),      # Can't reopen
]:
    result = check_transition(from_s, to_s, DERIVATIVE_TRANSITIONS)
    status = "VALID" if isinstance(result, Ok) else "INVALID"
    print(f"  {from_s.value:10s} -> {to_s.value:10s}  [{status}]")


# ============================================================================
#  STEP 7: THE PREMIUM PAYMENT (Money type)
# ============================================================================
#
# Financial arithmetic in Attestor uses the Money type with:
#   - Decimal (not float!) for exact representation
#   - Explicit currency (NonEmptyStr, validated)
#   - Banker's rounding (ROUND_HALF_EVEN) via ATTESTOR_DECIMAL_CONTEXT
#   - All operations (add, sub, mul, div) respect the Decimal context
#
# Money.create() returns Ok|Err, ensuring you never create Money with
# NaN, Infinity, or a non-Decimal amount.

sep("STEP 7: Calculate the Premium Payment")

# 10 contracts x 100 shares/contract x $12.50/share = $12,500 total premium
contracts = Decimal("10")
price_per_share = Decimal("12.50")
shares_per_contract = Decimal("100")

total_premium = contracts * shares_per_contract * price_per_share

premium_result = Money.create(amount=total_premium, currency="USD")
match premium_result:
    case Ok(premium):
        print(f"  Premium calculation:")
        print(f"    Contracts:         {contracts}")
        print(f"    Shares/contract:   {shares_per_contract}")
        print(f"    Price/share:       ${price_per_share}")
        print(f"    Total premium:     ${premium.amount} {premium.currency.value}")
    case Err(e):
        raise RuntimeError(f"Failed to create premium: {e}")

# Demonstrate Money arithmetic:
# The option has notional value = contracts x multiplier x strike
notional_value_amount = contracts * shares_per_contract * strike_price
notional_result = Money.create(amount=notional_value_amount, currency="USD")
match notional_result:
    case Ok(notional):
        print(f"    Notional value:    ${notional.amount} {notional.currency.value}")
    case Err(e):
        raise RuntimeError(f"Failed to create notional: {e}")

# Premium as percentage of notional:
pct = (total_premium / notional_value_amount) * Decimal("100")
print(f"    Premium/notional:  {pct:.2f}%")

# Round to minor unit (2 decimal places for USD):
rounded = premium.round_to_minor_unit()
print(f"    Rounded premium:   ${rounded.amount} {rounded.currency.value}")


# ============================================================================
#  SUMMARY
# ============================================================================

sep("SUMMARY: What We Built")

print("  CDM Security (NVDA)")
print(f"    ISIN:              {nvda.identifiers[0].identifier.value}")
print(f"    CUSIP:             {nvda.identifiers[1].identifier.value}")
print(f"    Type:              {nvda.instrument_type.value} ({nvda.classification.equity_type.equity_type.value})")
print(f"    Exchange:          {nvda.exchange.value} (NASDAQ)")
print()
print("  Parties")
print(f"    Buyer:             {gs.name.value} (LEI: {gs.party_id[1].identifier.value})")
print(f"    Seller:            {jpm.name.value} (LEI: {jpm.party_id[1].identifier.value})")
print()
print("  OTC Call Option")
print(f"    Underlying:        NVDA ({payout.underlying_id.value})")
print(f"    Strike:            ${payout.strike.value}")
print(f"    Expiry:            {payout.expiry_date}")
print(f"    Style:             {payout.option_style.value}")
print(f"    Settlement:        {payout.settlement_type.value}")
print(f"    Contracts:         {contracts} ({contracts * shares_per_contract} shares)")
print(f"    Premium:           ${premium.amount}")
print()
print("  Trade")
print(f"    Trade ID:          {trade.trade_id.value}")
print(f"    Status:            {formed_state.status.value}")
print(f"    Execution:         {trade.execution_type.value}")
print(f"    CDM Asset Class:   {asset_class.value if asset_class else 'Unknown'}")
print()
print("  CDM Type Hierarchy")
print("    Security -> Instrument -> Product -> EconomicTerms -> OptionPayoutSpec")
print("    Party -> PayerReceiver -> Trade -> TradeState -> BusinessEvent")
print("    CanonicalOrder (Gateway) -> ExecutePI (Lifecycle)")
print()
print("  Attestor Design Principles Demonstrated")
print("    1. Illegal states are structurally unrepresentable (sum types)")
print("    2. Every identifier is validated at creation (LEI, ISIN, CUSIP)")
print("    3. Money uses Decimal with explicit context (no floats)")
print("    4. Result types (Ok/Err) instead of exceptions")
print("    5. Immutable dataclasses (frozen=True) for all types")
print("    6. State machine transitions are explicit and verifiable")
print()
print("Done. Every object above is a CDM-aligned, validated, immutable value.")
