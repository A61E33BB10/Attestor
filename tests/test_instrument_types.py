"""Tests for attestor.instrument.types — Party, EquityPayoutSpec, Instrument, etc."""

from __future__ import annotations

from datetime import date

from attestor.core.result import Err, Ok, unwrap
from attestor.core.serialization import canonical_bytes
from attestor.instrument.types import (
    EquityPayoutSpec,
    Party,
    PositionStatusEnum,
    create_equity_instrument,
)

_LEI = "529900HNOAA1KXQJUQ27"


class TestParty:
    def test_valid_creation(self) -> None:
        result = Party.create("P001", "Acme Corp", _LEI)
        assert isinstance(result, Ok)
        assert result.value.party_id.value == "P001"
        assert result.value.name.value == "Acme Corp"

    def test_empty_party_id(self) -> None:
        result = Party.create("", "Acme Corp", _LEI)
        assert isinstance(result, Err)

    def test_empty_name(self) -> None:
        result = Party.create("P001", "", _LEI)
        assert isinstance(result, Err)

    def test_invalid_lei(self) -> None:
        result = Party.create("P001", "Acme Corp", "INVALID")
        assert isinstance(result, Err)


class TestEquityPayoutSpec:
    def test_valid_creation(self) -> None:
        result = EquityPayoutSpec.create("AAPL", "USD", "XNYS")
        assert isinstance(result, Ok)
        assert result.value.instrument_id.value == "AAPL"

    def test_empty_instrument_id(self) -> None:
        result = EquityPayoutSpec.create("", "USD", "XNYS")
        assert isinstance(result, Err)

    def test_empty_currency(self) -> None:
        result = EquityPayoutSpec.create("AAPL", "", "XNYS")
        assert isinstance(result, Err)


class TestInstrument:
    def test_create_equity_instrument(self) -> None:
        party = unwrap(Party.create("P001", "Acme Corp", _LEI))
        result = create_equity_instrument(
            instrument_id="AAPL",
            currency="USD",
            exchange="XNYS",
            parties=(party,),
            trade_date=date(2025, 6, 15),
        )
        assert isinstance(result, Ok)
        inst = result.value
        assert inst.instrument_id.value == "AAPL"
        assert inst.status is PositionStatusEnum.PROPOSED
        assert inst.product.economic_terms.termination_date is None
        assert len(inst.parties) == 1

    def test_instrument_frozen(self) -> None:
        import dataclasses

        import pytest
        party = unwrap(Party.create("P001", "Acme Corp", _LEI))
        inst = unwrap(create_equity_instrument("AAPL", "USD", "XNYS", (party,), date(2025, 6, 15)))
        with pytest.raises(dataclasses.FrozenInstanceError):
            inst.status = PositionStatusEnum.FORMED  # type: ignore[misc]

    def test_instrument_serialization(self) -> None:
        party = unwrap(Party.create("P001", "Acme Corp", _LEI))
        inst = unwrap(create_equity_instrument("AAPL", "USD", "XNYS", (party,), date(2025, 6, 15)))
        b1 = unwrap(canonical_bytes(inst))
        b2 = unwrap(canonical_bytes(inst))
        assert b1 == b2

    def test_invalid_instrument_id(self) -> None:
        party = unwrap(Party.create("P001", "Acme Corp", _LEI))
        result = create_equity_instrument("", "USD", "XNYS", (party,), date(2025, 6, 15))
        assert isinstance(result, Err)


class TestPositionStatusEnum:
    def test_all_values(self) -> None:
        expected = {"Proposed", "Formed", "Settled", "Cancelled", "Closed"}
        actual = {s.value for s in PositionStatusEnum}
        assert actual == expected
