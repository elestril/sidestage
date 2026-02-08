# `sidestage.graph.queries`

Higher-level graph query functions for common traversal patterns.

Provides specialized, efficient Cypher-based query functions that combine
entity and relationship operations into single graph traversals.

## Functions

### `characters_at_location(client: GraphClient, location_id: str) -> list[Character]` *async*

All characters currently at a location (via LOCATED_IN).

Returns a list of Character models. Returns empty list if no characters
are at the location or if the location does not exist.

### `connected_locations(client: GraphClient, location_id: str) -> list[Location]` *async*

All locations connected to a given location (CONNECTS_TO, both directions).

Uses undirected match since CONNECTS_TO is semantically bidirectional.
Returns a list of Location models. Returns empty list if no connections exist.

### `entity_graph(client: GraphClient, entity_id: str, depth: int = 1) -> dict[str, Any]` *async*

Get an entity and its neighborhood to a given depth.

Returns a dict with:
    - "entity": the center Entity model (or None if not found)
    - "related": list of Entity models within the given depth

### `scene_events(client: GraphClient, scene_id: str, since_gametime: int | None = None) -> list[Event]` *async*

Events in a scene, optionally filtered by gametime.

Returns a list of Event models (may include ChatMessage subtype based
on node labels). Returns empty list if scene has no events.
Always ordered by gametime ascending.
