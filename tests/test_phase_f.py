"""Phase F: Regulatory Reporting Enrichment — tests.

Tests for:
- RestructuringEnum (new enum in derivative_types.py)
- CreditEventTypeEnum expansion (3 new members)
- TradingCapacityEnum (new enum in mifid2.py)
- MiFIDIIReport optional field additions (6 fields)
- EMIRTradeReport optional field addition (1 field)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from attestor.core.identifiers import LEI, UTI
from attestor.core.money import NonEmptyStr, PositiveDecimal
from attestor.core.types import UtcDatetime
from attestor.gateway.types import OrderSide
from attestor.instrument.derivative_types import (
    CreditEventTypeEnum,
    RestructuringEnum,
)
from attestor.reporting.emir import EMIRTradeReport
from attestor.reporting.mifid2 import MiFIDIIReport, TradingCapacityEnum

# ---------------------------------------------------------------------------
# RestructuringEnum
# ---------------------------------------------------------------------------


class TestRestructuringEnum:
    def test_member_count(self) -> None:
        assert len(RestructuringEnum) == 3

    def test_member_values(self) -> None:
        assert {e.value for e in RestructuringEnum} == {
            "ModR", "ModModR", "FullR",
        }

    def test_mod_r(self) -> None:
        assert RestructuringEnum.MOD_R.value == "ModR"

    def test_mod_mod_r(self) -> None:
        assert RestructuringEnum.MOD_MOD_R.value == "ModModR"

    def test_full_r(self) -> None:
        assert RestructuringEnum.FULL_R.value == "FullR"


# ---------------------------------------------------------------------------
# CreditEventTypeEnum expansion
# ---------------------------------------------------------------------------


class TestCreditEventTypeExpansion:
    def test_member_count(self) -> None:
        assert len(CreditEventTypeEnum) == 13

    def test_original_members_preserved(self) -> None:
        assert CreditEventTypeEnum.BANKRUPTCY.value == "Bankruptcy"
        assert CreditEventTypeEnum.FAILURE_TO_PAY.value == "FailureToPay"
        assert CreditEventTypeEnum.RESTRUCTURING.value == "Restructuring"

    def test_new_members(self) -> None:
        assert CreditEventTypeEnum.OBLIGATION_DEFAULT.value == "ObligationDefault"
        assert CreditEventTypeEnum.GOVERNMENTAL_INTERVENTION.value == "GovernmentalIntervention"
        assert CreditEventTypeEnum.REPUDIATION_MORATORIUM.value == "RepudiationMoratorium"


# ---------------------------------------------------------------------------
# TradingCapacityEnum
# ---------------------------------------------------------------------------


class TestTradingCapacityEnum:
    def test_member_count(self) -> None:
        assert len(TradingCapacityEnum) == 3

    def test_member_values(self) -> None:
        assert {e.value for e in TradingCapacityEnum} == {
            "DEAL", "MTCH", "AOTC",
        }

    def test_deal(self) -> None:
        assert TradingCapacityEnum.DEAL.value == "DEAL"

    def test_mtch(self) -> None:
        assert TradingCapacityEnum.MTCH.value == "MTCH"

    def test_aotc(self) -> None:
        assert TradingCapacityEnum.AOTC.value == "AOTC"


# ---------------------------------------------------------------------------
# MiFIDIIReport new optional fields
# ---------------------------------------------------------------------------


def _make_lei(value: str) -> LEI:
    return LEI(value=value)


def _make_mifid_report(**overrides: object) -> MiFIDIIReport:
    """Build a minimal MiFIDIIReport with sensible defaults."""
    defaults: dict[str, object] = {
        "transaction_ref": NonEmptyStr(value="TX-001"),
        "reporting_entity_lei": _make_lei("AAAABBBBCCCCDDDDEE00"),
        "counterparty_lei": _make_lei("FFFFGGGGHHHHIIIIJJ11"),
        "instrument_id": NonEmptyStr(value="INST-001"),
        "instrument_fields": None,
        "direction": OrderSide.BUY,
        "quantity": PositiveDecimal(value=Decimal("100")),
        "price": Decimal("50.00"),
        "currency": NonEmptyStr(value="USD"),
        "trade_date": date(2026, 1, 15),
        "settlement_date": date(2026, 1, 17),
        "venue": NonEmptyStr(value="XLON"),
        "report_timestamp": UtcDatetime.now(),
        "attestation_refs": ("ATT-001",),
    }
    defaults.update(overrides)
    return MiFIDIIReport(**defaults)  # type: ignore[arg-type]


class TestMiFIDIIReportPhaseF:
    def test_new_fields_default_none(self) -> None:
        report = _make_mifid_report()
        assert report.cfi_code is None
        assert report.trading_capacity is None
        assert report.investment_decision_person is None
        assert report.executing_person is None
        assert report.risk_reducing_transaction is None
        assert report.securities_financing_indicator is None

    def test_cfi_code(self) -> None:
        report = _make_mifid_report(
            cfi_code=NonEmptyStr(value="ESXXXX"),
        )
        assert report.cfi_code is not None
        assert report.cfi_code.value == "ESXXXX"

    def test_trading_capacity(self) -> None:
        report = _make_mifid_report(
            trading_capacity=TradingCapacityEnum.DEAL,
        )
        assert report.trading_capacity is TradingCapacityEnum.DEAL

    def test_investment_decision_person(self) -> None:
        report = _make_mifid_report(
            investment_decision_person=NonEmptyStr(value="TRADER-42"),
        )
        assert report.investment_decision_person is not None
        assert report.investment_decision_person.value == "TRADER-42"

    def test_executing_person(self) -> None:
        report = _make_mifid_report(
            executing_person=NonEmptyStr(value="EXEC-07"),
        )
        assert report.executing_person is not None
        assert report.executing_person.value == "EXEC-07"

    def test_risk_reducing_transaction(self) -> None:
        report = _make_mifid_report(risk_reducing_transaction=True)
        assert report.risk_reducing_transaction is True

    def test_securities_financing_indicator(self) -> None:
        report = _make_mifid_report(securities_financing_indicator=False)
        assert report.securities_financing_indicator is False

    def test_all_new_fields_set(self) -> None:
        report = _make_mifid_report(
            cfi_code=NonEmptyStr(value="ESXXXX"),
            trading_capacity=TradingCapacityEnum.MTCH,
            investment_decision_person=NonEmptyStr(value="TRADER-1"),
            executing_person=NonEmptyStr(value="EXEC-1"),
            risk_reducing_transaction=False,
            securities_financing_indicator=True,
        )
        assert report.cfi_code is not None
        assert report.trading_capacity is TradingCapacityEnum.MTCH
        assert report.investment_decision_person is not None
        assert report.executing_person is not None
        assert report.risk_reducing_transaction is False
        assert report.securities_financing_indicator is True

    def test_frozen(self) -> None:
        report = _make_mifid_report()
        with pytest.raises(AttributeError):
            report.cfi_code = NonEmptyStr(value="ESXXXX")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# EMIRTradeReport new optional field
# ---------------------------------------------------------------------------


def _make_emir_report(**overrides: object) -> EMIRTradeReport:
    """Build a minimal EMIRTradeReport with sensible defaults."""
    defaults: dict[str, object] = {
        "uti": UTI(value="AAAABBBBCCCCDDDDEE00" + "A" * 32),
        "reporting_counterparty_lei": _make_lei("AAAABBBBCCCCDDDDEE00"),
        "other_counterparty_lei": _make_lei("FFFFGGGGHHHHIIIIJJ11"),
        "instrument_id": NonEmptyStr(value="INST-001"),
        "isin": None,
        "direction": OrderSide.BUY,
        "quantity": PositiveDecimal(value=Decimal("100")),
        "price": Decimal("50.00"),
        "currency": NonEmptyStr(value="USD"),
        "trade_date": date(2026, 1, 15),
        "settlement_date": date(2026, 1, 17),
        "venue": NonEmptyStr(value="XLON"),
        "report_timestamp": UtcDatetime.now(),
        "instrument_fields": None,
        "attestation_refs": ("ATT-001",),
    }
    defaults.update(overrides)
    return EMIRTradeReport(**defaults)  # type: ignore[arg-type]


class TestEMIRTradeReportPhaseF:
    def test_risk_reducing_default_none(self) -> None:
        report = _make_emir_report()
        assert report.risk_reducing_transaction is None

    def test_risk_reducing_true(self) -> None:
        report = _make_emir_report(risk_reducing_transaction=True)
        assert report.risk_reducing_transaction is True

    def test_risk_reducing_false(self) -> None:
        report = _make_emir_report(risk_reducing_transaction=False)
        assert report.risk_reducing_transaction is False

    def test_frozen(self) -> None:
        report = _make_emir_report()
        with pytest.raises(AttributeError):
            report.risk_reducing_transaction = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Re-export checks
# ---------------------------------------------------------------------------


class TestPhaseFReExports:
    def test_restructuring_enum_from_instrument(self) -> None:
        from attestor.instrument import RestructuringEnum
        assert RestructuringEnum.MOD_R.value == "ModR"

    def test_trading_capacity_from_reporting(self) -> None:
        from attestor.reporting import TradingCapacityEnum
        assert TradingCapacityEnum.DEAL.value == "DEAL"
