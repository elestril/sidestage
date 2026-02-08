# `sidestage.graph.entities`

Entity CRUD operations and serialization logic for FalkorDB graph nodes.

Provides async functions for creating, retrieving, updating, deleting,
listing, and querying entity nodes. Maps between Pydantic entity models
and FalkorDB graph node properties.

## Functions

### `create_entity(client: GraphClient, entity: Entity) -> Entity` *async*

Create a new entity node in the graph.

Raises DuplicateEntityError on unique constraint violation.
Raises QueryError on other failures.

### `delete_entity(client: GraphClient, entity_id: str) -> None` *async*

Delete an entity and all its relationships.

Succeeds silently if the entity does not exist.

### `entity_to_labels(entity: Entity) -> list[str]`

Return the FalkorDB labels for an entity instance.

### `entity_to_properties(entity: Entity) -> dict[str, Any]`

Convert a Pydantic entity to a dict of graph node properties.

Excludes fields listed in EXCLUDED_FIELDS for the entity type,
and omits None values.

### `find_entities(client: GraphClient, filters: Any) -> list[Entity]` *async*

Find entities matching all given property filters.

### `get_entity(client: GraphClient, entity_id: str) -> Entity | None` *async*

Retrieve an entity by ID, or None if not found.

### `list_entities(client: GraphClient, entity_type: str | None = None) -> list[Entity]` *async*

List all entities, optionally filtered by type label.

The entity_type string is validated against known labels.

### `node_to_entity(labels: list[str], properties: dict[str, Any]) -> Entity`

Reconstruct a Pydantic entity from graph node labels and properties.

Iterates LABEL_TO_MODEL in specificity order (most-specific first)
and picks the first matching label.

Raises QueryError if no matching label is found.

### `update_entity(client: GraphClient, entity_id: str, updates: dict[str, Any]) -> Entity` *async*

Update specified properties on an entity node.

Raises EntityNotFoundError if the entity does not exist.
Raises QueryError if update keys are invalid.
Returns the updated entity.
