"""Hypothesis strategies and pytest fixtures for Attestor Phase 0.

Every Phase 0 domain type has a corresponding Hypothesis strategy.
Strategies are composable: complex types are built from simpler types.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy

from attestor.core.money import (
    Money,
    NonEmptyStr,
    NonZeroDecimal,
    PositiveDecimal,
)
from attestor.core.result import unwrap
from attestor.core.types import (
    BitemporalEnvelope,
    FrozenMap,
    IdempotencyKey,
    UtcDatetime,
)
from attestor.oracle.attestation import (
    Attestation,
    Confidence,
    DerivedConfidence,
    FirmConfidence,
    QuotedConfidence,
    create_attestation,
)

# ---------------------------------------------------------------------------
# Hypothesis global settings
# ---------------------------------------------------------------------------

settings.register_profile(
    "ci",
    max_examples=200,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
settings.register_profile(
    "dev",
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
settings.load_profile("dev")


# ===================================================================
# PRIMITIVE STRATEGIES
# ===================================================================


def finite_decimals(
    min_value: str = "-1000000",
    max_value: str = "1000000",
    places: int = 6,
) -> SearchStrategy[Decimal]:
    """Finite Decimal values, no NaN, no Infinity."""
    return st.decimals(
        min_value=Decimal(min_value),
        max_value=Decimal(max_value),
        places=places,
        allow_nan=False,
        allow_infinity=False,
    )


def positive_decimals(
    min_value: str = "0.000001",
    max_value: str = "1000000",
    places: int = 6,
) -> SearchStrategy[Decimal]:
    """Strictly positive Decimal values."""
    return st.decimals(
        min_value=Decimal(min_value),
        max_value=Decimal(max_value),
        places=places,
        allow_nan=False,
        allow_infinity=False,
    ).filter(lambda d: d > 0)


def nonzero_decimals(
    min_value: str = "-1000000",
    max_value: str = "1000000",
    places: int = 6,
) -> SearchStrategy[Decimal]:
    """Non-zero Decimal values."""
    return finite_decimals(min_value, max_value, places).filter(lambda d: d != 0)


def aware_datetimes(
    min_year: int = 2020,
    max_year: int = 2030,
) -> SearchStrategy[datetime]:
    """Timezone-aware UTC datetimes."""
    return st.datetimes(
        min_value=datetime(min_year, 1, 1),
        max_value=datetime(max_year, 12, 31, 23, 59, 59),
        timezones=st.just(UTC),
    )


def nonempty_text(
    min_size: int = 1,
    max_size: int = 50,
) -> SearchStrategy[str]:
    """Non-empty printable ASCII strings (stripped)."""
    return st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
        min_size=min_size,
        max_size=max_size,
    ).map(str.strip).filter(bool)


CURRENCIES = ("USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "SEK")


def currency_codes() -> SearchStrategy[str]:
    """ISO 4217-ish currency codes."""
    return st.sampled_from(CURRENCIES)


def hex_hashes() -> SearchStrategy[str]:
    """64-character hex strings (SHA-256 digests)."""
    return st.text(alphabet="0123456789abcdef", min_size=64, max_size=64)


# ===================================================================
# CORE TYPE STRATEGIES
# ===================================================================


@st.composite
def non_empty_strs(draw: st.DrawFn) -> NonEmptyStr:
    """Generate valid NonEmptyStr instances."""
    raw = draw(nonempty_text())
    return unwrap(NonEmptyStr.parse(raw))


@st.composite
def positive_decimal_values(draw: st.DrawFn) -> PositiveDecimal:
    """Generate valid PositiveDecimal instances."""
    raw = draw(positive_decimals())
    return unwrap(PositiveDecimal.parse(raw))


@st.composite
def nonzero_decimal_values(draw: st.DrawFn) -> NonZeroDecimal:
    """Generate valid NonZeroDecimal instances."""
    raw = draw(nonzero_decimals())
    return unwrap(NonZeroDecimal.parse(raw))


@st.composite
def frozen_maps_str_decimal(
    draw: st.DrawFn,
    min_size: int = 1,
    max_size: int = 5,
) -> FrozenMap[str, Decimal]:
    """Generate FrozenMap[str, Decimal] with at least one entry."""
    entries = draw(
        st.dictionaries(
            nonempty_text(max_size=10),
            finite_decimals(min_value="0", max_value="1", places=4),
            min_size=min_size,
            max_size=max_size,
        )
    )
    return unwrap(FrozenMap.create(entries))


@st.composite
def money(draw: st.DrawFn) -> Money:
    """Generate valid Money instances."""
    amount = draw(finite_decimals(min_value="-1000000", max_value="1000000", places=2))
    cur = draw(currency_codes())
    return unwrap(Money.create(amount, cur))


@st.composite
def idempotency_keys(draw: st.DrawFn) -> IdempotencyKey:
    """Generate valid IdempotencyKey instances."""
    raw = draw(nonempty_text())
    return unwrap(IdempotencyKey.create(raw))


@st.composite
def utc_datetimes(draw: st.DrawFn) -> UtcDatetime:
    """Generate UtcDatetime values."""
    dt = draw(aware_datetimes())
    return unwrap(UtcDatetime.parse(dt))


_DEFAULT_PAYLOAD: SearchStrategy[Any] = st.integers()


@st.composite
def bitemporal_envelopes(
    draw: st.DrawFn,
    payload_strategy: SearchStrategy[Any] = _DEFAULT_PAYLOAD,
) -> BitemporalEnvelope[Any]:
    """Generate BitemporalEnvelope with UTC timestamps."""
    return BitemporalEnvelope(
        payload=draw(payload_strategy),
        event_time=draw(utc_datetimes()),
        knowledge_time=draw(utc_datetimes()),
    )


# ===================================================================
# CONFIDENCE STRATEGIES (using factory methods)
# ===================================================================


@st.composite
def firm_confidences(draw: st.DrawFn) -> FirmConfidence:
    """Generate FirmConfidence via create factory."""
    source = draw(st.sampled_from(["NYSE", "LCH", "ICE", "CME", "Eurex"]))
    ts = draw(aware_datetimes())
    ref = draw(hex_hashes())
    return unwrap(FirmConfidence.create(source, ts, ref))


@st.composite
def quoted_confidences(draw: st.DrawFn) -> QuotedConfidence:
    """Generate QuotedConfidence with bid <= ask via create factory."""
    bid = draw(positive_decimals(min_value="0.01", max_value="999999", places=4))
    spread = draw(positive_decimals(min_value="0.0001", max_value="10", places=4))
    ask = bid + spread
    venue = draw(st.sampled_from(["Bloomberg", "ICE", "Reuters", "BGC"]))
    return unwrap(QuotedConfidence.create(bid=bid, ask=ask, venue=venue))


@st.composite
def derived_confidences(draw: st.DrawFn) -> DerivedConfidence:
    """Generate DerivedConfidence via create factory."""
    fq = draw(frozen_maps_str_decimal(min_size=1, max_size=3))
    method = draw(st.sampled_from(["BlackScholes", "SVI", "GPRegression", "SABR"]))
    config_ref = draw(hex_hashes())
    has_ci = draw(st.booleans())
    if has_ci:
        lower = draw(finite_decimals(min_value="0", max_value="100", places=4))
        upper = lower + draw(positive_decimals(min_value="0.001", max_value="50", places=4))
        ci: tuple[Decimal, Decimal] | None = (lower, upper)
        cl: Decimal | None = draw(
            st.sampled_from([Decimal("0.90"), Decimal("0.95"), Decimal("0.99")])
        )
    else:
        ci = None
        cl = None
    return unwrap(DerivedConfidence.create(
        method=method, config_ref=config_ref, fit_quality=fq,
        confidence_interval=ci, confidence_level=cl,
    ))


@st.composite
def confidences(draw: st.DrawFn) -> Confidence:
    """Generate exactly one Confidence variant (Firm | Quoted | Derived)."""
    return draw(st.one_of(
        firm_confidences(),
        quoted_confidences(),
        derived_confidences(),
    ))


# ===================================================================
# ATTESTATION STRATEGIES
# ===================================================================


@st.composite
def attestations(
    draw: st.DrawFn,
    value_strategy: SearchStrategy[Any] | None = None,
) -> Attestation[Any]:
    """Generate Attestation[T] via create_attestation factory."""
    if value_strategy is None:
        value_strategy = finite_decimals()
    value = draw(value_strategy)
    confidence = draw(confidences())
    source = draw(nonempty_text(max_size=30))
    timestamp = draw(aware_datetimes())
    num_provenance = draw(st.integers(min_value=0, max_value=3))
    provenance = tuple(
        draw(hex_hashes()) for _ in range(num_provenance)
    )
    return unwrap(create_attestation(
        value=value,
        confidence=confidence,
        source=source,
        timestamp=timestamp,
        provenance=provenance,
    ))


@st.composite
def firm_attestations(
    draw: st.DrawFn,
    value_strategy: SearchStrategy[Any] | None = None,
) -> Attestation[Any]:
    """Generate Attestation with FirmConfidence."""
    if value_strategy is None:
        value_strategy = finite_decimals()
    return unwrap(create_attestation(
        value=draw(value_strategy),
        confidence=draw(firm_confidences()),
        source=draw(nonempty_text(max_size=30)),
        timestamp=draw(aware_datetimes()),
        provenance=(),
    ))
