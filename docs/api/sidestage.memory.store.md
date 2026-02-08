# `sidestage.memory.store`

Memory CRUD operations and vector search for FalkorDB.

All Cypher for Memory nodes lives here. Does NOT use graph/entities.py
or graph/relationships.py. Memory nodes use :Memory labels, not :Entity.

## Functions

### `delete_memory(client: GraphClient, memory_id: str) -> None` *async*

Delete a memory and its relationships.

Uses DETACH DELETE. Idempotent -- succeeds silently if memory_id does not exist.

### `get_all_memories(client: GraphClient, owner_id: str, memory_type: MemoryType | None = None) -> list[Memory]` *async*

Get all memories owned by a character, optionally filtered by type.

### `get_character_memory(client: GraphClient, owner_id: str, about_character_id: str) -> Memory | None` *async*

Get a character's memory about another character.

### `get_common_scene_memory(client: GraphClient, scene_id: str) -> Memory | None` *async*

Get the common scene memory.

### `get_memories_for_context(client: GraphClient, character_id: str, scene_id: str, present_character_ids: list[str]) -> ContextMemories` *async*

Fetch all memories needed for a character's context assembly.

Uses separate queries for each memory category. Returns a ContextMemories
object grouping them by type.

### `get_scene_memory(client: GraphClient, owner_id: str, scene_id: str) -> Memory | None` *async*

Get a character's private scene memory.

### `search_similar(client: GraphClient, query_embedding: list[float], owner_id: str | None = None, visibility: str | None = None, limit: int = 10) -> list[tuple[Memory, float]]` *async*

Find memories similar to query embedding.

Uses FalkorDB vector index via CALL db.idx.vector.queryNodes.
Post-filters by owner_id and/or visibility in the WHERE clause.
Returns (Memory, similarity_score) tuples ordered by score descending.

Returns empty list if the vector index does not exist or the query fails.

### `touch_memory(client: GraphClient, memory_id: str) -> None` *async*

Increment access_count and update last_accessed_at.

Called during context assembly. Separate from get to avoid
inflating counts during debugging/admin.

### `upsert_character_memory(client: GraphClient, owner_id: str, about_character_id: str, content: str, gametime: int | None = None) -> Memory` *async*

Upsert a character's memory about another character.

### `upsert_common_scene_memory(client: GraphClient, scene_id: str, content: str, gametime: int | None = None) -> Memory` *async*

Upsert the common scene memory (visibility=common, no owner).

### `upsert_memory(client: GraphClient, memory_type: MemoryType, visibility: str, owner_id: str | None, target_id: str, content: str, gametime: int | None = None) -> Memory` *async*

Create or update a memory.

Uniqueness key: (owner_id, memory_type, target_id) for private memories,
or (memory_type, visibility, target_id) for common memories (owner_id is None).

Uses MERGE in Cypher. Creates HAS_MEMORY and ABOUT relationships
if this is a new memory. Returns the Memory object.

### `upsert_scene_memory(client: GraphClient, owner_id: str, scene_id: str, content: str, gametime: int | None = None) -> Memory` *async*

Upsert a character's private scene memory.

### `upsert_world_fact(client: GraphClient, about_entity_id: str, content: str, visibility: str = 'common', owner_id: str | None = None) -> Memory` *async*

Upsert a world fact. Common by default, or private to a specific character.
