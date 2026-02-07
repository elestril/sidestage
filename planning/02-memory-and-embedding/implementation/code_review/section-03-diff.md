diff --git a/planning/02-memory-and-embedding/implementation/deep_implement_config.json b/planning/02-memory-and-embedding/implementation/deep_implement_config.json
index 6d6c005..147d5b2 100644
--- a/planning/02-memory-and-embedding/implementation/deep_implement_config.json
+++ b/planning/02-memory-and-embedding/implementation/deep_implement_config.json
@@ -20,6 +20,10 @@
     "section-01-models-and-health": {
       "status": "complete",
       "commit_hash": "e8e63d9"
+    },
+    "section-02-schema-migration": {
+      "status": "complete",
+      "commit_hash": "f01e78b"
     }
   },
   "pre_commit": {
diff --git a/src/sidestage/memory/__init__.py b/src/sidestage/memory/__init__.py
index 00a818f..c0a35f7 100644
--- a/src/sidestage/memory/__init__.py
+++ b/src/sidestage/memory/__init__.py
@@ -1,3 +1,19 @@
 """Sidestage memory system -- living text documents stored as graph nodes."""
 
 from sidestage.memory.models import Memory, MemoryType, ContextResult, ContextMemories
+from sidestage.memory.store import (
+    MEMORY_REL_TYPES,
+    upsert_memory,
+    upsert_scene_memory,
+    upsert_common_scene_memory,
+    upsert_character_memory,
+    upsert_world_fact,
+    get_scene_memory,
+    get_common_scene_memory,
+    get_character_memory,
+    get_memories_for_context,
+    get_all_memories,
+    delete_memory,
+    touch_memory,
+    search_similar,
+)
diff --git a/src/sidestage/memory/store.py b/src/sidestage/memory/store.py
new file mode 100644
index 0000000..e9ae4fa
--- /dev/null
+++ b/src/sidestage/memory/store.py
@@ -0,0 +1,390 @@
+"""Memory CRUD operations and vector search for FalkorDB.
+
+All Cypher for Memory nodes lives here. Does NOT use graph/entities.py
+or graph/relationships.py. Memory nodes use :Memory labels, not :Entity.
+"""
+
+from __future__ import annotations
+
+import logging
+import time
+import uuid
+from typing import TYPE_CHECKING
+
+from sidestage.memory.models import Memory, MemoryType, ContextMemories
+from sidestage.graph.errors import QueryError
+
+if TYPE_CHECKING:
+    from sidestage.graph.client import GraphClient
+
+logger = logging.getLogger(__name__)
+
+MEMORY_REL_TYPES = frozenset({"HAS_MEMORY", "ABOUT"})
+
+_TYPE_TO_SUBLABEL: dict[MemoryType, str] = {
+    MemoryType.SCENE: "SceneMemory",
+    MemoryType.CHARACTER: "CharacterMemory",
+    MemoryType.WORLD_FACT: "WorldFact",
+}
+
+
+def _node_to_memory(node) -> Memory:
+    """Convert a FalkorDB node to a Memory model."""
+    props = dict(node.properties)
+    # FalkorDB may store embedding as a special vector type; convert if needed
+    if "embedding" in props and props["embedding"] is not None:
+        props["embedding"] = list(props["embedding"])
+    return Memory(**props)
+
+
+# --- Upsert operations ---
+
+
+async def upsert_memory(
+    client: GraphClient,
+    memory_type: MemoryType,
+    visibility: str,
+    owner_id: str | None,
+    target_id: str,
+    content: str,
+    gametime: int | None = None,
+) -> Memory:
+    """Create or update a memory.
+
+    Uniqueness key: (owner_id, memory_type, target_id) for private memories,
+    or (memory_type, visibility, target_id) for common memories (owner_id is None).
+
+    Uses MERGE in Cypher. Creates HAS_MEMORY and ABOUT relationships
+    if this is a new memory. Returns the Memory object.
+    """
+    sublabel = _TYPE_TO_SUBLABEL[memory_type]
+    now = time.time()
+    mem_id = str(uuid.uuid4())
+
+    params: dict = {
+        "id": mem_id,
+        "content": content,
+        "memory_type": memory_type.value,
+        "visibility": visibility,
+        "owner_id": owner_id,
+        "target_id": target_id,
+        "now": now,
+        "gametime": gametime,
+    }
+
+    if owner_id is not None:
+        # Private memory: merge on (owner_id, memory_type, target_id)
+        cypher = (
+            f"MERGE (m:Memory:{sublabel} "
+            "{owner_id: $owner_id, memory_type: $memory_type, target_id: $target_id})\n"
+            "ON CREATE SET m.id = $id, m.created_at = $now, m.access_count = 0\n"
+            "SET m.content = $content, m.updated_at = $now, m.visibility = $visibility, m.gametime = $gametime\n"
+            "WITH m\n"
+            "OPTIONAL MATCH (owner {id: $owner_id})\n"
+            "FOREACH (_ IN CASE WHEN owner IS NOT NULL THEN [1] ELSE [] END |\n"
+            "  MERGE (owner)-[:HAS_MEMORY]->(m)\n"
+            ")\n"
+            "WITH m\n"
+            "OPTIONAL MATCH (target {id: $target_id})\n"
+            "FOREACH (_ IN CASE WHEN target IS NOT NULL THEN [1] ELSE [] END |\n"
+            "  MERGE (m)-[:ABOUT]->(target)\n"
+            ")\n"
+            "RETURN m"
+        )
+    else:
+        # Common memory: merge on (memory_type, visibility, target_id)
+        cypher = (
+            f"MERGE (m:Memory:{sublabel} "
+            "{memory_type: $memory_type, visibility: $visibility, target_id: $target_id})\n"
+            "ON CREATE SET m.id = $id, m.created_at = $now, m.access_count = 0\n"
+            "SET m.content = $content, m.updated_at = $now, m.gametime = $gametime\n"
+            "WITH m\n"
+            "OPTIONAL MATCH (target {id: $target_id})\n"
+            "FOREACH (_ IN CASE WHEN target IS NOT NULL THEN [1] ELSE [] END |\n"
+            "  MERGE (m)-[:ABOUT]->(target)\n"
+            ")\n"
+            "RETURN m"
+        )
+
+    logger.info("Upserting %s memory target_id=%s owner_id=%s", sublabel, target_id, owner_id)
+    logger.debug("Cypher: %s", cypher)
+
+    try:
+        result = await client.graph.query(cypher, params=params)
+    except Exception as exc:
+        raise QueryError(f"Failed to upsert memory: {exc}") from exc
+
+    if result.result_set:
+        return _node_to_memory(result.result_set[0][0])
+
+    # Fallback: construct from params if no node returned
+    return Memory(
+        id=mem_id,
+        content=content,
+        memory_type=memory_type,
+        visibility=visibility,
+        owner_id=owner_id,
+        target_id=target_id,
+        created_at=now,
+        updated_at=now,
+        gametime=gametime,
+        access_count=0,
+    )
+
+
+async def upsert_scene_memory(client, owner_id, scene_id, content, gametime=None) -> Memory:
+    """Upsert a character's private scene memory."""
+    return await upsert_memory(
+        client, MemoryType.SCENE, "private", owner_id, scene_id, content, gametime
+    )
+
+
+async def upsert_common_scene_memory(client, scene_id, content, gametime=None) -> Memory:
+    """Upsert the common scene memory (visibility=common, no owner)."""
+    return await upsert_memory(
+        client, MemoryType.SCENE, "common", None, scene_id, content, gametime
+    )
+
+
+async def upsert_character_memory(client, owner_id, about_character_id, content, gametime=None) -> Memory:
+    """Upsert a character's memory about another character."""
+    return await upsert_memory(
+        client, MemoryType.CHARACTER, "private", owner_id, about_character_id, content, gametime
+    )
+
+
+async def upsert_world_fact(client, about_entity_id, content, visibility="common", owner_id=None) -> Memory:
+    """Upsert a world fact. Common by default, or private to a specific character."""
+    return await upsert_memory(
+        client, MemoryType.WORLD_FACT, visibility, owner_id, about_entity_id, content
+    )
+
+
+# --- Read operations ---
+
+
+async def get_scene_memory(client, owner_id, scene_id) -> Memory | None:
+    """Get a character's private scene memory."""
+    cypher = (
+        "MATCH (m:Memory:SceneMemory {owner_id: $owner_id, memory_type: $memory_type, target_id: $scene_id})\n"
+        "RETURN m"
+    )
+    params = {"owner_id": owner_id, "memory_type": "scene", "scene_id": scene_id}
+
+    logger.debug("Getting scene memory owner=%s scene=%s", owner_id, scene_id)
+
+    try:
+        result = await client.graph.query(cypher, params=params)
+    except Exception as exc:
+        raise QueryError(f"Failed to get scene memory: {exc}") from exc
+
+    if not result.result_set:
+        return None
+    return _node_to_memory(result.result_set[0][0])
+
+
+async def get_common_scene_memory(client, scene_id) -> Memory | None:
+    """Get the common scene memory."""
+    cypher = (
+        "MATCH (m:Memory:SceneMemory {visibility: $visibility, memory_type: $memory_type, target_id: $scene_id})\n"
+        "WHERE m.owner_id IS NULL\n"
+        "RETURN m"
+    )
+    params = {"visibility": "common", "memory_type": "scene", "scene_id": scene_id}
+
+    logger.debug("Getting common scene memory scene=%s", scene_id)
+
+    try:
+        result = await client.graph.query(cypher, params=params)
+    except Exception as exc:
+        raise QueryError(f"Failed to get common scene memory: {exc}") from exc
+
+    if not result.result_set:
+        return None
+    return _node_to_memory(result.result_set[0][0])
+
+
+async def get_character_memory(client, owner_id, about_character_id) -> Memory | None:
+    """Get a character's memory about another character."""
+    cypher = (
+        "MATCH (m:Memory:CharacterMemory {owner_id: $owner_id, memory_type: $memory_type, target_id: $target_id})\n"
+        "RETURN m"
+    )
+    params = {"owner_id": owner_id, "memory_type": "character", "target_id": about_character_id}
+
+    logger.debug("Getting character memory owner=%s about=%s", owner_id, about_character_id)
+
+    try:
+        result = await client.graph.query(cypher, params=params)
+    except Exception as exc:
+        raise QueryError(f"Failed to get character memory: {exc}") from exc
+
+    if not result.result_set:
+        return None
+    return _node_to_memory(result.result_set[0][0])
+
+
+async def get_memories_for_context(
+    client: GraphClient,
+    character_id: str,
+    scene_id: str,
+    present_character_ids: list[str],
+) -> ContextMemories:
+    """Fetch all memories needed for a character's context assembly.
+
+    Uses separate queries for each memory category. Returns a ContextMemories
+    object grouping them by type.
+    """
+    # Query 1: common scene memory
+    common_scene = await get_common_scene_memory(client, scene_id)
+
+    # Query 2: private scene memory
+    private_scene = await get_scene_memory(client, character_id, scene_id)
+
+    # Query 3: character memories about present characters
+    character_memories: dict[str, Memory] = {}
+    if present_character_ids:
+        cypher = (
+            "MATCH (m:Memory:CharacterMemory {owner_id: $owner_id, memory_type: $memory_type})\n"
+            "WHERE m.target_id IN $target_ids\n"
+            "RETURN m"
+        )
+        params = {
+            "owner_id": character_id,
+            "memory_type": "character",
+            "target_ids": present_character_ids,
+        }
+        try:
+            result = await client.graph.query(cypher, params=params)
+        except Exception as exc:
+            raise QueryError(f"Failed to get character memories: {exc}") from exc
+
+        for row in result.result_set:
+            mem = _node_to_memory(row[0])
+            character_memories[mem.target_id] = mem
+
+    # Query 4: common world facts
+    wf_cypher = (
+        "MATCH (m:Memory:WorldFact {memory_type: $memory_type, visibility: $visibility})\n"
+        "RETURN m"
+    )
+    wf_params = {"memory_type": "world_fact", "visibility": "common"}
+    try:
+        wf_result = await client.graph.query(wf_cypher, params=wf_params)
+    except Exception as exc:
+        raise QueryError(f"Failed to get world facts: {exc}") from exc
+
+    world_facts = [_node_to_memory(row[0]) for row in wf_result.result_set]
+
+    return ContextMemories(
+        common_scene_memory=common_scene,
+        private_scene_memory=private_scene,
+        character_memories=character_memories,
+        world_facts=world_facts,
+    )
+
+
+async def get_all_memories(client, owner_id, memory_type=None) -> list[Memory]:
+    """Get all memories owned by a character, optionally filtered by type."""
+    if memory_type is not None:
+        cypher = (
+            "MATCH (m:Memory {owner_id: $owner_id, memory_type: $memory_type})\n"
+            "RETURN m"
+        )
+        params = {"owner_id": owner_id, "memory_type": memory_type.value if hasattr(memory_type, 'value') else memory_type}
+    else:
+        cypher = (
+            "MATCH (m:Memory {owner_id: $owner_id})\n"
+            "RETURN m"
+        )
+        params = {"owner_id": owner_id}
+
+    logger.debug("Getting all memories owner=%s type=%s", owner_id, memory_type)
+
+    try:
+        result = await client.graph.query(cypher, params=params)
+    except Exception as exc:
+        raise QueryError(f"Failed to get all memories: {exc}") from exc
+
+    return [_node_to_memory(row[0]) for row in result.result_set]
+
+
+# --- Delete and Touch ---
+
+
+async def delete_memory(client, memory_id) -> None:
+    """Delete a memory and its relationships.
+
+    Uses DETACH DELETE. Idempotent -- succeeds silently if memory_id does not exist.
+    """
+    cypher = "MATCH (m:Memory {id: $id}) DETACH DELETE m"
+
+    logger.info("Deleting memory id=%s", memory_id)
+
+    try:
+        await client.graph.query(cypher, params={"id": memory_id})
+    except Exception as exc:
+        raise QueryError(f"Failed to delete memory '{memory_id}': {exc}") from exc
+
+
+async def touch_memory(client, memory_id) -> None:
+    """Increment access_count and update last_accessed_at.
+
+    Called during context assembly. Separate from get to avoid
+    inflating counts during debugging/admin.
+    """
+    cypher = (
+        "MATCH (m:Memory {id: $id})\n"
+        "SET m.access_count = m.access_count + 1, m.last_accessed_at = $now"
+    )
+
+    logger.debug("Touching memory id=%s", memory_id)
+
+    try:
+        await client.graph.query(cypher, params={"id": memory_id, "now": time.time()})
+    except Exception as exc:
+        raise QueryError(f"Failed to touch memory '{memory_id}': {exc}") from exc
+
+
+# --- Vector search ---
+
+
+async def search_similar(
+    client: GraphClient,
+    query_embedding: list[float],
+    owner_id: str | None = None,
+    visibility: str | None = None,
+    limit: int = 10,
+) -> list[tuple[Memory, float]]:
+    """Find memories similar to query embedding.
+
+    Uses FalkorDB vector index via CALL db.idx.vector.queryNodes.
+    Post-filters by owner_id and/or visibility in the WHERE clause.
+    Returns (Memory, similarity_score) tuples ordered by score descending.
+
+    Returns empty list if the vector index does not exist or the query fails.
+    """
+    cypher = (
+        "CALL db.idx.vector.queryNodes('Memory', 'embedding', $limit, vecf32($vec))\n"
+        "YIELD node, score\n"
+        "WHERE ($owner_id IS NULL OR node.owner_id = $owner_id)\n"
+        "  AND ($visibility IS NULL OR node.visibility = $visibility)\n"
+        "RETURN node, score\n"
+        "ORDER BY score DESC"
+    )
+    params = {
+        "limit": limit,
+        "vec": query_embedding,
+        "owner_id": owner_id,
+        "visibility": visibility,
+    }
+
+    logger.debug("Searching similar memories limit=%d", limit)
+
+    try:
+        result = await client.graph.query(cypher, params=params)
+    except Exception:
+        logger.warning("Vector search failed (index may not exist), returning empty results")
+        return []
+
+    return [(_node_to_memory(row[0]), row[1]) for row in result.result_set]
diff --git a/tests/unit/test_memory_store.py b/tests/unit/test_memory_store.py
new file mode 100644
index 0000000..65c1fb7
--- /dev/null
+++ b/tests/unit/test_memory_store.py
@@ -0,0 +1,717 @@
+"""Unit tests for memory store CRUD and search operations."""
+
+import pytest
+from unittest.mock import AsyncMock, MagicMock, patch
+
+from sidestage.memory.models import Memory, MemoryType, ContextMemories
+from sidestage.memory.store import (
+    MEMORY_REL_TYPES,
+    upsert_memory,
+    upsert_scene_memory,
+    upsert_common_scene_memory,
+    upsert_character_memory,
+    upsert_world_fact,
+    get_scene_memory,
+    get_common_scene_memory,
+    get_character_memory,
+    get_memories_for_context,
+    get_all_memories,
+    delete_memory,
+    touch_memory,
+    search_similar,
+)
+from sidestage.graph.errors import QueryError
+
+
+# --- Fixtures ---
+
+
+@pytest.fixture
+def mock_client():
+    """Creates a MagicMock GraphClient with graph.query as AsyncMock."""
+    client = MagicMock()
+    client.graph = MagicMock()
+    client.graph.query = AsyncMock()
+    return client
+
+
+def _make_node_mock(properties):
+    """Helper to create a mock graph node with properties."""
+    node = MagicMock()
+    node.properties = properties
+    return node
+
+
+# --- Relationship type validation ---
+
+
+def test_memory_rel_types_contains_has_memory_and_about():
+    """MEMORY_REL_TYPES contains exactly HAS_MEMORY and ABOUT."""
+    assert MEMORY_REL_TYPES == frozenset({"HAS_MEMORY", "ABOUT"})
+
+
+# --- Upsert operations ---
+
+
+@pytest.mark.anyio
+async def test_upsert_memory_creates_new_memory_with_correct_labels(mock_client):
+    """upsert_memory creates new Memory node with correct labels (Memory:SceneMemory)."""
+    node = _make_node_mock({
+        "id": "mem-1",
+        "content": "The tavern was warm.",
+        "memory_type": "scene",
+        "visibility": "private",
+        "owner_id": "char-1",
+        "target_id": "scene-1",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    result = await upsert_memory(
+        mock_client,
+        MemoryType.SCENE,
+        "private",
+        "char-1",
+        "scene-1",
+        "The tavern was warm.",
+    )
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "Memory:SceneMemory" in cypher
+    assert "MERGE" in cypher
+    assert isinstance(result, Memory)
+
+
+@pytest.mark.anyio
+async def test_upsert_memory_creates_has_memory_and_about_for_private(mock_client):
+    """upsert_memory creates HAS_MEMORY and ABOUT relationships for private memory."""
+    node = _make_node_mock({
+        "id": "mem-1",
+        "content": "Test",
+        "memory_type": "scene",
+        "visibility": "private",
+        "owner_id": "char-1",
+        "target_id": "scene-1",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    await upsert_memory(
+        mock_client, MemoryType.SCENE, "private", "char-1", "scene-1", "Test"
+    )
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "HAS_MEMORY" in cypher
+    assert "ABOUT" in cypher
+
+
+@pytest.mark.anyio
+async def test_upsert_memory_common_skips_has_memory(mock_client):
+    """upsert_memory for common memory creates ABOUT relationship without HAS_MEMORY."""
+    node = _make_node_mock({
+        "id": "mem-1",
+        "content": "Common memory",
+        "memory_type": "scene",
+        "visibility": "common",
+        "target_id": "scene-1",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    await upsert_memory(
+        mock_client, MemoryType.SCENE, "common", None, "scene-1", "Common memory"
+    )
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "ABOUT" in cypher
+    assert "HAS_MEMORY" not in cypher
+
+
+@pytest.mark.anyio
+async def test_upsert_memory_uses_on_create_set_for_initial_fields(mock_client):
+    """upsert_memory uses ON CREATE SET for id and created_at."""
+    node = _make_node_mock({
+        "id": "mem-1",
+        "content": "Test",
+        "memory_type": "scene",
+        "visibility": "private",
+        "owner_id": "char-1",
+        "target_id": "scene-1",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    await upsert_memory(
+        mock_client, MemoryType.SCENE, "private", "char-1", "scene-1", "Test"
+    )
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "ON CREATE SET" in cypher
+
+
+@pytest.mark.anyio
+async def test_upsert_memory_preserves_id_and_created_at_on_update(mock_client):
+    """upsert_memory preserves id and created_at on update via ON CREATE SET."""
+    node = _make_node_mock({
+        "id": "mem-1",
+        "content": "Updated content",
+        "memory_type": "scene",
+        "visibility": "private",
+        "owner_id": "char-1",
+        "target_id": "scene-1",
+        "created_at": 1000.0,
+        "updated_at": 2000.0,
+        "access_count": 0,
+    })
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    await upsert_memory(
+        mock_client, MemoryType.SCENE, "private", "char-1", "scene-1", "Updated content"
+    )
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    # id and created_at should be in ON CREATE SET, not in the regular SET
+    assert "ON CREATE SET" in cypher
+    params = mock_client.graph.query.call_args[1].get("params", {})
+    assert "id" in params
+    assert "content" in params
+
+
+@pytest.mark.anyio
+async def test_upsert_scene_memory_delegates_correctly(mock_client):
+    """upsert_scene_memory creates private scene memory with correct owner_id and target_id."""
+    node = _make_node_mock({
+        "id": "mem-1",
+        "content": "Scene memory",
+        "memory_type": "scene",
+        "visibility": "private",
+        "owner_id": "char-1",
+        "target_id": "scene-1",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    result = await upsert_scene_memory(mock_client, "char-1", "scene-1", "Scene memory")
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "Memory:SceneMemory" in cypher
+    params = mock_client.graph.query.call_args[1].get("params", {})
+    assert params["owner_id"] == "char-1"
+    assert params["target_id"] == "scene-1"
+    assert isinstance(result, Memory)
+
+
+@pytest.mark.anyio
+async def test_upsert_common_scene_memory_no_owner(mock_client):
+    """upsert_common_scene_memory creates common scene memory with owner_id=None."""
+    node = _make_node_mock({
+        "id": "mem-1",
+        "content": "Common scene",
+        "memory_type": "scene",
+        "visibility": "common",
+        "target_id": "scene-1",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    result = await upsert_common_scene_memory(mock_client, "scene-1", "Common scene")
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "HAS_MEMORY" not in cypher
+    assert isinstance(result, Memory)
+
+
+@pytest.mark.anyio
+async def test_upsert_character_memory(mock_client):
+    """upsert_character_memory creates private character memory."""
+    node = _make_node_mock({
+        "id": "mem-1",
+        "content": "Alice is brave",
+        "memory_type": "character",
+        "visibility": "private",
+        "owner_id": "char-1",
+        "target_id": "char-2",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    result = await upsert_character_memory(
+        mock_client, "char-1", "char-2", "Alice is brave"
+    )
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "Memory:CharacterMemory" in cypher
+    assert isinstance(result, Memory)
+
+
+@pytest.mark.anyio
+async def test_upsert_world_fact_common(mock_client):
+    """upsert_world_fact with visibility='common' creates common world fact."""
+    node = _make_node_mock({
+        "id": "mem-1",
+        "content": "The sun is a star",
+        "memory_type": "world_fact",
+        "visibility": "common",
+        "target_id": "entity-1",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    result = await upsert_world_fact(
+        mock_client, "entity-1", "The sun is a star", visibility="common"
+    )
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "Memory:WorldFact" in cypher
+    assert isinstance(result, Memory)
+
+
+@pytest.mark.anyio
+async def test_upsert_world_fact_private(mock_client):
+    """upsert_world_fact with visibility='private' creates private world fact with owner."""
+    node = _make_node_mock({
+        "id": "mem-1",
+        "content": "Secret knowledge",
+        "memory_type": "world_fact",
+        "visibility": "private",
+        "owner_id": "char-1",
+        "target_id": "entity-1",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    result = await upsert_world_fact(
+        mock_client, "entity-1", "Secret knowledge", visibility="private", owner_id="char-1"
+    )
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "HAS_MEMORY" in cypher
+    assert isinstance(result, Memory)
+
+
+# --- Read operations ---
+
+
+@pytest.mark.anyio
+async def test_get_scene_memory_returns_memory(mock_client):
+    """get_scene_memory returns memory for matching owner_id + scene_id."""
+    node = _make_node_mock({
+        "id": "mem-1",
+        "content": "Scene content",
+        "memory_type": "scene",
+        "visibility": "private",
+        "owner_id": "char-1",
+        "target_id": "scene-1",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    result = await get_scene_memory(mock_client, "char-1", "scene-1")
+
+    assert isinstance(result, Memory)
+    assert result.content == "Scene content"
+
+
+@pytest.mark.anyio
+async def test_get_scene_memory_returns_none(mock_client):
+    """get_scene_memory returns None when no memory exists."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    result = await get_scene_memory(mock_client, "char-1", "scene-1")
+
+    assert result is None
+
+
+@pytest.mark.anyio
+async def test_get_common_scene_memory(mock_client):
+    """get_common_scene_memory returns common scene memory."""
+    node = _make_node_mock({
+        "id": "mem-1",
+        "content": "Common scene content",
+        "memory_type": "scene",
+        "visibility": "common",
+        "target_id": "scene-1",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    result = await get_common_scene_memory(mock_client, "scene-1")
+
+    assert isinstance(result, Memory)
+    assert result.visibility == "common"
+
+
+@pytest.mark.anyio
+async def test_get_character_memory_returns_memory(mock_client):
+    """get_character_memory returns memory for matching owner + about_character."""
+    node = _make_node_mock({
+        "id": "mem-1",
+        "content": "Alice is brave",
+        "memory_type": "character",
+        "visibility": "private",
+        "owner_id": "char-1",
+        "target_id": "char-2",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    result = await get_character_memory(mock_client, "char-1", "char-2")
+
+    assert isinstance(result, Memory)
+    assert result.content == "Alice is brave"
+
+
+@pytest.mark.anyio
+async def test_get_character_memory_returns_none(mock_client):
+    """get_character_memory returns None for non-existent pair."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    result = await get_character_memory(mock_client, "char-1", "char-2")
+
+    assert result is None
+
+
+@pytest.mark.anyio
+async def test_get_memories_for_context_returns_context_memories(mock_client):
+    """get_memories_for_context returns all applicable memories."""
+    # Common scene memory query
+    common_node = _make_node_mock({
+        "id": "mem-common",
+        "content": "Common scene",
+        "memory_type": "scene",
+        "visibility": "common",
+        "target_id": "scene-1",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+    # Private scene memory query
+    private_node = _make_node_mock({
+        "id": "mem-private",
+        "content": "Private scene",
+        "memory_type": "scene",
+        "visibility": "private",
+        "owner_id": "char-1",
+        "target_id": "scene-1",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+    # Character memory query
+    char_node = _make_node_mock({
+        "id": "mem-char",
+        "content": "About char-2",
+        "memory_type": "character",
+        "visibility": "private",
+        "owner_id": "char-1",
+        "target_id": "char-2",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+
+    # Mock sequential queries: common scene, private scene, character memories, world facts
+    mock_client.graph.query.side_effect = [
+        MagicMock(result_set=[[common_node]]),
+        MagicMock(result_set=[[private_node]]),
+        MagicMock(result_set=[[char_node]]),
+        MagicMock(result_set=[]),  # world facts
+    ]
+
+    result = await get_memories_for_context(
+        mock_client, "char-1", "scene-1", ["char-2"]
+    )
+
+    assert isinstance(result, ContextMemories)
+    assert result.common_scene_memory is not None
+    assert result.private_scene_memory is not None
+    assert "char-2" in result.character_memories
+
+
+@pytest.mark.anyio
+async def test_get_memories_for_context_common_only(mock_client):
+    """get_memories_for_context returns common memories even with no private memories."""
+    common_node = _make_node_mock({
+        "id": "mem-common",
+        "content": "Common",
+        "memory_type": "scene",
+        "visibility": "common",
+        "target_id": "scene-1",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+
+    mock_client.graph.query.side_effect = [
+        MagicMock(result_set=[[common_node]]),
+        MagicMock(result_set=[]),  # no private scene memory
+        MagicMock(result_set=[]),  # no character memories
+        MagicMock(result_set=[]),  # no world facts
+    ]
+
+    result = await get_memories_for_context(
+        mock_client, "char-1", "scene-1", []
+    )
+
+    assert result.common_scene_memory is not None
+    assert result.private_scene_memory is None
+    assert result.character_memories == {}
+
+
+@pytest.mark.anyio
+async def test_get_memories_for_context_world_facts(mock_client):
+    """get_memories_for_context returns world facts."""
+    wf_node = _make_node_mock({
+        "id": "wf-1",
+        "content": "The world is round",
+        "memory_type": "world_fact",
+        "visibility": "common",
+        "target_id": "entity-1",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+
+    # With empty present_character_ids, character memory query is skipped (3 queries total)
+    mock_client.graph.query.side_effect = [
+        MagicMock(result_set=[]),  # no common scene
+        MagicMock(result_set=[]),  # no private scene
+        MagicMock(result_set=[[wf_node]]),  # world facts
+    ]
+
+    result = await get_memories_for_context(
+        mock_client, "char-1", "scene-1", []
+    )
+
+    assert len(result.world_facts) == 1
+    assert result.world_facts[0].content == "The world is round"
+
+
+@pytest.mark.anyio
+async def test_get_all_memories_returns_all(mock_client):
+    """get_all_memories returns all memories for an owner."""
+    node1 = _make_node_mock({
+        "id": "mem-1",
+        "content": "Memory 1",
+        "memory_type": "scene",
+        "visibility": "private",
+        "owner_id": "char-1",
+        "target_id": "scene-1",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+    node2 = _make_node_mock({
+        "id": "mem-2",
+        "content": "Memory 2",
+        "memory_type": "character",
+        "visibility": "private",
+        "owner_id": "char-1",
+        "target_id": "char-2",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node1], [node2]])
+
+    result = await get_all_memories(mock_client, "char-1")
+
+    assert len(result) == 2
+
+
+@pytest.mark.anyio
+async def test_get_all_memories_filters_by_type(mock_client):
+    """get_all_memories filters by memory_type when specified."""
+    node = _make_node_mock({
+        "id": "mem-1",
+        "content": "Scene memory",
+        "memory_type": "scene",
+        "visibility": "private",
+        "owner_id": "char-1",
+        "target_id": "scene-1",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    result = await get_all_memories(mock_client, "char-1", memory_type=MemoryType.SCENE)
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "memory_type" in cypher
+    assert len(result) == 1
+
+
+# --- Delete / Touch ---
+
+
+@pytest.mark.anyio
+async def test_delete_memory_uses_detach_delete(mock_client):
+    """delete_memory removes node and all relationships."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    await delete_memory(mock_client, "mem-1")
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "DETACH DELETE" in cypher
+
+
+@pytest.mark.anyio
+async def test_delete_memory_noop_for_nonexistent(mock_client):
+    """delete_memory is no-op for non-existent id."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    # Should not raise
+    await delete_memory(mock_client, "nonexistent")
+
+
+@pytest.mark.anyio
+async def test_touch_memory_increments_access_count(mock_client):
+    """touch_memory increments access_count."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    await touch_memory(mock_client, "mem-1")
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "access_count" in cypher
+    assert "access_count + 1" in cypher
+
+
+@pytest.mark.anyio
+async def test_touch_memory_updates_last_accessed_at(mock_client):
+    """touch_memory updates last_accessed_at."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    await touch_memory(mock_client, "mem-1")
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "last_accessed_at" in cypher
+
+
+# --- Vector search ---
+
+
+@pytest.mark.anyio
+async def test_search_similar_returns_memories_ordered_by_score(mock_client):
+    """search_similar returns memories ordered by score."""
+    node1 = _make_node_mock({
+        "id": "mem-1",
+        "content": "Similar 1",
+        "memory_type": "scene",
+        "visibility": "private",
+        "owner_id": "char-1",
+        "target_id": "scene-1",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+    node2 = _make_node_mock({
+        "id": "mem-2",
+        "content": "Similar 2",
+        "memory_type": "scene",
+        "visibility": "private",
+        "owner_id": "char-1",
+        "target_id": "scene-2",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+    mock_client.graph.query.return_value = MagicMock(
+        result_set=[[node1, 0.95], [node2, 0.80]]
+    )
+
+    result = await search_similar(mock_client, [0.1, 0.2, 0.3])
+
+    assert len(result) == 2
+    assert result[0][1] >= result[1][1]  # Ordered by score
+
+
+@pytest.mark.anyio
+async def test_search_similar_filters_by_owner_id(mock_client):
+    """search_similar post-filters by owner_id when specified."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    await search_similar(mock_client, [0.1, 0.2], owner_id="char-1")
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "owner_id" in cypher
+
+
+@pytest.mark.anyio
+async def test_search_similar_filters_by_visibility(mock_client):
+    """search_similar post-filters by visibility when specified."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    await search_similar(mock_client, [0.1, 0.2], visibility="common")
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "visibility" in cypher
+
+
+@pytest.mark.anyio
+async def test_search_similar_returns_empty_on_no_index(mock_client):
+    """search_similar returns empty list when no vector index exists."""
+    mock_client.graph.query.side_effect = Exception("index does not exist")
+
+    result = await search_similar(mock_client, [0.1, 0.2])
+
+    assert result == []
+
+
+# --- Cypher safety ---
+
+
+@pytest.mark.anyio
+async def test_store_uses_parameterized_queries(mock_client):
+    """store uses parameterized queries (no string interpolation of user values)."""
+    node = _make_node_mock({
+        "id": "mem-1",
+        "content": "Test",
+        "memory_type": "scene",
+        "visibility": "private",
+        "owner_id": "char-1",
+        "target_id": "scene-1",
+        "created_at": 1000.0,
+        "updated_at": 1000.0,
+        "access_count": 0,
+    })
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    await upsert_memory(
+        mock_client, MemoryType.SCENE, "private", "char-1", "scene-1", "Test"
+    )
+
+    call_args = mock_client.graph.query.call_args
+    cypher = call_args[0][0]
+    params = call_args[1].get("params", {})
+    # User values should be in params, not interpolated in cypher
+    assert "$content" in cypher
+    assert "$owner_id" in cypher
+    assert "$target_id" in cypher
+    assert "content" in params
+    assert "owner_id" in params
+    assert "target_id" in params
