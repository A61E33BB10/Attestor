"""Error value hierarchy — no domain function raises exceptions.

Every error is a frozen dataclass value that can be pattern-matched,
serialized, and stored. Base class AttestorError, seven @final subclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import final

from attestor.core.types import UtcDatetime


@dataclass(frozen=True, slots=True)
class AttestorError:
    """Base error value. NOT @final — has subclasses."""

    message: str
    code: str
    timestamp: UtcDatetime
    source: str  # "module.function" that produced this error

    def with_context(self, context: str) -> AttestorError:
        """Return a copy with context prepended to message (GAP-29)."""
        return replace(self, message=f"{context}: {self.message}")

    def to_dict(self) -> dict[str, object]:
        """Serialize to dict with stable, documented keys (GAP-30)."""
        return {
            "message": self.message,
            "code": self.code,
            "timestamp": self.timestamp.value.isoformat(),
            "source": self.source,
        }


@final
@dataclass(frozen=True, slots=True)
class FieldViolation:
    """Describes a single field validation failure."""

    path: str  # e.g. "trade.notional"
    constraint: str  # e.g. "must be positive"
    actual_value: str  # e.g. "-100"


@final
@dataclass(frozen=True, slots=True)
class ValidationError(AttestorError):
    """One or more fields failed validation."""

    fields: tuple[FieldViolation, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            **AttestorError.to_dict(self),
            "fields": [
                {"path": f.path, "constraint": f.constraint, "actual_value": f.actual_value}
                for f in self.fields
            ],
        }


@final
@dataclass(frozen=True, slots=True)
class IllegalTransitionError(AttestorError):
    """State transition is not allowed."""

    from_state: str
    to_state: str

    def to_dict(self) -> dict[str, object]:
        return {
            **AttestorError.to_dict(self),
            "from_state": self.from_state,
            "to_state": self.to_state,
        }


@final
@dataclass(frozen=True, slots=True)
class ConservationViolationError(AttestorError):
    """A conservation law was violated."""

    law_name: str
    expected: str
    actual: str

    def to_dict(self) -> dict[str, object]:
        return {
            **AttestorError.to_dict(self),
            "law_name": self.law_name,
            "expected": self.expected,
            "actual": self.actual,
        }


@final
@dataclass(frozen=True, slots=True)
class MissingObservableError(AttestorError):
    """Required market observable is not available."""

    observable: str
    as_of: str

    def to_dict(self) -> dict[str, object]:
        return {**AttestorError.to_dict(self), "observable": self.observable, "as_of": self.as_of}


@final
@dataclass(frozen=True, slots=True)
class CalibrationError(AttestorError):
    """Model calibration failed."""

    model: str

    def to_dict(self) -> dict[str, object]:
        return {**AttestorError.to_dict(self), "model": self.model}


@final
@dataclass(frozen=True, slots=True)
class PricingError(AttestorError):
    """Pricing computation failed."""

    instrument: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {**AttestorError.to_dict(self), "instrument": self.instrument, "reason": self.reason}


@final
@dataclass(frozen=True, slots=True)
class PersistenceError(AttestorError):
    """Database or storage operation failed."""

    operation: str

    def to_dict(self) -> dict[str, object]:
        return {**AttestorError.to_dict(self), "operation": self.operation}
