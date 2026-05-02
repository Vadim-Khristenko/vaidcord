from __future__ import annotations

import pytest

from vaidcord.components import (
    IS_COMPONENTS_V2,
    ButtonStyle,
    ComponentType,
    action_row,
    button,
    components_v2_message,
    container,
    label,
    select_menu,
    select_option,
    text_display,
    text_input,
)


def test_components_v2_message_sets_flag() -> None:
    payload = components_v2_message([text_display("hello")], flags=4)

    assert payload == {
        "flags": IS_COMPONENTS_V2 | 4,
        "components": [{"type": int(ComponentType.TEXT_DISPLAY), "content": "hello"}],
    }


def test_button_validates_required_fields() -> None:
    with pytest.raises(ValueError):
        button(style=ButtonStyle.PRIMARY)

    assert button(style=ButtonStyle.LINK, label="Docs", url="https://docs.discord.com") == {
        "type": int(ComponentType.BUTTON),
        "style": int(ButtonStyle.LINK),
        "label": "Docs",
        "url": "https://docs.discord.com",
    }


def test_container_action_row_and_modal_label_build_payloads() -> None:
    row = action_row(
        [
            button(
                style=ButtonStyle.SUCCESS,
                custom_id="confirm",
                label="Confirm",
            )
        ]
    )
    panel = container([text_display("# Title"), row], accent_color=0x57F287)
    modal_label = label("Reason", text_input("reason", style=2))

    assert panel["type"] == int(ComponentType.CONTAINER)
    assert panel["components"][1]["type"] == int(ComponentType.ACTION_ROW)
    assert modal_label["component"]["custom_id"] == "reason"


def test_select_menu_supports_string_options() -> None:
    payload = select_menu(
        ComponentType.STRING_SELECT,
        "mode",
        options=[select_option("Fast", "fast")],
        placeholder="Mode",
    )

    assert payload["type"] == int(ComponentType.STRING_SELECT)
    assert payload["options"] == [{"label": "Fast", "value": "fast"}]
