import logging
import logging.config
from pathlib import Path
from pydantic import BaseModel, Field, BeforeValidator, PlainSerializer
from typing import Annotated
from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme
from sidestage.request_context import get_request_context


# ---------------------------------------------------------------------------
# Rich console — importable for use anywhere: from sidestage.logging import console
# ---------------------------------------------------------------------------

SIDESTAGE_THEME = Theme({
    "info": "green",
    "warning": "yellow",
    "error": "red",
    "critical": "bold red",
    "debug": "cyan",
    "entity": "bold magenta",
    "scene": "bold blue",
    "system": "dim white",
})

console = Console(theme=SIDESTAGE_THEME)

# ---------------------------------------------------------------------------
# Format strings (private)
# ---------------------------------------------------------------------------

_SERVER_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_REQUEST_FORMAT = "%(asctime)s [%(request_id)s] %(user)s - %(message)s"
_CAMPAIGN_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
_CHAT_FORMAT = "%(asctime)s %(actor)s - %(message)s"
_RICH_FORMAT = "%(name)s - %(message)s"


# ---------------------------------------------------------------------------
# Request context filter
# ---------------------------------------------------------------------------

class RequestContextFilter(logging.Filter):
    """Injects request_id, user, and origin into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = get_request_context()
        record.request_id = ctx.request_id if ctx else "-"  # type: ignore[attr-defined]
        record.user = ctx.user if ctx else "-"  # type: ignore[attr-defined]
        record.origin = ctx.origin if ctx else "-"  # type: ignore[attr-defined]
        return True


# ---------------------------------------------------------------------------
# LogLevel type + LogConfig model
# ---------------------------------------------------------------------------

def _parse_log_level(v: str | int) -> int:
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        return getattr(logging, v.upper())


def _serialize_log_level(v: int) -> str:
    return logging.getLevelName(v)


LogLevel = Annotated[int, BeforeValidator(_parse_log_level), PlainSerializer(_serialize_log_level)]


class LogConfig(BaseModel):
    level: LogLevel = Field(
        default=logging.INFO,
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")


# ---------------------------------------------------------------------------
# Global init — server.log, request.log, console
# ---------------------------------------------------------------------------

def _make_rich_handler(level: int = logging.INFO) -> RichHandler:
    handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        rich_tracebacks=True,
        markup=True,
    )
    handler.setFormatter(logging.Formatter(fmt=_RICH_FORMAT))
    handler.setLevel(level)
    return handler


def initLogging(sidestage_dir: Path, config: LogConfig) -> None:
    """Configure all logging via dictConfig.

    Sets up:
      - root logger        → server.log + Rich console
      - uvicorn            → stderr console, propagates to root (server.log)
      - uvicorn.access     → request.log (no propagation)
    """
    level_name = logging.getLevelName(config.level)

    dict_config: dict = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_context": {
                "()": "sidestage.logging.RequestContextFilter",
            },
        },
        "formatters": {
            "server": {"format": _SERVER_FORMAT},
            "request": {"format": _REQUEST_FORMAT},
            "uvicorn_default": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": "%(levelprefix)s %(message)s",
                "use_colors": True,
            },
        },
        "handlers": {
            "server_file": {
                "class": "logging.FileHandler",
                "filename": str(sidestage_dir / "server.log"),
                "formatter": "server",
            },
            "request_file": {
                "class": "logging.FileHandler",
                "filename": str(sidestage_dir / "request.log"),
                "formatter": "request",
                "filters": ["request_context"],
            },
            "uvicorn_console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
                "formatter": "uvicorn_default",
            },
        },
        "loggers": {
            "uvicorn": {
                "handlers": ["uvicorn_console"],
                "level": level_name,
                "propagate": True,
            },
            "uvicorn.error": {
                "level": level_name,
            },
            "uvicorn.access": {
                "handlers": ["request_file"],
                "level": level_name,
                "propagate": False,
            },
        },
        "root": {
            "level": level_name,
            "handlers": ["server_file"],
        },
    }

    logging.config.dictConfig(dict_config)

    # Add RichHandler to root manually (needs our themed Console instance)
    logging.getLogger().addHandler(_make_rich_handler(logging.INFO))


# ---------------------------------------------------------------------------
# Per-campaign init — campaign.log, chat.log
# ---------------------------------------------------------------------------

def initCampaignLogging(
    campaign_name: str,
    campaign_dir: Path,
    level: int | None = None,
) -> tuple[logging.Logger, logging.Logger]:
    """Set up campaign-scoped loggers.

    Returns (campaign_logger, chat_logger).

    Creates:
      sidestage.campaign.<name> → campaign.log + Rich console
      sidestage.chat.<name>     → chat.log (file only, debug trace)

    Both have propagate=False to avoid duplicating into server.log.
    """
    if level is None:
        from sidestage import config as _cfg
        level = _cfg.get_config().logging.level

    # --- Campaign logger ---
    campaign_logger = logging.getLogger(f"sidestage.campaign.{campaign_name}")
    campaign_logger.setLevel(level)
    campaign_logger.propagate = False
    campaign_logger.handlers.clear()

    campaign_fh = logging.FileHandler(campaign_dir / "campaign.log")
    campaign_fh.setFormatter(logging.Formatter(_CAMPAIGN_FORMAT))
    campaign_logger.addHandler(campaign_fh)
    campaign_logger.addHandler(_make_rich_handler(logging.INFO))

    # --- Chat logger ---
    chat_logger = logging.getLogger(f"sidestage.chat.{campaign_name}")
    chat_logger.setLevel(logging.DEBUG)
    chat_logger.propagate = False
    chat_logger.handlers.clear()

    chat_fh = logging.FileHandler(campaign_dir / "chat.log")
    chat_fh.setFormatter(logging.Formatter(_CHAT_FORMAT))
    chat_logger.addHandler(chat_fh)

    return campaign_logger, chat_logger
