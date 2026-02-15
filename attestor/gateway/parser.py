"""Gateway parser — raw dict to CanonicalOrder.

parse_order is the single entry point for all external trade data.
INV-G01: idempotent. INV-G02: total (never panics).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from attestor.core.errors import FieldViolation, ValidationError
from attestor.core.result import Err, Ok
from attestor.core.types import UtcDatetime
from attestor.gateway.types import CanonicalOrder, OrderSide, OrderType


def _add_business_days(start: date, days: int) -> date:
    """Add business days (skip weekends only — Phase 1 simplification)."""
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon=0 .. Fri=4
            added += 1
    return current


def _extract_str(raw: dict[str, object], key: str) -> str | None:
    val = raw.get(key)
    if isinstance(val, str):
        return val
    return None


def _extract_date(raw: dict[str, object], key: str) -> date | None:
    val = raw.get(key)
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return date.fromisoformat(val)
        except ValueError:
            return None
    return None


def _extract_decimal(raw: dict[str, object], key: str) -> Decimal | None:
    val = raw.get(key)
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (int, str)):
        try:
            return Decimal(str(val))
        except InvalidOperation:
            return None
    return None


def _extract_datetime(raw: dict[str, object], key: str) -> datetime | None:
    val = raw.get(key)
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            return None
    return None


def parse_order(raw: dict[str, object]) -> Ok[CanonicalOrder] | Err[ValidationError]:
    """Parse a raw dict into a CanonicalOrder.

    INV-G01: idempotent — parse(to_dict(parse(raw))) == parse(raw).
    INV-G02: total — always returns Ok or Err, never panics.
    """
    violations: list[FieldViolation] = []

    # --- Required string fields ---
    order_id = _extract_str(raw, "order_id")
    if order_id is None:
        violations.append(FieldViolation(
            path="order_id", constraint="required string", actual_value=repr(raw.get("order_id")),
        ))
        order_id = ""

    instrument_id = _extract_str(raw, "instrument_id")
    if instrument_id is None:
        violations.append(FieldViolation(
            path="instrument_id", constraint="required string",
            actual_value=repr(raw.get("instrument_id")),
        ))
        instrument_id = ""

    currency = _extract_str(raw, "currency")
    if currency is None:
        violations.append(FieldViolation(
            path="currency", constraint="required string",
            actual_value=repr(raw.get("currency")),
        ))
        currency = ""

    venue = _extract_str(raw, "venue")
    if venue is None:
        violations.append(FieldViolation(
            path="venue", constraint="required string", actual_value=repr(raw.get("venue")),
        ))
        venue = ""

    counterparty_lei = _extract_str(raw, "counterparty_lei")
    if counterparty_lei is None:
        violations.append(FieldViolation(
            path="counterparty_lei", constraint="required string",
            actual_value=repr(raw.get("counterparty_lei")),
        ))
        counterparty_lei = ""

    executing_party_lei = _extract_str(raw, "executing_party_lei")
    if executing_party_lei is None:
        violations.append(FieldViolation(
            path="executing_party_lei", constraint="required string",
            actual_value=repr(raw.get("executing_party_lei")),
        ))
        executing_party_lei = ""

    # --- ISIN (optional) ---
    isin = _extract_str(raw, "isin")

    # --- Enums ---
    side_raw = _extract_str(raw, "side")
    side: OrderSide | None = None
    if side_raw is not None:
        try:
            side = OrderSide(side_raw)
        except ValueError:
            violations.append(FieldViolation(
                path="side", constraint="must be BUY or SELL", actual_value=repr(side_raw),
            ))
    else:
        violations.append(FieldViolation(
            path="side", constraint="required", actual_value=repr(raw.get("side")),
        ))

    order_type_raw = _extract_str(raw, "order_type")
    order_type: OrderType | None = None
    if order_type_raw is not None:
        try:
            order_type = OrderType(order_type_raw)
        except ValueError:
            violations.append(FieldViolation(
                path="order_type", constraint="must be MARKET or LIMIT",
                actual_value=repr(order_type_raw),
            ))
    else:
        violations.append(FieldViolation(
            path="order_type", constraint="required", actual_value=repr(raw.get("order_type")),
        ))

    # --- Numerics ---
    quantity = _extract_decimal(raw, "quantity")
    if quantity is None:
        violations.append(FieldViolation(
            path="quantity", constraint="required numeric", actual_value=repr(raw.get("quantity")),
        ))
        quantity = Decimal("0")

    price = _extract_decimal(raw, "price")
    if price is None:
        violations.append(FieldViolation(
            path="price", constraint="required numeric", actual_value=repr(raw.get("price")),
        ))
        price = Decimal("0")

    # --- Dates ---
    trade_date = _extract_date(raw, "trade_date")
    if trade_date is None:
        violations.append(FieldViolation(
            path="trade_date", constraint="required date", actual_value=repr(raw.get("trade_date")),
        ))

    # settlement_date: computed from trade_date + 2 business days if not provided
    settlement_date = _extract_date(raw, "settlement_date")
    if settlement_date is None and trade_date is not None:
        settlement_date = _add_business_days(trade_date, 2)

    # --- Timestamp ---
    ts_raw = _extract_datetime(raw, "timestamp")
    if ts_raw is None:
        violations.append(FieldViolation(
            path="timestamp", constraint="required datetime",
            actual_value=repr(raw.get("timestamp")),
        ))

    # Early return on extraction failures before CanonicalOrder.create validation
    if violations:
        ts = UtcDatetime.now()
        return Err(ValidationError(
            message=f"parse_order failed: {len(violations)} field error(s)",
            code="GATEWAY_PARSE",
            timestamp=ts,
            source="gateway.parser.parse_order",
            fields=tuple(violations),
        ))

    # All fields extracted — now validate via CanonicalOrder.create
    assert ts_raw is not None
    assert trade_date is not None
    assert settlement_date is not None
    assert side is not None
    assert order_type is not None

    match UtcDatetime.parse(ts_raw):
        case Err(e):
            return Err(ValidationError(
                message=f"parse_order: {e}",
                code="GATEWAY_PARSE",
                timestamp=UtcDatetime.now(),
                source="gateway.parser.parse_order",
                fields=(FieldViolation(path="timestamp", constraint=e, actual_value=str(ts_raw)),),
            ))
        case Ok(ts):
            pass

    return CanonicalOrder.create(
        order_id=order_id,
        instrument_id=instrument_id,
        isin=isin,
        side=side,
        quantity=quantity,
        price=price,
        currency=currency,
        order_type=order_type,
        counterparty_lei=counterparty_lei,
        executing_party_lei=executing_party_lei,
        trade_date=trade_date,
        settlement_date=settlement_date,
        venue=venue,
        timestamp=ts,
    )


def order_to_dict(order: CanonicalOrder) -> dict[str, Any]:
    """Serialize a CanonicalOrder to a raw dict (for INV-G01 round-trip)."""
    return {
        "order_id": order.order_id.value,
        "instrument_id": order.instrument_id.value,
        "isin": order.isin.value if order.isin is not None else None,
        "side": order.side.value,
        "quantity": str(order.quantity.value),
        "price": str(order.price),
        "currency": order.currency.value,
        "order_type": order.order_type.value,
        "counterparty_lei": order.counterparty_lei.value,
        "executing_party_lei": order.executing_party_lei.value,
        "trade_date": order.trade_date.isoformat(),
        "settlement_date": order.settlement_date.isoformat(),
        "venue": order.venue.value,
        "timestamp": order.timestamp.value.isoformat(),
    }
