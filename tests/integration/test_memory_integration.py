"""Integration tests for memory system wiring through scene activation."""

from typing import Any

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from sidestage.models import SceneModel, CharacterModel, EventModel, EventType
from sidestage.scene import Scene
from sidestage.actors import NPCActor
from sidestage.character import Character
from sidestage.agent import LiteLLMAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scene(**overrides: Any) -> SceneModel:
    defaults = dict(
        id="scene_test",
        name="Test SceneModel",
        body="A test scene.",
        current_gametime=100,
    )
    defaults.update(overrides)
    return SceneModel(**defaults)  # type: ignore[arg-type]


def _make_character(**overrides: Any) -> CharacterModel:
    defaults = dict(
        id="char_alice",
        name="Alice",
        body="A brave warrior.",
    )
    defaults.update(overrides)
    return CharacterModel(**defaults)  # type: ignore[arg-type]


def _make_campaign() -> MagicMock:
    """Create a mock Campaign with get_character() that returns Character instances."""
    campaign = MagicMock()
    campaign.get_llm_config.return_value = MagicMock(
        provider="llama_cpp", model="test-model",
        base_url="http://localhost:8080/v1", api_key="sk-test",
        context_limit=4096,
    )

    def _get_character(model: CharacterModel) -> Character:
        actor = NPCActor(actor_id=f"agent:{model.id}")
        return Character(model=model, actor=actor)

    campaign.get_character = MagicMock(side_effect=_get_character)
    return campaign


def _make_storage() -> MagicMock:
    """Create a mock Storage."""
    storage = MagicMock()
    storage.list_characters.return_value = []
    return storage


# ---------------------------------------------------------------------------
# Scene accepts and stores memory deps
# ---------------------------------------------------------------------------


class TestSceneMemoryDeps:
    """Scene accepts and stores memory-related parameters."""

    def test_accepts_memory_kwargs(self) -> None:
        """Scene stores embed_config, health, and context_limit."""
        mock_client = MagicMock()
        mock_config = MagicMock()
        mock_health = MagicMock()

        sl = Scene(
            _make_storage(), _make_scene(), _make_campaign(),
            graph_client=mock_client,
            embed_config=mock_config,
            health=mock_health,
            context_limit=8192,
        )
        assert sl.embed_config is mock_config
        assert sl.health is mock_health
        assert sl.context_limit == 8192

    def test_backwards_compatible_without_memory_kwargs(self) -> None:
        """Scene works without memory-related arguments."""
        sl = Scene(_make_storage(), _make_scene(), _make_campaign())
        assert sl.embed_config is None
        assert sl.health is None
        assert sl.context_limit == 4096


# ---------------------------------------------------------------------------
# Scene.activate passes memory deps to NPCActor
# ---------------------------------------------------------------------------


class TestSceneActivation:
    """Scene.activate() passes memory dependencies to NPCActor."""

    @pytest.mark.anyio
    async def test_activate_passes_memory_deps_to_actor(self) -> None:
        """NPCActors receive memory deps during scene activation."""
        mock_config = MagicMock()
        mock_health = MagicMock()
        mock_health.is_accepting_chat = True

        storage = _make_storage()
        storage.list_characters.return_value = [
            _make_character(id="char_alice"),
            _make_character(id="char_bob", name="Bob", body="A sly rogue."),
        ]

        sl = Scene(
            storage, _make_scene(), _make_campaign(),
            embed_config=mock_config,
            health=mock_health,
            context_limit=8192,
        )
        sl.queue = MagicMock()
        sl.queue.start = AsyncMock()
        await sl.activate()

        for char_logic in sl.characters.values():
            actor = char_logic.actor
            assert isinstance(actor, NPCActor)
            assert actor.graph_client is None  # No graph_client on Scene
            assert actor.embed_config is mock_config
            assert actor.health is mock_health
            assert actor.context_limit == 8192

    @pytest.mark.anyio
    async def test_activate_passes_scene_id_and_present_characters(self) -> None:
        """NPCActors receive scene_id and the full list of present character IDs."""
        storage = _make_storage()
        alice = _make_character(id="char_alice")
        bob = _make_character(id="char_bob", name="Bob", body="A sly rogue.")
        storage.list_characters.return_value = [alice, bob]

        sl = Scene(
            storage, _make_scene(id="scene_tavern"), _make_campaign(),
            health=MagicMock(),
        )
        sl.queue = MagicMock()
        sl.queue.start = AsyncMock()
        await sl.activate()

        for char_logic in sl.characters.values():
            actor = char_logic.actor
            assert isinstance(actor, NPCActor)
            assert actor.scene_id == "scene_tavern"
            assert actor.present_character_ids is not None
            assert set(actor.present_character_ids) == {"char_alice", "char_bob"}

    @pytest.mark.anyio
    @patch("sidestage.graph.list_entities", new_callable=AsyncMock)
    async def test_activate_with_graph_client_uses_graph_entities(self, mock_list: AsyncMock) -> None:
        """When graph_client is set, activate loads characters from graph."""
        mock_client = MagicMock()
        mock_list.return_value = [
            _make_character(id="char_alice"),
        ]

        sl = Scene(
            _make_storage(), _make_scene(), _make_campaign(),
            graph_client=mock_client,
            health=MagicMock(),
        )
        sl.queue = MagicMock()
        sl.queue.start = AsyncMock()
        await sl.activate()

        mock_list.assert_awaited_once_with(mock_client, entity_type="Character")
        assert "char_alice" in sl.characters
        actor = sl.characters["char_alice"].actor
        assert isinstance(actor, NPCActor)
        assert actor.graph_client is mock_client


# ---------------------------------------------------------------------------
# Full wiring chain: Scene -> Character -> NPCActor
# ---------------------------------------------------------------------------


class TestFullWiringChain:
    """Verify memory deps flow from Scene to NPCActor."""

    @pytest.mark.anyio
    async def test_actor_receives_memory_deps_after_activation(self) -> None:
        """NPCActor receives memory deps after scene activation."""
        mock_config = MagicMock()
        mock_health = MagicMock()
        mock_health.is_accepting_chat = True

        storage = _make_storage()
        storage.list_characters.return_value = [_make_character(id="char_alice")]

        sl = Scene(
            storage, _make_scene(id="scene_01"), _make_campaign(),
            embed_config=mock_config,
            health=mock_health,
            context_limit=8192,
        )
        sl.queue = MagicMock()
        sl.queue.start = AsyncMock()
        await sl.activate()

        char_logic = sl.characters["char_alice"]
        actor = char_logic.actor
        assert isinstance(actor, NPCActor)
        assert actor.embed_config is mock_config
        assert actor.health is mock_health
        assert actor.scene_id == "scene_01"
        assert actor.context_limit == 8192

    @pytest.mark.anyio
    async def test_actor_has_memory_tools_when_graph_and_health_set(self) -> None:
        """NPCActor has memory tools when graph_client and health are set."""
        mock_client = MagicMock()
        mock_config = MagicMock()
        mock_health = MagicMock()
        mock_health.is_accepting_chat = True

        storage = _make_storage()
        storage.list_characters.return_value = [_make_character(id="char_alice")]

        campaign = _make_campaign()
        sl = Scene(
            storage, _make_scene(id="scene_01"), campaign,
            graph_client=mock_client,
            embed_config=mock_config,
            health=mock_health,
            context_limit=4096,
        )
        # Need to mock graph list_entities since graph_client is set
        sl.queue = MagicMock()
        sl.queue.start = AsyncMock()
        with patch("sidestage.graph.list_entities", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [_make_character(id="char_alice")]
            await sl.activate()

        actor = sl.characters["char_alice"].actor
        assert isinstance(actor, NPCActor)
        assert actor.agent is not None
        tool_names = [t.__name__ for t in actor.agent.tools]
        assert "update_scene_memory" in tool_names
        assert "update_character_memory" in tool_names


# ---------------------------------------------------------------------------
# Health check in Scene.chat()
# ---------------------------------------------------------------------------


class TestSceneHealthCheck:
    """Scene.chat() respects health status."""

    @pytest.mark.anyio
    async def test_chat_proceeds_when_healthy(self) -> None:
        """Chat proceeds when health is HEALTHY."""
        mock_health = MagicMock()
        mock_health.is_accepting_chat = True

        sl = Scene(
            _make_storage(), _make_scene(), _make_campaign(),
            health=mock_health,
        )
        sl.queue = MagicMock()
        sl.queue.put = AsyncMock()

        result = await sl.chat("user", "Hello")
        assert result is not None

    @pytest.mark.anyio
    async def test_chat_blocked_when_unhealthy(self) -> None:
        """Chat is rejected when health is UNHEALTHY."""
        mock_health = MagicMock()
        mock_health.is_accepting_chat = False

        sl = Scene(
            _make_storage(), _make_scene(), _make_campaign(),
            health=mock_health,
        )
        sl.queue = MagicMock()
        sl.queue.put = AsyncMock()

        result = await sl.chat("user", "Hello")
        assert result is None
        sl.queue.put.assert_not_awaited()

    @pytest.mark.anyio
    async def test_chat_proceeds_without_health(self) -> None:
        """Chat proceeds when health is None (backwards compatible)."""
        sl = Scene(
            _make_storage(), _make_scene(), _make_campaign(),
        )
        sl.queue = MagicMock()
        sl.queue.put = AsyncMock()

        result = await sl.chat("user", "Hello")
        assert result is not None


# ---------------------------------------------------------------------------
# Campaign.get_scene_object passes memory deps
# ---------------------------------------------------------------------------


class TestCampaignGetSceneObject:
    """Campaign.get_scene_object() passes memory dependencies to Scene."""

    def test_get_scene_object_passes_health_and_embed_config(self) -> None:
        """get_scene_object creates Scene with health and embed config."""
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

        storage = _make_storage()
        storage.get_scene.return_value = _make_scene()
        campaign.storage = storage

        scene_logic = campaign.get_scene_object("scene_test")

        assert scene_logic is not None
        assert scene_logic.embed_config is None
        assert scene_logic.context_limit == 4096  # default fallback
