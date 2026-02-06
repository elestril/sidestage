Good, the project uses `@pytest.mark.anyio` for async tests. Now I have all the context I need. Let me generate the section content.

# Section 05: Graph Queries (`queries.py`)

## Overview

This section implements `src/sidestage/graph/queries.py`, the higher-level graph query module. It provides specialized, efficient Cypher-based query functions that combine entity and relationship operations into single graph traversals. These functions return fully deserialized Pydantic models and are the primary interface for the rest of the application when answering questions like "which characters are at this location?" or "what events happened in this scene?"

## Dependencies

This section depends on:

- **section-03-entities**: Provides entity deserialization (`node_to_entity`), the `LABEL_TO_MODEL` registry, and `GraphClient` usage patterns
- **section-04-relationships**: Provides the relationship type constants and edge semantics (`LOCATED_IN`, `CONNECTS_TO`, `HAS_EVENT`, etc.)
- **section-01-errors-and-client**: Provides `GraphClient`, `GraphError`, `QueryError`, and `EntityNotFoundError`

## File to Create

**`/home/harald/src/sidestage/src/sidestage/graph/queries.py`**

## Background Context

### Entity Models (from `src/sidestage/schemas.py`)

The Pydantic models relevant to this module:

- `Character(Entity)` -- has `location_id`, `unseen`, `inventory`
- `Location(Entity)` -- has `connected_locations` (list of IDs; stored as `CONNECTS_TO` edges in graph)
- `Scene(Entity)` -- has `current_gametime`, `location_id`, `events`, `messages`
- `Event(Entity)` -- has `scene_id`, `gametime`, `walltime`
- `ChatMessage(Event)` -- has `character_id`, `actor_id`, `message`, `widget`

### Relationship Types

| Relationship | Source -> Target | Purpose |
|---|---|---|
| `LOCATED_IN` | Character -> Location | Character's current location |
| `CONNECTS_TO` | Location -> Location | Passable connection (semantically bidirectional) |
| `AT_LOCATION` | Scene -> Location | Scene's setting |
| `HAS_EVENT` | Scene -> Event | Events within a scene |
| `INVOLVES` | Event -> Character | Characters referenced in events |
| `PARTICIPATES_IN` | Character -> Scene | Characters present in a scene |

### GraphClient

`GraphClient` is the async FalkorDB wrapper established in section-01. It exposes a `.graph` attribute which provides a `.query(cypher_string)` method that returns result sets. All queries in this module use `client.graph.query(...)`.

### Deserialization

Entities are reconstructed from graph nodes using the `node_to_entity` function from the entities module. This function takes a node's labels and properties and returns the appropriate Pydantic model instance. It picks the most specific label when multiple apply (e.g., `ChatMessage` over `Event`).

## Tests First

### Test file: `/home/harald/src/sidestage/tests/unit/test_graph_queries.py`

All tests mock `GraphClient` and its `graph.query()` method. They verify that the correct Cypher queries are constructed and that results are properly deserialized into Pydantic models. Tests use `@pytest.mark.anyio` and `async def`.

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

# Test: characters_at_location returns characters LOCATED_IN the given location
#
# Mock graph.query to return result rows with Character node data.
# Call characters_at_location(client, "loc_tavern").
# Assert the Cypher query matches :Character nodes via -[:LOCATED_IN]-> pattern
# targeting the location by id.
# Assert returned list contains Character model instances with correct fields.

# Test: characters_at_location returns empty list for empty location
#
# Mock graph.query to return an empty result set.
# Call characters_at_location(client, "loc_empty").
# Assert returned list is empty (not None, not an error).

# Test: connected_locations returns all CONNECTS_TO locations (both directions)
#
# Mock graph.query to return Location nodes connected in both directions.
# Call connected_locations(client, "loc_tavern").
# Assert the Cypher query traverses CONNECTS_TO in both directions
# (using undirected match or a UNION / bidirectional pattern).
# Assert returned list contains Location model instances.

# Test: scene_events returns all events in a scene via HAS_EVENT
#
# Mock graph.query to return Event nodes.
# Call scene_events(client, "scene_01").
# Assert Cypher matches Scene -[:HAS_EVENT]-> Event pattern.
# Assert returned list contains Event model instances.

# Test: scene_events with since_gametime filters by gametime
#
# Mock graph.query to return filtered Event nodes.
# Call scene_events(client, "scene_01", since_gametime=3600).
# Assert the Cypher query includes a WHERE clause filtering
# e.gametime >= 3600.
# Assert only events at or after the threshold are returned.

# Test: entity_graph at depth=1 returns entity and directly connected entities
#
# Mock graph.query to return a center node and its neighbors.
# Call entity_graph(client, "char_alice", depth=1).
# Assert the Cypher uses a variable-length path pattern with depth 1.
# Assert the returned dict contains the center entity and its neighbors.

# Test: entity_graph at depth=2 returns two levels of connections
#
# Mock graph.query to return center node plus two levels of neighbors.
# Call entity_graph(client, "char_alice", depth=2).
# Assert the Cypher uses a variable-length path pattern up to depth 2.
# Assert the returned dict contains entities at both depth levels.
```

### Testing approach

Each test should:

1. Create a mock `GraphClient` with `client.graph.query = AsyncMock(return_value=mock_result)`
2. The mock result should simulate FalkorDB's result format: `result.result_set` is a list of rows (tuples/lists), where each element is a `Node` with `.labels` and `.properties` attributes, or a scalar value
3. Call the query function under test
4. Assert the Cypher string passed to `graph.query()` contains the expected patterns (use `call_args` inspection)
5. Assert the returned models are correct types with correct field values

## Implementation Details

### Function Signatures and Behavior

The module exposes four public async functions. Each constructs a single Cypher query string, executes it via `client.graph.query()`, and deserializes the result nodes into Pydantic models using `node_to_entity`.

```python
async def characters_at_location(client: GraphClient, location_id: str) -> list[Character]:
    """All characters currently at a location (via LOCATED_IN).

    Cypher pattern:
        MATCH (c:Character)-[:LOCATED_IN]->(l:Location {id: $location_id})
        RETURN c

    Returns a list of Character models. Returns empty list if no characters
    are at the location or if the location does not exist.
    """

async def connected_locations(client: GraphClient, location_id: str) -> list[Location]:
    """All locations connected to a given location (CONNECTS_TO, both directions).

    CONNECTS_TO is directional in the graph but semantically bidirectional.
    The query must traverse both directions. Two approaches:
      - Undirected match: MATCH (l:Location {id: $id})-[:CONNECTS_TO]-(other:Location)
      - Or UNION of both directions

    The undirected match approach is simpler and preferred.

    Returns a list of Location models. Returns empty list if no connections exist.
    """

async def scene_events(client: GraphClient, scene_id: str,
                       since_gametime: int | None = None) -> list[Event]:
    """Events in a scene, optionally filtered by gametime.

    Base Cypher:
        MATCH (s:Scene {id: $scene_id})-[:HAS_EVENT]->(e:Event)

    When since_gametime is provided, add:
        WHERE e.gametime >= $since_gametime

    Always order by gametime ascending:
        ORDER BY e.gametime ASC

    Returns a list of Event models (may include ChatMessage subtype based
    on node labels). Returns empty list if scene has no events.
    """

async def entity_graph(client: GraphClient, entity_id: str, depth: int = 1) -> dict:
    """Get an entity and its neighborhood to a given depth.

    Cypher pattern:
        MATCH (center:Entity {id: $entity_id})
        OPTIONAL MATCH path = (center)-[*1..$depth]-(neighbor:Entity)
        RETURN center, collect(DISTINCT neighbor) AS neighbors

    Returns a dict with:
        - "entity": the center Entity model
        - "related": list of Entity models within the given depth

    This is useful for building context for AI agents -- they can get
    a character and all directly related entities (location, scene,
    items, etc.) in a single query.

    Returns {"entity": None, "related": []} if the entity_id does not exist.
    """
```

### Cypher Query Construction

All query functions should use parameterized queries to prevent injection. FalkorDB supports Cypher parameters via the `params` keyword:

```python
result = await client.graph.query(
    "MATCH (c:Character)-[:LOCATED_IN]->(l:Location {id: $loc_id}) RETURN c",
    params={"loc_id": location_id}
)
```

If `graph.query` in the `falkordb` async client does not support `params` as a keyword, use string formatting with proper escaping as a fallback. Check the `falkordb` package API during implementation.

### Result Deserialization

FalkorDB query results come back as `result.result_set`, which is a list of rows. Each row is a list of values corresponding to the RETURN columns. For node returns, each value is a `Node` object with:

- `.labels` -- list of label strings (e.g., `["Entity", "Character"]`)
- `.properties` -- dict of property key-value pairs

Use the `node_to_entity` function from `entities.py` to convert each node to the appropriate Pydantic model:

```python
from sidestage.graph.entities import node_to_entity

entities = []
for row in result.result_set:
    node = row[0]  # First RETURN column
    entity = node_to_entity(node.labels, node.properties)
    entities.append(entity)
```

For `entity_graph`, the result includes both a single center node and a collected list of neighbor nodes, requiring slightly different deserialization logic.

### Error Handling

- If `graph.query()` raises an exception from FalkorDB/Redis, wrap it in `QueryError` with a descriptive message including the function name and parameters
- Functions that return lists should return empty lists (not raise) when no results match
- `entity_graph` returns `{"entity": None, "related": []}` when the center entity is not found, rather than raising `EntityNotFoundError` -- the caller can decide how to handle absence

### Import Structure

```python
from sidestage.graph.client import GraphClient
from sidestage.graph.entities import node_to_entity
from sidestage.graph.errors import QueryError
from sidestage.schemas import Character, Location, Event, Entity
```

### Module-Level Constants

No module-level constants are needed. The Cypher query strings are defined inline within each function. If query strings become long or are reused, they can be extracted to module-level string constants, but for four focused functions inline is clearer.

## Relationship to Other Sections

- **section-06-integration** will wire these query functions into `WorldTools` (for AI agent context) and `SceneLogic` (for scene event retrieval). The `entity_graph` function is particularly important for building rich context for AI agents.
- These functions are the primary read-path optimization over using raw `get_related` calls from `relationships.py`. Each function encapsulates a single efficient Cypher query rather than requiring multiple round-trips.