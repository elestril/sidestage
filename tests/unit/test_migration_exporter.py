"""Tests for migration/exporter.py -- backup campaign to markdown directory."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sidestage.memory.models import Memory, MemoryType
from sidestage.schemas import Character, Entity, Event, Item, Location, Scene


# --- Fixtures ---


@pytest.fixture
def mock_graph_client() -> MagicMock:
    """Mock GraphClient with query capabilities."""
    client = MagicMock()
    client.graph = MagicMock()
    client.graph.query = AsyncMock(return_value=MagicMock(result_set=[]))
    return client


@pytest.fixture
def mock_campaign(mock_graph_client: MagicMock, tmp_path: Path) -> MagicMock:
    """Mock Campaign object with graph_client, storage, health, and campaign_dir."""
    campaign = MagicMock()
    campaign.graph_client = mock_graph_client
    campaign.campaign_dir = tmp_path
    campaign.storage = MagicMock()
    campaign.storage.get_scene = MagicMock(return_value=None)
    campaign.health = MagicMock()
    return campaign


@pytest.fixture
def sample_entities() -> list[Entity]:
    """Return a list of sample Entity objects (Character, Location, Item, Scene, Event)."""
    return [
        Character(
            id="char_eldric",
            name="Eldric the Bold",
            body="A brave warrior.",
            unseen=False,
            inventory=["item_sword"],
        ),
        Character(
            id="char_mira",
            name="Mira",
            body="A cunning rogue.",
            unseen=True,
        ),
        Location(
            id="loc_tavern",
            name="Rusty Tavern",
            body="A dimly lit tavern.",
        ),
        Location(
            id="loc_forest",
            name="Dark Forest",
            body="Tall trees block the sun.",
        ),
        Item(
            id="item_sword",
            name="Flame Tongue",
            body="A sword wreathed in fire.",
        ),
        Scene(
            id="scene_01",
            name="Tavern Brawl",
            body="A fight breaks out.",
            current_gametime=100,
        ),
        Event(
            id="event_01",
            name="Door Opens",
            body="The door swings open.",
            scene_id="scene_01",
            gametime=50,
            walltime="2024-01-01T12:00:00",
        ),
    ]


@pytest.fixture
def sample_memories() -> list[Memory]:
    """Return a list of sample Memory objects with various owner_id/target_id combos."""
    return [
        Memory(
            id="mem_001",
            content="Eldric remembers the tavern fondly.",
            memory_type=MemoryType.CHARACTER,
            visibility="private",
            owner_id="char_eldric",
            target_id="loc_tavern",
            created_at=1000.0,
            updated_at=1000.0,
        ),
        Memory(
            id="mem_002",
            content="The tavern is known for its ale.",
            memory_type=MemoryType.WORLD_FACT,
            visibility="common",
            owner_id=None,
            target_id="loc_tavern",
            created_at=1001.0,
            updated_at=1001.0,
        ),
        Memory(
            id="mem_003",
            content="A scene memory about the brawl.",
            memory_type=MemoryType.SCENE,
            visibility="common",
            owner_id=None,
            target_id="scene_01",
            created_at=1002.0,
            updated_at=1002.0,
        ),
    ]


def _setup_list_entities(mock_campaign: MagicMock, entities: list[Entity]) -> Any:
    """Helper to set up list_entities mock to return given entities."""
    # Patch at the module level where it's imported
    return patch(
        "sidestage.migration.exporter.list_entities",
        new_callable=AsyncMock,
        return_value=entities,
    )


def _setup_memories_query(mock_campaign: MagicMock, memories: list[Memory]) -> None:
    """Helper to set up memory query mock."""
    # The exporter queries MATCH (m:Memory) RETURN m
    nodes = []
    for mem in memories:
        node = MagicMock()
        node.properties = mem.model_dump()
        nodes.append([node])

    mock_campaign.graph_client.graph.query = AsyncMock(
        return_value=MagicMock(result_set=nodes)
    )


def _setup_get_related(return_map: dict[tuple[str, str], list[Entity]] | None = None) -> Any:
    """Patch get_related to return entities from a mapping."""
    if return_map is None:
        return_map = {}

    async def _mock_get_related(client: Any, entity_id: str, rel_type: str, direction: str = "outgoing") -> list[Entity]:
        return return_map.get((entity_id, rel_type), [])

    return patch(
        "sidestage.migration.exporter.get_related",
        side_effect=_mock_get_related,
    )


# --- Entity export tests ---


@pytest.mark.anyio
async def test_queries_all_entities(mock_campaign: MagicMock, sample_entities: list[Entity]) -> None:
    """export_campaign calls list_entities(client) to retrieve all entities."""
    from sidestage.migration.exporter import export_campaign

    with _setup_list_entities(mock_campaign, sample_entities) as mock_list, \
         _setup_get_related():
        _setup_memories_query(mock_campaign, [])
        result = await export_campaign(mock_campaign)

    mock_list.assert_called_once_with(mock_campaign.graph_client)
    assert result.total_entities == len(sample_entities)


@pytest.mark.anyio
async def test_queries_all_memories(mock_campaign: MagicMock, sample_memories: list[Memory]) -> None:
    """export_campaign queries all Memory nodes from the graph."""
    from sidestage.migration.exporter import export_campaign

    with _setup_list_entities(mock_campaign, []), \
         _setup_get_related():
        _setup_memories_query(mock_campaign, sample_memories)
        result = await export_campaign(mock_campaign)

    assert result.total_memories == len(sample_memories)


@pytest.mark.anyio
async def test_retrieves_chat_logs_for_scenes(mock_campaign: MagicMock, sample_entities: list[Entity]) -> None:
    """For each Scene entity, export_campaign reads messages from storage."""
    from sidestage.migration.exporter import export_campaign
    from sidestage.schemas import ChatMessage as CM

    scene = Scene(
        id="scene_chat",
        name="Chat Scene",
        body="A scene with chat.",
        current_gametime=200,
        messages=[
            CM(
                id="msg_01",
                name="Eldric says hi",
                body="",
                scene_id="scene_chat",
                gametime=10,
                walltime="2024-01-01T12:00:00",
                character_id="char_eldric",
                message="Hello there!",
            ),
        ],
    )
    # storage.get_scene returns the scene with messages populated
    mock_campaign.storage.get_scene = MagicMock(return_value=scene)

    with _setup_list_entities(mock_campaign, [scene]), \
         _setup_get_related():
        _setup_memories_query(mock_campaign, [])
        result = await export_campaign(mock_campaign)

    mock_campaign.storage.get_scene.assert_called_with("scene_chat")
    assert result.written_chatlogs == 1


@pytest.mark.anyio
async def test_writes_entities_to_correct_subdirs(mock_campaign: MagicMock, sample_entities: list[Entity], tmp_path: Path) -> None:
    """Character -> characters/, Location -> locations/, etc."""
    from sidestage.migration.exporter import export_campaign

    with _setup_list_entities(mock_campaign, sample_entities), \
         _setup_get_related():
        _setup_memories_query(mock_campaign, [])
        result = await export_campaign(mock_campaign)

    md_dir = tmp_path / "markdown"
    assert (md_dir / "characters").is_dir()
    assert (md_dir / "locations").is_dir()
    assert (md_dir / "items").is_dir()
    assert (md_dir / "scenes").is_dir()
    assert (md_dir / "events").is_dir()

    # Check specific files exist
    char_files = list((md_dir / "characters").glob("*.md"))
    assert len(char_files) == 2

    loc_files = list((md_dir / "locations").glob("*.md"))
    assert len(loc_files) == 2

    item_files = list((md_dir / "items").glob("*.md"))
    assert len(item_files) == 1

    assert result.written_entities == len(sample_entities)


@pytest.mark.anyio
async def test_writes_memories_to_dot_d_dirs(
    mock_campaign: MagicMock, sample_entities: list[Entity], sample_memories: list[Memory], tmp_path: Path
) -> None:
    """Memories placed inside parent entity's .d/ directory."""
    from sidestage.migration.exporter import export_campaign

    with _setup_list_entities(mock_campaign, sample_entities), \
         _setup_get_related():
        _setup_memories_query(mock_campaign, sample_memories)
        result = await export_campaign(mock_campaign)

    md_dir = tmp_path / "markdown"
    assert result.written_memories == 3

    # mem_001 has owner_id=char_eldric -> should be in characters/Eldric_the_Bold.d/
    char_d_dirs = list((md_dir / "characters").glob("*.d"))
    assert len(char_d_dirs) >= 1

    # mem_002 has owner_id=None, target_id=loc_tavern -> in locations/Rusty_Tavern.d/
    loc_d_dirs = list((md_dir / "locations").glob("*.d"))
    assert len(loc_d_dirs) >= 1


@pytest.mark.anyio
async def test_writes_chatlog_to_scene_dot_d(mock_campaign: MagicMock, tmp_path: Path) -> None:
    """Scene chat logs written as chatlog.log inside scene_name.d/."""
    from sidestage.migration.exporter import export_campaign
    from sidestage.schemas import ChatMessage as CM

    scene = Scene(
        id="scene_chat",
        name="Chat Scene",
        body="A scene.",
        current_gametime=100,
    )
    scene_with_msgs = Scene(
        id="scene_chat",
        name="Chat Scene",
        body="A scene.",
        current_gametime=100,
        messages=[
            CM(
                id="msg_01",
                name="Greeting",
                body="",
                scene_id="scene_chat",
                gametime=10,
                walltime="2024-01-01T12:00:00",
                character_id="char_eldric",
                message="Hello!",
            ),
        ],
    )
    mock_campaign.storage.get_scene = MagicMock(return_value=scene_with_msgs)

    with _setup_list_entities(mock_campaign, [scene]), \
         _setup_get_related():
        _setup_memories_query(mock_campaign, [])
        result = await export_campaign(mock_campaign)

    md_dir = tmp_path / "markdown"
    scene_d_dirs = list((md_dir / "scenes").glob("*.d"))
    assert len(scene_d_dirs) == 1

    chatlog = scene_d_dirs[0] / "chatlog.log"
    assert chatlog.exists()

    content = chatlog.read_text()
    assert "char_eldric" in content
    assert "Hello!" in content


@pytest.mark.anyio
async def test_dot_d_created_only_when_needed(mock_campaign: MagicMock, sample_entities: list[Entity], tmp_path: Path) -> None:
    """Entities without memories or chat logs should not have .d/ directories."""
    from sidestage.migration.exporter import export_campaign

    # No memories, no chat logs
    mock_campaign.storage.get_scene = MagicMock(return_value=None)

    with _setup_list_entities(mock_campaign, sample_entities), \
         _setup_get_related():
        _setup_memories_query(mock_campaign, [])
        await export_campaign(mock_campaign)

    md_dir = tmp_path / "markdown"
    all_d_dirs = list(md_dir.rglob("*.d"))
    assert len(all_d_dirs) == 0


@pytest.mark.anyio
async def test_writes_status_json(
    mock_campaign: MagicMock, sample_entities: list[Entity], sample_memories: list[Memory], tmp_path: Path
) -> None:
    """status.json contains entity counts, memory count, chatlog count, timestamp."""
    from sidestage.migration.exporter import export_campaign

    with _setup_list_entities(mock_campaign, sample_entities), \
         _setup_get_related():
        _setup_memories_query(mock_campaign, sample_memories)
        await export_campaign(mock_campaign)

    status_path = tmp_path / "markdown" / "status.json"
    assert status_path.exists()

    status = json.loads(status_path.read_text())
    assert status["success"] is True
    assert status["memory_count"] == 3
    assert "timestamp" in status
    assert "entity_counts" in status
    assert status["entity_counts"]["Character"] == 2
    assert status["entity_counts"]["Location"] == 2


@pytest.mark.anyio
async def test_atomic_swap_preserves_old_on_failure(mock_campaign: MagicMock, tmp_path: Path) -> None:
    """If export fails mid-write, the original markdown/ dir is preserved."""
    from sidestage.migration.exporter import export_campaign

    # Create pre-existing markdown dir with a marker file
    md_dir = tmp_path / "markdown"
    md_dir.mkdir()
    (md_dir / "old_marker.txt").write_text("original content")

    # Make list_entities raise an error after the temp dir is created
    with _setup_list_entities(mock_campaign, []) as mock_list, \
         _setup_get_related():
        mock_list.side_effect = RuntimeError("FalkorDB connection lost")
        result = await export_campaign(mock_campaign)

    # Original directory should be preserved
    assert (tmp_path / "markdown" / "old_marker.txt").exists()
    assert result.phase == "failed"


@pytest.mark.anyio
async def test_filename_collision_handling(mock_campaign: MagicMock, tmp_path: Path) -> None:
    """Two entities with the same sanitized name get _2 suffix."""
    from sidestage.migration.exporter import export_campaign

    entities: list[Entity] = [
        Character(id="char_1", name="Test Entity!", body="First."),
        Character(id="char_2", name="Test Entity?", body="Second."),
    ]

    with _setup_list_entities(mock_campaign, entities), \
         _setup_get_related():
        _setup_memories_query(mock_campaign, [])
        result = await export_campaign(mock_campaign)

    md_dir = tmp_path / "markdown" / "characters"
    files = sorted(f.name for f in md_dir.glob("*.md"))
    assert len(files) == 2
    assert "Test_Entity.md" in files
    assert "Test_Entity_2.md" in files


@pytest.mark.anyio
async def test_memory_placed_in_owner_dot_d(mock_campaign: MagicMock, sample_entities: list[Entity], tmp_path: Path) -> None:
    """Memory with owner_id goes into the owner entity's .d/ directory."""
    from sidestage.migration.exporter import export_campaign

    memories = [
        Memory(
            id="mem_owned",
            content="A private memory.",
            memory_type=MemoryType.CHARACTER,
            visibility="private",
            owner_id="char_eldric",
            target_id="loc_tavern",
            created_at=1000.0,
            updated_at=1000.0,
        ),
    ]

    with _setup_list_entities(mock_campaign, sample_entities), \
         _setup_get_related():
        _setup_memories_query(mock_campaign, memories)
        result = await export_campaign(mock_campaign)

    md_dir = tmp_path / "markdown"
    # Should be in the character's .d/ dir (owner), not location's
    char_d_dirs = list((md_dir / "characters").glob("*.d"))
    assert len(char_d_dirs) == 1
    mem_files = list(char_d_dirs[0].glob("*.md"))
    assert len(mem_files) == 1
    assert result.written_memories == 1


@pytest.mark.anyio
async def test_memory_placed_in_target_dot_d_when_no_owner(
    mock_campaign: MagicMock, sample_entities: list[Entity], tmp_path: Path
) -> None:
    """Memory with owner_id=None goes into target entity's .d/ directory."""
    from sidestage.migration.exporter import export_campaign

    memories = [
        Memory(
            id="mem_world",
            content="A world fact.",
            memory_type=MemoryType.WORLD_FACT,
            visibility="common",
            owner_id=None,
            target_id="loc_tavern",
            created_at=1000.0,
            updated_at=1000.0,
        ),
    ]

    with _setup_list_entities(mock_campaign, sample_entities), \
         _setup_get_related():
        _setup_memories_query(mock_campaign, memories)
        result = await export_campaign(mock_campaign)

    md_dir = tmp_path / "markdown"
    loc_d_dirs = list((md_dir / "locations").glob("*.d"))
    assert len(loc_d_dirs) == 1
    mem_files = list(loc_d_dirs[0].glob("*.md"))
    assert len(mem_files) == 1
    assert result.written_memories == 1


@pytest.mark.anyio
async def test_memory_falls_back_to_target_when_owner_unknown(
    mock_campaign: MagicMock, sample_entities: list[Entity], tmp_path: Path
) -> None:
    """Memory with owner_id set to unknown entity falls back to target's .d/ dir."""
    from sidestage.migration.exporter import export_campaign

    memories = [
        Memory(
            id="mem_fallback",
            content="A memory with unknown owner.",
            memory_type=MemoryType.CHARACTER,
            visibility="private",
            owner_id="char_deleted",  # does not exist in sample_entities
            target_id="loc_tavern",   # exists in sample_entities
            created_at=1000.0,
            updated_at=1000.0,
        ),
    ]

    with _setup_list_entities(mock_campaign, sample_entities), \
         _setup_get_related():
        _setup_memories_query(mock_campaign, memories)
        result = await export_campaign(mock_campaign)

    # Memory should fall back to target entity (loc_tavern)
    md_dir = tmp_path / "markdown"
    loc_d_dirs = list((md_dir / "locations").glob("*.d"))
    assert len(loc_d_dirs) == 1
    mem_files = list(loc_d_dirs[0].glob("*.md"))
    assert len(mem_files) == 1
    assert result.written_memories == 1


@pytest.mark.anyio
async def test_memory_with_both_unknown_ids_skipped(mock_campaign: MagicMock, sample_entities: list[Entity], tmp_path: Path) -> None:
    """Memory where both owner_id and target_id are unknown is skipped with error."""
    from sidestage.migration.exporter import export_campaign

    memories = [
        Memory(
            id="mem_orphan",
            content="An orphaned memory.",
            memory_type=MemoryType.WORLD_FACT,
            visibility="common",
            owner_id="char_gone",
            target_id="loc_gone",
            created_at=1000.0,
            updated_at=1000.0,
        ),
    ]

    with _setup_list_entities(mock_campaign, sample_entities), \
         _setup_get_related():
        _setup_memories_query(mock_campaign, memories)
        result = await export_campaign(mock_campaign)

    assert result.written_memories == 0
    assert any("mem_orphan" in e for e in result.errors)


@pytest.mark.anyio
async def test_queries_located_in_for_characters(mock_campaign: MagicMock, tmp_path: Path) -> None:
    """Character frontmatter includes location_id from LOCATED_IN relationship."""
    from sidestage.migration.exporter import export_campaign

    char = Character(id="char_test", name="Test Char", body="")
    loc = Location(id="loc_home", name="Home", body="")

    related_map: dict[tuple[str, str], list[Entity]] = {
        ("char_test", "LOCATED_IN"): [loc],
    }

    with _setup_list_entities(mock_campaign, [char, loc]), \
         _setup_get_related(related_map):
        _setup_memories_query(mock_campaign, [])
        await export_campaign(mock_campaign)

    md_dir = tmp_path / "markdown" / "characters"
    char_file = list(md_dir.glob("*.md"))[0]
    content = char_file.read_text()
    assert "loc_home" in content


@pytest.mark.anyio
async def test_queries_connects_to_for_locations(mock_campaign: MagicMock, tmp_path: Path) -> None:
    """Location frontmatter includes connected_locations from CONNECTS_TO edges."""
    from sidestage.migration.exporter import export_campaign

    loc1 = Location(id="loc_a", name="Place A", body="")
    loc2 = Location(id="loc_b", name="Place B", body="")

    related_map: dict[tuple[str, str], list[Entity]] = {
        ("loc_a", "CONNECTS_TO"): [loc2],
        ("loc_b", "CONNECTS_TO"): [loc1],
    }

    with _setup_list_entities(mock_campaign, [loc1, loc2]), \
         _setup_get_related(related_map):
        _setup_memories_query(mock_campaign, [])
        await export_campaign(mock_campaign)

    md_dir = tmp_path / "markdown" / "locations"
    for f in md_dir.glob("*.md"):
        content = f.read_text()
        if "Place A" in content:
            assert "loc_b" in content
        elif "Place B" in content:
            assert "loc_a" in content


@pytest.mark.anyio
async def test_no_graph_client_returns_failed(tmp_path: Path) -> None:
    """If campaign.graph_client is None, return a failed result."""
    from sidestage.migration.exporter import export_campaign

    campaign = MagicMock()
    campaign.graph_client = None
    campaign.campaign_dir = tmp_path

    result = await export_campaign(campaign)
    assert result.phase == "failed"
    assert len(result.errors) > 0


@pytest.mark.anyio
async def test_empty_campaign(mock_campaign: MagicMock, tmp_path: Path) -> None:
    """Empty campaign produces directory structure with status.json showing zero counts."""
    from sidestage.migration.exporter import export_campaign

    with _setup_list_entities(mock_campaign, []), \
         _setup_get_related():
        _setup_memories_query(mock_campaign, [])
        result = await export_campaign(mock_campaign)

    md_dir = tmp_path / "markdown"
    assert md_dir.is_dir()

    status_path = md_dir / "status.json"
    assert status_path.exists()
    status = json.loads(status_path.read_text())
    assert status["success"] is True
    assert status["memory_count"] == 0

    assert result.phase == "complete"
    assert result.written_entities == 0
    assert result.written_memories == 0
