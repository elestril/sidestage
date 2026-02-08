# `sidestage.schemas`

## Classes

### `Character(Entity)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | — |
| `id` | `str` | — |
| `unseen` | `bool` | False |
| `location_id` | `str | None` | — |
| `inventory` | `list[str]` | *factory* |

### `ChatMessage(Event)`

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

### `ChatRequest(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `message` | `str` | — |
| `scene_id` | `str` | 'campaign_planning' |

### `ChatResponse(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `user_message` | `ChatMessage` | — |
| `agent_message` | `ChatMessage | None` | — |

### `Entity(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | — |
| `id` | `str` | — |

### `EntityListResponse(BaseModel)`

### `EntityMarkdownResponse(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `markdown` | `str` | — |

### `EntityMarkdownUpdateRequest(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `markdown` | `str` | — |

### `Event(Entity)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | — |
| `id` | `str` | — |
| `scene_id` | `str` | — |
| `gametime` | `int` | — |
| `walltime` | `str` | — |

### `ExportResponse(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `message` | `str` | — |

### `FastForwardEvent(Event)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | — |
| `id` | `str` | — |
| `scene_id` | `str` | — |
| `gametime` | `int` | — |
| `walltime` | `str` | — |
| `duration_str` | `str` | — |

### `ImportResponse(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `message` | `str` | — |

### `Item(Entity)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | — |
| `id` | `str` | — |

### `JoinEvent(Event)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | — |
| `id` | `str` | — |
| `scene_id` | `str` | — |
| `gametime` | `int` | — |
| `walltime` | `str` | — |
| `actor_id` | `str` | — |

### `LeaveEvent(Event)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | — |
| `id` | `str` | — |
| `scene_id` | `str` | — |
| `gametime` | `int` | — |
| `walltime` | `str` | — |
| `actor_id` | `str` | — |

### `Location(Entity)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | — |
| `id` | `str` | — |
| `connected_locations` | `list[str]` | *factory* |

### `Scene(Entity)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `body` | `str` | — |
| `id` | `str` | — |
| `current_gametime` | `int | None` | — |
| `location_id` | `str | None` | — |
| `events` | `list[str]` | *factory* |
| `messages` | `list[ChatMessage]` | *factory* |

### `SceneCreateRequest(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `description` | `str` | '' |
| `current_gametime` | `int | None` | — |

### `StatusResponse(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `status` | `Literal[ok, error]` | — |
| `message` | `str | None` | — |

### `WebSocketMessage(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `type` | `str` | — |
| `text` | `str | None` | — |
| `sender` | `str | None` | — |
| `scene_id` | `str | None` | — |
| `widget` | `dict[str, Any] | None` | — |
| `entity_id` | `str | None` | — |
| `body` | `str | None` | — |
