"""CDM base-staticdata-party -- Party, Counterparty, and role types.

Aligned with ISDA CDM Rosetta (base-staticdata-party-*):
  Party = partyId (1..*) + name (0..1)
  PartyIdentifier = identifier + identifierType
  Counterparty = role (CounterpartyRoleEnum) + partyReference
  BuyerSeller = buyer + seller (both CounterpartyRoleEnum)
  PartyRole = partyReference + role (PartyRoleEnum)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import final

from attestor.core.identifiers import LEI
from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, Ok

# ---------------------------------------------------------------------------
# Enums  (CDM Rosetta: base-staticdata-party-enum.rosetta)
# ---------------------------------------------------------------------------


class PartyIdentifierTypeEnum(Enum):
    """Identifier scheme for a party.

    CDM: PartyIdentifierTypeEnum (exact 3 members).
    """

    BIC = "BIC"
    LEI = "LEI"
    MIC = "MIC"


class CounterpartyRoleEnum(Enum):
    """Abstract party roles in a bilateral transaction.

    CDM: CounterpartyRoleEnum (exact 2 members).
    """

    PARTY1 = "Party1"
    PARTY2 = "Party2"


class PartyRoleEnum(Enum):
    """Role a party plays in a transaction.

    CDM: PartyRoleEnum (57 values).  Attestor models the equity-trade
    critical subset; expand as needed.
    """

    ACCOUNTANT = "Accountant"
    BENEFICIARY = "Beneficiary"
    BENEFICIAL_OWNER = "BeneficialOwner"
    BOOKING_PARTY = "BookingParty"
    BUYER = "Buyer"
    BUYER_DECISION_MAKER = "BuyerDecisionMaker"
    CLEARING_CLIENT = "ClearingClient"
    CLEARING_FIRM = "ClearingFirm"
    CLEARING_ORGANIZATION = "ClearingOrganization"
    CLIENT = "Client"
    CLIENT_DECISION_MAKER = "ClientDecisionMaker"
    COUNTERPARTY = "Counterparty"
    CUSTODIAN = "Custodian"
    DATA_SUBMITTER = "DataSubmitter"
    EXECUTING_BROKER = "ExecutingBroker"
    EXECUTING_ENTITY = "ExecutingEntity"
    EXECUTION_FACILITY = "ExecutionFacility"
    REPORTING_PARTY = "ReportingParty"
    SELLER = "Seller"
    SELLER_DECISION_MAKER = "SellerDecisionMaker"
    SETTLEMENT_AGENT = "SettlementAgent"
    TRADE_SOURCE = "TradeSource"


# ---------------------------------------------------------------------------
# PartyIdentifier  (CDM Rosetta: base-staticdata-party-type.rosetta)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class PartyIdentifier:
    """A single identifier for a party (e.g. LEI, BIC, MIC).

    CDM: PartyIdentifier = identifier (1..1) + identifierType (0..1).
    LEI values are cross-validated via ``LEI.parse()``.
    """

    identifier: NonEmptyStr
    identifier_type: PartyIdentifierTypeEnum | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identifier, NonEmptyStr):
            raise TypeError(
                f"PartyIdentifier.identifier must be NonEmptyStr, "
                f"got {type(self.identifier).__name__}"
            )
        if (
            self.identifier_type is not None
            and not isinstance(self.identifier_type, PartyIdentifierTypeEnum)
        ):
            raise TypeError(
                f"PartyIdentifier.identifier_type must be "
                f"PartyIdentifierTypeEnum, "
                f"got {type(self.identifier_type).__name__}"
            )
        if self.identifier_type == PartyIdentifierTypeEnum.LEI:
            match LEI.parse(self.identifier.value):
                case Err(e):
                    raise TypeError(
                        f"PartyIdentifier LEI validation: {e}"
                    )
                case Ok(_):
                    pass

    @staticmethod
    def create(
        identifier: str,
        identifier_type: PartyIdentifierTypeEnum | None = None,
    ) -> Ok[PartyIdentifier] | Err[str]:
        """Smart constructor returning Ok | Err."""
        match NonEmptyStr.parse(identifier):
            case Err(e):
                return Err(f"PartyIdentifier.identifier: {e}")
            case Ok(ident):
                pass
        if identifier_type == PartyIdentifierTypeEnum.LEI:
            match LEI.parse(ident.value):
                case Err(e):
                    return Err(f"PartyIdentifier LEI validation: {e}")
                case Ok(_):
                    pass
        return Ok(PartyIdentifier(
            identifier=ident, identifier_type=identifier_type,
        ))

    @staticmethod
    def of_lei(lei_value: str) -> Ok[PartyIdentifier] | Err[str]:
        """Create a PartyIdentifier with LEI type."""
        return PartyIdentifier.create(lei_value, PartyIdentifierTypeEnum.LEI)


# ---------------------------------------------------------------------------
# Counterparty  (CDM Rosetta: base-staticdata-party-type.rosetta)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class Counterparty:
    """Binds an abstract role to an actual party reference.

    CDM: Counterparty = role (1..1) + partyReference (1..1).
    Maps abstract PARTY1/PARTY2 to actual Party objects.
    """

    role: CounterpartyRoleEnum
    party_id: NonEmptyStr  # Reference key to a Party

    def __post_init__(self) -> None:
        if not isinstance(self.role, CounterpartyRoleEnum):
            raise TypeError(
                f"Counterparty.role must be CounterpartyRoleEnum, "
                f"got {type(self.role).__name__}"
            )
        if not isinstance(self.party_id, NonEmptyStr):
            raise TypeError(
                f"Counterparty.party_id must be NonEmptyStr, "
                f"got {type(self.party_id).__name__}"
            )


# ---------------------------------------------------------------------------
# BuyerSeller  (CDM Rosetta: base-staticdata-party-type.rosetta)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class BuyerSeller:
    """Which counterparty is buyer vs. seller.

    CDM: BuyerSeller = buyer + seller (both CounterpartyRoleEnum).
    Invariant: buyer != seller.
    """

    buyer: CounterpartyRoleEnum
    seller: CounterpartyRoleEnum

    def __post_init__(self) -> None:
        if not isinstance(self.buyer, CounterpartyRoleEnum):
            raise TypeError(
                f"BuyerSeller.buyer must be CounterpartyRoleEnum, "
                f"got {type(self.buyer).__name__}"
            )
        if not isinstance(self.seller, CounterpartyRoleEnum):
            raise TypeError(
                f"BuyerSeller.seller must be CounterpartyRoleEnum, "
                f"got {type(self.seller).__name__}"
            )
        if self.buyer == self.seller:
            raise TypeError(
                f"BuyerSeller: buyer must differ from seller, "
                f"both are {self.buyer!r}"
            )


# ---------------------------------------------------------------------------
# PartyRole  (CDM Rosetta: base-staticdata-party-type.rosetta)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class PartyRole:
    """Associates a party with a role in a transaction.

    CDM: PartyRole = partyReference (1..1) + role (1..1)
         + ownershipPartyReference (0..1).
    """

    party_id: NonEmptyStr  # Reference key to a Party
    role: PartyRoleEnum
    ownership_party_id: NonEmptyStr | None = None  # 0..1

    def __post_init__(self) -> None:
        if not isinstance(self.party_id, NonEmptyStr):
            raise TypeError(
                f"PartyRole.party_id must be NonEmptyStr, "
                f"got {type(self.party_id).__name__}"
            )
        if not isinstance(self.role, PartyRoleEnum):
            raise TypeError(
                f"PartyRole.role must be PartyRoleEnum, "
                f"got {type(self.role).__name__}"
            )
        if (
            self.ownership_party_id is not None
            and not isinstance(self.ownership_party_id, NonEmptyStr)
        ):
            raise TypeError(
                f"PartyRole.ownership_party_id must be NonEmptyStr or None, "
                f"got {type(self.ownership_party_id).__name__}"
            )
