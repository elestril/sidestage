import logging
import sys
from pathlib import Path
from pydantic import BaseModel, Field, BeforeValidator, PlainSerializer
from typing import Annotated, Optional, TYPE_CHECKING
from sidestage.request_context import get_request_context

_sidestage_loggers: dict[str, logging.Logger] = {}


class RequestContextFilter(logging.Filter):
    """Logging filter that injects request context fields into every log record.

    Adds ``request_id``, ``user``, and ``origin`` attributes so they can be
    referenced in format strings (e.g. ``%(request_id)s``).  When no request
    context is active the fields default to ``"-"``.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = get_request_context()
        record.request_id = ctx.request_id if ctx else "-"  # type: ignore[attr-defined]
        record.user = ctx.user if ctx else "-"  # type: ignore[attr-defined]
        record.origin = ctx.origin if ctx else "-"  # type: ignore[attr-defined]
        return True

def _parse_log_level(v: str | int) -> int:
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        # Convert string level to int using logging module
        return getattr(logging, v.upper())


def _serialize_log_level(v: int) -> str:
    # Convert int level to string representation
    return logging.getLevelName(v)

LogLevel = Annotated[int, BeforeValidator(_parse_log_level), PlainSerializer(_serialize_log_level)]

class LogConfig(BaseModel):
    level: LogLevel = Field(
        default=logging.INFO, 
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")

def initLogging(sidestage_dir: Path, config: LogConfig) -> None:
  logging.basicConfig(
    level=config.level,
    filename=sidestage_dir / "server.log",
    format="%(asctime)s [%(request_id)s] %(user)s - %(name)s - %(levelname)s - %(message)s",
  )
  ctx_filter = RequestContextFilter()
  for handler in logging.getLogger().handlers:
    handler.addFilter(ctx_filter)

def getSidestageLogger(
    name: str, 
    logfile: Optional[Path] = None) -> logging.Logger:
    
  global _sidestage_loggers
  if name in _sidestage_loggers:
    return _sidestage_loggers[name]

  from sidestage import config
  # We need to access config carefully to avoid circular import issues if possible.
  # config.get_config() is safe if called at runtime.
  level = config.get_config().logging.level

  logger = logging.getLogger(name)
  logger.setLevel(level)
  logger.propagate = False

  logger.handlers.clear()

  # stderr, only for critical errors
  stderr_handler = logging.StreamHandler(sys.stderr)
  stderr_handler.setLevel(level=logging.CRITICAL)
  logger.addHandler(stderr_handler)

  # stdout, if this is an info logger
  if level <= logging.INFO:
    stdout_handler = logging.StreamHandler()
    logger.addHandler(stdout_handler)
  
  # log to file, if configured
  if logfile:
    logger.addHandler(logging.FileHandler(logfile))

  _sidestage_loggers[name] = logger
  return logger
