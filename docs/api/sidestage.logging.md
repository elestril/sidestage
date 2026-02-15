# `sidestage.logging`

## Classes

### `LogConfig(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `level` | `int` | 20 |

### `RequestContextFilter(Filter)`

Injects request_id, user, and origin into every log record.

#### `__init__(name='')`

Initialize a filter.

Initialize with the name of the logger which, together with its
children, will have its events allowed through the filter. If no
name is specified, allow every event.

#### `filter(record: LogRecord) -> bool`

Determine if the specified record is to be logged.

Returns True if the record should be logged, or False otherwise.
If deemed appropriate, the record may be modified in-place.

## Functions

### `initCampaignLogging(campaign_name: str, campaign_dir: Path, level: int | None = None) -> tuple[Logger, Logger]`

Set up campaign-scoped loggers.

Returns (campaign_logger, chat_logger).

Creates:
  sidestage.campaign.<name> → campaign.log + Rich console
  sidestage.chat.<name>     → chat.log (file only, debug trace)

Both have propagate=False to avoid duplicating into server.log.

### `initLogging(sidestage_dir: Path, config: LogConfig) -> None`

Configure all logging via dictConfig.

Sets up:
  - root logger        → server.log + Rich console
  - uvicorn            → stderr console, propagates to root (server.log)
  - uvicorn.access     → request.log (no propagation)
