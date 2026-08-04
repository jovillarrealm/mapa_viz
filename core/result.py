from dataclasses import dataclass
from typing import TypeVar
from collections.abc import Callable

T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")


@dataclass(frozen=True)
class Ok[T]:
    """Represents a successful operation containing value `T`."""

    value: T

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self.value

    def unwrap_or(self, default: T) -> T:
        return self.value

    def map(self, fn: Callable[[T], U]) -> Result[U, E]:
        return Ok(fn(self.value))

    def and_then(self, fn: Callable[[T], Result[U, E]]) -> Result[U, E]:
        return fn(self.value)


@dataclass(frozen=True)
class Err[E]:
    """Represents a failed operation containing error `E`."""

    error: E

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def unwrap(self) -> T:
        raise ValueError(f"Called unwrap on Err: {self.error}")

    def unwrap_or(self, default: T) -> T:
        return default

    def map(self, fn: Callable[[T], U]) -> Result[U, E]:
        return Err(self.error)

    def and_then(self, fn: Callable[[T], Result[U, E]]) -> Result[U, E]:
        return Err(self.error)


type Result[T, E] = Ok[T] | Err[E]
