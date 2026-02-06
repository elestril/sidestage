# TDD Plan: FalkorDB Foundation

## Testing Context

**Framework:** pytest with pytest-anyio for async tests
**Mocking:** unittest.mock (AsyncMock, MagicMock, patch)
**Fixtures:** Use `tmp_path` for file-based isolation, custom fixtures for GraphClient mocking
**Async pattern:** `@pytest.mark.anyio` decorator on all async test functions
**Test location:** `tests/unit/test_graph_*.py` for unit tests, `tests/integration/test_graph_*.py` for integration tests

---

## 1. Project Context

No tests needed - this is background context for the plan.

---

## 2. Module Structure

No tests needed - this is about file organization.

---

## 3. Connection Management (`client.py`)

### Tests: `tests/unit/test_graph_client.py`

```python
# Test: connect() creates a BlockingConnectionPool with configured max_connections
# Test: connect() selects graph with the correct graph_name from config
# Test: connect() derives graph_name from campaign name when not specified
# Test: connect() sanitizes campaign name for graph_name (lowercase, no special chars)
# Test: connect() calls schema initialization after connection
# Test: close() closes the connection pool
# Test: connect() raises ConnectionError when FalkorDB host is unreachable
# Test: connect() with custom host/port/password uses those values
# Test: GraphConfig defaults (host=localhost, port=6379, max_connections=16)
```

---

## 4. Schema Design & Initialization (`schema.py`)

### Tests: `tests/unit/test_graph_schema.py`

```python
# Test: initialize_schema creates all expected indexes on fresh graph
# Test: initialize_schema creates all expected constraints on fresh graph
# Test: initialize_schema creates SchemaVersion node at version 1
# Test: initialize_schema is idempotent (calling twice doesn't error)
# Test: initialize_schema detects existing version and skips if current
# Test: initialize_schema runs migrations when version is behind
# Test: initialize_schema updates SchemaVersion node after migration
# Test: initialize_schema raises SchemaError on migration failure
# Test: get_schema_version returns None for fresh graph (no SchemaVersion node)
# Test: get_schema_version returns version number for initialized graph
# Test: index creation order (indexes before constraints, since unique constraints need indexes)
```

---

## 5. Entity Operations (`entities.py`)

### Tests: `tests/unit/test_graph_entities.py`

```python
# --- Create ---
# Test: create_entity with Character creates node with :Entity:Character labels
# Test: create_entity with Location creates node with :Entity:Location labels
# Test: create_entity with Item creates node with :Entity:Item labels
# Test: create_entity with Scene creates node with :Entity:Scene labels
# Test: create_entity with Event creates node with :Entity:Event labels
# Test: create_entity with ChatMessage creates node with :Entity:Event:ChatMessage labels
# Test: create_entity stores all scalar properties on the node
# Test: create_entity stores array properties (inventory) on Character node
# Test: create_entity does NOT store excluded fields (connected_locations, messages)
# Test: create_entity raises DuplicateEntityError if entity id already exists

# --- Get ---
# Test: get_entity returns correct entity by id
# Test: get_entity returns None for non-existent id
# Test: get_entity reconstructs correct Pydantic model type from node labels
# Test: get_entity for Character includes all Character-specific fields
# Test: get_entity for ChatMessage (multi-label) reconstructs as ChatMessage not Event

# --- Update ---
# Test: update_entity modifies specified properties
# Test: update_entity does not modify unspecified properties
# Test: update_entity raises EntityNotFoundError for non-existent id
# Test: update_entity returns updated entity

# --- Delete ---
# Test: delete_entity removes node from graph
# Test: delete_entity removes all relationships (DETACH DELETE)
# Test: delete_entity raises EntityNotFoundError for non-existent id (or silently succeeds)

# --- List ---
# Test: list_entities returns all entities when no type filter
# Test: list_entities with type filter returns only matching type
# Test: list_entities returns empty list for type with no entities

# --- Find ---
# Test: find_entities with name filter returns matching entities
# Test: find_entities with multiple filters applies AND logic
# Test: find_entities returns empty list when no matches
```

### Tests: `tests/unit/test_graph_serialization.py`

```python
# Test: entity_to_properties converts Character fields to property dict
# Test: entity_to_properties excludes fields in exclusion list
# Test: entity_to_properties handles None optional fields
# Test: entity_to_labels returns ["Entity", "Character"] for Character
# Test: entity_to_labels returns ["Entity", "Event", "ChatMessage"] for ChatMessage
# Test: node_to_entity reconstructs Character from labels + properties
# Test: node_to_entity picks most specific model (ChatMessage over Event)
# Test: LABEL_TO_MODEL registry contains all entity types
```

---

## 6. Relationship Operations (`relationships.py`)

### Tests: `tests/unit/test_graph_relationships.py`

```python
# --- Link ---
# Test: link creates typed edge between two entities
# Test: link with properties stores properties on edge
# Test: link raises EntityNotFoundError if source doesn't exist
# Test: link raises EntityNotFoundError if target doesn't exist

# --- Unlink ---
# Test: unlink removes edge between two entities
# Test: unlink is idempotent (no error if edge doesn't exist)

# --- Get Related ---
# Test: get_related returns outgoing related entities
# Test: get_related returns incoming related entities
# Test: get_related with direction="both" returns all related
# Test: get_related returns empty list when no relationships
# Test: get_related with CONNECTS_TO and direction="both" finds bidirectional connections

# --- Get Relationships ---
# Test: get_relationships returns all relationships for an entity
# Test: get_relationships includes rel_type, direction, target info
# Test: get_relationships returns empty list for entity with no relationships
```

---

## 7. Graph Queries (`queries.py`)

### Tests: `tests/unit/test_graph_queries.py`

```python
# Test: characters_at_location returns characters LOCATED_IN the given location
# Test: characters_at_location returns empty list for empty location
# Test: connected_locations returns all CONNECTS_TO locations (both directions)
# Test: scene_events returns all events in a scene via HAS_EVENT
# Test: scene_events with since_gametime filters by gametime
# Test: entity_graph at depth=1 returns entity and directly connected entities
# Test: entity_graph at depth=2 returns two levels of connections
```

---

## 8. Error Handling (`errors.py`)

### Tests: `tests/unit/test_graph_errors.py`

```python
# Test: GraphError is base class for all graph exceptions
# Test: ConnectionError is a subclass of GraphError
# Test: EntityNotFoundError is a subclass of GraphError
# Test: DuplicateEntityError is a subclass of GraphError
# Test: SchemaError is a subclass of GraphError
# Test: QueryError is a subclass of GraphError
# Test: All error types can carry a message
```

---

## 9. Integration with Existing Code

### Tests: `tests/integration/test_graph_integration.py`

```python
# Test: Campaign can create a GraphClient on startup
# Test: Campaign entity creation flows through graph module
# Test: Campaign entity retrieval flows through graph module
# Test: Campaign entity update flows through graph module
# Test: Campaign entity deletion flows through graph module
# Test: Campaign shutdown closes GraphClient
# Test: SceneLogic can create scene entities via graph module
# Test: WorldTools entity queries use graph module
```

**Note:** Integration tests require a running FalkorDB instance. These may be skipped in CI without FalkorDB, or use Docker containers.

---

## 10. Dependencies

No tests needed - this is about pyproject.toml changes.

---

## 11. Implementation Order

No tests needed - this is about sequencing.

---

## 12. Key Design Decisions Summary

No tests needed - this is a reference table.
