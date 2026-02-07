diff --git a/planning/01-falkordb-foundation/implementation/deep_implement_config.json b/planning/01-falkordb-foundation/implementation/deep_implement_config.json
index 8fb9cf9..20b66d5 100644
--- a/planning/01-falkordb-foundation/implementation/deep_implement_config.json
+++ b/planning/01-falkordb-foundation/implementation/deep_implement_config.json
@@ -26,6 +26,10 @@
     "section-03-entities": {
       "status": "complete",
       "commit_hash": "66f4564"
+    },
+    "section-04-relationships": {
+      "status": "complete",
+      "commit_hash": "404182a02436744a10c86e6b9c296fec84e8a1c2"
     }
   },
   "pre_commit": {
diff --git a/src/sidestage/graph/queries.py b/src/sidestage/graph/queries.py
new file mode 100644
index 0000000..e618016
--- /dev/null
+++ b/src/sidestage/graph/queries.py
@@ -0,0 +1,135 @@
+"""Higher-level graph query functions for common traversal patterns.
+
+Provides specialized, efficient Cypher-based query functions that combine
+entity and relationship operations into single graph traversals.
+"""
+
+from __future__ import annotations
+
+import logging
+from typing import Any, TYPE_CHECKING
+
+from sidestage.graph.entities import node_to_entity
+from sidestage.graph.errors import QueryError
+from sidestage.schemas import Character, Entity, Event, Location
+
+if TYPE_CHECKING:
+    from sidestage.graph.client import GraphClient
+
+logger = logging.getLogger(__name__)
+
+
+async def characters_at_location(client: GraphClient, location_id: str) -> list[Character]:
+    """All characters currently at a location (via LOCATED_IN).
+
+    Returns a list of Character models. Returns empty list if no characters
+    are at the location or if the location does not exist.
+    """
+    cypher = (
+        "MATCH (c:Character)-[:LOCATED_IN]->(l:Location {id: $location_id}) "
+        "RETURN c"
+    )
+
+    logger.debug("characters_at_location id=%s", location_id)
+
+    try:
+        result = await client.graph.query(cypher, params={"location_id": location_id})
+    except Exception as exc:
+        raise QueryError(f"Failed to query characters at location '{location_id}': {exc}") from exc
+
+    characters = [node_to_entity(row[0].labels, row[0].properties) for row in result.result_set]
+    logger.debug("characters_at_location returned %d characters", len(characters))
+    return characters
+
+
+async def connected_locations(client: GraphClient, location_id: str) -> list[Location]:
+    """All locations connected to a given location (CONNECTS_TO, both directions).
+
+    Uses undirected match since CONNECTS_TO is semantically bidirectional.
+    Returns a list of Location models. Returns empty list if no connections exist.
+    """
+    cypher = (
+        "MATCH (l:Location {id: $location_id})-[:CONNECTS_TO]-(other:Location) "
+        "RETURN other"
+    )
+
+    logger.debug("connected_locations id=%s", location_id)
+
+    try:
+        result = await client.graph.query(cypher, params={"location_id": location_id})
+    except Exception as exc:
+        raise QueryError(f"Failed to query connected locations for '{location_id}': {exc}") from exc
+
+    locations = [node_to_entity(row[0].labels, row[0].properties) for row in result.result_set]
+    logger.debug("connected_locations returned %d locations", len(locations))
+    return locations
+
+
+async def scene_events(
+    client: GraphClient, scene_id: str, since_gametime: int | None = None
+) -> list[Event]:
+    """Events in a scene, optionally filtered by gametime.
+
+    Returns a list of Event models (may include ChatMessage subtype based
+    on node labels). Returns empty list if scene has no events.
+    Always ordered by gametime ascending.
+    """
+    params: dict[str, Any] = {"scene_id": scene_id}
+
+    if since_gametime is not None:
+        cypher = (
+            "MATCH (s:Scene {id: $scene_id})-[:HAS_EVENT]->(e:Event) "
+            "WHERE e.gametime >= $since_gametime "
+            "RETURN e ORDER BY e.gametime ASC"
+        )
+        params["since_gametime"] = since_gametime
+    else:
+        cypher = (
+            "MATCH (s:Scene {id: $scene_id})-[:HAS_EVENT]->(e:Event) "
+            "RETURN e ORDER BY e.gametime ASC"
+        )
+
+    logger.debug("scene_events id=%s since=%s", scene_id, since_gametime)
+
+    try:
+        result = await client.graph.query(cypher, params=params)
+    except Exception as exc:
+        raise QueryError(f"Failed to query events for scene '{scene_id}': {exc}") from exc
+
+    events = [node_to_entity(row[0].labels, row[0].properties) for row in result.result_set]
+    logger.debug("scene_events returned %d events", len(events))
+    return events
+
+
+async def entity_graph(client: GraphClient, entity_id: str, depth: int = 1) -> dict:
+    """Get an entity and its neighborhood to a given depth.
+
+    Returns a dict with:
+        - "entity": the center Entity model (or None if not found)
+        - "related": list of Entity models within the given depth
+    """
+    cypher = (
+        "MATCH (center:Entity {id: $entity_id}) "
+        f"OPTIONAL MATCH path = (center)-[*1..{depth}]-(neighbor:Entity) "
+        "RETURN center, collect(DISTINCT neighbor) AS neighbors"
+    )
+
+    logger.debug("entity_graph id=%s depth=%d", entity_id, depth)
+
+    try:
+        result = await client.graph.query(cypher, params={"entity_id": entity_id})
+    except Exception as exc:
+        raise QueryError(f"Failed to query entity graph for '{entity_id}': {exc}") from exc
+
+    if not result.result_set:
+        return {"entity": None, "related": []}
+
+    row = result.result_set[0]
+    center_node = row[0]
+    neighbor_nodes = row[1]
+
+    entity = node_to_entity(center_node.labels, center_node.properties)
+    related = [node_to_entity(n.labels, n.properties) for n in neighbor_nodes]
+
+    logger.debug("entity_graph returned entity + %d related", len(related))
+    return {"entity": entity, "related": related}
diff --git a/tests/unit/test_graph_queries.py b/tests/unit/test_graph_queries.py
new file mode 100644
index 0000000..39e2cc1
--- /dev/null
+++ b/tests/unit/test_graph_queries.py
@@ -0,0 +1,299 @@
+"""Unit tests for graph query functions."""
+import pytest
+from unittest.mock import AsyncMock, MagicMock
+
+from sidestage.graph.errors import QueryError
+from sidestage.graph.queries import (
+    characters_at_location,
+    connected_locations,
+    scene_events,
+    entity_graph,
+)
+from sidestage.schemas import Character, ChatMessage, Event, Location
+
+
+# --- Fixtures ---
+
+
+@pytest.fixture
+def mock_client():
+    """Create a mock GraphClient with an async query method."""
+    client = MagicMock()
+    client.graph = MagicMock()
+    client.graph.query = AsyncMock()
+    return client
+
+
+def _make_node_mock(labels, properties):
+    """Helper to create a mock graph node."""
+    node = MagicMock()
+    node.labels = labels
+    node.properties = properties
+    return node
+
+
+# --- characters_at_location ---
+
+
+@pytest.mark.anyio
+async def test_characters_at_location_returns_characters(mock_client):
+    """characters_at_location returns characters LOCATED_IN the given location."""
+    node = _make_node_mock(
+        ["Entity", "Character"],
+        {"id": "char_1", "name": "Alice", "body": "A warrior", "unseen": False, "inventory": []},
+    )
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    result = await characters_at_location(mock_client, "loc_tavern")
+
+    assert len(result) == 1
+    assert isinstance(result[0], Character)
+    assert result[0].id == "char_1"
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "LOCATED_IN" in cypher
+    assert ":Character" in cypher
+
+
+@pytest.mark.anyio
+async def test_characters_at_location_empty(mock_client):
+    """characters_at_location returns empty list for empty location."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    result = await characters_at_location(mock_client, "loc_empty")
+
+    assert result == []
+
+
+@pytest.mark.anyio
+async def test_characters_at_location_query_error(mock_client):
+    """characters_at_location raises QueryError on failure."""
+    mock_client.graph.query.side_effect = Exception("network timeout")
+
+    with pytest.raises(QueryError):
+        await characters_at_location(mock_client, "loc_tavern")
+
+
+# --- connected_locations ---
+
+
+@pytest.mark.anyio
+async def test_connected_locations_both_directions(mock_client):
+    """connected_locations returns all CONNECTS_TO locations (both directions)."""
+    node1 = _make_node_mock(
+        ["Entity", "Location"],
+        {"id": "loc_2", "name": "Forest", "body": "A dark forest"},
+    )
+    node2 = _make_node_mock(
+        ["Entity", "Location"],
+        {"id": "loc_3", "name": "River", "body": "A flowing river"},
+    )
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node1], [node2]])
+
+    result = await connected_locations(mock_client, "loc_tavern")
+
+    assert len(result) == 2
+    assert all(isinstance(loc, Location) for loc in result)
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "CONNECTS_TO" in cypher
+    # Should use undirected pattern (no -> or <-)
+    assert "->" not in cypher
+    assert "<-" not in cypher
+
+
+@pytest.mark.anyio
+async def test_connected_locations_empty(mock_client):
+    """connected_locations returns empty list when no connections."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    result = await connected_locations(mock_client, "loc_isolated")
+
+    assert result == []
+
+
+@pytest.mark.anyio
+async def test_connected_locations_query_error(mock_client):
+    """connected_locations raises QueryError on failure."""
+    mock_client.graph.query.side_effect = Exception("network timeout")
+
+    with pytest.raises(QueryError):
+        await connected_locations(mock_client, "loc_tavern")
+
+
+# --- scene_events ---
+
+
+@pytest.mark.anyio
+async def test_scene_events_returns_events(mock_client):
+    """scene_events returns all events in a scene via HAS_EVENT."""
+    node = _make_node_mock(
+        ["Entity", "Event"],
+        {
+            "id": "evt_1", "name": "event1", "body": "Something happened",
+            "scene_id": "scene_01", "gametime": 100, "walltime": "2024-01-01T00:00:00",
+        },
+    )
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    result = await scene_events(mock_client, "scene_01")
+
+    assert len(result) == 1
+    assert isinstance(result[0], Event)
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "HAS_EVENT" in cypher
+    assert "ORDER BY" in cypher
+
+
+@pytest.mark.anyio
+async def test_scene_events_with_since_gametime(mock_client):
+    """scene_events with since_gametime filters by gametime."""
+    node = _make_node_mock(
+        ["Entity", "Event"],
+        {
+            "id": "evt_2", "name": "event2", "body": "Later event",
+            "scene_id": "scene_01", "gametime": 3700, "walltime": "2024-01-01T01:01:40",
+        },
+    )
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    result = await scene_events(mock_client, "scene_01", since_gametime=3600)
+
+    assert len(result) == 1
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "gametime" in cypher
+    assert "WHERE" in cypher
+
+
+@pytest.mark.anyio
+async def test_scene_events_returns_chat_messages(mock_client):
+    """scene_events correctly deserializes ChatMessage subtypes."""
+    node = _make_node_mock(
+        ["Entity", "Event", "ChatMessage"],
+        {
+            "id": "msg_1", "name": "msg", "body": "desc", "scene_id": "scene_01",
+            "gametime": 200, "walltime": "2024-01-01T00:03:20",
+            "character_id": "char_1", "message": "Hello!",
+        },
+    )
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    result = await scene_events(mock_client, "scene_01")
+
+    assert len(result) == 1
+    assert isinstance(result[0], ChatMessage)
+
+
+@pytest.mark.anyio
+async def test_scene_events_empty(mock_client):
+    """scene_events returns empty list when scene has no events."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    result = await scene_events(mock_client, "scene_01")
+
+    assert result == []
+
+
+@pytest.mark.anyio
+async def test_scene_events_query_error(mock_client):
+    """scene_events raises QueryError on failure."""
+    mock_client.graph.query.side_effect = Exception("network timeout")
+
+    with pytest.raises(QueryError):
+        await scene_events(mock_client, "scene_01")
+
+
+# --- entity_graph ---
+
+
+@pytest.mark.anyio
+async def test_entity_graph_depth_1(mock_client):
+    """entity_graph at depth=1 returns entity and directly connected entities."""
+    center_node = _make_node_mock(
+        ["Entity", "Character"],
+        {"id": "char_alice", "name": "Alice", "body": "A warrior", "unseen": False, "inventory": []},
+    )
+    neighbor_node = _make_node_mock(
+        ["Entity", "Location"],
+        {"id": "loc_1", "name": "Tavern", "body": "A cozy tavern"},
+    )
+    mock_client.graph.query.return_value = MagicMock(
+        result_set=[[center_node, [neighbor_node]]]
+    )
+
+    result = await entity_graph(mock_client, "char_alice", depth=1)
+
+    assert isinstance(result["entity"], Character)
+    assert result["entity"].id == "char_alice"
+    assert len(result["related"]) == 1
+    assert isinstance(result["related"][0], Location)
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "1..1" in cypher or "*1" in cypher
+
+
+@pytest.mark.anyio
+async def test_entity_graph_depth_2(mock_client):
+    """entity_graph at depth=2 returns two levels of connections."""
+    center_node = _make_node_mock(
+        ["Entity", "Character"],
+        {"id": "char_alice", "name": "Alice", "body": "A warrior", "unseen": False, "inventory": []},
+    )
+    neighbor1 = _make_node_mock(
+        ["Entity", "Location"],
+        {"id": "loc_1", "name": "Tavern", "body": "A cozy tavern"},
+    )
+    neighbor2 = _make_node_mock(
+        ["Entity", "Location"],
+        {"id": "loc_2", "name": "Forest", "body": "A dark forest"},
+    )
+    mock_client.graph.query.return_value = MagicMock(
+        result_set=[[center_node, [neighbor1, neighbor2]]]
+    )
+
+    result = await entity_graph(mock_client, "char_alice", depth=2)
+
+    assert isinstance(result["entity"], Character)
+    assert len(result["related"]) == 2
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "1..2" in cypher or "*2" in cypher
+
+
+@pytest.mark.anyio
+async def test_entity_graph_not_found(mock_client):
+    """entity_graph returns None entity when center not found."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    result = await entity_graph(mock_client, "nonexistent")
+
+    assert result["entity"] is None
+    assert result["related"] == []
+
+
+@pytest.mark.anyio
+async def test_entity_graph_no_neighbors(mock_client):
+    """entity_graph returns entity with empty related when no neighbors."""
+    center_node = _make_node_mock(
+        ["Entity", "Character"],
+        {"id": "char_alice", "name": "Alice", "body": "A warrior", "unseen": False, "inventory": []},
+    )
+    mock_client.graph.query.return_value = MagicMock(
+        result_set=[[center_node, []]]
+    )
+
+    result = await entity_graph(mock_client, "char_alice")
+
+    assert isinstance(result["entity"], Character)
+    assert result["related"] == []
+
+
+@pytest.mark.anyio
+async def test_entity_graph_query_error(mock_client):
+    """entity_graph raises QueryError on failure."""
+    mock_client.graph.query.side_effect = Exception("network timeout")
+
+    with pytest.raises(QueryError):
+        await entity_graph(mock_client, "char_alice")
