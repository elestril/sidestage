"""Unit tests for graph entity CRUD operations."""
from typing import Any

import pytest
from unittest.mock import AsyncMock, MagicMock

from sidestage.models import CharacterModel, LocationModel, ItemModel, SceneModel, EventModel, EventType
from sidestage.graph.errors import DuplicateEntityError, EntityNotFoundError, QueryError
from sidestage.graph.entities import (
    create_entity,
    get_entity,
    update_entity,
    delete_entity,
    list_entities,
    find_entities,
)


# --- Fixtures ---


@pytest.fixture
def mock_client() -> MagicMock:
    """Creates a MagicMock GraphClient with graph.query as AsyncMock."""
    client = MagicMock()
    client.graph = MagicMock()
    client.graph.query = AsyncMock()
    return client


@pytest.fixture
def sample_character() -> CharacterModel:
    return CharacterModel(
        id="char_1", name="Alice", body="A brave warrior",
        location_id="loc_1", inventory=["item_sword"],
    )


@pytest.fixture
def sample_location() -> LocationModel:
    return LocationModel(
        id="loc_1", name="Tavern", body="A cozy tavern",
        connected_locations=["loc_2"],
    )


def _make_node_mock(labels: list[str], properties: dict[str, Any]) -> MagicMock:
    """Helper to create a mock graph node."""
    node = MagicMock()
    node.labels = labels
    node.properties = properties
    return node


# --- Create ---


@pytest.mark.anyio
async def test_create_entity_character_cypher(mock_client: MagicMock, sample_character: CharacterModel) -> None:
    """create_entity with CharacterModel generates correct Cypher with :Entity:Character labels."""
    mock_client.graph.query.return_value = MagicMock(result_set=[[]])

    await create_entity(mock_client, sample_character)

    call_args = mock_client.graph.query.call_args
    cypher = call_args[0][0]
    assert ":Entity:Character" in cypher
    assert "CREATE" in cypher


@pytest.mark.anyio
async def test_create_entity_location_excludes_connected_locations(mock_client: MagicMock, sample_location: LocationModel) -> None:
    """create_entity with LocationModel does not include connected_locations in Cypher properties."""
    mock_client.graph.query.return_value = MagicMock(result_set=[[]])

    await create_entity(mock_client, sample_location)

    call_args = mock_client.graph.query.call_args
    params = call_args[1].get("params", call_args[0][1] if len(call_args[0]) > 1 else {})
    assert "connected_locations" not in params


@pytest.mark.anyio
async def test_create_entity_chat_message_labels(mock_client: MagicMock) -> None:
    """create_entity with EventModel CHAT_MESSAGE generates Cypher with :Entity:Event:ChatMessage labels."""
    msg = EventModel(
        id="m1", name="msg", body="desc", scene_id="s1",
        gametime=100, walltime="2024-01-01T00:00:00",
        event_type=EventType.CHAT_MESSAGE, character_id="c1",
    )
    mock_client.graph.query.return_value = MagicMock(result_set=[[]])

    await create_entity(mock_client, msg)

    cypher = mock_client.graph.query.call_args[0][0]
    assert ":Entity:Event:ChatMessage" in cypher


@pytest.mark.anyio
async def test_create_entity_raises_duplicate_on_constraint_violation(mock_client: MagicMock, sample_character: CharacterModel) -> None:
    """create_entity raises DuplicateEntityError on unique constraint violation."""
    mock_client.graph.query.side_effect = Exception("unique constraint")

    with pytest.raises(DuplicateEntityError):
        await create_entity(mock_client, sample_character)


@pytest.mark.anyio
async def test_create_entity_returns_entity(mock_client: MagicMock, sample_character: CharacterModel) -> None:
    """create_entity returns the created entity."""
    mock_client.graph.query.return_value = MagicMock(result_set=[[]])

    result = await create_entity(mock_client, sample_character)

    assert result is sample_character


# --- Get ---


@pytest.mark.anyio
async def test_get_entity_returns_correct_entity(mock_client: MagicMock) -> None:
    """get_entity returns correct entity when node is found."""
    node = _make_node_mock(
        ["Entity", "Character"],
        {"id": "c1", "name": "Alice", "body": "desc", "unseen": False, "inventory": []},
    )
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    entity = await get_entity(mock_client, "c1")

    assert isinstance(entity, CharacterModel)
    assert entity.id == "c1"
    assert entity.name == "Alice"


@pytest.mark.anyio
async def test_get_entity_returns_none_when_not_found(mock_client: MagicMock) -> None:
    """get_entity returns None when result_set is empty."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    result = await get_entity(mock_client, "nonexistent")

    assert result is None


@pytest.mark.anyio
async def test_get_entity_chat_message_reconstructs_correctly(mock_client: MagicMock) -> None:
    """get_entity for ChatMessage node reconstructs as EventModel with event_type=CHAT_MESSAGE."""
    node = _make_node_mock(
        ["Entity", "Event", "ChatMessage"],
        {
            "id": "m1", "name": "msg", "body": "desc", "scene_id": "s1",
            "gametime": 100, "walltime": "2024-01-01T00:00:00",
            "event_type": "ChatMessage", "character_id": "c1",
            "metadata": "{}", "visibility": "public",
        },
    )
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    entity = await get_entity(mock_client, "m1")

    assert isinstance(entity, EventModel)
    assert entity.event_type == EventType.CHAT_MESSAGE


@pytest.mark.anyio
async def test_get_entity_cypher(mock_client: MagicMock) -> None:
    """get_entity generates correct MATCH Cypher."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    await get_entity(mock_client, "c1")

    cypher = mock_client.graph.query.call_args[0][0]
    assert "MATCH" in cypher
    assert ":Entity" in cypher
    assert "RETURN" in cypher


# --- Update ---


@pytest.mark.anyio
async def test_update_entity_sets_specified_properties(mock_client: MagicMock) -> None:
    """update_entity generates Cypher SET for specified properties only."""
    node = _make_node_mock(
        ["Entity", "Character"],
        {"id": "c1", "name": "Bob", "body": "desc", "unseen": False, "inventory": []},
    )
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    await update_entity(mock_client, "c1", {"name": "Bob"})

    cypher = mock_client.graph.query.call_args[0][0]
    assert "SET" in cypher
    assert "n.name" in cypher
    assert "n.body" not in cypher


@pytest.mark.anyio
async def test_update_entity_empty_updates_raises(mock_client: MagicMock) -> None:
    """update_entity raises QueryError when updates dict is empty."""
    with pytest.raises(QueryError, match="No updates"):
        await update_entity(mock_client, "c1", {})


@pytest.mark.anyio
async def test_update_entity_invalid_key_raises(mock_client: MagicMock) -> None:
    """update_entity raises QueryError for unknown property keys."""
    with pytest.raises(QueryError, match="Unknown property"):
        await update_entity(mock_client, "c1", {"nonexistent_field": "value"})


@pytest.mark.anyio
async def test_update_entity_raises_not_found(mock_client: MagicMock) -> None:
    """update_entity raises EntityNotFoundError when node not found."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    with pytest.raises(EntityNotFoundError):
        await update_entity(mock_client, "nonexistent", {"name": "Bob"})


@pytest.mark.anyio
async def test_update_entity_returns_updated_entity(mock_client: MagicMock) -> None:
    """update_entity returns the updated entity."""
    node = _make_node_mock(
        ["Entity", "Character"],
        {"id": "c1", "name": "Bob", "body": "desc", "unseen": False, "inventory": []},
    )
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    result = await update_entity(mock_client, "c1", {"name": "Bob"})

    assert isinstance(result, CharacterModel)
    assert result.name == "Bob"


# --- Delete ---


@pytest.mark.anyio
async def test_delete_entity_uses_detach_delete(mock_client: MagicMock) -> None:
    """delete_entity generates Cypher MATCH + DETACH DELETE."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    await delete_entity(mock_client, "c1")

    cypher = mock_client.graph.query.call_args[0][0]
    assert "DETACH DELETE" in cypher


@pytest.mark.anyio
async def test_delete_entity_nonexistent_succeeds_silently(mock_client: MagicMock) -> None:
    """delete_entity for non-existent id succeeds silently."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    # Should not raise
    await delete_entity(mock_client, "nonexistent")


# --- List ---


@pytest.mark.anyio
async def test_list_entities_no_filter(mock_client: MagicMock) -> None:
    """list_entities without type filter queries MATCH (n:Entity) RETURN n."""
    node1 = _make_node_mock(["Entity", "Character"], {"id": "c1", "name": "Alice", "body": "desc", "unseen": False, "inventory": []})
    node2 = _make_node_mock(["Entity", "Location"], {"id": "l1", "name": "Tavern", "body": "desc"})
    mock_client.graph.query.return_value = MagicMock(result_set=[[node1], [node2]])

    result = await list_entities(mock_client)

    assert len(result) == 2
    assert isinstance(result[0], CharacterModel)
    assert isinstance(result[1], LocationModel)


@pytest.mark.anyio
async def test_list_entities_with_type_filter(mock_client: MagicMock) -> None:
    """list_entities with type filter queries MATCH (n:Character) RETURN n."""
    node = _make_node_mock(["Entity", "Character"], {"id": "c1", "name": "Alice", "body": "desc", "unseen": False, "inventory": []})
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    result = await list_entities(mock_client, entity_type="Character")

    cypher = mock_client.graph.query.call_args[0][0]
    assert ":Character" in cypher
    assert len(result) == 1


@pytest.mark.anyio
async def test_list_entities_returns_empty_list(mock_client: MagicMock) -> None:
    """list_entities returns empty list when result_set is empty."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    result = await list_entities(mock_client)

    assert result == []


@pytest.mark.anyio
async def test_list_entities_invalid_type_raises(mock_client: MagicMock) -> None:
    """list_entities raises QueryError for unknown entity type."""
    with pytest.raises(QueryError, match="Unknown entity type"):
        await list_entities(mock_client, entity_type="Bogus")


# --- Create (non-constraint error) ---


@pytest.mark.anyio
async def test_create_entity_non_constraint_error_raises_query_error(mock_client: MagicMock, sample_character: CharacterModel) -> None:
    """create_entity raises QueryError for non-constraint exceptions."""
    mock_client.graph.query.side_effect = Exception("network timeout")

    with pytest.raises(QueryError, match="Failed to create"):
        await create_entity(mock_client, sample_character)


# --- Find ---


@pytest.mark.anyio
async def test_find_entities_single_filter(mock_client: MagicMock) -> None:
    """find_entities with name='Alice' generates WHERE clause."""
    node = _make_node_mock(["Entity", "Character"], {"id": "c1", "name": "Alice", "body": "desc", "unseen": False, "inventory": []})
    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])

    result = await find_entities(mock_client, name="Alice")

    cypher = mock_client.graph.query.call_args[0][0]
    assert "WHERE" in cypher
    assert "n.name" in cypher
    assert len(result) == 1


@pytest.mark.anyio
async def test_find_entities_multiple_filters(mock_client: MagicMock) -> None:
    """find_entities with multiple filters generates AND conditions."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    await find_entities(mock_client, name="Alice", unseen=True)

    cypher = mock_client.graph.query.call_args[0][0]
    assert "AND" in cypher


@pytest.mark.anyio
async def test_find_entities_returns_empty_list(mock_client: MagicMock) -> None:
    """find_entities returns empty list when no matches."""
    mock_client.graph.query.return_value = MagicMock(result_set=[])

    result = await find_entities(mock_client, name="Nobody")

    assert result == []
