"""Phase B: Observable and Index Taxonomy — comprehensive tests.

Covers all 14 new types in attestor/oracle/observable.py:
- FloatingRateIndexEnum, FloatingRateIndex
- CreditIndex, EquityIndex, FXRateIndex
- Index union, Observable union
- PriceTypeEnum, PriceExpressionEnum, Price
- PriceQuantity, ObservationIdentifier
- CalculationMethodEnum, FloatingRateCalculationParameters
- ResetRelativeTo, ResetDates

Plus integration tests for FloatLeg.float_index migration from
NonEmptyStr to FloatingRateIndex.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from attestor.core.money import NonEmptyStr, PositiveDecimal
from attestor.core.types import (
    BusinessDayAdjustments,
    Frequency,
    Period,
    RelativeDateOffset,
    RollConventionEnum,
)
from attestor.oracle.observable import (
    CalculationMethodEnum,
    CreditIndex,
    EquityIndex,
    FloatingRateCalculationParameters,
    FloatingRateIndex,
    FloatingRateIndexEnum,
    FXRateIndex,
    Index,
    Observable,
    ObservationIdentifier,
    Price,
    PriceExpressionEnum,
    PriceQuantity,
    PriceTypeEnum,
    ResetDates,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SOFR = FloatingRateIndex(
    index=FloatingRateIndexEnum.SOFR,
    designated_maturity=Period(1, "D"),
)
_EURIBOR_3M = FloatingRateIndex(
    index=FloatingRateIndexEnum.EURIBOR,
    designated_maturity=Period(3, "M"),
)
_USD = NonEmptyStr.parse("USD")
assert not isinstance(_USD, Exception)
_USD = _USD.value

_CDX = NonEmptyStr.parse("CDX.NA.IG")
assert not isinstance(_CDX, Exception)
_CDX = _CDX.value

_SPX = NonEmptyStr.parse("S&P 500")
assert not isinstance(_SPX, Exception)
_SPX = _SPX.value

_WMR = NonEmptyStr.parse("WM/Reuters")
assert not isinstance(_WMR, Exception)
_WMR = _WMR.value

_BBG = NonEmptyStr.parse("Bloomberg")
assert not isinstance(_BBG, Exception)
_BBG = _BBG.value


def _pos(s: str) -> PositiveDecimal:
    r = PositiveDecimal.parse(Decimal(s))
    assert not isinstance(r, Exception)
    return r.value


# ---------------------------------------------------------------------------
# FloatingRateIndexEnum
# ---------------------------------------------------------------------------


class TestFloatingRateIndexEnum:
    def test_rfr_indices_count(self) -> None:
        rfr = ["SOFR", "ESTR", "SONIA", "TONA", "SARON", "AONIA", "CORRA"]
        for name in rfr:
            assert hasattr(FloatingRateIndexEnum, name)

    def test_ibor_indices_present(self) -> None:
        ibor = [
            "EURIBOR", "TIBOR", "BBSW", "CDOR",
            "HIBOR", "SIBOR", "KLIBOR", "JIBAR",
        ]
        for name in ibor:
            assert hasattr(FloatingRateIndexEnum, name)

    def test_legacy_libor_present(self) -> None:
        legacy = [
            "USD_LIBOR", "GBP_LIBOR", "CHF_LIBOR",
            "JPY_LIBOR", "EUR_LIBOR",
        ]
        for name in legacy:
            assert hasattr(FloatingRateIndexEnum, name)

    def test_total_count(self) -> None:
        assert len(FloatingRateIndexEnum) == 20

    def test_sofr_value(self) -> None:
        assert FloatingRateIndexEnum.SOFR.value == "USD-SOFR"

    def test_euribor_value(self) -> None:
        assert FloatingRateIndexEnum.EURIBOR.value == "EUR-EURIBOR"


# ---------------------------------------------------------------------------
# FloatingRateIndex
# ---------------------------------------------------------------------------


class TestFloatingRateIndex:
    def test_construction(self) -> None:
        fri = FloatingRateIndex(
            index=FloatingRateIndexEnum.SOFR,
            designated_maturity=Period(1, "D"),
        )
        assert fri.index == FloatingRateIndexEnum.SOFR
        assert fri.designated_maturity.multiplier == 1
        assert fri.designated_maturity.unit == "D"

    def test_3m_euribor(self) -> None:
        assert _EURIBOR_3M.index == FloatingRateIndexEnum.EURIBOR
        assert _EURIBOR_3M.designated_maturity.multiplier == 3
        assert _EURIBOR_3M.designated_maturity.unit == "M"

    def test_frozen(self) -> None:
        with pytest.raises(AttributeError):
            _SOFR.index = FloatingRateIndexEnum.ESTR  # type: ignore[misc]

    def test_equality(self) -> None:
        sofr2 = FloatingRateIndex(
            index=FloatingRateIndexEnum.SOFR,
            designated_maturity=Period(1, "D"),
        )
        assert sofr2 == _SOFR

    def test_inequality_different_index(self) -> None:
        assert _SOFR != _EURIBOR_3M

    def test_inequality_different_tenor(self) -> None:
        sofr_3m = FloatingRateIndex(
            index=FloatingRateIndexEnum.SOFR,
            designated_maturity=Period(3, "M"),
        )
        assert sofr_3m != _SOFR

    def test_raw_string_rejected(self) -> None:
        with pytest.raises(TypeError, match="FloatingRateIndexEnum"):
            FloatingRateIndex(
                index="USD-SOFR",  # type: ignore[arg-type]
                designated_maturity=Period(1, "D"),
            )

    def test_non_period_rejected(self) -> None:
        with pytest.raises(TypeError, match="Period"):
            FloatingRateIndex(
                index=FloatingRateIndexEnum.SOFR,
                designated_maturity="1D",  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# CreditIndex
# ---------------------------------------------------------------------------


class TestCreditIndex:
    def test_valid(self) -> None:
        ci = CreditIndex(
            index_name=_CDX, index_series=42, index_annex_version=1,
        )
        assert ci.index_name == _CDX
        assert ci.index_series == 42
        assert ci.index_annex_version == 1

    def test_frozen(self) -> None:
        ci = CreditIndex(
            index_name=_CDX, index_series=42, index_annex_version=1,
        )
        with pytest.raises(AttributeError):
            ci.index_series = 43  # type: ignore[misc]

    def test_series_zero_rejected(self) -> None:
        with pytest.raises(TypeError, match="index_series must be > 0"):
            CreditIndex(
                index_name=_CDX, index_series=0, index_annex_version=1,
            )

    def test_series_negative_rejected(self) -> None:
        with pytest.raises(TypeError, match="index_series must be > 0"):
            CreditIndex(
                index_name=_CDX, index_series=-1, index_annex_version=1,
            )

    def test_annex_version_zero_rejected(self) -> None:
        with pytest.raises(
            TypeError, match="index_annex_version must be > 0",
        ):
            CreditIndex(
                index_name=_CDX, index_series=42, index_annex_version=0,
            )

    def test_annex_version_negative_rejected(self) -> None:
        with pytest.raises(
            TypeError, match="index_annex_version must be > 0",
        ):
            CreditIndex(
                index_name=_CDX, index_series=42, index_annex_version=-5,
            )

    def test_series_bool_rejected(self) -> None:
        with pytest.raises(TypeError, match="index_series must be int"):
            CreditIndex(
                index_name=_CDX,
                index_series=True,  # type: ignore[arg-type]
                index_annex_version=1,
            )

    def test_series_float_rejected(self) -> None:
        with pytest.raises(TypeError, match="index_series must be int"):
            CreditIndex(
                index_name=_CDX,
                index_series=1.5,  # type: ignore[arg-type]
                index_annex_version=1,
            )

    def test_annex_version_bool_rejected(self) -> None:
        with pytest.raises(
            TypeError, match="index_annex_version must be int",
        ):
            CreditIndex(
                index_name=_CDX,
                index_series=42,
                index_annex_version=True,  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# EquityIndex
# ---------------------------------------------------------------------------


class TestEquityIndex:
    def test_valid(self) -> None:
        ei = EquityIndex(index_name=_SPX)
        assert ei.index_name == _SPX

    def test_frozen(self) -> None:
        ei = EquityIndex(index_name=_SPX)
        with pytest.raises(AttributeError):
            ei.index_name = _CDX  # type: ignore[misc]


# ---------------------------------------------------------------------------
# FXRateIndex
# ---------------------------------------------------------------------------


class TestFXRateIndex:
    def test_valid(self) -> None:
        fxi = FXRateIndex(fixing_source=_WMR, currency=_USD)
        assert fxi.fixing_source == _WMR
        assert fxi.currency == _USD

    def test_frozen(self) -> None:
        fxi = FXRateIndex(fixing_source=_WMR, currency=_USD)
        with pytest.raises(AttributeError):
            fxi.currency = _CDX  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Index and Observable unions
# ---------------------------------------------------------------------------


class TestIndexUnion:
    """Index = FloatingRateIndex | CreditIndex | EquityIndex | FXRateIndex.

    Python `type` aliases aren't introspectable via get_args at runtime.
    We verify the union's __value__ attribute (TypeAliasType) and test that
    each concrete type is assignable to Index via isinstance-style checks.
    """

    def test_index_alias_has_value(self) -> None:
        # type-statement aliases have a __value__ attribute
        assert hasattr(Index, "__value__")

    def test_floating_rate_is_valid_index(self) -> None:
        idx: Index = _SOFR
        assert isinstance(idx, FloatingRateIndex)

    def test_credit_is_valid_index(self) -> None:
        idx: Index = CreditIndex(
            index_name=_CDX, index_series=42, index_annex_version=1,
        )
        assert isinstance(idx, CreditIndex)

    def test_equity_is_valid_index(self) -> None:
        idx: Index = EquityIndex(index_name=_SPX)
        assert isinstance(idx, EquityIndex)

    def test_fxrate_is_valid_index(self) -> None:
        idx: Index = FXRateIndex(fixing_source=_WMR, currency=_USD)
        assert isinstance(idx, FXRateIndex)


class TestObservableUnion:
    """Observable = Asset | Index."""

    def test_asset_is_valid_observable(self) -> None:
        obs: Observable = _USD
        assert isinstance(obs, NonEmptyStr)

    def test_index_is_valid_observable(self) -> None:
        obs: Observable = _SOFR
        assert isinstance(obs, FloatingRateIndex)


# ---------------------------------------------------------------------------
# PriceTypeEnum
# ---------------------------------------------------------------------------


class TestPriceTypeEnum:
    def test_count(self) -> None:
        assert len(PriceTypeEnum) == 5

    def test_members(self) -> None:
        expected = {
            "INTEREST_RATE", "EXCHANGE_RATE", "ASSET_PRICE",
            "CASH_PRICE", "NET_PRICE",
        }
        actual = {e.name for e in PriceTypeEnum}
        assert actual == expected


# ---------------------------------------------------------------------------
# PriceExpressionEnum
# ---------------------------------------------------------------------------


class TestPriceExpressionEnum:
    def test_count(self) -> None:
        assert len(PriceExpressionEnum) == 3

    def test_members(self) -> None:
        expected = {"ABSOLUTE", "PERCENTAGE_OF_NOTIONAL", "PER_UNIT"}
        actual = {e.name for e in PriceExpressionEnum}
        assert actual == expected


# ---------------------------------------------------------------------------
# Price
# ---------------------------------------------------------------------------


class TestPrice:
    def test_valid(self) -> None:
        p = Price(
            value=Decimal("1.2345"),
            currency=_USD,
            price_type=PriceTypeEnum.EXCHANGE_RATE,
            price_expression=PriceExpressionEnum.ABSOLUTE,
        )
        assert p.value == Decimal("1.2345")
        assert p.currency == _USD
        assert p.price_type == PriceTypeEnum.EXCHANGE_RATE
        assert p.price_expression == PriceExpressionEnum.ABSOLUTE

    def test_frozen(self) -> None:
        p = Price(
            value=Decimal("100"),
            currency=_USD,
            price_type=PriceTypeEnum.ASSET_PRICE,
            price_expression=PriceExpressionEnum.PER_UNIT,
        )
        with pytest.raises(AttributeError):
            p.value = Decimal("200")  # type: ignore[misc]

    def test_nan_rejected(self) -> None:
        with pytest.raises(TypeError, match="finite Decimal"):
            Price(
                value=Decimal("NaN"),
                currency=_USD,
                price_type=PriceTypeEnum.ASSET_PRICE,
                price_expression=PriceExpressionEnum.ABSOLUTE,
            )

    def test_infinity_rejected(self) -> None:
        with pytest.raises(TypeError, match="finite Decimal"):
            Price(
                value=Decimal("Infinity"),
                currency=_USD,
                price_type=PriceTypeEnum.INTEREST_RATE,
                price_expression=PriceExpressionEnum.ABSOLUTE,
            )

    def test_negative_price_allowed(self) -> None:
        """Negative prices are valid (e.g. negative interest rates)."""
        p = Price(
            value=Decimal("-0.005"),
            currency=_USD,
            price_type=PriceTypeEnum.INTEREST_RATE,
            price_expression=PriceExpressionEnum.ABSOLUTE,
        )
        assert p.value == Decimal("-0.005")

    def test_zero_price_allowed(self) -> None:
        p = Price(
            value=Decimal("0"),
            currency=_USD,
            price_type=PriceTypeEnum.CASH_PRICE,
            price_expression=PriceExpressionEnum.ABSOLUTE,
        )
        assert p.value == Decimal("0")


# ---------------------------------------------------------------------------
# PriceQuantity
# ---------------------------------------------------------------------------


class TestPriceQuantity:
    def test_valid_with_floating_rate_observable(self) -> None:
        price = Price(
            value=Decimal("0.05"),
            currency=_USD,
            price_type=PriceTypeEnum.INTEREST_RATE,
            price_expression=PriceExpressionEnum.ABSOLUTE,
        )
        pq = PriceQuantity(
            price=price, quantity=_pos("1000000"), observable=_SOFR,
        )
        assert pq.price == price
        assert pq.observable == _SOFR

    def test_valid_with_asset_observable(self) -> None:
        price = Price(
            value=Decimal("150.25"),
            currency=_USD,
            price_type=PriceTypeEnum.ASSET_PRICE,
            price_expression=PriceExpressionEnum.PER_UNIT,
        )
        ticker = NonEmptyStr.parse("AAPL")
        assert not isinstance(ticker, Exception)
        pq = PriceQuantity(
            price=price, quantity=_pos("100"), observable=ticker.value,
        )
        assert pq.observable == ticker.value

    def test_frozen(self) -> None:
        price = Price(
            value=Decimal("1.5"),
            currency=_USD,
            price_type=PriceTypeEnum.EXCHANGE_RATE,
            price_expression=PriceExpressionEnum.ABSOLUTE,
        )
        pq = PriceQuantity(
            price=price, quantity=_pos("500"), observable=_SOFR,
        )
        with pytest.raises(AttributeError):
            pq.price = price  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ObservationIdentifier
# ---------------------------------------------------------------------------


class TestObservationIdentifier:
    def test_valid_with_index(self) -> None:
        oid = ObservationIdentifier(
            observable=_SOFR,
            observation_date=date(2025, 6, 15),
            source=_BBG,
        )
        assert oid.observable == _SOFR
        assert oid.observation_date == date(2025, 6, 15)
        assert oid.source == _BBG

    def test_valid_with_asset(self) -> None:
        ticker = NonEmptyStr.parse("MSFT")
        assert not isinstance(ticker, Exception)
        oid = ObservationIdentifier(
            observable=ticker.value,
            observation_date=date(2025, 1, 2),
            source=_BBG,
        )
        assert oid.observable == ticker.value

    def test_frozen(self) -> None:
        oid = ObservationIdentifier(
            observable=_SOFR,
            observation_date=date(2025, 6, 15),
            source=_BBG,
        )
        with pytest.raises(AttributeError):
            oid.source = _WMR  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CalculationMethodEnum
# ---------------------------------------------------------------------------


class TestCalculationMethodEnum:
    def test_count(self) -> None:
        assert len(CalculationMethodEnum) == 2

    def test_members(self) -> None:
        expected = {"COMPOUNDING", "AVERAGING"}
        actual = {e.name for e in CalculationMethodEnum}
        assert actual == expected


# ---------------------------------------------------------------------------
# FloatingRateCalculationParameters
# ---------------------------------------------------------------------------


class TestFloatingRateCalculationParameters:
    def test_valid_compounding(self) -> None:
        params = FloatingRateCalculationParameters(
            calculation_method=CalculationMethodEnum.COMPOUNDING,
            applicable_business_days=frozenset({"USNY", "GBLO"}),
            lookback_days=2,
            lockout_days=2,
            shift_days=0,
        )
        assert params.lookback_days == 2
        assert params.lockout_days == 2
        assert params.shift_days == 0
        assert "USNY" in params.applicable_business_days

    def test_valid_averaging(self) -> None:
        params = FloatingRateCalculationParameters(
            calculation_method=CalculationMethodEnum.AVERAGING,
            applicable_business_days=frozenset({"USNY"}),
            lookback_days=0,
            lockout_days=0,
            shift_days=2,
        )
        assert params.calculation_method == CalculationMethodEnum.AVERAGING

    def test_frozen(self) -> None:
        params = FloatingRateCalculationParameters(
            calculation_method=CalculationMethodEnum.COMPOUNDING,
            applicable_business_days=frozenset({"USNY"}),
            lookback_days=2,
            lockout_days=2,
            shift_days=0,
        )
        with pytest.raises(AttributeError):
            params.lookback_days = 3  # type: ignore[misc]

    def test_negative_lookback_rejected(self) -> None:
        with pytest.raises(TypeError, match="lookback_days.*>= 0"):
            FloatingRateCalculationParameters(
                calculation_method=CalculationMethodEnum.COMPOUNDING,
                applicable_business_days=frozenset({"USNY"}),
                lookback_days=-1,
                lockout_days=0,
                shift_days=0,
            )

    def test_negative_lockout_rejected(self) -> None:
        with pytest.raises(TypeError, match="lockout_days.*>= 0"):
            FloatingRateCalculationParameters(
                calculation_method=CalculationMethodEnum.COMPOUNDING,
                applicable_business_days=frozenset({"USNY"}),
                lookback_days=0,
                lockout_days=-1,
                shift_days=0,
            )

    def test_negative_shift_rejected(self) -> None:
        with pytest.raises(TypeError, match="shift_days.*>= 0"):
            FloatingRateCalculationParameters(
                calculation_method=CalculationMethodEnum.COMPOUNDING,
                applicable_business_days=frozenset({"USNY"}),
                lookback_days=0,
                lockout_days=0,
                shift_days=-1,
            )

    def test_zero_all_days_allowed(self) -> None:
        """Zero lookback/lockout/shift is valid (e.g. simple index reset)."""
        params = FloatingRateCalculationParameters(
            calculation_method=CalculationMethodEnum.COMPOUNDING,
            applicable_business_days=frozenset(),
            lookback_days=0,
            lockout_days=0,
            shift_days=0,
        )
        assert params.lookback_days == 0


# ---------------------------------------------------------------------------
# ResetDates
# ---------------------------------------------------------------------------


class TestResetDates:
    def _make_reset_dates(
        self,
        *,
        calc_params: FloatingRateCalculationParameters | None = None,
    ) -> ResetDates:
        return ResetDates(
            reset_frequency=Frequency(
                period=Period(3, "M"),
                roll_convention=RollConventionEnum.EOM,
            ),
            fixing_dates_offset=RelativeDateOffset(
                period=Period(2, "D"),
                day_type="Business",
                business_day_convention="PRECEDING",
                business_centers=frozenset({"USNY"}),
            ),
            reset_relative_to="CalculationPeriodStartDate",
            calculation_parameters=calc_params,
            business_day_adjustments=BusinessDayAdjustments(
                convention="MOD_FOLLOWING",
                business_centers=frozenset({"USNY"}),
            ),
        )

    def test_valid_without_calc_params(self) -> None:
        rd = self._make_reset_dates()
        assert rd.calculation_parameters is None
        assert rd.reset_relative_to == "CalculationPeriodStartDate"

    def test_valid_with_calc_params(self) -> None:
        params = FloatingRateCalculationParameters(
            calculation_method=CalculationMethodEnum.COMPOUNDING,
            applicable_business_days=frozenset({"USNY"}),
            lookback_days=2,
            lockout_days=2,
            shift_days=0,
        )
        rd = self._make_reset_dates(calc_params=params)
        assert rd.calculation_parameters is not None
        assert rd.calculation_parameters.lookback_days == 2

    def test_reset_relative_to_end(self) -> None:
        rd = ResetDates(
            reset_frequency=Frequency(
                period=Period(1, "M"), roll_convention=RollConventionEnum.EOM,
            ),
            fixing_dates_offset=RelativeDateOffset(
                period=Period(1, "D"),
                day_type="Calendar",
                business_day_convention="NONE",
                business_centers=frozenset(),
            ),
            reset_relative_to="CalculationPeriodEndDate",
            calculation_parameters=None,
            business_day_adjustments=BusinessDayAdjustments(
                convention="FOLLOWING",
                business_centers=frozenset({"GBLO"}),
            ),
        )
        assert rd.reset_relative_to == "CalculationPeriodEndDate"

    def test_frozen(self) -> None:
        rd = self._make_reset_dates()
        with pytest.raises(AttributeError):
            rd.reset_relative_to = "CalculationPeriodEndDate"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Integration: FloatLeg.float_index is FloatingRateIndex
# ---------------------------------------------------------------------------


class TestFloatLegIntegration:
    """Verify FloatLeg.float_index accepts only FloatingRateIndex."""

    def test_irs_create_with_floating_rate_index(self) -> None:
        from attestor.core.result import Ok
        from attestor.core.types import PayerReceiver
        from attestor.instrument.fx_types import (
            DayCountConvention,
            IRSwapPayoutSpec,
            PaymentFrequency,
        )

        pr = PayerReceiver(payer="PARTY1", receiver="PARTY2")
        result = IRSwapPayoutSpec.create(
            notional=Decimal("10000000"),
            currency="USD",
            fixed_rate=Decimal("0.03"),
            float_index=_SOFR,
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            start_date=date(2025, 1, 15),
            end_date=date(2030, 1, 15),
            payer_receiver=pr,
        )
        assert isinstance(result, Ok)
        spec = result.value
        assert spec.float_leg.float_index == _SOFR
        assert spec.float_leg.float_index.index == FloatingRateIndexEnum.SOFR

    def test_irs_float_leg_index_is_structured(self) -> None:
        """The float_index field carries structured data, not a string."""
        from attestor.core.result import Ok
        from attestor.core.types import PayerReceiver
        from attestor.instrument.fx_types import (
            DayCountConvention,
            IRSwapPayoutSpec,
            PaymentFrequency,
        )

        pr = PayerReceiver(payer="PARTY1", receiver="PARTY2")
        result = IRSwapPayoutSpec.create(
            notional=Decimal("10000000"),
            currency="USD",
            fixed_rate=Decimal("0.03"),
            float_index=_EURIBOR_3M,
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.SEMI_ANNUAL,
            start_date=date(2025, 1, 15),
            end_date=date(2030, 1, 15),
            payer_receiver=pr,
        )
        assert isinstance(result, Ok)
        fl = result.value.float_leg.float_index
        assert fl.index == FloatingRateIndexEnum.EURIBOR
        assert fl.designated_maturity.multiplier == 3
        assert fl.designated_maturity.unit == "M"
