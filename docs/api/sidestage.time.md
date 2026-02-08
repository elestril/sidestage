# `sidestage.time`

## Classes

### `Gametime(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `seconds` | `int` | 0 |

#### `add_seconds(seconds: int) -> Gametime`

#### `from_seconds(seconds: int) -> Gametime`

#### `from_string(time_str: str) -> Gametime`

Parses a string in format 'Day D, HH:MM:SS'

#### `to_string() -> str`

Converts to 'Day D, HH:MM:SS'
