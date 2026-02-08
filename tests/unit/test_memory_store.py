"""Unit tests for memory store CRUD and search operations."""

from typing import Any

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sidestage.memory.models import Memory, MemoryType, ContextMemories
from sidestage.memory.store import (
    MEMORY_REL_TYPES,
    upsert_memory,
    upsert_scene_memory,
    upsert_common_scene_memory,
    upsert_character_memory,
    upsert_world_fact,
    get_scene_memory,
    get_common_scene_memory,
    get_character_memory,
    get_memories_for_context,
    get_all_memories,
    delete_memory,
    touch_memory,
    search_similar,
)
from sidestage.graph.errors import QueryError


# --- Fixtures ---


@pytest.fixture
def mock_client() -> MagicMock:
    """Creates a MagicMock GraphClient with graph.query as AsyncMock."""
    client = MagicMock()
    client.graph = MagicMock()
    client.graph.query = AsyncMock()
    return client


def _make_node_mock(properties: dict[str, Any]) -> MagicMock:
    """Helper to create a mock graph node with properties."""
    node = MagicMock()
    node.properties = properties
    return node


# --- Relationship type validation ---


def test_memory_rel_types_contains_has_memory_and_about():
    """MEMORY_REL_TYPES contains exactly HAS_MEMORY and ABOUT."""
    assert MEMORY_REL_TYPES == frozenset({"HAS_MEMORY", "ABOUT"})


# --- Upsert operations ---


@pytest.mark.anyio
async def test_upsert_memory_creates_new_memory_with_correct_labels(mock_client: MagicMock) -> None:
    """upsert_memory creates new Memory node with correct labels (Memory:SceneMemory)."""
    node = _make_node_mock({
        "id": "mem-1",
        "content": "The tavern was warm.",
        "memory_type": "scene",
        "visibility": "private",
        "owner_id": "char-1",
        "target_id": "scene-1",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    result = await upsert_memory(
        mock_client,
        MemoryType.SCENE,
        "private",
        "char-1",
        "scene-1",
        "The tavern was warm.",
    )

    cypher = mock_client.graph.query.call_args[0][0]
    assert "Memory:SceneMemory" in cypher
    assert "MERGE" in cypher
    assert isinstance(result, Memory)


@pytest.mark.anyio
async def test_upsert_memory_creates_has_memory_and_about_for_private(mock_client: MagicMock) -> None:
    """upsert_memory creates HAS_MEMORY and ABOUT relationships for private memory."""
    node = _make_node_mock({
        "id": "mem-1",
        "content": "Test",
        "memory_type": "scene",
        "visibility": "private",
        "owner_id": "char-1",
        "target_id": "scene-1",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    await upsert_memory(
        mock_client, MemoryType.SCENE, "private", "char-1", "scene-1", "Test"
    )

    cypher = mock_client.graph.query.call_args[0][0]
    assert "HAS_MEMORY" in cypher
    assert "ABOUT" in cypher


@pytest.mark.anyio
async def test_upsert_memory_common_skips_has_memory(mock_client: MagicMock) -> None:
    """upsert_memory for common memory creates ABOUT relationship without HAS_MEMORY."""
    node = _make_node_mock({
        "id": "mem-1",
        "content": "Common memory",
        "memory_type": "scene",
        "visibility": "common",
        "target_id": "scene-1",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    await upsert_memory(
        mock_client, MemoryType.SCENE, "common", None, "scene-1", "Common memory"
    )

    cypher = mock_client.graph.query.call_args[0][0]
    assert "ABOUT" in cypher
    assert "HAS_MEMORY" not in cypher


@pytest.mark.anyio
async def test_upsert_memory_uses_on_create_set_for_initial_fields(mock_client: MagicMock) -> None:
    """upsert_memory uses ON CREATE SET for id and created_at."""
    node = _make_node_mock({
        "id": "mem-1",
        "content": "Test",
        "memory_type": "scene",
        "visibility": "private",
        "owner_id": "char-1",
        "target_id": "scene-1",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    await upsert_memory(
        mock_client, MemoryType.SCENE, "private", "char-1", "scene-1", "Test"
    )

    cypher = mock_client.graph.query.call_args[0][0]
    assert "ON CREATE SET" in cypher


@pytest.mark.anyio
async def test_upsert_memory_preserves_id_and_created_at_on_update(mock_client: MagicMock) -> None:
    """upsert_memory preserves id and created_at on update via ON CREATE SET."""
    node = _make_node_mock({
        "id": "mem-1",
        "content": "Updated content",
        "memory_type": "scene",
        "visibility": "private",
        "owner_id": "char-1",
        "target_id": "scene-1",
        "created_at": 1000.0,
        "updated_at": 2000.0,
        "access_count": 0,
    })
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    await upsert_memory(
        mock_client, MemoryType.SCENE, "private", "char-1", "scene-1", "Updated content"
    )

    cypher = mock_client.graph.query.call_args[0][0]
    # id and created_at should be in ON CREATE SET, not in the regular SET
    assert "ON CREATE SET" in cypher
    params = mock_client.graph.query.call_args[1].get("params", {})
    assert "id" in params
    assert "content" in params


@pytest.mark.anyio
async def test_upsert_scene_memory_delegates_correctly(mock_client: MagicMock) -> None:
    """upsert_scene_memory creates private scene memory with correct owner_id and target_id."""
    node = _make_node_mock({
        "id": "mem-1",
        "content": "SceneModel memory",
        "memory_type": "scene",
        "visibility": "private",
        "owner_id": "char-1",
        "target_id": "scene-1",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    result = await upsert_scene_memory(mock_client, "char-1", "scene-1", "SceneModel memory")

    cypher = mock_client.graph.query.call_args[0][0]
    assert "Memory:SceneMemory" in cypher
    params = mock_client.graph.query.call_args[1].get("params", {})
    assert params["owner_id"] == "char-1"
    assert params["target_id"] == "scene-1"
    assert isinstance(result, Memory)


@pytest.mark.anyio
async def test_upsert_common_scene_memory_no_owner(mock_client: MagicMock) -> None:
    """upsert_common_scene_memory creates common scene memory with owner_id=None."""
    node = _make_node_mock({
        "id": "mem-1",
        "content": "Common scene",
        "memory_type": "scene",
        "visibility": "common",
        "target_id": "scene-1",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    result = await upsert_common_scene_memory(mock_client, "scene-1", "Common scene")

    cypher = mock_client.graph.query.call_args[0][0]
    assert "HAS_MEMORY" not in cypher
    assert isinstance(result, Memory)


@pytest.mark.anyio
async def test_upsert_character_memory(mock_client: MagicMock) -> None:
    """upsert_character_memory creates private character memory."""
    node = _make_node_mock({
        "id": "mem-1",
        "content": "Alice is brave",
        "memory_type": "character",
        "visibility": "private",
        "owner_id": "char-1",
        "target_id": "char-2",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    result = await upsert_character_memory(
        mock_client, "char-1", "char-2", "Alice is brave"
    )

    cypher = mock_client.graph.query.call_args[0][0]
    assert "Memory:CharacterMemory" in cypher
    assert isinstance(result, Memory)


@pytest.mark.anyio
async def test_upsert_world_fact_common(mock_client: MagicMock) -> None:
    """upsert_world_fact with visibility='common' creates common world fact."""
    node = _make_node_mock({
        "id": "mem-1",
        "content": "The sun is a star",
        "memory_type": "world_fact",
        "visibility": "common",
        "target_id": "entity-1",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    result = await upsert_world_fact(
        mock_client, "entity-1", "The sun is a star", visibility="common"
    )

    cypher = mock_client.graph.query.call_args[0][0]
    assert "Memory:WorldFact" in cypher
    assert isinstance(result, Memory)


@pytest.mark.anyio
async def test_upsert_world_fact_private(mock_client: MagicMock) -> None:
    """upsert_world_fact with visibility='private' creates private world fact with owner."""
    node = _make_node_mock({
        "id": "mem-1",
        "content": "Secret knowledge",
        "memory_type": "world_fact",
        "visibility": "private",
        "owner_id": "char-1",
        "target_id": "entity-1",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    result = await upsert_world_fact(
        mock_client, "entity-1", "Secret knowledge", visibility="private", owner_id="char-1"
    )

    cypher = mock_client.graph.query.call_args[0][0]
    assert "HAS_MEMORY" in cypher
    assert isinstance(result, Memory)


# --- Read operations ---


@pytest.mark.anyio
async def test_get_scene_memory_returns_memory(mock_client: MagicMock) -> None:
    """get_scene_memory returns memory for matching owner_id + scene_id."""
    node = _make_node_mock({
        "id": "mem-1",
        "content": "SceneModel content",
        "memory_type": "scene",
        "visibility": "private",
        "owner_id": "char-1",
        "target_id": "scene-1",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    result = await get_scene_memory(mock_client, "char-1", "scene-1")

    assert isinstance(result, Memory)
    assert result.content == "SceneModel content"


@pytest.mark.anyio
async def test_get_scene_memory_returns_none(mock_client: MagicMock) -> None:
    """get_scene_memory returns None when no memory exists."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    result = await get_scene_memory(mock_client, "char-1", "scene-1")

    assert result is None


@pytest.mark.anyio
async def test_get_common_scene_memory(mock_client: MagicMock) -> None:
    """get_common_scene_memory returns common scene memory."""
    node = _make_node_mock({
        "id": "mem-1",
        "content": "Common scene content",
        "memory_type": "scene",
        "visibility": "common",
        "target_id": "scene-1",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    result = await get_common_scene_memory(mock_client, "scene-1")

    assert isinstance(result, Memory)
    assert result.visibility == "common"


@pytest.mark.anyio
async def test_get_character_memory_returns_memory(mock_client: MagicMock) -> None:
    """get_character_memory returns memory for matching owner + about_character."""
    node = _make_node_mock({
        "id": "mem-1",
        "content": "Alice is brave",
        "memory_type": "character",
        "visibility": "private",
        "owner_id": "char-1",
        "target_id": "char-2",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    result = await get_character_memory(mock_client, "char-1", "char-2")

    assert isinstance(result, Memory)
    assert result.content == "Alice is brave"


@pytest.mark.anyio
async def test_get_character_memory_returns_none(mock_client: MagicMock) -> None:
    """get_character_memory returns None for non-existent pair."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    result = await get_character_memory(mock_client, "char-1", "char-2")

    assert result is None


@pytest.mark.anyio
async def test_get_memories_for_context_returns_context_memories(mock_client: MagicMock) -> None:
    """get_memories_for_context returns all applicable memories."""
    # Common scene memory query
    common_node = _make_node_mock({
        "id": "mem-common",
        "content": "Common scene",
        "memory_type": "scene",
        "visibility": "common",
        "target_id": "scene-1",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })
    # Private scene memory query
    private_node = _make_node_mock({
        "id": "mem-private",
        "content": "Private scene",
        "memory_type": "scene",
        "visibility": "private",
        "owner_id": "char-1",
        "target_id": "scene-1",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })
    # CharacterModel memory query
    char_node = _make_node_mock({
        "id": "mem-char",
        "content": "About char-2",
        "memory_type": "character",
        "visibility": "private",
        "owner_id": "char-1",
        "target_id": "char-2",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })

    # Mock sequential queries: common scene, private scene, character memories, world facts
    mock_client.graph.query.side_effect = [
        MagicMock(result_set=[[common_node]]),
        MagicMock(result_set=[[private_node]]),
        MagicMock(result_set=[[char_node]]),
        MagicMock(result_set=[]),  # world facts
    ]

    result = await get_memories_for_context(
        mock_client, "char-1", "scene-1", ["char-2"]
    )

    assert isinstance(result, ContextMemories)
    assert result.common_scene_memory is not None
    assert result.private_scene_memory is not None
    assert "char-2" in result.character_memories


@pytest.mark.anyio
async def test_get_memories_for_context_common_only(mock_client: MagicMock) -> None:
    """get_memories_for_context returns common memories even with no private memories."""
    common_node = _make_node_mock({
        "id": "mem-common",
        "content": "Common",
        "memory_type": "scene",
        "visibility": "common",
        "target_id": "scene-1",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })

    mock_client.graph.query.side_effect = [
        MagicMock(result_set=[[common_node]]),
        MagicMock(result_set=[]),  # no private scene memory
        MagicMock(result_set=[]),  # no character memories
        MagicMock(result_set=[]),  # no world facts
    ]

    result = await get_memories_for_context(
        mock_client, "char-1", "scene-1", []
    )

    assert result.common_scene_memory is not None
    assert result.private_scene_memory is None
    assert result.character_memories == {}


@pytest.mark.anyio
async def test_get_memories_for_context_world_facts(mock_client: MagicMock) -> None:
    """get_memories_for_context returns world facts."""
    wf_node = _make_node_mock({
        "id": "wf-1",
        "content": "The world is round",
        "memory_type": "world_fact",
        "visibility": "common",
        "target_id": "entity-1",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })

    # With empty present_character_ids, character memory query is skipped (3 queries total)
    mock_client.graph.query.side_effect = [
        MagicMock(result_set=[]),  # no common scene
        MagicMock(result_set=[]),  # no private scene
        MagicMock(result_set=[[wf_node]]),  # world facts
    ]

    result = await get_memories_for_context(
        mock_client, "char-1", "scene-1", []
    )

    assert len(result.world_facts) == 1
    assert result.world_facts[0].content == "The world is round"


@pytest.mark.anyio
async def test_get_all_memories_returns_all(mock_client: MagicMock) -> None:
    """get_all_memories returns all memories for an owner."""
    node1 = _make_node_mock({
        "id": "mem-1",
        "content": "Memory 1",
        "memory_type": "scene",
        "visibility": "private",
        "owner_id": "char-1",
        "target_id": "scene-1",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })
    node2 = _make_node_mock({
        "id": "mem-2",
        "content": "Memory 2",
        "memory_type": "character",
        "visibility": "private",
        "owner_id": "char-1",
        "target_id": "char-2",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })
    mock_client.graph.query.return_value = MagicMock(result_set=[[node1], [node2]])

    result = await get_all_memories(mock_client, "char-1")

    assert len(result) == 2


@pytest.mark.anyio
async def test_get_all_memories_filters_by_type(mock_client: MagicMock) -> None:
    """get_all_memories filters by memory_type when specified."""
    node = _make_node_mock({
        "id": "mem-1",
        "content": "SceneModel memory",
        "memory_type": "scene",
        "visibility": "private",
        "owner_id": "char-1",
        "target_id": "scene-1",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    result = await get_all_memories(mock_client, "char-1", memory_type=MemoryType.SCENE)

    cypher = mock_client.graph.query.call_args[0][0]
    assert "memory_type" in cypher
    assert len(result) == 1


# --- Delete / Touch ---


@pytest.mark.anyio
async def test_delete_memory_uses_detach_delete(mock_client: MagicMock) -> None:
    """delete_memory removes node and all relationships."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    await delete_memory(mock_client, "mem-1")

    cypher = mock_client.graph.query.call_args[0][0]
    assert "DETACH DELETE" in cypher


@pytest.mark.anyio
async def test_delete_memory_noop_for_nonexistent(mock_client: MagicMock) -> None:
    """delete_memory is no-op for non-existent id."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    # Should not raise
    await delete_memory(mock_client, "nonexistent")


@pytest.mark.anyio
async def test_touch_memory_increments_access_count(mock_client: MagicMock) -> None:
    """touch_memory increments access_count."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    await touch_memory(mock_client, "mem-1")

    cypher = mock_client.graph.query.call_args[0][0]
    assert "access_count" in cypher
    assert "access_count + 1" in cypher


@pytest.mark.anyio
async def test_touch_memory_updates_last_accessed_at(mock_client: MagicMock) -> None:
    """touch_memory updates last_accessed_at."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    await touch_memory(mock_client, "mem-1")

    cypher = mock_client.graph.query.call_args[0][0]
    assert "last_accessed_at" in cypher


# --- Vector search ---


@pytest.mark.anyio
async def test_search_similar_returns_memories_ordered_by_score(mock_client: MagicMock) -> None:
    """search_similar returns memories ordered by score."""
    node1 = _make_node_mock({
        "id": "mem-1",
        "content": "Similar 1",
        "memory_type": "scene",
        "visibility": "private",
        "owner_id": "char-1",
        "target_id": "scene-1",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })
    node2 = _make_node_mock({
        "id": "mem-2",
        "content": "Similar 2",
        "memory_type": "scene",
        "visibility": "private",
        "owner_id": "char-1",
        "target_id": "scene-2",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })
    mock_client.graph.query.return_value = MagicMock(
        result_set=[[node1, 0.95], [node2, 0.80]]
    )

    result = await search_similar(mock_client, [0.1, 0.2, 0.3])

    assert len(result) == 2
    assert result[0][1] >= result[1][1]  # Ordered by score


@pytest.mark.anyio
async def test_search_similar_filters_by_owner_id(mock_client: MagicMock) -> None:
    """search_similar post-filters by owner_id when specified."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    await search_similar(mock_client, [0.1, 0.2], owner_id="char-1")

    cypher = mock_client.graph.query.call_args[0][0]
    assert "owner_id" in cypher


@pytest.mark.anyio
async def test_search_similar_filters_by_visibility(mock_client: MagicMock) -> None:
    """search_similar post-filters by visibility when specified."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    await search_similar(mock_client, [0.1, 0.2], visibility="common")

    cypher = mock_client.graph.query.call_args[0][0]
    assert "visibility" in cypher


@pytest.mark.anyio
async def test_search_similar_returns_empty_on_no_index(mock_client: MagicMock) -> None:
    """search_similar returns empty list when no vector index exists."""
    mock_client.graph.query.side_effect = Exception("index does not exist")

    result = await search_similar(mock_client, [0.1, 0.2])

    assert result == []


# --- Cypher safety ---


@pytest.mark.anyio
async def test_store_uses_parameterized_queries(mock_client: MagicMock) -> None:
    """store uses parameterized queries (no string interpolation of user values)."""
    node = _make_node_mock({
        "id": "mem-1",
        "content": "Test",
        "memory_type": "scene",
        "visibility": "private",
        "owner_id": "char-1",
        "target_id": "scene-1",
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "access_count": 0,
    })
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    await upsert_memory(
        mock_client, MemoryType.SCENE, "private", "char-1", "scene-1", "Test"
    )

    call_args = mock_client.graph.query.call_args
    cypher = call_args[0][0]
    params = call_args[1].get("params", {})
    # User values should be in params, not interpolated in cypher
    assert "$content" in cypher
    assert "$owner_id" in cypher
    assert "$target_id" in cypher
    assert "content" in params
    assert "owner_id" in params
    assert "target_id" in params
