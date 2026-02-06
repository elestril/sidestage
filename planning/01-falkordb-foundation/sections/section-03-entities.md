Now I have all the context needed. Let me produce the section content.

# Section 03: Entity Operations (`entities.py`)

## Overview

This section implements the entity CRUD module for the FalkorDB graph backend. It creates `src/sidestage/graph/entities.py`, which provides async functions for creating, retrieving, updating, deleting, listing, and querying entity nodes in the graph database. It also includes the serialization logic that maps between Pydantic entity models (defined in `src/sidestage/schemas.py`) and FalkorDB graph nodes.

## Dependencies

This section depends on:

- **section-01-errors-and-client**: Provides `GraphClient` (with `.graph` attribute for Cypher queries), `GraphConfig`, `connect()`, `close()`, and the exception hierarchy (`GraphError`, `EntityNotFoundError`, `DuplicateEntityError`, `QueryError`) in `src/sidestage/graph/errors.py` and `src/sidestage/graph/client.py`.
- **section-02-schema**: Provides schema initialization that creates indexes and constraints (unique on `Entity.id`, mandatory on `Entity.id` and `Entity.name`). These constraints are assumed to be in place when entity operations run.

## Background

### Existing Entity Models

All entity types are Pydantic models defined in `src/sidestage/schemas.py`. The hierarchy is:

```
Entity (base: id, name, body)
  ├── Item
  ├── Location (connected_locations: List[str])
  ├── Character (unseen: bool, location_id: Optional[str], inventory: List[str])
  ├── Scene (current_gametime: Optional[int], location_id: Optional[str], events: List[str], messages: List[ChatMessage])
  └── Event (scene_id: str, gametime: int, walltime: str)
       ├── ChatMessage (character_id: str, actor_id: Optional[str], message: str, widget: Optional[Dict])
       ├── JoinEvent (actor_id: str)
       ├── LeaveEvent (actor_id: str)
       └── FastForwardEvent (duration_str: str)
```

Re-export alias in `src/sidestage/models.py`:
```python
from sidestage.schemas import Entity, Item, Location, Character, Event, Scene, ChatMessage
```

### Graph Node Design

Every entity node carries the `:Entity` base label plus its specific type label(s):

| Entity Type  | Node Labels                   |
|-------------|-------------------------------|
| Character   | `:Entity:Character`           |
| Location    | `:Entity:Location`            |
| Item        | `:Entity:Item`                |
| Scene       | `:Entity:Scene`               |
| Event       | `:Entity:Event`               |
| ChatMessage | `:Entity:Event:ChatMessage`   |

The `:Entity` base label enables queries across all entity types. Specific labels enable type-filtered queries. Multi-label nodes (like ChatMessage having both `:Event` and `:ChatMessage`) allow querying at any level of the hierarchy.

### Property Serialization Rules

Not all Pydantic fields map to graph node properties:

- **Stored as scalar properties:** `id`, `name`, `body`, `unseen`, `location_id`, `scene_id`, `gametime`, `walltime`, `current_gametime`, `character_id`, `actor_id`, `message`, `duration_str`
- **Stored as array properties:** `inventory` on Character (list of item ID strings), `events` on Scene (list of event ID strings)
- **NOT stored as properties (become edges in section-04):** `connected_locations` on Location (becomes `CONNECTS_TO` edges)
- **NOT stored in graph at all:** `messages` on Scene (stays in SQLite), `widget` on ChatMessage (complex nested dict, not suitable for graph property storage)

### GraphClient Usage

The `GraphClient` object (from section-01) provides a `.graph` attribute that exposes FalkorDB's `Graph` object. Cypher queries are executed via `await client.graph.query(cypher_string)`. The query result object has a `.result_set` attribute containing rows of results, where each row is a list of values. Node objects have `.labels` (list of strings) and `.properties` (dict).

---

## Tests First

All tests go in `tests/unit/test_graph_entities.py` and `tests/unit/test_graph_serialization.py`. Tests use `pytest` with `unittest.mock.AsyncMock` for mocking the `GraphClient`. Since `pytest-anyio` is not currently in the project's dev dependencies, async tests should use `pytest` with `asyncio` (`@pytest.mark.asyncio` after adding `pytest-asyncio` to dev deps, or use synchronous wrappers around `asyncio.run()`).

### File: `tests/unit/test_graph_serialization.py`

This file tests the serialization/deserialization helpers in isolation (no graph calls needed, pure unit tests).

```python
"""Unit tests for entity serialization to/from graph node properties."""
import pytest
from sidestage.schemas import Character, Location, Item, Scene, Event, ChatMessage


# --- Label Registry ---

# Test: LABEL_TO_MODEL registry contains all entity types
#   Assert that every key in {Character, Location, Item, Scene, Event, ChatMessage}
#   is present in the registry and maps to the correct Pydantic class.

# --- entity_to_labels ---

# Test: entity_to_labels returns ["Entity", "Character"] for a Character instance
# Test: entity_to_labels returns ["Entity", "Location"] for a Location instance
# Test: entity_to_labels returns ["Entity", "Item"] for an Item instance
# Test: entity_to_labels returns ["Entity", "Scene"] for a Scene instance
# Test: entity_to_labels returns ["Entity", "Event"] for an Event instance
# Test: entity_to_labels returns ["Entity", "Event", "ChatMessage"] for a ChatMessage instance

# --- entity_to_properties ---

# Test: entity_to_properties converts Character fields to a property dict containing
#   id, name, body, unseen, location_id, inventory
# Test: entity_to_properties excludes connected_locations for Location
# Test: entity_to_properties excludes messages for Scene
# Test: entity_to_properties handles None optional fields (location_id=None stored as None or omitted)
# Test: entity_to_properties includes array fields (inventory as list)

# --- node_to_entity ---

# Test: node_to_entity reconstructs a Character from labels=["Entity","Character"]
#   plus a properties dict
# Test: node_to_entity reconstructs a ChatMessage from labels=["Entity","Event","ChatMessage"]
#   (picks most specific model)
# Test: node_to_entity picks ChatMessage over Event when both labels are present
# Test: node_to_entity reconstructs a Location from labels + properties
```

### File: `tests/unit/test_graph_entities.py`

This file tests the CRUD functions. The `GraphClient` and its `.graph.query()` method are mocked.

```python
"""Unit tests for graph entity CRUD operations."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sidestage.schemas import Character, Location, Item, Scene, Event, ChatMessage


# --- Fixtures ---

# Fixture: mock_client
#   Creates a MagicMock GraphClient with graph.query as an AsyncMock.
#   The query mock's return_value.result_set should be configurable per test.

# Fixture: sample_character
#   Returns a Character(id="char_1", name="Alice", body="A brave warrior",
#     location_id="loc_1", inventory=["item_sword"])

# Fixture: sample_location
#   Returns a Location(id="loc_1", name="Tavern", body="A cozy tavern",
#     connected_locations=["loc_2"])


# --- Create ---

# Test: create_entity with Character generates correct Cypher CREATE with :Entity:Character labels
#   Mock client.graph.query, call create_entity(client, character).
#   Assert the Cypher passed to query() contains "CREATE (n:Entity:Character" and
#   sets id, name, body, unseen, location_id, inventory properties.

# Test: create_entity with Location generates correct Cypher CREATE with :Entity:Location labels
#   Assert connected_locations is NOT in the Cypher property list.

# Test: create_entity with ChatMessage generates Cypher with :Entity:Event:ChatMessage labels

# Test: create_entity raises DuplicateEntityError when unique constraint is violated
#   Configure mock to raise a FalkorDB/Redis exception indicating constraint violation.
#   Assert DuplicateEntityError is raised.

# Test: create_entity returns the created entity


# --- Get ---

# Test: get_entity returns correct entity when node is found
#   Configure mock result_set to return a single row with a node mock
#   (node.labels = ["Entity","Character"], node.properties = {...}).
#   Assert returned entity is a Character with correct fields.

# Test: get_entity returns None when result_set is empty

# Test: get_entity for ChatMessage node (labels=["Entity","Event","ChatMessage"])
#   reconstructs as ChatMessage, not Event

# Test: get_entity generates Cypher: MATCH (n:Entity {id: $id}) RETURN n


# --- Update ---

# Test: update_entity generates Cypher SET for specified properties only
#   Call update_entity(client, "char_1", {"name": "Bob"}).
#   Assert Cypher contains SET n.name = ... but not SET n.body = ...

# Test: update_entity raises EntityNotFoundError when node not found
#   Configure mock result to indicate zero nodes matched.

# Test: update_entity returns updated entity (makes a get_entity call after update)


# --- Delete ---

# Test: delete_entity generates Cypher MATCH + DETACH DELETE
#   Assert Cypher passed to query() contains "DETACH DELETE"

# Test: delete_entity for non-existent id either raises EntityNotFoundError or succeeds silently
#   (design choice - document whichever is chosen)


# --- List ---

# Test: list_entities without type filter queries MATCH (n:Entity) RETURN n
#   Configure mock result_set with multiple node mocks of different types.
#   Assert all are returned and correctly deserialized.

# Test: list_entities with type filter "Character" queries MATCH (n:Character) RETURN n

# Test: list_entities returns empty list when result_set is empty


# --- Find ---

# Test: find_entities with name="Alice" generates WHERE n.name = "Alice"

# Test: find_entities with multiple filters generates AND conditions

# Test: find_entities returns empty list when no matches
```

---

## Implementation Details

### File: `src/sidestage/graph/entities.py`

This module implements entity CRUD operations and serialization logic for mapping between Pydantic models and FalkorDB graph nodes.

### Label-to-Model Registry

Define a module-level constant mapping FalkorDB label strings to Pydantic model classes. The registry is ordered from most specific to least specific so that deserialization picks the right model for multi-label nodes.

```python
from sidestage.schemas import Character, Location, Item, Scene, Event, ChatMessage

LABEL_TO_MODEL: dict[str, type[Entity]] = {
    "ChatMessage": ChatMessage,
    "Character": Character,
    "Location": Location,
    "Item": Item,
    "Scene": Scene,
    "Event": Event,
}
```

The specificity order matters: when a node has labels `["Entity", "Event", "ChatMessage"]`, the registry is checked and `ChatMessage` is matched first because it appears before `Event`.

### Model-to-Label Mapping

The reverse mapping determines which labels to apply when creating a node. This uses the model's MRO (method resolution order) to walk the class hierarchy.

```python
MODEL_TO_LABELS: dict[type[Entity], list[str]] = {
    Character: ["Entity", "Character"],
    Location: ["Entity", "Location"],
    Item: ["Entity", "Item"],
    Scene: ["Entity", "Scene"],
    Event: ["Entity", "Event"],
    ChatMessage: ["Entity", "Event", "ChatMessage"],
}
```

### Field Exclusion Lists

Some Pydantic fields should not be stored as node properties. Define per-type exclusion sets:

```python
EXCLUDED_FIELDS: dict[type[Entity], set[str]] = {
    Location: {"connected_locations"},  # Becomes CONNECTS_TO edges (section-04)
    Scene: {"messages"},                # Stays in SQLite
    ChatMessage: {"widget"},            # Complex nested dict, not graph-friendly
}
```

The exclusion check also applies to inherited exclusions (ChatMessage inherits Scene's exclusions if it were a subclass, but in this case ChatMessage extends Event, not Scene, so each type's exclusions are independent).

### Serialization Functions

#### `entity_to_labels(entity: Entity) -> list[str]`

Returns the list of FalkorDB labels for a given entity instance. Looks up the entity's type in `MODEL_TO_LABELS`. Falls back to `["Entity"]` if the type is not registered (defensive, should not happen in practice).

#### `entity_to_properties(entity: Entity) -> dict[str, Any]`

Converts a Pydantic entity to a dict of graph node properties. Uses `entity.model_dump()` to get all fields, then removes any fields in the exclusion list for the entity's type. Handles `None` values by either omitting them or storing them as graph null (implementation choice; omitting is cleaner for Cypher).

#### `node_to_entity(labels: list[str], properties: dict[str, Any]) -> Entity`

Reconstructs a Pydantic entity from a graph node's labels and properties. Iterates through `LABEL_TO_MODEL` in specificity order, checking if the label key is present in the node's label set. Uses the first match to determine the model class, then calls `model_class(**properties)` to construct the entity. Raises `QueryError` if no matching label is found.

### CRUD Functions

All functions are async and take a `GraphClient` as their first argument. They construct Cypher query strings and execute them via `await client.graph.query(cypher)`.

#### `create_entity(client: GraphClient, entity: Entity) -> Entity`

1. Call `entity_to_labels(entity)` to get labels like `["Entity", "Character"]`.
2. Call `entity_to_properties(entity)` to get the property dict.
3. Build Cypher: `CREATE (n:Entity:Character {id: $id, name: $name, ...}) RETURN n`
   - Labels are joined with colons: `:Entity:Character`
   - Properties are parameterized to prevent injection
4. Execute the query. On constraint violation (duplicate `id`), catch the FalkorDB exception and raise `DuplicateEntityError`.
5. Return the original entity.

**Cypher parameterization:** FalkorDB's Python client supports parameterized queries via `graph.query(cypher, params={"key": value})`. Use this for all property values to prevent Cypher injection and handle special characters in strings.

#### `get_entity(client: GraphClient, entity_id: str) -> Entity | None`

1. Build Cypher: `MATCH (n:Entity {id: $id}) RETURN n` with params `{"id": entity_id}`.
2. Execute query.
3. If `result_set` is empty, return `None`.
4. Extract the node from `result_set[0][0]`.
5. Call `node_to_entity(node.labels, node.properties)` to reconstruct the Pydantic model.

#### `update_entity(client: GraphClient, entity_id: str, updates: dict) -> Entity`

1. Build Cypher: `MATCH (n:Entity {id: $id}) SET n.prop1 = $prop1, n.prop2 = $prop2 RETURN n`
   - Only the keys in `updates` are included in the SET clause.
2. Execute query.
3. If `result_set` is empty (no node matched), raise `EntityNotFoundError`.
4. Reconstruct and return the updated entity from the result node.

#### `delete_entity(client: GraphClient, entity_id: str) -> None`

1. Build Cypher: `MATCH (n:Entity {id: $id}) DETACH DELETE n`
   - `DETACH DELETE` removes the node and all its relationships.
2. Execute query.
3. Optionally check if any node was actually deleted (via query statistics) and raise `EntityNotFoundError` if not. This is a design choice -- silent success on missing nodes is also acceptable.

#### `list_entities(client: GraphClient, entity_type: str | None = None) -> list[Entity]`

1. If `entity_type` is provided, build Cypher: `MATCH (n:{entity_type}) RETURN n`
   - The type string is validated against `LABEL_TO_MODEL` keys to prevent injection.
2. If `entity_type` is `None`, build Cypher: `MATCH (n:Entity) RETURN n`
3. Execute query.
4. Iterate `result_set`, call `node_to_entity()` for each row, collect into a list.

#### `find_entities(client: GraphClient, **filters) -> list[Entity]`

1. Build Cypher: `MATCH (n:Entity) WHERE n.prop1 = $prop1 AND n.prop2 = $prop2 RETURN n`
   - Filter keys become WHERE clause conditions.
   - Filter values become query parameters.
2. Execute query.
3. Deserialize all matching nodes and return as a list.

### Error Handling

All functions follow the fail-fast policy:

- `DuplicateEntityError` on constraint violations during `create_entity`.
- `EntityNotFoundError` on missing nodes during `update_entity` (and optionally `delete_entity`).
- `QueryError` for unexpected Cypher execution failures.
- Raw FalkorDB/Redis exceptions are caught and wrapped in the appropriate `GraphError` subclass with a descriptive message.

### Logging

Use Python's `logging` module with logger name `sidestage.graph.entities`. Log at INFO level for create/update/delete operations (entity type + id). Log at DEBUG level for query construction details. Log at ERROR level when wrapping exceptions.

---

## Files to Create

| File | Purpose |
|------|---------|
| `src/sidestage/graph/entities.py` | Entity CRUD operations and serialization logic |
| `tests/unit/test_graph_entities.py` | Unit tests for CRUD operations |
| `tests/unit/test_graph_serialization.py` | Unit tests for serialization helpers |

## Files Referenced (Read-Only)

| File | Why |
|------|-----|
| `src/sidestage/schemas.py` | Pydantic entity models (Character, Location, etc.) |
| `src/sidestage/graph/client.py` | GraphClient type used as first argument (from section-01) |
| `src/sidestage/graph/errors.py` | Exception classes raised by entity operations (from section-01) |

## Implementation Checklist

1. Write `tests/unit/test_graph_serialization.py` with all serialization tests (label registry, `entity_to_labels`, `entity_to_properties`, `node_to_entity`).
2. Write `tests/unit/test_graph_entities.py` with all CRUD tests (create, get, update, delete, list, find) using mocked `GraphClient`.
3. Implement serialization helpers in `src/sidestage/graph/entities.py`: `LABEL_TO_MODEL`, `MODEL_TO_LABELS`, `EXCLUDED_FIELDS`, `entity_to_labels()`, `entity_to_properties()`, `node_to_entity()`.
4. Implement CRUD functions in `src/sidestage/graph/entities.py`: `create_entity()`, `get_entity()`, `update_entity()`, `delete_entity()`, `list_entities()`, `find_entities()`.
5. Verify all tests pass with `poetry run pytest tests/unit/test_graph_serialization.py tests/unit/test_graph_entities.py`.