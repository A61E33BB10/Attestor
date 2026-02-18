"""Tests for attestor.core.party -- CDM base-staticdata-party alignment.

Covers PartyIdentifierTypeEnum, PartyIdentifier, CounterpartyRoleEnum,
Counterparty, BuyerSeller, PartyRoleEnum, PartyRole.
"""

from __future__ import annotations

import pytest

from attestor.core.money import NonEmptyStr
from attestor.core.party import (
    BuyerSeller,
    Counterparty,
    CounterpartyRoleEnum,
    PartyIdentifier,
    PartyIdentifierTypeEnum,
    PartyRole,
    PartyRoleEnum,
)
from attestor.core.result import Err, Ok

_VALID_LEI = "529900ODI3JL1O4COU11"


# ---------------------------------------------------------------------------
# PartyIdentifierTypeEnum
# ---------------------------------------------------------------------------


class TestPartyIdentifierTypeEnum:
    def test_member_count(self) -> None:
        assert len(PartyIdentifierTypeEnum) == 3

    def test_exact_members(self) -> None:
        names = {m.name for m in PartyIdentifierTypeEnum}
        assert names == {"BIC", "LEI", "MIC"}


# ---------------------------------------------------------------------------
# CounterpartyRoleEnum
# ---------------------------------------------------------------------------


class TestCounterpartyRoleEnum:
    def test_member_count(self) -> None:
        assert len(CounterpartyRoleEnum) == 2

    def test_exact_members(self) -> None:
        names = {m.name for m in CounterpartyRoleEnum}
        assert names == {"PARTY1", "PARTY2"}


# ---------------------------------------------------------------------------
# PartyRoleEnum
# ---------------------------------------------------------------------------


class TestPartyRoleEnum:
    def test_has_equity_trade_roles(self) -> None:
        names = {m.name for m in PartyRoleEnum}
        assert "BUYER" in names
        assert "SELLER" in names
        assert "EXECUTING_BROKER" in names
        assert "CLEARING_ORGANIZATION" in names
        assert "CUSTODIAN" in names
        assert "REPORTING_PARTY" in names
        assert "SETTLEMENT_AGENT" in names

    def test_at_least_15_members(self) -> None:
        assert len(PartyRoleEnum) >= 15


# ---------------------------------------------------------------------------
# PartyIdentifier
# ---------------------------------------------------------------------------


class TestPartyIdentifier:
    def test_untyped_identifier(self) -> None:
        pid = PartyIdentifier(
            identifier=NonEmptyStr(value="P001"),
        )
        assert pid.identifier.value == "P001"
        assert pid.identifier_type is None

    def test_lei_typed_identifier(self) -> None:
        pid = PartyIdentifier(
            identifier=NonEmptyStr(value=_VALID_LEI),
            identifier_type=PartyIdentifierTypeEnum.LEI,
        )
        assert pid.identifier_type == PartyIdentifierTypeEnum.LEI

    def test_lei_validation(self) -> None:
        with pytest.raises(TypeError, match="LEI"):
            PartyIdentifier(
                identifier=NonEmptyStr(value="INVALID"),
                identifier_type=PartyIdentifierTypeEnum.LEI,
            )

    def test_create_untyped(self) -> None:
        result = PartyIdentifier.create("P001")
        assert isinstance(result, Ok)
        assert result.value.identifier.value == "P001"

    def test_create_lei(self) -> None:
        result = PartyIdentifier.create(
            _VALID_LEI, PartyIdentifierTypeEnum.LEI,
        )
        assert isinstance(result, Ok)

    def test_create_lei_invalid(self) -> None:
        result = PartyIdentifier.create(
            "BAD", PartyIdentifierTypeEnum.LEI,
        )
        assert isinstance(result, Err)

    def test_of_lei(self) -> None:
        result = PartyIdentifier.of_lei(_VALID_LEI)
        assert isinstance(result, Ok)
        assert result.value.identifier_type == PartyIdentifierTypeEnum.LEI

    def test_of_lei_invalid(self) -> None:
        result = PartyIdentifier.of_lei("BAD")
        assert isinstance(result, Err)

    def test_create_empty_rejected(self) -> None:
        result = PartyIdentifier.create("")
        assert isinstance(result, Err)

    def test_raw_string_identifier_rejected(self) -> None:
        with pytest.raises(TypeError, match="NonEmptyStr"):
            PartyIdentifier(identifier="bad")  # type: ignore[arg-type]

    def test_frozen(self) -> None:
        pid = PartyIdentifier(identifier=NonEmptyStr(value="X"))
        with pytest.raises(AttributeError):
            pid.identifier = NonEmptyStr(value="Y")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Counterparty
# ---------------------------------------------------------------------------


class TestCounterparty:
    def test_valid(self) -> None:
        cp = Counterparty(
            role=CounterpartyRoleEnum.PARTY1,
            party_id=NonEmptyStr(value="PA"),
        )
        assert cp.role == CounterpartyRoleEnum.PARTY1
        assert cp.party_id.value == "PA"

    def test_invalid_role_type(self) -> None:
        with pytest.raises(TypeError, match="CounterpartyRoleEnum"):
            Counterparty(
                role="PARTY1",  # type: ignore[arg-type]
                party_id=NonEmptyStr(value="PA"),
            )

    def test_frozen(self) -> None:
        cp = Counterparty(
            role=CounterpartyRoleEnum.PARTY1,
            party_id=NonEmptyStr(value="PA"),
        )
        with pytest.raises(AttributeError):
            cp.role = CounterpartyRoleEnum.PARTY2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# BuyerSeller
# ---------------------------------------------------------------------------


class TestBuyerSeller:
    def test_valid(self) -> None:
        bs = BuyerSeller(
            buyer=CounterpartyRoleEnum.PARTY1,
            seller=CounterpartyRoleEnum.PARTY2,
        )
        assert bs.buyer == CounterpartyRoleEnum.PARTY1
        assert bs.seller == CounterpartyRoleEnum.PARTY2

    def test_reversed(self) -> None:
        bs = BuyerSeller(
            buyer=CounterpartyRoleEnum.PARTY2,
            seller=CounterpartyRoleEnum.PARTY1,
        )
        assert bs.buyer == CounterpartyRoleEnum.PARTY2

    def test_same_role_rejected(self) -> None:
        with pytest.raises(TypeError, match="must differ"):
            BuyerSeller(
                buyer=CounterpartyRoleEnum.PARTY1,
                seller=CounterpartyRoleEnum.PARTY1,
            )

    def test_invalid_type_rejected(self) -> None:
        with pytest.raises(TypeError, match="CounterpartyRoleEnum"):
            BuyerSeller(
                buyer="PARTY1",  # type: ignore[arg-type]
                seller=CounterpartyRoleEnum.PARTY2,
            )

    def test_frozen(self) -> None:
        bs = BuyerSeller(
            buyer=CounterpartyRoleEnum.PARTY1,
            seller=CounterpartyRoleEnum.PARTY2,
        )
        with pytest.raises(AttributeError):
            bs.buyer = CounterpartyRoleEnum.PARTY2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PartyRole
# ---------------------------------------------------------------------------


class TestPartyRole:
    def test_valid(self) -> None:
        pr = PartyRole(
            party_id=NonEmptyStr(value="PA"),
            role=PartyRoleEnum.BUYER,
        )
        assert pr.role == PartyRoleEnum.BUYER
        assert pr.party_id.value == "PA"

    def test_invalid_role_type(self) -> None:
        with pytest.raises(TypeError, match="PartyRoleEnum"):
            PartyRole(
                party_id=NonEmptyStr(value="PA"),
                role="BUYER",  # type: ignore[arg-type]
            )

    def test_frozen(self) -> None:
        pr = PartyRole(
            party_id=NonEmptyStr(value="PA"),
            role=PartyRoleEnum.SELLER,
        )
        with pytest.raises(AttributeError):
            pr.role = PartyRoleEnum.BUYER  # type: ignore[misc]
