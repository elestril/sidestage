"""Unit tests for memory tools (NPC and DM agent-callable tools)."""

import json
from typing import Any

import anyio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sidestage.memory.models import Memory, MemoryType
from sidestage.memory.tools import MemoryTools, DmMemoryTools


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_memory(**overrides: Any) -> Memory:
    """Helper to build a Memory with sensible defaults."""
    defaults = dict(
        id="mem_test123",
        content="test content",
        memory_type=MemoryType.SCENE,
        visibility="private",
        embedding=None,
        owner_id="char_alice",
        target_id="scene_01",
        created_at=1000.0,
        updated_at=1000.0,
        gametime=None,
        access_count=0,
        last_accessed_at=None,
    )
    defaults.update(overrides)
    return Memory(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def mock_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_embed_config() -> MagicMock:
    """A minimal LLMConfig-like object for embedding."""
    cfg = MagicMock()
    cfg.provider = "llama_cpp"
    cfg.model = "embed"
    cfg.base_url = "http://localhost:8080/v1"
    cfg.api_key = "sk-no-key-required"
    return cfg


@pytest.fixture
def mock_health() -> MagicMock:
    health = MagicMock()
    health.is_embedding_available = True
    return health


@pytest.fixture
def npc_tools(mock_client: MagicMock, mock_embed_config: MagicMock, mock_health: MagicMock) -> MemoryTools:
    return MemoryTools(
        client=mock_client,
        embed_config=mock_embed_config,
        health=mock_health,
        owner_id="char_alice",
        scene_id="scene_01",
    )


@pytest.fixture
def dm_tools(mock_client: MagicMock, mock_embed_config: MagicMock, mock_health: MagicMock) -> DmMemoryTools:
    return DmMemoryTools(
        client=mock_client,
        embed_config=mock_embed_config,
        health=mock_health,
        dm_actor_id="dm_001",
    )


# ---------------------------------------------------------------------------
# NPC MemoryTools tests
# ---------------------------------------------------------------------------

class TestMemoryToolsBinding:
    """Test that MemoryTools binds to specific owner_id and scene_id at construction."""

    def test_binds_owner_id(self, npc_tools: MemoryTools) -> None:
        assert npc_tools.owner_id == "char_alice"

    def test_binds_scene_id(self, npc_tools: MemoryTools) -> None:
        assert npc_tools.scene_id == "scene_01"


class TestUpdateSceneMemory:
    """Tests for MemoryTools.update_scene_memory."""

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_scene_memory", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_calls_upsert_with_correct_params(self, mock_embed: AsyncMock, mock_upsert: AsyncMock, npc_tools: MemoryTools) -> None:
        """update_scene_memory calls upsert_scene_memory with correct owner_id and scene_id."""
        mock_upsert.return_value = _make_memory()
        result = await npc_tools.update_scene_memory(content="The tavern exploded")
        mock_upsert.assert_awaited_once_with(
            npc_tools.client, "char_alice", "scene_01", "The tavern exploded", gametime=None,
        )

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_scene_memory", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_fires_embed_as_background_task(self, mock_embed: AsyncMock, mock_upsert: AsyncMock, npc_tools: MemoryTools) -> None:
        """update_scene_memory fires embed_and_update as a background asyncio.Task."""
        import sniffio
        mem = _make_memory()
        mock_upsert.return_value = mem
        await npc_tools.update_scene_memory(content="something happened")
        await anyio.sleep(0)
        # asyncio.create_task only works under asyncio, not trio
        if sniffio.current_async_library() == "asyncio":
            mock_embed.assert_awaited_once()

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_scene_memory", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_returns_json_with_memory_id(self, mock_embed: AsyncMock, mock_upsert: AsyncMock, npc_tools: MemoryTools) -> None:
        """update_scene_memory returns JSON confirmation with memory ID."""
        mock_upsert.return_value = _make_memory(id="mem_abc")
        result = await npc_tools.update_scene_memory(content="noted")
        parsed = json.loads(result)
        assert parsed["memory_id"] == "mem_abc"
        assert parsed["status"] == "ok"

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_scene_memory", new_callable=AsyncMock)
    async def test_returns_error_json_on_graph_failure(self, mock_upsert: AsyncMock, npc_tools: MemoryTools) -> None:
        """update_scene_memory returns error JSON when the store raises an exception."""
        mock_upsert.side_effect = Exception("graph down")
        result = await npc_tools.update_scene_memory(content="crash")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert "graph down" in parsed["message"]


class TestUpdateCharacterMemory:
    """Tests for MemoryTools.update_character_memory."""

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_character_memory", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_calls_upsert_with_correct_params(self, mock_embed: AsyncMock, mock_upsert: AsyncMock, npc_tools: MemoryTools) -> None:
        """update_character_memory calls upsert_character_memory with correct parameters."""
        mock_upsert.return_value = _make_memory(memory_type=MemoryType.CHARACTER, target_id="char_bob")
        await npc_tools.update_character_memory(
            about_character_id="char_bob", content="Bob seems trustworthy",
        )
        mock_upsert.assert_awaited_once_with(
            npc_tools.client, "char_alice", "char_bob", "Bob seems trustworthy", gametime=None,
        )

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_character_memory", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_returns_json_with_memory_id(self, mock_embed: AsyncMock, mock_upsert: AsyncMock, npc_tools: MemoryTools) -> None:
        """update_character_memory returns JSON with memory ID."""
        mock_upsert.return_value = _make_memory(id="mem_xyz")
        result = await npc_tools.update_character_memory(
            about_character_id="char_bob", content="Bob is shady",
        )
        parsed = json.loads(result)
        assert parsed["memory_id"] == "mem_xyz"
        assert parsed["status"] == "ok"


class TestNpcToolsEmbedSkippedWhenNoConfig:
    """Embedding is skipped when embed_config is None."""

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_scene_memory", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_no_embed_when_config_none(self, mock_embed: AsyncMock, mock_upsert: AsyncMock, mock_client: MagicMock, mock_health: MagicMock) -> None:
        tools = MemoryTools(
            client=mock_client,
            embed_config=None,
            health=mock_health,
            owner_id="char_alice",
            scene_id="scene_01",
        )
        mock_upsert.return_value = _make_memory()
        await tools.update_scene_memory(content="noted")
        await anyio.sleep(0)
        mock_embed.assert_not_awaited()


# ---------------------------------------------------------------------------
# DM Tools tests
# ---------------------------------------------------------------------------

class TestUpdateCommonMemory:
    """Tests for DmMemoryTools.update_common_memory."""

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_common_scene_memory", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_calls_upsert_common(self, mock_embed: AsyncMock, mock_upsert: AsyncMock, dm_tools: DmMemoryTools) -> None:
        """update_common_memory calls upsert_common_scene_memory."""
        mock_upsert.return_value = _make_memory(visibility="common", owner_id=None)
        await dm_tools.update_common_memory(scene_id="scene_01", content="A brawl broke out")
        mock_upsert.assert_awaited_once_with(
            dm_tools.client, "scene_01", "A brawl broke out", gametime=None,
        )


class TestUpdateCanonicalMemory:
    """Tests for DmMemoryTools.update_canonical_memory."""

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_scene_memory", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_calls_upsert_with_dm_owner(self, mock_embed: AsyncMock, mock_upsert: AsyncMock, dm_tools: DmMemoryTools) -> None:
        """update_canonical_memory calls upsert_scene_memory with DM owner_id."""
        mock_upsert.return_value = _make_memory(owner_id="dm_001")
        await dm_tools.update_canonical_memory(scene_id="scene_01", content="The assassin was there")
        mock_upsert.assert_awaited_once_with(
            dm_tools.client, "dm_001", "scene_01", "The assassin was there", gametime=None,
        )


class TestAddWorldFact:
    """Tests for DmMemoryTools.add_world_fact."""

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_world_fact", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_common_world_fact(self, mock_embed: AsyncMock, mock_upsert: AsyncMock, dm_tools: DmMemoryTools) -> None:
        """add_world_fact with visibility='common' creates common world fact."""
        mock_upsert.return_value = _make_memory(memory_type=MemoryType.WORLD_FACT, visibility="common")
        await dm_tools.add_world_fact(
            about_entity_id="loc_tavern", content="The tavern is haunted", visibility="common",
        )
        mock_upsert.assert_awaited_once_with(
            dm_tools.client, "loc_tavern", "The tavern is haunted",
            visibility="common", owner_id=None,
        )

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_world_fact", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_private_world_fact(self, mock_embed: AsyncMock, mock_upsert: AsyncMock, dm_tools: DmMemoryTools) -> None:
        """add_world_fact with visibility='private' creates private world fact."""
        mock_upsert.return_value = _make_memory(memory_type=MemoryType.WORLD_FACT, visibility="private")
        await dm_tools.add_world_fact(
            about_entity_id="loc_tavern", content="Secret passage exists",
            visibility="private",
        )
        mock_upsert.assert_awaited_once_with(
            dm_tools.client, "loc_tavern", "Secret passage exists",
            visibility="private", owner_id=None,
        )


class TestDmToolsFireEmbed:
    """DM tools fire embed_and_update as a background task."""

    @pytest.mark.anyio
    @patch("sidestage.memory.tools.upsert_common_scene_memory", new_callable=AsyncMock)
    @patch("sidestage.memory.tools.embed_and_update", new_callable=AsyncMock)
    async def test_embed_fired_for_common_memory(self, mock_embed: AsyncMock, mock_upsert: AsyncMock, dm_tools: DmMemoryTools) -> None:
        import sniffio
        mem = _make_memory(visibility="common", owner_id=None)
        mock_upsert.return_value = mem
        await dm_tools.update_common_memory(scene_id="scene_01", content="stuff")
        await anyio.sleep(0)
        if sniffio.current_async_library() == "asyncio":
            mock_embed.assert_awaited_once()
