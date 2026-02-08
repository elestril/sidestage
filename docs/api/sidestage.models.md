# `sidestage.models`

Domain model classes for Sidestage campaign entities.

All persistent domain objects (entities, events, scenes) are defined here.
API request/response schemas live in schemas.py.

## Classes

### `CharacterModel(EntityModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | — |
| `id` | `str` | — |
| `unseen` | `bool` | False |
| `location_id` | `str | None` | — |
| `inventory` | `list[str]` | *factory* |

### `ChatMessageModel(EventModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | — |
| `id` | `str` | — |
| `scene_id` | `str` | — |
| `gametime` | `int` | — |
| `walltime` | `str` | — |
| `character_id` | `str` | — |
| `actor_id` | `str | None` | — |
| `message` | `str` | — |
| `widget` | `dict[str, Any] | None` | — |

#### `backfill_legacy_fields(data: Any) -> Any`

### `EntityModel(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | — |
| `id` | `str` | — |

### `EventModel(EntityModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | — |
| `id` | `str` | — |
| `scene_id` | `str` | — |
| `gametime` | `int` | — |
| `walltime` | `str` | — |

### `FastForwardEventModel(EventModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | — |
| `id` | `str` | — |
| `scene_id` | `str` | — |
| `gametime` | `int` | — |
| `walltime` | `str` | — |
| `duration_str` | `str` | — |

### `ItemModel(EntityModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | — |
| `id` | `str` | — |

### `JoinEventModel(EventModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | — |
| `id` | `str` | — |
| `scene_id` | `str` | — |
| `gametime` | `int` | — |
| `walltime` | `str` | — |
| `actor_id` | `str` | — |

### `LeaveEventModel(EventModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | — |
| `id` | `str` | — |
| `scene_id` | `str` | — |
| `gametime` | `int` | — |
| `walltime` | `str` | — |
| `actor_id` | `str` | — |

### `LocationModel(EntityModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | — |
| `id` | `str` | — |
| `connected_locations` | `list[str]` | *factory* |

### `SceneModel(EntityModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | — |
| `id` | `str` | — |
| `current_gametime` | `int | None` | — |
| `location_id` | `str | None` | — |
| `events` | `list[str]` | *factory* |
| `messages` | `list[ChatMessageModel]` | *factory* |
