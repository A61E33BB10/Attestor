"""Tests for attestor.core.identifiers — LEI, UTI, ISIN."""

from __future__ import annotations

import dataclasses

import pytest

from attestor.core.identifiers import ISIN, LEI, UTI
from attestor.core.result import Err, Ok, unwrap

# ---------------------------------------------------------------------------
# LEI
# ---------------------------------------------------------------------------


class TestLEI:
    def test_valid_20_alphanumeric(self) -> None:
        result = LEI.parse("529900T8BM49AURSDO55")
        assert isinstance(result, Ok)
        assert unwrap(result).value == "529900T8BM49AURSDO55"

    def test_too_short_19(self) -> None:
        assert isinstance(LEI.parse("529900T8BM49AURSDO5"), Err)

    def test_too_long_21(self) -> None:
        assert isinstance(LEI.parse("529900T8BM49AURSDO555"), Err)

    def test_non_alphanumeric(self) -> None:
        assert isinstance(LEI.parse("529900T8BM49-URSDO55"), Err)

    def test_with_space(self) -> None:
        assert isinstance(LEI.parse("529900T8BM49 URSDO55"), Err)

    def test_frozen(self) -> None:
        lei = unwrap(LEI.parse("529900T8BM49AURSDO55"))
        with pytest.raises(dataclasses.FrozenInstanceError):
            lei.value = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# UTI
# ---------------------------------------------------------------------------


class TestUTI:
    def test_valid_52_chars(self) -> None:
        raw = "529900T8BM49AURSDO55" + "A" * 32  # 20 + 32 = 52
        result = UTI.parse(raw)
        assert isinstance(result, Ok)

    def test_valid_21_chars(self) -> None:
        raw = "529900T8BM49AURSDO55X"  # 20 LEI prefix + 1
        assert isinstance(UTI.parse(raw), Ok)

    def test_too_long_53(self) -> None:
        raw = "529900T8BM49AURSDO55" + "A" * 33  # 53
        assert isinstance(UTI.parse(raw), Err)

    def test_empty(self) -> None:
        assert isinstance(UTI.parse(""), Err)

    def test_invalid_prefix(self) -> None:
        raw = "52990-T8BM49AURSDO55X"
        assert isinstance(UTI.parse(raw), Err)


# ---------------------------------------------------------------------------
# ISIN
# ---------------------------------------------------------------------------


class TestISIN:
    def test_valid_apple(self) -> None:
        result = ISIN.parse("US0378331005")
        assert isinstance(result, Ok)
        assert unwrap(result).value == "US0378331005"

    def test_valid_microsoft(self) -> None:
        result = ISIN.parse("US5949181045")
        assert isinstance(result, Ok)

    def test_wrong_check_digit(self) -> None:
        assert isinstance(ISIN.parse("US0378331006"), Err)  # changed 5 -> 6

    def test_too_short_11(self) -> None:
        assert isinstance(ISIN.parse("US037833100"), Err)

    def test_too_long_13(self) -> None:
        assert isinstance(ISIN.parse("US03783310050"), Err)

    def test_lowercase(self) -> None:
        assert isinstance(ISIN.parse("us0378331005"), Err)

    def test_non_alpha_country(self) -> None:
        assert isinstance(ISIN.parse("120378331005"), Err)

    def test_frozen(self) -> None:
        isin = unwrap(ISIN.parse("US0378331005"))
        with pytest.raises(dataclasses.FrozenInstanceError):
            isin.value = "changed"  # type: ignore[misc]
