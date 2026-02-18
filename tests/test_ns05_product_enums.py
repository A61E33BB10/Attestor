"""NS5a tests — product-template enums aligned to CDM Rosetta.

Tests cover: OptionTypeEnum (5), OptionExerciseStyleEnum (3),
ExpirationTimeTypeEnum (7), CallingPartyEnum (4),
ExerciseNoticeGiverEnum (4), AveragingInOutEnum (3),
AssetPayoutTradeTypeEnum (2).
"""

from __future__ import annotations

from attestor.instrument.derivative_types import (
    AssetPayoutTradeTypeEnum,
    AveragingInOutEnum,
    CallingPartyEnum,
    ExerciseNoticeGiverEnum,
    ExpirationTimeTypeEnum,
    OptionExerciseStyleEnum,
    OptionTypeEnum,
)

# ---------------------------------------------------------------------------
# OptionTypeEnum (extends PutCallEnum)
# ---------------------------------------------------------------------------


class TestOptionTypeEnum:
    def test_count(self) -> None:
        assert len(OptionTypeEnum) == 5

    def test_members(self) -> None:
        assert {e.name for e in OptionTypeEnum} == {
            "CALL", "PUT", "PAYER", "RECEIVER", "STRADDLE",
        }

    def test_values_pascal_case(self) -> None:
        assert OptionTypeEnum.CALL.value == "Call"
        assert OptionTypeEnum.PUT.value == "Put"
        assert OptionTypeEnum.PAYER.value == "Payer"
        assert OptionTypeEnum.RECEIVER.value == "Receiver"
        assert OptionTypeEnum.STRADDLE.value == "Straddle"

    def test_put_call_subset(self) -> None:
        """CALL and PUT are the vanilla option subset (CDM PutCallEnum)."""
        vanilla = {OptionTypeEnum.CALL, OptionTypeEnum.PUT}
        assert len(vanilla) == 2

    def test_construct_from_value(self) -> None:
        assert OptionTypeEnum("Payer") is OptionTypeEnum.PAYER
        assert OptionTypeEnum("Straddle") is OptionTypeEnum.STRADDLE


# ---------------------------------------------------------------------------
# OptionExerciseStyleEnum
# ---------------------------------------------------------------------------


class TestOptionExerciseStyleEnum:
    def test_count(self) -> None:
        assert len(OptionExerciseStyleEnum) == 3

    def test_members(self) -> None:
        assert {e.name for e in OptionExerciseStyleEnum} == {
            "EUROPEAN", "BERMUDA", "AMERICAN",
        }

    def test_values_pascal_case(self) -> None:
        assert OptionExerciseStyleEnum.EUROPEAN.value == "European"
        assert OptionExerciseStyleEnum.BERMUDA.value == "Bermuda"
        assert OptionExerciseStyleEnum.AMERICAN.value == "American"

    def test_construct_from_value(self) -> None:
        assert (
            OptionExerciseStyleEnum("Bermuda")
            is OptionExerciseStyleEnum.BERMUDA
        )


# ---------------------------------------------------------------------------
# ExpirationTimeTypeEnum
# ---------------------------------------------------------------------------


class TestExpirationTimeTypeEnum:
    def test_count(self) -> None:
        assert len(ExpirationTimeTypeEnum) == 7

    def test_members(self) -> None:
        assert {e.name for e in ExpirationTimeTypeEnum} == {
            "CLOSE", "OPEN", "OSP", "SPECIFIC_TIME", "XETRA",
            "DERIVATIVES_CLOSE", "AS_SPECIFIED_IN_MASTER_CONFIRMATION",
        }

    def test_values_pascal_case(self) -> None:
        assert ExpirationTimeTypeEnum.CLOSE.value == "Close"
        assert ExpirationTimeTypeEnum.OSP.value == "OSP"
        assert ExpirationTimeTypeEnum.SPECIFIC_TIME.value == "SpecificTime"
        assert ExpirationTimeTypeEnum.XETRA.value == "XETRA"
        assert (
            ExpirationTimeTypeEnum.AS_SPECIFIED_IN_MASTER_CONFIRMATION.value
            == "AsSpecifiedInMasterConfirmation"
        )


# ---------------------------------------------------------------------------
# CallingPartyEnum
# ---------------------------------------------------------------------------


class TestCallingPartyEnum:
    def test_count(self) -> None:
        assert len(CallingPartyEnum) == 4

    def test_members(self) -> None:
        assert {e.name for e in CallingPartyEnum} == {
            "INITIAL_BUYER", "INITIAL_SELLER", "EITHER",
            "AS_DEFINED_IN_MASTER_AGREEMENT",
        }

    def test_values_pascal_case(self) -> None:
        assert CallingPartyEnum.INITIAL_BUYER.value == "InitialBuyer"
        assert CallingPartyEnum.EITHER.value == "Either"


# ---------------------------------------------------------------------------
# ExerciseNoticeGiverEnum
# ---------------------------------------------------------------------------


class TestExerciseNoticeGiverEnum:
    def test_count(self) -> None:
        assert len(ExerciseNoticeGiverEnum) == 4

    def test_members(self) -> None:
        assert {e.name for e in ExerciseNoticeGiverEnum} == {
            "BUYER", "SELLER", "BOTH",
            "AS_SPECIFIED_IN_MASTER_AGREEMENT",
        }

    def test_values_pascal_case(self) -> None:
        assert ExerciseNoticeGiverEnum.BUYER.value == "Buyer"
        assert ExerciseNoticeGiverEnum.BOTH.value == "Both"


# ---------------------------------------------------------------------------
# AveragingInOutEnum
# ---------------------------------------------------------------------------


class TestAveragingInOutEnum:
    def test_count(self) -> None:
        assert len(AveragingInOutEnum) == 3

    def test_members(self) -> None:
        assert {e.name for e in AveragingInOutEnum} == {"IN", "OUT", "BOTH"}

    def test_values_pascal_case(self) -> None:
        assert AveragingInOutEnum.IN.value == "In"
        assert AveragingInOutEnum.OUT.value == "Out"
        assert AveragingInOutEnum.BOTH.value == "Both"


# ---------------------------------------------------------------------------
# AssetPayoutTradeTypeEnum
# ---------------------------------------------------------------------------


class TestAssetPayoutTradeTypeEnum:
    def test_count(self) -> None:
        assert len(AssetPayoutTradeTypeEnum) == 2

    def test_members(self) -> None:
        assert {e.name for e in AssetPayoutTradeTypeEnum} == {
            "REPO", "BUY_SELL_BACK",
        }

    def test_values_pascal_case(self) -> None:
        assert AssetPayoutTradeTypeEnum.REPO.value == "Repo"
        assert AssetPayoutTradeTypeEnum.BUY_SELL_BACK.value == "BuySellBack"
