"""Tests for attestor.core.errors — Error value hierarchy."""

from __future__ import annotations

import dataclasses
import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from attestor.core.errors import (
    AttestorError,
    CalibrationError,
    ConservationViolationError,
    FieldViolation,
    IllegalTransitionError,
    MissingObservableError,
    PersistenceError,
    PricingError,
    ValidationError,
)
from attestor.core.types import UtcDatetime


def _ts() -> UtcDatetime:
    return UtcDatetime.now()


def _base() -> AttestorError:
    return AttestorError(message="base error", code="E001", timestamp=_ts(), source="test.fn")


# ---------------------------------------------------------------------------
# AttestorError base
# ---------------------------------------------------------------------------


class TestAttestorError:
    def test_is_frozen(self) -> None:
        err = _base()
        with pytest.raises(dataclasses.FrozenInstanceError):
            err.message = "changed"  # type: ignore[misc]

    def test_to_dict_keys(self) -> None:
        d = _base().to_dict()
        assert set(d.keys()) == {"message", "code", "timestamp", "source"}

    def test_to_dict_json_serializable(self) -> None:
        json.dumps(_base().to_dict())  # should not raise


class TestFieldViolation:
    def test_is_frozen(self) -> None:
        fv = FieldViolation(
            path="trade.notional", constraint="must be positive", actual_value="-100",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            fv.path = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# .with_context() — GAP-29
# ---------------------------------------------------------------------------


class TestWithContext:
    def test_prepends_context(self) -> None:
        err = _base()
        ctx_err = err.with_context("trade TX-1")
        assert ctx_err.message == "trade TX-1: base error"

    def test_preserves_subclass(self) -> None:
        ve = ValidationError(
            message="bad", code="V001", timestamp=_ts(), source="val.fn",
            fields=(FieldViolation("f", "c", "v"),),
        )
        ctx_ve = ve.with_context("ctx")
        assert isinstance(ctx_ve, ValidationError)

    def test_preserves_fields(self) -> None:
        fv = FieldViolation("f", "c", "v")
        ve = ValidationError(
            message="bad", code="V001", timestamp=_ts(), source="val.fn",
            fields=(fv,),
        )
        ctx_ve = ve.with_context("ctx")
        assert isinstance(ctx_ve, ValidationError)
        assert ctx_ve.fields == (fv,)

    def test_preserves_other_base_fields(self) -> None:
        err = _base()
        ctx_err = err.with_context("ctx")
        assert ctx_err.code == err.code
        assert ctx_err.source == err.source
        assert ctx_err.timestamp == err.timestamp


# ---------------------------------------------------------------------------
# Subclasses — fields and to_dict keys (GAP-30)
# ---------------------------------------------------------------------------


class TestValidationError:
    def test_has_fields(self) -> None:
        fv = FieldViolation("trade.notional", "must be positive", "-100")
        ve = ValidationError(
            message="validation failed", code="V001", timestamp=_ts(),
            source="val.fn", fields=(fv,),
        )
        assert ve.fields == (fv,)

    def test_to_dict_keys(self) -> None:
        ve = ValidationError(
            message="bad", code="V001", timestamp=_ts(), source="val.fn",
            fields=(FieldViolation("f", "c", "v"),),
        )
        d = ve.to_dict()
        assert set(d.keys()) == {"message", "code", "timestamp", "source", "fields"}

    def test_inherits_from_attestor_error(self) -> None:
        ve = ValidationError(
            message="bad", code="V001", timestamp=_ts(), source="v",
            fields=(),
        )
        assert isinstance(ve, AttestorError)


class TestIllegalTransitionError:
    def test_fields(self) -> None:
        err = IllegalTransitionError(
            message="bad transition", code="T001", timestamp=_ts(),
            source="sm.fn", from_state="OPEN", to_state="CANCELLED",
        )
        assert err.from_state == "OPEN"
        assert err.to_state == "CANCELLED"

    def test_to_dict_keys(self) -> None:
        err = IllegalTransitionError(
            message="m", code="c", timestamp=_ts(), source="s",
            from_state="A", to_state="B",
        )
        assert set(err.to_dict().keys()) == {
            "message", "code", "timestamp", "source", "from_state", "to_state",
        }


class TestConservationViolationError:
    def test_fields(self) -> None:
        err = ConservationViolationError(
            message="m", code="c", timestamp=_ts(), source="s",
            law_name="double_entry", expected="0", actual="100",
        )
        assert err.law_name == "double_entry"

    def test_to_dict_keys(self) -> None:
        err = ConservationViolationError(
            message="m", code="c", timestamp=_ts(), source="s",
            law_name="l", expected="e", actual="a",
        )
        assert set(err.to_dict().keys()) == {
            "message", "code", "timestamp", "source", "law_name", "expected", "actual",
        }


class TestMissingObservableError:
    def test_to_dict_keys(self) -> None:
        err = MissingObservableError(
            message="m", code="c", timestamp=_ts(), source="s",
            observable="EUR/USD", as_of="2024-01-15",
        )
        assert set(err.to_dict().keys()) == {
            "message", "code", "timestamp", "source", "observable", "as_of",
        }


class TestCalibrationError:
    def test_to_dict_keys(self) -> None:
        err = CalibrationError(
            message="m", code="c", timestamp=_ts(), source="s",
            model="SABR",
        )
        assert set(err.to_dict().keys()) == {
            "message", "code", "timestamp", "source", "model",
        }


class TestPricingError:
    def test_to_dict_keys(self) -> None:
        err = PricingError(
            message="m", code="c", timestamp=_ts(), source="s",
            instrument="AAPL-CALL-2024", reason="missing vol",
        )
        assert set(err.to_dict().keys()) == {
            "message", "code", "timestamp", "source", "instrument", "reason",
        }


class TestPersistenceError:
    def test_to_dict_keys(self) -> None:
        err = PersistenceError(
            message="m", code="c", timestamp=_ts(), source="s",
            operation="INSERT",
        )
        assert set(err.to_dict().keys()) == {
            "message", "code", "timestamp", "source", "operation",
        }


# ---------------------------------------------------------------------------
# All errors JSON-serializable and inherit from AttestorError
# ---------------------------------------------------------------------------


_ALL_ERROR_INSTANCES = [
    lambda: AttestorError(message="m", code="c", timestamp=_ts(), source="s"),
    lambda: ValidationError(
        message="m", code="c", timestamp=_ts(), source="s",
        fields=(FieldViolation("p", "c", "v"),),
    ),
    lambda: IllegalTransitionError(
        message="m", code="c", timestamp=_ts(), source="s",
        from_state="A", to_state="B",
    ),
    lambda: ConservationViolationError(
        message="m", code="c", timestamp=_ts(), source="s",
        law_name="l", expected="e", actual="a",
    ),
    lambda: MissingObservableError(
        message="m", code="c", timestamp=_ts(), source="s",
        observable="o", as_of="d",
    ),
    lambda: CalibrationError(
        message="m", code="c", timestamp=_ts(), source="s", model="M",
    ),
    lambda: PricingError(
        message="m", code="c", timestamp=_ts(), source="s",
        instrument="I", reason="R",
    ),
    lambda: PersistenceError(
        message="m", code="c", timestamp=_ts(), source="s", operation="O",
    ),
]


class TestAllErrors:
    @pytest.mark.parametrize("factory", _ALL_ERROR_INSTANCES, ids=lambda f: f().__class__.__name__)
    def test_json_serializable(self, factory: object) -> None:
        err = factory()  # type: ignore[operator]
        json.dumps(err.to_dict())  # should not raise

    @pytest.mark.parametrize(
        "factory", _ALL_ERROR_INSTANCES[1:], ids=lambda f: f().__class__.__name__,
    )
    def test_inherits_from_attestor_error(self, factory: object) -> None:
        err = factory()  # type: ignore[operator]
        assert isinstance(err, AttestorError)


# ---------------------------------------------------------------------------
# Property-based
# ---------------------------------------------------------------------------


class TestProperties:
    @given(msg=st.text(min_size=1), ctx=st.text(min_size=1))
    def test_with_context_format(self, msg: str, ctx: str) -> None:
        err = AttestorError(message=msg, code="E", timestamp=_ts(), source="s")
        assert err.with_context(ctx).message == f"{ctx}: {msg}"

    @given(msg=st.text(min_size=1))
    def test_to_dict_always_has_base_keys(self, msg: str) -> None:
        err = AttestorError(message=msg, code="E", timestamp=_ts(), source="s")
        d = err.to_dict()
        assert {"message", "code", "timestamp", "source"} <= set(d.keys())
