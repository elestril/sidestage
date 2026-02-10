"""Integration tests: verify Campaign, Scene, and WorldTools route through graph module."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from sidestage.graph import GraphConfig
from sidestage.graph.client import GraphClient
from sidestage.models import CharacterModel, LocationModel, ItemModel, SceneModel


# --- GraphConfig in SidestageConfig ---


def test_sidestage_config_has_graph_field():
    """SidestageConfig has a graph field with GraphConfig default."""
    from sidestage.config import SidestageConfig
    config = SidestageConfig()
    assert isinstance(config.graph, GraphConfig)
    assert config.graph.host == "localhost"
    assert config.graph.port == 6379


def test_sidestage_config_graph_custom_values():
    """SidestageConfig accepts custom graph configuration."""
    from sidestage.config import SidestageConfig
    config = SidestageConfig(graph=GraphConfig(host="graphdb", port=7379, max_connections=8))
    assert config.graph.host == "graphdb"
    assert config.graph.port == 7379
    assert config.graph.max_connections == 8


def test_sidestage_config_has_llms_dict():
    """SidestageConfig has an llms dict with a default entry."""
    from sidestage.config import SidestageConfig, LLMConfig
    config = SidestageConfig()
    assert "default" in config.llms
    assert isinstance(config.llms["default"], LLMConfig)
    assert config.llms["default"].provider == "llama_cpp"
    assert config.llms["default"].model == "default"


def test_sidestage_config_multi_llm():
    """SidestageConfig accepts multiple LLM entries."""
    from sidestage.config import SidestageConfig, LLMConfig
    config = SidestageConfig(llms={
        "default": LLMConfig(provider="llama_cpp", model="default"),
        "embed": LLMConfig(provider="llama_cpp", model="embed", base_url="http://localhost:8080/v1"),
    })
    assert "default" in config.llms
    assert "embed" in config.llms
    assert config.llms["embed"].model == "embed"


# --- Campaign graph lifecycle ---


def test_campaign_has_graph_client_attribute():
    """Campaign has a graph_client attribute (initially None)."""
    from sidestage.campaign import Campaign
    assert hasattr(Campaign, '__init__')
    assert hasattr(Campaign, 'start_graph')
    assert hasattr(Campaign, 'shutdown')


# --- WorldTools graph delegation ---


def test_world_tools_accepts_graph_client():
    """WorldTools constructor accepts optional graph_client."""
    from sidestage.tools import WorldTools
    storage = MagicMock()
    client = MagicMock(spec=GraphClient)

    wt = WorldTools(storage=storage, graph_client=client)

    assert wt.graph_client is client


def test_world_tools_graph_client_defaults_none():
    """WorldTools graph_client defaults to None."""
    from sidestage.tools import WorldTools
    storage = MagicMock()

    wt = WorldTools(storage=storage)

    assert wt.graph_client is None


@pytest.mark.anyio
async def test_world_tools_create_character_delegates_to_graph():
    """WorldTools.create_character delegates to graph.create_entity when graph_client set."""
    from sidestage.tools import WorldTools
    storage = MagicMock()
    client = MagicMock(spec=GraphClient)

    wt = WorldTools(storage=storage, graph_client=client)

    with patch("sidestage.graph.create_entity", new_callable=AsyncMock) as mock_create, \
         patch("sidestage.graph.link", new_callable=AsyncMock):
        mock_create.return_value = MagicMock()
        result = await wt.create_character(name="Alice", body="A warrior", location_id="loc_1")

    mock_create.assert_called_once()
    entity_arg = mock_create.call_args[0][1]
    assert entity_arg.name == "Alice"
    storage.add_character.assert_not_called()


@pytest.mark.anyio
async def test_world_tools_create_character_falls_back_to_storage():
    """WorldTools.create_character uses Storage when graph_client is None."""
    from sidestage.tools import WorldTools
    storage = MagicMock()

    wt = WorldTools(storage=storage)

    result = await wt.create_character(name="Bob", body="A mage")

    storage.add_character.assert_called_once()


@pytest.mark.anyio
async def test_world_tools_list_characters_delegates_to_graph():
    """WorldTools.list_characters delegates to graph.list_entities when graph_client set."""
    from sidestage.tools import WorldTools
    storage = MagicMock()
    client = MagicMock(spec=GraphClient)

    wt = WorldTools(storage=storage, graph_client=client)

    mock_char = CharacterModel(id="char_1", name="Alice", body="A warrior")
    with patch("sidestage.graph.list_entities", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [mock_char]
        result = await wt.list_characters()

    mock_list.assert_called_once_with(client, entity_type="Character")
    storage.list_characters.assert_not_called()
    assert "Alice" in result


@pytest.mark.anyio
async def test_world_tools_get_character_delegates_to_graph():
    """WorldTools.get_character delegates to graph.get_entity when graph_client set."""
    from sidestage.tools import WorldTools
    storage = MagicMock()
    client = MagicMock(spec=GraphClient)

    wt = WorldTools(storage=storage, graph_client=client)

    mock_char = CharacterModel(id="char_1", name="Alice", body="A warrior")
    with patch("sidestage.graph.get_entity", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_char
        result = await wt.get_character("char_1")

    mock_get.assert_called_once_with(client, "char_1")
    storage.get_character.assert_not_called()
    assert "Alice" in result


# --- Scene graph delegation ---


def test_scene_logic_accepts_graph_client():
    """Scene constructor accepts optional graph_client."""
    from sidestage.scene import Scene

    storage = MagicMock()
    campaign = MagicMock()
    scene_data = SceneModel(id="s1", name="Test", body="desc", current_gametime=0)
    client = MagicMock(spec=GraphClient)

    sl = Scene(storage, scene_data, campaign, graph_client=client)

    assert sl.graph_client is client


def test_scene_logic_graph_client_defaults_none():
    """Scene graph_client defaults to None."""
    from sidestage.scene import Scene

    storage = MagicMock()
    campaign = MagicMock()
    scene_data = SceneModel(id="s1", name="Test", body="desc", current_gametime=0)

    sl = Scene(storage, scene_data, campaign)

    assert sl.graph_client is None


def _mock_campaign_with_character():
    """Create a mock Campaign that returns Character-like objects from get_character()."""
    from sidestage.character import Character
    from sidestage.actors import User

    campaign = MagicMock()
    user = User(actor_id="user")
    campaign.user = user

    def _get_character(model):
        char = Character(model=model, actor=user)
        return char

    campaign.get_character = _get_character
    return campaign


@pytest.mark.anyio
async def test_scene_logic_activate_uses_graph_for_characters():
    """Scene.activate uses graph.list_entities for characters when graph_client set."""
    from sidestage.scene import Scene

    storage = MagicMock()
    campaign = _mock_campaign_with_character()
    scene_data = SceneModel(id="s1", name="Test", body="desc", current_gametime=0)
    client = MagicMock(spec=GraphClient)

    sl = Scene(storage, scene_data, campaign, graph_client=client)
    # Mock the queue to avoid needing a real event loop for asyncio.create_task
    sl.queue = MagicMock()
    sl.queue.start = AsyncMock()

    mock_char = CharacterModel(id="char_1", name="Alice", body="A warrior")
    with patch("sidestage.graph.list_entities", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [mock_char]
        await sl.activate()

    mock_list.assert_called_once_with(client, entity_type="Character")
    storage.list_characters.assert_not_called()


@pytest.mark.anyio
async def test_scene_logic_activate_falls_back_to_storage():
    """Scene.activate uses Storage for characters when graph_client is None."""
    from sidestage.scene import Scene

    storage = MagicMock()
    storage.list_characters.return_value = []
    campaign = _mock_campaign_with_character()
    scene_data = SceneModel(id="s1", name="Test", body="desc", current_gametime=0)

    sl = Scene(storage, scene_data, campaign)
    # Mock the queue to avoid needing a real event loop for asyncio.create_task
    sl.queue = MagicMock()
    sl.queue.start = AsyncMock()
    await sl.activate()

    storage.list_characters.assert_called_once()


# --- Hyphen sanitization ---


def test_sanitize_graph_name_converts_hyphens():
    """sanitize_graph_name converts hyphens to underscores."""
    from sidestage.graph.client import sanitize_graph_name
    assert sanitize_graph_name("my-great-campaign") == "my_great_campaign"


def test_sanitize_graph_name_handles_spaces():
    """sanitize_graph_name converts spaces to underscores."""
    from sidestage.graph.client import sanitize_graph_name
    assert sanitize_graph_name("My Great Campaign") == "my_great_campaign"


# --- Agent async tool support ---


def test_agent_handles_async_tool_functions():
    """LiteLLMAgent.arun contains iscoroutine check for async tools."""
    import inspect
    from sidestage.agent import LiteLLMAgent

    source = inspect.getsource(LiteLLMAgent.arun)
    assert "iscoroutine" in source, "Agent must detect and await coroutine results from async tools"
