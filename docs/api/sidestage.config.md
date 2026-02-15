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
| `logging` | `LogConfig` | *factory* |
| `llms` | `dict[str, LLMConfig]` | *factory* |
| `graph` | `GraphConfig` | *factory* |
| `tracing` | `TraceConfig` | *factory* |

### `TraceConfig(BaseModel)`

Configuration for the tracing subsystem.

| Field | Type | Default |
|-------|------|---------|
| `enabled` | `bool` | False |
| `otlp_endpoint` | `str` | 'http://localhost:4318' |
| `capture_prompts` | `bool` | True |
| `capture_tool_args` | `bool` | True |
| `capture_memory_content` | `bool` | True |
| `max_attribute_length` | `int` | 4096 |

## Functions

### `get_config() -> SidestageConfig`

Load config from sidestage_dir/config.yml and set as global singleton.

Creates the config file with defaults if it doesn't exist.

### `init(sidestage_dir: Path) -> SidestageConfig`

Initialize the configuration with a specific directory.
