from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

CommandHandler = Callable[[Any], Awaitable[None]]


class ApplicationCommandType(IntEnum):
    CHAT_INPUT = 1
    USER = 2
    MESSAGE = 3


@dataclass(slots=True)
class RegisteredCommand:
    name: str
    description: str
    kind: ApplicationCommandType
    handler: CommandHandler
    guild_id: int | None = None
    options: list[dict[str, Any]] = field(default_factory=list)
    dm_permission: bool | None = None
    default_member_permissions: str | None = None
    name_localizations: dict[str, str] | None = None
    description_localizations: dict[str, str] | None = None
    integration_types: list[int] | None = None
    contexts: list[int] | None = None
    nsfw: bool | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": int(self.kind),
            "name": self.name,
        }
        if self.name_localizations is not None:
            payload["name_localizations"] = dict(self.name_localizations)
        if self.kind == ApplicationCommandType.CHAT_INPUT:
            payload["description"] = self.description or "No description"
            if self.description_localizations is not None:
                payload["description_localizations"] = dict(self.description_localizations)
            if self.options:
                payload["options"] = _validate_options(self.options)
        if self.dm_permission is not None:
            payload["dm_permission"] = self.dm_permission
        if self.default_member_permissions is not None:
            payload["default_member_permissions"] = self.default_member_permissions
        if self.integration_types is not None:
            payload["integration_types"] = list(self.integration_types)
        if self.contexts is not None:
            payload["contexts"] = list(self.contexts)
        if self.nsfw is not None:
            payload["nsfw"] = self.nsfw
        return payload


def _validate_options(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_optional = False
    normalized: list[dict[str, Any]] = []
    for option in options:
        item = dict(option)
        if item.get("required") is True and seen_optional:
            raise ValueError("Discord command options must list required options before optional options")
        if item.get("required") is not True:
            seen_optional = True
        nested = item.get("options")
        if isinstance(nested, list):
            item["options"] = _validate_options(nested)
        normalized.append(item)
    return normalized


@dataclass(slots=True)
class CommandContext:
    raw: dict[str, Any]

    @property
    def name(self) -> str | None:
        data = self.raw.get("data")
        if not isinstance(data, dict):
            return None
        name = data.get("name")
        return name if isinstance(name, str) else None

    @property
    def guild_id(self) -> int | None:
        value = self.raw.get("guild_id")
        if value is None:
            return None
        return int(value)

    @property
    def options(self) -> dict[str, Any]:
        data = self.raw.get("data")
        if not isinstance(data, dict):
            return {}
        result: dict[str, Any] = {}
        for item in data.get("options", []):
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str):
                continue
            result[name] = item.get("value")
        return result

    def option(self, name: str, default: Any = None) -> Any:
        return self.options.get(name, default)

    def option_str(self, name: str, default: str | None = None) -> str | None:
        value = self.option(name, default)
        if value is None:
            return None
        return str(value)

    def option_int(self, name: str, default: int | None = None) -> int | None:
        value = self.option(name, default)
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        return int(value)

    def option_float(self, name: str, default: float | None = None) -> float | None:
        value = self.option(name, default)
        if value is None:
            return None
        if isinstance(value, bool):
            return float(int(value))
        return float(value)

    def option_bool(self, name: str, default: bool | None = None) -> bool | None:
        value = self.option(name, default)
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        text = str(value).strip().lower()
        if text in {"true", "1", "yes", "y", "on"}:
            return True
        if text in {"false", "0", "no", "n", "off"}:
            return False
        raise ValueError(f"Option '{name}' cannot be parsed as bool: {value!r}")

    def require_option(self, name: str) -> Any:
        if name not in self.options:
            raise KeyError(f"Missing required option: {name}")
        return self.options[name]

    def require_str(self, name: str) -> str:
        return str(self.require_option(name))

    def require_int(self, name: str) -> int:
        value = self.require_option(name)
        if isinstance(value, bool):
            return int(value)
        return int(value)

    def require_float(self, name: str) -> float:
        value = self.require_option(name)
        if isinstance(value, bool):
            return float(int(value))
        return float(value)

    def require_bool(self, name: str) -> bool:
        value = self.option_bool(name, None)
        if value is None:
            raise KeyError(f"Missing required option: {name}")
        return value

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)
