# `sidestage.config`

## Classes

### `LLMConfig(BaseModel)`

Configuration for a single LLM endpoint.

| Field | Type | Default |
|-------|------|---------|
| `provider` | `str` | 'llama_cpp' |
| `base_url` | `str` | 'http://localhost:8080/v1' |
| `api_key` | `str` | 'sk-no-key-required' |
| `model` | `str` | 'default' |
| `context_limit` | `int | None` | — |
| `memory_token_budget` | `int | None` | — |

### `SidestageConfig(BaseModel)`

Configuration model for Sidestage settings.

| Field | Type | Default |
|-------|------|---------|
| `loglevel` | `str` | 'INFO' |
| `llms` | `dict[str, LLMConfig]` | *factory* |
| `graph` | `GraphConfig` | *factory* |

## Functions

### `get() -> SidestageConfig`

Get the global config singleton.

Raises:
    RuntimeError: If init() has not been called yet.

### `init(sidestage_dir: Path) -> SidestageConfig`

Load config from sidestage_dir/config.yml and set as global singleton.

Creates the config file with defaults if it doesn't exist.
