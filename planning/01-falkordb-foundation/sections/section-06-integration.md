Now I have all the context I need. Let me produce the section content.

# Section 06: Integration with Existing Code

## Overview

This section covers the final integration step: wiring the new `src/sidestage/graph/` package into the existing Sidestage codebase. It involves five work items:

1. Creating the `src/sidestage/graph/__init__.py` public API re-exports
2. Adding `GraphConfig` to the campaign configuration schema
3. Updating `Campaign` to create and use a `GraphClient` for entity operations
4. Updating `SceneLogic` to use the graph module for scene and event persistence
5. Updating `WorldTools` to route entity queries through the graph module
6. Adding the `falkordb` dependency to `pyproject.toml`

All previous sections (01 through 05) must be completed before this section can be implemented. This section assumes the following modules already exist and are functional:

- `src/sidestage/graph/errors.py` -- exception hierarchy (section 01)
- `src/sidestage/graph/client.py` -- `GraphClient`, `GraphConfig`, `connect()`, `close()` (section 01)
- `src/sidestage/graph/schema.py` -- `initialize_schema()` (section 02)
- `src/sidestage/graph/entities.py` -- `create_entity()`, `get_entity()`, `update_entity()`, `delete_entity()`, `list_entities()`, `find_entities()` (section 03)
- `src/sidestage/graph/relationships.py` -- `link()`, `unlink()`, `get_related()`, `get_relationships()` (section 04)
- `src/sidestage/graph/queries.py` -- `characters_at_location()`, `connected_locations()`, `scene_events()`, `entity_graph()` (section 05)

---

## Dependencies

| Dependency | Section | What It Provides |
|---|---|---|
| section-01-errors-and-client | 01 | `GraphClient`, `GraphConfig`, `connect()`, `close()`, exception classes |
| section-02-schema | 02 | `initialize_schema()` called by `connect()` |
| section-03-entities | 03 | All entity CRUD functions |
| section-04-relationships | 04 | `link()`, `unlink()`, `get_related()`, `get_relationships()` |
| section-05-queries | 05 | Higher-level query functions |

---

## Tests First

### File: `/home/harald/src/sidestage/tests/integration/test_graph_integration.py`

These integration tests verify that the existing Sidestage components correctly delegate to the graph module. Because the graph module is fully async while the current `Campaign` and `WorldTools` are partly synchronous, these tests use mocking to verify the wiring without requiring a running FalkorDB instance.

```python
"""Integration tests: verify Campaign, SceneLogic, and WorldTools route through the graph module."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Test: Campaign creates a GraphClient on startup when graph config is present
# - Mock graph.client.connect to return a mock GraphClient
# - Verify connect() was called with the expected GraphConfig
# - Verify the Campaign instance holds a reference to the GraphClient

# Test: Campaign entity creation flows through graph module
# - With a Campaign that has a mocked GraphClient
# - Call campaign entity creation logic
# - Verify graph.entities.create_entity was invoked with the correct Entity

# Test: Campaign entity retrieval flows through graph module
# - Mock graph.entities.get_entity to return a Character
# - Call campaign entity retrieval
# - Verify graph.entities.get_entity was called with the correct entity_id

# Test: Campaign entity update flows through graph module
# - Mock graph.entities.update_entity
# - Call campaign entity update logic
# - Verify graph.entities.update_entity was called

# Test: Campaign entity deletion flows through graph module
# - Mock graph.entities.delete_entity
# - Call campaign entity deletion
# - Verify graph.entities.delete_entity was called

# Test: Campaign shutdown closes GraphClient
# - Create Campaign with mocked GraphClient
# - Call campaign shutdown
# - Verify graph.client.close() was called

# Test: SceneLogic can create scene entities via graph module
# - Create SceneLogic with a mocked GraphClient
# - Verify scene event persistence routes through graph.entities.create_entity

# Test: WorldTools entity queries use graph module
# - Create WorldTools with a mocked GraphClient
# - Call list_characters, get_character, etc.
# - Verify they delegate to graph.entities.list_entities and graph.entities.get_entity
```

### File: `/home/harald/src/sidestage/tests/unit/test_graph_init.py`

```python
"""Tests for graph package __init__.py public API."""
import pytest

# Test: graph package exports GraphClient
# Test: graph package exports GraphConfig
# Test: graph package exports connect and close
# Test: graph package exports entity CRUD functions
# Test: graph package exports relationship functions
# Test: graph package exports query functions
# Test: graph package exports all error types
```

---

## Implementation Details

### 1. Public API Re-exports (`src/sidestage/graph/__init__.py`)

This file serves as the public API for the graph package. All consumers (Campaign, SceneLogic, WorldTools) should import from `sidestage.graph` rather than from submodules directly.

The file should re-export the following names:

From `client.py`:
- `GraphClient`
- `GraphConfig`
- `connect`
- `close`

From `entities.py`:
- `create_entity`
- `get_entity`
- `update_entity`
- `delete_entity`
- `list_entities`
- `find_entities`

From `relationships.py`:
- `link`
- `unlink`
- `get_related`
- `get_relationships`

From `queries.py`:
- `characters_at_location`
- `connected_locations`
- `scene_events`
- `entity_graph`

From `errors.py`:
- `GraphError`
- `ConnectionError` (aliased as `GraphConnectionError` to avoid shadowing the builtin)
- `EntityNotFoundError`
- `DuplicateEntityError`
- `SchemaError`
- `QueryError`

An `__all__` list should enumerate every exported name for documentation and linting tools.

---

### 2. GraphConfig in Campaign Configuration

The `GraphConfig` class is defined in `src/sidestage/graph/client.py` (section 01). The integration task is to add it to the campaign's configuration schema so that graph connection settings can be specified in a campaign's `config.yml`.

**File to modify:** `/home/harald/src/sidestage/src/sidestage/campaign.py`

Add a `graph` field to `SidestageConfig`:

```python
from sidestage.graph import GraphConfig

class SidestageConfig(BaseModel):
    # ... existing LLM fields ...
    
    # Graph Database Configuration
    graph: GraphConfig = Field(default_factory=GraphConfig, description="FalkorDB graph database configuration")
```

This makes graph configuration optional -- if not specified in `config.yml`, defaults are used (localhost:6379, graph name derived from campaign name).

---

### 3. Campaign Integration (`src/sidestage/campaign.py`)

Campaign currently instantiates `Storage` for all persistence. The changes add a `GraphClient` alongside `Storage`, routing entity operations through the graph module while keeping `Storage` for chat logs and campaign configuration.

**Key changes:**

The Campaign `__init__` method becomes `async` (or more practically, a new `async` class method or startup method is introduced) because `graph.connect()` is async. The recommended approach is to add an `async def start_graph(self)` method that the application entrypoint calls after constructing the Campaign.

```python
class Campaign:
    def __init__(self, name: str, base_dir: Path):
        # ... existing init code ...
        self.graph_client: GraphClient | None = None
    
    async def start_graph(self) -> None:
        """Initialize the FalkorDB graph connection.
        
        Must be called after __init__ and before any graph operations.
        Derives graph_name from campaign name if not configured.
        """
    
    async def shutdown(self) -> None:
        """Shut down the campaign, closing graph connections."""
```

`start_graph()` should:
1. Read `self.config.graph` for connection parameters
2. If `graph_name` is None, derive it from `self.name` (lowercase, replace spaces with underscores, strip special characters)
3. Call `graph.connect(config)` to get a `GraphClient`
4. Store the client as `self.graph_client`

`shutdown()` should:
1. Call `graph.close(self.graph_client)` if `graph_client` is not None
2. Set `self.graph_client = None`

**Entity operation routing:**

The following Campaign methods should be updated to use the graph module when `self.graph_client` is available. If graph_client is None (graph not yet initialized), they should fall back to `self.storage` for backwards compatibility during the transition period.

- `list_entities()` -- delegates to `graph.list_entities(self.graph_client)` instead of `self.storage.list_all_entities()`
- `update_entity_markdown()` -- uses `graph.update_entity()` after parsing markdown
- `update_entity()` -- uses `graph.update_entity()`
- `create_scene()` -- uses `graph.create_entity()` and `graph.link()` for location association
- `_ensure_defaults()` -- uses `graph.create_entity()` for the default scene and default characters
- `reload_defaults()` -- uses `graph.create_entity()` for loading characters from markdown files

**Important note on `Storage` coexistence:** Storage retains responsibility for:
- Chat message persistence (the `messages` list on Scene)
- `get_scene_messages()` still reads from Storage
- Any non-entity data (campaign config, logs)

Entity methods on Storage (`add_character`, `get_character`, `list_characters`, etc.) are NOT removed in this section -- they remain available but are no longer called by Campaign, SceneLogic, or WorldTools for entity operations. Removal happens in a future cleanup.

---

### 4. SceneLogic Integration (`src/sidestage/scene.py`)

SceneLogic currently takes a `Storage` instance and uses it for scene data persistence. The integration adds an optional `GraphClient` parameter.

**File to modify:** `/home/harald/src/sidestage/src/sidestage/scene.py`

**Key changes:**

The constructor gains an optional `graph_client` parameter:

```python
class SceneLogic:
    def __init__(self, storage: Storage, agent: LiteLLMAgent, data: Scene,
                 graph_client: GraphClient | None = None):
        """..."""
        self.graph_client = graph_client
        # ... rest of init ...
```

The `_on_publish_hook` method is updated to persist Event entities to the graph when a `graph_client` is available:

- When a `ChatMessage` is published, and `self.graph_client` is not None:
  1. Create the ChatMessage as a graph entity via `graph.create_entity(self.graph_client, event)`
  2. Create a `HAS_EVENT` relationship from the Scene to the Event via `graph.link()`
  3. If the message has a `character_id`, create an `INVOLVES` relationship via `graph.link()`
  4. Continue to append to `self.data.messages` and persist via `self.storage.update_scene()` for backward compatibility

The `activate` method is updated to use graph queries for character loading when available:

```python
async def activate(self) -> None:
    # If graph_client available, use graph.queries.characters_at_location
    # or graph.entities.list_entities to find characters
    # Otherwise, fall back to self.storage.list_characters()
```

The `get_scene_object` factory in Campaign is updated to pass the `graph_client`:

```python
def get_scene_object(self, scene_id: str) -> Optional[SceneLogic]:
    data = self.storage.get_scene(scene_id)
    if not data:
        return None
    return SceneLogic(self.storage, self.agent, data, graph_client=self.graph_client)
```

---

### 5. WorldTools Integration (`src/sidestage/tools.py`)

WorldTools currently accepts only a `Storage` instance. The integration adds an optional `GraphClient` parameter and routes entity operations through the graph module when available.

**File to modify:** `/home/harald/src/sidestage/src/sidestage/tools.py`

**Key changes:**

The constructor gains an optional `graph_client` parameter:

```python
class WorldTools:
    def __init__(self, storage: Storage, on_change: Optional[Callable[[], Any]] = None,
                 graph_client: GraphClient | None = None):
        self.storage = storage
        self.graph_client = graph_client
        self.on_change = on_change
```

Because all graph module functions are async, and WorldTools methods are currently synchronous (they are registered as LLM tool functions), the methods need to become async. This is a significant change that affects how the LiteLLMAgent calls tools.

The recommended approach for each method:

**`create_character`:** Becomes async. When `self.graph_client` is available:
1. Creates a `Character` Pydantic model
2. Calls `await graph.create_entity(self.graph_client, char)`
3. If `location_id` is set, calls `await graph.link(self.graph_client, char.id, "LOCATED_IN", location_id)`
4. Returns `char.model_dump_json()`
5. Falls back to `self.storage.add_character(char)` if no graph_client

**`get_character`:** Becomes async. When `self.graph_client` is available:
1. Calls `await graph.get_entity(self.graph_client, character_id)`
2. Returns the entity serialized as JSON, or "Character not found."
3. Falls back to `self.storage.get_character()` if no graph_client

**`list_characters`:** Becomes async. When `self.graph_client` is available:
1. Calls `await graph.list_entities(self.graph_client, entity_type="Character")`
2. Returns JSON list
3. Falls back to `self.storage.list_characters()` if no graph_client

**`update_character`:** Becomes async. When `self.graph_client` is available:
1. Calls `await graph.get_entity()` to verify existence
2. Calls `await graph.update_entity()` with the changed properties
3. If `location_id` changed, calls `await graph.unlink()` for old LOCATED_IN and `await graph.link()` for new one
4. Falls back to `self.storage.update_character()` if no graph_client

The same pattern applies to `create_location`, `update_location`, `list_locations`, `create_item`, `update_item`, `list_items`.

**Campaign wiring update:** In `campaign.py`, update the `WorldTools` construction to pass the graph client:

```python
self.world_tools = WorldTools(storage=self.storage, graph_client=self.graph_client)
```

Since `self.graph_client` may be None at Campaign construction time (before `start_graph()` is called), WorldTools should handle the None case gracefully by falling back to Storage.

---

### 6. Dependency Addition (`pyproject.toml`)

**File to modify:** `/home/harald/src/sidestage/pyproject.toml`

Add `falkordb` to the project dependencies:

```toml
dependencies = [
    # ... existing dependencies ...
    "falkordb (>=1.4.0,<2.0.0)",
]
```

The `falkordb` package bundles `redis[hiredis]` as a dependency, so no additional Redis packages need to be added. Also add `anyio` or `pytest-anyio` to dev dependencies if not already present, since the integration tests use `@pytest.mark.anyio`:

```toml
[dependency-groups]
dev = [
    # ... existing dev dependencies ...
    "anyio (>=4.0.0,<5.0.0)",
    "pytest-anyio (>=0.0.0)",
]
```

Check whether `anyio` or `pytest-anyio` is already available transitively before adding -- if `fastapi` or another dependency already pulls it in, only the pytest plugin needs to be explicit.

---

### 7. Graph Name Sanitization

When `GraphConfig.graph_name` is None, the Campaign must derive a graph name from the campaign name. The sanitization rules are:

1. Convert to lowercase
2. Replace spaces and hyphens with underscores
3. Strip any characters that are not alphanumeric or underscore
4. Ensure the result is not empty (fall back to "default" if it would be)

This logic belongs in `Campaign.start_graph()` where the config is prepared before calling `graph.connect()`. A standalone helper function is acceptable:

```python
def sanitize_graph_name(campaign_name: str) -> str:
    """Derive a FalkorDB graph name from a campaign name."""
```

---

## File Summary

| File | Action | Purpose |
|---|---|---|
| `/home/harald/src/sidestage/src/sidestage/graph/__init__.py` | Create | Public API re-exports for the graph package |
| `/home/harald/src/sidestage/src/sidestage/campaign.py` | Modify | Add GraphConfig to SidestageConfig, add start_graph()/shutdown(), route entity ops through graph |
| `/home/harald/src/sidestage/src/sidestage/scene.py` | Modify | Accept optional GraphClient, persist events to graph, use graph for character queries |
| `/home/harald/src/sidestage/src/sidestage/tools.py` | Modify | Accept optional GraphClient, make methods async, route entity ops through graph |
| `/home/harald/src/sidestage/pyproject.toml` | Modify | Add falkordb dependency, ensure pytest-anyio in dev deps |
| `/home/harald/src/sidestage/tests/integration/test_graph_integration.py` | Create | Integration tests verifying wiring between Campaign/SceneLogic/WorldTools and graph module |
| `/home/harald/src/sidestage/tests/unit/test_graph_init.py` | Create | Tests for graph package public API exports |

---

## Implementation Notes

### Async Transition

The most impactful change in this section is introducing async operations into components that were previously synchronous. The `WorldTools` methods becoming async requires that the LLM agent framework (LiteLLMAgent) supports async tool functions. Before implementing, verify that `LiteLLMAgent` can handle async tool callbacks. If it cannot, the WorldTools methods may need to use `asyncio.run()` or a similar bridge, or the agent framework may need modification (which would be a separate task).

### Backward Compatibility

All changes use the "optional graph_client" pattern. When `graph_client` is None, all code paths fall back to the existing `Storage`-based behavior. This means:

- The application continues to work without a running FalkorDB instance
- Graph integration can be enabled per-campaign via `config.yml`
- No existing tests break due to the changes

### Testing Without FalkorDB

The integration tests in this section use mocks for the `GraphClient`. They verify that the wiring is correct (the right graph functions are called with the right arguments) without requiring a live FalkorDB instance. True end-to-end integration tests (against a real FalkorDB) should be added separately and marked with a custom pytest marker (e.g., `@pytest.mark.falkordb`) so they can be skipped in CI environments without FalkorDB.

### Storage Deprecation Path

Entity methods on the `Storage` class are NOT removed in this section. They remain for:
- Backward compatibility during the transition
- Chat message persistence (which stays in SQLite)
- Any code paths where `graph_client` is None

A future cleanup task should remove the deprecated entity methods from `Storage` once all consumers have been fully migrated and FalkorDB is a hard requirement.