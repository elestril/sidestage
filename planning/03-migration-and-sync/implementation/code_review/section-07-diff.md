diff --git a/src/sidestage/migration/importer.py b/src/sidestage/migration/importer.py
new file mode 100644
index 0000000..6abcea9
--- /dev/null
+++ b/src/sidestage/migration/importer.py
@@ -0,0 +1,319 @@
+"""Import parsed campaign data into FalkorDB, replacing the existing graph."""
+
+from __future__ import annotations
+
+import logging
+import re
+from typing import TYPE_CHECKING
+
+from sidestage.graph.entities import create_entity, list_entities
+from sidestage.graph.relationships import link
+from sidestage.graph.schema import initialize_schema
+from sidestage.health import HealthStatus
+from sidestage.memory.models import Memory, MemoryType
+from sidestage.memory.store import _TYPE_TO_SUBLABEL
+from sidestage.migration.models import MigrationImportResult, ParseResult
+from sidestage.schemas import Character, ChatMessage, Entity, Event, Location, Scene
+
+if TYPE_CHECKING:
+    from sidestage.campaign import Campaign
+    from sidestage.graph.client import GraphClient
+    from sidestage.sync import SyncManager
+
+logger = logging.getLogger(__name__)
+
+_CHATLOG_RE = re.compile(
+    r"^\[([^\]]+)\]\s+\(([^)]+)\)\s+([^:]+):\s+\"(.*)\"$"
+)
+
+
+async def import_campaign(
+    campaign: Campaign,
+    parse_result: ParseResult,
+    sync_manager: SyncManager | None = None,
+    active_scenes: dict | None = None,
+) -> MigrationImportResult:
+    """Import parsed entities and memories into FalkorDB, replacing the existing graph.
+
+    This is a destructive operation: the existing graph is dropped and recreated.
+
+    Args:
+        campaign: The Campaign object (provides graph_client, storage, health, config).
+        parse_result: The parsed directory tree (entities, memories, chatlogs, errors).
+        sync_manager: Optional SyncManager for broadcasting entities_updated.
+        active_scenes: Optional dict of active scenes to clear after import.
+
+    Returns:
+        MigrationImportResult with counts of processed entities and memories.
+    """
+    errors: list[str] = []
+    processed_entities = 0
+    processed_memories = 0
+
+    if campaign.graph_client is None:
+        return MigrationImportResult(
+            phase="failed",
+            total_entities=len(parse_result.entities),
+            total_memories=len(parse_result.memories),
+            processed_entities=0,
+            processed_memories=0,
+            errors=["No graph_client available on campaign"],
+        )
+
+    try:
+        await campaign.health.set_status(HealthStatus.DEGRADED, "Importing campaign data")
+
+        # Step 2: Drop and recreate graph
+        try:
+            await _drop_and_recreate_graph(campaign)
+        except Exception as exc:
+            errors.append(f"Graph drop failed: {exc}")
+            return MigrationImportResult(
+                phase="failed",
+                total_entities=len(parse_result.entities),
+                total_memories=len(parse_result.memories),
+                processed_entities=0,
+                processed_memories=0,
+                errors=errors,
+            )
+
+        # Step 4: Insert entities
+        processed_entities, entity_errors = await _insert_entities(
+            campaign.graph_client, parse_result.entities
+        )
+        errors.extend(entity_errors)
+
+        # Step 5: Create relationships
+        rel_errors = await _create_relationships(
+            campaign.graph_client, parse_result.entities
+        )
+        errors.extend(rel_errors)
+
+        # Step 6: Insert memories
+        processed_memories, mem_errors = await _insert_memories(
+            campaign.graph_client, parse_result.memories
+        )
+        errors.extend(mem_errors)
+
+        # Step 7: Restore chat logs
+        chatlog_errors = _restore_chatlogs(campaign, parse_result.chatlogs)
+        errors.extend(chatlog_errors)
+
+        # Step 8: Verify counts
+        try:
+            inserted = await list_entities(campaign.graph_client)
+            if len(inserted) != processed_entities:
+                logger.warning(
+                    "Entity count mismatch: expected %d, got %d",
+                    processed_entities, len(inserted),
+                )
+        except Exception as exc:
+            logger.warning("Failed to verify entity counts: %s", exc)
+
+        # Step 9: Post-import cleanup
+        if active_scenes is not None:
+            active_scenes.clear()
+
+        if sync_manager is not None:
+            await sync_manager.broadcast({"type": "entities_updated"})
+
+        phase = "failed" if processed_entities == 0 and len(parse_result.entities) > 0 else "complete"
+
+        return MigrationImportResult(
+            phase=phase,
+            total_entities=len(parse_result.entities),
+            total_memories=len(parse_result.memories),
+            processed_entities=processed_entities,
+            processed_memories=processed_memories,
+            errors=errors,
+        )
+
+    finally:
+        await campaign.health.set_status(HealthStatus.HEALTHY, "")
+
+
+async def _drop_and_recreate_graph(campaign: Campaign) -> None:
+    """Drop the existing graph and reinitialize the schema."""
+    client = campaign.graph_client
+    await client.graph.delete()
+    client.graph = client.db.select_graph(client.graph_name)
+    await initialize_schema(
+        client,
+        vector_dimension=campaign.config.graph.vector_dimension,
+    )
+
+
+async def _insert_entities(
+    client: GraphClient, entities: list[Entity],
+) -> tuple[int, list[str]]:
+    """Insert all entities into the graph. Returns (success_count, errors)."""
+    count = 0
+    errors: list[str] = []
+    for entity in entities:
+        try:
+            await create_entity(client, entity)
+            count += 1
+        except Exception as exc:
+            errors.append(f"Failed to insert entity '{entity.id}': {exc}")
+            logger.warning("Failed to insert entity %s: %s", entity.id, exc)
+    return count, errors
+
+
+async def _create_relationships(
+    client: GraphClient, entities: list[Entity],
+) -> list[str]:
+    """Create all entity-to-entity relationship edges.
+
+    Handles LOCATED_IN, CONNECTS_TO (deduplicated), AT_LOCATION, HAS_EVENT.
+    """
+    errors: list[str] = []
+    connected_pairs: set[frozenset[str]] = set()
+
+    for entity in entities:
+        try:
+            if isinstance(entity, Character) and entity.location_id:
+                await link(client, entity.id, "LOCATED_IN", entity.location_id)
+        except Exception as exc:
+            errors.append(f"LOCATED_IN failed for '{entity.id}': {exc}")
+
+        try:
+            if isinstance(entity, Location):
+                for other_id in entity.connected_locations:
+                    pair = frozenset({entity.id, other_id})
+                    if pair not in connected_pairs:
+                        await link(client, entity.id, "CONNECTS_TO", other_id)
+                        connected_pairs.add(pair)
+        except Exception as exc:
+            errors.append(f"CONNECTS_TO failed for '{entity.id}': {exc}")
+
+        try:
+            if isinstance(entity, Scene) and entity.location_id:
+                await link(client, entity.id, "AT_LOCATION", entity.location_id)
+        except Exception as exc:
+            errors.append(f"AT_LOCATION failed for '{entity.id}': {exc}")
+
+        try:
+            if isinstance(entity, Event) and hasattr(entity, "scene_id"):
+                await link(client, entity.scene_id, "HAS_EVENT", entity.id)
+        except Exception as exc:
+            errors.append(f"HAS_EVENT failed for '{entity.id}': {exc}")
+
+    return errors
+
+
+async def _insert_memories(
+    client: GraphClient, memories: list[Memory],
+) -> tuple[int, list[str]]:
+    """Insert all memories with HAS_MEMORY/ABOUT relationships."""
+    count = 0
+    errors: list[str] = []
+    for memory in memories:
+        try:
+            await _insert_memory(client, memory)
+            count += 1
+        except Exception as exc:
+            errors.append(f"Failed to insert memory '{memory.id}': {exc}")
+            logger.warning("Failed to insert memory %s: %s", memory.id, exc)
+    return count, errors
+
+
+async def _insert_memory(client: GraphClient, memory: Memory) -> None:
+    """Insert a single memory node with HAS_MEMORY and ABOUT relationships.
+
+    Uses CREATE (not MERGE) since we are starting from an empty graph.
+    Preserves the original memory ID from the import data.
+    """
+    sublabel = _TYPE_TO_SUBLABEL[memory.memory_type]
+
+    params = {
+        "id": memory.id,
+        "content": memory.content,
+        "memory_type": memory.memory_type.value,
+        "visibility": memory.visibility,
+        "owner_id": memory.owner_id,
+        "target_id": memory.target_id,
+        "gametime": memory.gametime,
+        "created_at": memory.created_at,
+        "updated_at": memory.updated_at,
+        "access_count": memory.access_count,
+    }
+
+    if memory.last_accessed_at is not None:
+        params["last_accessed_at"] = memory.last_accessed_at
+
+    # Build property assignments
+    prop_parts = ", ".join(f"{k}: ${k}" for k in params)
+    last_accessed = (
+        ", last_accessed_at: $last_accessed_at"
+        if "last_accessed_at" in params
+        else ""
+    )
+
+    cypher = (
+        f"CREATE (m:Memory:{sublabel} {{{prop_parts}}})\n"
+        "WITH m\n"
+        "OPTIONAL MATCH (owner:Entity {id: $owner_id})\n"
+        "FOREACH (_ IN CASE WHEN owner IS NOT NULL THEN [1] ELSE [] END |\n"
+        "  CREATE (owner)-[:HAS_MEMORY]->(m)\n"
+        ")\n"
+        "WITH m\n"
+        "OPTIONAL MATCH (target:Entity {id: $target_id})\n"
+        "FOREACH (_ IN CASE WHEN target IS NOT NULL THEN [1] ELSE [] END |\n"
+        "  CREATE (m)-[:ABOUT]->(target)\n"
+        ")"
+    )
+
+    await client.graph.query(cypher, params=params)
+
+
+def _restore_chatlogs(
+    campaign: Campaign, chatlogs: dict[str, list[str]],
+) -> list[str]:
+    """Restore chat logs to SQLite storage. Returns list of error messages."""
+    errors: list[str] = []
+
+    for scene_id, lines in chatlogs.items():
+        if not lines:
+            continue
+        try:
+            messages = _parse_chatlog_lines(scene_id, lines)
+            existing = campaign.storage.get_scene(scene_id)
+            if existing is not None:
+                existing.messages = messages
+                campaign.storage.update_scene(existing)
+            else:
+                scene = Scene(
+                    name=scene_id, body="", id=scene_id, messages=messages,
+                )
+                campaign.storage.add_scene(scene)
+        except Exception as exc:
+            errors.append(f"Failed to restore chatlog for scene '{scene_id}': {exc}")
+            logger.warning("Failed to restore chatlog for %s: %s", scene_id, exc)
+
+    return errors
+
+
+def _parse_chatlog_lines(scene_id: str, lines: list[str]) -> list[ChatMessage]:
+    """Parse raw chatlog lines into ChatMessage objects.
+
+    Format: [{walltime}] ({character_id}) {name}: "{message}"
+    """
+    messages: list[ChatMessage] = []
+    for line in lines:
+        match = _CHATLOG_RE.match(line.strip())
+        if not match:
+            logger.warning("Unparseable chatlog line: %s", line)
+            continue
+        walltime, character_id, name, message = match.groups()
+        msg = ChatMessage(
+            name=name.strip(),
+            body="",
+            id=f"{scene_id}_msg_{len(messages)}",
+            scene_id=scene_id,
+            gametime=0,
+            walltime=walltime,
+            character_id=character_id,
+            message=message,
+        )
+        messages.append(msg)
+    return messages
diff --git a/tests/unit/test_migration_importer.py b/tests/unit/test_migration_importer.py
new file mode 100644
index 0000000..618a1dd
--- /dev/null
+++ b/tests/unit/test_migration_importer.py
@@ -0,0 +1,483 @@
+"""Tests for migration/importer.py -- import campaign from parsed data into FalkorDB."""
+
+from unittest.mock import AsyncMock, MagicMock, patch, call
+
+import pytest
+
+from sidestage.health import CampaignHealth, HealthStatus
+from sidestage.memory.models import Memory, MemoryType
+from sidestage.migration.importer import import_campaign
+from sidestage.migration.models import MigrationValidationIssue, ParseResult
+from sidestage.schemas import Character, Event, Item, JoinEvent, Location, Scene
+
+
+# --- Fixtures ---
+
+
+@pytest.fixture
+def mock_graph_client():
+    """Mock GraphClient with graph.query and graph.delete capabilities."""
+    client = MagicMock()
+    client.graph = AsyncMock()
+    client.graph.query = AsyncMock(return_value=MagicMock(result_set=[]))
+    client.graph.delete = AsyncMock()
+    client.db = MagicMock()
+    client.graph_name = "test_campaign"
+    client.db.select_graph = MagicMock(return_value=client.graph)
+    return client
+
+
+@pytest.fixture
+def mock_campaign(mock_graph_client, tmp_path):
+    """Mock Campaign object with graph_client, storage, health, and campaign_dir."""
+    campaign = MagicMock()
+    campaign.graph_client = mock_graph_client
+    campaign.campaign_dir = tmp_path
+    campaign.health = CampaignHealth()
+    campaign.storage = MagicMock()
+    campaign.storage.get_scene = MagicMock(return_value=None)
+    campaign.storage.update_scene = MagicMock()
+    campaign.storage.add_scene = MagicMock()
+    campaign.name = "test_campaign"
+    campaign.config = MagicMock()
+    campaign.config.graph = MagicMock()
+    campaign.config.graph.vector_dimension = None
+    return campaign
+
+
+@pytest.fixture
+def mock_sync_manager():
+    """Mock SyncManager for broadcast assertions."""
+    sm = MagicMock()
+    sm.broadcast = AsyncMock()
+    return sm
+
+
+@pytest.fixture
+def sample_entities():
+    """Return a list of representative Entity objects."""
+    return [
+        Character(
+            name="Eldric the Bold", body="A brave warrior.", id="char_eldric",
+            location_id="loc_tavern", inventory=["item_sword"],
+        ),
+        Character(
+            name="Alice the Merchant", body="A shrewd merchant.", id="char_alice",
+        ),
+        Location(
+            name="The Rusty Tavern", body="A dingy tavern.", id="loc_tavern",
+            connected_locations=["loc_square"],
+        ),
+        Location(
+            name="Town Square", body="The town square.", id="loc_square",
+            connected_locations=["loc_tavern"],
+        ),
+        Item(name="Flame Tongue Sword", body="A fiery blade.", id="item_sword"),
+        Scene(
+            name="Tavern Brawl", body="A brawl erupts.", id="scene_brawl",
+            location_id="loc_tavern", events=["evt_join"],
+        ),
+        JoinEvent(
+            name="Eldric Joins Brawl", body="Eldric enters the fray.",
+            id="evt_join", scene_id="scene_brawl", gametime=3600,
+            walltime="2026-01-15T14:30:00Z", actor_id="actor_1",
+        ),
+    ]
+
+
+@pytest.fixture
+def sample_memories():
+    """Return a list of sample Memory objects."""
+    return [
+        Memory(
+            id="mem_tavern_brawl", content="The brawl was fierce.",
+            memory_type=MemoryType.SCENE, visibility="private",
+            owner_id="char_eldric", target_id="scene_brawl",
+            gametime=3600, created_at=1706000000.0, updated_at=1706000000.0,
+        ),
+        Memory(
+            id="mem_knows_alice", content="Eldric met Alice.",
+            memory_type=MemoryType.CHARACTER, visibility="common",
+            owner_id="char_eldric", target_id="char_alice",
+            gametime=1800, created_at=1705900000.0, updated_at=1705900000.0,
+        ),
+        Memory(
+            id="mem_trade_secret", content="The tavern has a hidden cellar.",
+            memory_type=MemoryType.WORLD_FACT, visibility="private",
+            owner_id="char_alice", target_id="loc_tavern",
+        ),
+    ]
+
+
+@pytest.fixture
+def sample_parse_result(sample_entities, sample_memories):
+    """Return a ParseResult with representative entities, memories, and chatlogs."""
+    return ParseResult(
+        entities=sample_entities,
+        memories=sample_memories,
+        chatlogs={
+            "scene_brawl": [
+                '[2026-01-15T14:30:00Z] (char_eldric) Eldric the Bold: "I challenge you!"',
+                '[2026-01-15T14:30:05Z] (char_alice) Alice the Merchant: "You\'ll regret that."',
+            ],
+        },
+        errors=[],
+        warnings=[],
+    )
+
+
+@pytest.fixture
+def empty_parse_result():
+    """Return an empty ParseResult."""
+    return ParseResult(entities=[], memories=[], chatlogs={}, errors=[])
+
+
+# --- Concurrency guard tests ---
+
+
+@pytest.mark.anyio
+async def test_sets_health_degraded_before_import(mock_campaign, sample_parse_result, mock_sync_manager):
+    """import_campaign sets campaign.health to DEGRADED before starting graph operations."""
+    health_states = []
+
+    original_delete = mock_campaign.graph_client.graph.delete
+
+    async def capture_health_on_delete():
+        health_states.append(mock_campaign.health.status)
+        return await original_delete()
+
+    mock_campaign.graph_client.graph.delete = capture_health_on_delete
+
+    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
+        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
+            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
+                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
+                    await import_campaign(mock_campaign, sample_parse_result, mock_sync_manager)
+
+    assert HealthStatus.DEGRADED in health_states
+
+
+@pytest.mark.anyio
+async def test_restores_health_healthy_after_successful_import(mock_campaign, sample_parse_result, mock_sync_manager):
+    """After a successful import, campaign.health is restored to HEALTHY."""
+    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
+        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
+            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
+                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
+                    result = await import_campaign(mock_campaign, sample_parse_result, mock_sync_manager)
+
+    assert mock_campaign.health.status == HealthStatus.HEALTHY
+    assert result.phase == "complete"
+
+
+@pytest.mark.anyio
+async def test_restores_health_healthy_after_failed_import(mock_campaign, sample_parse_result, mock_sync_manager):
+    """If import fails (e.g., graph drop raises), health is still restored to HEALTHY."""
+    mock_campaign.graph_client.graph.delete = AsyncMock(side_effect=RuntimeError("DB down"))
+
+    result = await import_campaign(mock_campaign, sample_parse_result, mock_sync_manager)
+
+    assert mock_campaign.health.status == HealthStatus.HEALTHY
+    assert result.phase == "failed"
+    assert any("Graph drop failed" in e for e in result.errors)
+
+
+# --- Graph lifecycle tests ---
+
+
+@pytest.mark.anyio
+async def test_drops_and_recreates_graph(mock_campaign, sample_parse_result, mock_sync_manager):
+    """import_campaign calls graph.delete() then db.select_graph() and initialize_schema()."""
+    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
+        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
+            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock) as mock_init:
+                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
+                    await import_campaign(mock_campaign, sample_parse_result, mock_sync_manager)
+
+    mock_campaign.graph_client.graph.delete.assert_awaited_once()
+    mock_campaign.graph_client.db.select_graph.assert_called_once_with("test_campaign")
+    mock_init.assert_awaited_once_with(
+        mock_campaign.graph_client, vector_dimension=None,
+    )
+
+
+@pytest.mark.anyio
+async def test_graph_drop_failure_aborts_import(mock_campaign, sample_parse_result, mock_sync_manager):
+    """If graph.delete() raises, the import aborts and returns a failed result."""
+    mock_campaign.graph_client.graph.delete = AsyncMock(side_effect=RuntimeError("Connection lost"))
+
+    result = await import_campaign(mock_campaign, sample_parse_result, mock_sync_manager)
+
+    assert result.phase == "failed"
+    assert result.processed_entities == 0
+    assert result.processed_memories == 0
+
+
+# --- Entity insertion tests ---
+
+
+@pytest.mark.anyio
+async def test_inserts_all_entities_via_create_entity(mock_campaign, sample_parse_result, mock_sync_manager):
+    """Every entity in the ParseResult is inserted via graph create_entity()."""
+    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock) as mock_create:
+        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
+            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
+                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
+                    result = await import_campaign(mock_campaign, sample_parse_result, mock_sync_manager)
+
+    assert mock_create.call_count == len(sample_parse_result.entities)
+    assert result.processed_entities == len(sample_parse_result.entities)
+
+
+# --- Relationship creation tests ---
+
+
+@pytest.mark.anyio
+async def test_creates_located_in_edges_for_characters(mock_campaign, mock_sync_manager):
+    """Characters with a location_id get a LOCATED_IN edge to that location."""
+    parse_result = ParseResult(
+        entities=[
+            Character(name="A", body="", id="c1", location_id="loc1"),
+            Location(name="B", body="", id="loc1"),
+        ],
+        memories=[], chatlogs={}, errors=[],
+    )
+
+    link_calls = []
+    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
+        with patch("sidestage.migration.importer.link", new_callable=AsyncMock) as mock_link:
+            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
+                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
+                    await import_campaign(mock_campaign, parse_result, mock_sync_manager)
+            link_calls = mock_link.call_args_list
+
+    located_in_calls = [c for c in link_calls if c[0][2] == "LOCATED_IN"]
+    assert len(located_in_calls) == 1
+    assert located_in_calls[0] == call(mock_campaign.graph_client, "c1", "LOCATED_IN", "loc1")
+
+
+@pytest.mark.anyio
+async def test_creates_connects_to_edges_deduplicated(mock_campaign, mock_sync_manager):
+    """CONNECTS_TO edges are created once per pair, not twice for A->B and B->A."""
+    parse_result = ParseResult(
+        entities=[
+            Location(name="A", body="", id="loc1", connected_locations=["loc2"]),
+            Location(name="B", body="", id="loc2", connected_locations=["loc1"]),
+        ],
+        memories=[], chatlogs={}, errors=[],
+    )
+
+    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
+        with patch("sidestage.migration.importer.link", new_callable=AsyncMock) as mock_link:
+            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
+                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
+                    await import_campaign(mock_campaign, parse_result, mock_sync_manager)
+
+    connects_to_calls = [c for c in mock_link.call_args_list if c[0][2] == "CONNECTS_TO"]
+    assert len(connects_to_calls) == 1
+
+
+@pytest.mark.anyio
+async def test_creates_at_location_edges_for_scenes(mock_campaign, mock_sync_manager):
+    """Scenes with a location_id get an AT_LOCATION edge to that location."""
+    parse_result = ParseResult(
+        entities=[
+            Scene(name="S", body="", id="s1", location_id="loc1"),
+            Location(name="L", body="", id="loc1"),
+        ],
+        memories=[], chatlogs={}, errors=[],
+    )
+
+    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
+        with patch("sidestage.migration.importer.link", new_callable=AsyncMock) as mock_link:
+            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
+                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
+                    await import_campaign(mock_campaign, parse_result, mock_sync_manager)
+
+    at_location_calls = [c for c in mock_link.call_args_list if c[0][2] == "AT_LOCATION"]
+    assert len(at_location_calls) == 1
+    assert at_location_calls[0] == call(mock_campaign.graph_client, "s1", "AT_LOCATION", "loc1")
+
+
+@pytest.mark.anyio
+async def test_creates_has_event_edges_for_events(mock_campaign, mock_sync_manager):
+    """Events with a scene_id get a HAS_EVENT edge from the scene."""
+    parse_result = ParseResult(
+        entities=[
+            Scene(name="S", body="", id="s1"),
+            JoinEvent(
+                name="E", body="", id="e1", scene_id="s1",
+                gametime=0, walltime="2026-01-01T00:00:00Z", actor_id="a1",
+            ),
+        ],
+        memories=[], chatlogs={}, errors=[],
+    )
+
+    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
+        with patch("sidestage.migration.importer.link", new_callable=AsyncMock) as mock_link:
+            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
+                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
+                    await import_campaign(mock_campaign, parse_result, mock_sync_manager)
+
+    has_event_calls = [c for c in mock_link.call_args_list if c[0][2] == "HAS_EVENT"]
+    assert len(has_event_calls) == 1
+    assert has_event_calls[0] == call(mock_campaign.graph_client, "s1", "HAS_EVENT", "e1")
+
+
+# --- Memory insertion tests ---
+
+
+@pytest.mark.anyio
+async def test_inserts_memories_via_graph_query(mock_campaign, sample_parse_result, mock_sync_manager):
+    """All memories from ParseResult are inserted via graph Cypher queries."""
+    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
+        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
+            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
+                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
+                    result = await import_campaign(mock_campaign, sample_parse_result, mock_sync_manager)
+
+    assert result.processed_memories == len(sample_parse_result.memories)
+    # Memory insertion uses graph.query for Cypher CREATE
+    memory_query_calls = [
+        c for c in mock_campaign.graph_client.graph.query.call_args_list
+        if c[0] and "Memory" in str(c[0][0])
+    ]
+    assert len(memory_query_calls) == len(sample_parse_result.memories)
+
+
+@pytest.mark.anyio
+async def test_skips_embedding_generation_during_import(mock_campaign, sample_parse_result, mock_sync_manager):
+    """During import, health is DEGRADED so is_embedding_available returns False."""
+    embedding_available_during_import = []
+
+    original_delete = mock_campaign.graph_client.graph.delete
+
+    async def capture_embedding_state():
+        embedding_available_during_import.append(mock_campaign.health.is_embedding_available)
+        return await original_delete()
+
+    mock_campaign.graph_client.graph.delete = capture_embedding_state
+
+    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
+        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
+            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
+                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
+                    await import_campaign(mock_campaign, sample_parse_result, mock_sync_manager)
+
+    assert False in embedding_available_during_import
+
+
+# --- Chat log restoration tests ---
+
+
+@pytest.mark.anyio
+async def test_restores_chat_logs_via_storage(mock_campaign, mock_sync_manager):
+    """Chat logs from ParseResult are restored via campaign.storage."""
+    parse_result = ParseResult(
+        entities=[
+            Scene(name="Tavern Brawl", body="", id="scene_brawl"),
+        ],
+        memories=[],
+        chatlogs={
+            "scene_brawl": [
+                '[2026-01-15T14:30:00Z] (char_eldric) Eldric the Bold: "Hello!"',
+            ],
+        },
+        errors=[],
+    )
+
+    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
+        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
+            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
+                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
+                    await import_campaign(mock_campaign, parse_result, mock_sync_manager)
+
+    # Storage should have been called to save scene with chatlog data
+    assert mock_campaign.storage.add_scene.called or mock_campaign.storage.update_scene.called
+
+
+# --- Post-import verification tests ---
+
+
+@pytest.mark.anyio
+async def test_verifies_entity_counts_after_import(mock_campaign, sample_parse_result, mock_sync_manager):
+    """After import, the importer queries entity counts and includes them in the result."""
+    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
+        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
+            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
+                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]) as mock_list:
+                    result = await import_campaign(mock_campaign, sample_parse_result, mock_sync_manager)
+
+    # list_entities is called for verification
+    mock_list.assert_awaited()
+    assert result.total_entities == len(sample_parse_result.entities)
+
+
+@pytest.mark.anyio
+async def test_clears_active_scenes_after_import(mock_campaign, sample_parse_result, mock_sync_manager):
+    """Active scenes dict is cleared after import completes."""
+    active_scenes = {"scene_1": MagicMock(), "scene_2": MagicMock()}
+
+    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
+        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
+            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
+                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
+                    await import_campaign(
+                        mock_campaign, sample_parse_result, mock_sync_manager,
+                        active_scenes=active_scenes,
+                    )
+
+    assert len(active_scenes) == 0
+
+
+@pytest.mark.anyio
+async def test_broadcasts_entities_updated_after_import(mock_campaign, sample_parse_result, mock_sync_manager):
+    """After import, a WebSocket broadcast of entities_updated is sent."""
+    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
+        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
+            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
+                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
+                    await import_campaign(mock_campaign, sample_parse_result, mock_sync_manager)
+
+    mock_sync_manager.broadcast.assert_awaited_once_with({"type": "entities_updated"})
+
+
+# --- Empty / edge case tests ---
+
+
+@pytest.mark.anyio
+async def test_empty_parse_result_still_drops_graph(mock_campaign, empty_parse_result, mock_sync_manager):
+    """An empty parse result still drops and recreates the graph (clean slate)."""
+    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
+        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
+            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
+                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
+                    result = await import_campaign(mock_campaign, empty_parse_result, mock_sync_manager)
+
+    mock_campaign.graph_client.graph.delete.assert_awaited_once()
+    assert result.phase == "complete"
+    assert result.processed_entities == 0
+    assert result.processed_memories == 0
+
+
+@pytest.mark.anyio
+async def test_no_graph_client_returns_failed(mock_campaign, sample_parse_result, mock_sync_manager):
+    """If campaign.graph_client is None, return a failed result immediately."""
+    mock_campaign.graph_client = None
+
+    result = await import_campaign(mock_campaign, sample_parse_result, mock_sync_manager)
+
+    assert result.phase == "failed"
+    assert any("graph_client" in e.lower() for e in result.errors)
+
+
+@pytest.mark.anyio
+async def test_no_sync_manager_skips_broadcast(mock_campaign, sample_parse_result):
+    """If sync_manager is None, broadcast is skipped without error."""
+    with patch("sidestage.migration.importer.create_entity", new_callable=AsyncMock):
+        with patch("sidestage.migration.importer.link", new_callable=AsyncMock):
+            with patch("sidestage.migration.importer.initialize_schema", new_callable=AsyncMock):
+                with patch("sidestage.migration.importer.list_entities", new_callable=AsyncMock, return_value=[]):
+                    result = await import_campaign(mock_campaign, sample_parse_result, sync_manager=None)
+
+    assert result.phase == "complete"
