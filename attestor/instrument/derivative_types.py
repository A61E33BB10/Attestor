"""Derivative instrument types — options, futures, and supporting enums.

All types are @final @dataclass(frozen=True, slots=True). Smart constructors
return Ok | Err for validated creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import final

from attestor.core.money import NonEmptyStr, PositiveDecimal
from attestor.core.result import Err, Ok

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OptionType(Enum):
    CALL = "CALL"
    PUT = "PUT"


class OptionStyle(Enum):
    EUROPEAN = "EUROPEAN"
    AMERICAN = "AMERICAN"


class SettlementType(Enum):
    """Physical delivery or cash settlement."""

    PHYSICAL = "PHYSICAL"
    CASH = "CASH"


class MarginType(Enum):
    """Variation or initial margin."""

    VARIATION = "VARIATION"
    INITIAL = "INITIAL"


# ---------------------------------------------------------------------------
# PayoutSpec types
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class OptionPayoutSpec:
    """Vanilla option payout specification."""

    underlying_id: NonEmptyStr
    strike: PositiveDecimal
    expiry_date: date
    option_type: OptionType
    option_style: OptionStyle
    settlement_type: SettlementType
    currency: NonEmptyStr
    exchange: NonEmptyStr
    multiplier: PositiveDecimal  # typically 100

    @staticmethod
    def create(
        underlying_id: str,
        strike: Decimal,
        expiry_date: date,
        option_type: OptionType,
        option_style: OptionStyle,
        settlement_type: SettlementType,
        currency: str,
        exchange: str,
        multiplier: Decimal = Decimal("100"),
    ) -> Ok[OptionPayoutSpec] | Err[str]:
        match NonEmptyStr.parse(underlying_id):
            case Err(e):
                return Err(f"OptionPayoutSpec.underlying_id: {e}")
            case Ok(uid):
                pass
        match PositiveDecimal.parse(strike):
            case Err(e):
                return Err(f"OptionPayoutSpec.strike: {e}")
            case Ok(s):
                pass
        match NonEmptyStr.parse(currency):
            case Err(e):
                return Err(f"OptionPayoutSpec.currency: {e}")
            case Ok(cur):
                pass
        match NonEmptyStr.parse(exchange):
            case Err(e):
                return Err(f"OptionPayoutSpec.exchange: {e}")
            case Ok(ex):
                pass
        match PositiveDecimal.parse(multiplier):
            case Err(e):
                return Err(f"OptionPayoutSpec.multiplier: {e}")
            case Ok(mul):
                pass
        return Ok(OptionPayoutSpec(
            underlying_id=uid, strike=s, expiry_date=expiry_date,
            option_type=option_type, option_style=option_style,
            settlement_type=settlement_type,
            currency=cur, exchange=ex, multiplier=mul,
        ))


@final
@dataclass(frozen=True, slots=True)
class FuturesPayoutSpec:
    """Listed futures payout specification."""

    underlying_id: NonEmptyStr
    expiry_date: date
    last_trading_date: date
    settlement_type: SettlementType
    contract_size: PositiveDecimal  # point value (USD per unit of price movement)
    currency: NonEmptyStr
    exchange: NonEmptyStr

    @staticmethod
    def create(
        underlying_id: str,
        expiry_date: date,
        last_trading_date: date,
        settlement_type: SettlementType,
        contract_size: Decimal,
        currency: str,
        exchange: str,
    ) -> Ok[FuturesPayoutSpec] | Err[str]:
        match NonEmptyStr.parse(underlying_id):
            case Err(e):
                return Err(f"FuturesPayoutSpec.underlying_id: {e}")
            case Ok(uid):
                pass
        if last_trading_date > expiry_date:
            return Err(
                f"FuturesPayoutSpec: last_trading_date ({last_trading_date}) "
                f"must be <= expiry_date ({expiry_date})"
            )
        match PositiveDecimal.parse(contract_size):
            case Err(e):
                return Err(f"FuturesPayoutSpec.contract_size: {e}")
            case Ok(cs):
                pass
        match NonEmptyStr.parse(currency):
            case Err(e):
                return Err(f"FuturesPayoutSpec.currency: {e}")
            case Ok(cur):
                pass
        match NonEmptyStr.parse(exchange):
            case Err(e):
                return Err(f"FuturesPayoutSpec.exchange: {e}")
            case Ok(ex):
                pass
        return Ok(FuturesPayoutSpec(
            underlying_id=uid, expiry_date=expiry_date,
            last_trading_date=last_trading_date,
            settlement_type=settlement_type,
            contract_size=cs, currency=cur, exchange=ex,
        ))


# ---------------------------------------------------------------------------
# InstrumentDetail (gateway-level discriminated union)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class EquityDetail:
    """Marker type for equity orders. No extra fields needed."""


@final
@dataclass(frozen=True, slots=True)
class OptionDetail:
    """Option-specific fields on a CanonicalOrder."""

    strike: PositiveDecimal
    expiry_date: date
    option_type: OptionType
    option_style: OptionStyle
    settlement_type: SettlementType
    underlying_id: NonEmptyStr
    multiplier: PositiveDecimal

    @staticmethod
    def create(
        strike: Decimal,
        expiry_date: date,
        option_type: OptionType,
        option_style: OptionStyle,
        settlement_type: SettlementType,
        underlying_id: str,
        multiplier: Decimal = Decimal("100"),
    ) -> Ok[OptionDetail] | Err[str]:
        match PositiveDecimal.parse(strike):
            case Err(e):
                return Err(f"OptionDetail.strike: {e}")
            case Ok(s):
                pass
        match NonEmptyStr.parse(underlying_id):
            case Err(e):
                return Err(f"OptionDetail.underlying_id: {e}")
            case Ok(uid):
                pass
        match PositiveDecimal.parse(multiplier):
            case Err(e):
                return Err(f"OptionDetail.multiplier: {e}")
            case Ok(mul):
                pass
        return Ok(OptionDetail(
            strike=s, expiry_date=expiry_date,
            option_type=option_type, option_style=option_style,
            settlement_type=settlement_type,
            underlying_id=uid, multiplier=mul,
        ))


@final
@dataclass(frozen=True, slots=True)
class FuturesDetail:
    """Futures-specific fields on a CanonicalOrder."""

    expiry_date: date
    contract_size: PositiveDecimal
    settlement_type: SettlementType
    underlying_id: NonEmptyStr

    @staticmethod
    def create(
        expiry_date: date,
        contract_size: Decimal,
        settlement_type: SettlementType,
        underlying_id: str,
    ) -> Ok[FuturesDetail] | Err[str]:
        match PositiveDecimal.parse(contract_size):
            case Err(e):
                return Err(f"FuturesDetail.contract_size: {e}")
            case Ok(cs):
                pass
        match NonEmptyStr.parse(underlying_id):
            case Err(e):
                return Err(f"FuturesDetail.underlying_id: {e}")
            case Ok(uid):
                pass
        return Ok(FuturesDetail(
            expiry_date=expiry_date, contract_size=cs,
            settlement_type=settlement_type, underlying_id=uid,
        ))


@final
@dataclass(frozen=True, slots=True)
class FXDetail:
    """FX order detail — covers spot, forward, and NDF."""

    currency_pair: str  # "EUR/USD" format, validated at gateway
    settlement_date: date
    settlement_type: SettlementType
    forward_rate: PositiveDecimal | None = None  # None for spot
    fixing_source: NonEmptyStr | None = None  # non-None for NDF
    fixing_date: date | None = None  # non-None for NDF

    @staticmethod
    def create(
        currency_pair: str,
        settlement_date: date,
        settlement_type: SettlementType,
        forward_rate: Decimal | None = None,
        fixing_source: str | None = None,
        fixing_date: date | None = None,
    ) -> Ok[FXDetail] | Err[str]:
        if not currency_pair or "/" not in currency_pair:
            return Err(f"FXDetail.currency_pair must be BASE/QUOTE, got '{currency_pair}'")
        fr: PositiveDecimal | None = None
        if forward_rate is not None:
            match PositiveDecimal.parse(forward_rate):
                case Err(e):
                    return Err(f"FXDetail.forward_rate: {e}")
                case Ok(f):
                    fr = f
        fs: NonEmptyStr | None = None
        if fixing_source is not None:
            match NonEmptyStr.parse(fixing_source):
                case Err(e):
                    return Err(f"FXDetail.fixing_source: {e}")
                case Ok(s):
                    fs = s
        if fixing_date is not None and fixing_date > settlement_date:
            return Err(
                f"FXDetail: fixing_date ({fixing_date}) "
                f"must be <= settlement_date ({settlement_date})"
            )
        return Ok(FXDetail(
            currency_pair=currency_pair, settlement_date=settlement_date,
            settlement_type=settlement_type, forward_rate=fr,
            fixing_source=fs, fixing_date=fixing_date,
        ))


@final
@dataclass(frozen=True, slots=True)
class IRSwapDetail:
    """IRS order detail on a CanonicalOrder."""

    fixed_rate: PositiveDecimal
    float_index: NonEmptyStr
    day_count: str  # "ACT/360", "ACT/365", "30/360"
    payment_frequency: str  # "MONTHLY", "QUARTERLY", etc.
    tenor_months: int
    start_date: date
    end_date: date

    @staticmethod
    def create(
        fixed_rate: Decimal,
        float_index: str,
        day_count: str,
        payment_frequency: str,
        tenor_months: int,
        start_date: date,
        end_date: date,
    ) -> Ok[IRSwapDetail] | Err[str]:
        match PositiveDecimal.parse(fixed_rate):
            case Err(e):
                return Err(f"IRSwapDetail.fixed_rate: {e}")
            case Ok(fr):
                pass
        match NonEmptyStr.parse(float_index):
            case Err(e):
                return Err(f"IRSwapDetail.float_index: {e}")
            case Ok(fi):
                pass
        if tenor_months <= 0:
            return Err(f"IRSwapDetail.tenor_months must be > 0, got {tenor_months}")
        if start_date >= end_date:
            return Err(
                f"IRSwapDetail: start_date ({start_date}) "
                f"must be < end_date ({end_date})"
            )
        return Ok(IRSwapDetail(
            fixed_rate=fr, float_index=fi, day_count=day_count,
            payment_frequency=payment_frequency, tenor_months=tenor_months,
            start_date=start_date, end_date=end_date,
        ))


type InstrumentDetail = EquityDetail | OptionDetail | FuturesDetail | FXDetail | IRSwapDetail
