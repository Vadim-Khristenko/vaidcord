# Examples

This directory collects small, focused examples instead of one large kitchen-sink sample.

The bot examples define routers at module level and let `build_dispatcher()` only assemble already registered routers. In a larger project, those routers can live in separate feature files and be imported by the main entrypoint.

## What to read first

- [hello_echo_bot.py](hello_echo_bot.py) - the smallest runnable `Dispatcher` + `Router` bot.
- [intents_permissions_bot.py](intents_permissions_bot.py) - explicit Gateway intents, privileged-intent opt-in, and a channel permission checklist.
- [advanced_router_di.py](advanced_router_di.py) - nested routers, DI, middleware, poll helpers, and gateway-event shortcuts.
- [polls_bot.py](polls_bot.py) - create polls, inspect answer voters, and handle `PollVote` gateway events.
- [filters_showcase.py](filters_showcase.py) - class-based filters + MagicFilter/MagicData/BotFilter usage with shortcut decorators.
- [fsm_conversation.py](fsm_conversation.py) - a multi-step profile flow using `StatesGroup`, `State`, and injected `FSMContext`.
- [mock_testing.py](mock_testing.py) - deterministic testing with the mock layer.
- [mock_server_ui.py](mock_server_ui.py) - run the local mock Discord server with the AMOLED browser UI.
- [oauth2_examples.py](oauth2_examples.py) - the minimal OAuth2 authorization URL helper.
- [oauth2_workflow.py](oauth2_workflow.py) - a richer OAuth2 install and token helper example.
- [send_dm_to_user.py](send_dm_to_user.py) - open a user DM channel and send a direct message by user ID.

## Run them

```bash
uv run python examples/hello_echo_bot.py
uv run python examples/intents_permissions_bot.py
uv run python examples/advanced_router_di.py
uv run python examples/polls_bot.py
uv run python examples/filters_showcase.py
uv run python examples/fsm_conversation.py
uv run python examples/mock_testing.py
uv run python examples/mock_server_ui.py
uv run python examples/oauth2_examples.py
uv run python examples/oauth2_workflow.py
uv run python examples/send_dm_to_user.py 123456789012345678 "Hello from VaidCord"
```

The bot examples expect a `DISCORD_BOT_TOKEN` environment variable.

## Intents and permissions

Discord has two separate gates:

- Gateway intents decide which events and fields Discord sends to the bot.
- Server/channel permissions decide what the bot can do after it receives an event.

Examples use typed handler injection where possible:

```python
@router.on_message_create()
async def echo(message: Message) -> None:
    await message.answer(f"echo: {message.content}")

@router.on_message_poll_vote_add()
async def vote(vote: PollVote) -> None:
    print(vote.message_id, vote.answer_id)
```

Examples that read guild message text need `MESSAGE_CONTENT` enabled in the Developer Portal and passed in `Bot(intents=...)`. If the intent is missing, guild messages may arrive with empty `content`, so an echo handler will answer with only its prefix.

Privileged intents such as `MESSAGE_CONTENT`, `GUILD_MEMBERS`, and `GUILD_PRESENCES` must be enabled for the application before they are sent in `IDENTIFY`. If Discord closes the Gateway with `4014`, remove that intent or enable/approve it in the Developer Portal.

Handlers for member events need `GUILD_MEMBERS`. In examples this is opt-in with:

```bash
VAIDCORD_ENABLE_GUILD_MEMBERS_INTENT=1 uv run python examples/intents_permissions_bot.py
```

For text-channel examples, invite the bot with at least `View Channel`, `Send Messages`, and `Read Message History`. Examples that send embeds, polls, manage messages, or work in threads need their matching Discord permissions as well. Poll vote handlers also need `GUILD_MESSAGE_POLLS` and/or `DIRECT_MESSAGE_POLLS` intents depending on where polls are used.

Logging is enabled in every runnable bot example through `configure_logging()`. Once Discord sends `READY` or `get_current_user()` returns, VaidCord remembers the bot id and adds it to later bot/API log records.
