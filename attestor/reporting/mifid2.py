"""MiFID II trade reporting — pure projection from CanonicalOrder.

INV-R01: Reporting is projection, not transformation.
Instrument-specific fields use a discriminated union (Minsky F3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import assert_never, final

from attestor.core.identifiers import LEI
from attestor.core.money import NonEmptyStr, PositiveDecimal
from attestor.core.result import Err, Ok
from attestor.core.serialization import content_hash
from attestor.core.types import UtcDatetime
from attestor.gateway.types import CanonicalOrder, OrderSide
from attestor.instrument.derivative_types import (
    CDSDetail,
    EquityDetail,
    FuturesDetail,
    FXDetail,
    IRSwapDetail,
    OptionDetail,
    OptionStyle,
    OptionType,
    SwaptionDetail,
)
from attestor.oracle.attestation import (
    Attestation,
    FirmConfidence,
    create_attestation,
)


class TradingCapacityEnum(Enum):
    """MiFID II trading capacity indicator.

    CDM: TradingCapacityEnum (~3 values).
    RTS 25 Field 29: capacity in which the firm traded.
    """

    DEAL = "DEAL"  # Dealing on own account
    MTCH = "MTCH"  # Matched principal trading
    AOTC = "AOTC"  # Any other trading capacity


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


@final
@dataclass(frozen=True, slots=True)
class CDSReportFields:
    """CDS-specific fields for MiFID II report."""

    reference_entity: str
    spread_bps: Decimal
    seniority: str
    protection_side: str


@final
@dataclass(frozen=True, slots=True)
class SwaptionReportFields:
    """Swaption-specific fields for MiFID II report."""

    swaption_type: str
    expiry_date: date
    underlying_fixed_rate: Decimal
    underlying_tenor_months: int
    settlement_type: str


@final
@dataclass(frozen=True, slots=True)
class CollateralReportFields:
    """Collateral-specific fields for MiFID II report."""

    collateral_type: str
    agreement_id: str
    threshold: Decimal
    minimum_transfer_amount: Decimal


type InstrumentReportFields = (
    OptionReportFields | FuturesReportFields
    | FXReportFields | IRSwapReportFields
    | CDSReportFields | SwaptionReportFields
    | CollateralReportFields
    | None
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
    # Phase F: regulatory reporting enrichment
    cfi_code: NonEmptyStr | None = None
    trading_capacity: TradingCapacityEnum | None = None
    investment_decision_person: NonEmptyStr | None = None
    executing_person: NonEmptyStr | None = None
    risk_reducing_transaction: bool | None = None
    securities_financing_indicator: bool | None = None


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
                fixed_rate=ird.fixed_rate,
                float_index=ird.float_index.value,
                day_count=ird.day_count,
                tenor_months=ird.tenor_months,
                notional_currency=order.currency.value,
            )
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
                underlying_fixed_rate=sd.underlying_fixed_rate,
                underlying_tenor_months=sd.underlying_tenor_months,
                settlement_type=sd.settlement_type.value,
            )
        case EquityDetail():
            inst_fields = None
        case _never:
            assert_never(_never)

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
