"""Canonical serialization and content-addressed hashing.

canonical_bytes(obj) -> Result[bytes, str]: deterministic JSON bytes.
content_hash(obj) -> Result[str, str]: SHA-256 hex of canonical bytes.
derive_seed(name) -> str: deterministic seed from identifier.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from attestor.core.result import Err, Ok
from attestor.core.types import FrozenMap, UtcDatetime


def _to_serializable(obj: object) -> Any:  # noqa: PLR0911
    """Recursively convert a domain object to a JSON-compatible Python value."""
    if obj is None:
        return None
    # bool before int (bool is subclass of int)
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, str):
        return obj
    if isinstance(obj, Decimal):
        # GAP-05: normalize, but map all zeros to "0"
        if obj == 0:
            return "0"
        return str(obj.normalize())
    if isinstance(obj, UtcDatetime):
        return obj.value.isoformat()
    if isinstance(obj, datetime):
        # GAP-14: reject naive datetimes
        if obj.tzinfo is None:
            msg = "Cannot serialize naive datetime — use UtcDatetime"
            raise TypeError(msg)
        return obj.astimezone(UTC).isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, (tuple, list)):
        return [_to_serializable(x) for x in obj]
    if isinstance(obj, FrozenMap):
        return {str(k): _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {str(k): _to_serializable(v) for k, v in sorted(obj.items())}
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        field_names = sorted(f.name for f in dataclasses.fields(obj))
        result: dict[str, Any] = {"_type": type(obj).__name__}
        for name in field_names:
            result[name] = _to_serializable(getattr(obj, name))
        return result
    msg = f"Cannot serialize {type(obj).__name__}"
    raise TypeError(msg)


def canonical_bytes(obj: object) -> Ok[bytes] | Err[str]:
    """Convert any domain type to canonical JSON bytes.

    Returns Err on unsupported types (GAP-04: never raises TypeError).
    Type names are part of the serialization contract (GAP-11 / D-12).
    """
    try:
        serializable = _to_serializable(obj)
    except TypeError as e:
        return Err(f"Unsupported type in canonical serialization: {e}")
    return Ok(
        json.dumps(serializable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def content_hash(obj: object) -> Ok[str] | Err[str]:
    """SHA-256 hex digest of canonical_bytes(obj)."""
    match canonical_bytes(obj):
        case Err() as e:
            return e
        case Ok(b):
            return Ok(hashlib.sha256(b).hexdigest())


def derive_seed(name: str) -> str:
    """Deterministic seed from an identifier string."""
    return hashlib.sha256(name.encode("utf-8")).hexdigest()
