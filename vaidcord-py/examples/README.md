# Examples

This directory collects small, focused examples instead of one large kitchen-sink sample.

## What to read first

- [hello_echo_bot.py](hello_echo_bot.py) - the smallest runnable bot.
- [advanced_router_di.py](advanced_router_di.py) - nested routers, DI, middleware, and command/class-filter shortcuts.
- [filters_showcase.py](filters_showcase.py) - class-based filters + advanced MagicFilter/MagicData/BotFilter usage.
- [fsm_conversation.py](fsm_conversation.py) - a multi-step profile flow using FSM state.
- [mock_testing.py](mock_testing.py) - deterministic testing with the mock layer.
- [oauth2_examples.py](oauth2_examples.py) - the minimal OAuth2 authorization URL helper.
- [oauth2_workflow.py](oauth2_workflow.py) - a richer OAuth2 install and token helper example.
- [send_dm_to_user.py](send_dm_to_user.py) - open a user DM channel and send a direct message by user ID.

## Run them

```bash
uv run python examples/hello_echo_bot.py
uv run python examples/advanced_router_di.py
uv run python examples/filters_showcase.py
uv run python examples/fsm_conversation.py
uv run python examples/mock_testing.py
uv run python examples/oauth2_examples.py
uv run python examples/oauth2_workflow.py
uv run python examples/send_dm_to_user.py 123456789012345678 "Hello from VaidCord"
```

The bot examples expect a `DISCORD_BOT_TOKEN` environment variable. The OAuth2 examples use placeholder values and are meant as templates.
