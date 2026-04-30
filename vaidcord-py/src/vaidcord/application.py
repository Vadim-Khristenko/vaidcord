from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class ApplicationRoleConnectionMetadataType(IntEnum):
    INTEGER_LESS_THAN_OR_EQUAL = 1
    INTEGER_GREATER_THAN_OR_EQUAL = 2
    INTEGER_EQUAL = 3
    INTEGER_NOT_EQUAL = 4
    DATETIME_LESS_THAN_OR_EQUAL = 5
    DATETIME_GREATER_THAN_OR_EQUAL = 6
    BOOLEAN_EQUAL = 7
    BOOLEAN_NOT_EQUAL = 8


@dataclass
class ApplicationRoleConnectionMetadata:
    type: ApplicationRoleConnectionMetadataType
    key: str
    name: str
    description: str
    name_localizations: dict[str, str] = field(default_factory=dict)
    description_localizations: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApplicationRoleConnectionMetadata":
        return cls(
            type=ApplicationRoleConnectionMetadataType(int(data["type"])),
            key=data["key"],
            name=data["name"],
            description=data["description"],
            name_localizations=data.get("name_localizations", {}) or {},
            description_localizations=data.get("description_localizations", {}) or {},
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": int(self.type),
            "key": self.key,
            "name": self.name,
            "description": self.description,
        }
        if self.name_localizations:
            payload["name_localizations"] = self.name_localizations
        if self.description_localizations:
            payload["description_localizations"] = self.description_localizations
        return payload


@dataclass
class Application:
    id: int
    name: str
    description: str = ""
    icon: str | None = None
    bot_public: bool = True
    bot_require_code_grant: bool = False
    role_connections_verification_url: str | None = None
    interactions_endpoint_url: str | None = None
    flags: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Application":
        return cls(
            id=int(data["id"]),
            name=data.get("name", ""),
            description=data.get("description", ""),
            icon=data.get("icon"),
            bot_public=data.get("bot_public", True),
            bot_require_code_grant=data.get("bot_require_code_grant", False),
            role_connections_verification_url=data.get("role_connections_verification_url"),
            interactions_endpoint_url=data.get("interactions_endpoint_url"),
            flags=data.get("flags"),
            raw=data,
        )
