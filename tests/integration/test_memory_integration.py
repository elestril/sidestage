"""Integration tests for memory system wiring through scene activation."""

from typing import Any

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from sidestage.schemas import Scene, Character, ChatMessage
from sidestage.scene import SceneLogic
from sidestage.character import CharacterLogic, AgentActor
from sidestage.agent import LiteLLMAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scene(**overrides: Any) -> Scene:
    defaults = dict(
        id="scene_test",
        name="Test Scene",
        body="A test scene.",
        current_gametime=100,
    )
    defaults.update(overrides)
    return Scene(**defaults)  # type: ignore[arg-type]


def _make_character(**overrides: Any) -> Character:
    defaults = dict(
        id="char_alice",
        name="Alice",
        body="A brave warrior.",
    )
    defaults.update(overrides)
    return Character(**defaults)  # type: ignore[arg-type]


def _make_agent() -> MagicMock:
    """Create a mock LiteLLMAgent with expected attributes."""
    agent = MagicMock(spec=LiteLLMAgent)
    agent.model = "openai/default"
    agent.api_base = "http://localhost:8080/v1"
    agent.api_key = "sk-no-key-required"
    agent.tools = []
    agent.debug_mode = False
    return agent


def _make_storage() -> MagicMock:
    """Create a mock Storage."""
    storage = MagicMock()
    storage.list_characters.return_value = []
    return storage


# ---------------------------------------------------------------------------
# SceneLogic accepts and stores memory deps
# ---------------------------------------------------------------------------


class TestSceneLogicMemoryDeps:
    """SceneLogic accepts and stores memory-related parameters."""

    def test_accepts_memory_kwargs(self) -> None:
        """SceneLogic stores embed_config, health, and context_limit."""
        mock_client = MagicMock()
        mock_config = MagicMock()
        mock_health = MagicMock()

        sl = SceneLogic(
            _make_storage(), _make_agent(), _make_scene(),
            graph_client=mock_client,
            embed_config=mock_config,
            health=mock_health,
            context_limit=8192,
        )
        assert sl.embed_config is mock_config
        assert sl.health is mock_health
        assert sl.context_limit == 8192

    def test_backwards_compatible_without_memory_kwargs(self) -> None:
        """SceneLogic works without memory-related arguments."""
        sl = SceneLogic(_make_storage(), _make_agent(), _make_scene())
        assert sl.embed_config is None
        assert sl.health is None
        assert sl.context_limit == 4096


# ---------------------------------------------------------------------------
# SceneLogic.activate passes memory deps to CharacterLogic
# ---------------------------------------------------------------------------


class TestSceneLogicActivation:
    """SceneLogic.activate() passes memory dependencies to CharacterLogic."""

    @pytest.mark.anyio
    async def test_activate_passes_graph_client_to_character_logic(self) -> None:
        """Characters receive graph_client during scene activation."""
        mock_config = MagicMock()
        mock_health = MagicMock()
        mock_health.is_accepting_chat = True

        storage = _make_storage()
        storage.list_characters.return_value = [
            _make_character(id="char_alice"),
            _make_character(id="char_bob", name="Bob", body="A sly rogue."),
        ]

        sl = SceneLogic(
            storage, _make_agent(), _make_scene(),
            embed_config=mock_config,
            health=mock_health,
            context_limit=8192,
        )
        sl.queue = MagicMock()
        sl.queue.start = AsyncMock()
        await sl.activate()

        for char_logic in sl.characters.values():
            assert char_logic.graph_client is None  # No graph_client on SceneLogic
            assert char_logic.embed_config is mock_config
            assert char_logic.health is mock_health
            assert char_logic.context_limit == 8192

    @pytest.mark.anyio
    async def test_activate_passes_scene_id_and_present_characters(self) -> None:
        """Characters receive scene_id and the full list of present character IDs."""
        storage = _make_storage()
        alice = _make_character(id="char_alice")
        bob = _make_character(id="char_bob", name="Bob", body="A sly rogue.")
        storage.list_characters.return_value = [alice, bob]

        sl = SceneLogic(
            storage, _make_agent(), _make_scene(id="scene_tavern"),
            health=MagicMock(),
        )
        sl.queue = MagicMock()
        sl.queue.start = AsyncMock()
        await sl.activate()

        for char_logic in sl.characters.values():
            assert char_logic.scene_id == "scene_tavern"
            assert char_logic.present_character_ids is not None
            assert set(char_logic.present_character_ids) == {"char_alice", "char_bob"}

    @pytest.mark.anyio
    @patch("sidestage.graph.list_entities", new_callable=AsyncMock)
    async def test_activate_with_graph_client_uses_graph_entities(self, mock_list: AsyncMock) -> None:
        """When graph_client is set, activate loads characters from graph."""
        mock_client = MagicMock()
        mock_list.return_value = [
            _make_character(id="char_alice"),
        ]

        sl = SceneLogic(
            _make_storage(), _make_agent(), _make_scene(),
            graph_client=mock_client,
            health=MagicMock(),
        )
        sl.queue = MagicMock()
        sl.queue.start = AsyncMock()
        await sl.activate()

        mock_list.assert_awaited_once_with(mock_client, entity_type="Character")
        assert "char_alice" in sl.characters
        assert sl.characters["char_alice"].graph_client is mock_client


# ---------------------------------------------------------------------------
# Full wiring chain: SceneLogic -> CharacterLogic -> AgentActor
# ---------------------------------------------------------------------------


class TestFullWiringChain:
    """Verify memory deps flow from SceneLogic to AgentActor."""

    @pytest.mark.anyio
    async def test_actor_receives_memory_deps_after_activation(self) -> None:
        """AgentActor receives memory deps after scene and character activation."""
        mock_config = MagicMock()
        mock_health = MagicMock()
        mock_health.is_accepting_chat = True

        storage = _make_storage()
        storage.list_characters.return_value = [_make_character(id="char_alice")]

        sl = SceneLogic(
            storage, _make_agent(), _make_scene(id="scene_01"),
            embed_config=mock_config,
            health=mock_health,
            context_limit=8192,
        )
        sl.queue = MagicMock()
        sl.queue.start = AsyncMock()
        await sl.activate()

        char_logic = sl.characters["char_alice"]
        actor = char_logic.actor
        assert actor is not None
        assert actor.embed_config is mock_config
        assert actor.health is mock_health
        assert actor.scene_id == "scene_01"
        assert actor.context_limit == 8192

    @pytest.mark.anyio
    async def test_actor_has_memory_tools_when_graph_and_health_set(self) -> None:
        """AgentActor has memory tools when graph_client and health are set."""
        mock_client = MagicMock()
        mock_config = MagicMock()
        mock_health = MagicMock()
        mock_health.is_accepting_chat = True

        storage = _make_storage()
        storage.list_characters.return_value = [_make_character(id="char_alice")]

        sl = SceneLogic(
            storage, _make_agent(), _make_scene(id="scene_01"),
            graph_client=mock_client,
            embed_config=mock_config,
            health=mock_health,
            context_limit=4096,
        )
        sl.queue = MagicMock()
        sl.queue.start = AsyncMock()
        # Need to mock graph list_entities since graph_client is set
        with patch("sidestage.graph.list_entities", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [_make_character(id="char_alice")]
            await sl.activate()

        actor = sl.characters["char_alice"].actor
        assert actor is not None
        assert actor.agent is not None
        tool_names = [t.__name__ for t in actor.agent.tools]
        assert "update_scene_memory" in tool_names
        assert "update_character_memory" in tool_names


# ---------------------------------------------------------------------------
# Health check in SceneLogic.chat()
# ---------------------------------------------------------------------------


class TestSceneLogicHealthCheck:
    """SceneLogic.chat() respects health status."""

    @pytest.mark.anyio
    async def test_chat_proceeds_when_healthy(self) -> None:
        """Chat proceeds when health is HEALTHY."""
        mock_health = MagicMock()
        mock_health.is_accepting_chat = True

        sl = SceneLogic(
            _make_storage(), _make_agent(), _make_scene(),
            health=mock_health,
        )
        sl.queue = MagicMock()
        sl.queue.put = AsyncMock()

        msg = ChatMessage(
            id="m1", name="Msg", body="Hello",
            actor_id="user", character_id="user", message="Hello",
            scene_id="scene_test", gametime=0, walltime="now",
        )
        await sl.chat(msg)
        sl.queue.put.assert_awaited_once()

    @pytest.mark.anyio
    async def test_chat_blocked_when_unhealthy(self) -> None:
        """Chat is rejected when health is UNHEALTHY."""
        mock_health = MagicMock()
        mock_health.is_accepting_chat = False

        sl = SceneLogic(
            _make_storage(), _make_agent(), _make_scene(),
            health=mock_health,
        )
        sl.queue = MagicMock()
        sl.queue.put = AsyncMock()

        msg = ChatMessage(
            id="m1", name="Msg", body="Hello",
            actor_id="user", character_id="user", message="Hello",
            scene_id="scene_test", gametime=0, walltime="now",
        )
        await sl.chat(msg)
        sl.queue.put.assert_not_awaited()

    @pytest.mark.anyio
    async def test_chat_proceeds_without_health(self) -> None:
        """Chat proceeds when health is None (backwards compatible)."""
        sl = SceneLogic(
            _make_storage(), _make_agent(), _make_scene(),
        )
        sl.queue = MagicMock()
        sl.queue.put = AsyncMock()

        msg = ChatMessage(
            id="m1", name="Msg", body="Hello",
            actor_id="user", character_id="user", message="Hello",
            scene_id="scene_test", gametime=0, walltime="now",
        )
        await sl.chat(msg)
        sl.queue.put.assert_awaited_once()


# ---------------------------------------------------------------------------
# Campaign.get_scene_object passes memory deps
# ---------------------------------------------------------------------------


class TestCampaignGetSceneObject:
    """Campaign.get_scene_object() passes memory dependencies to SceneLogic."""

    def test_get_scene_object_passes_health_and_embed_config(self) -> None:
        """get_scene_object creates SceneLogic with health and embed config."""
        from sidestage.campaign import Campaign
        from sidestage.config import LLMConfig, SidestageConfig
        from sidestage.graph import GraphConfig
        from sidestage.health import CampaignHealth

        campaign = object.__new__(Campaign)
        campaign.name = "test"
        campaign.config = SidestageConfig(
            llms={
                "default": LLMConfig(context_limit=8192),
                "embed": LLMConfig(provider="llama_cpp", model="embed-model"),
            },
            graph=GraphConfig(),
        )
        campaign.graph_client = MagicMock()
        campaign.health = CampaignHealth()
        campaign.agent = _make_agent()

        storage = _make_storage()
        storage.get_scene.return_value = _make_scene()
        campaign.storage = storage

        scene_logic = campaign.get_scene_object("scene_test")

        assert scene_logic is not None
        assert scene_logic.embed_config is not None
        assert scene_logic.health is campaign.health
        assert scene_logic.context_limit == 8192

    def test_get_scene_object_no_embed_config(self) -> None:
        """get_scene_object works when no embed config exists."""
        from sidestage.campaign import Campaign
        from sidestage.config import LLMConfig, SidestageConfig
        from sidestage.graph import GraphConfig
        from sidestage.health import CampaignHealth

        campaign = object.__new__(Campaign)
        campaign.name = "test"
        campaign.config = SidestageConfig(
            llms={"default": LLMConfig()},  # No embed
            graph=GraphConfig(),
        )
        campaign.graph_client = None
        campaign.health = CampaignHealth()
        campaign.agent = _make_agent()

        storage = _make_storage()
        storage.get_scene.return_value = _make_scene()
        campaign.storage = storage

        scene_logic = campaign.get_scene_object("scene_test")

        assert scene_logic is not None
        assert scene_logic.embed_config is None
        assert scene_logic.context_limit == 4096  # default fallback
