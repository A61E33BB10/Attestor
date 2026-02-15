"""GL projection — pure read-only projection from sub-ledger to GL accounts.

INV-17: No state mutation. Pure projection.
INV-GL-01: Trial balance — sum(debits) == sum(cr_total).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import final

from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, Ok
from attestor.core.types import FrozenMap, UtcDatetime
from attestor.ledger.engine import LedgerEngine


class GLAccountType(Enum):
    """Standard GL account classification."""

    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


@final
@dataclass(frozen=True, slots=True)
class GLEntry:
    """A single GL entry for an account/instrument pair."""

    gl_account: NonEmptyStr
    gl_account_type: GLAccountType
    instrument_id: NonEmptyStr
    debit_total: Decimal
    credit_total: Decimal


@final
@dataclass(frozen=True, slots=True)
class GLAccountMapping:
    """Maps sub-ledger account IDs to (GL code, GL account type)."""

    mappings: FrozenMap[str, tuple[str, GLAccountType]]


@final
@dataclass(frozen=True, slots=True)
class GLProjection:
    """Snapshot of GL entries projected from the sub-ledger."""

    entries: tuple[GLEntry, ...]
    as_of: UtcDatetime

    def trial_balance(self) -> Ok[Decimal] | Err[str]:
        """INV-GL-01: sum(debits) == sum(cr_total). Returns 0 if balanced."""
        total_debits = sum(
            (e.debit_total for e in self.entries), Decimal(0),
        )
        total_cr_total = sum(
            (e.credit_total for e in self.entries), Decimal(0),
        )
        diff = total_debits - total_cr_total
        if diff != Decimal(0):
            return Err(
                f"Trial balance unbalanced: debits={total_debits}, "
                f"cr_total={total_cr_total}, diff={diff}"
            )
        return Ok(Decimal(0))


def project_gl(
    engine: LedgerEngine,
    mapping: GLAccountMapping,
    as_of: UtcDatetime,
) -> GLProjection:
    """INV-17: Pure projection. No state mutation.

    For each position in the engine, map to GL account and aggregate.
    Positive balances are debits (for asset accounts), negative are cr_total.
    """
    # Aggregate by (gl_account, instrument)
    aggregated: dict[
        tuple[str, str, GLAccountType], tuple[Decimal, Decimal]
    ] = {}

    for position in engine.positions():
        acct_id = position.account.value
        inst = position.instrument.value
        mapping_entry = mapping.mappings.get(acct_id)
        if mapping_entry is None:
            continue
        gl_code, gl_type = mapping_entry

        key = (gl_code, inst, gl_type)
        existing = aggregated.get(key, (Decimal(0), Decimal(0)))

        if position.quantity >= 0:
            aggregated[key] = (
                existing[0] + position.quantity, existing[1],
            )
        else:
            aggregated[key] = (
                existing[0], existing[1] + abs(position.quantity),
            )

    entries = tuple(
        GLEntry(
            gl_account=NonEmptyStr(value=gl_code),
            gl_account_type=gl_type,
            instrument_id=NonEmptyStr(value=inst),
            debit_total=debits,
            credit_total=cr_total,
        )
        for (gl_code, inst, gl_type), (debits, cr_total)
        in sorted(aggregated.items())
    )

    return GLProjection(entries=entries, as_of=as_of)
