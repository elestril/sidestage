# `sidestage.logging`

## Constants

### `SIDESTAGE_THEME`
Rich `Theme` with semantic styles: `info`, `warning`, `error`, `critical`, `debug`, `entity`, `scene`, `system`.

### `console`
`rich.console.Console` instance with `SIDESTAGE_THEME` applied. Import for colored terminal output anywhere:
```python
from sidestage.logging import console
console.print("[entity]Gandalf[/entity] entered [scene]The Prancing Pony[/scene]")
```

## Classes

### `LogConfig(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `level` | `int` | 20 (`INFO`) |

### `RequestContextFilter(Filter)`

Logging filter that injects request context fields into every log record.

Adds `request_id`, `user`, and `origin` attributes so they can be
referenced in format strings (e.g. `%(request_id)s`). When no request
context is active the fields default to `"-"`.

#### `filter(record: LogRecord) -> bool`

## Functions

### `initLogging(sidestage_dir: Path, config: LogConfig) -> None`

Configure all logging via `logging.config.dictConfig`. Sets up:

- **Root logger** → `server.log` file handler + Rich console
- **`uvicorn`** → stderr console, propagates to root (`server.log`)
- **`uvicorn.access`** → `request.log` file handler (no propagation)

### `initCampaignLogging(campaign_name: str, campaign_dir: Path, level: int | None = None) -> tuple[Logger, Logger]`

Set up campaign-scoped loggers. Returns `(campaign_logger, chat_logger)`.

Creates:
- `sidestage.campaign.<name>` → `campaign.log` file handler + Rich console
- `sidestage.chat.<name>` → `chat.log` file handler only (debug trace)

Both have `propagate=False` to avoid duplicating into `server.log`.
