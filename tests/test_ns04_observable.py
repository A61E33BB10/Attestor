"""NS4 observable-asset — tests for new CDM-aligned types and conditions.

Covers types added/modified during NS4 alignment:
- New enums: PriceSubTypeEnum, FeeTypeEnum, PremiumTypeEnum, PriceOperandEnum,
  InformationProviderEnum, QuoteBasisEnum, CreditRatingAgencyEnum,
  CreditRatingOutlookEnum, CreditRatingCreditWatchEnum, QuotationStyleEnum,
  ValuationMethodEnum, InflationRateIndexEnum, EquityIndexEnum
- New types: InformationSource, QuotedCurrencyPair, PriceComposite,
  InflationIndex, OtherIndex, ForeignExchangeRateIndex
- Modified: Price CDM conditions, PriceQuantity tuple API,
  CreditIndex optional fields + index_factor, EquityIndex mutual exclusion
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from attestor.core.money import NonEmptyStr
from attestor.core.quantity import (
    ArithmeticOperationEnum,
    FinancialUnitEnum,
    NonNegativeQuantity,
    UnitType,
)
from attestor.core.types import Period
from attestor.oracle.observable import (
    CreditIndex,
    CreditRatingAgencyEnum,
    CreditRatingCreditWatchEnum,
    CreditRatingOutlookEnum,
    EquityIndex,
    EquityIndexEnum,
    FeeTypeEnum,
    ForeignExchangeRateIndex,
    InflationIndex,
    InflationRateIndexEnum,
    InformationProviderEnum,
    InformationSource,
    OtherIndex,
    PremiumTypeEnum,
    Price,
    PriceComposite,
    PriceOperandEnum,
    PriceQuantity,
    PriceSubTypeEnum,
    PriceTypeEnum,
    QuotationStyleEnum,
    QuoteBasisEnum,
    QuotedCurrencyPair,
    ValuationMethodEnum,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USD = NonEmptyStr(value="USD")
_EUR = NonEmptyStr(value="EUR")
_GBP = NonEmptyStr(value="GBP")


# ---------------------------------------------------------------------------
# New enum counts and members
# ---------------------------------------------------------------------------


class TestPriceSubTypeEnum:
    def test_count(self) -> None:
        assert len(PriceSubTypeEnum) == 4

    def test_members(self) -> None:
        expected = {"PREMIUM", "FEE", "DISCOUNT", "REBATE"}
        assert {e.name for e in PriceSubTypeEnum} == expected


class TestFeeTypeEnum:
    def test_count(self) -> None:
        assert len(FeeTypeEnum) == 11

    def test_members(self) -> None:
        expected = {
            "ASSIGNMENT", "BROKERAGE_COMMISSION", "INCREASE", "NOVATION",
            "PARTIAL_TERMINATION", "PREMIUM", "RENEGOTIATION", "TERMINATION",
            "UPFRONT", "CREDIT_EVENT", "CORPORATE_ACTION",
        }
        assert {e.name for e in FeeTypeEnum} == expected


class TestPremiumTypeEnum:
    def test_count(self) -> None:
        assert len(PremiumTypeEnum) == 4

    def test_members(self) -> None:
        expected = {"PRE_PAID", "POST_PAID", "VARIABLE", "FIXED"}
        assert {e.name for e in PremiumTypeEnum} == expected


class TestPriceOperandEnum:
    def test_count(self) -> None:
        assert len(PriceOperandEnum) == 3

    def test_members(self) -> None:
        expected = {"ACCRUED_INTEREST", "COMMISSION", "FORWARD_POINT"}
        assert {e.name for e in PriceOperandEnum} == expected


class TestInformationProviderEnum:
    def test_count(self) -> None:
        assert len(InformationProviderEnum) == 18

    def test_key_members(self) -> None:
        for name in ("BLOOMBERG", "REUTERS", "REFINITIV", "FEDERAL_RESERVE",
                      "EURO_CENTRAL_BANK", "BANK_OF_ENGLAND", "ISDA"):
            assert hasattr(InformationProviderEnum, name)


class TestQuoteBasisEnum:
    def test_count(self) -> None:
        assert len(QuoteBasisEnum) == 2

    def test_members(self) -> None:
        expected = {"CURRENCY1_PER_CURRENCY2", "CURRENCY2_PER_CURRENCY1"}
        assert {e.name for e in QuoteBasisEnum} == expected


class TestCreditRatingAgencyEnum:
    def test_count(self) -> None:
        assert len(CreditRatingAgencyEnum) == 8


class TestCreditRatingOutlookEnum:
    def test_count(self) -> None:
        assert len(CreditRatingOutlookEnum) == 4

    def test_members(self) -> None:
        expected = {"POSITIVE", "NEGATIVE", "STABLE", "DEVELOPING"}
        assert {e.name for e in CreditRatingOutlookEnum} == expected


class TestCreditRatingCreditWatchEnum:
    def test_count(self) -> None:
        assert len(CreditRatingCreditWatchEnum) == 3


class TestQuotationStyleEnum:
    def test_count(self) -> None:
        assert len(QuotationStyleEnum) == 3

    def test_members(self) -> None:
        expected = {"POINTS_UP_FRONT", "TRADED_SPREAD", "PRICE"}
        assert {e.name for e in QuotationStyleEnum} == expected


class TestValuationMethodEnum:
    def test_count(self) -> None:
        assert len(ValuationMethodEnum) == 8

    def test_key_members(self) -> None:
        for name in ("MARKET", "HIGHEST", "AVERAGE_MARKET", "BLENDED_MARKET"):
            assert hasattr(ValuationMethodEnum, name)


class TestInflationRateIndexEnum:
    def test_count(self) -> None:
        assert len(InflationRateIndexEnum) == 10

    def test_key_members(self) -> None:
        for name in ("USA_CPI_U", "EUR_HICP", "GBP_RPI"):
            assert hasattr(InflationRateIndexEnum, name)


class TestEquityIndexEnum:
    def test_count(self) -> None:
        assert len(EquityIndexEnum) == 29

    def test_key_members(self) -> None:
        for name in ("SP500", "DJES50", "FT100", "DAX", "NIKKEI", "TOPIX"):
            assert hasattr(EquityIndexEnum, name)


# ---------------------------------------------------------------------------
# InformationSource
# ---------------------------------------------------------------------------


class TestInformationSource:
    def test_valid_minimal(self) -> None:
        src = InformationSource(
            source_provider=InformationProviderEnum.BLOOMBERG,
        )
        assert src.source_provider == InformationProviderEnum.BLOOMBERG
        assert src.source_page is None

    def test_valid_with_page(self) -> None:
        page = NonEmptyStr(value="ALLQ")
        src = InformationSource(
            source_provider=InformationProviderEnum.REUTERS,
            source_page=page,
        )
        assert src.source_page == page

    def test_frozen(self) -> None:
        src = InformationSource(
            source_provider=InformationProviderEnum.ISDA,
        )
        with pytest.raises(AttributeError):
            src.source_provider = InformationProviderEnum.BLOOMBERG  # type: ignore[misc]

    def test_bad_provider_rejected(self) -> None:
        with pytest.raises(TypeError, match="InformationProviderEnum"):
            InformationSource(source_provider="Bloomberg")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# QuotedCurrencyPair
# ---------------------------------------------------------------------------


class TestQuotedCurrencyPair:
    def test_valid(self) -> None:
        qcp = QuotedCurrencyPair(
            currency1=_EUR, currency2=_USD,
            quote_basis=QuoteBasisEnum.CURRENCY1_PER_CURRENCY2,
        )
        assert qcp.currency1 == _EUR
        assert qcp.currency2 == _USD

    def test_same_currency_rejected(self) -> None:
        with pytest.raises(TypeError, match="must differ"):
            QuotedCurrencyPair(
                currency1=_USD, currency2=_USD,
                quote_basis=QuoteBasisEnum.CURRENCY1_PER_CURRENCY2,
            )

    def test_frozen(self) -> None:
        qcp = QuotedCurrencyPair(
            currency1=_EUR, currency2=_USD,
            quote_basis=QuoteBasisEnum.CURRENCY2_PER_CURRENCY1,
        )
        with pytest.raises(AttributeError):
            qcp.currency1 = _GBP  # type: ignore[misc]

    def test_bad_quote_basis_rejected(self) -> None:
        with pytest.raises(TypeError, match="QuoteBasisEnum"):
            QuotedCurrencyPair(
                currency1=_EUR, currency2=_USD,
                quote_basis="Currency1PerCurrency2",  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# PriceComposite
# ---------------------------------------------------------------------------


class TestPriceComposite:
    def test_valid_add(self) -> None:
        pc = PriceComposite(
            base_value=Decimal("100"),
            operand=Decimal("0.5"),
            arithmetic_operator=ArithmeticOperationEnum.ADD,
            operand_type=PriceOperandEnum.FORWARD_POINT,
        )
        assert pc.base_value == Decimal("100")
        assert pc.operand == Decimal("0.5")

    def test_valid_multiply_no_operand_type(self) -> None:
        pc = PriceComposite(
            base_value=Decimal("50"),
            operand=Decimal("2"),
            arithmetic_operator=ArithmeticOperationEnum.MULTIPLY,
        )
        assert pc.operand_type is None

    def test_forward_point_with_multiply_rejected(self) -> None:
        """CDM condition: ForwardPoint → Add or Subtract only."""
        with pytest.raises(TypeError, match="Add or Subtract"):
            PriceComposite(
                base_value=Decimal("100"),
                operand=Decimal("0.5"),
                arithmetic_operator=ArithmeticOperationEnum.MULTIPLY,
                operand_type=PriceOperandEnum.FORWARD_POINT,
            )

    def test_accrued_interest_with_divide_rejected(self) -> None:
        """CDM condition: AccruedInterest → Add or Subtract only."""
        with pytest.raises(TypeError, match="Add or Subtract"):
            PriceComposite(
                base_value=Decimal("100"),
                operand=Decimal("5"),
                arithmetic_operator=ArithmeticOperationEnum.DIVIDE,
                operand_type=PriceOperandEnum.ACCRUED_INTEREST,
            )

    def test_accrued_interest_with_subtract_allowed(self) -> None:
        pc = PriceComposite(
            base_value=Decimal("100"),
            operand=Decimal("2"),
            arithmetic_operator=ArithmeticOperationEnum.SUBTRACT,
            operand_type=PriceOperandEnum.ACCRUED_INTEREST,
        )
        assert pc.arithmetic_operator == ArithmeticOperationEnum.SUBTRACT

    def test_nan_rejected(self) -> None:
        with pytest.raises(TypeError, match="finite Decimal"):
            PriceComposite(
                base_value=Decimal("NaN"),
                operand=Decimal("1"),
                arithmetic_operator=ArithmeticOperationEnum.ADD,
            )

    def test_frozen(self) -> None:
        pc = PriceComposite(
            base_value=Decimal("100"),
            operand=Decimal("1"),
            arithmetic_operator=ArithmeticOperationEnum.ADD,
        )
        with pytest.raises(AttributeError):
            pc.base_value = Decimal("200")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# InflationIndex
# ---------------------------------------------------------------------------


class TestInflationIndex:
    def test_valid_with_tenor(self) -> None:
        ii = InflationIndex(
            inflation_rate_index=InflationRateIndexEnum.USA_CPI_U,
            index_tenor=Period(3, "M"),
        )
        assert ii.inflation_rate_index == InflationRateIndexEnum.USA_CPI_U
        assert ii.index_tenor is not None

    def test_valid_without_tenor(self) -> None:
        ii = InflationIndex(
            inflation_rate_index=InflationRateIndexEnum.EUR_HICP,
        )
        assert ii.index_tenor is None

    def test_frozen(self) -> None:
        ii = InflationIndex(
            inflation_rate_index=InflationRateIndexEnum.GBP_RPI,
        )
        with pytest.raises(AttributeError):
            ii.inflation_rate_index = InflationRateIndexEnum.USA_CPI_U  # type: ignore[misc]

    def test_bad_index_rejected(self) -> None:
        with pytest.raises(TypeError, match="InflationRateIndexEnum"):
            InflationIndex(inflation_rate_index="USA-CPI-U")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# OtherIndex
# ---------------------------------------------------------------------------


class TestOtherIndex:
    def test_valid(self) -> None:
        name = NonEmptyStr(value="Custom Index")
        oi = OtherIndex(index_name=name)
        assert oi.index_name == name
        assert oi.description is None

    def test_with_description(self) -> None:
        name = NonEmptyStr(value="MyIdx")
        desc = NonEmptyStr(value="A custom index")
        oi = OtherIndex(index_name=name, description=desc)
        assert oi.description == desc

    def test_bad_name_rejected(self) -> None:
        with pytest.raises(TypeError, match="NonEmptyStr"):
            OtherIndex(index_name="bad")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ForeignExchangeRateIndex (detailed)
# ---------------------------------------------------------------------------


class TestForeignExchangeRateIndexDetailed:
    def test_with_secondary_source(self) -> None:
        pair = QuotedCurrencyPair(
            currency1=_GBP, currency2=_USD,
            quote_basis=QuoteBasisEnum.CURRENCY2_PER_CURRENCY1,
        )
        primary = InformationSource(
            source_provider=InformationProviderEnum.REUTERS,
        )
        secondary = InformationSource(
            source_provider=InformationProviderEnum.BLOOMBERG,
        )
        fxi = ForeignExchangeRateIndex(
            quoted_currency_pair=pair,
            primary_source=primary,
            secondary_source=secondary,
        )
        assert fxi.secondary_source == secondary

    def test_bad_pair_rejected(self) -> None:
        with pytest.raises(TypeError, match="QuotedCurrencyPair"):
            ForeignExchangeRateIndex(
                quoted_currency_pair="EURUSD",  # type: ignore[arg-type]
                primary_source=InformationSource(
                    source_provider=InformationProviderEnum.REUTERS,
                ),
            )

    def test_bad_source_rejected(self) -> None:
        pair = QuotedCurrencyPair(
            currency1=_EUR, currency2=_USD,
            quote_basis=QuoteBasisEnum.CURRENCY1_PER_CURRENCY2,
        )
        with pytest.raises(TypeError, match="InformationSource"):
            ForeignExchangeRateIndex(
                quoted_currency_pair=pair,
                primary_source="Reuters",  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# Price CDM conditions
# ---------------------------------------------------------------------------


class TestPriceCDMConditions:
    def test_positive_asset_price_enforced(self) -> None:
        """CDM PositiveAssetPrice: AssetPrice w/o operator → value > 0."""
        with pytest.raises(TypeError, match="ASSET_PRICE.*value > 0"):
            Price(
                value=Decimal("0"),
                currency=_USD,
                price_type=PriceTypeEnum.ASSET_PRICE,
            )

    def test_positive_exchange_rate_enforced(self) -> None:
        """CDM PositiveAssetPrice: ExchangeRate w/o operator → value > 0."""
        with pytest.raises(TypeError, match="EXCHANGE_RATE.*value > 0"):
            Price(
                value=Decimal("-1"),
                currency=_USD,
                price_type=PriceTypeEnum.EXCHANGE_RATE,
            )

    def test_asset_price_with_operator_allows_negative(self) -> None:
        """With arithmetic_operator, positivity is not enforced."""
        p = Price(
            value=Decimal("-5"),
            currency=_USD,
            price_type=PriceTypeEnum.ASSET_PRICE,
            arithmetic_operator=ArithmeticOperationEnum.ADD,
        )
        assert p.value == Decimal("-5")

    def test_positive_cash_price_enforced(self) -> None:
        """CDM PositiveCashPrice: CashPrice → value > 0."""
        with pytest.raises(TypeError, match="CashPrice must have value > 0"):
            Price(
                value=Decimal("0"),
                currency=_USD,
                price_type=PriceTypeEnum.CASH_PRICE,
            )

    def test_choice_operator_composite_exclusive(self) -> None:
        """CDM: arithmetic_operator and composite mutually exclusive."""
        with pytest.raises(TypeError, match="mutually exclusive"):
            Price(
                value=Decimal("100"),
                currency=_USD,
                price_type=PriceTypeEnum.INTEREST_RATE,
                arithmetic_operator=ArithmeticOperationEnum.ADD,
                composite=PriceComposite(
                    base_value=Decimal("99"),
                    operand=Decimal("1"),
                    arithmetic_operator=ArithmeticOperationEnum.ADD,
                ),
            )

    def test_premium_requires_premium_subtype(self) -> None:
        """CDM: premium_type → price_sub_type == PREMIUM."""
        with pytest.raises(TypeError, match="price_sub_type == PREMIUM"):
            Price(
                value=Decimal("5"),
                currency=_USD,
                price_type=PriceTypeEnum.CASH_PRICE,
                premium_type=PremiumTypeEnum.PRE_PAID,
                price_sub_type=PriceSubTypeEnum.FEE,
            )

    def test_premium_with_correct_subtype_allowed(self) -> None:
        p = Price(
            value=Decimal("5"),
            currency=_USD,
            price_type=PriceTypeEnum.CASH_PRICE,
            premium_type=PremiumTypeEnum.PRE_PAID,
            price_sub_type=PriceSubTypeEnum.PREMIUM,
        )
        assert p.premium_type == PremiumTypeEnum.PRE_PAID

    def test_arithmetic_operator_subtract_rejected(self) -> None:
        """CDM: arithmetic_operator must not be Subtract or Divide."""
        with pytest.raises(TypeError, match="Subtract or Divide"):
            Price(
                value=Decimal("100"),
                currency=_USD,
                price_type=PriceTypeEnum.INTEREST_RATE,
                arithmetic_operator=ArithmeticOperationEnum.SUBTRACT,
            )

    def test_arithmetic_operator_divide_rejected(self) -> None:
        with pytest.raises(TypeError, match="Subtract or Divide"):
            Price(
                value=Decimal("100"),
                currency=_USD,
                price_type=PriceTypeEnum.INTEREST_RATE,
                arithmetic_operator=ArithmeticOperationEnum.DIVIDE,
            )

    def test_arithmetic_operator_add_allowed(self) -> None:
        p = Price(
            value=Decimal("100"),
            currency=_USD,
            price_type=PriceTypeEnum.INTEREST_RATE,
            arithmetic_operator=ArithmeticOperationEnum.ADD,
        )
        assert p.arithmetic_operator == ArithmeticOperationEnum.ADD

    def test_price_expression_optional(self) -> None:
        """price_expression is 0..1 per CDM."""
        p = Price(
            value=Decimal("1.25"),
            currency=_USD,
            price_type=PriceTypeEnum.EXCHANGE_RATE,
        )
        assert p.price_expression is None

    def test_positive_spot_rate_enforced(self) -> None:
        """CDM PositiveSpotRate: composite.base_value > 0 for ExchangeRate."""
        with pytest.raises(TypeError, match="PositiveSpotRate"):
            Price(
                value=Decimal("1.0"),
                currency=_USD,
                price_type=PriceTypeEnum.EXCHANGE_RATE,
                composite=PriceComposite(
                    base_value=Decimal("-0.5"),
                    operand=Decimal("1.5"),
                    arithmetic_operator=ArithmeticOperationEnum.ADD,
                ),
            )

    def test_premium_subtype_requires_cash_price(self) -> None:
        """CDM PremiumSubType: priceSubType == PREMIUM → priceType == CashPrice."""
        with pytest.raises(TypeError, match="PremiumSubType"):
            Price(
                value=Decimal("5"),
                currency=_USD,
                price_type=PriceTypeEnum.INTEREST_RATE,
                price_sub_type=PriceSubTypeEnum.PREMIUM,
            )

    def test_spread_price_add_only_for_asset_or_interest(self) -> None:
        """CDM SpreadPrice: Add → AssetPrice or InterestRate."""
        with pytest.raises(TypeError, match="SpreadPrice"):
            Price(
                value=Decimal("100"),
                currency=_USD,
                price_type=PriceTypeEnum.CORRELATION,
                arithmetic_operator=ArithmeticOperationEnum.ADD,
            )

    def test_forward_point_requires_exchange_rate(self) -> None:
        """CDM ForwardPoint: ForwardPoint operand → ExchangeRate."""
        with pytest.raises(TypeError, match="ForwardPoint condition"):
            Price(
                value=Decimal("100"),
                currency=_USD,
                price_type=PriceTypeEnum.ASSET_PRICE,
                composite=PriceComposite(
                    base_value=Decimal("99"),
                    operand=Decimal("1"),
                    arithmetic_operator=ArithmeticOperationEnum.ADD,
                    operand_type=PriceOperandEnum.FORWARD_POINT,
                ),
            )

    def test_forward_point_with_exchange_rate_allowed(self) -> None:
        p = Price(
            value=Decimal("1.25"),
            currency=_USD,
            price_type=PriceTypeEnum.EXCHANGE_RATE,
            composite=PriceComposite(
                base_value=Decimal("1.20"),
                operand=Decimal("0.05"),
                arithmetic_operator=ArithmeticOperationEnum.ADD,
                operand_type=PriceOperandEnum.FORWARD_POINT,
            ),
        )
        assert p.composite is not None

    def test_accrued_interest_requires_asset_price(self) -> None:
        """CDM AccruedInterest: AccruedInterest operand → AssetPrice."""
        with pytest.raises(TypeError, match="AccruedInterest condition"):
            Price(
                value=Decimal("1.5"),
                currency=_USD,
                price_type=PriceTypeEnum.EXCHANGE_RATE,
                composite=PriceComposite(
                    base_value=Decimal("1.0"),
                    operand=Decimal("0.5"),
                    arithmetic_operator=ArithmeticOperationEnum.ADD,
                    operand_type=PriceOperandEnum.ACCRUED_INTEREST,
                ),
            )

    def test_accrued_interest_with_asset_price_allowed(self) -> None:
        p = Price(
            value=Decimal("102"),
            currency=_USD,
            price_type=PriceTypeEnum.ASSET_PRICE,
            composite=PriceComposite(
                base_value=Decimal("100"),
                operand=Decimal("2"),
                arithmetic_operator=ArithmeticOperationEnum.ADD,
                operand_type=PriceOperandEnum.ACCRUED_INTEREST,
            ),
        )
        assert p.composite is not None


# ---------------------------------------------------------------------------
# PriceQuantity tuple API
# ---------------------------------------------------------------------------


class TestPriceQuantityTupleAPI:
    def test_empty_defaults(self) -> None:
        """CDM: price 0..*, quantity 0..*  → default empty tuples."""
        pq = PriceQuantity()
        assert pq.price == ()
        assert pq.quantity == ()
        assert pq.observable is None

    def test_multiple_prices(self) -> None:
        p1 = Price(
            value=Decimal("100"),
            currency=_USD,
            price_type=PriceTypeEnum.CASH_PRICE,
        )
        p2 = Price(
            value=Decimal("0.05"),
            currency=_USD,
            price_type=PriceTypeEnum.INTEREST_RATE,
        )
        pq = PriceQuantity(price=(p1, p2))
        assert len(pq.price) == 2
        assert pq.price[0] == p1
        assert pq.price[1] == p2

    def test_multiple_quantities(self) -> None:
        unit = UnitType.of_financial(FinancialUnitEnum.SHARE)
        q1 = NonNegativeQuantity(value=Decimal("100"), unit=unit)
        q2 = NonNegativeQuantity(value=Decimal("200"), unit=unit)
        pq = PriceQuantity(quantity=(q1, q2))
        assert len(pq.quantity) == 2

    def test_non_tuple_price_rejected(self) -> None:
        p = Price(
            value=Decimal("100"),
            currency=_USD,
            price_type=PriceTypeEnum.CASH_PRICE,
        )
        with pytest.raises(TypeError, match="tuple"):
            PriceQuantity(price=p)  # type: ignore[arg-type]

    def test_non_price_in_tuple_rejected(self) -> None:
        with pytest.raises(TypeError, match="Price"):
            PriceQuantity(price=("not a price",))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# CreditIndex optional fields + index_factor
# ---------------------------------------------------------------------------


class TestCreditIndexExtended:
    def test_name_only(self) -> None:
        """CDM: all fields except name are 0..1."""
        name = NonEmptyStr(value="CDX.NA.IG")
        ci = CreditIndex(index_name=name)
        assert ci.index_series is None
        assert ci.index_annex_version is None
        assert ci.index_annex_date is None
        assert ci.index_factor is None

    def test_with_index_factor(self) -> None:
        name = NonEmptyStr(value="CDX.NA.IG")
        ci = CreditIndex(
            index_name=name,
            index_series=42,
            index_factor=Decimal("0.95"),
        )
        assert ci.index_factor == Decimal("0.95")

    def test_index_factor_out_of_range_rejected(self) -> None:
        name = NonEmptyStr(value="CDX.NA.IG")
        with pytest.raises(TypeError, match="index_factor.*\\[0, 1\\]"):
            CreditIndex(
                index_name=name,
                index_factor=Decimal("1.5"),
            )

    def test_index_factor_negative_rejected(self) -> None:
        name = NonEmptyStr(value="CDX.NA.IG")
        with pytest.raises(TypeError, match="index_factor.*\\[0, 1\\]"):
            CreditIndex(
                index_name=name,
                index_factor=Decimal("-0.1"),
            )

    def test_index_factor_boundaries(self) -> None:
        name = NonEmptyStr(value="CDX.NA.IG")
        ci_zero = CreditIndex(index_name=name, index_factor=Decimal("0"))
        assert ci_zero.index_factor == Decimal("0")
        ci_one = CreditIndex(index_name=name, index_factor=Decimal("1"))
        assert ci_one.index_factor == Decimal("1")

    def test_with_annex_date(self) -> None:
        name = NonEmptyStr(value="CDX.NA.IG")
        ci = CreditIndex(
            index_name=name,
            index_annex_date=date(2025, 3, 20),
        )
        assert ci.index_annex_date == date(2025, 3, 20)


# ---------------------------------------------------------------------------
# EquityIndex mutual exclusion
# ---------------------------------------------------------------------------


class TestEquityIndexExtended:
    def test_by_enum(self) -> None:
        ei = EquityIndex(equity_index=EquityIndexEnum.SP500)
        assert ei.equity_index == EquityIndexEnum.SP500
        assert ei.index_name is None

    def test_by_name(self) -> None:
        name = NonEmptyStr(value="Custom Equity Index")
        ei = EquityIndex(index_name=name)
        assert ei.index_name == name
        assert ei.equity_index is None

    def test_both_set_rejected(self) -> None:
        """CDM: index_name and equity_index are mutually exclusive."""
        name = NonEmptyStr(value="S&P 500")
        with pytest.raises(TypeError, match="mutually exclusive"):
            EquityIndex(index_name=name, equity_index=EquityIndexEnum.SP500)

    def test_neither_set_rejected(self) -> None:
        with pytest.raises(TypeError, match="at least one"):
            EquityIndex()

    def test_bad_enum_rejected(self) -> None:
        with pytest.raises(TypeError, match="EquityIndexEnum"):
            EquityIndex(equity_index="SP500")  # type: ignore[arg-type]
