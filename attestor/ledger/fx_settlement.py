"""FX settlement transaction creation — spot, forward, and NDF.

FX spot/forward: 2 Moves (one per currency leg).
NDF: 1 Move in settlement currency (cash-settled difference).

Conservation: each currency unit sigma is independently unchanged.
"""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import TYPE_CHECKING

from attestor.core.errors import FieldViolation, ValidationError
from attestor.core.money import ATTESTOR_DECIMAL_CONTEXT, PositiveDecimal
from attestor.core.result import Err, Ok
from attestor.core.types import UtcDatetime
from attestor.instrument.derivative_types import FXDetail
from attestor.ledger.transactions import Move, Transaction

if TYPE_CHECKING:
    from attestor.gateway.types import CanonicalOrder


def _validate_accounts(
    accounts: dict[str, str], source_fn: str,
) -> list[FieldViolation]:
    """Check all account strings are non-empty."""
    violations: list[FieldViolation] = []
    for name, val in accounts.items():
        if not val:
            violations.append(FieldViolation(
                path=name, constraint="must be non-empty", actual_value="",
            ))
    return violations


def create_fx_spot_settlement(
    order: CanonicalOrder,
    buyer_base_account: str,
    buyer_quote_account: str,
    seller_base_account: str,
    seller_quote_account: str,
    spot_rate: Decimal,
    tx_id: str,
) -> Ok[Transaction] | Err[ValidationError]:
    """Create FX spot settlement with 2 Moves (one per currency).

    Move 1: base_notional of BASE currency from seller -> buyer
    Move 2: base_notional * spot_rate of QUOTE currency from buyer -> seller

    Conservation: sigma(BASE) unchanged, sigma(QUOTE) unchanged.
    """
    violations = _validate_accounts({
        "buyer_base_account": buyer_base_account,
        "buyer_quote_account": buyer_quote_account,
        "seller_base_account": seller_base_account,
        "seller_quote_account": seller_quote_account,
        "tx_id": tx_id,
    }, "create_fx_spot_settlement")

    detail = order.instrument_detail
    if not isinstance(detail, FXDetail):
        violations.append(FieldViolation(
            path="instrument_detail", constraint="must be FXDetail",
            actual_value=type(detail).__name__,
        ))

    if violations:
        return Err(ValidationError(
            message="FX spot settlement validation failed",
            code="FX_SETTLEMENT_VALIDATION",
            timestamp=UtcDatetime.now(),
            source="ledger.fx_settlement.create_fx_spot_settlement",
            fields=tuple(violations),
        ))

    assert isinstance(detail, FXDetail)
    base_notional = order.quantity.value
    cp = detail.currency_pair
    base_ccy = cp.split("/")[0] if "/" in cp else cp
    quote_ccy = cp.split("/")[1] if "/" in cp else cp

    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        quote_amount = base_notional * spot_rate

    match PositiveDecimal.parse(base_notional):
        case Err(_):
            return Err(ValidationError(
                message=f"Base notional must be positive, got {base_notional}",
                code="FX_SETTLEMENT_VALIDATION",
                timestamp=UtcDatetime.now(),
                source="ledger.fx_settlement.create_fx_spot_settlement",
                fields=(FieldViolation(
                    path="base_notional", constraint="must be > 0",
                    actual_value=str(base_notional),
                ),),
            ))
        case Ok(base_qty):
            pass

    match PositiveDecimal.parse(quote_amount):
        case Err(_):
            return Err(ValidationError(
                message=f"Quote amount must be positive, got {quote_amount}",
                code="FX_SETTLEMENT_VALIDATION",
                timestamp=UtcDatetime.now(),
                source="ledger.fx_settlement.create_fx_spot_settlement",
                fields=(FieldViolation(
                    path="quote_amount", constraint="must be > 0",
                    actual_value=str(quote_amount),
                ),),
            ))
        case Ok(quote_qty):
            pass

    contract_id = order.order_id.value
    moves = (
        Move(
            source=seller_base_account,
            destination=buyer_base_account,
            unit=base_ccy,
            quantity=base_qty,
            contract_id=contract_id,
        ),
        Move(
            source=buyer_quote_account,
            destination=seller_quote_account,
            unit=quote_ccy,
            quantity=quote_qty,
            contract_id=contract_id,
        ),
    )

    return Ok(Transaction(tx_id=tx_id, moves=moves, timestamp=order.timestamp))


def create_fx_forward_settlement(
    order: CanonicalOrder,
    buyer_base_account: str,
    buyer_quote_account: str,
    seller_base_account: str,
    seller_quote_account: str,
    tx_id: str,
) -> Ok[Transaction] | Err[ValidationError]:
    """Create FX forward settlement at the agreed forward rate."""
    detail = order.instrument_detail
    if not isinstance(detail, FXDetail):
        return Err(ValidationError(
            message="instrument_detail must be FXDetail",
            code="FX_SETTLEMENT_VALIDATION",
            timestamp=UtcDatetime.now(),
            source="ledger.fx_settlement.create_fx_forward_settlement",
            fields=(FieldViolation(
                path="instrument_detail", constraint="must be FXDetail",
                actual_value=type(detail).__name__,
            ),),
        ))
    if detail.forward_rate is None:
        return Err(ValidationError(
            message="FX forward must have a forward_rate",
            code="FX_SETTLEMENT_VALIDATION",
            timestamp=UtcDatetime.now(),
            source="ledger.fx_settlement.create_fx_forward_settlement",
            fields=(FieldViolation(
                path="forward_rate", constraint="required for forward",
                actual_value="None",
            ),),
        ))

    return create_fx_spot_settlement(
        order=order,
        buyer_base_account=buyer_base_account,
        buyer_quote_account=buyer_quote_account,
        seller_base_account=seller_base_account,
        seller_quote_account=seller_quote_account,
        spot_rate=detail.forward_rate.value,
        tx_id=tx_id,
    )


def create_ndf_settlement(
    order: CanonicalOrder,
    buyer_cash_account: str,
    seller_cash_account: str,
    fixing_rate: Decimal,
    tx_id: str,
) -> Ok[Transaction] | Err[ValidationError]:
    """Create NDF cash settlement.

    Settlement amount = notional * (fixing_rate - forward_rate) / fixing_rate
    Single Move in settlement currency. Direction depends on sign.
    """
    violations = _validate_accounts({
        "buyer_cash_account": buyer_cash_account,
        "seller_cash_account": seller_cash_account,
        "tx_id": tx_id,
    }, "create_ndf_settlement")

    detail = order.instrument_detail
    if not isinstance(detail, FXDetail):
        violations.append(FieldViolation(
            path="instrument_detail", constraint="must be FXDetail",
            actual_value=type(detail).__name__,
        ))
    if violations:
        return Err(ValidationError(
            message="NDF settlement validation failed",
            code="NDF_SETTLEMENT_VALIDATION",
            timestamp=UtcDatetime.now(),
            source="ledger.fx_settlement.create_ndf_settlement",
            fields=tuple(violations),
        ))

    assert isinstance(detail, FXDetail)
    if detail.forward_rate is None:
        return Err(ValidationError(
            message="NDF must have a forward_rate",
            code="NDF_SETTLEMENT_VALIDATION",
            timestamp=UtcDatetime.now(),
            source="ledger.fx_settlement.create_ndf_settlement",
            fields=(FieldViolation(
                path="forward_rate", constraint="required for NDF",
                actual_value="None",
            ),),
        ))

    notional = order.quantity.value
    forward_rate = detail.forward_rate.value
    currency = order.currency.value

    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        if fixing_rate == 0:
            return Err(ValidationError(
                message="fixing_rate cannot be zero",
                code="NDF_SETTLEMENT_VALIDATION",
                timestamp=UtcDatetime.now(),
                source="ledger.fx_settlement.create_ndf_settlement",
                fields=(FieldViolation(
                    path="fixing_rate", constraint="must be non-zero",
                    actual_value="0",
                ),),
            ))
        settlement_amount = notional * (fixing_rate - forward_rate) / fixing_rate

    # Positive = buyer receives, negative = seller receives
    abs_amount = abs(settlement_amount)
    match PositiveDecimal.parse(abs_amount):
        case Err(_):
            # Zero settlement — no Move needed, but still create a Transaction
            return Ok(Transaction(
                tx_id=tx_id, moves=(), timestamp=order.timestamp,
            ))
        case Ok(qty):
            pass

    contract_id = order.order_id.value
    if settlement_amount > 0:
        move = Move(
            source=seller_cash_account,
            destination=buyer_cash_account,
            unit=currency,
            quantity=qty,
            contract_id=contract_id,
        )
    else:
        move = Move(
            source=buyer_cash_account,
            destination=seller_cash_account,
            unit=currency,
            quantity=qty,
            contract_id=contract_id,
        )

    return Ok(Transaction(tx_id=tx_id, moves=(move,), timestamp=order.timestamp))
