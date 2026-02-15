"""Dividend transaction creation.

For each holder: Move cash from issuer → holder (amount_per_share * shares_held).
Conservation: total cash out of issuer == sum of cash into all holders.
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from attestor.core.errors import FieldViolation, ValidationError
from attestor.core.money import ATTESTOR_DECIMAL_CONTEXT, PositiveDecimal
from attestor.core.result import Err, Ok
from attestor.core.types import UtcDatetime
from attestor.ledger.transactions import Move, Transaction


def create_dividend_transaction(
    instrument_id: str,
    amount_per_share: Decimal,
    currency: str,
    holder_accounts: tuple[tuple[str, Decimal], ...],
    issuer_account: str,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Create dividend payment transaction.

    For each holder: Move cash from issuer → holder (amount_per_share * shares_held).
    Conservation: total cash out of issuer == sum of cash into all holders.
    """
    violations: list[FieldViolation] = []
    if not instrument_id:
        violations.append(FieldViolation(
            path="instrument_id", constraint="must be non-empty", actual_value="",
        ))
    if not currency:
        violations.append(FieldViolation(
            path="currency", constraint="must be non-empty", actual_value="",
        ))
    if not issuer_account:
        violations.append(FieldViolation(
            path="issuer_account", constraint="must be non-empty", actual_value="",
        ))
    if not tx_id:
        violations.append(FieldViolation(
            path="tx_id", constraint="must be non-empty", actual_value="",
        ))
    if not holder_accounts:
        violations.append(FieldViolation(
            path="holder_accounts", constraint="must have at least one holder",
            actual_value="empty",
        ))
    if amount_per_share <= 0:
        violations.append(FieldViolation(
            path="amount_per_share", constraint="must be > 0",
            actual_value=str(amount_per_share),
        ))
    if violations:
        return Err(ValidationError(
            message="Dividend validation failed",
            code="DIVIDEND_VALIDATION",
            timestamp=timestamp,
            source="ledger.dividends.create_dividend_transaction",
            fields=tuple(violations),
        ))

    moves: list[Move] = []
    for account_id, shares_held in holder_accounts:
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            payment = amount_per_share * shares_held
        match PositiveDecimal.parse(payment):
            case Err(_):
                return Err(ValidationError(
                    message=f"Dividend payment must be positive for {account_id}",
                    code="DIVIDEND_VALIDATION",
                    timestamp=timestamp,
                    source="ledger.dividends.create_dividend_transaction",
                    fields=(FieldViolation(
                        path=f"holder[{account_id}]", constraint="payment must be > 0",
                        actual_value=str(payment),
                    ),),
                ))
            case Ok(pay_qty):
                moves.append(Move(
                    source=issuer_account,
                    destination=account_id,
                    unit=currency,
                    quantity=pay_qty,
                    contract_id=f"DIV-{instrument_id}-{tx_id}",
                ))

    return Ok(Transaction(
        tx_id=tx_id,
        moves=tuple(moves),
        timestamp=timestamp,
    ))
