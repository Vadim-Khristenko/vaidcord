from __future__ import annotations

from enum import IntEnum
from typing import Any

IS_COMPONENTS_V2 = 1 << 15


class ComponentType(IntEnum):
    ACTION_ROW = 1
    BUTTON = 2
    STRING_SELECT = 3
    TEXT_INPUT = 4
    USER_SELECT = 5
    ROLE_SELECT = 6
    MENTIONABLE_SELECT = 7
    CHANNEL_SELECT = 8
    SECTION = 9
    TEXT_DISPLAY = 10
    THUMBNAIL = 11
    MEDIA_GALLERY = 12
    FILE = 13
    SEPARATOR = 14
    CONTAINER = 17
    LABEL = 18
    FILE_UPLOAD = 19
    RADIO_GROUP = 21
    CHECKBOX_GROUP = 22
    CHECKBOX = 23


class ButtonStyle(IntEnum):
    PRIMARY = 1
    SECONDARY = 2
    SUCCESS = 3
    DANGER = 4
    LINK = 5
    PREMIUM = 6


def components_v2_message(
    components: list[dict[str, Any]],
    *,
    flags: int = 0,
    allowed_mentions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if len(components) > 40:
        raise ValueError("Discord Components V2 messages allow up to 40 total components")
    payload: dict[str, Any] = {"flags": flags | IS_COMPONENTS_V2, "components": components}
    if allowed_mentions is not None:
        payload["allowed_mentions"] = allowed_mentions
    return payload


def modal_payload(custom_id: str, title: str, components: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": 9,
        "data": {
            "custom_id": custom_id,
            "title": title,
            "components": components,
        },
    }


def action_row(components: list[dict[str, Any]], *, id: int | None = None) -> dict[str, Any]:
    if len(components) > 5:
        raise ValueError("Action rows allow up to 5 buttons or one select component")
    payload = _component(ComponentType.ACTION_ROW, id=id)
    payload["components"] = components
    return payload


def button(
    *,
    style: ButtonStyle | int = ButtonStyle.PRIMARY,
    custom_id: str | None = None,
    label: str | None = None,
    emoji: dict[str, Any] | None = None,
    url: str | None = None,
    sku_id: int | str | None = None,
    disabled: bool | None = None,
    id: int | None = None,
) -> dict[str, Any]:
    style_value = int(style)
    payload = _component(ComponentType.BUTTON, id=id)
    payload["style"] = style_value
    if style_value == ButtonStyle.LINK and not url:
        raise ValueError("Link buttons require url")
    if style_value == ButtonStyle.PREMIUM and sku_id is None:
        raise ValueError("Premium buttons require sku_id")
    if style_value not in {ButtonStyle.LINK, ButtonStyle.PREMIUM} and not custom_id:
        raise ValueError("Interactive buttons require custom_id")
    _set_optional(payload, "custom_id", custom_id)
    _set_optional(payload, "label", label)
    _set_optional(payload, "emoji", emoji)
    _set_optional(payload, "url", url)
    if sku_id is not None:
        payload["sku_id"] = str(sku_id)
    _set_optional(payload, "disabled", disabled)
    return payload


def select_menu(
    component_type: ComponentType | int,
    custom_id: str,
    *,
    options: list[dict[str, Any]] | None = None,
    placeholder: str | None = None,
    min_values: int | None = None,
    max_values: int | None = None,
    required: bool | None = None,
    disabled: bool | None = None,
    default_values: list[dict[str, Any]] | None = None,
    channel_types: list[int] | None = None,
    id: int | None = None,
) -> dict[str, Any]:
    payload = _component(component_type, id=id)
    payload["custom_id"] = custom_id
    _set_optional(payload, "options", options)
    _set_optional(payload, "placeholder", placeholder)
    _set_optional(payload, "min_values", min_values)
    _set_optional(payload, "max_values", max_values)
    _set_optional(payload, "required", required)
    _set_optional(payload, "disabled", disabled)
    _set_optional(payload, "default_values", default_values)
    _set_optional(payload, "channel_types", channel_types)
    return payload


def select_option(
    label: str,
    value: str,
    *,
    description: str | None = None,
    emoji: dict[str, Any] | None = None,
    default: bool | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"label": label, "value": value}
    _set_optional(payload, "description", description)
    _set_optional(payload, "emoji", emoji)
    _set_optional(payload, "default", default)
    return payload


def text_input(
    custom_id: str,
    *,
    style: int = 1,
    min_length: int | None = None,
    max_length: int | None = None,
    required: bool | None = None,
    value: str | None = None,
    placeholder: str | None = None,
    id: int | None = None,
) -> dict[str, Any]:
    payload = _component(ComponentType.TEXT_INPUT, id=id)
    payload.update({"custom_id": custom_id, "style": style})
    _set_optional(payload, "min_length", min_length)
    _set_optional(payload, "max_length", max_length)
    _set_optional(payload, "required", required)
    _set_optional(payload, "value", value)
    _set_optional(payload, "placeholder", placeholder)
    return payload


def text_display(content: str, *, id: int | None = None) -> dict[str, Any]:
    payload = _component(ComponentType.TEXT_DISPLAY, id=id)
    payload["content"] = content
    return payload


def thumbnail(
    url: str,
    *,
    description: str | None = None,
    spoiler: bool | None = None,
    id: int | None = None,
) -> dict[str, Any]:
    payload = _component(ComponentType.THUMBNAIL, id=id)
    payload["media"] = {"url": url}
    _set_optional(payload, "description", description)
    _set_optional(payload, "spoiler", spoiler)
    return payload


def media_gallery(items: list[dict[str, Any]], *, id: int | None = None) -> dict[str, Any]:
    if not 1 <= len(items) <= 10:
        raise ValueError("Media gallery requires 1 to 10 items")
    payload = _component(ComponentType.MEDIA_GALLERY, id=id)
    payload["items"] = items
    return payload


def media_item(
    url: str,
    *,
    description: str | None = None,
    spoiler: bool | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"media": {"url": url}}
    _set_optional(payload, "description", description)
    _set_optional(payload, "spoiler", spoiler)
    return payload


def file_component(url: str, *, spoiler: bool | None = None, id: int | None = None) -> dict[str, Any]:
    payload = _component(ComponentType.FILE, id=id)
    payload["file"] = {"url": url}
    _set_optional(payload, "spoiler", spoiler)
    return payload


def separator(
    *,
    divider: bool | None = None,
    spacing: int | None = None,
    id: int | None = None,
) -> dict[str, Any]:
    payload = _component(ComponentType.SEPARATOR, id=id)
    _set_optional(payload, "divider", divider)
    _set_optional(payload, "spacing", spacing)
    return payload


def section(
    components: list[dict[str, Any]],
    accessory: dict[str, Any],
    *,
    id: int | None = None,
) -> dict[str, Any]:
    if not 1 <= len(components) <= 3:
        raise ValueError("Section requires 1 to 3 text components")
    payload = _component(ComponentType.SECTION, id=id)
    payload["components"] = components
    payload["accessory"] = accessory
    return payload


def container(
    components: list[dict[str, Any]],
    *,
    accent_color: int | None = None,
    spoiler: bool | None = None,
    id: int | None = None,
) -> dict[str, Any]:
    payload = _component(ComponentType.CONTAINER, id=id)
    payload["components"] = components
    _set_optional(payload, "accent_color", accent_color)
    _set_optional(payload, "spoiler", spoiler)
    return payload


def label(
    text: str,
    component: dict[str, Any],
    *,
    description: str | None = None,
    id: int | None = None,
) -> dict[str, Any]:
    payload = _component(ComponentType.LABEL, id=id)
    payload["label"] = text
    payload["component"] = component
    _set_optional(payload, "description", description)
    return payload


def checkbox(custom_id: str, *, default: bool | None = None, id: int | None = None) -> dict[str, Any]:
    payload = _component(ComponentType.CHECKBOX, id=id)
    payload["custom_id"] = custom_id
    _set_optional(payload, "default", default)
    return payload


def _component(component_type: ComponentType | int, *, id: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": int(component_type)}
    _set_optional(payload, "id", id)
    return payload


def _set_optional(payload: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        payload[key] = value
