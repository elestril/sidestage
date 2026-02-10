# `sidestage.models`

Domain model classes for Sidestage campaign entities.

All persistent domain objects (entities, events, scenes) are defined here.
API request/response schemas live in schemas.py.

## Classes

### `CharacterModel(EntityModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | '' |
| `id` | `str` | — |
| `unseen` | `bool` | False |
| `location_id` | `str | None` | — |
| `inventory` | `list[str]` | *factory* |
| `owner` | `str` | 'npc' |
| `system_actor` | `bool` | False |

### `ChatMessageModel(EntityModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | '' |
| `id` | `str` | — |
| `event_type` | `EventType` | — |
| `scene_id` | `str` | — |
| `gametime` | `int` | — |
| `walltime` | `datetime` | — |
| `character_id` | `str | None` | — |
| `actor_id` | `str | None` | — |
| `metadata` | `dict[str, Any]` | *factory* |
| `visibility` | `Visibility` | <Visibility.PUBLIC: 'public'> |

### `EntityModel(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | '' |
| `id` | `str` | — |

### `EventModel(EntityModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | '' |
| `id` | `str` | — |
| `event_type` | `EventType` | — |
| `scene_id` | `str` | — |
| `gametime` | `int` | — |
| `walltime` | `datetime` | — |
| `character_id` | `str | None` | — |
| `actor_id` | `str | None` | — |
| `metadata` | `dict[str, Any]` | *factory* |
| `visibility` | `Visibility` | <Visibility.PUBLIC: 'public'> |

### `EventType(str, Enum)`

**Values:**

- `CHAT_MESSAGE` = `'ChatMessage'`
- `JOIN` = `'JoinEvent'`
- `LEAVE` = `'LeaveEvent'`
- `ADJUST_GAMETIME` = `'AdjustGametime'`
- `ERROR` = `'Error'`

### `FastForwardEventModel(EntityModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | '' |
| `id` | `str` | — |
| `event_type` | `EventType` | — |
| `scene_id` | `str` | — |
| `gametime` | `int` | — |
| `walltime` | `datetime` | — |
| `character_id` | `str | None` | — |
| `actor_id` | `str | None` | — |
| `metadata` | `dict[str, Any]` | *factory* |
| `visibility` | `Visibility` | <Visibility.PUBLIC: 'public'> |

### `ItemModel(EntityModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | '' |
| `id` | `str` | — |

### `JoinEventModel(EntityModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | '' |
| `id` | `str` | — |
| `event_type` | `EventType` | — |
| `scene_id` | `str` | — |
| `gametime` | `int` | — |
| `walltime` | `datetime` | — |
| `character_id` | `str | None` | — |
| `actor_id` | `str | None` | — |
| `metadata` | `dict[str, Any]` | *factory* |
| `visibility` | `Visibility` | <Visibility.PUBLIC: 'public'> |

### `LeaveEventModel(EntityModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | '' |
| `id` | `str` | — |
| `event_type` | `EventType` | — |
| `scene_id` | `str` | — |
| `gametime` | `int` | — |
| `walltime` | `datetime` | — |
| `character_id` | `str | None` | — |
| `actor_id` | `str | None` | — |
| `metadata` | `dict[str, Any]` | *factory* |
| `visibility` | `Visibility` | <Visibility.PUBLIC: 'public'> |

### `LocationModel(EntityModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | '' |
| `id` | `str` | — |
| `connected_locations` | `list[str]` | *factory* |

### `SceneModel(EntityModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | '' |
| `id` | `str` | — |
| `current_gametime` | `int | None` | — |
| `location_id` | `str | None` | — |
| `events` | `list[str]` | *factory* |

### `Visibility(str, Enum)`

**Values:**

- `PUBLIC` = `'public'`
- `GM_ONLY` = `'gm_only'`
- `PRIVATE` = `'private'`
