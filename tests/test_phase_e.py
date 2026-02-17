"""Tests for Phase E: Collateral and Margin types."""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal

import pytest

from attestor.core.money import Money, NonEmptyStr, PositiveDecimal
from attestor.core.result import Ok
from attestor.ledger.collateral import (
    AssetClassEnum,
    CollateralType,
    CollateralValuationTreatment,
    ConcentrationLimit,
    Haircut,
    MarginCallIssuance,
    MarginCallResponse,
    MarginCallResponseEnum,
    StandardizedSchedule,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USD_r = NonEmptyStr.parse("USD")
assert isinstance(_USD_r, Ok)
_USD: NonEmptyStr = _USD_r.value

_SWAP_r = NonEmptyStr.parse("Swap")
assert isinstance(_SWAP_r, Ok)
_SWAP: NonEmptyStr = _SWAP_r.value

_CSA_r = NonEmptyStr.parse("CSA-001")
assert isinstance(_CSA_r, Ok)
_CSA: NonEmptyStr = _CSA_r.value

_PARTY_A_r = NonEmptyStr.parse("PARTY-A")
assert isinstance(_PARTY_A_r, Ok)
_PARTY_A: NonEmptyStr = _PARTY_A_r.value


def _money(amount: str, ccy: str = "USD") -> Money:
    r = Money.create(Decimal(amount), ccy)
    assert isinstance(r, Ok)
    return r.value


# ---------------------------------------------------------------------------
# AssetClassEnum
# ---------------------------------------------------------------------------


class TestAssetClassEnum:
    def test_has_5_members(self) -> None:
        assert len(AssetClassEnum) == 5

    def test_members(self) -> None:
        names = {m.name for m in AssetClassEnum}
        assert names == {
            "INTEREST_RATES", "CREDIT", "FX", "EQUITY", "COMMODITY",
        }


# ---------------------------------------------------------------------------
# MarginCallResponseEnum
# ---------------------------------------------------------------------------


class TestMarginCallResponseEnum:
    def test_has_2_members(self) -> None:
        assert len(MarginCallResponseEnum) == 2

    def test_members(self) -> None:
        assert MarginCallResponseEnum.AGREE.value == "AGREE"
        assert MarginCallResponseEnum.DISPUTE.value == "DISPUTE"


# ---------------------------------------------------------------------------
# Haircut
# ---------------------------------------------------------------------------


class TestHaircut:
    def test_valid_zero(self) -> None:
        h = Haircut(value=Decimal("0"))
        assert h.value == Decimal("0")

    def test_valid_half(self) -> None:
        h = Haircut(value=Decimal("0.50"))
        assert h.value == Decimal("0.50")

    def test_valid_near_one(self) -> None:
        h = Haircut(value=Decimal("0.99"))
        assert h.value == Decimal("0.99")

    def test_rejects_one(self) -> None:
        with pytest.raises(TypeError, match=r"\[0, 1\)"):
            Haircut(value=Decimal("1"))

    def test_rejects_negative(self) -> None:
        with pytest.raises(TypeError, match=r"\[0, 1\)"):
            Haircut(value=Decimal("-0.01"))

    def test_rejects_greater_than_one(self) -> None:
        with pytest.raises(TypeError, match=r"\[0, 1\)"):
            Haircut(value=Decimal("1.5"))

    def test_rejects_infinity(self) -> None:
        with pytest.raises(TypeError, match="finite Decimal"):
            Haircut(value=Decimal("Infinity"))

    def test_rejects_nan(self) -> None:
        with pytest.raises(TypeError, match="finite Decimal"):
            Haircut(value=Decimal("NaN"))

    def test_frozen(self) -> None:
        h = Haircut(value=Decimal("0.10"))
        with pytest.raises(dataclasses.FrozenInstanceError):
            h.value = Decimal("0.20")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CollateralValuationTreatment
# ---------------------------------------------------------------------------


class TestCollateralValuationTreatment:
    def test_basic_construction(self) -> None:
        h = Haircut(value=Decimal("0.10"))
        cvt = CollateralValuationTreatment(haircut=h)
        assert cvt.haircut.value == Decimal("0.10")
        assert cvt.margin_percentage is None
        assert cvt.fx_haircut is None

    def test_with_all_fields(self) -> None:
        h = Haircut(value=Decimal("0.05"))
        fxh = Haircut(value=Decimal("0.08"))
        cvt = CollateralValuationTreatment(
            haircut=h,
            margin_percentage=Decimal("0.02"),
            fx_haircut=fxh,
        )
        assert cvt.margin_percentage == Decimal("0.02")
        assert cvt.fx_haircut is not None
        assert cvt.fx_haircut.value == Decimal("0.08")

    def test_rejects_negative_margin_percentage(self) -> None:
        h = Haircut(value=Decimal("0.10"))
        with pytest.raises(TypeError, match="margin_percentage"):
            CollateralValuationTreatment(
                haircut=h,
                margin_percentage=Decimal("-0.01"),
            )

    def test_rejects_infinite_margin_percentage(self) -> None:
        h = Haircut(value=Decimal("0.10"))
        with pytest.raises(TypeError, match="finite Decimal"):
            CollateralValuationTreatment(
                haircut=h,
                margin_percentage=Decimal("Infinity"),
            )

    def test_frozen(self) -> None:
        h = Haircut(value=Decimal("0.10"))
        cvt = CollateralValuationTreatment(haircut=h)
        with pytest.raises(dataclasses.FrozenInstanceError):
            cvt.haircut = h  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ConcentrationLimit
# ---------------------------------------------------------------------------


class TestConcentrationLimit:
    def test_valid_limit(self) -> None:
        cl = ConcentrationLimit(
            collateral_type=CollateralType.CASH,
            limit_fraction=Decimal("0.50"),
        )
        assert cl.collateral_type is CollateralType.CASH
        assert cl.limit_fraction == Decimal("0.50")

    def test_valid_full_concentration(self) -> None:
        cl = ConcentrationLimit(
            collateral_type=CollateralType.GOVERNMENT_BOND,
            limit_fraction=Decimal("1"),
        )
        assert cl.limit_fraction == Decimal("1")

    def test_rejects_zero(self) -> None:
        with pytest.raises(TypeError, match=r"\(0, 1\]"):
            ConcentrationLimit(
                collateral_type=CollateralType.CASH,
                limit_fraction=Decimal("0"),
            )

    def test_rejects_greater_than_one(self) -> None:
        with pytest.raises(TypeError, match=r"\(0, 1\]"):
            ConcentrationLimit(
                collateral_type=CollateralType.EQUITY,
                limit_fraction=Decimal("1.01"),
            )

    def test_rejects_negative(self) -> None:
        with pytest.raises(TypeError, match=r"\(0, 1\]"):
            ConcentrationLimit(
                collateral_type=CollateralType.CASH,
                limit_fraction=Decimal("-0.5"),
            )

    def test_frozen(self) -> None:
        cl = ConcentrationLimit(
            collateral_type=CollateralType.CASH,
            limit_fraction=Decimal("0.50"),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            cl.limit_fraction = Decimal("0.60")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# StandardizedSchedule
# ---------------------------------------------------------------------------


class TestStandardizedSchedule:
    def test_basic_construction(self) -> None:
        ss = StandardizedSchedule(
            asset_class=AssetClassEnum.INTEREST_RATES,
            product_class=_SWAP,
            notional=PositiveDecimal(value=Decimal("10000000")),
            currency=_USD,
        )
        assert ss.asset_class is AssetClassEnum.INTEREST_RATES
        assert ss.product_class.value == "Swap"
        assert ss.notional.value == Decimal("10000000")
        assert ss.duration_in_years is None

    def test_with_duration(self) -> None:
        ss = StandardizedSchedule(
            asset_class=AssetClassEnum.CREDIT,
            product_class=_SWAP,
            notional=PositiveDecimal(value=Decimal("5000000")),
            currency=_USD,
            duration_in_years=Decimal("5"),
        )
        assert ss.duration_in_years == Decimal("5")

    def test_rejects_zero_duration(self) -> None:
        with pytest.raises(TypeError, match="duration_in_years"):
            StandardizedSchedule(
                asset_class=AssetClassEnum.FX,
                product_class=_SWAP,
                notional=PositiveDecimal(value=Decimal("1000000")),
                currency=_USD,
                duration_in_years=Decimal("0"),
            )

    def test_rejects_negative_duration(self) -> None:
        with pytest.raises(TypeError, match="duration_in_years"):
            StandardizedSchedule(
                asset_class=AssetClassEnum.EQUITY,
                product_class=_SWAP,
                notional=PositiveDecimal(value=Decimal("1000000")),
                currency=_USD,
                duration_in_years=Decimal("-1"),
            )

    def test_rejects_infinite_duration(self) -> None:
        with pytest.raises(TypeError, match="finite Decimal"):
            StandardizedSchedule(
                asset_class=AssetClassEnum.COMMODITY,
                product_class=_SWAP,
                notional=PositiveDecimal(value=Decimal("1000000")),
                currency=_USD,
                duration_in_years=Decimal("Infinity"),
            )

    def test_frozen(self) -> None:
        ss = StandardizedSchedule(
            asset_class=AssetClassEnum.INTEREST_RATES,
            product_class=_SWAP,
            notional=PositiveDecimal(value=Decimal("10000000")),
            currency=_USD,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            ss.asset_class = AssetClassEnum.CREDIT  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MarginCallIssuance
# ---------------------------------------------------------------------------


class TestMarginCallIssuance:
    def test_construction(self) -> None:
        mc = MarginCallIssuance(
            agreement_id=_CSA,
            call_amount=_money("5000000"),
            call_date=date(2026, 7, 1),
            demanding_party=_PARTY_A,
        )
        assert mc.agreement_id.value == "CSA-001"
        assert mc.call_amount.amount == Decimal("5000000")
        assert mc.call_date == date(2026, 7, 1)
        assert mc.collateral_type is None

    def test_with_collateral_type(self) -> None:
        mc = MarginCallIssuance(
            agreement_id=_CSA,
            call_amount=_money("1000000"),
            call_date=date(2026, 7, 1),
            demanding_party=_PARTY_A,
            collateral_type=CollateralType.CASH,
        )
        assert mc.collateral_type is CollateralType.CASH

    def test_frozen(self) -> None:
        mc = MarginCallIssuance(
            agreement_id=_CSA,
            call_amount=_money("5000000"),
            call_date=date(2026, 7, 1),
            demanding_party=_PARTY_A,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            mc.call_date = date(2026, 8, 1)  # type: ignore[misc]

    def test_rejects_zero_call_amount(self) -> None:
        with pytest.raises(TypeError, match="call_amount must be positive"):
            MarginCallIssuance(
                agreement_id=_CSA,
                call_amount=_money("0"),
                call_date=date(2026, 7, 1),
                demanding_party=_PARTY_A,
            )

    def test_rejects_negative_call_amount(self) -> None:
        with pytest.raises(TypeError, match="call_amount must be positive"):
            MarginCallIssuance(
                agreement_id=_CSA,
                call_amount=_money("-1000"),
                call_date=date(2026, 7, 1),
                demanding_party=_PARTY_A,
            )


# ---------------------------------------------------------------------------
# MarginCallResponse
# ---------------------------------------------------------------------------


class TestMarginCallResponse:
    def _issuance(self) -> MarginCallIssuance:
        return MarginCallIssuance(
            agreement_id=_CSA,
            call_amount=_money("5000000"),
            call_date=date(2026, 7, 1),
            demanding_party=_PARTY_A,
        )

    def test_agree_valid(self) -> None:
        iss = self._issuance()
        resp = MarginCallResponse(
            issuance=iss,
            response=MarginCallResponseEnum.AGREE,
            agreed_amount=_money("5000000"),
            response_date=date(2026, 7, 2),
        )
        assert resp.response is MarginCallResponseEnum.AGREE
        assert resp.agreed_amount == iss.call_amount

    def test_agree_mismatched_amount_rejected(self) -> None:
        iss = self._issuance()
        with pytest.raises(TypeError, match="agreed_amount must equal"):
            MarginCallResponse(
                issuance=iss,
                response=MarginCallResponseEnum.AGREE,
                agreed_amount=_money("4000000"),
                response_date=date(2026, 7, 2),
            )

    def test_dispute_allows_different_amount(self) -> None:
        iss = self._issuance()
        resp = MarginCallResponse(
            issuance=iss,
            response=MarginCallResponseEnum.DISPUTE,
            agreed_amount=_money("3000000"),
            response_date=date(2026, 7, 2),
        )
        assert resp.response is MarginCallResponseEnum.DISPUTE
        assert resp.agreed_amount.amount == Decimal("3000000")

    def test_frozen(self) -> None:
        iss = self._issuance()
        resp = MarginCallResponse(
            issuance=iss,
            response=MarginCallResponseEnum.AGREE,
            agreed_amount=_money("5000000"),
            response_date=date(2026, 7, 2),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            resp.response = MarginCallResponseEnum.DISPUTE  # type: ignore[misc]

    def test_replace(self) -> None:
        iss = self._issuance()
        resp = MarginCallResponse(
            issuance=iss,
            response=MarginCallResponseEnum.DISPUTE,
            agreed_amount=_money("3000000"),
            response_date=date(2026, 7, 2),
        )
        updated = dataclasses.replace(
            resp,
            response=MarginCallResponseEnum.AGREE,
            agreed_amount=iss.call_amount,
        )
        assert updated.response is MarginCallResponseEnum.AGREE
        assert resp.response is MarginCallResponseEnum.DISPUTE

    def test_rejects_currency_mismatch(self) -> None:
        iss = self._issuance()  # call in USD
        eur_amount = _money("3000000", "EUR")
        with pytest.raises(TypeError, match="currency must match"):
            MarginCallResponse(
                issuance=iss,
                response=MarginCallResponseEnum.DISPUTE,
                agreed_amount=eur_amount,
                response_date=date(2026, 7, 2),
            )

    def test_rejects_negative_agreed_amount(self) -> None:
        iss = self._issuance()
        with pytest.raises(TypeError, match="non-negative"):
            MarginCallResponse(
                issuance=iss,
                response=MarginCallResponseEnum.DISPUTE,
                agreed_amount=_money("-1000"),
                response_date=date(2026, 7, 2),
            )

    def test_rejects_response_before_call(self) -> None:
        iss = self._issuance()  # call_date = 2026-07-01
        with pytest.raises(TypeError, match="response_date must be"):
            MarginCallResponse(
                issuance=iss,
                response=MarginCallResponseEnum.AGREE,
                agreed_amount=iss.call_amount,
                response_date=date(2026, 6, 15),
            )

    def test_dispute_rejects_amount_ge_call(self) -> None:
        iss = self._issuance()  # call = 5M
        with pytest.raises(TypeError, match="less than"):
            MarginCallResponse(
                issuance=iss,
                response=MarginCallResponseEnum.DISPUTE,
                agreed_amount=_money("5000000"),  # equal = not less
                response_date=date(2026, 7, 2),
            )

    def test_dispute_rejects_amount_over_call(self) -> None:
        iss = self._issuance()  # call = 5M
        with pytest.raises(TypeError, match="less than"):
            MarginCallResponse(
                issuance=iss,
                response=MarginCallResponseEnum.DISPUTE,
                agreed_amount=_money("10000000"),  # 10M > 5M
                response_date=date(2026, 7, 2),
            )

    def test_dispute_zero_agreed_valid(self) -> None:
        """Disputing with zero (total disagreement) is valid."""
        iss = self._issuance()
        resp = MarginCallResponse(
            issuance=iss,
            response=MarginCallResponseEnum.DISPUTE,
            agreed_amount=_money("0"),
            response_date=date(2026, 7, 2),
        )
        assert resp.agreed_amount.amount == Decimal("0")

    def test_same_day_response_valid(self) -> None:
        """Response on same day as call is valid."""
        iss = self._issuance()
        resp = MarginCallResponse(
            issuance=iss,
            response=MarginCallResponseEnum.AGREE,
            agreed_amount=iss.call_amount,
            response_date=date(2026, 7, 1),  # same as call_date
        )
        assert resp.response_date == iss.call_date
