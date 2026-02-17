"""Phase 0 Safety Hardening — new tests for __post_init__ sealing.

Tests that direct construction with invalid args raises TypeError,
verifying that every smart-constructor bypass is now sealed.

Covers: P0-1 (seal constructors), P0-2 (NonNegativeDecimal),
P0-3 (pure Decimal calibration), P0-4 (negative rates / zero strike),
P0-5 (multi-leg payouts), P0-6 (date invariant), P0-7 (gateway match).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from attestor.core.identifiers import ISIN, LEI, UTI
from attestor.core.money import (
    CurrencyPair,
    Money,
    NonEmptyStr,
    NonNegativeDecimal,
    NonZeroDecimal,
    PositiveDecimal,
)
from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import IdempotencyKey, PayerReceiver, Period, UtcDatetime
from attestor.gateway.types import (
    CanonicalOrder,
    OrderSide,
    OrderType,
)
from attestor.instrument.credit_types import SwaptionPayoutSpec
from attestor.instrument.derivative_types import (
    CDSDetail,
    FuturesPayoutSpec,
    FXDetail,
    IRSwapDetail,
    OptionDetail,
    OptionPayoutSpec,
    OptionStyle,
    OptionType,
    SettlementType,
    SwaptionDetail,
    SwaptionType,
)
from attestor.instrument.fx_types import (
    DayCountConvention,
    IRSwapPayoutSpec,
    NDFPayoutSpec,
    PaymentFrequency,
)
from attestor.instrument.types import EconomicTerms, EquityPayoutSpec
from attestor.ledger.collateral import CollateralAgreement, CollateralType
from attestor.ledger.transactions import DistinctAccountPair, Move, Transaction
from attestor.oracle.attestation import QuoteCondition, QuotedConfidence
from attestor.oracle.calibration import YieldCurve, discount_factor, forward_rate
from attestor.oracle.observable import FloatingRateIndex, FloatingRateIndexEnum

_SOFR = FloatingRateIndex(
    index=FloatingRateIndexEnum.SOFR, designated_maturity=Period(1, "D"),
)
_EURIBOR = FloatingRateIndex(
    index=FloatingRateIndexEnum.EURIBOR, designated_maturity=Period(3, "M"),
)

# ---------------------------------------------------------------------------
# P0-1: Seal constructor bypass — core types
# ---------------------------------------------------------------------------


class TestSealPositiveDecimal:
    def test_negative_value_raises(self) -> None:
        with pytest.raises(TypeError, match="PositiveDecimal"):
            PositiveDecimal(value=Decimal("-5"))

    def test_zero_value_raises(self) -> None:
        with pytest.raises(TypeError, match="PositiveDecimal"):
            PositiveDecimal(value=Decimal("0"))


class TestSealNonZeroDecimal:
    def test_zero_value_raises(self) -> None:
        with pytest.raises(TypeError, match="NonZeroDecimal"):
            NonZeroDecimal(value=Decimal("0"))


class TestSealNonEmptyStr:
    def test_empty_string_raises(self) -> None:
        with pytest.raises(TypeError, match="NonEmptyStr"):
            NonEmptyStr(value="")


class TestSealMoney:
    def test_nan_amount_raises(self) -> None:
        cur = NonEmptyStr(value="USD")
        with pytest.raises(TypeError, match="Money.amount"):
            Money(amount=Decimal("NaN"), currency=cur)

    def test_infinity_amount_raises(self) -> None:
        cur = NonEmptyStr(value="USD")
        with pytest.raises(TypeError, match="Money.amount"):
            Money(amount=Decimal("Infinity"), currency=cur)


class TestSealCurrencyPair:
    def test_same_base_quote_raises(self) -> None:
        usd = NonEmptyStr(value="USD")
        with pytest.raises(TypeError, match="CurrencyPair"):
            CurrencyPair(base=usd, quote=usd)


class TestSealLEI:
    def test_short_lei_raises(self) -> None:
        with pytest.raises(TypeError, match="LEI"):
            LEI(value="ABC")

    def test_non_alnum_lei_raises(self) -> None:
        with pytest.raises(TypeError, match="LEI"):
            LEI(value="5299-0HNOAA1KXQJUQ27")


class TestSealUTI:
    def test_empty_uti_raises(self) -> None:
        with pytest.raises(TypeError, match="UTI"):
            UTI(value="")

    def test_too_long_uti_raises(self) -> None:
        with pytest.raises(TypeError, match="UTI"):
            UTI(value="X" * 53)


class TestSealISIN:
    def test_short_isin_raises(self) -> None:
        with pytest.raises(TypeError, match="ISIN"):
            ISIN(value="US000000")

    def test_bad_luhn_raises(self) -> None:
        with pytest.raises(TypeError, match="ISIN"):
            ISIN(value="US0000000001")  # Bad Luhn


class TestSealUtcDatetime:
    def test_naive_datetime_raises(self) -> None:
        with pytest.raises(TypeError, match="UtcDatetime"):
            UtcDatetime(value=datetime(2025, 1, 1))


class TestSealIdempotencyKey:
    def test_empty_key_raises(self) -> None:
        with pytest.raises(TypeError, match="IdempotencyKey"):
            IdempotencyKey(value="")


# ---------------------------------------------------------------------------
# P0-1: Seal constructor bypass — instrument types
# ---------------------------------------------------------------------------


class TestSealFuturesPayoutSpec:
    def test_last_trading_after_expiry_raises(self) -> None:
        with pytest.raises(TypeError, match="last_trading_date"):
            FuturesPayoutSpec(
                underlying_id=NonEmptyStr(value="ES"),
                expiry_date=date(2025, 12, 19),
                last_trading_date=date(2025, 12, 20),
                settlement_type=SettlementType.CASH,
                contract_size=PositiveDecimal(value=Decimal("50")),
                currency=NonEmptyStr(value="USD"),
                exchange=NonEmptyStr(value="CME"),
            )


class TestSealNDFPayoutSpec:
    def test_fixing_after_settlement_raises(self) -> None:
        with pytest.raises(TypeError, match="fixing_date"):
            NDFPayoutSpec(
                currency_pair=CurrencyPair(
                    base=NonEmptyStr(value="USD"),
                    quote=NonEmptyStr(value="BRL"),
                ),
                base_notional=PositiveDecimal(value=Decimal("1000000")),
                forward_rate=PositiveDecimal(value=Decimal("5.0")),
                fixing_date=date(2025, 7, 20),
                settlement_date=date(2025, 7, 15),
                fixing_source=NonEmptyStr(value="PTAX"),
                currency=NonEmptyStr(value="USD"),
            )


# ---------------------------------------------------------------------------
# P0-1: Seal constructor bypass — ledger types
# ---------------------------------------------------------------------------


class TestSealDistinctAccountPair:
    def test_same_debit_credit_raises(self) -> None:
        with pytest.raises(TypeError, match="DistinctAccountPair"):
            DistinctAccountPair(debit="ACC-1", credit="ACC-1")

    def test_empty_debit_raises(self) -> None:
        with pytest.raises(TypeError, match="DistinctAccountPair"):
            DistinctAccountPair(debit="", credit="ACC-2")


class TestSealMove:
    def test_same_source_dest_raises(self) -> None:
        qty = PositiveDecimal(value=Decimal("100"))
        with pytest.raises(TypeError, match="Move"):
            Move(source="A", destination="A", unit="USD", quantity=qty, contract_id="C")

    def test_empty_source_raises(self) -> None:
        qty = PositiveDecimal(value=Decimal("100"))
        with pytest.raises(TypeError, match="Move"):
            Move(source="", destination="B", unit="USD", quantity=qty, contract_id="C")


class TestSealTransaction:
    def test_empty_moves_raises(self) -> None:
        ts = UtcDatetime.now()
        with pytest.raises(TypeError, match="Transaction.moves"):
            Transaction(tx_id="TX-1", moves=(), timestamp=ts)

    def test_empty_tx_id_raises(self) -> None:
        qty = PositiveDecimal(value=Decimal("50"))
        m = Move("A", "B", "USD", qty, "C")
        ts = UtcDatetime.now()
        with pytest.raises(TypeError, match="Transaction.tx_id"):
            Transaction(tx_id="", moves=(m,), timestamp=ts)


# ---------------------------------------------------------------------------
# P0-1: Seal constructor bypass — collateral
# ---------------------------------------------------------------------------


class TestSealCollateralAgreement:
    def test_empty_eligible_collateral_raises(self) -> None:
        with pytest.raises(TypeError, match="eligible_collateral"):
            CollateralAgreement(
                agreement_id=NonEmptyStr(value="CSA-001"),
                party_a=NonEmptyStr(value="PartyA"),
                party_b=NonEmptyStr(value="PartyB"),
                eligible_collateral=(),
                threshold_a=Decimal("0"),
                threshold_b=Decimal("0"),
                minimum_transfer_amount=Decimal("0"),
                currency=NonEmptyStr(value="USD"),
            )

    def test_negative_threshold_raises(self) -> None:
        with pytest.raises(TypeError, match="threshold_a"):
            CollateralAgreement(
                agreement_id=NonEmptyStr(value="CSA-001"),
                party_a=NonEmptyStr(value="PartyA"),
                party_b=NonEmptyStr(value="PartyB"),
                eligible_collateral=(CollateralType.CASH,),
                threshold_a=Decimal("-1"),
                threshold_b=Decimal("0"),
                minimum_transfer_amount=Decimal("0"),
                currency=NonEmptyStr(value="USD"),
            )


# ---------------------------------------------------------------------------
# P0-1: Seal constructor bypass — oracle
# ---------------------------------------------------------------------------


class TestSealQuotedConfidence:
    def test_bid_gt_ask_raises(self) -> None:
        with pytest.raises(TypeError, match="QuotedConfidence"):
            QuotedConfidence(
                bid=Decimal("102"),
                ask=Decimal("100"),
                venue=NonEmptyStr(value="XNYS"),
                size=None,
                conditions=QuoteCondition.FIRM,
            )

    def test_nan_bid_raises(self) -> None:
        with pytest.raises(TypeError, match="QuotedConfidence"):
            QuotedConfidence(
                bid=Decimal("NaN"),
                ask=Decimal("100"),
                venue=NonEmptyStr(value="XNYS"),
                size=None,
                conditions=QuoteCondition.FIRM,
            )


# ---------------------------------------------------------------------------
# P0-2: NonNegativeDecimal
# ---------------------------------------------------------------------------


class TestNonNegativeDecimal:
    def test_zero_ok(self) -> None:
        result = NonNegativeDecimal.parse(Decimal("0"))
        assert isinstance(result, Ok)
        assert result.value.value == Decimal("0")

    def test_positive_ok(self) -> None:
        result = NonNegativeDecimal.parse(Decimal("42"))
        assert isinstance(result, Ok)
        assert result.value.value == Decimal("42")

    def test_negative_err(self) -> None:
        result = NonNegativeDecimal.parse(Decimal("-1"))
        assert isinstance(result, Err)

    def test_direct_negative_raises(self) -> None:
        with pytest.raises(TypeError, match="NonNegativeDecimal"):
            NonNegativeDecimal(value=Decimal("-1"))


# ---------------------------------------------------------------------------
# P0-3: Pure Decimal calibration
# ---------------------------------------------------------------------------


class TestCalibrationPureDecimal:
    def _make_curve(self) -> YieldCurve:
        return unwrap(YieldCurve.create(
            currency="USD",
            as_of=date(2025, 6, 15),
            tenors=(Decimal("0.5"), Decimal("1"), Decimal("2")),
            discount_factors=(Decimal("0.975"), Decimal("0.95"), Decimal("0.90")),
            model_config_ref="test-config",
        ))

    def test_discount_factor_returns_decimal(self) -> None:
        curve = self._make_curve()
        result = discount_factor(curve, Decimal("1.5"))
        assert isinstance(result, Ok)
        assert isinstance(result.value, Decimal)

    def test_forward_rate_returns_decimal(self) -> None:
        curve = self._make_curve()
        result = forward_rate(curve, Decimal("0.5"), Decimal("1"))
        assert isinstance(result, Ok)
        assert isinstance(result.value, Decimal)


# ---------------------------------------------------------------------------
# P0-4: Relaxed rates and strikes
# ---------------------------------------------------------------------------


class TestNegativeRateAndZeroStrike:
    def test_option_zero_strike_ok(self) -> None:
        result = OptionPayoutSpec.create(
            underlying_id="AAPL", strike=Decimal("0"),
            expiry_date=date(2025, 12, 19), option_type=OptionType.CALL,
            option_style=OptionStyle.AMERICAN,
            settlement_type=SettlementType.PHYSICAL,
            currency="USD", exchange="CBOE",
        )
        assert isinstance(result, Ok)
        assert unwrap(result).strike.value == Decimal("0")

    def test_option_detail_zero_strike_ok(self) -> None:
        result = OptionDetail.create(
            strike=Decimal("0"), expiry_date=date(2025, 12, 19),
            option_type=OptionType.CALL, option_style=OptionStyle.AMERICAN,
            settlement_type=SettlementType.PHYSICAL, underlying_id="AAPL",
        )
        assert isinstance(result, Ok)

    def test_irs_negative_fixed_rate_ok(self) -> None:
        _pr = PayerReceiver(payer="PARTY1", receiver="PARTY2")
        result = IRSwapPayoutSpec.create(
            fixed_rate=Decimal("-0.005"),
            float_index=_EURIBOR,
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.SEMI_ANNUAL,
            notional=Decimal("10000000"),
            currency="EUR",
            start_date=date(2025, 6, 15),
            end_date=date(2030, 6, 15),
            payer_receiver=_pr,
        )
        assert isinstance(result, Ok)
        assert unwrap(result).fixed_leg.fixed_rate == Decimal("-0.005")

    def test_swaption_zero_strike_ok(self) -> None:
        _pr = PayerReceiver(payer="PARTY1", receiver="PARTY2")
        result = SwaptionPayoutSpec.create(
            swaption_type=SwaptionType.PAYER,
            exercise_date=date(2025, 12, 19),
            strike=Decimal("0"),
            underlying_swap=unwrap(IRSwapPayoutSpec.create(
                fixed_rate=Decimal("0.035"),
                float_index=_SOFR,
                day_count=DayCountConvention.ACT_360,
                payment_frequency=PaymentFrequency.QUARTERLY,
                notional=Decimal("10000000"),
                currency="USD",
                start_date=date(2026, 1, 15),
                end_date=date(2031, 1, 15),
                payer_receiver=_pr,
            )),
            settlement_type=SettlementType.PHYSICAL,
            currency="USD",
            notional=Decimal("10000000"),
            payer_receiver=_pr,
        )
        assert isinstance(result, Ok)
        assert unwrap(result).strike.value == Decimal("0")


# ---------------------------------------------------------------------------
# P0-5: Multi-leg payouts
# ---------------------------------------------------------------------------


class TestMultiLegPayouts:
    def test_empty_payouts_raises(self) -> None:
        with pytest.raises(TypeError, match="EconomicTerms.payouts"):
            EconomicTerms(
                payouts=(),
                effective_date=date(2025, 6, 15),
                termination_date=None,
            )

    def test_single_payout_ok(self) -> None:
        payout = unwrap(EquityPayoutSpec.create("AAPL", "USD", "XNYS"))
        terms = EconomicTerms(
            payouts=(payout,),
            effective_date=date(2025, 6, 15),
            termination_date=None,
        )
        assert len(terms.payouts) == 1

    def test_two_payouts_ok(self) -> None:
        p1 = unwrap(EquityPayoutSpec.create("AAPL", "USD", "XNYS"))
        p2 = unwrap(EquityPayoutSpec.create("MSFT", "USD", "XNYS"))
        terms = EconomicTerms(
            payouts=(p1, p2),
            effective_date=date(2025, 6, 15),
            termination_date=None,
        )
        assert len(terms.payouts) == 2


# ---------------------------------------------------------------------------
# P0-6: EconomicTerms date invariant
# ---------------------------------------------------------------------------


class TestEconomicTermsDateInvariant:
    def test_reversed_dates_raises(self) -> None:
        payout = unwrap(EquityPayoutSpec.create("AAPL", "USD", "XNYS"))
        with pytest.raises(TypeError, match="effective_date.*termination_date"):
            EconomicTerms(
                payouts=(payout,),
                effective_date=date(2030, 1, 1),
                termination_date=date(2025, 1, 1),
            )

    def test_equal_dates_ok(self) -> None:
        payout = unwrap(EquityPayoutSpec.create("AAPL", "USD", "XNYS"))
        terms = EconomicTerms(
            payouts=(payout,),
            effective_date=date(2025, 6, 15),
            termination_date=date(2025, 6, 15),
        )
        assert terms.effective_date == terms.termination_date


# ---------------------------------------------------------------------------
# P0-7: Gateway match exhaustiveness
# ---------------------------------------------------------------------------

_LEI_STR = "529900HNOAA1KXQJUQ27"
_TS = UtcDatetime(value=datetime(2025, 6, 15, 12, 0, tzinfo=UTC))


def _make_order(detail: object) -> Ok[CanonicalOrder]:
    """Helper: create a valid CanonicalOrder with given instrument_detail."""
    return CanonicalOrder.create(
        order_id="ORD-001",
        instrument_id="INST-001",
        isin=None,
        side=OrderSide.BUY,
        quantity=Decimal("100"),
        price=Decimal("50"),
        currency="USD",
        order_type=OrderType.MARKET,
        counterparty_lei=_LEI_STR,
        executing_party_lei=_LEI_STR,
        trade_date=date(2025, 6, 15),
        settlement_date=date(2025, 6, 17),
        venue="XNYS",
        timestamp=_TS,
        instrument_detail=detail,
    )


class TestGatewayMatchExhaustiveness:
    def test_fx_detail_accepted(self) -> None:
        detail = unwrap(FXDetail.create(
            currency_pair="EUR/USD",
            settlement_date=date(2025, 6, 17),
            settlement_type=SettlementType.PHYSICAL,
        ))
        result = _make_order(detail)
        assert isinstance(result, Ok)

    def test_irs_detail_accepted(self) -> None:
        detail = unwrap(IRSwapDetail.create(
            fixed_rate=Decimal("0.035"),
            float_index="SOFR",
            day_count="ACT/360",
            payment_frequency="QUARTERLY",
            tenor_months=60,
            start_date=date(2025, 6, 15),
            end_date=date(2030, 6, 15),
        ))
        result = _make_order(detail)
        assert isinstance(result, Ok)

    def test_cds_detail_accepted(self) -> None:
        detail = unwrap(CDSDetail.create(
            reference_entity="ACME Corp",
            seniority="SENIOR_UNSECURED",
            spread_bps=Decimal("100"),
            protection_side="BUYER",
            start_date=date(2025, 6, 15),
            maturity_date=date(2030, 6, 15),
        ))
        result = _make_order(detail)
        assert isinstance(result, Ok)

    def test_swaption_detail_accepted(self) -> None:
        detail = unwrap(SwaptionDetail.create(
            swaption_type="PAYER",
            expiry_date=date(2026, 6, 15),
            underlying_fixed_rate=Decimal("0.035"),
            underlying_float_index="SOFR",
            underlying_tenor_months=60,
            settlement_type="PHYSICAL",
        ))
        result = _make_order(detail)
        assert isinstance(result, Ok)
