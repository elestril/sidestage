# Section 09: Integration Tests

## Overview

This section creates `/home/harald/src/sidestage/tests/unit/test_migration_integration.py`, the full roundtrip integration test suite for the campaign import and backup migration system. These tests exercise the complete pipeline: copying the canonical test campaign fixture to a temporary directory, parsing, validating, importing into FalkorDB, verifying graph state, backing up to disk, and comparing the output with the original input.

Unlike sections 01-08 which test individual modules in isolation with mocks, this section tests the modules working together end-to-end. These tests require a running FalkorDB instance and exercise real graph operations (create, query, delete).

### Dependencies

- **section-01-data-models**: Provides `ParseResult`, `MigrationImportResult`, `MigrationBackupResult`, `MigrationValidationReport` from `migration/models.py`
- **section-02-serialization**: Provides canonical serialization functions from `migration/serialization.py`
- **section-03-test-campaign**: Provides the canonical test fixture at `/home/harald/src/sidestage/data/test_campaign/markdown/`
- **section-06-exporter**: Provides `export_campaign()` from `migration/exporter.py`
- **section-07-importer**: Provides `import_campaign()` from `migration/importer.py`
- **section-08-routes-and-frontend**: Provides `POST /v1/campaign/import` and `POST /v1/campaign/backup` FastAPI endpoints in `orchestrator.py`

All six must be implemented before this section.

### What This Section Produces

- **Test file**: `/home/harald/src/sidestage/tests/unit/test_migration_integration.py`

---

## Background: Infrastructure and Components

### FalkorDB Graph Layer

The graph layer consists of several modules:

- **`graph/client.py`**: `GraphClient` holds the FalkorDB connection pool, `db`, `graph` handle, and `graph_name`. Created via `connect()`, cleaned up via `close()`.
- **`graph/schema.py`**: `initialize_schema(client, vector_dimension=None)` creates indexes and constraints on Entity nodes (v1 migration) and Memory nodes (v2 migration). After an import drops the graph, schema must be reinitialized.
- **`graph/entities.py`**: `create_entity(client, entity)` inserts an entity node with labels determined by `MODEL_TO_LABELS` (e.g., `["Entity", "Character"]`). `list_entities(client)` queries all Entity nodes and returns Pydantic model instances. `node_to_entity()` converts FalkorDB nodes to Pydantic models using `LABEL_TO_MODEL`.
- **`graph/relationships.py`**: `link(client, source_id, rel_type, target_id)` creates a directed edge. `get_related(client, entity_id, rel_type, direction)` queries related entities. `VALID_REL_TYPES` includes `LOCATED_IN`, `CONNECTS_TO`, `AT_LOCATION`, `HAS_EVENT`, `INVOLVES`, `PARTICIPATES_IN`.

### Memory Store

`memory/store.py` provides `upsert_memory()` which uses MERGE semantics and generates new UUIDs. The importer does NOT use `upsert_memory()` -- it uses a custom `_insert_memory()` that preserves original IDs and uses CREATE.

`Memory` model fields: `id`, `content`, `memory_type` (enum: scene/character/world_fact), `visibility`, `embedding` (excluded from disk), `owner_id`, `target_id`, `created_at`, `updated_at`, `gametime`, `access_count`, `last_accessed_at`.

### SQLite Storage

`storage.py` provides `Storage` with synchronous methods: `add_scene()`, `update_scene()`, `get_scene()`. Scene messages (chat logs) are stored in SQLite as JSON, not in FalkorDB. The importer restores chat messages via `storage.update_scene()`.

### Health System

`health.py` provides `CampaignHealth` with async `set_status(status, reason)`. Three states:
- `HEALTHY`: normal operation, `is_accepting_chat=True`, `is_embedding_available=True`
- `DEGRADED`: import in progress, `is_accepting_chat=True`, `is_embedding_available=False`
- `UNHEALTHY`: `is_accepting_chat=False`, `is_embedding_available=False`

### Campaign Object

`campaign.py` provides `Campaign` which owns `graph_client`, `storage`, `health`, `config` (with `config.graph.vector_dimension`), `campaign_dir`, and `name`.

### SyncManager

`sync.py` provides `SyncManager` with `broadcast(message)` for WebSocket notifications.

### Parser and Validator

- `migration/parser.py`: `parse_directory(markdown_dir)` returns `ParseResult` with entities, memories, chatlogs, errors, and warnings.
- `migration/validator.py`: `validate_parse_result(parse_result)` returns `MigrationValidationReport` with valid flag, counts, errors, and warnings.

### Importer

`migration/importer.py`: `import_campaign(campaign, parse_result, sync_manager, active_scenes)` orchestrates: set health DEGRADED, drop graph, recreate schema, insert entities, create relationships (LOCATED_IN, CONNECTS_TO deduplicated, AT_LOCATION, HAS_EVENT), insert memories (HAS_MEMORY, ABOUT), restore chat logs, verify counts, restore health HEALTHY. Returns `MigrationImportResult`.

### Exporter

`migration/exporter.py`: `export_campaign(campaign)` queries all entities and memories from FalkorDB, enriches relationship fields (location_id, connected_locations via graph queries), retrieves chat logs from SQLite, writes markdown directory tree, writes status.json, performs atomic swap. Returns `MigrationBackupResult`.

### Test Campaign Fixture

The canonical test campaign is at `/home/harald/src/sidestage/data/test_campaign/markdown/` and contains:

| Entity | ID | Type |
|---|---|---|
| Eldric the Bold | `char_eldric` | Character |
| Alice the Merchant | `char_alice` | Character |
| The Rusty Tavern | `loc_rusty_tavern` | Location |
| Castle Blackmoor | `loc_castle_blackmoor` | Location |
| Town Square | `loc_town_square` | Location |
| Flame Tongue Sword | `item_flame_tongue` | Item |
| Healing Potion | `item_healing_potion` | Item |
| Tavern Brawl | `scene_tavern_brawl` | Scene |
| Castle Audience | `scene_castle_audience` | Scene |
| Eldric Joins Brawl | `event_eldric_joins` | JoinEvent |

**10 entities** total (2 characters, 3 locations, 2 items, 2 scenes, 1 event).

**6 memories**: `mem_tavern_brawl`, `mem_knows_alice`, `mem_trade_secret`, `mem_haunted_history`, `mem_brawl_outcome`, `mem_castle_legend`.

**1 chat log**: `Tavern_Brawl.d/chatlog.log` with 3 lines.

**Relationships exercised**:
- LOCATED_IN: `char_eldric` -> `loc_rusty_tavern`
- CONNECTS_TO: Triangle between all 3 locations (3 deduplicated edges from 6 directional references)
- AT_LOCATION: `scene_tavern_brawl` -> `loc_rusty_tavern`, `scene_castle_audience` -> `loc_castle_blackmoor`
- HAS_EVENT: `scene_tavern_brawl` -> `event_eldric_joins`
- HAS_MEMORY / ABOUT: 6 memories with various owner/target combos

---

## Tests

Create `/home/harald/src/sidestage/tests/unit/test_migration_integration.py` with the following test stubs. Tests use `pytest` with `pytest-anyio` for async tests. Tests that interact with FalkorDB require a running FalkorDB instance and should use appropriate fixtures.

```python
"""Integration tests for the migration pipeline: import -> verify -> backup -> compare.

These tests exercise the full roundtrip: parse the canonical test campaign fixture,
import it into FalkorDB, verify graph state, back up to a second directory, and
compare the results. They require a running FalkorDB instance.

Test fixture data lives at data/test_campaign/markdown/ (created in section-03).
All tests copy fixture data to tmp_path to avoid modifying checked-in files.
"""

import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from sidestage.health import CampaignHealth, HealthStatus
from sidestage.memory.models import Memory, MemoryType
from sidestage.migration.models import ParseResult, MigrationValidationReport
from sidestage.migration.parser import parse_directory
from sidestage.migration.validator import validate_parse_result
from sidestage.migration.importer import import_campaign
from sidestage.migration.exporter import export_campaign
from sidestage.migration.serialization import (
    frontmatter_dict_to_entity,
    frontmatter_dict_to_memory,
    entity_to_frontmatter_dict,
)
from sidestage.schemas import Character, Location, Item, Scene, Event, JoinEvent


# --- Constants ---

CAMPAIGN_ROOT = Path(__file__).parent.parent.parent / "data" / "test_campaign" / "markdown"

EXPECTED_ENTITY_COUNTS = {
    "Character": 2,
    "Location": 3,
    "Item": 2,
    "Scene": 2,
    "JoinEvent": 1,
}
EXPECTED_TOTAL_ENTITIES = 10
EXPECTED_TOTAL_MEMORIES = 6
EXPECTED_CHATLOG_SCENES = 1  # Only Tavern_Brawl has a chatlog


# --- Fixtures ---


@pytest.fixture
def test_campaign_markdown(tmp_path: Path) -> Path:
    """Copy canonical test campaign to a temp directory for testing.

    Returns the path to the copied markdown/ directory.
    """
    dst = tmp_path / "markdown"
    shutil.copytree(CAMPAIGN_ROOT, dst)
    return dst


@pytest.fixture
def backup_dir(tmp_path: Path) -> Path:
    """Return a second temp directory for backup output."""
    d = tmp_path / "backup_campaign"
    d.mkdir()
    return d


@pytest.fixture
def parsed_campaign(test_campaign_markdown: Path) -> ParseResult:
    """Parse the test campaign fixture and return the ParseResult.

    This fixture validates that parsing succeeds with no errors.
    """
    result = parse_directory(test_campaign_markdown)
    assert len(result.errors) == 0, f"Parse errors: {result.errors}"
    return result


@pytest.fixture
def validated_campaign(parsed_campaign: ParseResult) -> MigrationValidationReport:
    """Validate the parsed campaign and return the report.

    Asserts that validation passes (valid=True, no errors except the
    always-present data-loss warning).
    """
    report = validate_parse_result(parsed_campaign)
    assert report.valid, f"Validation errors: {report.errors}"
    return report


@pytest.fixture
def mock_campaign(tmp_path: Path):
    """Mock Campaign object for integration tests that need graph interactions.

    For tests that require actual FalkorDB, this fixture should be replaced
    with a real Campaign connected to a test FalkorDB instance. The mock
    version is useful for testing the pipeline logic without a live database.
    """
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
    return campaign


@pytest.fixture
def mock_sync_manager():
    """Mock SyncManager for verifying broadcast calls."""
    sm = MagicMock()
    sm.broadcast = AsyncMock()
    return sm


# =============================================================================
# Test 1: Full Roundtrip (import -> backup -> compare)
# =============================================================================


class TestFullRoundtrip:
    """Full roundtrip integration tests: parse -> validate -> import -> backup -> compare."""

    def test_parse_produces_correct_entity_counts(self, parsed_campaign: ParseResult):
        """Parsing the test campaign yields the expected number and types of entities.

        Expected: 2 Characters, 3 Locations, 2 Items, 2 Scenes, 1 JoinEvent = 10 total.
        """

    def test_parse_produces_correct_memory_count(self, parsed_campaign: ParseResult):
        """Parsing the test campaign yields exactly 6 memories."""

    def test_parse_produces_correct_chatlog_count(self, parsed_campaign: ParseResult):
        """Parsing the test campaign yields 1 scene with chat log (Tavern_Brawl)."""

    def test_validation_passes_with_no_errors(self, validated_campaign: MigrationValidationReport):
        """Validation of the test campaign produces valid=True with no error-severity issues.

        The data-loss warning is expected as a warning, not an error.
        """

    def test_validation_includes_data_loss_warning(self, validated_campaign: MigrationValidationReport):
        """Validation always includes the data-loss warning even when all references are valid."""

    @pytest.mark.anyio
    async def test_import_completes_successfully(
        self, mock_campaign, parsed_campaign, mock_sync_manager
    ):
        """import_campaign returns a result with phase='complete' and correct counts.

        This test uses a mock campaign (no real FalkorDB). It verifies the importer
        orchestration logic: health transitions, entity/memory insertion calls,
        relationship creation calls, and final cleanup.
        """

    @pytest.mark.anyio
    async def test_health_transitions_during_import(
        self, mock_campaign, parsed_campaign, mock_sync_manager
    ):
        """During import, health transitions to DEGRADED then back to HEALTHY.

        After import_campaign returns, campaign.health.status should be HEALTHY.
        """

    @pytest.mark.anyio
    async def test_broadcast_sent_after_import(
        self, mock_campaign, parsed_campaign, mock_sync_manager
    ):
        """After a successful import, sync_manager.broadcast is called with entities_updated."""


# =============================================================================
# Test 2: Entity Fidelity (canonical format = API format)
# =============================================================================


class TestEntityFidelity:
    """Verify that entity data survives the parse -> serialize roundtrip unchanged."""

    def test_entity_frontmatter_dict_roundtrip_all_types(self, parsed_campaign: ParseResult):
        """For every parsed entity, converting to frontmatter dict and back produces
        an identical entity. This validates the canonical format is lossless.

        Steps:
        1. For each entity in parsed_campaign.entities
        2. Call entity_to_frontmatter_dict(entity) -> (fm_dict, body)
        3. Call frontmatter_dict_to_entity(fm_dict, body) -> restored
        4. Assert restored.id == entity.id, restored.name == entity.name, etc.
        """

    def test_character_fields_preserved(self, parsed_campaign: ParseResult):
        """Character-specific fields (location_id, inventory, unseen) survive roundtrip.

        Verify Eldric has location_id='loc_rusty_tavern', inventory=['item_flame_tongue'].
        Verify Alice has location_id=None, inventory=[].
        """

    def test_location_fields_preserved(self, parsed_campaign: ParseResult):
        """Location-specific fields (connected_locations) survive roundtrip.

        Each of the 3 locations should have exactly 2 entries in connected_locations.
        """

    def test_scene_fields_preserved(self, parsed_campaign: ParseResult):
        """Scene-specific fields (location_id, current_gametime, events) survive roundtrip.

        Tavern_Brawl: location_id='loc_rusty_tavern', current_gametime=7200.
        Castle_Audience: location_id='loc_castle_blackmoor', current_gametime=None.
        Messages should be empty (stripped from frontmatter by parser).
        """

    def test_event_subtype_preserved(self, parsed_campaign: ParseResult):
        """JoinEvent subtype and its fields (actor_id, scene_id) survive roundtrip."""


# =============================================================================
# Test 3: Memory Fidelity
# =============================================================================


class TestMemoryFidelity:
    """Verify that memory data survives the parse roundtrip with all fields intact."""

    def test_all_memory_fields_preserved(self, parsed_campaign: ParseResult):
        """For each memory: id, content, memory_type, visibility, owner_id, target_id,
        gametime, created_at, updated_at, access_count, last_accessed_at are preserved.

        Embedding should be None (not stored on disk).
        """

    def test_memory_types_correct(self, parsed_campaign: ParseResult):
        """Parsed memories have the correct memory_type values:
        - mem_tavern_brawl: scene
        - mem_knows_alice: character
        - mem_trade_secret: world_fact
        - mem_haunted_history: world_fact
        - mem_brawl_outcome: scene
        - mem_castle_legend: world_fact
        """

    def test_memory_visibility_correct(self, parsed_campaign: ParseResult):
        """Parsed memories have the correct visibility values:
        - mem_tavern_brawl: private
        - mem_trade_secret: private
        - Others: common
        """

    def test_memory_owner_target_correct(self, parsed_campaign: ParseResult):
        """Each memory has the correct owner_id and target_id as defined in the fixture.

        - mem_tavern_brawl: owner=char_eldric, target=scene_tavern_brawl
        - mem_knows_alice: owner=char_eldric, target=char_alice
        - mem_trade_secret: owner=char_alice, target=loc_rusty_tavern
        - mem_haunted_history: owner=None, target=loc_rusty_tavern
        - mem_brawl_outcome: owner=None, target=scene_tavern_brawl
        - mem_castle_legend: owner=None, target=loc_castle_blackmoor
        """


# =============================================================================
# Test 4: Chat Log Fidelity
# =============================================================================


class TestChatLogFidelity:
    """Verify that chat log data is parsed correctly from chatlog.log files."""

    def test_chatlog_parsed_for_tavern_brawl(self, parsed_campaign: ParseResult):
        """The Tavern_Brawl scene has a chatlog with 3 lines parsed."""

    def test_chatlog_lines_match_expected_format(self, parsed_campaign: ParseResult):
        """Each chatlog line matches the [timestamp] (character_id) Name: "message" format."""

    def test_chatlog_contains_correct_speakers(self, parsed_campaign: ParseResult):
        """The chatlog contains messages from char_eldric and char_alice."""

    def test_no_chatlog_for_castle_audience(self, parsed_campaign: ParseResult):
        """The Castle_Audience scene has no chatlog (no .d/ directory)."""


# =============================================================================
# Test 5: Relationship Integrity
# =============================================================================


class TestRelationshipIntegrity:
    """Verify that entity cross-references are consistent in the parsed data."""

    def test_character_location_references_valid(self, parsed_campaign: ParseResult):
        """Eldric's location_id (loc_rusty_tavern) exists in the parsed locations.
        Alice's location_id is None (valid).
        """

    def test_character_inventory_references_valid(self, parsed_campaign: ParseResult):
        """Eldric's inventory [item_flame_tongue] references a valid item entity."""

    def test_location_connectivity_triangle(self, parsed_campaign: ParseResult):
        """The 3 locations form a complete connectivity triangle.

        Each location's connected_locations lists the other two location IDs.
        Verify: loc_rusty_tavern connects to [loc_castle_blackmoor, loc_town_square],
        loc_castle_blackmoor connects to [loc_rusty_tavern, loc_town_square],
        loc_town_square connects to [loc_rusty_tavern, loc_castle_blackmoor].
        """

    def test_connects_to_deduplication_count(self, parsed_campaign: ParseResult):
        """The triangle has 6 directional references but should produce only 3 unique
        undirected pairs when deduplicated for CONNECTS_TO edge creation.

        Pairs: {rusty_tavern, castle_blackmoor}, {rusty_tavern, town_square},
               {castle_blackmoor, town_square}.
        """

    def test_scene_location_references_valid(self, parsed_campaign: ParseResult):
        """Both scenes reference valid location IDs:
        - Tavern_Brawl -> loc_rusty_tavern
        - Castle_Audience -> loc_castle_blackmoor
        """

    def test_event_scene_references_valid(self, parsed_campaign: ParseResult):
        """The JoinEvent references scene_tavern_brawl which exists in parsed scenes."""


# =============================================================================
# Test 6: Validation Errors (broken references)
# =============================================================================


class TestValidationErrors:
    """Verify that the validator catches broken references in modified fixture data."""

    def test_broken_character_location_ref(self, test_campaign_markdown: Path):
        """Modify a character to reference a nonexistent location_id.

        Parse the modified fixture, validate, and assert an error is reported.
        """

    def test_broken_character_inventory_ref(self, test_campaign_markdown: Path):
        """Modify a character's inventory to reference a nonexistent item.

        Parse, validate, assert error with the offending ID in the message.
        """

    def test_broken_scene_location_ref(self, test_campaign_markdown: Path):
        """Modify a scene to reference a nonexistent location_id.

        Parse, validate, assert error.
        """

    def test_broken_event_scene_ref(self, test_campaign_markdown: Path):
        """Modify an event to reference a nonexistent scene_id.

        Parse, validate, assert error.
        """

    def test_broken_memory_target_ref(self, test_campaign_markdown: Path):
        """Modify a memory to reference a nonexistent target_id.

        Parse, validate, assert error.
        """

    def test_broken_memory_owner_ref(self, test_campaign_markdown: Path):
        """Modify a memory to reference a nonexistent owner_id.

        Parse, validate, assert error.
        """


# =============================================================================
# Test 7: Concurrency Guard
# =============================================================================


class TestConcurrencyGuard:
    """Verify health status transitions and concurrency protection during import."""

    @pytest.mark.anyio
    async def test_health_degraded_during_import(self, mock_campaign, parsed_campaign, mock_sync_manager):
        """During import execution, campaign.health.status is set to DEGRADED.

        The test verifies that set_status was called with DEGRADED before graph ops,
        and that health is restored to HEALTHY after import completes.
        """

    @pytest.mark.anyio
    async def test_health_restored_on_import_failure(self, mock_campaign, parsed_campaign, mock_sync_manager):
        """Even if import fails (e.g., graph drop raises), health is restored to HEALTHY.

        Simulate a failure by making graph.delete() raise an exception.
        Assert health is HEALTHY after import_campaign returns.
        """

    @pytest.mark.anyio
    async def test_is_embedding_available_false_during_import(self, mock_campaign, parsed_campaign, mock_sync_manager):
        """While health is DEGRADED, is_embedding_available returns False.

        This blocks background embedding generation during import.
        """

    @pytest.mark.anyio
    async def test_active_scenes_cleared_after_import(self, mock_campaign, parsed_campaign, mock_sync_manager):
        """The active_scenes dict is cleared after import completes."""


# =============================================================================
# Test 8: Re-import from Backup (idempotency)
# =============================================================================


class TestReimportFromBackup:
    """Verify that importing, backing up, and re-importing produces identical results."""

    def test_backup_parse_matches_original_parse(
        self, test_campaign_markdown: Path, backup_dir: Path
    ):
        """Parse the original fixture and a hypothetical backup of the same data.

        Both should produce the same entity IDs, memory IDs, and entity field values.
        This test validates the serialization roundtrip at the filesystem level:
        original markdown -> parse -> (serialize back to markdown) -> parse -> compare.
        """

    def test_entity_ids_preserved_through_roundtrip(self, parsed_campaign: ParseResult):
        """All entity IDs from the original fixture are present after roundtrip.

        IDs: char_eldric, char_alice, loc_rusty_tavern, loc_castle_blackmoor,
        loc_town_square, item_flame_tongue, item_healing_potion, scene_tavern_brawl,
        scene_castle_audience, event_eldric_joins.
        """

    def test_memory_ids_preserved_through_roundtrip(self, parsed_campaign: ParseResult):
        """All memory IDs from the original fixture are present after roundtrip.

        IDs: mem_tavern_brawl, mem_knows_alice, mem_trade_secret,
        mem_haunted_history, mem_brawl_outcome, mem_castle_legend.
        """
```

---

## Implementation Details

### File: `/home/harald/src/sidestage/tests/unit/test_migration_integration.py`

This test file exercises the migration pipeline end-to-end. Below is guidance on implementing each test class.

### Shared test helpers

Several helpers are useful across multiple test classes:

```python
def _read_frontmatter(file_path: Path) -> tuple[dict, str]:
    """Read a markdown file and return (frontmatter_dict, body).

    Splits on --- delimiters and parses YAML.
    """

def _modify_frontmatter(file_path: Path, updates: dict) -> None:
    """Read a markdown file, update its frontmatter fields, and write it back.

    Used by TestValidationErrors to introduce broken references.
    """

def _find_entity_by_id(entities: list, entity_id: str):
    """Find an entity in a list by its id field."""

def _find_memory_by_id(memories: list, memory_id: str):
    """Find a memory in a list by its id field."""
```

### TestFullRoundtrip implementation notes

- **test_parse_produces_correct_entity_counts**: Group `parsed_campaign.entities` by `type(e).__name__` and compare against `EXPECTED_ENTITY_COUNTS`. Verify total is 10.
- **test_parse_produces_correct_memory_count**: Assert `len(parsed_campaign.memories) == 6`.
- **test_parse_produces_correct_chatlog_count**: Assert `len(parsed_campaign.chatlogs) == 1` and `"scene_tavern_brawl" in parsed_campaign.chatlogs`.
- **test_validation_passes_with_no_errors**: Assert `validated_campaign.valid is True` and `len(validated_campaign.errors) == 0`.
- **test_validation_includes_data_loss_warning**: Assert `len(validated_campaign.warnings) >= 1` and at least one warning mentions "data loss" or "drop" or "cannot be undone".
- **test_import_completes_successfully**: Call `import_campaign(mock_campaign, parsed_campaign, mock_sync_manager)` with appropriately configured mocks for `graph.delete()`, `db.select_graph()`, etc. Assert result `phase == "complete"` and counts match expectations. The mock campaign's `graph_client.graph` must support async `.delete()` and `.query()` calls.
- **test_health_transitions_during_import**: After calling `import_campaign()`, assert `mock_campaign.health.status == HealthStatus.HEALTHY`. The CampaignHealth fixture is a real instance (not mocked), so `set_status()` actually transitions the state.
- **test_broadcast_sent_after_import**: Assert `mock_sync_manager.broadcast.called` and the message contains `{"type": "entities_updated"}`.

### TestEntityFidelity implementation notes

- **test_entity_frontmatter_dict_roundtrip_all_types**: For each entity in `parsed_campaign.entities`, call `entity_to_frontmatter_dict(entity)` to get `(fm, body)`, then `frontmatter_dict_to_entity(fm, body)` to reconstruct. Compare key fields: `id`, `name`, `body`, and type-specific fields.
- **test_character_fields_preserved**: Find `char_eldric` and `char_alice` in parsed entities. Assert Eldric's `location_id == "loc_rusty_tavern"` and `inventory == ["item_flame_tongue"]`. Assert Alice's `location_id is None` and `inventory == []`.
- **test_location_fields_preserved**: Find all 3 locations. Each should have `len(connected_locations) == 2`.
- **test_scene_fields_preserved**: Find both scenes. Tavern_Brawl should have `current_gametime == 7200` and `events == ["event_eldric_joins"]`. Castle_Audience should have `current_gametime is None`. Both should have `messages == []` (stripped by parser).
- **test_event_subtype_preserved**: Find entity with `id == "event_eldric_joins"`. Assert `isinstance(entity, JoinEvent)`, `actor_id == "char_eldric"`, `scene_id == "scene_tavern_brawl"`.

### TestMemoryFidelity implementation notes

- **test_all_memory_fields_preserved**: For each memory, assert `embedding is None`. Check that `created_at`, `updated_at`, `access_count` are present and non-None.
- **test_memory_types_correct**: Build a dict mapping memory ID to `memory_type` and compare against expected values.
- **test_memory_visibility_correct**: Check `mem_tavern_brawl.visibility == "private"`, `mem_trade_secret.visibility == "private"`, and all others are `"common"`.
- **test_memory_owner_target_correct**: Check each memory's `owner_id` and `target_id` against the table in section-03.

### TestChatLogFidelity implementation notes

- **test_chatlog_parsed_for_tavern_brawl**: Assert `"scene_tavern_brawl" in parsed_campaign.chatlogs` and `len(parsed_campaign.chatlogs["scene_tavern_brawl"]) == 3`.
- **test_chatlog_lines_match_expected_format**: Each line should match the regex `r"\[.*\] \(.*\) .*: \".*\""` (timestamp, character_id, name, message).
- **test_chatlog_contains_correct_speakers**: At least one line contains `(char_eldric)` and at least one contains `(char_alice)`.
- **test_no_chatlog_for_castle_audience**: Assert `"scene_castle_audience" not in parsed_campaign.chatlogs`.

### TestRelationshipIntegrity implementation notes

- **test_character_location_references_valid**: Build a set of location IDs from parsed locations. Assert `char_eldric.location_id` is in that set. Assert `char_alice.location_id is None`.
- **test_character_inventory_references_valid**: Build a set of item IDs. Assert each ID in Eldric's inventory is in that set.
- **test_location_connectivity_triangle**: Build a dict of `loc_id -> connected_locations` from parsed locations. Assert each location references exactly the other two.
- **test_connects_to_deduplication_count**: Collect all `frozenset({loc_id, other_id})` pairs from all locations' `connected_locations`. Assert the set of unique pairs has exactly 3 elements.
- **test_scene_location_references_valid**: Assert both scene `location_id` values are in the set of location IDs.
- **test_event_scene_references_valid**: Assert `event_eldric_joins.scene_id` is in the set of scene IDs.

### TestValidationErrors implementation notes

Each test modifies the fixture data in `test_campaign_markdown` (already a tmp_path copy), re-parses, re-validates, and asserts validation errors.

The `_modify_frontmatter` helper reads a file, parses frontmatter, updates specific fields, and writes it back. Example for `test_broken_character_location_ref`:

```python
def test_broken_character_location_ref(self, test_campaign_markdown: Path):
    # Modify Eldric's location_id to reference a nonexistent location
    eldric_path = test_campaign_markdown / "characters" / "Eldric_the_Bold.md"
    _modify_frontmatter(eldric_path, {"location_id": "loc_nonexistent"})

    result = parse_directory(test_campaign_markdown)
    report = validate_parse_result(result)

    assert not report.valid
    assert any("loc_nonexistent" in e.message for e in report.errors)
```

Similar pattern for all broken-reference tests: modify one field to point at a nonexistent ID, parse, validate, assert `valid == False` and the error mentions the broken reference.

### TestConcurrencyGuard implementation notes

- **test_health_degraded_during_import**: The key challenge is observing health status during import (not just before/after). One approach: use a real `CampaignHealth` instance and patch one of the graph operations (e.g., `create_entity`) to assert `campaign.health.status == HealthStatus.DEGRADED` when called. After import returns, assert status is HEALTHY.
- **test_health_restored_on_import_failure**: Make `mock_campaign.graph_client.graph.delete` raise an `Exception`. Call `import_campaign()`. Assert the result has `phase == "failed"`. Assert `mock_campaign.health.status == HealthStatus.HEALTHY`.
- **test_is_embedding_available_false_during_import**: Similar to the DEGRADED test -- patch a graph operation to check `campaign.health.is_embedding_available is False` during import.
- **test_active_scenes_cleared_after_import**: Pass `active_scenes={"scene_1": MagicMock()}` to `import_campaign()`. After completion, assert `len(active_scenes) == 0`.

### TestReimportFromBackup implementation notes

- **test_backup_parse_matches_original_parse**: This test validates filesystem-level roundtrip. Parse the original fixture, then for each entity call `entity_to_frontmatter_dict()` and write to a temp directory in the canonical layout, then parse that directory. Compare entity IDs and key fields.
- **test_entity_ids_preserved_through_roundtrip**: Assert all 10 expected entity IDs are in the parsed entities.
- **test_memory_ids_preserved_through_roundtrip**: Assert all 6 expected memory IDs are in the parsed memories.

### Mock Campaign Setup for Import Tests

For tests that call `import_campaign()`, the mock campaign must have:

```python
# Graph client with async-compatible mocks
campaign.graph_client = MagicMock()
campaign.graph_client.graph = AsyncMock()
campaign.graph_client.graph.delete = AsyncMock()
campaign.graph_client.graph.query = AsyncMock(return_value=MagicMock(result_set=[]))
campaign.graph_client.db = MagicMock()
campaign.graph_client.graph_name = "test_campaign"
campaign.graph_client.db.select_graph = MagicMock(return_value=campaign.graph_client.graph)
```

The `create_entity`, `link`, and `initialize_schema` functions from the graph module should be patched at the module level where they are imported in `importer.py`:

```python
@pytest.fixture(autouse=True)
def patch_graph_operations():
    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock) as mock_create, \
         patch("sidestage.migration.importer.link", new_callable=AsyncMock) as mock_link, \
         patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock) as mock_schema, \
         patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]) as mock_list:
        yield {
            "create_entity": mock_create,
            "link": mock_link,
            "initialize_schema": mock_schema,
            "list_entities": mock_list,
        }
```

This allows verifying call counts and arguments on each mocked function without requiring a live FalkorDB.

### Relationship to other sections

- **section-03-test-campaign**: This section consumes the test fixture files created there. All tests copy from `data/test_campaign/markdown/` to `tmp_path`.
- **section-04-parser**: `parse_directory()` is called directly in many tests as the first step of the pipeline.
- **section-05-validator**: `validate_parse_result()` is called in validation tests and as a prerequisite fixture.
- **section-06-exporter**: `export_campaign()` would be called in full-roundtrip tests that include backup. Those tests require FalkorDB or extensive mocking of the exporter's graph queries.
- **section-07-importer**: `import_campaign()` is called in import and concurrency guard tests.
- **section-08-routes-and-frontend**: API endpoint tests (POST /v1/campaign/import returning 409 during DEGRADED) are in `test_migration_routes.py` from section-08, not here. This section focuses on the underlying pipeline, not the HTTP layer.

### Acceptance Criteria

1. All test stubs in `test_migration_integration.py` pass when sections 01-08 are fully implemented
2. The `test_campaign_markdown` fixture successfully copies from `data/test_campaign/markdown/` to `tmp_path`
3. Parsing the test campaign produces 10 entities, 6 memories, and 1 scene chatlog with no errors
4. Validation of the test campaign passes (valid=True) with only the data-loss warning
5. Entity fidelity tests confirm all type-specific fields survive the serialization roundtrip
6. Memory fidelity tests confirm all memory fields (except embedding) survive the roundtrip
7. Chat log tests confirm correct line count, format, and speaker identification
8. Relationship integrity tests confirm all cross-references are consistent
9. Validation error tests confirm broken references are caught with descriptive messages
10. Concurrency guard tests confirm DEGRADED/HEALTHY transitions and embedding availability
11. Re-import tests confirm entity and memory IDs are preserved through the roundtrip
