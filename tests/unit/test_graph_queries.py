"""Unit tests for graph query functions."""
from typing import Any

import pytest
from unittest.mock import AsyncMock, MagicMock

from sidestage.graph.errors import QueryError
from sidestage.graph.queries import (
    characters_at_location,
    characters_in_scene,
    connected_locations,
    scene_events,
    entity_graph,
)
from sidestage.models import CharacterModel, EventModel, EventType, LocationModel


# --- Fixtures ---


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock GraphClient with an async query method."""
    client = MagicMock()
    client.graph = MagicMock()
    client.graph.query = AsyncMock()
    return client


def _make_node_mock(labels: list[str], properties: dict[str, Any]) -> MagicMock:
    """Helper to create a mock graph node."""
    node = MagicMock()
    node.labels = labels
    node.properties = properties
    return node


# --- characters_at_location ---


@pytest.mark.anyio
async def test_characters_at_location_returns_characters(mock_client: MagicMock) -> None:
    """characters_at_location returns characters LOCATED_IN the given location."""
    node = _make_node_mock(
        ["Entity", "Character"],
        {"id": "char_1", "name": "Alice", "body": "A warrior", "unseen": False, "inventory": []},
    )
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    result = await characters_at_location(mock_client, "loc_tavern")

    assert len(result) == 1
    assert isinstance(result[0], CharacterModel)
    assert result[0].id == "char_1"

    cypher = mock_client.graph.query.call_args[0][0]
    assert "LOCATED_IN" in cypher
    assert ":Character" in cypher


@pytest.mark.anyio
async def test_characters_at_location_empty(mock_client: MagicMock) -> None:
    """characters_at_location returns empty list for empty location."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    result = await characters_at_location(mock_client, "loc_empty")

    assert result == []


@pytest.mark.anyio
async def test_characters_at_location_query_error(mock_client: MagicMock) -> None:
    """characters_at_location raises QueryError on failure."""
    mock_client.graph.query.side_effect = Exception("network timeout")

    with pytest.raises(QueryError):
        await characters_at_location(mock_client, "loc_tavern")


# --- characters_in_scene ---


@pytest.mark.anyio
async def test_characters_in_scene_returns_members(mock_client: MagicMock) -> None:
    """characters_in_scene returns only characters with PARTICIPATES_IN edges."""
    node = _make_node_mock(
        ["Entity", "Character"],
        {"id": "char_1", "name": "Alice", "body": "A warrior", "unseen": False, "inventory": []},
    )
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    result = await characters_in_scene(mock_client, "scene_01")

    assert len(result) == 1
    assert isinstance(result[0], CharacterModel)
    assert result[0].id == "char_1"

    cypher = mock_client.graph.query.call_args[0][0]
    assert "PARTICIPATES_IN" in cypher
    assert ":Character" in cypher


@pytest.mark.anyio
async def test_characters_in_scene_empty_scene(mock_client: MagicMock) -> None:
    """characters_in_scene returns empty list when scene has no membership edges."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    result = await characters_in_scene(mock_client, "scene_empty")

    assert result == []


@pytest.mark.anyio
async def test_characters_in_scene_multiple_scenes_isolation(mock_client: MagicMock) -> None:
    """characters_in_scene queries with the correct scene_id parameter."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    await characters_in_scene(mock_client, "scene_a")

    params = mock_client.graph.query.call_args[1].get("params") or mock_client.graph.query.call_args[0][1] if len(mock_client.graph.query.call_args[0]) > 1 else mock_client.graph.query.call_args[1]["params"]
    assert params["scene_id"] == "scene_a"


@pytest.mark.anyio
async def test_characters_in_scene_nonexistent_scene(mock_client: MagicMock) -> None:
    """characters_in_scene returns empty list for a nonexistent scene (not an error)."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    result = await characters_in_scene(mock_client, "scene_nonexistent")

    assert result == []


@pytest.mark.anyio
async def test_characters_in_scene_query_error(mock_client: MagicMock) -> None:
    """characters_in_scene raises QueryError on failure."""
    mock_client.graph.query.side_effect = Exception("network timeout")

    with pytest.raises(QueryError):
        await characters_in_scene(mock_client, "scene_01")


# --- connected_locations ---


@pytest.mark.anyio
async def test_connected_locations_both_directions(mock_client: MagicMock) -> None:
    """connected_locations returns all CONNECTS_TO locations (both directions)."""
    node1 = _make_node_mock(
        ["Entity", "Location"],
        {"id": "loc_2", "name": "Forest", "body": "A dark forest"},
    )
    node2 = _make_node_mock(
        ["Entity", "Location"],
        {"id": "loc_3", "name": "River", "body": "A flowing river"},
    )
    mock_client.graph.query.return_value = MagicMock(result_set=[[node1], [node2]])

    result = await connected_locations(mock_client, "loc_tavern")

    assert len(result) == 2
    assert all(isinstance(loc, LocationModel) for loc in result)

    cypher = mock_client.graph.query.call_args[0][0]
    assert "CONNECTS_TO" in cypher
    # Should use undirected pattern (no -> or <-)
    assert "->" not in cypher
    assert "<-" not in cypher


@pytest.mark.anyio
async def test_connected_locations_empty(mock_client: MagicMock) -> None:
    """connected_locations returns empty list when no connections."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    result = await connected_locations(mock_client, "loc_isolated")

    assert result == []


@pytest.mark.anyio
async def test_connected_locations_query_error(mock_client: MagicMock) -> None:
    """connected_locations raises QueryError on failure."""
    mock_client.graph.query.side_effect = Exception("network timeout")

    with pytest.raises(QueryError):
        await connected_locations(mock_client, "loc_tavern")


# --- scene_events ---


@pytest.mark.anyio
async def test_scene_events_returns_events(mock_client: MagicMock) -> None:
    """scene_events returns all events in a scene via HAS_EVENT."""
    node = _make_node_mock(
        ["Entity", "Event", "JoinEvent"],
        {
            "id": "evt_1", "name": "event1", "body": "Something happened",
            "scene_id": "scene_01", "gametime": 100, "walltime": "2024-01-01T00:00:00",
            "event_type": "JoinEvent", "metadata": "{}", "visibility": "public",
        },
    )
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    result = await scene_events(mock_client, "scene_01")

    assert len(result) == 1
    assert isinstance(result[0], EventModel)

    cypher = mock_client.graph.query.call_args[0][0]
    assert "HAS_EVENT" in cypher
    assert "ORDER BY" in cypher


@pytest.mark.anyio
async def test_scene_events_with_since_gametime(mock_client: MagicMock) -> None:
    """scene_events with since_gametime filters by gametime."""
    node = _make_node_mock(
        ["Entity", "Event", "JoinEvent"],
        {
            "id": "evt_2", "name": "event2", "body": "Later event",
            "scene_id": "scene_01", "gametime": 3700, "walltime": "2024-01-01T01:01:40",
            "event_type": "JoinEvent", "metadata": "{}", "visibility": "public",
        },
    )
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    result = await scene_events(mock_client, "scene_01", since_gametime=3600)

    assert len(result) == 1

    cypher = mock_client.graph.query.call_args[0][0]
    assert "gametime" in cypher
    assert "WHERE" in cypher


@pytest.mark.anyio
async def test_scene_events_returns_chat_messages(mock_client: MagicMock) -> None:
    """scene_events correctly deserializes ChatMessage events."""
    node = _make_node_mock(
        ["Entity", "Event", "ChatMessage"],
        {
            "id": "msg_1", "name": "msg", "body": "Hello!", "scene_id": "scene_01",
            "gametime": 200, "walltime": "2024-01-01T00:03:20",
            "event_type": "ChatMessage", "character_id": "char_1",
            "metadata": "{}", "visibility": "public",
        },
    )
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    result = await scene_events(mock_client, "scene_01")

    assert len(result) == 1
    assert isinstance(result[0], EventModel)
    assert result[0].event_type == EventType.CHAT_MESSAGE


@pytest.mark.anyio
async def test_scene_events_empty(mock_client: MagicMock) -> None:
    """scene_events returns empty list when scene has no events."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    result = await scene_events(mock_client, "scene_01")

    assert result == []


@pytest.mark.anyio
async def test_scene_events_query_error(mock_client: MagicMock) -> None:
    """scene_events raises QueryError on failure."""
    mock_client.graph.query.side_effect = Exception("network timeout")

    with pytest.raises(QueryError):
        await scene_events(mock_client, "scene_01")


# --- entity_graph ---


@pytest.mark.anyio
async def test_entity_graph_depth_1(mock_client: MagicMock) -> None:
    """entity_graph at depth=1 returns entity and directly connected entities."""
    center_node = _make_node_mock(
        ["Entity", "Character"],
        {"id": "char_alice", "name": "Alice", "body": "A warrior", "unseen": False, "inventory": []},
    )
    neighbor_node = _make_node_mock(
        ["Entity", "Location"],
        {"id": "loc_1", "name": "Tavern", "body": "A cozy tavern"},
    )
    mock_client.graph.query.return_value = MagicMock(
        result_set=[[center_node, [neighbor_node]]]
    )

    result = await entity_graph(mock_client, "char_alice", depth=1)

    assert isinstance(result["entity"], CharacterModel)
    assert result["entity"].id == "char_alice"
    assert len(result["related"]) == 1
    assert isinstance(result["related"][0], LocationModel)

    cypher = mock_client.graph.query.call_args[0][0]
    assert "1..1" in cypher or "*1" in cypher


@pytest.mark.anyio
async def test_entity_graph_depth_2(mock_client: MagicMock) -> None:
    """entity_graph at depth=2 returns two levels of connections."""
    center_node = _make_node_mock(
        ["Entity", "Character"],
        {"id": "char_alice", "name": "Alice", "body": "A warrior", "unseen": False, "inventory": []},
    )
    neighbor1 = _make_node_mock(
        ["Entity", "Location"],
        {"id": "loc_1", "name": "Tavern", "body": "A cozy tavern"},
    )
    neighbor2 = _make_node_mock(
        ["Entity", "Location"],
        {"id": "loc_2", "name": "Forest", "body": "A dark forest"},
    )
    mock_client.graph.query.return_value = MagicMock(
        result_set=[[center_node, [neighbor1, neighbor2]]]
    )

    result = await entity_graph(mock_client, "char_alice", depth=2)

    assert isinstance(result["entity"], CharacterModel)
    assert len(result["related"]) == 2

    cypher = mock_client.graph.query.call_args[0][0]
    assert "1..2" in cypher or "*2" in cypher


@pytest.mark.anyio
async def test_entity_graph_not_found(mock_client: MagicMock) -> None:
    """entity_graph returns None entity when center not found."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    result = await entity_graph(mock_client, "nonexistent")

    assert result["entity"] is None
    assert result["related"] == []


@pytest.mark.anyio
async def test_entity_graph_no_neighbors(mock_client: MagicMock) -> None:
    """entity_graph returns entity with empty related when no neighbors."""
    center_node = _make_node_mock(
        ["Entity", "Character"],
        {"id": "char_alice", "name": "Alice", "body": "A warrior", "unseen": False, "inventory": []},
    )
    mock_client.graph.query.return_value = MagicMock(
        result_set=[[center_node, []]]
    )

    result = await entity_graph(mock_client, "char_alice")

    assert isinstance(result["entity"], CharacterModel)
    assert result["related"] == []


@pytest.mark.anyio
async def test_entity_graph_query_error(mock_client: MagicMock) -> None:
    """entity_graph raises QueryError on failure."""
    mock_client.graph.query.side_effect = Exception("network timeout")

    with pytest.raises(QueryError):
        await entity_graph(mock_client, "char_alice")


@pytest.mark.anyio
async def test_entity_graph_invalid_depth(mock_client: MagicMock) -> None:
    """entity_graph raises ValueError for invalid depth."""
    with pytest.raises(ValueError, match="positive integer"):
        await entity_graph(mock_client, "char_alice", depth=0)

    with pytest.raises(ValueError, match="positive integer"):
        await entity_graph(mock_client, "char_alice", depth=-1)
