"""Logging helpers for VaidCord."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Literal, TextIO

SUCCESS_LEVEL = 25
_DEFAULT_BOT_ID: str | None = None


def register_success_level() -> None:
    """Register SUCCESS log level and helper method."""
    if logging.getLevelName(SUCCESS_LEVEL) != "SUCCESS":
        logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")

        def success(
            self: logging.Logger,
            msg: object,
            *args: object,
            **kwargs: Any,
        ) -> None:
            if self.isEnabledFor(SUCCESS_LEVEL):
                self._log(SUCCESS_LEVEL, msg, args, **kwargs)

        logging.Logger.success = success  # type: ignore[attr-defined]


@dataclass
class LogFileConfig:
    directory: str = "logs"
    filename: str = "vaidcord.log"
    mode: Literal["single", "time", "bot_time"] = "single"
    rotate_minutes: int = 5
    backup_count: int = 0
    utc: bool = False


@dataclass
class LogConfig:
    level: str | int = "INFO"
    color: bool = True
    prefix: str = "VAIDCORD"
    stream: TextIO = sys.stdout
    file: LogFileConfig | None = None


class VaidcordContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - name is required by logging
        if not hasattr(record, "category"):
            record.category = _derive_category(record.name)
        if not hasattr(record, "bot_id"):
            record.bot_id = _derive_bot_id(record)
        if not hasattr(record, "event_id"):
            record.event_id = _derive_event_id(record)
        if not hasattr(record, "request_id"):
            record.request_id = _derive_request_id(record)
        return True


def set_default_bot_id(bot_id: str | int | None) -> None:
    """Remember a process-wide bot id for logs that cannot carry bot context."""
    global _DEFAULT_BOT_ID
    _DEFAULT_BOT_ID = None if bot_id is None else str(bot_id)


def get_default_bot_id() -> str | None:
    """Return the current process-wide bot id, if known."""
    return _DEFAULT_BOT_ID


class VaidcordFormatter(logging.Formatter):
    def __init__(self, *, use_color: bool, prefix: str) -> None:
        super().__init__()
        self._use_color = use_color
        self._prefix = prefix

    def format(self, record: logging.LogRecord) -> str:
        level = record.levelname
        category = getattr(record, "category", "GENERAL")
        bot_id = getattr(record, "bot_id", "-")
        event_id = getattr(record, "event_id", "-")
        request_id = getattr(record, "request_id", "-")
        message = _format_log_message(record)

        if self._use_color:
            level = _badge(level, _background_for_level(record.levelname))
            category = _badge(str(category), _BG_CONTEXT)
            bot_id = _paint(str(bot_id), _FG_BOT)
            event_id = _paint(str(event_id), _FG_EVENT)
            request_id = _paint(str(request_id), _FG_REQUEST)

        return (
            f"{self._prefix} | [{level}] | [{category}] | "
            f"Bot id=\"{bot_id}\" | Event id=\"{event_id}\" | "
            f"Request id=\"{request_id}\" | {message}"
        )


class BotTimedRotatingFileHandler(logging.Handler):
    """Timed rotating file handler that splits files by bot id."""

    def __init__(
        self,
        base_path: Path,
        *,
        interval_minutes: int,
        backup_count: int,
        utc: bool,
    ) -> None:
        super().__init__()
        self._base_path = base_path
        self._interval = interval_minutes
        self._backup_count = backup_count
        self._utc = utc
        self._handlers: dict[str, TimedRotatingFileHandler] = {}

    def setFormatter(self, fmt: logging.Formatter | None) -> None:  # noqa: N802 - logging API
        super().setFormatter(fmt)
        for handler in self._handlers.values():
            handler.setFormatter(fmt)

    def addFilter(  # noqa: N802 - logging API
        self,
        filt: Any,
    ) -> None:
        super().addFilter(filt)
        for handler in self._handlers.values():
            handler.addFilter(filt)

    def emit(self, record: logging.LogRecord) -> None:
        bot_id = str(getattr(record, "bot_id", "unknown"))
        handler = self._handlers.get(bot_id)
        if handler is None:
            filename = _bot_filename(self._base_path, bot_id)
            handler = TimedRotatingFileHandler(
                filename,
                when="M",
                interval=self._interval,
                backupCount=self._backup_count,
                utc=self._utc,
                encoding="utf-8",
            )
            if self.formatter:
                handler.setFormatter(self.formatter)
            for filt in self.filters:
                handler.addFilter(filt)
            self._handlers[bot_id] = handler
        handler.emit(record)

    def close(self) -> None:
        for handler in self._handlers.values():
            handler.close()
        self._handlers.clear()
        super().close()


def configure_logging(config: LogConfig | None = None) -> None:
    """Configure VaidCord logging handlers and formatters."""
    register_success_level()
    config = config or LogConfig()

    logger = logging.getLogger("vaidcord")
    logger.handlers.clear()
    logger.setLevel(config.level)
    logger.propagate = False

    use_color = bool(config.color and getattr(config.stream, "isatty", lambda: False)())
    formatter = VaidcordFormatter(use_color=use_color, prefix=config.prefix)
    context_filter = VaidcordContextFilter()

    stream_handler = logging.StreamHandler(config.stream)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(context_filter)
    logger.addHandler(stream_handler)

    if config.file:
        file_handler = _build_file_handler(config.file, formatter, context_filter)
        logger.addHandler(file_handler)


def get_logger(
    name: str,
    *,
    category: str | None = None,
    bot_id: str | int | None = None,
) -> logging.LoggerAdapter[logging.Logger]:
    """Return a logger adapter with optional category/bot id fields."""
    extra: dict[str, str] = {}
    if category is not None:
        extra["category"] = category
    if bot_id is not None:
        extra["bot_id"] = str(bot_id)
    return logging.LoggerAdapter(logging.getLogger(name), extra)


def _build_file_handler(
    config: LogFileConfig,
    formatter: logging.Formatter,
    context_filter: logging.Filter,
) -> logging.Handler:
    directory = Path(config.directory)
    directory.mkdir(parents=True, exist_ok=True)
    base_path = directory / config.filename

    if config.mode == "single":
        handler: logging.Handler = logging.FileHandler(base_path, encoding="utf-8")
    elif config.mode == "time":
        handler = TimedRotatingFileHandler(
            base_path,
            when="M",
            interval=config.rotate_minutes,
            backupCount=config.backup_count,
            utc=config.utc,
            encoding="utf-8",
        )
    elif config.mode == "bot_time":
        handler = BotTimedRotatingFileHandler(
            base_path,
            interval_minutes=config.rotate_minutes,
            backup_count=config.backup_count,
            utc=config.utc,
        )
    else:
        raise ValueError(f"Unsupported log file mode: {config.mode}")

    handler.setFormatter(formatter)
    handler.addFilter(context_filter)
    return handler


def _derive_category(logger_name: str) -> str:
    name = logger_name.lower()
    if "router" in name:
        return "ROUTING"
    if "fsm" in name:
        return "FSM"
    if "filter" in name:
        return "FILTERS"
    if "middleware" in name:
        return "MIDDLEWARES"
    if "gateway" in name:
        return "GATEWAY"
    if "http" in name or "api_client" in name or "oauth" in name:
        return "API"
    if "mock" in name:
        return "MOCK"
    if "bot" in name:
        return "BOT"
    return "GENERAL"


def _derive_bot_id(record: logging.LogRecord) -> str:
    payload = _record_mapping(record)
    if payload is not None and payload.get("bot_id") is not None:
        return str(payload["bot_id"])
    event = getattr(record, "event", None)
    if event is not None:
        bot = getattr(event, "bot", None)
        if bot is not None:
            user = getattr(bot, "user", None)
            if user is not None and getattr(user, "id", None) is not None:
                return str(user.id)
            if getattr(bot, "id", None) is not None:
                return str(bot.id)
    if _DEFAULT_BOT_ID is not None:
        return _DEFAULT_BOT_ID
    return "-"


def _derive_event_id(record: logging.LogRecord) -> str:
    payload = _record_mapping(record)
    if payload is not None:
        for key in ("event_id", "message_id"):
            if payload.get(key) is not None:
                return str(payload[key])
    event = getattr(record, "event", None)
    if event is not None:
        event_id = getattr(event, "event_id", None)
        if event_id is not None:
            return str(event_id)
        message = getattr(event, "message", None)
        if message is not None and getattr(message, "id", None) is not None:
            return str(message.id)
        event_type = getattr(event, "type", None)
        if event_type is not None:
            return str(getattr(event_type, "value", event_type))
    return "-"


def _derive_request_id(record: logging.LogRecord) -> str:
    payload = _record_mapping(record)
    if payload is not None and payload.get("request_id") is not None:
        return str(payload["request_id"])
    return "-"


def _record_mapping(record: logging.LogRecord) -> dict[str, Any] | None:
    if isinstance(record.msg, dict):
        return record.msg
    return None


def _format_log_message(record: logging.LogRecord) -> str:
    payload = _record_mapping(record)
    if payload is None:
        return record.getMessage()
    event = payload.get("event", "event")
    fields = [
        f"{key}={value!r}"
        for key, value in payload.items()
        if key not in {"event", "bot_id", "event_id", "message_id", "request_id"}
    ]
    if not fields:
        return str(event)
    return f"{event} " + " ".join(fields)


def _bot_filename(base_path: Path, bot_id: str) -> Path:
    stem = base_path.stem
    suffix = "".join(base_path.suffixes) or ".log"
    return base_path.with_name(f"{stem}.bot-{bot_id}{suffix}")


_BG_BY_LEVEL = {
    "DEBUG": "\x1b[48;5;238m\x1b[38;5;250m",
    "INFO": "\x1b[48;5;24m\x1b[38;5;195m",
    "SUCCESS": "\x1b[48;5;22m\x1b[38;5;194m",
    "WARNING": "\x1b[48;5;94m\x1b[38;5;230m",
    "ERROR": "\x1b[48;5;88m\x1b[38;5;224m",
    "CRITICAL": "\x1b[48;5;52m\x1b[38;5;225m",
}
_BG_CONTEXT = "\x1b[48;5;236m\x1b[38;5;159m"
_FG_BOT = "\x1b[38;5;120m"
_FG_EVENT = "\x1b[38;5;213m"
_FG_REQUEST = "\x1b[38;5;111m"
_BOLD = "\x1b[1m"
_RESET = "\x1b[0m"


def _background_for_level(level: str) -> str:
    return _BG_BY_LEVEL.get(level, "\x1b[48;5;238m\x1b[38;5;250m")


def _badge(value: str, style: str) -> str:
    return f"{style}{_BOLD} {value} {_RESET}"


def _paint(value: str, color: str) -> str:
    return f"{color}{value}{_RESET}"


register_success_level()
