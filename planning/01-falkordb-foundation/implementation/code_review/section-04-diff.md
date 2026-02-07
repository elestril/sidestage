diff --git a/planning/01-falkordb-foundation/implementation/deep_implement_config.json b/planning/01-falkordb-foundation/implementation/deep_implement_config.json
index 7829d98..8fb9cf9 100644
--- a/planning/01-falkordb-foundation/implementation/deep_implement_config.json
+++ b/planning/01-falkordb-foundation/implementation/deep_implement_config.json
@@ -22,6 +22,10 @@
     "section-02-schema": {
       "status": "complete",
       "commit_hash": "7330302"
+    },
+    "section-03-entities": {
+      "status": "complete",
+      "commit_hash": "66f4564"
     }
   },
   "pre_commit": {
diff --git a/src/sidestage/graph/relationships.py b/src/sidestage/graph/relationships.py
new file mode 100644
index 0000000..9bf573f
--- /dev/null
+++ b/src/sidestage/graph/relationships.py
@@ -0,0 +1,249 @@
+"""Relationship (edge) operations for FalkorDB graph.
+
+Provides async functions for creating, removing, and querying
+relationships between entity nodes.
+"""
+
+from __future__ import annotations
+
+import logging
+from typing import Any, TYPE_CHECKING
+
+from sidestage.graph.entities import node_to_entity
+from sidestage.graph.errors import EntityNotFoundError, QueryError
+from sidestage.schemas import Entity
+
+if TYPE_CHECKING:
+    from sidestage.graph.client import GraphClient
+
+logger = logging.getLogger(__name__)
+
+VALID_REL_TYPES = frozenset({
+    "LOCATED_IN",
+    "CONNECTS_TO",
+    "AT_LOCATION",
+    "HAS_EVENT",
+    "INVOLVES",
+    "PARTICIPATES_IN",
+})
+
+VALID_DIRECTIONS = frozenset({"outgoing", "incoming", "both"})
+
+
+def _validate_rel_type(rel_type: str) -> None:
+    """Validate rel_type against allowed set to prevent Cypher injection."""
+    if rel_type not in VALID_REL_TYPES:
+        raise ValueError(
+            f"Invalid relationship type: {rel_type!r}. "
+            f"Must be one of {sorted(VALID_REL_TYPES)}"
+        )
+
+
+def _validate_direction(direction: str) -> None:
+    """Validate direction parameter."""
+    if direction not in VALID_DIRECTIONS:
+        raise ValueError(
+            f"Invalid direction: {direction!r}. "
+            f"Must be one of {sorted(VALID_DIRECTIONS)}"
+        )
+
+
+async def link(
+    client: GraphClient,
+    source_id: str,
+    rel_type: str,
+    target_id: str,
+    properties: dict | None = None,
+) -> None:
+    """Create a relationship between two entities.
+
+    Matches source and target by :Entity id property, creates a typed edge.
+    Optional properties dict for edge metadata (stored on the edge).
+
+    Raises EntityNotFoundError if source or target entity does not exist.
+    Raises QueryError if the Cypher query fails.
+    """
+    _validate_rel_type(rel_type)
+
+    logger.debug("Linking %s -[%s]-> %s", source_id, rel_type, target_id)
+
+    # Check both entities exist
+    check_cypher = (
+        "OPTIONAL MATCH (s:Entity {id: $source_id}) "
+        "OPTIONAL MATCH (t:Entity {id: $target_id}) "
+        "RETURN s.id, t.id"
+    )
+    try:
+        result = await client.graph.query(
+            check_cypher, params={"source_id": source_id, "target_id": target_id}
+        )
+    except Exception as exc:
+        raise QueryError(f"Failed to check entities for link: {exc}") from exc
+
+    if not result.result_set:
+        raise EntityNotFoundError(
+            f"Entity '{source_id}' or '{target_id}' not found"
+        )
+
+    row = result.result_set[0]
+    if row[0] is None:
+        raise EntityNotFoundError(f"Source entity '{source_id}' not found")
+    if row[1] is None:
+        raise EntityNotFoundError(f"Target entity '{target_id}' not found")
+
+    # Create the edge
+    if properties:
+        prop_assignments = ", ".join(f"{k}: ${k}" for k in properties)
+        create_cypher = (
+            f"MATCH (s:Entity {{id: $source_id}}) "
+            f"MATCH (t:Entity {{id: $target_id}}) "
+            f"CREATE (s)-[:{rel_type} {{{prop_assignments}}}]->(t)"
+        )
+        params: dict[str, Any] = {
+            "source_id": source_id,
+            "target_id": target_id,
+            **properties,
+        }
+    else:
+        create_cypher = (
+            f"MATCH (s:Entity {{id: $source_id}}) "
+            f"MATCH (t:Entity {{id: $target_id}}) "
+            f"CREATE (s)-[:{rel_type}]->(t)"
+        )
+        params = {"source_id": source_id, "target_id": target_id}
+
+    try:
+        await client.graph.query(create_cypher, params=params)
+    except Exception as exc:
+        raise QueryError(
+            f"Failed to create {rel_type} from '{source_id}' to '{target_id}': {exc}"
+        ) from exc
+
+    logger.debug("Linked %s -[%s]-> %s", source_id, rel_type, target_id)
+
+
+async def unlink(
+    client: GraphClient,
+    source_id: str,
+    rel_type: str,
+    target_id: str,
+) -> None:
+    """Remove a relationship between two entities.
+
+    Idempotent: does not raise if the edge does not exist.
+    """
+    _validate_rel_type(rel_type)
+
+    logger.debug("Unlinking %s -[%s]-> %s", source_id, rel_type, target_id)
+
+    cypher = (
+        f"MATCH (s:Entity {{id: $source_id}})-[r:{rel_type}]->(t:Entity {{id: $target_id}}) "
+        "DELETE r"
+    )
+    try:
+        await client.graph.query(
+            cypher, params={"source_id": source_id, "target_id": target_id}
+        )
+    except Exception as exc:
+        raise QueryError(
+            f"Failed to unlink {rel_type} from '{source_id}' to '{target_id}': {exc}"
+        ) from exc
+
+    logger.debug("Unlinked %s -[%s]-> %s", source_id, rel_type, target_id)
+
+
+async def get_related(
+    client: GraphClient,
+    entity_id: str,
+    rel_type: str,
+    direction: str = "outgoing",
+) -> list[Entity]:
+    """Get entities related via a specific relationship type.
+
+    Args:
+        client: The graph client.
+        entity_id: ID of the source entity.
+        rel_type: The relationship type to traverse.
+        direction: "outgoing", "incoming", or "both".
+
+    Returns:
+        List of deserialized Entity (or subclass) objects.
+    """
+    _validate_rel_type(rel_type)
+    _validate_direction(direction)
+
+    if direction == "outgoing":
+        cypher = f"MATCH (s:Entity {{id: $id}})-[:{rel_type}]->(t) RETURN t"
+    elif direction == "incoming":
+        cypher = f"MATCH (s:Entity {{id: $id}})<-[:{rel_type}]-(t) RETURN t"
+    else:  # both
+        cypher = f"MATCH (s:Entity {{id: $id}})-[:{rel_type}]-(t) RETURN t"
+
+    logger.debug("get_related id=%s rel=%s dir=%s", entity_id, rel_type, direction)
+
+    try:
+        result = await client.graph.query(cypher, params={"id": entity_id})
+    except Exception as exc:
+        raise QueryError(
+            f"Failed to get related entities for '{entity_id}': {exc}"
+        ) from exc
+
+    entities = [node_to_entity(row[0].labels, row[0].properties) for row in result.result_set]
+    logger.debug("get_related returned %d entities", len(entities))
+    return entities
+
+
+async def get_relationships(
+    client: GraphClient,
+    entity_id: str,
+) -> list[dict]:
+    """Get all relationships for an entity.
+
+    Returns list of dicts, each containing:
+        - rel_type: str
+        - direction: str ("outgoing" or "incoming")
+        - target_id: str
+        - target_name: str
+        - properties: dict
+    """
+    logger.debug("get_relationships id=%s", entity_id)
+
+    outgoing_cypher = (
+        "MATCH (s:Entity {id: $id})-[r]->(t:Entity) "
+        "RETURN type(r) AS rel_type, t.id AS target_id, t.name AS target_name, properties(r) AS props"
+    )
+    incoming_cypher = (
+        "MATCH (s:Entity {id: $id})<-[r]-(t:Entity) "
+        "RETURN type(r) AS rel_type, t.id AS target_id, t.name AS target_name, properties(r) AS props"
+    )
+
+    try:
+        outgoing_result = await client.graph.query(outgoing_cypher, params={"id": entity_id})
+        incoming_result = await client.graph.query(incoming_cypher, params={"id": entity_id})
+    except Exception as exc:
+        raise QueryError(
+            f"Failed to get relationships for '{entity_id}': {exc}"
+        ) from exc
+
+    relationships: list[dict] = []
+
+    for row in outgoing_result.result_set:
+        relationships.append({
+            "rel_type": row[0],
+            "direction": "outgoing",
+            "target_id": row[1],
+            "target_name": row[2],
+            "properties": row[3] if row[3] else {},
+        })
+
+    for row in incoming_result.result_set:
+        relationships.append({
+            "rel_type": row[0],
+            "direction": "incoming",
+            "target_id": row[1],
+            "target_name": row[2],
+            "properties": row[3] if row[3] else {},
+        })
+
+    logger.debug("get_relationships returned %d relationships", len(relationships))
+    return relationships
diff --git a/tests/unit/test_graph_relationships.py b/tests/unit/test_graph_relationships.py
new file mode 100644
index 0000000..61246b1
--- /dev/null
+++ b/tests/unit/test_graph_relationships.py
@@ -0,0 +1,289 @@
+"""Unit tests for graph relationship operations."""
+import pytest
+from unittest.mock import AsyncMock, MagicMock
+
+from sidestage.graph.errors import EntityNotFoundError
+from sidestage.graph.relationships import (
+    VALID_REL_TYPES,
+    link,
+    unlink,
+    get_related,
+    get_relationships,
+)
+from sidestage.schemas import Character, Location
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
+# --- Link ---
+
+
+@pytest.mark.anyio
+async def test_link_creates_typed_edge(mock_client):
+    """link creates typed edge between two entities."""
+    # First call: OPTIONAL MATCH to check existence - both nodes found
+    mock_client.graph.query.side_effect = [
+        MagicMock(result_set=[["char_1", "loc_1"]]),  # existence check
+        MagicMock(result_set=[]),  # CREATE edge
+    ]
+
+    await link(mock_client, "char_1", "LOCATED_IN", "loc_1")
+
+    assert mock_client.graph.query.call_count == 2
+    create_cypher = mock_client.graph.query.call_args_list[1][0][0]
+    assert "LOCATED_IN" in create_cypher
+    assert "CREATE" in create_cypher
+
+
+@pytest.mark.anyio
+async def test_link_with_properties(mock_client):
+    """link with properties stores properties on edge."""
+    mock_client.graph.query.side_effect = [
+        MagicMock(result_set=[["char_1", "loc_1"]]),  # existence check
+        MagicMock(result_set=[]),  # CREATE edge
+    ]
+
+    await link(mock_client, "char_1", "LOCATED_IN", "loc_1", properties={"since": "2024-01-01"})
+
+    create_cypher = mock_client.graph.query.call_args_list[1][0][0]
+    assert "LOCATED_IN" in create_cypher
+    assert "since" in create_cypher
+
+
+@pytest.mark.anyio
+async def test_link_raises_entity_not_found_for_source(mock_client):
+    """link raises EntityNotFoundError if source doesn't exist."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[[None, "loc_1"]])
+
+    with pytest.raises(EntityNotFoundError, match="char_1"):
+        await link(mock_client, "char_1", "LOCATED_IN", "loc_1")
+
+
+@pytest.mark.anyio
+async def test_link_raises_entity_not_found_for_target(mock_client):
+    """link raises EntityNotFoundError if target doesn't exist."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[[None, None]])
+
+    with pytest.raises(EntityNotFoundError):
+        await link(mock_client, "char_1", "LOCATED_IN", "loc_nonexistent")
+
+
+@pytest.mark.anyio
+async def test_link_raises_entity_not_found_no_results(mock_client):
+    """link raises EntityNotFoundError if OPTIONAL MATCH returns empty result_set."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    with pytest.raises(EntityNotFoundError):
+        await link(mock_client, "char_1", "LOCATED_IN", "loc_1")
+
+
+@pytest.mark.anyio
+async def test_link_invalid_rel_type_raises_value_error(mock_client):
+    """link raises ValueError for invalid relationship type."""
+    with pytest.raises(ValueError, match="Invalid relationship type"):
+        await link(mock_client, "char_1", "INVALID_TYPE", "loc_1")
+
+
+# --- Unlink ---
+
+
+@pytest.mark.anyio
+async def test_unlink_removes_edge(mock_client):
+    """unlink removes edge between two entities."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    await unlink(mock_client, "char_1", "LOCATED_IN", "loc_1")
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "MATCH" in cypher
+    assert "DELETE" in cypher
+    assert "LOCATED_IN" in cypher
+
+
+@pytest.mark.anyio
+async def test_unlink_idempotent(mock_client):
+    """unlink is idempotent (no error if edge doesn't exist)."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    # Should not raise
+    await unlink(mock_client, "char_1", "LOCATED_IN", "loc_1")
+
+
+@pytest.mark.anyio
+async def test_unlink_invalid_rel_type_raises_value_error(mock_client):
+    """unlink raises ValueError for invalid relationship type."""
+    with pytest.raises(ValueError, match="Invalid relationship type"):
+        await unlink(mock_client, "char_1", "BOGUS", "loc_1")
+
+
+# --- Get Related ---
+
+
+@pytest.mark.anyio
+async def test_get_related_outgoing(mock_client):
+    """get_related returns outgoing related entities."""
+    node = _make_node_mock(
+        ["Entity", "Location"],
+        {"id": "loc_1", "name": "Tavern", "body": "A cozy tavern"},
+    )
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    result = await get_related(mock_client, "char_1", "LOCATED_IN", direction="outgoing")
+
+    assert len(result) == 1
+    assert isinstance(result[0], Location)
+    assert result[0].id == "loc_1"
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "]->" in cypher
+
+
+@pytest.mark.anyio
+async def test_get_related_incoming(mock_client):
+    """get_related returns incoming related entities."""
+    node = _make_node_mock(
+        ["Entity", "Character"],
+        {"id": "char_1", "name": "Alice", "body": "A warrior", "unseen": False, "inventory": []},
+    )
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    result = await get_related(mock_client, "loc_1", "LOCATED_IN", direction="incoming")
+
+    assert len(result) == 1
+    assert isinstance(result[0], Character)
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "<-[" in cypher
+
+
+@pytest.mark.anyio
+async def test_get_related_both_directions(mock_client):
+    """get_related with direction='both' returns all related."""
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
+    result = await get_related(mock_client, "loc_1", "CONNECTS_TO", direction="both")
+
+    assert len(result) == 2
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    # "both" uses undirected pattern: no -> or <-
+    assert "]-(" in cypher or "]->" not in cypher
+
+
+@pytest.mark.anyio
+async def test_get_related_empty(mock_client):
+    """get_related returns empty list when no relationships."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    result = await get_related(mock_client, "char_1", "LOCATED_IN")
+
+    assert result == []
+
+
+@pytest.mark.anyio
+async def test_get_related_connects_to_bidirectional(mock_client):
+    """get_related with CONNECTS_TO and direction='both' finds bidirectional connections."""
+    node1 = _make_node_mock(
+        ["Entity", "Location"],
+        {"id": "loc_2", "name": "Forest", "body": "A dark forest"},
+    )
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node1]])
+
+    result = await get_related(mock_client, "loc_1", "CONNECTS_TO", direction="both")
+
+    assert len(result) == 1
+    assert isinstance(result[0], Location)
+
+
+@pytest.mark.anyio
+async def test_get_related_invalid_direction_raises(mock_client):
+    """get_related raises ValueError for invalid direction."""
+    with pytest.raises(ValueError, match="Invalid direction"):
+        await get_related(mock_client, "char_1", "LOCATED_IN", direction="sideways")
+
+
+@pytest.mark.anyio
+async def test_get_related_invalid_rel_type_raises(mock_client):
+    """get_related raises ValueError for invalid relationship type."""
+    with pytest.raises(ValueError, match="Invalid relationship type"):
+        await get_related(mock_client, "char_1", "BOGUS")
+
+
+# --- Get Relationships ---
+
+
+@pytest.mark.anyio
+async def test_get_relationships_returns_all(mock_client):
+    """get_relationships returns all relationships for an entity."""
+    # Outgoing query result
+    outgoing_result = MagicMock(result_set=[
+        ["LOCATED_IN", "loc_1", "Tavern", {}],
+    ])
+    # Incoming query result
+    incoming_result = MagicMock(result_set=[
+        ["PARTICIPATES_IN", "scene_1", "Battle", {}],
+    ])
+    mock_client.graph.query.side_effect = [outgoing_result, incoming_result]
+
+    result = await get_relationships(mock_client, "char_1")
+
+    assert len(result) == 2
+
+
+@pytest.mark.anyio
+async def test_get_relationships_includes_expected_keys(mock_client):
+    """get_relationships includes rel_type, direction, target info."""
+    outgoing_result = MagicMock(result_set=[
+        ["LOCATED_IN", "loc_1", "Tavern", {"since": "2024-01-01"}],
+    ])
+    incoming_result = MagicMock(result_set=[])
+    mock_client.graph.query.side_effect = [outgoing_result, incoming_result]
+
+    result = await get_relationships(mock_client, "char_1")
+
+    assert len(result) == 1
+    rel = result[0]
+    assert rel["rel_type"] == "LOCATED_IN"
+    assert rel["direction"] == "outgoing"
+    assert rel["target_id"] == "loc_1"
+    assert rel["target_name"] == "Tavern"
+    assert rel["properties"] == {"since": "2024-01-01"}
+
+
+@pytest.mark.anyio
+async def test_get_relationships_empty(mock_client):
+    """get_relationships returns empty list for entity with no relationships."""
+    mock_client.graph.query.side_effect = [
+        MagicMock(result_set=[]),
+        MagicMock(result_set=[]),
+    ]
+
+    result = await get_relationships(mock_client, "char_1")
+
+    assert result == []
