"""Tests for attestor.instrument.asset -- CDM asset taxonomy."""

from __future__ import annotations

from attestor.core.result import Err, Ok, unwrap
from attestor.instrument.asset import (
    VALID_EXCHANGE_MICS,
    Asset,
    AssetIdentifier,
    AssetIdTypeEnum,
    DepositaryReceiptTypeEnum,
    EquityClassification,
    EquityType,
    EquityTypeEnum,
    FundClassification,
    FundProductTypeEnum,
    InstrumentTypeEnum,
    Security,
    create_equity_security,
    create_fund_security,
)

# ---------------------------------------------------------------------------
# Enum counts and members
# ---------------------------------------------------------------------------


class TestAssetIdTypeEnum:
    def test_member_count(self) -> None:
        assert len(AssetIdTypeEnum) == 18

    def test_members(self) -> None:
        names = {m.name for m in AssetIdTypeEnum}
        assert names == {
            "BBGID", "BBGTICKER", "CUSIP", "FIGI", "ISDACRP", "ISIN",
            "NAME", "REDID", "RIC", "OTHER", "SICOVAM", "SEDOL",
            "UPI", "VALOREN", "WERTPAPIER",
            "CURRENCY_CODE", "EXCHANGE_CODE", "CLEARING_CODE",
        }


class TestEquityTypeEnum:
    def test_member_count(self) -> None:
        assert len(EquityTypeEnum) == 4

    def test_members(self) -> None:
        names = {m.name for m in EquityTypeEnum}
        assert names == {
            "ORDINARY", "NON_CONVERTIBLE_PREFERENCE",
            "DEPOSITARY_RECEIPT", "CONVERTIBLE_PREFERENCE",
        }


class TestDepositaryReceiptTypeEnum:
    def test_member_count(self) -> None:
        assert len(DepositaryReceiptTypeEnum) == 4

    def test_members(self) -> None:
        names = {m.name for m in DepositaryReceiptTypeEnum}
        assert names == {"ADR", "GDR", "IDR", "EDR"}


class TestInstrumentTypeEnum:
    def test_member_count(self) -> None:
        assert len(InstrumentTypeEnum) == 7

    def test_members(self) -> None:
        names = {m.name for m in InstrumentTypeEnum}
        assert names == {
            "DEBT", "EQUITY", "FUND", "WARRANT",
            "CERTIFICATE", "LETTER_OF_CREDIT", "LISTED_DERIVATIVE",
        }


class TestFundProductTypeEnum:
    def test_member_count(self) -> None:
        assert len(FundProductTypeEnum) == 4

    def test_members(self) -> None:
        names = {m.name for m in FundProductTypeEnum}
        assert names == {
            "MONEY_MARKET_FUND", "EXCHANGE_TRADED_FUND",
            "MUTUAL_FUND", "OTHER_FUND",
        }


# ---------------------------------------------------------------------------
# AssetIdentifier
# ---------------------------------------------------------------------------


class TestAssetIdentifier:
    def test_valid_isin(self) -> None:
        result = AssetIdentifier.create("US67066G1040", AssetIdTypeEnum.ISIN)
        assert isinstance(result, Ok)
        aid = result.value
        assert aid.identifier.value == "US67066G1040"
        assert aid.identifier_type == AssetIdTypeEnum.ISIN

    def test_valid_cusip(self) -> None:
        result = AssetIdentifier.create("67066G104", AssetIdTypeEnum.CUSIP)
        assert isinstance(result, Ok)

    def test_valid_other(self) -> None:
        result = AssetIdentifier.create("NVDA.OQ", AssetIdTypeEnum.OTHER)
        assert isinstance(result, Ok)

    def test_empty_rejected(self) -> None:
        result = AssetIdentifier.create("", AssetIdTypeEnum.OTHER)
        assert isinstance(result, Err)

    def test_isin_luhn_validated(self) -> None:
        result = AssetIdentifier.create("US67066G1049", AssetIdTypeEnum.ISIN)
        assert isinstance(result, Err)
        assert "ISIN" in result.error

    def test_cusip_length(self) -> None:
        result = AssetIdentifier.create("67066G10", AssetIdTypeEnum.CUSIP)
        assert isinstance(result, Err)
        assert "CUSIP" in result.error

    def test_sedol_length(self) -> None:
        result = AssetIdentifier.create("BZ4B", AssetIdTypeEnum.SEDOL)
        assert isinstance(result, Err)
        assert "SEDOL" in result.error

    def test_frozen(self) -> None:
        aid = unwrap(AssetIdentifier.create("US67066G1040", AssetIdTypeEnum.ISIN))
        try:
            aid.identifier_type = AssetIdTypeEnum.CUSIP  # type: ignore[misc]
            assert False, "should be frozen"  # noqa: B011
        except AttributeError:
            pass

    def test_direct_constructor_validates_isin(self) -> None:
        """__post_init__ rejects invalid ISIN even when bypassing create()."""
        import pytest

        from attestor.core.money import NonEmptyStr

        with pytest.raises(TypeError, match="ISIN"):
            AssetIdentifier(
                identifier=NonEmptyStr(value="US67066G1049"),
                identifier_type=AssetIdTypeEnum.ISIN,
            )

    def test_direct_constructor_validates_cusip(self) -> None:
        import pytest

        from attestor.core.money import NonEmptyStr

        with pytest.raises(TypeError, match="CUSIP"):
            AssetIdentifier(
                identifier=NonEmptyStr(value="XX"),
                identifier_type=AssetIdTypeEnum.CUSIP,
            )


# ---------------------------------------------------------------------------
# EquityType
# ---------------------------------------------------------------------------


class TestEquityType:
    def test_construction(self) -> None:
        et = EquityType(equity_type=EquityTypeEnum.ORDINARY)
        assert et.equity_type == EquityTypeEnum.ORDINARY
        assert et.depositary_receipt is None

    def test_frozen(self) -> None:
        et = EquityType(equity_type=EquityTypeEnum.ORDINARY)
        try:
            et.equity_type = EquityTypeEnum.DEPOSITARY_RECEIPT  # type: ignore[misc]
            assert False, "should be frozen"  # noqa: B011
        except AttributeError:
            pass

    def test_depositary_receipt_valid(self) -> None:
        """CDM: depositaryReceipt valid when equityType == DEPOSITARY_RECEIPT."""
        et = EquityType(
            equity_type=EquityTypeEnum.DEPOSITARY_RECEIPT,
            depositary_receipt=DepositaryReceiptTypeEnum.ADR,
        )
        assert et.depositary_receipt == DepositaryReceiptTypeEnum.ADR

    def test_depositary_receipt_invalid_combination(self) -> None:
        """CDM condition: depositaryReceipt absent when equityType != DEPOSITARY_RECEIPT."""
        import pytest

        with pytest.raises(TypeError, match="depositary_receipt"):
            EquityType(
                equity_type=EquityTypeEnum.ORDINARY,
                depositary_receipt=DepositaryReceiptTypeEnum.GDR,
            )

    def test_depositary_receipt_without_subtype(self) -> None:
        """DEPOSITARY_RECEIPT equity_type without specific DR type is valid."""
        et = EquityType(equity_type=EquityTypeEnum.DEPOSITARY_RECEIPT)
        assert et.depositary_receipt is None


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------


def _nvda_ids() -> tuple[AssetIdentifier, ...]:
    return (
        unwrap(AssetIdentifier.create("US67066G1040", AssetIdTypeEnum.ISIN)),
        unwrap(AssetIdentifier.create("67066G104", AssetIdTypeEnum.CUSIP)),
    )


class TestSecurity:
    def test_valid_equity(self) -> None:
        result = Security.create(
            identifiers=_nvda_ids(),
            classification=EquityClassification(
                equity_type=EquityType(equity_type=EquityTypeEnum.ORDINARY),
            ),
            currency="USD",
            exchange="XNAS",
        )
        assert isinstance(result, Ok)
        sec = result.value
        assert sec.instrument_type == InstrumentTypeEnum.EQUITY
        assert sec.is_exchange_listed is True

    def test_nvda_golden(self) -> None:
        """NVDA share: ISIN + CUSIP, ordinary equity, XNAS listed, USD."""
        nvda = unwrap(create_equity_security(
            isin="US67066G1040",
            cusip="67066G104",
            equity_type=EquityTypeEnum.ORDINARY,
            exchange="XNAS",
            currency="USD",
        ))
        assert nvda.identifiers[0].identifier.value == "US67066G1040"
        assert nvda.identifiers[1].identifier.value == "67066G104"
        assert isinstance(nvda.classification, EquityClassification)
        assert nvda.classification.equity_type.equity_type == EquityTypeEnum.ORDINARY
        assert nvda.exchange is not None
        assert nvda.exchange.value == "XNAS"
        assert nvda.currency.value == "USD"
        assert nvda.is_exchange_listed is True

    def test_valid_fund(self) -> None:
        result = Security.create(
            identifiers=_nvda_ids()[:1],
            classification=FundClassification(
                fund_type=FundProductTypeEnum.EXCHANGE_TRADED_FUND,
            ),
            currency="USD",
            exchange="XNAS",
        )
        assert isinstance(result, Ok)
        sec = result.value
        assert isinstance(sec.classification, FundClassification)
        assert sec.classification.fund_type == FundProductTypeEnum.EXCHANGE_TRADED_FUND

    def test_empty_identifiers_rejected(self) -> None:
        result = Security.create(
            identifiers=(),
            classification=EquityClassification(
                equity_type=EquityType(equity_type=EquityTypeEnum.ORDINARY),
            ),
            currency="USD",
        )
        assert isinstance(result, Err)
        assert "identifiers" in result.error

    def test_classification_required_by_type_system(self) -> None:
        """classification is not Optional -- omitting it is a type error.

        Illegal states (no classification, or mismatched instrument_type)
        are now structurally unrepresentable.
        """
        equity = unwrap(Security.create(
            identifiers=_nvda_ids(),
            classification=EquityClassification(
                equity_type=EquityType(equity_type=EquityTypeEnum.ORDINARY),
            ),
            currency="USD",
        ))
        assert equity.instrument_type == InstrumentTypeEnum.EQUITY

        fund = unwrap(Security.create(
            identifiers=_nvda_ids()[:1],
            classification=FundClassification(
                fund_type=FundProductTypeEnum.EXCHANGE_TRADED_FUND,
            ),
            currency="USD",
        ))
        assert fund.instrument_type == InstrumentTypeEnum.FUND

    def test_duplicate_identifier_types_rejected(self) -> None:
        isin1 = unwrap(AssetIdentifier.create("US67066G1040", AssetIdTypeEnum.ISIN))
        isin2 = unwrap(AssetIdentifier.create("US78462F1030", AssetIdTypeEnum.ISIN))
        result = Security.create(
            identifiers=(isin1, isin2),
            classification=EquityClassification(
                equity_type=EquityType(equity_type=EquityTypeEnum.ORDINARY),
            ),
            currency="USD",
            exchange="XNAS",
        )
        assert isinstance(result, Err)
        assert "duplicate" in result.error

    def test_is_exchange_listed_derived_from_exchange(self) -> None:
        listed = unwrap(Security.create(
            identifiers=_nvda_ids(),
            classification=EquityClassification(
                equity_type=EquityType(equity_type=EquityTypeEnum.ORDINARY),
            ),
            currency="USD",
            exchange="XNAS",
        ))
        assert listed.is_exchange_listed is True

        unlisted = unwrap(Security.create(
            identifiers=_nvda_ids(),
            classification=EquityClassification(
                equity_type=EquityType(equity_type=EquityTypeEnum.ORDINARY),
            ),
            currency="USD",
        ))
        assert unlisted.is_exchange_listed is False

    def test_is_exchange_listed_explicit_true_without_exchange(self) -> None:
        """CDM allows isExchangeListed=True without specifying exchange."""
        sec = unwrap(Security.create(
            identifiers=_nvda_ids(),
            classification=EquityClassification(
                equity_type=EquityType(equity_type=EquityTypeEnum.ORDINARY),
            ),
            currency="USD",
            is_exchange_listed=True,
        ))
        assert sec.is_exchange_listed is True
        assert sec.exchange is None

    def test_is_exchange_listed_false_with_exchange_rejected(self) -> None:
        """CDM condition: if exchange exists then isExchangeListed must be True."""
        result = Security.create(
            identifiers=_nvda_ids(),
            classification=EquityClassification(
                equity_type=EquityType(equity_type=EquityTypeEnum.ORDINARY),
            ),
            currency="USD",
            exchange="XNAS",
            is_exchange_listed=False,
        )
        assert isinstance(result, Err)
        assert "exchange" in result.error

    def test_frozen(self) -> None:
        sec = unwrap(Security.create(
            identifiers=_nvda_ids(),
            classification=EquityClassification(
                equity_type=EquityType(equity_type=EquityTypeEnum.ORDINARY),
            ),
            currency="USD",
            exchange="XNAS",
        ))
        try:
            sec.currency = "EUR"  # type: ignore[misc]
            assert False, "should be frozen"  # noqa: B011
        except (AttributeError, TypeError):
            pass

    def test_identifiers_accessible(self) -> None:
        sec = unwrap(Security.create(
            identifiers=_nvda_ids(),
            classification=EquityClassification(
                equity_type=EquityType(equity_type=EquityTypeEnum.ORDINARY),
            ),
            currency="USD",
            exchange="XNAS",
        ))
        assert len(sec.identifiers) == 2
        types = {aid.identifier_type for aid in sec.identifiers}
        assert types == {AssetIdTypeEnum.ISIN, AssetIdTypeEnum.CUSIP}

    def test_empty_currency_rejected(self) -> None:
        result = Security.create(
            identifiers=_nvda_ids(),
            classification=EquityClassification(
                equity_type=EquityType(equity_type=EquityTypeEnum.ORDINARY),
            ),
            currency="",
        )
        assert isinstance(result, Err)
        assert "currency" in result.error

    def test_valid_iso4217_currency_accepted(self) -> None:
        for code in ("USD", "EUR", "GBP", "JPY"):
            result = Security.create(
                identifiers=_nvda_ids(),
                classification=EquityClassification(
                    equity_type=EquityType(equity_type=EquityTypeEnum.ORDINARY),
                ),
                currency=code,
            )
            assert isinstance(result, Ok), f"Expected Ok for {code}"

    def test_invalid_currency_rejected(self) -> None:
        result = Security.create(
            identifiers=_nvda_ids(),
            classification=EquityClassification(
                equity_type=EquityType(equity_type=EquityTypeEnum.ORDINARY),
            ),
            currency="ZZZZZ",
        )
        assert isinstance(result, Err)
        assert "currency" in result.error

    def test_valid_mic_accepted(self) -> None:
        for mic in ("XNAS", "XNYS", "XLON"):
            result = Security.create(
                identifiers=_nvda_ids(),
                classification=EquityClassification(
                    equity_type=EquityType(equity_type=EquityTypeEnum.ORDINARY),
                ),
                currency="USD",
                exchange=mic,
            )
            assert isinstance(result, Ok), f"Expected Ok for {mic}"

    def test_invalid_mic_rejected(self) -> None:
        result = Security.create(
            identifiers=_nvda_ids(),
            classification=EquityClassification(
                equity_type=EquityType(equity_type=EquityTypeEnum.ORDINARY),
            ),
            currency="USD",
            exchange="not-a-mic",
        )
        assert isinstance(result, Err)
        assert "exchange" in result.error.lower() or "MIC" in result.error

    def test_unknown_but_valid_format_mic_accepted(self) -> None:
        """4 uppercase alpha not in known set is still accepted (forward compat)."""
        result = Security.create(
            identifiers=_nvda_ids(),
            classification=EquityClassification(
                equity_type=EquityType(equity_type=EquityTypeEnum.ORDINARY),
            ),
            currency="USD",
            exchange="XZZZ",
        )
        assert isinstance(result, Ok)
        assert result.value.exchange is not None
        assert result.value.exchange.value == "XZZZ"

    def test_valid_exchange_mics_is_populated(self) -> None:
        assert len(VALID_EXCHANGE_MICS) >= 15
        assert "XNAS" in VALID_EXCHANGE_MICS
        assert "XNYS" in VALID_EXCHANGE_MICS


# ---------------------------------------------------------------------------
# create_equity_security
# ---------------------------------------------------------------------------


class TestCreateEquitySecurity:
    def test_nvda_both_ids(self) -> None:
        result = create_equity_security(
            isin="US67066G1040", cusip="67066G104",
            equity_type=EquityTypeEnum.ORDINARY,
            exchange="XNAS", currency="USD",
        )
        assert isinstance(result, Ok)
        sec = result.value
        assert len(sec.identifiers) == 2

    def test_isin_only(self) -> None:
        result = create_equity_security(isin="US67066G1040")
        assert isinstance(result, Ok)
        assert len(result.value.identifiers) == 1

    def test_cusip_only(self) -> None:
        result = create_equity_security(cusip="67066G104")
        assert isinstance(result, Ok)
        assert len(result.value.identifiers) == 1

    def test_no_ids_rejected(self) -> None:
        result = create_equity_security()
        assert isinstance(result, Err)
        assert "identifier" in result.error

    def test_invalid_isin_rejected(self) -> None:
        result = create_equity_security(isin="INVALID12345")
        assert isinstance(result, Err)

    def test_extra_identifiers(self) -> None:
        extra = unwrap(AssetIdentifier.create("NVDA.OQ", AssetIdTypeEnum.RIC))
        result = create_equity_security(isin="US67066G1040", extra_identifiers=(extra,))
        assert isinstance(result, Ok)
        assert len(result.value.identifiers) == 2

    def test_depositary_receipt(self) -> None:
        """ADR equity via factory with depositary receipt sub-type."""
        result = create_equity_security(
            isin="US67066G1040",
            equity_type=EquityTypeEnum.DEPOSITARY_RECEIPT,
            depositary_receipt=DepositaryReceiptTypeEnum.ADR,
        )
        assert isinstance(result, Ok)
        sec = result.value
        assert isinstance(sec.classification, EquityClassification)
        et = sec.classification.equity_type
        assert et.equity_type == EquityTypeEnum.DEPOSITARY_RECEIPT
        assert et.depositary_receipt == DepositaryReceiptTypeEnum.ADR

    def test_depositary_receipt_invalid_combination_returns_err(self) -> None:
        """Factory returns Err (not TypeError) for invalid DR combination."""
        result = create_equity_security(
            isin="US67066G1040",
            equity_type=EquityTypeEnum.ORDINARY,
            depositary_receipt=DepositaryReceiptTypeEnum.ADR,
        )
        assert isinstance(result, Err)
        assert "depositary_receipt" in result.error


# ---------------------------------------------------------------------------
# create_fund_security
# ---------------------------------------------------------------------------


class TestCreateFundSecurity:
    def test_spy_etf(self) -> None:
        result = create_fund_security(
            isin="US78462F1030", cusip="78462F103",
            fund_type=FundProductTypeEnum.EXCHANGE_TRADED_FUND,
            exchange="XNAS", currency="USD",
        )
        assert isinstance(result, Ok)
        sec = result.value
        assert sec.instrument_type == InstrumentTypeEnum.FUND
        assert isinstance(sec.classification, FundClassification)
        assert sec.classification.fund_type == FundProductTypeEnum.EXCHANGE_TRADED_FUND

    def test_no_ids_rejected(self) -> None:
        result = create_fund_security()
        assert isinstance(result, Err)
        assert "identifier" in result.error

    def test_invalid_cusip_rejected(self) -> None:
        result = create_fund_security(cusip="TOOSHORT")
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Asset type alias
# ---------------------------------------------------------------------------


class TestAssetAlias:
    def test_asset_is_security(self) -> None:
        nvda = unwrap(create_equity_security(isin="US67066G1040"))
        # Asset is just Security at this point
        asset: Asset = nvda
        assert isinstance(asset, Security)
