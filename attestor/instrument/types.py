"""Instrument model types — Party, EquityPayoutSpec, EconomicTerms, Product, Instrument.

Phase 1: Cash equities and ETFs only. Phase 2 extends EconomicTerms.payout
to a union of EquityPayoutSpec | OptionPayoutSpec | FuturesPayoutSpec.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import final

from attestor.core.identifiers import LEI
from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, Ok


class PositionStatusEnum(Enum):
    """Lifecycle states for a trade/position."""

    PROPOSED = "Proposed"
    FORMED = "Formed"
    SETTLED = "Settled"
    CANCELLED = "Cancelled"
    CLOSED = "Closed"


@final
@dataclass(frozen=True, slots=True)
class Party:
    """Counterparty or executing party."""

    party_id: NonEmptyStr
    name: NonEmptyStr
    lei: LEI

    @staticmethod
    def create(party_id: str, name: str, lei: str) -> Ok[Party] | Err[str]:
        match NonEmptyStr.parse(party_id):
            case Err(e):
                return Err(f"Party.party_id: {e}")
            case Ok(pid):
                pass
        match NonEmptyStr.parse(name):
            case Err(e):
                return Err(f"Party.name: {e}")
            case Ok(n):
                pass
        match LEI.parse(lei):
            case Err(e):
                return Err(f"Party.lei: {e}")
            case Ok(l_):
                pass
        return Ok(Party(party_id=pid, name=n, lei=l_))


@final
@dataclass(frozen=True, slots=True)
class EquityPayoutSpec:
    """Cash equity or ETF payout specification."""

    instrument_id: NonEmptyStr
    currency: NonEmptyStr
    exchange: NonEmptyStr

    @staticmethod
    def create(
        instrument_id: str, currency: str, exchange: str,
    ) -> Ok[EquityPayoutSpec] | Err[str]:
        match NonEmptyStr.parse(instrument_id):
            case Err(e):
                return Err(f"EquityPayoutSpec.instrument_id: {e}")
            case Ok(iid):
                pass
        match NonEmptyStr.parse(currency):
            case Err(e):
                return Err(f"EquityPayoutSpec.currency: {e}")
            case Ok(cur):
                pass
        match NonEmptyStr.parse(exchange):
            case Err(e):
                return Err(f"EquityPayoutSpec.exchange: {e}")
            case Ok(ex):
                pass
        return Ok(EquityPayoutSpec(instrument_id=iid, currency=cur, exchange=ex))


@final
@dataclass(frozen=True, slots=True)
class EconomicTerms:
    """Economic terms of an instrument. Phase 1: equity payout only."""

    payout: EquityPayoutSpec
    effective_date: date
    termination_date: date | None  # None for perpetual equities


@final
@dataclass(frozen=True, slots=True)
class Product:
    """Product wrapping economic terms."""

    economic_terms: EconomicTerms


@final
@dataclass(frozen=True, slots=True)
class Instrument:
    """A tradeable instrument with its parties and lifecycle status."""

    instrument_id: NonEmptyStr
    product: Product
    parties: tuple[Party, ...]
    trade_date: date
    status: PositionStatusEnum


def create_equity_instrument(
    instrument_id: str,
    currency: str,
    exchange: str,
    parties: tuple[Party, ...],
    trade_date: date,
) -> Ok[Instrument] | Err[str]:
    """Create an equity Instrument from basic parameters."""
    match EquityPayoutSpec.create(instrument_id, currency, exchange):
        case Err(e):
            return Err(e)
        case Ok(payout):
            pass
    match NonEmptyStr.parse(instrument_id):
        case Err(e):
            return Err(f"Instrument.instrument_id: {e}")
        case Ok(iid):
            pass
    terms = EconomicTerms(payout=payout, effective_date=trade_date, termination_date=None)
    product = Product(economic_terms=terms)
    return Ok(Instrument(
        instrument_id=iid,
        product=product,
        parties=parties,
        trade_date=trade_date,
        status=PositionStatusEnum.PROPOSED,
    ))
