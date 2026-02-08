"""Integration tests for the migration pipeline: import -> verify -> backup -> compare.

These tests exercise the full roundtrip: parse the canonical test campaign fixture,
import it into FalkorDB, verify graph state, back up to a second directory, and
compare the results. They require a running FalkorDB instance.

Test fixture data lives at data/dev_campaign/markdown/ (created in section-03).
All tests copy fixture data to tmp_path to avoid modifying checked-in files.
"""

import re
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from sidestage.health import CampaignHealth, HealthStatus
from sidestage.memory.models import Memory, MemoryType
from sidestage.migration.models import MigrationValidationReport, ParseResult
from sidestage.migration.parser import parse_directory
from sidestage.migration.validator import validate_parse_result
from sidestage.migration.importer import import_campaign
from sidestage.migration.serialization import (
    entity_to_frontmatter_dict,
    frontmatter_dict_to_entity,
)
from sidestage.schemas import Character, Entity, Event, JoinEvent, Location, Scene


# --- Constants ---

CAMPAIGN_ROOT = Path(__file__).parent.parent.parent / "data" / "dev_campaign" / "markdown"

EXPECTED_ENTITY_COUNTS = {
    "Character": 2,
    "Location": 3,
    "Item": 2,
    "Scene": 2,
    "JoinEvent": 1,
}
EXPECTED_TOTAL_ENTITIES = 10
EXPECTED_TOTAL_MEMORIES = 6
EXPECTED_CHATLOG_SCENES = 1

EXPECTED_ENTITY_IDS = {
    "char_eldric", "char_alice",
    "loc_rusty_tavern", "loc_castle_blackmoor", "loc_town_square",
    "item_flame_tongue", "item_healing_potion",
    "scene_tavern_brawl", "scene_castle_audience",
    "event_eldric_joins",
}

EXPECTED_MEMORY_IDS = {
    "mem_tavern_brawl", "mem_knows_alice", "mem_trade_secret",
    "mem_haunted_history", "mem_brawl_outcome", "mem_castle_legend",
}


# --- Helpers ---


def _find_entity_by_id(entities: list[Entity], entity_id: str) -> Entity | None:
    """Find an entity in a list by its id field."""
    for e in entities:
        if e.id == entity_id:
            return e
    return None


def _find_memory_by_id(memories: list[Memory], memory_id: str) -> Memory | None:
    """Find a memory in a list by its id field."""
    for m in memories:
        if m.id == memory_id:
            return m
    return None


def _modify_frontmatter(file_path: Path, updates: dict[str, object]) -> None:
    """Read a markdown file, update its frontmatter fields, and write it back."""
    text = file_path.read_text()
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"No frontmatter in {file_path}")
    fm = yaml.safe_load(parts[1])
    fm.update(updates)
    dumped = yaml.dump(fm, default_flow_style=False)
    file_path.write_text(f"---\n{dumped}---{parts[2]}")


# --- Fixtures ---


@pytest.fixture
def test_campaign_markdown(tmp_path: Path) -> Path:
    """Copy canonical test campaign to a temp directory for testing."""
    dst = tmp_path / "markdown"
    shutil.copytree(CAMPAIGN_ROOT, dst)
    return dst


@pytest.fixture
def parsed_campaign(test_campaign_markdown: Path) -> ParseResult:
    """Parse the test campaign fixture and return the ParseResult."""
    result = parse_directory(test_campaign_markdown)
    assert len(result.errors) == 0, f"Parse errors: {result.errors}"
    return result


@pytest.fixture
def validated_campaign(parsed_campaign: ParseResult) -> MigrationValidationReport:
    """Validate the parsed campaign and return the report."""
    report = validate_parse_result(parsed_campaign)
    assert report.valid, f"Validation errors: {report.errors}"
    return report


@pytest.fixture
def mock_campaign(tmp_path: Path):
    """Mock Campaign object for integration tests that need graph interactions."""
    campaign = MagicMock()
    campaign.campaign_dir = tmp_path
    campaign.name = "test_campaign"
    campaign.health = CampaignHealth()
    campaign.config = MagicMock()
    campaign.config.graph = MagicMock()
    campaign.config.graph.vector_dimension = None
    campaign.storage = MagicMock()
    campaign.storage.get_scene = MagicMock(return_value=None)
    campaign.storage.update_scene = MagicMock()
    campaign.storage.add_scene = MagicMock()
    # Graph client with async-compatible mocks
    campaign.graph_client = MagicMock()
    campaign.graph_client.graph = AsyncMock()
    campaign.graph_client.graph.delete = AsyncMock()
    campaign.graph_client.graph.query = AsyncMock(return_value=MagicMock(result_set=[]))
    campaign.graph_client.db = MagicMock()
    campaign.graph_client.graph_name = "test_campaign"
    campaign.graph_client.db.select_graph = MagicMock(return_value=campaign.graph_client.graph)
    return campaign


@pytest.fixture
def mock_sync_manager():
    """Mock SyncManager for verifying broadcast calls."""
    sm = MagicMock()
    sm.broadcast = AsyncMock()
    return sm


@pytest.fixture
def patch_graph_operations():
    """Patch graph operations used by importer to avoid needing real FalkorDB.

    Not autouse — only applied to test classes that call import_campaign.
    """
    from unittest.mock import patch

    with (
        patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock) as mock_create,
        patch("sidestage.migration.importer.link", new_callable=AsyncMock) as mock_link,
        patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock) as mock_schema,
        patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]) as mock_list,
    ):
        yield {
            "create_entity": mock_create,
            "link": mock_link,
            "initialize_schema": mock_schema,
            "list_entities": mock_list,
        }


# =============================================================================
# Test 1: Full Roundtrip (import -> backup -> compare)
# =============================================================================


@pytest.mark.usefixtures("patch_graph_operations")
class TestFullRoundtrip:
    """Full roundtrip integration tests: parse -> validate -> import -> backup -> compare."""

    def test_parse_produces_correct_entity_counts(self, parsed_campaign: ParseResult):
        """Parsing the test campaign yields the expected number and types of entities."""
        from collections import Counter

        type_counts = Counter(type(e).__name__ for e in parsed_campaign.entities)
        for type_name, expected_count in EXPECTED_ENTITY_COUNTS.items():
            assert type_counts[type_name] == expected_count, (
                f"Expected {expected_count} {type_name}, got {type_counts[type_name]}"
            )
        assert len(parsed_campaign.entities) == EXPECTED_TOTAL_ENTITIES

    def test_parse_produces_correct_memory_count(self, parsed_campaign: ParseResult):
        """Parsing the test campaign yields exactly 6 memories."""
        assert len(parsed_campaign.memories) == EXPECTED_TOTAL_MEMORIES

    def test_parse_produces_correct_chatlog_count(self, parsed_campaign: ParseResult):
        """Parsing the test campaign yields 1 scene with chat log (Tavern_Brawl)."""
        assert len(parsed_campaign.chatlogs) == EXPECTED_CHATLOG_SCENES
        assert "scene_tavern_brawl" in parsed_campaign.chatlogs

    def test_validation_passes_with_no_errors(self, validated_campaign: MigrationValidationReport):
        """Validation of the test campaign produces valid=True with no error-severity issues."""
        assert validated_campaign.valid is True
        assert len(validated_campaign.errors) == 0

    def test_validation_includes_data_loss_warning(self, validated_campaign: MigrationValidationReport):
        """Validation always includes the data-loss warning."""
        assert len(validated_campaign.warnings) >= 1
        assert any(
            "cannot be undone" in w.message.lower() or "drop" in w.message.lower()
            for w in validated_campaign.warnings
        )

    @pytest.mark.anyio
    async def test_import_completes_successfully(
        self, mock_campaign: MagicMock, parsed_campaign: ParseResult, mock_sync_manager: MagicMock
    ):
        """import_campaign returns a result with phase='complete' and correct counts."""
        result = await import_campaign(
            campaign=mock_campaign,
            parse_result=parsed_campaign,
            sync_manager=mock_sync_manager,
        )
        assert result.phase == "complete"
        assert result.errors == []
        assert result.total_entities == EXPECTED_TOTAL_ENTITIES
        assert result.total_memories == EXPECTED_TOTAL_MEMORIES
        assert result.processed_entities == EXPECTED_TOTAL_ENTITIES
        assert result.processed_memories == EXPECTED_TOTAL_MEMORIES

    @pytest.mark.anyio
    async def test_health_transitions_during_import(
        self, mock_campaign: MagicMock, parsed_campaign: ParseResult, mock_sync_manager: MagicMock
    ):
        """After import_campaign returns, campaign.health.status should be HEALTHY."""
        await import_campaign(
            campaign=mock_campaign,
            parse_result=parsed_campaign,
            sync_manager=mock_sync_manager,
        )
        assert mock_campaign.health.status == HealthStatus.HEALTHY

    @pytest.mark.anyio
    async def test_broadcast_sent_after_import(
        self, mock_campaign: MagicMock, parsed_campaign: ParseResult, mock_sync_manager: MagicMock
    ):
        """After a successful import, sync_manager.broadcast is called with entities_updated."""
        await import_campaign(
            campaign=mock_campaign,
            parse_result=parsed_campaign,
            sync_manager=mock_sync_manager,
        )
        mock_sync_manager.broadcast.assert_called()
        calls = mock_sync_manager.broadcast.call_args_list
        assert any(
            call.args[0].get("type") == "entities_updated"
            for call in calls
        )


# =============================================================================
# Test 2: Entity Fidelity (canonical format = API format)
# =============================================================================


class TestEntityFidelity:
    """Verify that entity data survives the parse -> serialize roundtrip unchanged."""

    def test_entity_frontmatter_dict_roundtrip_all_types(self, parsed_campaign: ParseResult):
        """For every parsed entity, converting to frontmatter dict and back produces
        an identical entity."""
        for entity in parsed_campaign.entities:
            fm, body = entity_to_frontmatter_dict(entity)
            restored = frontmatter_dict_to_entity(fm, body)
            assert restored.id == entity.id
            assert restored.name == entity.name
            assert restored.body == entity.body
            assert type(restored).__name__ == type(entity).__name__
            # Type-specific fields
            if isinstance(entity, Character):
                assert isinstance(restored, Character)
                assert restored.location_id == entity.location_id
                assert restored.inventory == entity.inventory
                assert restored.unseen == entity.unseen
            elif isinstance(entity, Location):
                assert isinstance(restored, Location)
                assert set(restored.connected_locations) == set(entity.connected_locations)
            elif isinstance(entity, Scene):
                assert isinstance(restored, Scene)
                assert restored.location_id == entity.location_id
                assert restored.current_gametime == entity.current_gametime
                assert restored.events == entity.events
            elif isinstance(entity, Event):
                assert isinstance(restored, Event)
                assert restored.scene_id == entity.scene_id

    def test_character_fields_preserved(self, parsed_campaign: ParseResult):
        """Character-specific fields survive roundtrip."""
        eldric = _find_entity_by_id(parsed_campaign.entities, "char_eldric")
        assert isinstance(eldric, Character)
        assert eldric.location_id == "loc_rusty_tavern"
        assert eldric.inventory == ["item_flame_tongue"]

        alice = _find_entity_by_id(parsed_campaign.entities, "char_alice")
        assert isinstance(alice, Character)
        assert alice.location_id is None
        assert alice.inventory == []

    def test_location_fields_preserved(self, parsed_campaign: ParseResult):
        """Each of the 3 locations should have exactly 2 entries in connected_locations."""
        locations = [e for e in parsed_campaign.entities if isinstance(e, Location)]
        assert len(locations) == 3
        for loc in locations:
            assert len(loc.connected_locations) == 2, (
                f"Location {loc.id} has {len(loc.connected_locations)} connections, expected 2"
            )

    def test_scene_fields_preserved(self, parsed_campaign: ParseResult):
        """Scene-specific fields survive roundtrip."""
        tavern = _find_entity_by_id(parsed_campaign.entities, "scene_tavern_brawl")
        assert isinstance(tavern, Scene)
        assert tavern.location_id == "loc_rusty_tavern"
        assert tavern.current_gametime == 7200
        assert tavern.events == ["event_eldric_joins"]
        assert tavern.messages == []

        castle = _find_entity_by_id(parsed_campaign.entities, "scene_castle_audience")
        assert isinstance(castle, Scene)
        assert castle.location_id == "loc_castle_blackmoor"
        assert castle.current_gametime is None
        assert castle.messages == []

    def test_event_subtype_preserved(self, parsed_campaign: ParseResult):
        """JoinEvent subtype and its fields survive roundtrip."""
        event = _find_entity_by_id(parsed_campaign.entities, "event_eldric_joins")
        assert isinstance(event, JoinEvent)
        assert event.actor_id == "char_eldric"
        assert event.scene_id == "scene_tavern_brawl"


# =============================================================================
# Test 3: Memory Fidelity
# =============================================================================


class TestMemoryFidelity:
    """Verify that memory data survives the parse roundtrip with all fields intact."""

    def test_all_memory_fields_preserved(self, parsed_campaign: ParseResult):
        """For each memory: key fields are present, embedding is None."""
        for mem in parsed_campaign.memories:
            assert mem.id is not None
            assert mem.content is not None and len(mem.content) > 0
            assert mem.memory_type is not None
            assert mem.visibility is not None
            assert mem.embedding is None
            assert mem.created_at is not None
            assert mem.updated_at is not None
            assert mem.access_count is not None

    def test_memory_types_correct(self, parsed_campaign: ParseResult):
        """Parsed memories have the correct memory_type values."""
        expected = {
            "mem_tavern_brawl": MemoryType.SCENE,
            "mem_knows_alice": MemoryType.CHARACTER,
            "mem_trade_secret": MemoryType.WORLD_FACT,
            "mem_haunted_history": MemoryType.WORLD_FACT,
            "mem_brawl_outcome": MemoryType.SCENE,
            "mem_castle_legend": MemoryType.WORLD_FACT,
        }
        for mem_id, expected_type in expected.items():
            mem = _find_memory_by_id(parsed_campaign.memories, mem_id)
            assert mem is not None, f"Memory {mem_id} not found"
            assert mem.memory_type == expected_type, (
                f"{mem_id}: expected {expected_type}, got {mem.memory_type}"
            )

    def test_memory_visibility_correct(self, parsed_campaign: ParseResult):
        """Parsed memories have the correct visibility values."""
        private_ids = {"mem_tavern_brawl", "mem_trade_secret"}
        for mem in parsed_campaign.memories:
            if mem.id in private_ids:
                assert mem.visibility == "private", f"{mem.id} should be private"
            else:
                assert mem.visibility == "common", f"{mem.id} should be common"

    def test_memory_owner_target_correct(self, parsed_campaign: ParseResult):
        """Each memory has the correct owner_id and target_id."""
        expected = {
            "mem_tavern_brawl": ("char_eldric", "scene_tavern_brawl"),
            "mem_knows_alice": ("char_eldric", "char_alice"),
            "mem_trade_secret": ("char_alice", "loc_rusty_tavern"),
            "mem_haunted_history": (None, "loc_rusty_tavern"),
            "mem_brawl_outcome": (None, "scene_tavern_brawl"),
            "mem_castle_legend": (None, "loc_castle_blackmoor"),
        }
        for mem_id, (exp_owner, exp_target) in expected.items():
            mem = _find_memory_by_id(parsed_campaign.memories, mem_id)
            assert mem is not None, f"Memory {mem_id} not found"
            assert mem.owner_id == exp_owner, f"{mem_id}: owner expected {exp_owner}, got {mem.owner_id}"
            assert mem.target_id == exp_target, f"{mem_id}: target expected {exp_target}, got {mem.target_id}"


# =============================================================================
# Test 4: Chat Log Fidelity
# =============================================================================


class TestChatLogFidelity:
    """Verify that chat log data is parsed correctly from chatlog.log files."""

    def test_chatlog_parsed_for_tavern_brawl(self, parsed_campaign: ParseResult):
        """The Tavern_Brawl scene has a chatlog with 3 lines parsed."""
        assert "scene_tavern_brawl" in parsed_campaign.chatlogs
        assert len(parsed_campaign.chatlogs["scene_tavern_brawl"]) == 3

    def test_chatlog_lines_match_expected_format(self, parsed_campaign: ParseResult):
        """Each chatlog line matches the [timestamp] (character_id) Name: "message" format."""
        pattern = re.compile(r'^\[.*\]\s+\(.*\)\s+.*:\s+".*"$')
        for line in parsed_campaign.chatlogs["scene_tavern_brawl"]:
            assert pattern.match(line.strip()), f"Line doesn't match format: {line}"

    def test_chatlog_contains_correct_speakers(self, parsed_campaign: ParseResult):
        """The chatlog contains messages from char_eldric and char_alice."""
        lines = parsed_campaign.chatlogs["scene_tavern_brawl"]
        all_text = "\n".join(lines)
        assert "(char_eldric)" in all_text
        assert "(char_alice)" in all_text

    def test_no_chatlog_for_castle_audience(self, parsed_campaign: ParseResult):
        """The Castle_Audience scene has no chatlog."""
        assert "scene_castle_audience" not in parsed_campaign.chatlogs


# =============================================================================
# Test 5: Relationship Integrity
# =============================================================================


class TestRelationshipIntegrity:
    """Verify that entity cross-references are consistent in the parsed data."""

    def test_character_location_references_valid(self, parsed_campaign: ParseResult):
        """Location references from characters point to valid locations."""
        location_ids = {e.id for e in parsed_campaign.entities if isinstance(e, Location)}
        eldric = _find_entity_by_id(parsed_campaign.entities, "char_eldric")
        assert isinstance(eldric, Character)
        assert eldric.location_id in location_ids

        alice = _find_entity_by_id(parsed_campaign.entities, "char_alice")
        assert isinstance(alice, Character)
        assert alice.location_id is None

    def test_character_inventory_references_valid(self, parsed_campaign: ParseResult):
        """Eldric's inventory references a valid item entity."""
        item_ids = {e.id for e in parsed_campaign.entities if hasattr(e, "id") and e.id.startswith("item_")}
        eldric = _find_entity_by_id(parsed_campaign.entities, "char_eldric")
        assert isinstance(eldric, Character)
        for inv_id in eldric.inventory:
            assert inv_id in item_ids, f"Inventory item {inv_id} not found in items"

    def test_location_connectivity_triangle(self, parsed_campaign: ParseResult):
        """The 3 locations form a complete connectivity triangle."""
        locations = {e.id: e for e in parsed_campaign.entities if isinstance(e, Location)}

        assert set(locations["loc_rusty_tavern"].connected_locations) == {"loc_castle_blackmoor", "loc_town_square"}
        assert set(locations["loc_castle_blackmoor"].connected_locations) == {"loc_rusty_tavern", "loc_town_square"}
        assert set(locations["loc_town_square"].connected_locations) == {"loc_rusty_tavern", "loc_castle_blackmoor"}

    def test_connects_to_deduplication_count(self, parsed_campaign: ParseResult):
        """The triangle has 6 directional references but should produce only 3 unique pairs."""
        locations = [e for e in parsed_campaign.entities if isinstance(e, Location)]
        pairs = set()
        for loc in locations:
            for other_id in loc.connected_locations:
                pairs.add(frozenset({loc.id, other_id}))
        assert len(pairs) == 3

    def test_scene_location_references_valid(self, parsed_campaign: ParseResult):
        """Both scenes reference valid location IDs."""
        location_ids = {e.id for e in parsed_campaign.entities if isinstance(e, Location)}
        tavern = _find_entity_by_id(parsed_campaign.entities, "scene_tavern_brawl")
        castle = _find_entity_by_id(parsed_campaign.entities, "scene_castle_audience")
        assert isinstance(tavern, Scene)
        assert isinstance(castle, Scene)
        assert tavern.location_id in location_ids
        assert castle.location_id in location_ids

    def test_event_scene_references_valid(self, parsed_campaign: ParseResult):
        """The JoinEvent references scene_tavern_brawl which exists in parsed scenes."""
        scene_ids = {e.id for e in parsed_campaign.entities if isinstance(e, Scene)}
        event = _find_entity_by_id(parsed_campaign.entities, "event_eldric_joins")
        assert isinstance(event, Event)
        assert event.scene_id in scene_ids


# =============================================================================
# Test 6: Validation Errors (broken references)
# =============================================================================


class TestValidationErrors:
    """Verify that the validator catches broken references in modified fixture data."""

    def test_broken_character_location_ref(self, test_campaign_markdown: Path):
        """Modify a character to reference a nonexistent location_id."""
        eldric_path = test_campaign_markdown / "characters" / "Eldric_the_Bold.md"
        _modify_frontmatter(eldric_path, {"location_id": "loc_nonexistent"})

        result = parse_directory(test_campaign_markdown)
        report = validate_parse_result(result)

        assert not report.valid
        assert any("loc_nonexistent" in e.message for e in report.errors)

    def test_broken_character_inventory_ref(self, test_campaign_markdown: Path):
        """Modify a character's inventory to reference a nonexistent item."""
        eldric_path = test_campaign_markdown / "characters" / "Eldric_the_Bold.md"
        _modify_frontmatter(eldric_path, {"inventory": ["item_nonexistent"]})

        result = parse_directory(test_campaign_markdown)
        report = validate_parse_result(result)

        assert not report.valid
        assert any("item_nonexistent" in e.message for e in report.errors)

    def test_broken_scene_location_ref(self, test_campaign_markdown: Path):
        """Modify a scene to reference a nonexistent location_id."""
        tavern_path = test_campaign_markdown / "scenes" / "Tavern_Brawl.md"
        _modify_frontmatter(tavern_path, {"location_id": "loc_nonexistent"})

        result = parse_directory(test_campaign_markdown)
        report = validate_parse_result(result)

        assert not report.valid
        assert any("loc_nonexistent" in e.message for e in report.errors)

    def test_broken_event_scene_ref(self, test_campaign_markdown: Path):
        """Modify an event to reference a nonexistent scene_id."""
        event_path = test_campaign_markdown / "events" / "Eldric_Joins_Brawl.md"
        _modify_frontmatter(event_path, {"scene_id": "scene_nonexistent"})

        result = parse_directory(test_campaign_markdown)
        report = validate_parse_result(result)

        assert not report.valid
        assert any("scene_nonexistent" in e.message for e in report.errors)

    def test_broken_memory_target_ref(self, test_campaign_markdown: Path):
        """Modify a memory to reference a nonexistent target_id."""
        mem_path = test_campaign_markdown / "characters" / "Eldric_the_Bold.d" / "mem_tavern_brawl.md"
        _modify_frontmatter(mem_path, {"target_id": "target_nonexistent"})

        result = parse_directory(test_campaign_markdown)
        report = validate_parse_result(result)

        assert not report.valid
        assert any("target_nonexistent" in e.message for e in report.errors)

    def test_broken_memory_owner_ref(self, test_campaign_markdown: Path):
        """Modify a memory to reference a nonexistent owner_id."""
        mem_path = test_campaign_markdown / "characters" / "Eldric_the_Bold.d" / "mem_tavern_brawl.md"
        _modify_frontmatter(mem_path, {"owner_id": "owner_nonexistent"})

        result = parse_directory(test_campaign_markdown)
        report = validate_parse_result(result)

        assert not report.valid
        assert any("owner_nonexistent" in e.message for e in report.errors)


# =============================================================================
# Test 7: Concurrency Guard
# =============================================================================


@pytest.mark.usefixtures("patch_graph_operations")
class TestConcurrencyGuard:
    """Verify health status transitions and concurrency protection during import."""

    @pytest.mark.anyio
    async def test_health_degraded_during_import(self, mock_campaign: MagicMock, parsed_campaign: ParseResult, mock_sync_manager: MagicMock):
        """During import execution, campaign.health.status is set to DEGRADED."""
        observed_statuses = []

        original_delete = mock_campaign.graph_client.graph.delete

        async def capture_status() -> None:
            observed_statuses.append(mock_campaign.health.status)
            await original_delete()

        mock_campaign.graph_client.graph.delete = capture_status

        await import_campaign(
            campaign=mock_campaign,
            parse_result=parsed_campaign,
            sync_manager=mock_sync_manager,
        )

        assert HealthStatus.DEGRADED in observed_statuses
        assert mock_campaign.health.status == HealthStatus.HEALTHY

    @pytest.mark.anyio
    async def test_health_restored_on_import_failure(self, mock_campaign: MagicMock, parsed_campaign: ParseResult, mock_sync_manager: MagicMock):
        """Even if import fails, health is restored to HEALTHY."""
        mock_campaign.graph_client.graph.delete = AsyncMock(side_effect=Exception("Graph drop failed"))

        result = await import_campaign(
            campaign=mock_campaign,
            parse_result=parsed_campaign,
            sync_manager=mock_sync_manager,
        )

        assert result.phase == "failed"
        assert mock_campaign.health.status == HealthStatus.HEALTHY

    @pytest.mark.anyio
    async def test_is_embedding_available_false_during_import(self, mock_campaign: MagicMock, parsed_campaign: ParseResult, mock_sync_manager: MagicMock):
        """While health is DEGRADED, is_embedding_available returns False."""
        observed_embedding = []

        original_delete = mock_campaign.graph_client.graph.delete

        async def capture_embedding() -> None:
            observed_embedding.append(mock_campaign.health.is_embedding_available)
            await original_delete()

        mock_campaign.graph_client.graph.delete = capture_embedding

        await import_campaign(
            campaign=mock_campaign,
            parse_result=parsed_campaign,
            sync_manager=mock_sync_manager,
        )

        assert False in observed_embedding

    @pytest.mark.anyio
    async def test_active_scenes_cleared_after_import(self, mock_campaign: MagicMock, parsed_campaign: ParseResult, mock_sync_manager: MagicMock):
        """The active_scenes dict is cleared after import completes."""
        active_scenes = {"scene_1": MagicMock()}
        await import_campaign(
            campaign=mock_campaign,
            parse_result=parsed_campaign,
            sync_manager=mock_sync_manager,
            active_scenes=active_scenes,
        )
        assert len(active_scenes) == 0


# =============================================================================
# Test 8: Re-import from Backup (idempotency)
# =============================================================================


class TestReimportFromBackup:
    """Verify that importing, backing up, and re-importing produces identical results."""

    def test_backup_parse_matches_original_parse(
        self, test_campaign_markdown: Path, tmp_path: Path
    ):
        """Parse original fixture and a serialized copy, compare entity IDs and fields."""
        from sidestage.migration.serialization import (
            entity_to_frontmatter_dict,
            entity_type_to_subdir,
            memory_to_frontmatter_dict,
            sanitize_filename,
        )

        original = parse_directory(test_campaign_markdown)

        # Serialize entities to a second directory
        backup_md = tmp_path / "backup_markdown"
        for entity in original.entities:
            fm, body = entity_to_frontmatter_dict(entity)
            subdir = entity_type_to_subdir(type(entity).__name__)
            target_dir = backup_md / subdir
            target_dir.mkdir(parents=True, exist_ok=True)
            filename = sanitize_filename(entity.name) + ".md"
            dumped = yaml.dump(dict(fm), default_flow_style=False)
            (target_dir / filename).write_text(f"---\n{dumped}---\n\n{body}\n")

            # Serialize companion memories
            entity_memories = [m for m in original.memories if m.owner_id == entity.id or m.target_id == entity.id]
            if entity_memories:
                companion_dir = target_dir / (sanitize_filename(entity.name) + ".d")
                companion_dir.mkdir(exist_ok=True)
                for mem in entity_memories:
                    # Only write once per memory (use owner's dir or target's dir for ownerless)
                    if mem.owner_id == entity.id or (mem.owner_id is None and mem.target_id == entity.id):
                        mfm, mbody = memory_to_frontmatter_dict(mem)
                        # Convert enum values to plain strings for safe YAML serialization
                        mfm_safe = {
                            k: (v.value if isinstance(v, MemoryType) else v)
                            for k, v in mfm.items()
                        }
                        mdumped = yaml.dump(mfm_safe, default_flow_style=False)
                        (companion_dir / f"{mem.id}.md").write_text(f"---\n{mdumped}---\n\n{mbody}\n")

        # Parse the backup copy
        reparsed = parse_directory(backup_md)

        # Compare entity IDs
        original_ids = {e.id for e in original.entities}
        reparsed_ids = {e.id for e in reparsed.entities}
        assert original_ids == reparsed_ids

        # Compare entity field values
        for orig in original.entities:
            reparsed_entity = _find_entity_by_id(reparsed.entities, orig.id)
            assert reparsed_entity is not None, f"Missing entity {orig.id} in reparsed"
            assert reparsed_entity.name == orig.name
            assert type(reparsed_entity).__name__ == type(orig).__name__

        # Compare memory IDs
        original_mem_ids = {m.id for m in original.memories}
        reparsed_mem_ids = {m.id for m in reparsed.memories}
        assert original_mem_ids == reparsed_mem_ids

    def test_entity_ids_preserved_through_roundtrip(self, parsed_campaign: ParseResult):
        """All entity IDs from the original fixture are present after roundtrip."""
        parsed_ids = {e.id for e in parsed_campaign.entities}
        assert parsed_ids == EXPECTED_ENTITY_IDS

    def test_memory_ids_preserved_through_roundtrip(self, parsed_campaign: ParseResult):
        """All memory IDs from the original fixture are present after roundtrip."""
        parsed_ids = {m.id for m in parsed_campaign.memories}
        assert parsed_ids == EXPECTED_MEMORY_IDS
