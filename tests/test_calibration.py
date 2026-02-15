"""Tests for attestor.oracle.calibration — yield curves, ModelConfig, calibration."""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, Ok, unwrap
from attestor.oracle.attestation import DerivedConfidence
from attestor.oracle.calibration import (
    CalibrationResult,
    FailedCalibrationRecord,
    ModelConfig,
    RateInstrument,
    YieldCurve,
    bootstrap_curve,
    create_model_config_attestation,
    discount_factor,
    forward_rate,
    handle_calibration_failure,
)

_TS = datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC)


def _sample_config() -> ModelConfig:
    return unwrap(ModelConfig.create(
        config_id="CFG-001",
        model_class="PIECEWISE_LOG_LINEAR",
        code_version="1.0.0",
    ))


def _sample_curve() -> YieldCurve:
    return unwrap(YieldCurve.create(
        currency="USD",
        as_of=date(2025, 6, 15),
        tenors=(Decimal("0.25"), Decimal("0.5"), Decimal("1"), Decimal("2")),
        discount_factors=(Decimal("0.99"), Decimal("0.98"), Decimal("0.96"), Decimal("0.92")),
        model_config_ref="CFG-001",
    ))


# ---------------------------------------------------------------------------
# ModelConfig
# ---------------------------------------------------------------------------


class TestModelConfig:
    def test_create_valid(self) -> None:
        result = ModelConfig.create("CFG-001", "MODEL", "1.0")
        assert isinstance(result, Ok)

    def test_empty_id_err(self) -> None:
        assert isinstance(ModelConfig.create("", "MODEL", "1.0"), Err)

    def test_frozen(self) -> None:
        cfg = _sample_config()
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.config_id = NonEmptyStr(value="X")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# YieldCurve
# ---------------------------------------------------------------------------


class TestYieldCurve:
    def test_valid(self) -> None:
        curve = _sample_curve()
        assert len(curve.tenors) == 4

    def test_mismatched_lengths(self) -> None:
        result = YieldCurve.create(
            currency="USD", as_of=date(2025, 1, 1),
            tenors=(Decimal("0.25"),),
            discount_factors=(Decimal("0.99"), Decimal("0.98")),
            model_config_ref="CFG",
        )
        assert isinstance(result, Err)

    def test_unsorted_tenors(self) -> None:
        result = YieldCurve.create(
            currency="USD", as_of=date(2025, 1, 1),
            tenors=(Decimal("1"), Decimal("0.5")),
            discount_factors=(Decimal("0.96"), Decimal("0.98")),
            model_config_ref="CFG",
        )
        assert isinstance(result, Err)

    def test_negative_df(self) -> None:
        result = YieldCurve.create(
            currency="USD", as_of=date(2025, 1, 1),
            tenors=(Decimal("0.25"),),
            discount_factors=(Decimal("-0.5"),),
            model_config_ref="CFG",
        )
        assert isinstance(result, Err)

    def test_empty_tenors(self) -> None:
        result = YieldCurve.create(
            currency="USD", as_of=date(2025, 1, 1),
            tenors=(), discount_factors=(),
            model_config_ref="CFG",
        )
        assert isinstance(result, Err)

    def test_frozen(self) -> None:
        curve = _sample_curve()
        with pytest.raises(dataclasses.FrozenInstanceError):
            curve.as_of = date(2020, 1, 1)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# discount_factor / forward_rate
# ---------------------------------------------------------------------------


class TestDiscountFactor:
    def test_exact_point(self) -> None:
        curve = _sample_curve()
        d = unwrap(discount_factor(curve, Decimal("0.25")))
        assert d == Decimal("0.99")

    def test_d0_is_one(self) -> None:
        curve = _sample_curve()
        d = unwrap(discount_factor(curve, Decimal("0")))
        assert d == Decimal("1")

    def test_interpolation(self) -> None:
        curve = _sample_curve()
        d = unwrap(discount_factor(curve, Decimal("0.75")))
        assert Decimal("0.96") < d < Decimal("0.99")


class TestForwardRate:
    def test_positive_normal_curve(self) -> None:
        curve = _sample_curve()
        f = unwrap(forward_rate(curve, Decimal("0.25"), Decimal("1")))
        assert f > 0

    def test_t2_before_t1_err(self) -> None:
        curve = _sample_curve()
        result = forward_rate(curve, Decimal("1"), Decimal("0.5"))
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# RateInstrument + bootstrap
# ---------------------------------------------------------------------------


class TestBootstrapCurve:
    def test_simple_bootstrap(self) -> None:
        instruments = (
            RateInstrument(
                instrument_type=NonEmptyStr(value="DEPOSIT"),
                tenor=Decimal("0.25"), rate=Decimal("0.04"),
                currency=NonEmptyStr(value="USD"),
            ),
            RateInstrument(
                instrument_type=NonEmptyStr(value="SWAP"),
                tenor=Decimal("1"), rate=Decimal("0.05"),
                currency=NonEmptyStr(value="USD"),
            ),
        )
        result = bootstrap_curve(instruments, _sample_config(), date(2025, 6, 15), "USD")
        assert isinstance(result, Ok)
        att = unwrap(result)
        assert isinstance(att.confidence, DerivedConfidence)

    def test_empty_instruments_err(self) -> None:
        result = bootstrap_curve((), _sample_config(), date(2025, 6, 15), "USD")
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# ModelConfig attestation (III-06)
# ---------------------------------------------------------------------------


class TestModelConfigAttestation:
    def test_valid(self) -> None:
        cfg = _sample_config()
        result = create_model_config_attestation(cfg, "CALIBRATION", _TS)
        assert isinstance(result, Ok)

    def test_provenance(self) -> None:
        cfg = _sample_config()
        att = unwrap(create_model_config_attestation(cfg, "CALIBRATION", _TS))
        assert att.content_hash != ""


# ---------------------------------------------------------------------------
# Calibration failure (III-08)
# ---------------------------------------------------------------------------


class TestCalibrationFailure:
    def test_fallback_to_last_good(self) -> None:
        """When calibration fails with a last_good, return it."""
        instruments = (
            RateInstrument(
                instrument_type=NonEmptyStr(value="DEPOSIT"),
                tenor=Decimal("0.25"), rate=Decimal("0.04"),
                currency=NonEmptyStr(value="USD"),
            ),
        )
        last_good = unwrap(bootstrap_curve(
            instruments, _sample_config(), date(2025, 6, 15), "USD",
        ))
        result = handle_calibration_failure(
            error_reason="monotonicity violated",
            model_config=_sample_config(),
            last_good=last_good,
            timestamp=_TS,
        )
        assert isinstance(result, Ok)
        assert unwrap(result) is last_good

    def test_no_fallback_err(self) -> None:
        result = handle_calibration_failure(
            error_reason="monotonicity violated",
            model_config=_sample_config(),
            last_good=None,
            timestamp=_TS,
        )
        assert isinstance(result, Err)

    def test_calibration_result_type(self) -> None:
        cr = CalibrationResult(
            curve=_sample_curve(),
            model_config=_sample_config(),
            passed=True,
        )
        assert cr.passed is True

    def test_failed_calibration_record(self) -> None:
        from attestor.core.types import UtcDatetime
        rec = FailedCalibrationRecord(
            model_class=NonEmptyStr(value="PIECEWISE_LOG_LINEAR"),
            reason=NonEmptyStr(value="AF-YC-03 failed"),
            fallback_config_ref="CFG-001",
            timestamp=UtcDatetime.now(),
        )
        assert rec.reason.value == "AF-YC-03 failed"
