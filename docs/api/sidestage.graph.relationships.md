# `sidestage.graph.relationships`

Relationship (edge) operations for FalkorDB graph.

Provides async functions for creating, removing, and querying
relationships between entity nodes.

## Functions

### `get_related(client: GraphClient, entity_id: str, rel_type: str, direction: str = 'outgoing') -> list[Entity]` *async*

Get entities related via a specific relationship type.

Args:
    client: The graph client.
    entity_id: ID of the source entity.
    rel_type: The relationship type to traverse.
    direction: "outgoing", "incoming", or "both".

Returns:
    List of deserialized Entity (or subclass) objects.

### `get_relationships(client: GraphClient, entity_id: str) -> list[dict[str, Any]]` *async*

Get all relationships for an entity.

Returns list of dicts, each containing:
    - rel_type: str
    - direction: str ("outgoing" or "incoming")
    - target_id: str
    - target_name: str
    - properties: dict

### `link(client: GraphClient, source_id: str, rel_type: str, target_id: str, properties: dict[str, Any] | None = None) -> None` *async*

Create a relationship between two entities.

Matches source and target by :Entity id property, creates a typed edge.
Optional properties dict for edge metadata (stored on the edge).

Raises EntityNotFoundError if source or target entity does not exist.
Raises QueryError if the Cypher query fails.

### `unlink(client: GraphClient, source_id: str, rel_type: str, target_id: str) -> None` *async*

Remove a relationship between two entities.

Idempotent: does not raise if the edge does not exist.
