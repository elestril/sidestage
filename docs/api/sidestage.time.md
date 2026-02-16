# `sidestage.time`

## Classes

### `Gametime(datetime)`

Game-world timestamp stored as seconds since an arbitrary epoch.

Subclasses ``datetime`` so ``timedelta`` arithmetic works naturally.
Storage representation is always ``int`` (total seconds).
Display format is ``"Day D, HH:MM:SS"``.

#### `__init__(args, kwargs)`

#### `from_seconds(seconds: int) -> Gametime`

Create a Gametime from total seconds since the game epoch.

#### `from_string(time_str: str) -> Gametime`

Parse ``'Day D, HH:MM:SS'`` format.

#### `total_seconds() -> int`

Return total seconds since the game epoch (for storage).
