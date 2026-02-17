"""CDM asset taxonomy — Security with identifiers and classification.

CDM: Asset = Cash | Commodity | DigitalAsset | Instrument,
     Instrument = Security | Loan | ListedDerivative.

This module implements Security with AssetIdentifier, equity/fund classification,
and exchange listing. The ``Asset`` type alias will widen to
``Security | Cash | Commodity`` when those types are added.

Factory functions ``create_equity_security`` and ``create_fund_security``
provide ergonomic constructors for the most common cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import final

from attestor.core.identifiers import ISIN
from attestor.core.money import NonEmptyStr, validate_currency
from attestor.core.result import Err, Ok

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AssetIdTypeEnum(Enum):
    """Identifier scheme for a security.

    CDM: AssetIdTypeEnum + ProductIdTypeEnum (merged).
    """

    ISIN = "ISIN"
    CUSIP = "CUSIP"
    SEDOL = "SEDOL"
    FIGI = "FIGI"
    RIC = "RIC"
    BBGID = "BBGID"
    OTHER = "OTHER"


class EquityTypeEnum(Enum):
    """Equity sub-classification.

    CDM: EquityTypeEnum (exact).
    """

    ORDINARY = "ORDINARY"
    NON_CONVERTIBLE_PREFERENCE = "NON_CONVERTIBLE_PREFERENCE"
    DEPOSITARY_RECEIPT = "DEPOSITARY_RECEIPT"
    CONVERTIBLE_PREFERENCE = "CONVERTIBLE_PREFERENCE"


class InstrumentTypeEnum(Enum):
    """Broad instrument classification.

    CDM: InstrumentTypeEnum (subset).
    """

    EQUITY = "EQUITY"
    DEBT = "DEBT"
    FUND = "FUND"
    LISTED_DERIVATIVE = "LISTED_DERIVATIVE"


class FundProductTypeEnum(Enum):
    """Fund sub-classification.

    CDM: FundProductTypeEnum.
    """

    ETF = "ETF"
    MUTUAL_FUND = "MUTUAL_FUND"
    HEDGE_FUND = "HEDGE_FUND"
    MONEY_MARKET_FUND = "MONEY_MARKET_FUND"


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
# Dataclasses
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class AssetIdentifier:
    """A single identifier for a security (e.g. ISIN, CUSIP).

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

    CDM adds DepositaryReceiptTypeEnum as a refinement; this thin wrapper
    accommodates future extension.
    """

    equity_type: EquityTypeEnum


@final
@dataclass(frozen=True, slots=True)
class EquityClassification:
    """Classification for equity securities.

    CDM: narrows InstrumentTypeEnum.EQUITY with an EquityType sub-classification.
    """

    equity_type: EquityType


@final
@dataclass(frozen=True, slots=True)
class FundClassification:
    """Classification for fund securities.

    CDM: narrows InstrumentTypeEnum.FUND with a FundProductTypeEnum sub-classification.
    """

    fund_type: FundProductTypeEnum


type SecurityClassification = EquityClassification | FundClassification


@final
@dataclass(frozen=True, slots=True)
class Security:
    """A security in the CDM asset taxonomy.

    Invariants:
    - ``identifiers`` must be non-empty.
    - ``classification`` determines the instrument type (sum type — no invalid states).
    - ``is_exchange_listed`` is derived from ``exchange is not None``.
    """

    identifiers: tuple[AssetIdentifier, ...]
    classification: SecurityClassification
    exchange: NonEmptyStr | None
    currency: NonEmptyStr

    @property
    def is_exchange_listed(self) -> bool:
        """Derive listing status from exchange field."""
        return self.exchange is not None

    @property
    def instrument_type(self) -> InstrumentTypeEnum:
        """Derive instrument type from classification."""
        match self.classification:
            case EquityClassification():
                return InstrumentTypeEnum.EQUITY
            case FundClassification():
                return InstrumentTypeEnum.FUND

    def __post_init__(self) -> None:
        if not self.identifiers:
            raise TypeError("Security.identifiers must be non-empty")
        id_types = [aid.identifier_type for aid in self.identifiers]
        if len(id_types) != len(set(id_types)):
            raise TypeError("Security: duplicate identifier types")

    @staticmethod
    def create(
        identifiers: tuple[AssetIdentifier, ...],
        classification: SecurityClassification,
        currency: str,
        *,
        exchange: str | None = None,
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
        return Ok(Security(
            identifiers=identifiers,
            classification=classification,
            exchange=ex,
            currency=cur,
        ))


# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------

type Asset = Security  # Widen to Security | Cash | Commodity later


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
) -> Ok[Security] | Err[str]:
    """Create an equity Security with ISIN and/or CUSIP identifiers."""
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
        return Err("create_equity_security: at least one identifier (isin or cusip) required")
    return Security.create(
        identifiers=tuple(ids),
        classification=EquityClassification(
            equity_type=EquityType(equity_type=equity_type),
        ),
        currency=currency,
        exchange=exchange,
    )


def create_fund_security(
    *,
    isin: str | None = None,
    cusip: str | None = None,
    fund_type: FundProductTypeEnum = FundProductTypeEnum.ETF,
    exchange: str = "XNAS",
    currency: str = "USD",
    extra_identifiers: tuple[AssetIdentifier, ...] = (),
) -> Ok[Security] | Err[str]:
    """Create a fund Security with ISIN and/or CUSIP identifiers."""
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
        return Err("create_fund_security: at least one identifier (isin or cusip) required")
    return Security.create(
        identifiers=tuple(ids),
        classification=FundClassification(fund_type=fund_type),
        currency=currency,
        exchange=exchange,
    )
