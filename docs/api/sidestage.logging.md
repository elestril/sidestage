# `sidestage.logging`

## Classes

### `LogConfig(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `level` | `int` | 20 |

### `RequestContextFilter(Filter)`

Logging filter that injects request context fields into every log record.

Adds ``request_id``, ``user``, and ``origin`` attributes so they can be
referenced in format strings (e.g. ``%(request_id)s``).  When no request
context is active the fields default to ``"-"``.

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

### `getSidestageLogger(name: str, logfile: Path | None = None) -> Logger`

### `initLogging(sidestage_dir: Path, config: LogConfig) -> None`
