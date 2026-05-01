# Filters in VaidCord

VaidCord supports **class-based filters**, **magic filters** (`F`), and **composed expressions**.

## 1) Class-based filters

```python
from vaidcord.filters import CommandFilter, ChatTypeFilter
from vaidcord.types import ChannelType

@router.on_message(CommandFilter(("start",)))
async def start(event, bot):
    await bot.send_message(event.message.channel_id, "started")

@router.on_message(ChatTypeFilter([ChannelType.DM, "group_dm"]))
async def private_only(event, bot):
    await bot.send_message(event.message.channel_id, "DM only")
```

## 2) Magic filters (`F`)

```python
from vaidcord.filters import F

@router.on_message(F.message.content.startswith("/echo"))
async def echo(event, bot):
    ...
```

### Useful magic capabilities

- Attribute paths: `F.message.content`, `F.user.id`, `F.bot.id`
- Comparisons: `== != > >= < <=`
- Inclusion: `in_`, `not_in`
- Presence: `exists()`
- Transform: `lower()`, `upper()`, `len()`, `cast(...)`, `map(...)`
- Pattern: `regex(...)`
- Injection: `as_("name")`
- List selectors:
  - `F.items[...]` => **any** item must match
  - `F.items[:]` => **all** items must match

## 3) MagicData for middleware/dispatcher context

`MagicData` evaluates expressions against `event.data + event.context`.

```python
from vaidcord.filters import MagicData, F

router.add_filter(MagicData(F.maintenance_mode.is_(True)))
```

## 4) Multi-bot routing

Use `BotFilter` or magic bot checks:

```python
from vaidcord.filters import BotFilter, F

@router.on_message(BotFilter(bot_ids={111, 222}))
async def for_selected_bots(event, bot):
    ...

@router.on_message(F.bot.bot_id_in({111, 222}))
async def for_selected_bots_magic(event, bot):
    ...
```

## 5) Composition semantics

- Filter can return `bool` or `dict`
- `dict` means **pass + inject data**
- `A & B`: both pass; dict payloads are merged
- `A | B`: first passing branch wins
