from __future__ import annotations

from typing import ClassVar, Self


class State:
    """Aiogram-like declarative FSM state."""

    def __init__(self, state: str | None = None) -> None:
        self._explicit_state = state
        self._group_name: str | None = None
        self._name: str | None = None

    def __set_name__(self, owner: type[StatesGroup], name: str) -> None:
        self._group_name = owner.__name__
        self._name = name

    @property
    def state(self) -> str:
        if self._explicit_state is not None:
            return self._explicit_state
        if self._group_name is None or self._name is None:
            raise RuntimeError("State is not bound to a StatesGroup")
        return f"{self._group_name}:{self._name}"

    def __str__(self) -> str:
        return self.state

    def __repr__(self) -> str:
        return f"<State {self.state!r}>"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, State):
            return self.state == other.state
        if isinstance(other, str):
            return self.state == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.state)


class StatesGroup:
    """Base class for declarative FSM state groups."""

    __states__: ClassVar[tuple[State, ...]]

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        cls.__states__ = tuple(
            value for value in cls.__dict__.values() if isinstance(value, State)
        )

    @classmethod
    def states(cls) -> tuple[State, ...]:
        return cls.__states__

    @classmethod
    def state_names(cls) -> tuple[str, ...]:
        return tuple(state.state for state in cls.__states__)

    @classmethod
    def all(cls) -> tuple[State, ...]:
        return cls.states()

    def __new__(cls) -> Self:
        raise TypeError("StatesGroup classes are declarative and should not be instantiated")
