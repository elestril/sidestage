# `sidestage.schemas`

API request/response schemas for Sidestage HTTP and WebSocket endpoints.

Domain model classes live in models.py.

## Classes

### `ChatRequest(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `message` | `str` | — |
| `scene_id` | `str` | 'campaign_planning' |

### `ChatResponse(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `user_message` | `ChatMessageModel` | — |
| `agent_message` | `ChatMessageModel | None` | — |

### `EntityListResponse(BaseModel)`

### `EntityMarkdownResponse(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `markdown` | `str` | — |

### `EntityMarkdownUpdateRequest(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `markdown` | `str` | — |

### `ExportResponse(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `message` | `str` | — |

### `ImportResponse(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `message` | `str` | — |

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
