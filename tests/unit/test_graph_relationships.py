"""Unit tests for graph relationship operations."""
from typing import Any

import pytest
from unittest.mock import AsyncMock, MagicMock

from sidestage.graph.errors import EntityNotFoundError, QueryError
from sidestage.graph.relationships import (
    VALID_REL_TYPES,
    link,
    unlink,
    get_related,
    get_relationships,
)
from sidestage.models import CharacterModel, LocationModel


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


# --- Link ---


@pytest.mark.anyio
async def test_link_creates_typed_edge(mock_client: MagicMock) -> None:
    """link creates typed edge between two entities."""
    # First call: OPTIONAL MATCH to check existence - both nodes found
    mock_client.graph.query.side_effect = [
        MagicMock(result_set=[["char_1", "loc_1"]]),  # existence check
        MagicMock(result_set=[]),  # CREATE edge
    ]

    await link(mock_client, "char_1", "LOCATED_IN", "loc_1")

    assert mock_client.graph.query.call_count == 2
    create_cypher = mock_client.graph.query.call_args_list[1][0][0]
    assert "LOCATED_IN" in create_cypher
    assert "CREATE" in create_cypher


@pytest.mark.anyio
async def test_link_with_properties(mock_client: MagicMock) -> None:
    """link with properties stores properties on edge."""
    mock_client.graph.query.side_effect = [
        MagicMock(result_set=[["char_1", "loc_1"]]),  # existence check
        MagicMock(result_set=[]),  # CREATE edge
    ]

    await link(mock_client, "char_1", "LOCATED_IN", "loc_1", properties={"since": "2024-01-01"})

    create_cypher = mock_client.graph.query.call_args_list[1][0][0]
    assert "LOCATED_IN" in create_cypher
    assert "since" in create_cypher


@pytest.mark.anyio
async def test_link_raises_entity_not_found_for_source(mock_client: MagicMock) -> None:
    """link raises EntityNotFoundError if source doesn't exist."""
    mock_client.graph.query.return_value = MagicMock(result_set=[[None, "loc_1"]])

    with pytest.raises(EntityNotFoundError, match="char_1"):
        await link(mock_client, "char_1", "LOCATED_IN", "loc_1")


@pytest.mark.anyio
async def test_link_raises_entity_not_found_for_target(mock_client: MagicMock) -> None:
    """link raises EntityNotFoundError if target doesn't exist."""
    mock_client.graph.query.return_value = MagicMock(result_set=[["char_1", None]])

    with pytest.raises(EntityNotFoundError, match="loc_nonexistent"):
        await link(mock_client, "char_1", "LOCATED_IN", "loc_nonexistent")


@pytest.mark.anyio
async def test_link_raises_entity_not_found_no_results(mock_client: MagicMock) -> None:
    """link raises EntityNotFoundError if OPTIONAL MATCH returns empty result_set."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    with pytest.raises(EntityNotFoundError):
        await link(mock_client, "char_1", "LOCATED_IN", "loc_1")


@pytest.mark.anyio
async def test_link_invalid_rel_type_raises_value_error(mock_client: MagicMock) -> None:
    """link raises ValueError for invalid relationship type."""
    with pytest.raises(ValueError, match="Invalid relationship type"):
        await link(mock_client, "char_1", "INVALID_TYPE", "loc_1")


# --- Unlink ---


@pytest.mark.anyio
async def test_unlink_removes_edge(mock_client: MagicMock) -> None:
    """unlink removes edge between two entities."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    await unlink(mock_client, "char_1", "LOCATED_IN", "loc_1")

    cypher = mock_client.graph.query.call_args[0][0]
    assert "MATCH" in cypher
    assert "DELETE" in cypher
    assert "LOCATED_IN" in cypher


@pytest.mark.anyio
async def test_unlink_idempotent(mock_client: MagicMock) -> None:
    """unlink is idempotent (no error if edge doesn't exist)."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    # Should not raise
    await unlink(mock_client, "char_1", "LOCATED_IN", "loc_1")


@pytest.mark.anyio
async def test_unlink_invalid_rel_type_raises_value_error(mock_client: MagicMock) -> None:
    """unlink raises ValueError for invalid relationship type."""
    with pytest.raises(ValueError, match="Invalid relationship type"):
        await unlink(mock_client, "char_1", "BOGUS", "loc_1")


# --- Get Related ---


@pytest.mark.anyio
async def test_get_related_outgoing(mock_client: MagicMock) -> None:
    """get_related returns outgoing related entities."""
    node = _make_node_mock(
        ["Entity", "Location"],
        {"id": "loc_1", "name": "Tavern", "body": "A cozy tavern"},
    )
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    result = await get_related(mock_client, "char_1", "LOCATED_IN", direction="outgoing")

    assert len(result) == 1
    assert isinstance(result[0], LocationModel)
    assert result[0].id == "loc_1"

    cypher = mock_client.graph.query.call_args[0][0]
    assert "]->" in cypher


@pytest.mark.anyio
async def test_get_related_incoming(mock_client: MagicMock) -> None:
    """get_related returns incoming related entities."""
    node = _make_node_mock(
        ["Entity", "Character"],
        {"id": "char_1", "name": "Alice", "body": "A warrior", "unseen": False, "inventory": []},
    )
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    result = await get_related(mock_client, "loc_1", "LOCATED_IN", direction="incoming")

    assert len(result) == 1
    assert isinstance(result[0], CharacterModel)

    cypher = mock_client.graph.query.call_args[0][0]
    assert "<-[" in cypher


@pytest.mark.anyio
async def test_get_related_both_directions(mock_client: MagicMock) -> None:
    """get_related with direction='both' returns all related."""
    node1 = _make_node_mock(
        ["Entity", "Location"],
        {"id": "loc_2", "name": "Forest", "body": "A dark forest"},
    )
    node2 = _make_node_mock(
        ["Entity", "Location"],
        {"id": "loc_3", "name": "River", "body": "A flowing river"},
    )
    mock_client.graph.query.return_value = MagicMock(result_set=[[node1], [node2]])

    result = await get_related(mock_client, "loc_1", "CONNECTS_TO", direction="both")

    assert len(result) == 2

    cypher = mock_client.graph.query.call_args[0][0]
    # "both" uses undirected pattern: neither -> nor <- should appear
    assert "->" not in cypher
    assert "<-" not in cypher


@pytest.mark.anyio
async def test_get_related_empty(mock_client: MagicMock) -> None:
    """get_related returns empty list when no relationships."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    result = await get_related(mock_client, "char_1", "LOCATED_IN")

    assert result == []


@pytest.mark.anyio
async def test_get_related_connects_to_bidirectional(mock_client: MagicMock) -> None:
    """get_related with CONNECTS_TO and direction='both' finds bidirectional connections."""
    node1 = _make_node_mock(
        ["Entity", "Location"],
        {"id": "loc_2", "name": "Forest", "body": "A dark forest"},
    )
    mock_client.graph.query.return_value = MagicMock(result_set=[[node1]])

    result = await get_related(mock_client, "loc_1", "CONNECTS_TO", direction="both")

    assert len(result) == 1
    assert isinstance(result[0], LocationModel)


@pytest.mark.anyio
async def test_get_related_invalid_direction_raises(mock_client: MagicMock) -> None:
    """get_related raises ValueError for invalid direction."""
    with pytest.raises(ValueError, match="Invalid direction"):
        await get_related(mock_client, "char_1", "LOCATED_IN", direction="sideways")


@pytest.mark.anyio
async def test_get_related_invalid_rel_type_raises(mock_client: MagicMock) -> None:
    """get_related raises ValueError for invalid relationship type."""
    with pytest.raises(ValueError, match="Invalid relationship type"):
        await get_related(mock_client, "char_1", "BOGUS")


# --- Get Relationships ---


@pytest.mark.anyio
async def test_get_relationships_returns_all(mock_client: MagicMock) -> None:
    """get_relationships returns all relationships for an entity."""
    # Outgoing query result
    outgoing_result = MagicMock(result_set=[
        ["LOCATED_IN", "loc_1", "Tavern", {}],
    ])
    # Incoming query result
    incoming_result = MagicMock(result_set=[
        ["PARTICIPATES_IN", "scene_1", "Battle", {}],
    ])
    mock_client.graph.query.side_effect = [outgoing_result, incoming_result]

    result = await get_relationships(mock_client, "char_1")

    assert len(result) == 2


@pytest.mark.anyio
async def test_get_relationships_includes_expected_keys(mock_client: MagicMock) -> None:
    """get_relationships includes rel_type, direction, target info."""
    outgoing_result = MagicMock(result_set=[
        ["LOCATED_IN", "loc_1", "Tavern", {"since": "2024-01-01"}],
    ])
    incoming_result = MagicMock(result_set=[])
    mock_client.graph.query.side_effect = [outgoing_result, incoming_result]

    result = await get_relationships(mock_client, "char_1")

    assert len(result) == 1
    rel = result[0]
    assert rel["rel_type"] == "LOCATED_IN"
    assert rel["direction"] == "outgoing"
    assert rel["target_id"] == "loc_1"
    assert rel["target_name"] == "Tavern"
    assert rel["properties"] == {"since": "2024-01-01"}


@pytest.mark.anyio
async def test_get_relationships_empty(mock_client: MagicMock) -> None:
    """get_relationships returns empty list for entity with no relationships."""
    mock_client.graph.query.side_effect = [
        MagicMock(result_set=[]),
        MagicMock(result_set=[]),
    ]

    result = await get_relationships(mock_client, "char_1")

    assert result == []


# --- QueryError Tests ---


@pytest.mark.anyio
async def test_link_query_error_on_create(mock_client: MagicMock) -> None:
    """link raises QueryError when the CREATE query fails."""
    mock_client.graph.query.side_effect = [
        MagicMock(result_set=[["char_1", "loc_1"]]),  # existence check ok
        Exception("network timeout"),  # CREATE fails
    ]

    with pytest.raises(QueryError, match="Failed to create"):
        await link(mock_client, "char_1", "LOCATED_IN", "loc_1")


@pytest.mark.anyio
async def test_unlink_query_error(mock_client: MagicMock) -> None:
    """unlink raises QueryError when the DELETE query fails."""
    mock_client.graph.query.side_effect = Exception("network timeout")

    with pytest.raises(QueryError, match="Failed to unlink"):
        await unlink(mock_client, "char_1", "LOCATED_IN", "loc_1")


@pytest.mark.anyio
async def test_get_related_query_error(mock_client: MagicMock) -> None:
    """get_related raises QueryError when the query fails."""
    mock_client.graph.query.side_effect = Exception("network timeout")

    with pytest.raises(QueryError, match="Failed to get related"):
        await get_related(mock_client, "char_1", "LOCATED_IN")


@pytest.mark.anyio
async def test_get_relationships_query_error(mock_client: MagicMock) -> None:
    """get_relationships raises QueryError when a query fails."""
    mock_client.graph.query.side_effect = Exception("network timeout")

    with pytest.raises(QueryError, match="Failed to get relationships"):
        await get_relationships(mock_client, "char_1")
