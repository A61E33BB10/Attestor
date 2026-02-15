"""Tests for attestor.core.result — Result[T, E] monadic error handling."""

from __future__ import annotations

import dataclasses

import pytest
from hypothesis import given
from hypothesis import strategies as st

from attestor.core.result import Err, Ok, map_result, sequence, unwrap

# ---------------------------------------------------------------------------
# Core: Ok and Err hold values, are frozen, support pattern matching
# ---------------------------------------------------------------------------


class TestOkBasics:
    def test_ok_holds_value(self) -> None:
        assert Ok(42).value == 42

    def test_ok_holds_string(self) -> None:
        assert Ok("hello").value == "hello"

    def test_ok_is_frozen(self) -> None:
        ok = Ok(42)
        with pytest.raises(dataclasses.FrozenInstanceError):
            ok.value = 99  # type: ignore[misc]

    def test_ok_equality(self) -> None:
        assert Ok(42) == Ok(42)
        assert Ok(42) != Ok(99)
        assert Ok("a") != Ok("b")

    def test_pattern_match_ok(self) -> None:
        match Ok(42):
            case Ok(v):
                assert v == 42
            case _:
                pytest.fail("Should match Ok")


class TestErrBasics:
    def test_err_holds_error(self) -> None:
        assert Err("fail").error == "fail"

    def test_err_holds_int(self) -> None:
        assert Err(404).error == 404

    def test_err_is_frozen(self) -> None:
        err = Err("fail")
        with pytest.raises(dataclasses.FrozenInstanceError):
            err.error = "other"  # type: ignore[misc]

    def test_err_equality(self) -> None:
        assert Err("fail") == Err("fail")
        assert Err("a") != Err("b")

    def test_pattern_match_err(self) -> None:
        match Err("fail"):
            case Err(e):
                assert e == "fail"
            case _:
                pytest.fail("Should match Err")


class TestResultTypeAlias:
    def test_ok_is_not_err(self) -> None:
        ok: Ok[int] = Ok(1)
        assert isinstance(ok, Ok)
        assert not isinstance(ok, Err)

    def test_err_is_not_ok(self) -> None:
        err: Err[str] = Err("fail")
        assert isinstance(err, Err)
        assert not isinstance(err, Ok)


# ---------------------------------------------------------------------------
# .map() — GAP-21
# ---------------------------------------------------------------------------


class TestMap:
    def test_ok_map_applies_function(self) -> None:
        assert Ok(5).map(lambda x: x * 2) == Ok(10)

    def test_ok_map_changes_type(self) -> None:
        assert Ok(42).map(str) == Ok("42")

    def test_err_map_passthrough(self) -> None:
        result = Err("fail").map(lambda x: x * 2)
        assert result == Err("fail")


# ---------------------------------------------------------------------------
# .bind() / .and_then() — GAP-22
# ---------------------------------------------------------------------------


def _safe_div(x: int) -> Ok[float] | Err[str]:
    if x == 0:
        return Err("division by zero")
    return Ok(10.0 / x)


class TestBind:
    def test_ok_bind_returns_ok(self) -> None:
        assert Ok(5).bind(_safe_div) == Ok(2.0)

    def test_ok_bind_returns_err(self) -> None:
        assert Ok(0).bind(_safe_div) == Err("division by zero")

    def test_err_bind_passthrough(self) -> None:
        result = Err("initial").bind(_safe_div)
        assert result == Err("initial")

    def test_and_then_is_bind_alias(self) -> None:
        assert Ok(5).and_then(_safe_div) == Ok(2.0)
        assert Err("e").and_then(_safe_div) == Err("e")


# ---------------------------------------------------------------------------
# .unwrap() and .unwrap_or() — GAP-23
# ---------------------------------------------------------------------------


class TestUnwrap:
    def test_ok_unwrap(self) -> None:
        assert Ok(42).unwrap() == 42

    def test_err_unwrap_raises(self) -> None:
        with pytest.raises(RuntimeError, match="Called unwrap on Err"):
            Err("fail").unwrap()

    def test_ok_unwrap_or_returns_value(self) -> None:
        assert Ok(42).unwrap_or(0) == 42

    def test_err_unwrap_or_returns_default(self) -> None:
        assert Err("fail").unwrap_or(0) == 0


# ---------------------------------------------------------------------------
# .map_err() — GAP-24
# ---------------------------------------------------------------------------


class TestMapErr:
    def test_ok_map_err_passthrough(self) -> None:
        result = Ok(42).map_err(str.upper)
        assert result == Ok(42)

    def test_err_map_err_transforms(self) -> None:
        result = Err("error").map_err(str.upper)
        assert result == Err("ERROR")


# ---------------------------------------------------------------------------
# Free functions: unwrap, map_result, sequence — GAP-25
# ---------------------------------------------------------------------------


class TestFreeUnwrap:
    def test_unwrap_ok(self) -> None:
        assert unwrap(Ok(42)) == 42

    def test_unwrap_err_raises(self) -> None:
        with pytest.raises(RuntimeError, match="unwrap on Err"):
            unwrap(Err("fail"))


class TestMapResult:
    def test_map_result_ok(self) -> None:
        assert map_result(Ok(5), lambda x: x * 2) == Ok(10)

    def test_map_result_err(self) -> None:
        assert map_result(Err("e"), lambda x: x * 2) == Err("e")


class TestSequence:
    def test_sequence_all_ok(self) -> None:
        assert sequence([Ok(1), Ok(2), Ok(3)]) == Ok([1, 2, 3])

    def test_sequence_first_err(self) -> None:
        assert sequence([Ok(1), Err("e"), Ok(3)]) == Err("e")

    def test_sequence_empty(self) -> None:
        assert sequence([]) == Ok([])

    def test_sequence_short_circuits(self) -> None:
        """After Err, remaining items are not consumed."""
        consumed: list[int] = []

        def gen() -> list[Ok[int] | Err[str]]:
            consumed.append(1)
            yield Ok(1)  # type: ignore[misc]
            consumed.append(2)
            yield Err("stop")  # type: ignore[misc]
            consumed.append(3)
            yield Ok(3)  # type: ignore[misc]

        result = sequence(gen())
        assert result == Err("stop")
        assert consumed == [1, 2]  # 3 was never reached


# ---------------------------------------------------------------------------
# Property-based tests (Hypothesis)
# ---------------------------------------------------------------------------


class TestMonadLaws:
    @given(st.integers())
    def test_map_identity_law(self, x: int) -> None:
        """result.map(id) == result"""
        assert Ok(x).map(lambda v: v) == Ok(x)

    @given(st.integers())
    def test_map_composition_law(self, x: int) -> None:
        """result.map(f).map(g) == result.map(lambda v: g(f(v)))"""
        f = lambda v: v + 1  # noqa: E731
        g = lambda v: v * 2  # noqa: E731
        assert Ok(x).map(f).map(g) == Ok(x).map(lambda v: g(f(v)))

    @given(st.integers())
    def test_bind_left_identity(self, x: int) -> None:
        """Ok(x).bind(f) == f(x)"""
        assert Ok(x).bind(_safe_div) == _safe_div(x)

    @given(st.text())
    def test_err_map_identity(self, e: str) -> None:
        """Err(e).map(anything) == Err(e)"""
        assert Err(e).map(lambda v: v * 2) == Err(e)
