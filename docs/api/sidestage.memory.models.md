# `sidestage.memory.models`

Core memory data types for the sidestage memory system.

## Classes

### `ContextMemories(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `common_scene_memory` | `sidestage.memory.models.Memory | None` | — |
| `private_scene_memory` | `sidestage.memory.models.Memory | None` | — |
| `character_memories` | `dict[str, Memory]` | — |
| `world_facts` | `list[Memory]` | — |

### `ContextResult(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `memory_text` | `str` | — |
| `chat_text` | `str` | — |
| `token_estimate` | `int` | — |

### `Memory(BaseModel)`

| Field | Type | Default |
|-------|------|---------|
| `id` | `str` | *factory* |
| `content` | `str` | — |
| `memory_type` | `MemoryType` | — |
| `visibility` | `str` | — |
| `embedding` | `list[float] | None` | — |
| `owner_id` | `str | None` | — |
| `target_id` | `str` | — |
| `created_at` | `float` | *factory* |
| `updated_at` | `float` | *factory* |
| `gametime` | `int | None` | — |
| `access_count` | `int` | 0 |
| `last_accessed_at` | `float | None` | — |

### `MemoryType(str, Enum)`

**Values:**

- `SCENE` = `'scene'`
- `CHARACTER` = `'character'`
- `WORLD_FACT` = `'world_fact'`
