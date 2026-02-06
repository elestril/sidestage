Now I have all the context I need. Let me generate the section content.

# Section 04: Relationship Operations (`relationships.py`)

## Overview

This section implements the relationship (edge) operations module at `/home/harald/src/sidestage/src/sidestage/graph/relationships.py`. It provides functions to create, delete, and query edges between entity nodes in FalkorDB. These operations form the core graph capability that distinguishes FalkorDB from the previous flat SQLite storage.

## Dependencies

This section depends on:
- **section-01-errors-and-client**: `GraphClient` class, `GraphError`, `EntityNotFoundError`, and `QueryError` from `/home/harald/src/sidestage/src/sidestage/graph/errors.py` and `/home/harald/src/sidestage/src/sidestage/graph/client.py`
- **section-03-entities**: Entity CRUD and serialization helpers from `/home/harald/src/sidestage/src/sidestage/graph/entities.py`, specifically `node_to_entity` for deserializing query results into Pydantic models

These must be implemented and working before starting this section.

## Background Context

### Relationship Types in the Graph Schema

The FalkorDB graph uses these typed relationships (edges) between entity nodes:

| Relationship | Source -> Target | Purpose |
|---|---|---|
| `LOCATED_IN` | Character -> Location | Character's current location |
| `CONNECTS_TO` | Location -> Location | Passable connection between locations |
| `AT_LOCATION` | Scene -> Location | Scene's setting |
| `HAS_EVENT` | Scene -> Event | Events within a scene |
| `INVOLVES` | Event -> Character | Characters referenced in events |
| `PARTICIPATES_IN` | Character -> Scene | Characters present in a scene |

`CONNECTS_TO` is stored as a directed edge in the graph but is semantically bidirectional. Queries for "locations connected to X" must traverse both incoming and outgoing `CONNECTS_TO` edges. The `get_related` function handles this via its `direction` parameter.

### Entity Node Structure

Every entity node carries the `:Entity` base label plus its type-specific label (e.g., `:Entity:Character`). All entity nodes have at minimum an `id` and `name` property. The `id` property is unique across all entities and is used to match source/target nodes when creating edges.

### Design Principles

- **Single-edge focus**: The `relationships.py` module handles one edge at a time. Compound operations (e.g., "move character to new location" = delete old LOCATED_IN + create new LOCATED_IN) are coordinated by callers at a higher level.
- **Fail-fast**: Operations raise immediately on error. No retry logic or fallback.
- **Best effort for multi-step**: When a higher-level operation involves multiple edge changes, each step is logged individually. If an intermediate step fails, the error is logged with context and re-raised.

---

## Tests First

### Test File: `/home/harald/src/sidestage/tests/unit/test_graph_relationships.py`

All tests are async and use `pytest.mark.anyio`. The `GraphClient` is mocked -- the `client.graph.query` method is replaced with an `AsyncMock` that returns controlled results. This keeps tests fast and avoids requiring a running FalkorDB instance.

```python
"""Unit tests for graph relationship operations."""
import pytest
from unittest.mock import AsyncMock, MagicMock

# --- Link ---

# Test: link creates typed edge between two entities
# Setup: Mock client.graph.query to succeed. Call link(client, "char_1", "LOCATED_IN", "loc_1").
# Assert: The Cypher query passed to client.graph.query contains MATCH for source :Entity {id: "char_1"},
#   MATCH for target :Entity {id: "loc_1"}, and CREATE (source)-[:LOCATED_IN]->(target).
# Assert: The query is called exactly once.

# Test: link with properties stores properties on edge
# Setup: Call link(client, "char_1", "LOCATED_IN", "loc_1", properties={"since": "2024-01-01"}).
# Assert: The Cypher query includes property assignment on the edge, e.g., [:LOCATED_IN {since: "2024-01-01"}].

# Test: link raises EntityNotFoundError if source doesn't exist
# Setup: Mock client.graph.query to return a result indicating zero nodes matched for source.
# Assert: Raises EntityNotFoundError with a message mentioning the source ID.

# Test: link raises EntityNotFoundError if target doesn't exist
# Setup: Mock client.graph.query to return a result indicating zero nodes matched for target.
# Assert: Raises EntityNotFoundError with a message mentioning the target ID.

# --- Unlink ---

# Test: unlink removes edge between two entities
# Setup: Call unlink(client, "char_1", "LOCATED_IN", "loc_1").
# Assert: Cypher query MATCHes the specific edge pattern and DELETEs it.

# Test: unlink is idempotent (no error if edge doesn't exist)
# Setup: Mock client.graph.query to return result with zero relationships deleted.
# Assert: No exception is raised.

# --- Get Related ---

# Test: get_related returns outgoing related entities
# Setup: Mock query result with nodes connected via outgoing edges.
# Assert: Returns list of deserialized Entity objects.

# Test: get_related returns incoming related entities
# Setup: Mock query result with nodes connected via incoming edges.
# Assert: Returns list of deserialized Entity objects with correct types.

# Test: get_related with direction="both" returns all related
# Setup: Mock query with both-direction traversal.
# Assert: Returns combined results from both directions.

# Test: get_related returns empty list when no relationships
# Setup: Mock query returning no results.
# Assert: Returns empty list, no error.

# Test: get_related with CONNECTS_TO and direction="both" finds bidirectional connections
# Setup: Create mock results representing Location nodes connected in both directions.
# Assert: Returns all connected locations regardless of edge direction.

# --- Get Relationships ---

# Test: get_relationships returns all relationships for an entity
# Setup: Mock query returning multiple relationships of different types.
# Assert: Returns list of dicts with rel_type, direction, target_id, target_name, properties.

# Test: get_relationships includes rel_type, direction, target info
# Setup: Mock a single relationship result.
# Assert: Returned dict has all expected keys with correct values.

# Test: get_relationships returns empty list for entity with no relationships
# Setup: Mock query returning no results.
# Assert: Returns empty list.
```

### Test Fixture Pattern

Tests should use a shared fixture that provides a mock `GraphClient`:

```python
@pytest.fixture
def mock_client():
    """Create a mock GraphClient with an async query method."""
    client = MagicMock()
    client.graph = MagicMock()
    client.graph.query = AsyncMock()
    return client
```

The `AsyncMock` for `client.graph.query` should be configured per-test to return appropriate `QueryResult`-like objects. The FalkorDB query result has a `result_set` attribute (list of rows) and metadata about nodes/relationships created or deleted.

---

## Implementation Details

### File: `/home/harald/src/sidestage/src/sidestage/graph/relationships.py`

This module exposes four public async functions: `link`, `unlink`, `get_related`, and `get_relationships`.

### `link` Function

```python
async def link(
    client: GraphClient,
    source_id: str,
    rel_type: str,
    target_id: str,
    properties: dict | None = None,
) -> None:
    """Create a relationship between two entities.

    Matches source and target by :Entity id property, creates a typed edge.
    Optional properties dict for edge metadata (stored on the edge).

    Raises EntityNotFoundError if source or target entity does not exist.
    Raises QueryError if the Cypher query fails.
    """
```

**Cypher pattern** (without properties):
```cypher
MATCH (s:Entity {id: $source_id})
MATCH (t:Entity {id: $target_id})
CREATE (s)-[:LOCATED_IN]->(t)
```

**Cypher pattern** (with properties):
```cypher
MATCH (s:Entity {id: $source_id})
MATCH (t:Entity {id: $target_id})
CREATE (s)-[:LOCATED_IN $props]->(t)
```

The relationship type (`rel_type`) is interpolated into the Cypher string since FalkorDB does not support parameterized relationship types. The `rel_type` value must be validated against a known set of relationship types to prevent injection. A constant set of valid types should be defined:

```python
VALID_REL_TYPES = frozenset({
    "LOCATED_IN",
    "CONNECTS_TO",
    "AT_LOCATION",
    "HAS_EVENT",
    "INVOLVES",
    "PARTICIPATES_IN",
})
```

To detect whether source/target exist, the implementation should use a single query that attempts the MATCH and checks whether nodes were found. One approach is to use a two-step query: first MATCH both nodes, then conditionally CREATE. Alternatively, check the query statistics (nodes_created, relationships_created) to verify the edge was created. If zero relationships were created after a query that should create one, it means a source or target was not found.

A practical approach: use `OPTIONAL MATCH` for both nodes, `RETURN` their IDs, then conditionally raise `EntityNotFoundError` if either is null. If both exist, run the `CREATE` query. This costs two round-trips but gives clear error messages about which entity is missing.

### `unlink` Function

```python
async def unlink(
    client: GraphClient,
    source_id: str,
    rel_type: str,
    target_id: str,
) -> None:
    """Remove a relationship between two entities.

    Idempotent: does not raise if the edge does not exist.
    """
```

**Cypher pattern**:
```cypher
MATCH (s:Entity {id: $source_id})-[r:LOCATED_IN]->(t:Entity {id: $target_id})
DELETE r
```

If no matching edge exists, the MATCH simply returns no rows and DELETE is a no-op. This makes unlink naturally idempotent.

### `get_related` Function

```python
async def get_related(
    client: GraphClient,
    entity_id: str,
    rel_type: str,
    direction: str = "outgoing",
) -> list[Entity]:
    """Get entities related via a specific relationship type.

    Args:
        client: The graph client.
        entity_id: ID of the source entity.
        rel_type: The relationship type to traverse.
        direction: "outgoing", "incoming", or "both".
            For CONNECTS_TO, use "both" since it is semantically bidirectional.

    Returns:
        List of deserialized Entity (or subclass) objects.
    """
```

**Cypher patterns by direction**:

- **outgoing**: `MATCH (s:Entity {id: $id})-[:REL_TYPE]->(t) RETURN t`
- **incoming**: `MATCH (s:Entity {id: $id})<-[:REL_TYPE]-(t) RETURN t`
- **both**: `MATCH (s:Entity {id: $id})-[:REL_TYPE]-(t) RETURN t`

The "both" direction uses the undirected edge pattern `()-[:REL_TYPE]-()` which matches edges in either direction. This is the correct pattern for `CONNECTS_TO` which is semantically bidirectional.

The returned nodes must be deserialized into their correct Pydantic model types. This requires reading the node's labels to determine the model class, then populating properties. This uses the `node_to_entity` helper from `entities.py` (section-03).

FalkorDB query results return `Node` objects with `.labels` (list of strings) and `.properties` (dict). The deserialization flow is:
1. Extract node from each result row
2. Read node labels
3. Look up the most specific label in `LABEL_TO_MODEL` (from entities module)
4. Construct the Pydantic model from node properties

### `get_relationships` Function

```python
async def get_relationships(
    client: GraphClient,
    entity_id: str,
) -> list[dict]:
    """Get all relationships for an entity.

    Returns list of dicts, each containing:
        - rel_type: str (e.g., "LOCATED_IN")
        - direction: str ("outgoing" or "incoming")
        - target_id: str
        - target_name: str
        - properties: dict (edge properties, may be empty)

    Useful for entity detail views showing all connections.
    """
```

**Cypher approach**: Use two queries (or a UNION) to get both outgoing and incoming relationships:

```cypher
// Outgoing
MATCH (s:Entity {id: $id})-[r]->(t:Entity)
RETURN type(r) AS rel_type, t.id AS target_id, t.name AS target_name, properties(r) AS props

// Incoming
MATCH (s:Entity {id: $id})<-[r]-(t:Entity)
RETURN type(r) AS rel_type, t.id AS target_id, t.name AS target_name, properties(r) AS props
```

Tag outgoing results with `direction: "outgoing"` and incoming with `direction: "incoming"`. Combine into a single list.

Alternatively, use a single query with two OPTIONAL MATCH clauses and UNION, but two queries may be simpler and clearer.

### Relationship Lifecycle Notes

The `relationships.py` module focuses on single-edge operations. However, certain entity lifecycle events require coordinated relationship changes. These compound operations are handled by the caller (typically `entities.py` or a higher-level orchestration function):

- **Character creation with `location_id`**: After `create_entity` for the Character node, call `link(client, char_id, "LOCATED_IN", location_id)`.
- **Character location change**: Call `unlink(client, char_id, "LOCATED_IN", old_location_id)`, then `link(client, char_id, "LOCATED_IN", new_location_id)`.
- **Scene creation with `location_id`**: After `create_entity` for the Scene node, call `link(client, scene_id, "AT_LOCATION", location_id)`.
- **Location deletion**: Handled by `DETACH DELETE` in `delete_entity` (section-03), which automatically removes all edges.

The `relationships.py` module does NOT need to know about these orchestration patterns. It provides the primitive operations that callers compose.

### Logging

All operations should log at DEBUG level for normal operations and ERROR level for failures. Use the standard `logging` module:

```python
import logging

logger = logging.getLogger(__name__)
```

Log the entity IDs and relationship type for every `link` and `unlink` call. Log the count of results for `get_related` and `get_relationships`.

### Validation

The `rel_type` parameter must be validated against `VALID_REL_TYPES` before interpolation into Cypher strings. If an invalid type is passed, raise a `ValueError` immediately. This prevents Cypher injection and catches typos early.

The `direction` parameter in `get_related` must be one of `"outgoing"`, `"incoming"`, or `"both"`. Raise `ValueError` for any other value.

---

## Summary Checklist

1. Create test file at `/home/harald/src/sidestage/tests/unit/test_graph_relationships.py` with all test stubs listed above
2. Implement `VALID_REL_TYPES` constant and `direction` validation
3. Implement `link()` with Cypher edge creation, optional properties, and existence checking
4. Implement `unlink()` with idempotent Cypher edge deletion
5. Implement `get_related()` with directional traversal and entity deserialization
6. Implement `get_relationships()` returning all edges as structured dicts
7. Verify all tests pass with mocked `GraphClient`