"""Dodd-Frank swap reporting -- pure projection from CanonicalOrder.

INV-R01: Reporting is projection, not transformation.
Only CDS and swaption orders produce Dodd-Frank swap reports.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import final

from attestor.core.identifiers import LEI
from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, Ok
from attestor.core.serialization import content_hash
from attestor.core.types import UtcDatetime
from attestor.gateway.types import CanonicalOrder
from attestor.instrument.derivative_types import CDSDetail, SwaptionDetail
from attestor.oracle.attestation import (
    Attestation,
    FirmConfidence,
    create_attestation,
)

_AC_CREDIT = NonEmptyStr(value="CREDIT")
_AC_INTEREST_RATE = NonEmptyStr(value="INTEREST_RATE")
_PT_CDS = NonEmptyStr(value="CDS")
_PT_SWAPTION = NonEmptyStr(value="SWAPTION")


@final
@dataclass(frozen=True, slots=True)
class DoddFrankSwapReport:
    """Dodd-Frank swap report for CDS and swaption orders."""

    usi: NonEmptyStr
    reporting_counterparty_lei: LEI
    non_reporting_counterparty_lei: LEI
    instrument_id: NonEmptyStr
    asset_class: NonEmptyStr  # "CREDIT" or "INTEREST_RATE"
    product_type: NonEmptyStr  # "CDS" or "SWAPTION"
    notional: Decimal
    currency: NonEmptyStr
    effective_date: date
    maturity_date: date
    report_timestamp: UtcDatetime
    attestation_refs: tuple[str, ...]
    reference_entity: NonEmptyStr | None  # CDS only
    spread_bps: Decimal | None  # CDS only
    expiry_date: date | None  # Swaption only
    underlying_fixed_rate: Decimal | None  # Swaption only


def project_dodd_frank_report(
    order: CanonicalOrder,
    trade_attestation_id: str,
) -> Ok[Attestation[DoddFrankSwapReport]] | Err[str]:
    """Project Dodd-Frank report from CDS or swaption order.

    Returns Err for non-CDS/non-swaption orders.
    """
    # Generate USI from content hash of order
    match content_hash(order):
        case Err(e):
            return Err(f"Cannot compute USI: {e}")
        case Ok(ch):
            pass

    usi_value = order.executing_party_lei.value + ch[:32]
    match NonEmptyStr.parse(usi_value):
        case Err(e):
            return Err(f"USI: {e}")
        case Ok(usi):
            pass

    # Build asset-class-specific fields via exhaustive match
    match order.instrument_detail:
        case CDSDetail() as cd:
            asset_class = _AC_CREDIT
            product_type = _PT_CDS
            effective_date = cd.start_date
            maturity_date = cd.maturity_date
            reference_entity: NonEmptyStr | None = cd.reference_entity
            spread_bps: Decimal | None = cd.spread_bps.value
            expiry_date: date | None = None
            underlying_fixed_rate: Decimal | None = None

        case SwaptionDetail() as sd:
            asset_class = _AC_INTEREST_RATE
            product_type = _PT_SWAPTION
            effective_date = order.trade_date
            maturity_date = order.settlement_date
            reference_entity = None
            spread_bps = None
            expiry_date = sd.expiry_date
            underlying_fixed_rate = sd.underlying_fixed_rate.value

        case _:
            return Err(
                "Dodd-Frank swap report requires CDS or swaption order, "
                f"got {type(order.instrument_detail).__name__}"
            )

    now = UtcDatetime.now()
    # CDS notional is the contract notional (quantity), not quantity * price.
    # Swaption notional is also quantity (contract size).
    notional = order.quantity.value

    report = DoddFrankSwapReport(
        usi=usi,
        reporting_counterparty_lei=order.executing_party_lei,
        non_reporting_counterparty_lei=order.counterparty_lei,
        instrument_id=order.instrument_id,
        asset_class=asset_class,
        product_type=product_type,
        notional=notional,
        currency=order.currency,
        effective_date=effective_date,
        maturity_date=maturity_date,
        report_timestamp=now,
        attestation_refs=(trade_attestation_id,),
        reference_entity=reference_entity,
        spread_bps=spread_bps,
        expiry_date=expiry_date,
        underlying_fixed_rate=underlying_fixed_rate,
    )

    match FirmConfidence.create(
        source="dodd-frank-reporter",
        timestamp=now.value,
        attestation_ref=trade_attestation_id,
    ):
        case Err(e):
            return Err(f"Dodd-Frank confidence: {e}")
        case Ok(confidence):
            pass

    return create_attestation(
        value=report,
        confidence=confidence,
        source="dodd-frank-reporter",
        timestamp=now.value,
        provenance=(trade_attestation_id,),
    )
