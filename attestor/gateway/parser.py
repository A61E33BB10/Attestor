"""Gateway parser — raw dict to CanonicalOrder.

parse_order is the single entry point for all external trade data.
INV-G01: idempotent. INV-G02: total (never panics).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from attestor.core.calendar import add_business_days
from attestor.core.errors import FieldViolation, ValidationError
from attestor.core.result import Err, Ok
from attestor.core.types import UtcDatetime
from attestor.gateway.types import CanonicalOrder, OrderSide, OrderType
from attestor.instrument.derivative_types import (
    CDSDetail,
    FuturesDetail,
    FXDetail,
    IRSwapDetail,
    OptionDetail,
    OptionStyle,
    OptionType,
    ProtectionSide,
    SeniorityLevel,
    SettlementType,
    SwaptionDetail,
    SwaptionType,
)


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
        settlement_date = add_business_days(trade_date, 2)

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


def _parse_enum(
    raw: dict[str, object], key: str, enum_cls: type[Any],
    violations: list[FieldViolation],
) -> Any | None:
    val = _extract_str(raw, key)
    if val is None:
        violations.append(FieldViolation(
            path=key, constraint="required", actual_value=repr(raw.get(key)),
        ))
        return None
    try:
        return enum_cls(val)
    except ValueError:
        violations.append(FieldViolation(
            path=key, constraint=f"must be one of {[e.value for e in enum_cls]}",
            actual_value=repr(val),
        ))
        return None


def parse_option_order(
    raw: dict[str, object],
) -> Ok[CanonicalOrder] | Err[ValidationError]:
    """Parse raw dict into a CanonicalOrder with OptionDetail.

    Settlement date defaults to T+1 (premium settlement).
    """
    violations: list[FieldViolation] = []

    # Derivative-specific fields
    strike = _extract_decimal(raw, "strike")
    if strike is None:
        violations.append(FieldViolation(
            path="strike", constraint="required numeric",
            actual_value=repr(raw.get("strike")),
        ))
    expiry_date = _extract_date(raw, "expiry_date")
    if expiry_date is None:
        violations.append(FieldViolation(
            path="expiry_date", constraint="required date",
            actual_value=repr(raw.get("expiry_date")),
        ))
    option_type: OptionType | None = _parse_enum(raw, "option_type", OptionType, violations)
    option_style: OptionStyle | None = _parse_enum(raw, "option_style", OptionStyle, violations)
    settlement_type: SettlementType | None = _parse_enum(
        raw, "settlement_type", SettlementType, violations,
    )
    underlying_id = _extract_str(raw, "underlying_id")
    if underlying_id is None:
        violations.append(FieldViolation(
            path="underlying_id", constraint="required string",
            actual_value=repr(raw.get("underlying_id")),
        ))
    multiplier = _extract_decimal(raw, "multiplier") or Decimal("100")

    if violations:
        return Err(ValidationError(
            message=f"parse_option_order failed: {len(violations)} field error(s)",
            code="GATEWAY_PARSE",
            timestamp=UtcDatetime.now(),
            source="gateway.parser.parse_option_order",
            fields=tuple(violations),
        ))

    assert strike is not None and expiry_date is not None and underlying_id is not None
    assert option_type is not None and option_style is not None and settlement_type is not None

    # Build OptionDetail
    match OptionDetail.create(
        strike=strike, expiry_date=expiry_date,
        option_type=option_type, option_style=option_style,
        settlement_type=settlement_type, underlying_id=underlying_id,
        multiplier=multiplier,
    ):
        case Err(e):
            return Err(ValidationError(
                message=f"parse_option_order: {e}",
                code="GATEWAY_PARSE",
                timestamp=UtcDatetime.now(),
                source="gateway.parser.parse_option_order",
                fields=(FieldViolation(
                    path="instrument_detail", constraint=e, actual_value="",
                ),),
            ))
        case Ok(detail):
            pass

    # Override settlement_date to T+1 if not provided
    trade_date = _extract_date(raw, "trade_date")
    if trade_date is not None:
        settlement_date = _extract_date(raw, "settlement_date")
        if settlement_date is None:
            raw = {**raw, "settlement_date": add_business_days(trade_date, 1)}

    # Delegate to base parser with instrument_detail injected
    base_raw: dict[str, object] = {**raw}
    base_raw.pop("strike", None)
    base_raw.pop("expiry_date", None)
    base_raw.pop("option_type", None)
    base_raw.pop("option_style", None)
    base_raw.pop("settlement_type", None)
    base_raw.pop("underlying_id", None)
    base_raw.pop("multiplier", None)

    # Parse common fields via parse_order then re-create with detail
    match parse_order(base_raw):
        case Err(ve):
            return Err(ve)
        case Ok(base_order):
            pass

    return CanonicalOrder.create(
        order_id=base_order.order_id.value,
        instrument_id=base_order.instrument_id.value,
        isin=base_order.isin.value if base_order.isin else None,
        side=base_order.side,
        quantity=base_order.quantity.value,
        price=base_order.price,
        currency=base_order.currency.value,
        order_type=base_order.order_type,
        counterparty_lei=base_order.counterparty_lei.value,
        executing_party_lei=base_order.executing_party_lei.value,
        trade_date=base_order.trade_date,
        settlement_date=base_order.settlement_date,
        venue=base_order.venue.value,
        timestamp=base_order.timestamp,
        instrument_detail=detail,
    )


def parse_futures_order(
    raw: dict[str, object],
) -> Ok[CanonicalOrder] | Err[ValidationError]:
    """Parse raw dict into a CanonicalOrder with FuturesDetail.

    Settlement date defaults to T+0 (same day).
    """
    violations: list[FieldViolation] = []

    # Futures-specific fields
    expiry_date = _extract_date(raw, "expiry_date")
    if expiry_date is None:
        violations.append(FieldViolation(
            path="expiry_date", constraint="required date",
            actual_value=repr(raw.get("expiry_date")),
        ))
    contract_size = _extract_decimal(raw, "contract_size")
    if contract_size is None:
        violations.append(FieldViolation(
            path="contract_size", constraint="required numeric",
            actual_value=repr(raw.get("contract_size")),
        ))
    settlement_type: SettlementType | None = _parse_enum(
        raw, "settlement_type", SettlementType, violations,
    )
    underlying_id = _extract_str(raw, "underlying_id")
    if underlying_id is None:
        violations.append(FieldViolation(
            path="underlying_id", constraint="required string",
            actual_value=repr(raw.get("underlying_id")),
        ))

    if violations:
        return Err(ValidationError(
            message=f"parse_futures_order failed: {len(violations)} field error(s)",
            code="GATEWAY_PARSE",
            timestamp=UtcDatetime.now(),
            source="gateway.parser.parse_futures_order",
            fields=tuple(violations),
        ))

    assert expiry_date is not None and contract_size is not None
    assert settlement_type is not None and underlying_id is not None

    # Build FuturesDetail
    match FuturesDetail.create(
        expiry_date=expiry_date, contract_size=contract_size,
        settlement_type=settlement_type, underlying_id=underlying_id,
    ):
        case Err(e):
            return Err(ValidationError(
                message=f"parse_futures_order: {e}",
                code="GATEWAY_PARSE",
                timestamp=UtcDatetime.now(),
                source="gateway.parser.parse_futures_order",
                fields=(FieldViolation(
                    path="instrument_detail", constraint=e, actual_value="",
                ),),
            ))
        case Ok(detail):
            pass

    # Override settlement_date to T+0 if not provided
    trade_date = _extract_date(raw, "trade_date")
    if trade_date is not None:
        settlement_date = _extract_date(raw, "settlement_date")
        if settlement_date is None:
            raw = {**raw, "settlement_date": trade_date}

    # Delegate to base parser with instrument_detail injected
    base_raw: dict[str, object] = {**raw}
    base_raw.pop("expiry_date", None)
    base_raw.pop("contract_size", None)
    base_raw.pop("settlement_type", None)
    base_raw.pop("underlying_id", None)

    match parse_order(base_raw):
        case Err(ve):
            return Err(ve)
        case Ok(base_order):
            pass

    return CanonicalOrder.create(
        order_id=base_order.order_id.value,
        instrument_id=base_order.instrument_id.value,
        isin=base_order.isin.value if base_order.isin else None,
        side=base_order.side,
        quantity=base_order.quantity.value,
        price=base_order.price,
        currency=base_order.currency.value,
        order_type=base_order.order_type,
        counterparty_lei=base_order.counterparty_lei.value,
        executing_party_lei=base_order.executing_party_lei.value,
        trade_date=base_order.trade_date,
        settlement_date=base_order.settlement_date,
        venue=base_order.venue.value,
        timestamp=base_order.timestamp,
        instrument_detail=detail,
    )


# ---------------------------------------------------------------------------
# Phase 3 parsers — FX and IRS
# ---------------------------------------------------------------------------


def _delegate_to_base(
    raw: dict[str, object],
    detail: FXDetail | IRSwapDetail | CDSDetail | SwaptionDetail,
    *,
    strip_keys: tuple[str, ...],
    source: str,
    default_settlement_days: int = 2,
) -> Ok[CanonicalOrder] | Err[ValidationError]:
    """Extract common fields, build CanonicalOrder with instrument_detail."""
    trade_date = _extract_date(raw, "trade_date")
    if trade_date is not None:
        settlement_date = _extract_date(raw, "settlement_date")
        if settlement_date is None:
            raw = {**raw, "settlement_date": add_business_days(trade_date, default_settlement_days)}

    base_raw: dict[str, object] = {**raw}
    for k in strip_keys:
        base_raw.pop(k, None)

    match parse_order(base_raw):
        case Err(ve):
            return Err(ve)
        case Ok(base_order):
            pass

    return CanonicalOrder.create(
        order_id=base_order.order_id.value,
        instrument_id=base_order.instrument_id.value,
        isin=base_order.isin.value if base_order.isin else None,
        side=base_order.side,
        quantity=base_order.quantity.value,
        price=base_order.price,
        currency=base_order.currency.value,
        order_type=base_order.order_type,
        counterparty_lei=base_order.counterparty_lei.value,
        executing_party_lei=base_order.executing_party_lei.value,
        trade_date=base_order.trade_date,
        settlement_date=base_order.settlement_date,
        venue=base_order.venue.value,
        timestamp=base_order.timestamp,
        instrument_detail=detail,
    )


def _parse_optional_enum(
    raw: dict[str, object], key: str, enum_cls: type[Any],
    violations: list[FieldViolation], default: Any,
) -> Any:
    """Parse enum or return default if key missing. Only append violation on bad value."""
    val = _extract_str(raw, key)
    if val is None:
        return default
    try:
        return enum_cls(val)
    except ValueError:
        violations.append(FieldViolation(
            path=key, constraint=f"must be one of {[e.value for e in enum_cls]}",
            actual_value=repr(val),
        ))
        return None


def parse_fx_spot_order(
    raw: dict[str, object],
) -> Ok[CanonicalOrder] | Err[ValidationError]:
    """Parse raw FX spot order. Settlement default: T+2."""
    violations: list[FieldViolation] = []

    currency_pair = _extract_str(raw, "currency_pair")
    if currency_pair is None:
        violations.append(FieldViolation(
            path="currency_pair", constraint="required string",
            actual_value=repr(raw.get("currency_pair")),
        ))

    settlement_type: SettlementType | None = _parse_optional_enum(
        raw, "settlement_type", SettlementType, violations, SettlementType.PHYSICAL,
    )

    if violations:
        return Err(ValidationError(
            message=f"parse_fx_spot_order failed: {len(violations)} field error(s)",
            code="GATEWAY_PARSE",
            timestamp=UtcDatetime.now(),
            source="gateway.parser.parse_fx_spot_order",
            fields=tuple(violations),
        ))

    assert currency_pair is not None
    assert settlement_type is not None

    # Settlement date: T+2
    trade_date = _extract_date(raw, "trade_date")
    settlement_date = _extract_date(raw, "settlement_date")
    if settlement_date is None and trade_date is not None:
        settlement_date = add_business_days(trade_date, 2)

    if settlement_date is None:
        return Err(ValidationError(
            message="parse_fx_spot_order: cannot compute settlement_date",
            code="GATEWAY_PARSE",
            timestamp=UtcDatetime.now(),
            source="gateway.parser.parse_fx_spot_order",
            fields=(FieldViolation(
                path="settlement_date", constraint="required (or trade_date for T+2)",
                actual_value="None",
            ),),
        ))

    match FXDetail.create(
        currency_pair=currency_pair,
        settlement_date=settlement_date,
        settlement_type=settlement_type,
    ):
        case Err(e):
            return Err(ValidationError(
                message=f"parse_fx_spot_order: {e}",
                code="GATEWAY_PARSE",
                timestamp=UtcDatetime.now(),
                source="gateway.parser.parse_fx_spot_order",
                fields=(FieldViolation(
                    path="instrument_detail", constraint=e, actual_value="",
                ),),
            ))
        case Ok(detail):
            pass

    return _delegate_to_base(
        raw, detail,
        strip_keys=("currency_pair", "settlement_type"),
        source="gateway.parser.parse_fx_spot_order",
    )


def parse_fx_forward_order(
    raw: dict[str, object],
) -> Ok[CanonicalOrder] | Err[ValidationError]:
    """Parse raw FX forward order. Settlement date from forward contract."""
    violations: list[FieldViolation] = []

    currency_pair = _extract_str(raw, "currency_pair")
    if currency_pair is None:
        violations.append(FieldViolation(
            path="currency_pair", constraint="required string",
            actual_value=repr(raw.get("currency_pair")),
        ))

    forward_rate = _extract_decimal(raw, "forward_rate")
    if forward_rate is None:
        violations.append(FieldViolation(
            path="forward_rate", constraint="required numeric",
            actual_value=repr(raw.get("forward_rate")),
        ))

    settlement_date = _extract_date(raw, "settlement_date")
    if settlement_date is None:
        violations.append(FieldViolation(
            path="settlement_date", constraint="required date",
            actual_value=repr(raw.get("settlement_date")),
        ))

    settlement_type: SettlementType | None = _parse_optional_enum(
        raw, "settlement_type", SettlementType, violations, SettlementType.PHYSICAL,
    )

    if violations:
        return Err(ValidationError(
            message=f"parse_fx_forward_order failed: {len(violations)} field error(s)",
            code="GATEWAY_PARSE",
            timestamp=UtcDatetime.now(),
            source="gateway.parser.parse_fx_forward_order",
            fields=tuple(violations),
        ))

    assert currency_pair is not None and forward_rate is not None and settlement_date is not None
    assert settlement_type is not None

    match FXDetail.create(
        currency_pair=currency_pair,
        settlement_date=settlement_date,
        settlement_type=settlement_type,
        forward_rate=forward_rate,
    ):
        case Err(e):
            return Err(ValidationError(
                message=f"parse_fx_forward_order: {e}",
                code="GATEWAY_PARSE",
                timestamp=UtcDatetime.now(),
                source="gateway.parser.parse_fx_forward_order",
                fields=(FieldViolation(
                    path="instrument_detail", constraint=e, actual_value="",
                ),),
            ))
        case Ok(detail):
            pass

    return _delegate_to_base(
        raw, detail,
        strip_keys=("currency_pair", "forward_rate", "settlement_type"),
        source="gateway.parser.parse_fx_forward_order",
    )


def parse_ndf_order(
    raw: dict[str, object],
) -> Ok[CanonicalOrder] | Err[ValidationError]:
    """Parse raw NDF order. Fixing date + settlement date required."""
    violations: list[FieldViolation] = []

    currency_pair = _extract_str(raw, "currency_pair")
    if currency_pair is None:
        violations.append(FieldViolation(
            path="currency_pair", constraint="required string",
            actual_value=repr(raw.get("currency_pair")),
        ))

    forward_rate = _extract_decimal(raw, "forward_rate")
    if forward_rate is None:
        violations.append(FieldViolation(
            path="forward_rate", constraint="required numeric",
            actual_value=repr(raw.get("forward_rate")),
        ))

    fixing_date = _extract_date(raw, "fixing_date")
    if fixing_date is None:
        violations.append(FieldViolation(
            path="fixing_date", constraint="required date",
            actual_value=repr(raw.get("fixing_date")),
        ))

    settlement_date = _extract_date(raw, "settlement_date")
    if settlement_date is None:
        violations.append(FieldViolation(
            path="settlement_date", constraint="required date",
            actual_value=repr(raw.get("settlement_date")),
        ))

    fixing_source = _extract_str(raw, "fixing_source")
    if fixing_source is None:
        violations.append(FieldViolation(
            path="fixing_source", constraint="required string",
            actual_value=repr(raw.get("fixing_source")),
        ))

    if violations:
        return Err(ValidationError(
            message=f"parse_ndf_order failed: {len(violations)} field error(s)",
            code="GATEWAY_PARSE",
            timestamp=UtcDatetime.now(),
            source="gateway.parser.parse_ndf_order",
            fields=tuple(violations),
        ))

    assert currency_pair is not None and forward_rate is not None
    assert fixing_date is not None and settlement_date is not None and fixing_source is not None

    match FXDetail.create(
        currency_pair=currency_pair,
        settlement_date=settlement_date,
        settlement_type=SettlementType.CASH,
        forward_rate=forward_rate,
        fixing_source=fixing_source,
        fixing_date=fixing_date,
    ):
        case Err(e):
            return Err(ValidationError(
                message=f"parse_ndf_order: {e}",
                code="GATEWAY_PARSE",
                timestamp=UtcDatetime.now(),
                source="gateway.parser.parse_ndf_order",
                fields=(FieldViolation(
                    path="instrument_detail", constraint=e, actual_value="",
                ),),
            ))
        case Ok(detail):
            pass

    return _delegate_to_base(
        raw, detail,
        strip_keys=(
            "currency_pair", "forward_rate", "fixing_date",
            "settlement_type", "fixing_source",
        ),
        source="gateway.parser.parse_ndf_order",
    )


def parse_irs_order(
    raw: dict[str, object],
) -> Ok[CanonicalOrder] | Err[ValidationError]:
    """Parse raw IRS order."""
    violations: list[FieldViolation] = []

    fixed_rate = _extract_decimal(raw, "fixed_rate")
    if fixed_rate is None:
        violations.append(FieldViolation(
            path="fixed_rate", constraint="required numeric",
            actual_value=repr(raw.get("fixed_rate")),
        ))

    float_index = _extract_str(raw, "float_index")
    if float_index is None:
        violations.append(FieldViolation(
            path="float_index", constraint="required string",
            actual_value=repr(raw.get("float_index")),
        ))

    day_count = _extract_str(raw, "day_count")
    if day_count is None:
        violations.append(FieldViolation(
            path="day_count", constraint="required string",
            actual_value=repr(raw.get("day_count")),
        ))

    payment_frequency = _extract_str(raw, "payment_frequency")
    if payment_frequency is None:
        violations.append(FieldViolation(
            path="payment_frequency", constraint="required string",
            actual_value=repr(raw.get("payment_frequency")),
        ))

    tenor_months = _extract_decimal(raw, "tenor_months")
    if tenor_months is None:
        violations.append(FieldViolation(
            path="tenor_months", constraint="required numeric",
            actual_value=repr(raw.get("tenor_months")),
        ))

    start_date = _extract_date(raw, "start_date")
    if start_date is None:
        violations.append(FieldViolation(
            path="start_date", constraint="required date",
            actual_value=repr(raw.get("start_date")),
        ))

    end_date = _extract_date(raw, "end_date")
    if end_date is None:
        violations.append(FieldViolation(
            path="end_date", constraint="required date",
            actual_value=repr(raw.get("end_date")),
        ))

    if violations:
        return Err(ValidationError(
            message=f"parse_irs_order failed: {len(violations)} field error(s)",
            code="GATEWAY_PARSE",
            timestamp=UtcDatetime.now(),
            source="gateway.parser.parse_irs_order",
            fields=tuple(violations),
        ))

    assert fixed_rate is not None and float_index is not None
    assert day_count is not None and payment_frequency is not None
    assert tenor_months is not None and start_date is not None and end_date is not None

    match IRSwapDetail.create(
        fixed_rate=fixed_rate,
        float_index=float_index,
        day_count=day_count,
        payment_frequency=payment_frequency,
        tenor_months=int(tenor_months),
        start_date=start_date,
        end_date=end_date,
    ):
        case Err(e):
            return Err(ValidationError(
                message=f"parse_irs_order: {e}",
                code="GATEWAY_PARSE",
                timestamp=UtcDatetime.now(),
                source="gateway.parser.parse_irs_order",
                fields=(FieldViolation(
                    path="instrument_detail", constraint=e, actual_value="",
                ),),
            ))
        case Ok(detail):
            pass

    # IRS settles T+2 by default
    return _delegate_to_base(
        raw, detail,
        strip_keys=(
            "fixed_rate", "float_index", "day_count", "payment_frequency",
            "tenor_months", "start_date", "end_date",
        ),
        source="gateway.parser.parse_irs_order",
    )


# ---------------------------------------------------------------------------
# Phase 4 parsers — CDS and Swaptions
# ---------------------------------------------------------------------------


def parse_cds_order(
    raw: dict[str, object],
) -> Ok[CanonicalOrder] | Err[ValidationError]:
    """Parse raw CDS order into CanonicalOrder with CDSDetail.

    Required fields: reference_entity, spread_bps, start_date, maturity_date,
    seniority (SENIOR_UNSECURED|SUBORDINATED|SENIOR_SECURED),
    protection_side (BUYER|SELLER).  Settlement default: T+1.
    """
    violations: list[FieldViolation] = []

    reference_entity = _extract_str(raw, "reference_entity")
    if reference_entity is None:
        violations.append(FieldViolation(
            path="reference_entity", constraint="required string",
            actual_value=repr(raw.get("reference_entity")),
        ))

    spread_bps = _extract_decimal(raw, "spread_bps")
    if spread_bps is None:
        violations.append(FieldViolation(
            path="spread_bps", constraint="required numeric",
            actual_value=repr(raw.get("spread_bps")),
        ))

    seniority: SeniorityLevel | None = _parse_enum(
        raw, "seniority", SeniorityLevel, violations,
    )

    protection_side: ProtectionSide | None = _parse_enum(
        raw, "protection_side", ProtectionSide, violations,
    )

    start_date = _extract_date(raw, "start_date")
    if start_date is None:
        violations.append(FieldViolation(
            path="start_date", constraint="required date",
            actual_value=repr(raw.get("start_date")),
        ))

    maturity_date = _extract_date(raw, "maturity_date")
    if maturity_date is None:
        violations.append(FieldViolation(
            path="maturity_date", constraint="required date",
            actual_value=repr(raw.get("maturity_date")),
        ))

    if violations:
        return Err(ValidationError(
            message=f"parse_cds_order failed: {len(violations)} field error(s)",
            code="GATEWAY_PARSE",
            timestamp=UtcDatetime.now(),
            source="gateway.parser.parse_cds_order",
            fields=tuple(violations),
        ))

    assert reference_entity is not None and spread_bps is not None
    assert seniority is not None and protection_side is not None
    assert start_date is not None and maturity_date is not None

    match CDSDetail.create(
        reference_entity=reference_entity,
        spread_bps=spread_bps,
        seniority=seniority,
        protection_side=protection_side,
        start_date=start_date,
        maturity_date=maturity_date,
    ):
        case Err(e):
            return Err(ValidationError(
                message=f"parse_cds_order: {e}",
                code="GATEWAY_PARSE",
                timestamp=UtcDatetime.now(),
                source="gateway.parser.parse_cds_order",
                fields=(FieldViolation(
                    path="instrument_detail", constraint=e, actual_value="",
                ),),
            ))
        case Ok(detail):
            pass

    # CDS settles T+1 by default
    return _delegate_to_base(
        raw, detail,
        strip_keys=(
            "reference_entity", "spread_bps", "seniority", "protection_side",
            "start_date", "maturity_date",
        ),
        source="gateway.parser.parse_cds_order",
        default_settlement_days=1,
    )


def parse_swaption_order(
    raw: dict[str, object],
) -> Ok[CanonicalOrder] | Err[ValidationError]:
    """Parse raw swaption order into CanonicalOrder with SwaptionDetail.

    Required fields: swaption_type (PAYER|RECEIVER), expiry_date, underlying_fixed_rate,
    underlying_float_index, underlying_tenor_months, settlement_type (PHYSICAL|CASH).
    Settlement default: T+1.
    """
    violations: list[FieldViolation] = []

    swaption_type: SwaptionType | None = _parse_enum(
        raw, "swaption_type", SwaptionType, violations,
    )

    expiry_date = _extract_date(raw, "expiry_date")
    if expiry_date is None:
        violations.append(FieldViolation(
            path="expiry_date", constraint="required date",
            actual_value=repr(raw.get("expiry_date")),
        ))

    underlying_fixed_rate = _extract_decimal(raw, "underlying_fixed_rate")
    if underlying_fixed_rate is None:
        violations.append(FieldViolation(
            path="underlying_fixed_rate", constraint="required numeric",
            actual_value=repr(raw.get("underlying_fixed_rate")),
        ))

    underlying_float_index = _extract_str(raw, "underlying_float_index")
    if underlying_float_index is None:
        violations.append(FieldViolation(
            path="underlying_float_index", constraint="required string",
            actual_value=repr(raw.get("underlying_float_index")),
        ))

    underlying_tenor_months_raw = _extract_decimal(raw, "underlying_tenor_months")
    if underlying_tenor_months_raw is None:
        violations.append(FieldViolation(
            path="underlying_tenor_months", constraint="required numeric",
            actual_value=repr(raw.get("underlying_tenor_months")),
        ))

    settlement_type: SettlementType | None = _parse_enum(
        raw, "settlement_type", SettlementType, violations,
    )

    if violations:
        return Err(ValidationError(
            message=f"parse_swaption_order failed: {len(violations)} field error(s)",
            code="GATEWAY_PARSE",
            timestamp=UtcDatetime.now(),
            source="gateway.parser.parse_swaption_order",
            fields=tuple(violations),
        ))

    assert swaption_type is not None and expiry_date is not None
    assert underlying_fixed_rate is not None and underlying_float_index is not None
    assert underlying_tenor_months_raw is not None and settlement_type is not None

    match SwaptionDetail.create(
        swaption_type=swaption_type,
        expiry_date=expiry_date,
        underlying_fixed_rate=underlying_fixed_rate,
        underlying_float_index=underlying_float_index,
        underlying_tenor_months=int(underlying_tenor_months_raw),
        settlement_type=settlement_type,
    ):
        case Err(e):
            return Err(ValidationError(
                message=f"parse_swaption_order: {e}",
                code="GATEWAY_PARSE",
                timestamp=UtcDatetime.now(),
                source="gateway.parser.parse_swaption_order",
                fields=(FieldViolation(
                    path="instrument_detail", constraint=e, actual_value="",
                ),),
            ))
        case Ok(detail):
            pass

    # Swaptions settle T+1 by default
    return _delegate_to_base(
        raw, detail,
        strip_keys=(
            "swaption_type", "expiry_date", "underlying_fixed_rate",
            "underlying_float_index", "underlying_tenor_months", "settlement_type",
        ),
        source="gateway.parser.parse_swaption_order",
        default_settlement_days=1,
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
