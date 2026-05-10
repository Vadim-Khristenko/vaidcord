"""Message resource service extracted from :class:`vaidcord.bot.Bot` (issue #32).

Owns every Discord message endpoint: send / reply / edit / delete /
typing / pins / reactions / polls / DMs. ``Bot`` keeps the same public
methods (``send_message``, ``reply``, ``send_dm`` ...) but each one
forwards to the matching method here, so the facade no longer expands
every time a new endpoint lands.

Why a separate service:

* ``Bot`` was over 1700 lines and had ~340 lines of message-resource
  code. Most of it has nothing to do with the gateway / lifecycle / cache
  responsibilities the rest of ``Bot`` cares about.
* The service is constructor-injected (Bot creates it once, hands itself
  in as the host), which means new resource families can be added in
  parallel modules without touching ``Bot`` at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from vaidcord.components import IS_COMPONENTS_V2
from vaidcord.errors import DiscordAPIError, ForbiddenError, RateLimitError
from vaidcord.types import Message, User

if TYPE_CHECKING:
    from vaidcord.api_client import APIClient

    from ..event_parser import EventParser


class MessageHost(Protocol):
    """Bot surface that the message service depends on."""

    api_client: APIClient
    _channels: dict[int, Any]
    _users: dict[int, Any]

    async def request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]: ...

    async def send_message(
        self, channel_id: int, content: str | None = None, **kwargs: Any
    ) -> dict[str, Any]: ...

    async def send_dm(
        self, user_id: int, content: str, **kwargs: Any
    ) -> Message: ...

    @property
    def parser(self) -> EventParser: ...


class MessageService:
    """All Discord message-resource endpoints, decoupled from Bot."""

    __slots__ = ("_host",)

    def __init__(self, host: MessageHost) -> None:
        self._host = host

    # ------------------------------------------------------------------ #
    # Send / reply / DM                                                  #
    # ------------------------------------------------------------------ #

    async def send_message(
        self,
        channel_id: int,
        content: str | None = None,
        *,
        tts: bool = False,
        embeds: list[dict[str, Any]] | None = None,
        allowed_mentions: dict[str, Any] | None = None,
        components: list[dict[str, Any]] | None = None,
        sticker_ids: list[int] | None = None,
        message_reference: dict[str, Any] | None = None,
        flags: int | None = None,
        poll: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"tts": tts}
        if content is not None:
            payload["content"] = content
        if embeds:
            payload["embeds"] = embeds
        if allowed_mentions is not None:
            payload["allowed_mentions"] = allowed_mentions
        if components:
            payload["components"] = components
        if sticker_ids:
            payload["sticker_ids"] = sticker_ids
        if message_reference is not None:
            payload["message_reference"] = message_reference
        if flags is not None:
            payload["flags"] = flags
        if poll is not None:
            payload["poll"] = poll
        has_sendable_content = any(
            payload.get(field)
            for field in ("content", "embeds", "components", "sticker_ids", "poll")
        ) or message_reference is not None
        if not has_sendable_content:
            raise ValueError(
                "send_message requires at least one of content/embeds/components/"
                "sticker_ids/message_reference"
            )
        return await self._host.request(
            "POST", f"/channels/{channel_id}/messages", json=payload
        )

    async def reply(
        self,
        channel_id: int,
        message_id: int,
        content: str,
        *,
        tts: bool = False,
        allowed_mentions: dict[str, Any] | None = None,
        mention_author: bool = True,
    ) -> dict[str, Any]:
        message_reference = {"message_id": str(message_id)}
        if not mention_author:
            allowed_mentions = {**(allowed_mentions or {}), "replied_user": False}
        return await self.send_message(
            channel_id=channel_id,
            content=content,
            tts=tts,
            allowed_mentions=allowed_mentions,
            message_reference=message_reference,
        )

    async def send_components_v2(
        self,
        channel_id: int,
        components: list[dict[str, Any]],
        *,
        allowed_mentions: dict[str, Any] | None = None,
        flags: int = 0,
    ) -> dict[str, Any]:
        return await self.send_message(
            channel_id=channel_id,
            components=components,
            allowed_mentions=allowed_mentions,
            flags=flags | IS_COMPONENTS_V2,
        )

    async def send_dm(self, user_id: int, content: str, **kwargs: Any) -> Message:
        host = self._host
        try:
            dm_channel = await host.request(
                "POST",
                "/users/@me/channels",
                json={"recipient_id": str(user_id)},
            )
        except DiscordAPIError as exc:
            if exc.status == 429:
                raise RateLimitError(
                    "Rate limited while opening DM channel",
                    retry_after=0.0,
                    global_limit=False,
                    raw_data=exc.raw_data,
                ) from exc
            if exc.status == 403:
                raise ForbiddenError(
                    "Cannot open DM channel. User may have DMs disabled or no shared server/permissions.",
                    raw_data=exc.raw_data,
                ) from exc
            raise

        channel_id = int(dm_channel["id"])
        try:
            # Route back through the host so that subclasses / tests that
            # override Bot.send_message see the call. send_dm has long been
            # treated as a thin convenience wrapper around send_message.
            message_data = await host.send_message(
                channel_id=channel_id,
                content=content,
                **kwargs,
            )
        except DiscordAPIError as exc:
            if exc.status == 429:
                raise RateLimitError(
                    "Rate limited while sending DM message",
                    retry_after=0.0,
                    global_limit=False,
                    raw_data=exc.raw_data,
                ) from exc
            if exc.status == 403:
                raise ForbiddenError(
                    "Cannot send DM. User may have DMs disabled or no shared server/permissions.",
                    raw_data=exc.raw_data,
                ) from exc
            raise

        message = host.parser.parse_message(message_data)
        host._channels[message.channel.id] = message.channel
        host._users[message.author.id] = message.author
        return message

    async def send_message_to_user(self, user_id: int, content: str, **kwargs: Any) -> Message:
        # Route back through the host so subclass / test overrides of
        # Bot.send_dm still take effect.
        return await self._host.send_dm(user_id=user_id, content=content, **kwargs)

    # ------------------------------------------------------------------ #
    # Polls                                                              #
    # ------------------------------------------------------------------ #

    async def send_poll(
        self,
        channel_id: int,
        question: str,
        answers: list[str],
        *,
        duration_hours: int = 24,
        allow_multiselect: bool = False,
        content: str | None = None,
    ) -> dict[str, Any]:
        if not question.strip():
            raise ValueError("Poll question cannot be empty")
        if len(answers) < 2:
            raise ValueError("Poll requires at least 2 answers")
        if len(answers) > 10:
            raise ValueError("Poll supports at most 10 answers")
        if duration_hours < 1 or duration_hours > 768:
            raise ValueError("Poll duration must be between 1 and 768 hours")
        normalized_answers = []
        for answer in answers:
            value = answer.strip()
            if not value:
                raise ValueError("Poll answers cannot be empty")
            normalized_answers.append({"poll_media": {"text": value}})
        poll_payload: dict[str, Any] = {
            "question": {"text": question.strip()},
            "answers": normalized_answers,
            "duration": duration_hours,
            "allow_multiselect": allow_multiselect,
        }
        return await self.send_message(
            channel_id=channel_id,
            content=content,
            poll=poll_payload,
        )

    async def get_poll_answer_voters(
        self,
        channel_id: int,
        message_id: int,
        answer_id: int,
        **params: Any,
    ) -> list[User]:
        data = await self._host.api_client.get_poll_answer_voters(
            channel_id,
            message_id,
            answer_id,
            **params,
        )
        parser = self._host.parser
        return [parser.parse_user(item) for item in data.get("users", [])]

    async def end_poll(self, channel_id: int, message_id: int) -> Message:
        data = await self._host.api_client.end_poll(channel_id, message_id)
        return self._host.parser.parse_message(data)

    # ------------------------------------------------------------------ #
    # Read / edit / delete                                               #
    # ------------------------------------------------------------------ #

    async def trigger_typing(self, channel_id: int) -> None:
        await self._host.api_client.trigger_typing(channel_id)

    async def list_messages(
        self,
        channel_id: int,
        *,
        limit: int = 50,
        before: int | None = None,
        after: int | None = None,
        around: int | None = None,
    ) -> list[Message]:
        items = await self._host.api_client.list_messages(
            channel_id,
            limit=limit,
            before=before,
            after=after,
            around=around,
        )
        parser = self._host.parser
        return [parser.parse_message(item) for item in items]

    async def fetch_message(self, channel_id: int, message_id: int) -> Message:
        data = await self._host.api_client.fetch_message(channel_id, message_id)
        return self._host.parser.parse_message(data)

    async def edit_message(self, channel_id: int, message_id: int, **payload: Any) -> Message:
        data = await self._host.api_client.edit_message(channel_id, message_id, payload)
        return self._host.parser.parse_message(data)

    async def delete_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self._host.api_client.delete_message(channel_id, message_id)

    async def crosspost_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self._host.api_client.crosspost_message(channel_id, message_id)

    async def bulk_delete_messages(self, channel_id: int, message_ids: list[int]) -> dict[str, Any]:
        return await self._host.api_client.bulk_delete_messages(channel_id, message_ids)

    # ------------------------------------------------------------------ #
    # Reactions                                                          #
    # ------------------------------------------------------------------ #

    async def add_reaction(self, channel_id: int, message_id: int, emoji: str) -> dict[str, Any]:
        return await self._host.api_client.add_reaction(channel_id, message_id, emoji)

    async def delete_own_reaction(self, channel_id: int, message_id: int, emoji: str) -> dict[str, Any]:
        return await self._host.api_client.delete_own_reaction(channel_id, message_id, emoji)

    async def delete_user_reaction(
        self,
        channel_id: int,
        message_id: int,
        emoji: str,
        user_id: int,
    ) -> dict[str, Any]:
        return await self._host.api_client.delete_user_reaction(
            channel_id, message_id, emoji, user_id,
        )

    async def list_reactions(
        self, channel_id: int, message_id: int, emoji: str, **params: Any,
    ) -> list[User]:
        items = await self._host.api_client.list_reactions(
            channel_id, message_id, emoji, **params,
        )
        parser = self._host.parser
        return [parser.parse_user(item) for item in items]

    async def clear_reactions(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self._host.api_client.clear_reactions(channel_id, message_id)

    async def clear_reaction(self, channel_id: int, message_id: int, emoji: str) -> dict[str, Any]:
        return await self._host.api_client.clear_reaction(channel_id, message_id, emoji)

    # ------------------------------------------------------------------ #
    # Pins                                                               #
    # ------------------------------------------------------------------ #

    async def list_pins(self, channel_id: int) -> list[Message]:
        items = await self._host.api_client.list_pins(channel_id)
        parser = self._host.parser
        return [parser.parse_message(item) for item in items]

    async def get_channel_pins(
        self,
        channel_id: int,
        *,
        before: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        data = await self._host.api_client.get_channel_pins(
            channel_id,
            before=before,
            limit=limit,
        )
        items = data.get("items", [])
        parser = self._host.parser
        return {
            **data,
            "items": [parser.parse_message_pin(item) for item in items],
        }

    async def pin_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self._host.api_client.pin_message(channel_id, message_id)

    async def unpin_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self._host.api_client.unpin_message(channel_id, message_id)

    async def pin_channel_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self._host.api_client.pin_channel_message(channel_id, message_id)

    async def unpin_channel_message(self, channel_id: int, message_id: int) -> dict[str, Any]:
        return await self._host.api_client.unpin_channel_message(channel_id, message_id)


__all__ = ["MessageService", "MessageHost"]
