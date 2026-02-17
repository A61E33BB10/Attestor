"""CDM asset taxonomy -- Security with identifiers and classification.

Aligned with ISDA CDM Rosetta (base-staticdata-asset-common-*):
  Asset = Cash | Commodity | DigitalAsset | Instrument
  Instrument = Security | Loan | ListedDerivative
  InstrumentBase extends AssetBase: instrumentType
  Security extends InstrumentBase: equityType, fundType, debtType

This module implements Security with AssetIdentifier, equity/fund
classification, and exchange listing.  The ``Asset`` type alias will
widen to ``Security | Cash | Commodity`` when those types are added.

Attestor models ``instrumentType`` as a derived property of the
``SecurityClassification`` sum type (``EquityClassification |
FundClassification``), which makes illegal states structurally
unrepresentable -- an intentional type-safety improvement over
Rosetta's runtime-checked conditional sub-types.

Factory functions ``create_equity_security`` and ``create_fund_security``
provide ergonomic constructors for the most common cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import assert_never, final

from attestor.core.identifiers import ISIN
from attestor.core.money import NonEmptyStr, validate_currency
from attestor.core.result import Err, Ok

# ---------------------------------------------------------------------------
# Enums  (CDM Rosetta: base-staticdata-asset-common-enum.rosetta)
# ---------------------------------------------------------------------------


class AssetIdTypeEnum(Enum):
    """Identifier scheme for a security.

    CDM: ProductIdTypeEnum + AssetIdTypeEnum (merged, 18 members).
    """

    # ProductIdTypeEnum members
    BBGID = "BBGID"
    BBGTICKER = "BBGTICKER"
    CUSIP = "CUSIP"
    FIGI = "FIGI"
    ISDACRP = "ISDACRP"
    ISIN = "ISIN"
    NAME = "NAME"
    REDID = "REDID"
    RIC = "RIC"
    OTHER = "OTHER"
    SICOVAM = "SICOVAM"
    SEDOL = "SEDOL"
    UPI = "UPI"
    VALOREN = "VALOREN"
    WERTPAPIER = "WERTPAPIER"
    # AssetIdTypeEnum extensions
    CURRENCY_CODE = "CURRENCY_CODE"
    EXCHANGE_CODE = "EXCHANGE_CODE"
    CLEARING_CODE = "CLEARING_CODE"


class EquityTypeEnum(Enum):
    """Equity sub-classification.

    CDM: EquityTypeEnum (exact 4 members).
    """

    ORDINARY = "ORDINARY"
    NON_CONVERTIBLE_PREFERENCE = "NON_CONVERTIBLE_PREFERENCE"
    DEPOSITARY_RECEIPT = "DEPOSITARY_RECEIPT"
    CONVERTIBLE_PREFERENCE = "CONVERTIBLE_PREFERENCE"


class DepositaryReceiptTypeEnum(Enum):
    """Depositary receipt sub-classification.

    CDM: DepositaryReceiptTypeEnum (exact 4 members).
    Only valid when EquityTypeEnum is DEPOSITARY_RECEIPT.
    """

    ADR = "ADR"
    GDR = "GDR"
    IDR = "IDR"
    EDR = "EDR"


class InstrumentTypeEnum(Enum):
    """Broad instrument classification.

    CDM: InstrumentTypeEnum (exact 7 members).
    """

    DEBT = "DEBT"
    EQUITY = "EQUITY"
    FUND = "FUND"
    WARRANT = "WARRANT"
    CERTIFICATE = "CERTIFICATE"
    LETTER_OF_CREDIT = "LETTER_OF_CREDIT"
    LISTED_DERIVATIVE = "LISTED_DERIVATIVE"


class FundProductTypeEnum(Enum):
    """Fund sub-classification.

    CDM: FundProductTypeEnum (exact 4 members).
    """

    MONEY_MARKET_FUND = "MONEY_MARKET_FUND"
    EXCHANGE_TRADED_FUND = "EXCHANGE_TRADED_FUND"
    MUTUAL_FUND = "MUTUAL_FUND"
    OTHER_FUND = "OTHER_FUND"


# ---------------------------------------------------------------------------
# ISO 10383 MIC codes (commonly used exchanges)
# ---------------------------------------------------------------------------

VALID_EXCHANGE_MICS: frozenset[str] = frozenset({
    "XNAS",  # NASDAQ
    "XNYS",  # NYSE
    "XLON",  # LSE
    "XPAR",  # Euronext Paris
    "XFRA",  # Frankfurt
    "XHKG",  # HKEX
    "XTKS",  # Tokyo
    "XSHE",  # Shenzhen
    "XASE",  # AMEX
    "BATS",  # BATS/Cboe
    "XCHI",  # Chicago
    "XBOM",  # BSE India
    "XNSE",  # NSE India
    "XCME",  # CME
    "XEUR",  # Eurex
})


def _validate_exchange_mic(code: str) -> Ok[NonEmptyStr] | Err[str]:
    """Validate exchange MIC against known set or ISO 10383 format.

    Accepts known MICs and falls back to accepting any 4-character
    uppercase alpha string (ISO 10383 format) for forward compatibility.
    """
    if code in VALID_EXCHANGE_MICS:
        return Ok(NonEmptyStr(value=code))
    if len(code) == 4 and code.isalpha() and code.isupper():
        return Ok(NonEmptyStr(value=code))
    return Err(
        f"Invalid exchange MIC '{code}': must be a known MIC or "
        f"4 uppercase letters (ISO 10383 format)"
    )


# ---------------------------------------------------------------------------
# Dataclasses  (CDM Rosetta: base-staticdata-asset-common-type.rosetta)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class AssetIdentifier:
    """A single identifier for a security (e.g. ISIN, CUSIP).

    CDM: AssetIdentifier with identifier (string) + identifierType.

    Validation:
    - ISIN is cross-validated via ``ISIN.parse()`` (Luhn check).
    - CUSIP must be exactly 9 alphanumeric characters.
    - SEDOL must be exactly 7 alphanumeric characters.
    """

    identifier: NonEmptyStr
    identifier_type: AssetIdTypeEnum

    def __post_init__(self) -> None:
        raw = self.identifier.value
        if self.identifier_type == AssetIdTypeEnum.ISIN:
            match ISIN.parse(raw):
                case Err(e):
                    raise TypeError(f"AssetIdentifier ISIN validation: {e}")
                case Ok(_):
                    pass
        elif self.identifier_type == AssetIdTypeEnum.CUSIP:
            if len(raw) != 9 or not raw.isalnum():
                raise TypeError(
                    f"AssetIdentifier CUSIP must be 9 alphanumeric characters, "
                    f"got '{raw}'"
                )
        elif self.identifier_type == AssetIdTypeEnum.SEDOL:  # noqa: SIM102
            if len(raw) != 7 or not raw.isalnum():
                raise TypeError(
                    f"AssetIdentifier SEDOL must be 7 alphanumeric characters, "
                    f"got '{raw}'"
                )

    @staticmethod
    def create(
        identifier: str, identifier_type: AssetIdTypeEnum,
    ) -> Ok[AssetIdentifier] | Err[str]:
        match NonEmptyStr.parse(identifier):
            case Err(e):
                return Err(f"AssetIdentifier.identifier: {e}")
            case Ok(ident):
                pass
        if identifier_type == AssetIdTypeEnum.ISIN:
            match ISIN.parse(ident.value):
                case Err(e):
                    return Err(f"AssetIdentifier ISIN validation: {e}")
                case Ok(_):
                    pass
        elif identifier_type == AssetIdTypeEnum.CUSIP:
            if len(ident.value) != 9 or not ident.value.isalnum():
                return Err(
                    f"AssetIdentifier CUSIP must be 9 alphanumeric characters, "
                    f"got '{ident.value}'"
                )
        elif identifier_type == AssetIdTypeEnum.SEDOL:  # noqa: SIM102
            if len(ident.value) != 7 or not ident.value.isalnum():
                return Err(
                    f"AssetIdentifier SEDOL must be 7 alphanumeric characters, "
                    f"got '{ident.value}'"
                )
        return Ok(AssetIdentifier(identifier=ident, identifier_type=identifier_type))


@final
@dataclass(frozen=True, slots=True)
class EquityType:
    """Equity classification wrapper.

    CDM: EquityType with equityType (EquityTypeEnum) and
    depositaryReceipt (DepositaryReceiptTypeEnum).
    Condition: depositaryReceipt only when equityType == DEPOSITARY_RECEIPT.
    """

    equity_type: EquityTypeEnum
    depositary_receipt: DepositaryReceiptTypeEnum | None = None

    def __post_init__(self) -> None:
        if (
            self.depositary_receipt is not None
            and self.equity_type != EquityTypeEnum.DEPOSITARY_RECEIPT
        ):
            raise TypeError(
                "EquityType: depositary_receipt is only valid when "
                "equity_type is DEPOSITARY_RECEIPT"
            )


@final
@dataclass(frozen=True, slots=True)
class EquityClassification:
    """Classification for equity securities.

    CDM: narrows InstrumentTypeEnum.EQUITY with EquityType sub-classification.
    """

    equity_type: EquityType


@final
@dataclass(frozen=True, slots=True)
class FundClassification:
    """Classification for fund securities.

    CDM: narrows InstrumentTypeEnum.FUND with FundProductTypeEnum.
    """

    fund_type: FundProductTypeEnum


type SecurityClassification = EquityClassification | FundClassification


@final
@dataclass(frozen=True, slots=True)
class Security:
    """A security in the CDM asset taxonomy.

    CDM: Security extends InstrumentBase extends AssetBase.

    Invariants:
    - ``identifiers`` must be non-empty with unique identifier types.
    - ``classification`` determines the instrument type (sum type).
    - ``is_exchange_listed`` is a field (CDM: AssetBase.isExchangeListed).
    - CDM condition: if exchange exists then is_exchange_listed must be True.
    """

    identifiers: tuple[AssetIdentifier, ...]
    classification: SecurityClassification
    is_exchange_listed: bool
    exchange: NonEmptyStr | None
    currency: NonEmptyStr

    @property
    def instrument_type(self) -> InstrumentTypeEnum:
        """Derive instrument type from classification.

        CDM: instrumentType is a field on InstrumentBase.  Attestor derives
        it from the SecurityClassification sum type for type safety.
        """
        match self.classification:
            case EquityClassification():
                return InstrumentTypeEnum.EQUITY
            case FundClassification():
                return InstrumentTypeEnum.FUND
            case _ as unreachable:  # pragma: no cover
                assert_never(unreachable)

    def __post_init__(self) -> None:
        if not self.identifiers:
            raise TypeError("Security.identifiers must be non-empty")
        id_types = [aid.identifier_type for aid in self.identifiers]
        if len(id_types) != len(set(id_types)):
            raise TypeError("Security: duplicate identifier types")
        if self.exchange is not None and not self.is_exchange_listed:
            raise TypeError(
                "Security: exchange is set but is_exchange_listed is False "
                "(CDM condition: if exchange exists then isExchangeListed)"
            )

    @staticmethod
    def create(
        identifiers: tuple[AssetIdentifier, ...],
        classification: SecurityClassification,
        currency: str,
        *,
        exchange: str | None = None,
        is_exchange_listed: bool | None = None,
    ) -> Ok[Security] | Err[str]:
        if not identifiers:
            return Err("Security.identifiers must be non-empty")
        id_types = [aid.identifier_type for aid in identifiers]
        if len(id_types) != len(set(id_types)):
            return Err("Security: duplicate identifier types")
        if not validate_currency(currency):
            return Err(
                f"Security.currency: invalid ISO 4217 currency code '{currency}'"
            )
        cur = NonEmptyStr(value=currency)
        ex: NonEmptyStr | None = None
        if exchange is not None:
            match _validate_exchange_mic(exchange):
                case Err(e):
                    return Err(f"Security.exchange: {e}")
                case Ok(ex_val):
                    ex = ex_val
        # CDM: derive is_exchange_listed from exchange when not explicit
        listed = ex is not None if is_exchange_listed is None else is_exchange_listed
        # CDM condition: if exchange exists then isExchangeListed
        if ex is not None and not listed:
            return Err(
                "Security: exchange is set but is_exchange_listed is False "
                "(CDM condition: if exchange exists then isExchangeListed)"
            )
        return Ok(Security(
            identifiers=identifiers,
            classification=classification,
            is_exchange_listed=listed,
            exchange=ex,
            currency=cur,
        ))


# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------

type Asset = Security  # Widen to Security | Cash | Commodity later


# ---------------------------------------------------------------------------
# Shared identifier parsing helper
# ---------------------------------------------------------------------------


def _parse_identifiers(
    isin: str | None,
    cusip: str | None,
    extra_identifiers: tuple[AssetIdentifier, ...],
) -> Ok[tuple[AssetIdentifier, ...]] | Err[str]:
    """Parse ISIN and/or CUSIP into AssetIdentifiers, merged with extras."""
    ids: list[AssetIdentifier] = []
    if isin is not None:
        match AssetIdentifier.create(isin, AssetIdTypeEnum.ISIN):
            case Err(e):
                return Err(e)
            case Ok(aid):
                ids.append(aid)
    if cusip is not None:
        match AssetIdentifier.create(cusip, AssetIdTypeEnum.CUSIP):
            case Err(e):
                return Err(e)
            case Ok(aid):
                ids.append(aid)
    ids.extend(extra_identifiers)
    if not ids:
        return Err("at least one identifier (isin or cusip) required")
    return Ok(tuple(ids))


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


def create_equity_security(
    *,
    isin: str | None = None,
    cusip: str | None = None,
    equity_type: EquityTypeEnum = EquityTypeEnum.ORDINARY,
    exchange: str = "XNAS",
    currency: str = "USD",
    extra_identifiers: tuple[AssetIdentifier, ...] = (),
    depositary_receipt: DepositaryReceiptTypeEnum | None = None,
) -> Ok[Security] | Err[str]:
    """Create an equity Security with ISIN and/or CUSIP identifiers."""
    if (
        depositary_receipt is not None
        and equity_type != EquityTypeEnum.DEPOSITARY_RECEIPT
    ):
        return Err(
            "create_equity_security: depositary_receipt is only valid "
            "when equity_type is DEPOSITARY_RECEIPT"
        )
    match _parse_identifiers(isin, cusip, extra_identifiers):
        case Err(e):
            return Err(f"create_equity_security: {e}")
        case Ok(ids):
            pass
    return Security.create(
        identifiers=ids,
        classification=EquityClassification(
            equity_type=EquityType(
                equity_type=equity_type,
                depositary_receipt=depositary_receipt,
            ),
        ),
        currency=currency,
        exchange=exchange,
    )


def create_fund_security(
    *,
    isin: str | None = None,
    cusip: str | None = None,
    fund_type: FundProductTypeEnum = FundProductTypeEnum.EXCHANGE_TRADED_FUND,
    exchange: str = "XNAS",
    currency: str = "USD",
    extra_identifiers: tuple[AssetIdentifier, ...] = (),
) -> Ok[Security] | Err[str]:
    """Create a fund Security with ISIN and/or CUSIP identifiers."""
    match _parse_identifiers(isin, cusip, extra_identifiers):
        case Err(e):
            return Err(f"create_fund_security: {e}")
        case Ok(ids):
            pass
    return Security.create(
        identifiers=ids,
        classification=FundClassification(fund_type=fund_type),
        currency=currency,
        exchange=exchange,
    )
