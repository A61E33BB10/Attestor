"""EMIR trade reporting — pure projection from CanonicalOrder.

INV-R01: Reporting is projection, not transformation. No new values computed.
The report contains exactly the fields from the order, reformatted to EMIR schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import final

from attestor.core.identifiers import ISIN, LEI, UTI
from attestor.core.money import NonEmptyStr, PositiveDecimal
from attestor.core.result import Err, Ok
from attestor.core.serialization import content_hash
from attestor.core.types import UtcDatetime
from attestor.gateway.types import CanonicalOrder, OrderSide
from attestor.instrument.derivative_types import CDSDetail, SwaptionDetail
from attestor.oracle.attestation import (
    Attestation,
    FirmConfidence,
    create_attestation,
)
from attestor.reporting.mifid2 import (
    CDSReportFields,
    InstrumentReportFields,
    SwaptionReportFields,
)


@final
@dataclass(frozen=True, slots=True)
class EMIRTradeReport:
    """EMIR trade report — pure projection from CanonicalOrder."""

    uti: UTI
    reporting_counterparty_lei: LEI
    other_counterparty_lei: LEI
    instrument_id: NonEmptyStr
    isin: ISIN | None
    direction: OrderSide
    quantity: PositiveDecimal
    price: Decimal
    currency: NonEmptyStr
    trade_date: date
    settlement_date: date
    venue: NonEmptyStr
    report_timestamp: UtcDatetime
    instrument_fields: InstrumentReportFields
    attestation_refs: tuple[str, ...]


def project_emir_report(
    order: CanonicalOrder,
    trade_attestation_id: str,
) -> Ok[Attestation[EMIRTradeReport]] | Err[str]:
    """Project an EMIR report from a canonical order.

    INV-R01: This is a PROJECTION, not a transformation.
    The report contains exactly the fields from the order, reformatted
    to EMIR schema. No new values are computed.
    """
    # Generate UTI from content hash of the order
    match content_hash(order):
        case Err(e):
            return Err(f"Cannot compute UTI: {e}")
        case Ok(ch):
            pass

    # UTI = first 52 chars of the LEI prefix + hash (ensuring alnum prefix)
    uti_value = order.executing_party_lei.value + ch[:32]
    match UTI.parse(uti_value):
        case Err(e):
            return Err(f"UTI: {e}")
        case Ok(uti):
            pass

    # Build instrument-specific fields from order detail
    inst_fields: InstrumentReportFields = None
    match order.instrument_detail:
        case CDSDetail() as cd:
            inst_fields = CDSReportFields(
                reference_entity=cd.reference_entity.value,
                spread_bps=cd.spread_bps.value,
                seniority=cd.seniority.value,
                protection_side=cd.protection_side.value,
            )
        case SwaptionDetail() as sd:
            inst_fields = SwaptionReportFields(
                swaption_type=sd.swaption_type.value,
                expiry_date=sd.expiry_date,
                underlying_fixed_rate=sd.underlying_fixed_rate.value,
                underlying_tenor_months=sd.underlying_tenor_months,
                settlement_type=sd.settlement_type.value,
            )

    report = EMIRTradeReport(
        uti=uti,
        reporting_counterparty_lei=order.executing_party_lei,
        other_counterparty_lei=order.counterparty_lei,
        instrument_id=order.instrument_id,
        isin=order.isin,
        direction=order.side,
        quantity=order.quantity,
        price=order.price,
        currency=order.currency,
        trade_date=order.trade_date,
        settlement_date=order.settlement_date,
        venue=order.venue,
        report_timestamp=order.timestamp,
        instrument_fields=inst_fields,
        attestation_refs=(trade_attestation_id,),
    )

    match FirmConfidence.create(
        source="EMIR_REPORTING",
        timestamp=order.timestamp.value,
        attestation_ref=trade_attestation_id,
    ):
        case Err(e):
            return Err(f"confidence: {e}")
        case Ok(confidence):
            pass

    return create_attestation(
        value=report,
        confidence=confidence,
        source="EMIR_REPORTING",
        timestamp=order.timestamp.value,
        provenance=(trade_attestation_id,),
    )
