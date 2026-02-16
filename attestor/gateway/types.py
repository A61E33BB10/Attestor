"""Gateway types — normalised order, output of Pillar I.

CanonicalOrder is the single canonical representation of a trade entering the system.
Every downstream pillar consumes this type.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import final

from attestor.core.errors import FieldViolation, ValidationError
from attestor.core.identifiers import ISIN, LEI
from attestor.core.money import NonEmptyStr, PositiveDecimal
from attestor.core.result import Err, Ok
from attestor.core.types import UtcDatetime
from attestor.instrument.derivative_types import (
    CDSDetail,
    EquityDetail,
    FuturesDetail,
    FXDetail,
    InstrumentDetail,
    IRSwapDetail,
    OptionDetail,
    SwaptionDetail,
)

_DEFAULT_EQUITY_DETAIL = EquityDetail()


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


def _parse_nonempty(
    raw: str, path: str, violations: list[FieldViolation],
) -> NonEmptyStr | None:
    match NonEmptyStr.parse(raw):
        case Ok(v):
            return v
        case Err(_):
            violations.append(FieldViolation(
                path=path, constraint="must be non-empty", actual_value=repr(raw),
            ))
            return None


def _parse_lei(
    raw: str, path: str, violations: list[FieldViolation],
) -> LEI | None:
    match LEI.parse(raw):
        case Ok(v):
            return v
        case Err(e):
            violations.append(FieldViolation(path=path, constraint=e, actual_value=raw))
            return None


@final
@dataclass(frozen=True, slots=True)
class CanonicalOrder:
    """Normalised order — output of Gateway, input to Ledger."""

    order_id: NonEmptyStr
    instrument_id: NonEmptyStr
    isin: ISIN | None
    side: OrderSide
    quantity: PositiveDecimal
    price: Decimal
    currency: NonEmptyStr
    order_type: OrderType
    counterparty_lei: LEI
    executing_party_lei: LEI
    trade_date: date
    settlement_date: date
    venue: NonEmptyStr
    timestamp: UtcDatetime
    instrument_detail: InstrumentDetail = _DEFAULT_EQUITY_DETAIL

    @staticmethod
    def create(
        *,
        order_id: str,
        instrument_id: str,
        isin: str | None,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal,
        currency: str,
        order_type: OrderType,
        counterparty_lei: str,
        executing_party_lei: str,
        trade_date: date,
        settlement_date: date,
        venue: str,
        timestamp: UtcDatetime,
        instrument_detail: InstrumentDetail = _DEFAULT_EQUITY_DETAIL,
    ) -> Ok[CanonicalOrder] | Err[ValidationError]:
        """Validate all fields and return Result."""
        violations: list[FieldViolation] = []

        oid = _parse_nonempty(order_id, "order_id", violations)
        iid = _parse_nonempty(instrument_id, "instrument_id", violations)
        cur = _parse_nonempty(currency, "currency", violations)
        ven = _parse_nonempty(venue, "venue", violations)
        cp_lei = _parse_lei(counterparty_lei, "counterparty_lei", violations)
        ep_lei = _parse_lei(executing_party_lei, "executing_party_lei", violations)

        # ISIN (optional)
        parsed_isin: ISIN | None = None
        if isin is not None:
            match ISIN.parse(isin):
                case Err(e):
                    violations.append(FieldViolation(
                        path="isin", constraint=e, actual_value=isin,
                    ))
                case Ok(i):
                    parsed_isin = i

        # Quantity (must be > 0)
        qty: PositiveDecimal | None = None
        match PositiveDecimal.parse(quantity):
            case Err(_):
                violations.append(FieldViolation(
                    path="quantity", constraint="must be > 0", actual_value=str(quantity),
                ))
            case Ok(q):
                qty = q

        # Price (must be finite)
        if not isinstance(price, Decimal) or not price.is_finite():
            violations.append(FieldViolation(
                path="price", constraint="must be finite Decimal", actual_value=str(price),
            ))

        # Settlement date >= trade date
        if settlement_date < trade_date:
            violations.append(FieldViolation(
                path="settlement_date",
                constraint="must be >= trade_date",
                actual_value=f"{settlement_date} < {trade_date}",
            ))

        # Derivative expiry must be after trade date
        match instrument_detail:
            case OptionDetail(expiry_date=exp):
                if exp <= trade_date:
                    violations.append(FieldViolation(
                        path="instrument_detail.expiry_date",
                        constraint="must be > trade_date",
                        actual_value=f"{exp} <= {trade_date}",
                    ))
            case FuturesDetail(expiry_date=exp):
                if exp <= trade_date:
                    violations.append(FieldViolation(
                        path="instrument_detail.expiry_date",
                        constraint="must be > trade_date",
                        actual_value=f"{exp} <= {trade_date}",
                    ))
            case EquityDetail():
                pass
            case FXDetail():
                pass  # FX date validation handled at payout level
            case IRSwapDetail():
                pass  # IRS date validation handled at payout level
            case CDSDetail():
                pass  # CDS date validation handled at payout level
            case SwaptionDetail(expiry_date=exp):
                if exp <= trade_date:
                    violations.append(FieldViolation(
                        path="instrument_detail.expiry_date",
                        constraint="must be > trade_date",
                        actual_value=f"{exp} <= {trade_date}",
                    ))

        if violations:
            return Err(ValidationError(
                message=f"CanonicalOrder validation failed: {len(violations)} violation(s)",
                code="GATEWAY_VALIDATION",
                timestamp=timestamp,
                source="gateway.types.CanonicalOrder.create",
                fields=tuple(violations),
            ))

        # All valid — None checks are safe because violations would have been collected above
        assert oid is not None and iid is not None and cur is not None and ven is not None
        assert cp_lei is not None and ep_lei is not None and qty is not None

        return Ok(CanonicalOrder(
            order_id=oid,
            instrument_id=iid,
            isin=parsed_isin,
            side=side,
            quantity=qty,
            price=price,
            currency=cur,
            order_type=order_type,
            counterparty_lei=cp_lei,
            executing_party_lei=ep_lei,
            trade_date=trade_date,
            settlement_date=settlement_date,
            venue=ven,
            timestamp=timestamp,
            instrument_detail=instrument_detail,
        ))
