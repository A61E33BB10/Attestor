"""Tests for attestor.instrument.derivative_types and factory functions."""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal

import pytest

from attestor.core.result import Err, Ok, unwrap
from attestor.instrument.derivative_types import (
    EquityDetail,
    FuturesDetail,
    FuturesPayoutSpec,
    MarginType,
    OptionDetail,
    OptionPayoutSpec,
    OptionStyle,
    OptionType,
    SettlementType,
)
from attestor.instrument.types import (
    EconomicTerms,
    EquityPayoutSpec,
    Party,
    create_futures_instrument,
    create_option_instrument,
)

_LEI = "529900HNOAA1KXQJUQ27"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_option_type_values(self) -> None:
        assert {e.value for e in OptionType} == {"CALL", "PUT"}

    def test_option_style_values(self) -> None:
        assert {e.value for e in OptionStyle} == {"EUROPEAN", "AMERICAN"}

    def test_settlement_type_values(self) -> None:
        assert {e.value for e in SettlementType} == {"PHYSICAL", "CASH"}

    def test_margin_type_values(self) -> None:
        assert {e.value for e in MarginType} == {"VARIATION", "INITIAL"}


# ---------------------------------------------------------------------------
# OptionPayoutSpec
# ---------------------------------------------------------------------------


class TestOptionPayoutSpec:
    def test_create_valid(self) -> None:
        result = OptionPayoutSpec.create(
            underlying_id="AAPL", strike=Decimal("150"),
            expiry_date=date(2025, 12, 19), option_type=OptionType.CALL,
            option_style=OptionStyle.AMERICAN,
            settlement_type=SettlementType.PHYSICAL,
            currency="USD", exchange="CBOE",
        )
        assert isinstance(result, Ok)
        spec = unwrap(result)
        assert spec.underlying_id.value == "AAPL"
        assert spec.strike.value == Decimal("150")
        assert spec.option_type == OptionType.CALL
        assert spec.multiplier.value == Decimal("100")

    def test_create_custom_multiplier(self) -> None:
        result = OptionPayoutSpec.create(
            underlying_id="SPX", strike=Decimal("5000"),
            expiry_date=date(2025, 12, 19), option_type=OptionType.PUT,
            option_style=OptionStyle.EUROPEAN,
            settlement_type=SettlementType.CASH,
            currency="USD", exchange="CBOE", multiplier=Decimal("1"),
        )
        assert isinstance(result, Ok)
        assert unwrap(result).multiplier.value == Decimal("1")

    def test_create_empty_underlying_err(self) -> None:
        result = OptionPayoutSpec.create(
            underlying_id="", strike=Decimal("150"),
            expiry_date=date(2025, 12, 19), option_type=OptionType.CALL,
            option_style=OptionStyle.AMERICAN,
            settlement_type=SettlementType.PHYSICAL,
            currency="USD", exchange="CBOE",
        )
        assert isinstance(result, Err)
        assert "underlying_id" in result.error

    def test_create_zero_strike_err(self) -> None:
        result = OptionPayoutSpec.create(
            underlying_id="AAPL", strike=Decimal("0"),
            expiry_date=date(2025, 12, 19), option_type=OptionType.CALL,
            option_style=OptionStyle.AMERICAN,
            settlement_type=SettlementType.PHYSICAL,
            currency="USD", exchange="CBOE",
        )
        assert isinstance(result, Err)
        assert "strike" in result.error

    def test_create_empty_currency_err(self) -> None:
        result = OptionPayoutSpec.create(
            underlying_id="AAPL", strike=Decimal("150"),
            expiry_date=date(2025, 12, 19), option_type=OptionType.CALL,
            option_style=OptionStyle.AMERICAN,
            settlement_type=SettlementType.PHYSICAL,
            currency="", exchange="CBOE",
        )
        assert isinstance(result, Err)

    def test_frozen(self) -> None:
        spec = unwrap(OptionPayoutSpec.create(
            underlying_id="AAPL", strike=Decimal("150"),
            expiry_date=date(2025, 12, 19), option_type=OptionType.CALL,
            option_style=OptionStyle.AMERICAN,
            settlement_type=SettlementType.PHYSICAL,
            currency="USD", exchange="CBOE",
        ))
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.option_type = OptionType.PUT  # type: ignore[misc]


# ---------------------------------------------------------------------------
# FuturesPayoutSpec
# ---------------------------------------------------------------------------


class TestFuturesPayoutSpec:
    def test_create_valid(self) -> None:
        result = FuturesPayoutSpec.create(
            underlying_id="ES", expiry_date=date(2025, 12, 19),
            last_trading_date=date(2025, 12, 18),
            settlement_type=SettlementType.CASH,
            contract_size=Decimal("50"), currency="USD", exchange="CME",
        )
        assert isinstance(result, Ok)
        spec = unwrap(result)
        assert spec.underlying_id.value == "ES"
        assert spec.contract_size.value == Decimal("50")

    def test_last_trading_date_after_expiry_err(self) -> None:
        result = FuturesPayoutSpec.create(
            underlying_id="ES", expiry_date=date(2025, 12, 19),
            last_trading_date=date(2025, 12, 20),
            settlement_type=SettlementType.CASH,
            contract_size=Decimal("50"), currency="USD", exchange="CME",
        )
        assert isinstance(result, Err)
        assert "last_trading_date" in result.error

    def test_last_trading_date_equals_expiry_ok(self) -> None:
        result = FuturesPayoutSpec.create(
            underlying_id="ES", expiry_date=date(2025, 12, 19),
            last_trading_date=date(2025, 12, 19),
            settlement_type=SettlementType.CASH,
            contract_size=Decimal("50"), currency="USD", exchange="CME",
        )
        assert isinstance(result, Ok)

    def test_create_empty_underlying_err(self) -> None:
        result = FuturesPayoutSpec.create(
            underlying_id="", expiry_date=date(2025, 12, 19),
            last_trading_date=date(2025, 12, 18),
            settlement_type=SettlementType.CASH,
            contract_size=Decimal("50"), currency="USD", exchange="CME",
        )
        assert isinstance(result, Err)

    def test_frozen(self) -> None:
        spec = unwrap(FuturesPayoutSpec.create(
            underlying_id="ES", expiry_date=date(2025, 12, 19),
            last_trading_date=date(2025, 12, 18),
            settlement_type=SettlementType.CASH,
            contract_size=Decimal("50"), currency="USD", exchange="CME",
        ))
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.contract_size = unwrap(  # type: ignore[misc]
                __import__("attestor.core.money", fromlist=["PositiveDecimal"])
                .PositiveDecimal.parse(Decimal("100"))
            )


# ---------------------------------------------------------------------------
# InstrumentDetail types
# ---------------------------------------------------------------------------


class TestEquityDetail:
    def test_marker_type(self) -> None:
        ed = EquityDetail()
        assert isinstance(ed, EquityDetail)

    def test_no_dict_with_slots(self) -> None:
        ed = EquityDetail()
        with pytest.raises(AttributeError):
            ed.__dict__  # noqa: B018


class TestOptionDetail:
    def test_create_valid(self) -> None:
        result = OptionDetail.create(
            strike=Decimal("150"), expiry_date=date(2025, 12, 19),
            option_type=OptionType.CALL, option_style=OptionStyle.AMERICAN,
            settlement_type=SettlementType.PHYSICAL, underlying_id="AAPL",
        )
        assert isinstance(result, Ok)
        od = unwrap(result)
        assert od.option_type == OptionType.CALL
        assert od.multiplier.value == Decimal("100")

    def test_create_zero_strike_err(self) -> None:
        result = OptionDetail.create(
            strike=Decimal("0"), expiry_date=date(2025, 12, 19),
            option_type=OptionType.CALL, option_style=OptionStyle.AMERICAN,
            settlement_type=SettlementType.PHYSICAL, underlying_id="AAPL",
        )
        assert isinstance(result, Err)

    def test_create_empty_underlying_err(self) -> None:
        result = OptionDetail.create(
            strike=Decimal("150"), expiry_date=date(2025, 12, 19),
            option_type=OptionType.CALL, option_style=OptionStyle.AMERICAN,
            settlement_type=SettlementType.PHYSICAL, underlying_id="",
        )
        assert isinstance(result, Err)


class TestFuturesDetail:
    def test_create_valid(self) -> None:
        result = FuturesDetail.create(
            expiry_date=date(2025, 12, 19), contract_size=Decimal("50"),
            settlement_type=SettlementType.CASH, underlying_id="ES",
        )
        assert isinstance(result, Ok)
        fd = unwrap(result)
        assert fd.underlying_id.value == "ES"

    def test_create_zero_contract_size_err(self) -> None:
        result = FuturesDetail.create(
            expiry_date=date(2025, 12, 19), contract_size=Decimal("0"),
            settlement_type=SettlementType.CASH, underlying_id="ES",
        )
        assert isinstance(result, Err)


class TestInstrumentDetailPatternMatch:
    def test_exhaustive_match(self) -> None:
        details: list[EquityDetail | OptionDetail | FuturesDetail] = [
            EquityDetail(),
            unwrap(OptionDetail.create(
                strike=Decimal("150"), expiry_date=date(2025, 12, 19),
                option_type=OptionType.CALL, option_style=OptionStyle.AMERICAN,
                settlement_type=SettlementType.PHYSICAL, underlying_id="AAPL",
            )),
            unwrap(FuturesDetail.create(
                expiry_date=date(2025, 12, 19), contract_size=Decimal("50"),
                settlement_type=SettlementType.CASH, underlying_id="ES",
            )),
        ]
        for d in details:
            match d:
                case EquityDetail():
                    pass
                case OptionDetail():
                    pass
                case FuturesDetail():
                    pass


# ---------------------------------------------------------------------------
# EconomicTerms Payout union
# ---------------------------------------------------------------------------


class TestPayoutUnion:
    def test_equity_payout(self) -> None:
        payout = unwrap(EquityPayoutSpec.create("AAPL", "USD", "XNYS"))
        terms = EconomicTerms(payout=payout, effective_date=date(2025, 6, 15),
                              termination_date=None)
        assert isinstance(terms.payout, EquityPayoutSpec)

    def test_option_payout(self) -> None:
        payout = unwrap(OptionPayoutSpec.create(
            underlying_id="AAPL", strike=Decimal("150"),
            expiry_date=date(2025, 12, 19), option_type=OptionType.CALL,
            option_style=OptionStyle.AMERICAN,
            settlement_type=SettlementType.PHYSICAL,
            currency="USD", exchange="CBOE",
        ))
        terms = EconomicTerms(payout=payout, effective_date=date(2025, 6, 15),
                              termination_date=date(2025, 12, 19))
        assert isinstance(terms.payout, OptionPayoutSpec)

    def test_futures_payout(self) -> None:
        payout = unwrap(FuturesPayoutSpec.create(
            underlying_id="ES", expiry_date=date(2025, 12, 19),
            last_trading_date=date(2025, 12, 18),
            settlement_type=SettlementType.CASH,
            contract_size=Decimal("50"), currency="USD", exchange="CME",
        ))
        terms = EconomicTerms(payout=payout, effective_date=date(2025, 6, 15),
                              termination_date=date(2025, 12, 19))
        assert isinstance(terms.payout, FuturesPayoutSpec)


# ---------------------------------------------------------------------------
# Instrument factory functions
# ---------------------------------------------------------------------------


class TestCreateOptionInstrument:
    def test_valid(self) -> None:
        party = unwrap(Party.create("P001", "Acme Corp", _LEI))
        result = create_option_instrument(
            instrument_id="AAPL251219C00150000",
            underlying_id="AAPL", strike=Decimal("150"),
            expiry_date=date(2025, 12, 19), option_type=OptionType.CALL,
            option_style=OptionStyle.AMERICAN,
            settlement_type=SettlementType.PHYSICAL,
            currency="USD", exchange="CBOE",
            parties=(party,), trade_date=date(2025, 6, 15),
        )
        assert isinstance(result, Ok)
        inst = unwrap(result)
        assert isinstance(inst.product.economic_terms.payout, OptionPayoutSpec)
        assert inst.product.economic_terms.termination_date == date(2025, 12, 19)

    def test_empty_instrument_id_err(self) -> None:
        party = unwrap(Party.create("P001", "Acme Corp", _LEI))
        result = create_option_instrument(
            instrument_id="", underlying_id="AAPL", strike=Decimal("150"),
            expiry_date=date(2025, 12, 19), option_type=OptionType.CALL,
            option_style=OptionStyle.AMERICAN,
            settlement_type=SettlementType.PHYSICAL,
            currency="USD", exchange="CBOE",
            parties=(party,), trade_date=date(2025, 6, 15),
        )
        assert isinstance(result, Err)

    def test_invalid_strike_err(self) -> None:
        party = unwrap(Party.create("P001", "Acme Corp", _LEI))
        result = create_option_instrument(
            instrument_id="OPT-1", underlying_id="AAPL", strike=Decimal("-10"),
            expiry_date=date(2025, 12, 19), option_type=OptionType.CALL,
            option_style=OptionStyle.AMERICAN,
            settlement_type=SettlementType.PHYSICAL,
            currency="USD", exchange="CBOE",
            parties=(party,), trade_date=date(2025, 6, 15),
        )
        assert isinstance(result, Err)


class TestCreateFuturesInstrument:
    def test_valid(self) -> None:
        party = unwrap(Party.create("P001", "Acme Corp", _LEI))
        result = create_futures_instrument(
            instrument_id="ESZ5", underlying_id="ES",
            expiry_date=date(2025, 12, 19),
            last_trading_date=date(2025, 12, 18),
            settlement_type=SettlementType.CASH,
            contract_size=Decimal("50"), currency="USD", exchange="CME",
            parties=(party,), trade_date=date(2025, 6, 15),
        )
        assert isinstance(result, Ok)
        inst = unwrap(result)
        assert isinstance(inst.product.economic_terms.payout, FuturesPayoutSpec)
        assert inst.product.economic_terms.termination_date == date(2025, 12, 19)

    def test_empty_instrument_id_err(self) -> None:
        party = unwrap(Party.create("P001", "Acme Corp", _LEI))
        result = create_futures_instrument(
            instrument_id="", underlying_id="ES",
            expiry_date=date(2025, 12, 19),
            last_trading_date=date(2025, 12, 18),
            settlement_type=SettlementType.CASH,
            contract_size=Decimal("50"), currency="USD", exchange="CME",
            parties=(party,), trade_date=date(2025, 6, 15),
        )
        assert isinstance(result, Err)

    def test_last_trading_after_expiry_err(self) -> None:
        party = unwrap(Party.create("P001", "Acme Corp", _LEI))
        result = create_futures_instrument(
            instrument_id="ESZ5", underlying_id="ES",
            expiry_date=date(2025, 12, 19),
            last_trading_date=date(2025, 12, 25),
            settlement_type=SettlementType.CASH,
            contract_size=Decimal("50"), currency="USD", exchange="CME",
            parties=(party,), trade_date=date(2025, 6, 15),
        )
        assert isinstance(result, Err)
