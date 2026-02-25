"""Custom Temporal DataConverter for Attestor frozen-dataclass types.

Handles serialization of: Decimal, date, timedelta, frozenset, Enum,
and discriminated dataclass unions (InstrumentDetail, Payout, etc.)
by adding __type__ tags during encoding.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, get_type_hints

from temporalio.converter import (
    CompositePayloadConverter,
    DataConverter,
    DefaultPayloadConverter,
    JSONPlainPayloadConverter,
    JSONTypeConverter,
)

# ---------------------------------------------------------------------------
# Recursive serializer (replaces dataclasses.asdict)
# ---------------------------------------------------------------------------


def _to_json(obj: Any) -> Any:
    """Recursively convert Attestor objects to JSON-compatible values.

    Adds ``__type__`` tags to dataclass instances so that union types
    (InstrumentDetail, Payout, Confidence, etc.) can be round-tripped.
    """
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, Decimal):
        return {"__decimal__": str(obj)}
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return {"__date__": obj.isoformat()}
    if isinstance(obj, timedelta):
        return {"__timedelta_s__": obj.total_seconds()}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, frozenset):
        return {"__frozenset__": sorted(str(x) for x in obj)}
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        d: dict[str, Any] = {
            "__type__": f"{type(obj).__module__}.{type(obj).__qualname__}",
        }
        for field in dataclasses.fields(obj):
            d[field.name] = _to_json(getattr(obj, field.name))
        return d
    if isinstance(obj, tuple):
        return [_to_json(x) for x in obj]
    if isinstance(obj, list):
        return [_to_json(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _to_json(v) for k, v in obj.items()}
    # Fallback: try str
    return str(obj)


class AttestorJSONEncoder(json.JSONEncoder):
    """JSON encoder using _to_json for full Attestor type support."""

    def default(self, o: Any) -> Any:
        result = _to_json(o)
        if result is not o:
            return result
        return super().default(o)


# ---------------------------------------------------------------------------
# Recursive deserializer
# ---------------------------------------------------------------------------

# Security: only resolve classes from these Attestor modules.
_ALLOWED_MODULES: frozenset[str] = frozenset({
    "attestor.core.identifiers",
    "attestor.core.money",
    "attestor.core.types",
    "attestor.gateway.types",
    "attestor.instrument.asset",
    "attestor.instrument.derivative_types",
    "attestor.instrument.lifecycle",
    "attestor.instrument.types",
    "attestor.oracle.attestation",
    "attestor.workflow.types",
})

# Cache for class resolution
_CLASS_CACHE: dict[str, type] = {}


def _resolve_class(fqn: str) -> type | None:
    """Resolve a fully qualified class name to a type.

    Only classes from ``_ALLOWED_MODULES`` are resolved — prevents
    arbitrary class instantiation from crafted payloads.
    """
    if fqn in _CLASS_CACHE:
        return _CLASS_CACHE[fqn]
    parts = fqn.rsplit(".", 1)
    if len(parts) != 2:
        return None
    module_name, class_name = parts
    if module_name not in _ALLOWED_MODULES:
        return None
    try:
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name, None)
        if cls is not None:
            _CLASS_CACHE[fqn] = cls
        return cls
    except (ImportError, AttributeError):
        return None


def _from_json(hint: Any, value: Any) -> Any:
    """Recursively convert JSON values back to Attestor types."""
    if value is None:
        return None

    # Tagged dataclass
    if isinstance(value, dict) and "__type__" in value:
        cls = _resolve_class(value["__type__"])
        if cls is not None and dataclasses.is_dataclass(cls):
            try:
                hints = get_type_hints(cls)
            except Exception:
                hints = {}
            kwargs: dict[str, Any] = {}
            for field in dataclasses.fields(cls):
                if field.name in value:
                    field_hint = hints.get(field.name, type(value[field.name]))
                    kwargs[field.name] = _from_json(field_hint, value[field.name])
                elif field.default is not dataclasses.MISSING:
                    kwargs[field.name] = field.default
                elif field.default_factory is not dataclasses.MISSING:
                    kwargs[field.name] = field.default_factory()
            return cls(**kwargs)

    # Decimal
    if isinstance(value, dict) and "__decimal__" in value:
        return Decimal(value["__decimal__"])
    if hint is Decimal:
        if isinstance(value, str):
            return Decimal(value)
        if isinstance(value, (int, float)):
            return Decimal(str(value))

    # datetime (ISO string) — must come before date check
    if hint is datetime and isinstance(value, str):
        return datetime.fromisoformat(value)
    if isinstance(value, str) and "T" in value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass

    # date (not datetime)
    if isinstance(value, dict) and "__date__" in value:
        return date.fromisoformat(value["__date__"])

    # timedelta
    if isinstance(value, dict) and "__timedelta_s__" in value:
        return timedelta(seconds=value["__timedelta_s__"])

    # frozenset
    if isinstance(value, dict) and "__frozenset__" in value:
        return frozenset(value["__frozenset__"])

    # date from ISO string
    if hint is date and isinstance(value, str):
        return date.fromisoformat(value)

    # Enum
    if isinstance(hint, type) and issubclass(hint, Enum) and not isinstance(value, Enum):
        return hint(value)

    # tuple from list
    if isinstance(value, list):
        return tuple(_from_json(Any, x) for x in value)

    return value


class AttestorJSONTypeConverter(JSONTypeConverter):
    """Deserialize tagged JSON values back to Attestor types."""

    def to_typed_value(
        self, hint: type, value: Any,
    ) -> Any:
        # Let our recursive deserializer handle tagged dicts
        if isinstance(value, dict) and "__type__" in value:
            return _from_json(hint, value)
        if isinstance(value, dict) and "__decimal__" in value:
            return Decimal(value["__decimal__"])
        if isinstance(value, dict) and "__date__" in value:
            return date.fromisoformat(value["__date__"])
        if isinstance(value, dict) and "__timedelta_s__" in value:
            return timedelta(seconds=value["__timedelta_s__"])
        if isinstance(value, dict) and "__frozenset__" in value:
            return frozenset(value["__frozenset__"])
        if hint is Decimal and isinstance(value, (int, float, str)):
            return Decimal(str(value))
        if hint is date and isinstance(value, str):
            return date.fromisoformat(value)
        # Handle Python 3.12 type aliases (e.g., type InstrumentDetail = ...)
        # These are TypeAliasType instances that Temporal can't resolve
        if hasattr(hint, "__value__"):
            # It's a TypeAliasType — resolve the underlying union
            return _from_json(hint.__value__, value)
        return JSONTypeConverter.Unhandled


# ---------------------------------------------------------------------------
# Wire up
# ---------------------------------------------------------------------------


class AttestorPayloadConverter(CompositePayloadConverter):
    """Payload converter with Attestor-aware JSON handling."""

    def __init__(self) -> None:
        json_converter = JSONPlainPayloadConverter(
            encoder=AttestorJSONEncoder,
            custom_type_converters=[AttestorJSONTypeConverter()],
        )
        super().__init__(
            *(
                c
                for c in DefaultPayloadConverter.default_encoding_payload_converters
                if not isinstance(c, JSONPlainPayloadConverter)
            ),
            json_converter,
        )


ATTESTOR_DATA_CONVERTER = DataConverter(
    payload_converter_class=AttestorPayloadConverter,
)
