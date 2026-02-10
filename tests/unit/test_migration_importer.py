"""Tests for migration/importer.py -- import campaign from parsed data into FalkorDB."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from sidestage.health import CampaignHealth, HealthStatus
from sidestage.memory.models import Memory, MemoryType
from sidestage.migration.importer import import_campaign
from sidestage.migration.models import MigrationValidationIssue, ParseResult
from sidestage.models import CharacterModel, EntityModel, EventModel, EventType, ItemModel, LocationModel, SceneModel


# --- Fixtures ---


@pytest.fixture
def mock_graph_client() -> MagicMock:
    """Mock GraphClient with graph.query and graph.delete capabilities."""
    client = MagicMock()
    client.graph = AsyncMock()
    client.graph.query = AsyncMock(return_value=MagicMock(result_set=[]))
    client.graph.delete = AsyncMock()
    client.db = MagicMock()
    client.graph_name = "test_campaign"
    client.db.select_graph = MagicMock(return_value=client.graph)
    return client


@pytest.fixture
def mock_campaign(mock_graph_client: MagicMock, tmp_path: Path) -> MagicMock:
    """Mock Campaign object with graph_client, storage, health, and campaign_dir."""
    campaign = MagicMock()
    campaign.graph_client = mock_graph_client
    campaign.campaign_dir = tmp_path
    campaign.health = CampaignHealth()
    campaign.storage = MagicMock()
    campaign.storage.get_scene = MagicMock(return_value=None)
    campaign.storage.update_scene = MagicMock()
    campaign.storage.add_scene = MagicMock()
    campaign.storage.add_event = MagicMock()
    campaign.name = "test_campaign"
    campaign.config = MagicMock()
    campaign.config.graph = MagicMock()
    campaign.config.graph.vector_dimension = None
    return campaign


@pytest.fixture
def sample_entities() -> list[EntityModel]:
    """Return a list of representative EntityModel objects."""
    return [
        CharacterModel(
            name="Eldric the Bold", body="A brave warrior.", id="char_eldric",
            location_id="loc_tavern", inventory=["item_sword"],
        ),
        CharacterModel(
            name="Alice the Merchant", body="A shrewd merchant.", id="char_alice",
        ),
        LocationModel(
            name="The Rusty Tavern", body="A dingy tavern.", id="loc_tavern",
            connected_locations=["loc_square"],
        ),
        LocationModel(
            name="Town Square", body="The town square.", id="loc_square",
            connected_locations=["loc_tavern"],
        ),
        ItemModel(name="Flame Tongue Sword", body="A fiery blade.", id="item_sword"),
        SceneModel(
            name="Tavern Brawl", body="A brawl erupts.", id="scene_brawl",
            location_id="loc_tavern", events=["evt_join"],
        ),
        EventModel(
            name="Eldric Joins Brawl", body="Eldric enters the fray.",
            id="evt_join", scene_id="scene_brawl", gametime=3600,
            walltime="2026-01-15T14:30:00Z", actor_id="actor_1",
            event_type=EventType.JOIN,
        ),
    ]


@pytest.fixture
def sample_memories() -> list[Memory]:
    """Return a list of sample Memory objects."""
    return [
        Memory(
            id="mem_tavern_brawl", content="The brawl was fierce.",
            memory_type=MemoryType.SCENE, visibility="private",
            owner_id="char_eldric", target_id="scene_brawl",
            gametime=3600, created_at=1706000000.0, updated_at=1706000000.0,
        ),
        Memory(
            id="mem_knows_alice", content="Eldric met Alice.",
            memory_type=MemoryType.CHARACTER, visibility="common",
            owner_id="char_eldric", target_id="char_alice",
            gametime=1800, created_at=1705900000.0, updated_at=1705900000.0,
        ),
        Memory(
            id="mem_trade_secret", content="The tavern has a hidden cellar.",
            memory_type=MemoryType.WORLD_FACT, visibility="private",
            owner_id="char_alice", target_id="loc_tavern",
        ),
    ]


@pytest.fixture
def sample_parse_result(sample_entities: list[EntityModel], sample_memories: list[Memory]) -> ParseResult:
    """Return a ParseResult with representative entities, memories, and chatlogs."""
    return ParseResult(
        entities=sample_entities,
        memories=sample_memories,
        chatlogs={
            "scene_brawl": [
                '[2026-01-15T14:30:00Z] (char_eldric) Eldric the Bold: "I challenge you!"',
                '[2026-01-15T14:30:05Z] (char_alice) Alice the Merchant: "You\'ll regret that."',
            ],
        },
        errors=[],
        warnings=[],
    )


@pytest.fixture
def empty_parse_result() -> ParseResult:
    """Return an empty ParseResult."""
    return ParseResult(entities=[], memories=[], chatlogs={}, errors=[])


# --- Concurrency guard tests ---


@pytest.mark.anyio
async def test_sets_health_degraded_before_import(mock_campaign: MagicMock, sample_parse_result: ParseResult, ) -> None:
    """import_campaign sets campaign.health to DEGRADED before starting graph operations."""
    health_states: list[HealthStatus] = []

    original_delete = mock_campaign.graph_client.graph.delete

    async def capture_health_on_delete() -> None:
        health_states.append(mock_campaign.health.status)
        return await original_delete()

    mock_campaign.graph_client.graph.delete = capture_health_on_delete

    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
                    await import_campaign(mock_campaign, sample_parse_result)

    assert HealthStatus.DEGRADED in health_states


@pytest.mark.anyio
async def test_restores_health_healthy_after_successful_import(mock_campaign: MagicMock, sample_parse_result: ParseResult, ) -> None:
    """After a successful import, campaign.health is restored to HEALTHY."""
    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
                    result = await import_campaign(mock_campaign, sample_parse_result)

    assert mock_campaign.health.status == HealthStatus.HEALTHY
    assert result.phase == "complete"


@pytest.mark.anyio
async def test_restores_health_healthy_after_failed_import(mock_campaign: MagicMock, sample_parse_result: ParseResult, ) -> None:
    """If import fails (e.g., graph drop raises), health is still restored to HEALTHY."""
    mock_campaign.graph_client.graph.delete = AsyncMock(side_effect=RuntimeError("DB down"))

    result = await import_campaign(mock_campaign, sample_parse_result)

    assert mock_campaign.health.status == HealthStatus.HEALTHY
    assert result.phase == "failed"
    assert any("Graph drop failed" in e for e in result.errors)


# --- Graph lifecycle tests ---


@pytest.mark.anyio
async def test_drops_and_recreates_graph(mock_campaign: MagicMock, sample_parse_result: ParseResult, ) -> None:
    """import_campaign calls graph.delete() then db.select_graph() and initialize_schema()."""
    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock) as mock_init:
                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
                    await import_campaign(mock_campaign, sample_parse_result)

    mock_campaign.graph_client.graph.delete.assert_awaited_once()
    mock_campaign.graph_client.db.select_graph.assert_called_once_with("test_campaign")
    mock_init.assert_awaited_once_with(
        mock_campaign.graph_client, vector_dimension=None,
    )


@pytest.mark.anyio
async def test_graph_drop_failure_aborts_import(mock_campaign: MagicMock, sample_parse_result: ParseResult, ) -> None:
    """If graph.delete() raises, the import aborts and returns a failed result."""
    mock_campaign.graph_client.graph.delete = AsyncMock(side_effect=RuntimeError("Connection lost"))

    result = await import_campaign(mock_campaign, sample_parse_result)

    assert result.phase == "failed"
    assert result.processed_entities == 0
    assert result.processed_memories == 0


# --- EntityModel insertion tests ---


@pytest.mark.anyio
async def test_inserts_all_entities_via_create_entity(mock_campaign: MagicMock, sample_parse_result: ParseResult, ) -> None:
    """Every entity in the ParseResult is inserted via graph create_entity()."""
    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock) as mock_create:
        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
                    result = await import_campaign(mock_campaign, sample_parse_result)

    assert mock_create.call_count == len(sample_parse_result.entities)
    assert result.processed_entities == len(sample_parse_result.entities)


# --- Relationship creation tests ---


@pytest.mark.anyio
async def test_creates_located_in_edges_for_characters(mock_campaign: MagicMock, ) -> None:
    """Characters with a location_id get a LOCATED_IN edge to that location."""
    parse_result = ParseResult(
        entities=[
            CharacterModel(name="A", body="", id="c1", location_id="loc1"),
            LocationModel(name="B", body="", id="loc1"),
        ],
        memories=[], chatlogs={}, errors=[],
    )

    link_calls: list[Any] = []
    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
        with patch("sidestage.migration.importer.link", new_callable=AsyncMock) as mock_link:
            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
                    await import_campaign(mock_campaign, parse_result)
            link_calls = mock_link.call_args_list

    located_in_calls = [c for c in link_calls if c[0][2] == "LOCATED_IN"]
    assert len(located_in_calls) == 1
    assert located_in_calls[0] == call(mock_campaign.graph_client, "c1", "LOCATED_IN", "loc1")


@pytest.mark.anyio
async def test_creates_connects_to_edges_deduplicated(mock_campaign: MagicMock, ) -> None:
    """CONNECTS_TO edges are created once per pair, not twice for A->B and B->A."""
    parse_result = ParseResult(
        entities=[
            LocationModel(name="A", body="", id="loc1", connected_locations=["loc2"]),
            LocationModel(name="B", body="", id="loc2", connected_locations=["loc1"]),
        ],
        memories=[], chatlogs={}, errors=[],
    )

    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
        with patch("sidestage.migration.importer.link", new_callable=AsyncMock) as mock_link:
            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
                    await import_campaign(mock_campaign, parse_result)

    connects_to_calls = [c for c in mock_link.call_args_list if c[0][2] == "CONNECTS_TO"]
    assert len(connects_to_calls) == 1


@pytest.mark.anyio
async def test_creates_at_location_edges_for_scenes(mock_campaign: MagicMock, ) -> None:
    """Scenes with a location_id get an AT_LOCATION edge to that location."""
    parse_result = ParseResult(
        entities=[
            SceneModel(name="S", body="", id="s1", location_id="loc1"),
            LocationModel(name="L", body="", id="loc1"),
        ],
        memories=[], chatlogs={}, errors=[],
    )

    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
        with patch("sidestage.migration.importer.link", new_callable=AsyncMock) as mock_link:
            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
                    await import_campaign(mock_campaign, parse_result)

    at_location_calls = [c for c in mock_link.call_args_list if c[0][2] == "AT_LOCATION"]
    assert len(at_location_calls) == 1
    assert at_location_calls[0] == call(mock_campaign.graph_client, "s1", "AT_LOCATION", "loc1")


@pytest.mark.anyio
async def test_creates_has_event_edges_for_events(mock_campaign: MagicMock, ) -> None:
    """Events with a scene_id get a HAS_EVENT edge from the scene."""
    parse_result = ParseResult(
        entities=[
            SceneModel(name="S", body="", id="s1"),
            EventModel(
                name="E", body="", id="e1", scene_id="s1",
                gametime=0, walltime="2026-01-01T00:00:00Z", actor_id="a1",
                event_type=EventType.JOIN,
            ),
        ],
        memories=[], chatlogs={}, errors=[],
    )

    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
        with patch("sidestage.migration.importer.link", new_callable=AsyncMock) as mock_link:
            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
                    await import_campaign(mock_campaign, parse_result)

    has_event_calls = [c for c in mock_link.call_args_list if c[0][2] == "HAS_EVENT"]
    assert len(has_event_calls) == 1
    assert has_event_calls[0] == call(mock_campaign.graph_client, "s1", "HAS_EVENT", "e1")


# --- Memory insertion tests ---


@pytest.mark.anyio
async def test_inserts_memories_via_graph_query(mock_campaign: MagicMock, sample_parse_result: ParseResult, ) -> None:
    """All memories from ParseResult are inserted via graph Cypher queries."""
    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
                    result = await import_campaign(mock_campaign, sample_parse_result)

    assert result.processed_memories == len(sample_parse_result.memories)
    # Memory insertion uses graph.query for Cypher CREATE (not count verification)
    memory_query_calls = [
        c for c in mock_campaign.graph_client.graph.query.call_args_list
        if c[0] and "CREATE" in str(c[0][0]) and "Memory" in str(c[0][0])
    ]
    assert len(memory_query_calls) == len(sample_parse_result.memories)


@pytest.mark.anyio
async def test_skips_embedding_generation_during_import(mock_campaign: MagicMock, sample_parse_result: ParseResult, ) -> None:
    """During import, health is DEGRADED so is_embedding_available returns False."""
    embedding_available_during_import: list[bool] = []

    original_delete = mock_campaign.graph_client.graph.delete

    async def capture_embedding_state() -> None:
        embedding_available_during_import.append(mock_campaign.health.is_embedding_available)
        return await original_delete()

    mock_campaign.graph_client.graph.delete = capture_embedding_state

    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
                    await import_campaign(mock_campaign, sample_parse_result)

    assert False in embedding_available_during_import


# --- Chat log restoration tests ---


@pytest.mark.anyio
async def test_restores_chat_logs_via_storage(mock_campaign: MagicMock, ) -> None:
    """Chat logs from ParseResult are restored via campaign.storage."""
    parse_result = ParseResult(
        entities=[
            SceneModel(name="Tavern Brawl", body="", id="scene_brawl"),
        ],
        memories=[],
        chatlogs={
            "scene_brawl": [
                '[2026-01-15T14:30:00Z] (char_eldric) Eldric the Bold: "Hello!"',
            ],
        },
        errors=[],
    )

    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
                    await import_campaign(mock_campaign, parse_result)

    # Storage should have been called to save individual events
    assert mock_campaign.storage.add_event.called


# --- Post-import verification tests ---


@pytest.mark.anyio
async def test_verifies_entity_counts_after_import(mock_campaign: MagicMock, sample_parse_result: ParseResult, ) -> None:
    """After import, the importer queries entity counts and includes them in the result."""
    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]) as mock_list:
                    result = await import_campaign(mock_campaign, sample_parse_result)

    # list_entities is called for verification
    mock_list.assert_awaited()
    assert result.total_entities == len(sample_parse_result.entities)


@pytest.mark.anyio
async def test_clears_active_scenes_after_import(mock_campaign: MagicMock, sample_parse_result: ParseResult, ) -> None:
    """Active scenes dict is cleared after import completes."""
    active_scenes: dict[str, MagicMock] = {"scene_1": MagicMock(), "scene_2": MagicMock()}

    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
                    await import_campaign(
                        mock_campaign, sample_parse_result,
                        active_scenes=active_scenes,
                    )

    assert len(active_scenes) == 0


# --- Empty / edge case tests ---


@pytest.mark.anyio
async def test_empty_parse_result_still_drops_graph(mock_campaign: MagicMock, empty_parse_result: ParseResult, ) -> None:
    """An empty parse result still drops and recreates the graph (clean slate)."""
    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
                    result = await import_campaign(mock_campaign, empty_parse_result)

    mock_campaign.graph_client.graph.delete.assert_awaited_once()
    assert result.phase == "complete"
    assert result.processed_entities == 0
    assert result.processed_memories == 0


@pytest.mark.anyio
async def test_no_graph_client_returns_failed(mock_campaign: MagicMock, sample_parse_result: ParseResult, ) -> None:
    """If campaign.graph_client is None, return a failed result immediately."""
    mock_campaign.graph_client = None

    result = await import_campaign(mock_campaign, sample_parse_result)

    assert result.phase == "failed"
    assert any("graph_client" in e.lower() or "no graph" in e.lower() for e in result.errors)


@pytest.mark.anyio
async def test_import_without_active_scenes(mock_campaign: MagicMock, sample_parse_result: ParseResult) -> None:
    """Import works fine when active_scenes is not provided."""
    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
                    result = await import_campaign(mock_campaign, sample_parse_result)

    assert result.phase == "complete"
