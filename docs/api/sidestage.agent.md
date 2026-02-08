# `sidestage.agent`

## Classes

### `AgentResponse(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `content` | `str` | — |

### `LiteLLMAgent`

#### `__init__(name: str, model: str, api_base: str | None = None, api_key: str | None = None, instructions: list[str] | None = None, tools: list[Callable[Ellipsis, Any]] | None = None, debug_mode: bool = False, kwargs: Any)`

#### `arun(message: str, context: str | None = None, stream: bool = False) -> AgentResponse` *async*
