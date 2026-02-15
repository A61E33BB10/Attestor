"""Result[T, E] — monadic error handling for Attestor.

Every function that can fail returns Result[T, E] instead of raising.
Ok[T] wraps a success value; Err[E] wraps an error.

Supports: .map, .bind/.and_then, .unwrap, .unwrap_or, .map_err.
Free functions: unwrap, map_result, sequence.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, NoReturn, final


@final
@dataclass(frozen=True, slots=True)
class Ok[T]:
    """Success variant of Result."""

    value: T

    def map[U](self, f: Callable[[T], U]) -> Ok[U]:
        """Apply f to the value, returning Ok(f(value))."""
        return Ok(f(self.value))

    def bind[U, E](self, f: Callable[[T], Ok[U] | Err[E]]) -> Ok[U] | Err[E]:
        """Apply f to the value, where f itself returns a Result."""
        return f(self.value)

    def and_then[U, E](self, f: Callable[[T], Ok[U] | Err[E]]) -> Ok[U] | Err[E]:
        """Alias for bind (Rust-familiar name)."""
        return f(self.value)

    def unwrap(self) -> T:
        """Return the value."""
        return self.value

    def unwrap_or(self, default: T) -> T:  # noqa: ARG002
        """Return the value, ignoring the default."""
        return self.value

    def map_err(self, f: Callable[[Any], Any]) -> Ok[T]:  # noqa: ARG002
        """No-op on Ok: error transform does not apply."""
        return self


@final
@dataclass(frozen=True, slots=True)
class Err[E]:
    """Error variant of Result."""

    error: E

    def map(self, f: Callable[[Any], Any]) -> Err[E]:  # noqa: ARG002
        """No-op on Err: value transform does not apply."""
        return self

    def bind(self, f: Callable[[Any], Any]) -> Err[E]:  # noqa: ARG002
        """No-op on Err: short-circuits."""
        return self

    def and_then(self, f: Callable[[Any], Any]) -> Err[E]:  # noqa: ARG002
        """No-op on Err: short-circuits."""
        return self

    def unwrap(self) -> NoReturn:
        """Raise RuntimeError — there is no value to return."""
        raise RuntimeError(f"Called unwrap on Err: {self.error}")

    def unwrap_or[T](self, default: T) -> T:
        """Return the default since there is no Ok value."""
        return default

    def map_err[F](self, f: Callable[[E], F]) -> Err[F]:
        """Apply f to the error, returning Err(f(error))."""
        return Err(f(self.error))


type Result[T, E] = Ok[T] | Err[E]


# --- Free functions ---


def unwrap[T](result: Ok[T] | Err[Any]) -> T:
    """Extract Ok value or raise RuntimeError. Test/boundary code only."""
    if isinstance(result, Ok):
        return result.value
    if isinstance(result, Err):
        raise RuntimeError(f"unwrap on Err: {result.error}")
    raise TypeError(f"Expected Ok or Err, got {type(result).__name__}")


def map_result[T, U, E](result: Ok[T] | Err[E], f: Callable[[T], U]) -> Ok[U] | Err[E]:
    """Apply f to Ok value, pass Err through unchanged."""
    if isinstance(result, Ok):
        return Ok(f(result.value))
    return result


def sequence[T, E](results: Iterable[Ok[T] | Err[E]]) -> Ok[list[T]] | Err[E]:
    """Collect Results into Result of list. Short-circuits on first Err."""
    values: list[T] = []
    for r in results:
        if isinstance(r, Err):
            return r
        if isinstance(r, Ok):
            values.append(r.value)
    return Ok(values)
