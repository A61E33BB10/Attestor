"""MiFID II trade reporting — pure projection from CanonicalOrder.

INV-R01: Reporting is projection, not transformation.
Instrument-specific fields use a discriminated union (Minsky F3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import final

from attestor.core.identifiers import LEI
from attestor.core.money import NonEmptyStr, PositiveDecimal
from attestor.core.result import Err, Ok
from attestor.core.serialization import content_hash
from attestor.core.types import UtcDatetime
from attestor.gateway.types import CanonicalOrder, OrderSide
from attestor.instrument.derivative_types import (
    FuturesDetail,
    FXDetail,
    IRSwapDetail,
    OptionDetail,
    OptionStyle,
    OptionType,
)
from attestor.oracle.attestation import (
    Attestation,
    FirmConfidence,
    create_attestation,
)


@final
@dataclass(frozen=True, slots=True)
class OptionReportFields:
    """Option-specific fields for MiFID II report."""

    strike: Decimal
    expiry_date: date
    option_type: OptionType
    option_style: OptionStyle


@final
@dataclass(frozen=True, slots=True)
class FuturesReportFields:
    """Futures-specific fields for MiFID II report."""

    expiry_date: date
    contract_size: Decimal


@final
@dataclass(frozen=True, slots=True)
class FXReportFields:
    """FX-specific reporting fields for MiFID II."""

    currency_pair: str
    forward_rate: Decimal | None  # None for spot
    settlement_type: str


@final
@dataclass(frozen=True, slots=True)
class IRSwapReportFields:
    """IRS-specific reporting fields for MiFID II."""

    fixed_rate: Decimal
    float_index: str
    day_count: str
    tenor_months: int
    notional_currency: str


type InstrumentReportFields = (
    OptionReportFields | FuturesReportFields
    | FXReportFields | IRSwapReportFields | None
)


@final
@dataclass(frozen=True, slots=True)
class MiFIDIIReport:
    """MiFID II transaction report."""

    transaction_ref: NonEmptyStr
    reporting_entity_lei: LEI
    counterparty_lei: LEI
    instrument_id: NonEmptyStr
    instrument_fields: InstrumentReportFields
    direction: OrderSide
    quantity: PositiveDecimal
    price: Decimal
    currency: NonEmptyStr
    trade_date: date
    settlement_date: date
    venue: NonEmptyStr
    report_timestamp: UtcDatetime
    attestation_refs: tuple[str, ...]


def project_mifid2_report(
    order: CanonicalOrder,
    trade_attestation_id: str,
) -> Ok[Attestation[MiFIDIIReport]] | Err[str]:
    """INV-R01: pure projection from order."""
    # Build instrument-specific fields
    inst_fields: InstrumentReportFields = None
    match order.instrument_detail:
        case OptionDetail() as od:
            inst_fields = OptionReportFields(
                strike=od.strike.value,
                expiry_date=od.expiry_date,
                option_type=od.option_type,
                option_style=od.option_style,
            )
        case FuturesDetail() as fd:
            inst_fields = FuturesReportFields(
                expiry_date=fd.expiry_date,
                contract_size=fd.contract_size.value,
            )
        case FXDetail() as fxd:
            inst_fields = FXReportFields(
                currency_pair=fxd.currency_pair,
                forward_rate=fxd.forward_rate.value if fxd.forward_rate else None,
                settlement_type=fxd.settlement_type.value,
            )
        case IRSwapDetail() as ird:
            inst_fields = IRSwapReportFields(
                fixed_rate=ird.fixed_rate.value,
                float_index=ird.float_index.value,
                day_count=ird.day_count,
                tenor_months=ird.tenor_months,
                notional_currency=order.currency.value,
            )
        case _:
            inst_fields = None

    match NonEmptyStr.parse(trade_attestation_id):
        case Err(e):
            return Err(f"trade_attestation_id: {e}")
        case Ok(tx_ref):
            pass

    report = MiFIDIIReport(
        transaction_ref=tx_ref,
        reporting_entity_lei=order.executing_party_lei,
        counterparty_lei=order.counterparty_lei,
        instrument_id=order.instrument_id,
        instrument_fields=inst_fields,
        direction=order.side,
        quantity=order.quantity,
        price=order.price,
        currency=order.currency,
        trade_date=order.trade_date,
        settlement_date=order.settlement_date,
        venue=order.venue,
        report_timestamp=UtcDatetime.now(),
        attestation_refs=(trade_attestation_id,),
    )

    match content_hash(report):
        case Err(e):
            return Err(f"MiFID II content_hash: {e}")
        case Ok(_):
            pass

    match FirmConfidence.create(
        source="mifid2-reporter",
        timestamp=report.report_timestamp.value,
        attestation_ref=trade_attestation_id,
    ):
        case Err(e):
            return Err(f"MiFID II confidence: {e}")
        case Ok(confidence):
            pass

    return create_attestation(
        value=report,
        confidence=confidence,
        source="mifid2-reporter",
        timestamp=report.report_timestamp.value,
    )
