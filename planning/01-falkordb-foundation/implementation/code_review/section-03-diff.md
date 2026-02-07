diff --git a/src/sidestage/graph/entities.py b/src/sidestage/graph/entities.py
new file mode 100644
index 0000000..7f033d7
--- /dev/null
+++ b/src/sidestage/graph/entities.py
@@ -0,0 +1,210 @@
+"""Entity CRUD operations and serialization logic for FalkorDB graph nodes.
+
+Provides async functions for creating, retrieving, updating, deleting,
+listing, and querying entity nodes. Maps between Pydantic entity models
+and FalkorDB graph node properties.
+"""
+
+from __future__ import annotations
+
+import logging
+from typing import Any, TYPE_CHECKING
+
+from sidestage.graph.errors import DuplicateEntityError, EntityNotFoundError, QueryError
+from sidestage.schemas import (
+    Entity,
+    Character,
+    ChatMessage,
+    Event,
+    Item,
+    Location,
+    Scene,
+)
+
+if TYPE_CHECKING:
+    from sidestage.graph.client import GraphClient
+
+logger = logging.getLogger(__name__)
+
+# --- Label/Model Registries ---
+
+# Ordered most-specific first so deserialization picks the right model.
+LABEL_TO_MODEL: dict[str, type[Entity]] = {
+    "ChatMessage": ChatMessage,
+    "Character": Character,
+    "Location": Location,
+    "Item": Item,
+    "Scene": Scene,
+    "Event": Event,
+}
+
+MODEL_TO_LABELS: dict[type[Entity], list[str]] = {
+    Character: ["Entity", "Character"],
+    Location: ["Entity", "Location"],
+    Item: ["Entity", "Item"],
+    Scene: ["Entity", "Scene"],
+    Event: ["Entity", "Event"],
+    ChatMessage: ["Entity", "Event", "ChatMessage"],
+}
+
+# Fields that should NOT be stored as graph node properties.
+EXCLUDED_FIELDS: dict[type[Entity], set[str]] = {
+    Location: {"connected_locations"},
+    Scene: {"messages"},
+    ChatMessage: {"widget"},
+}
+
+
+# --- Serialization Helpers ---
+
+
+def entity_to_labels(entity: Entity) -> list[str]:
+    """Return the FalkorDB labels for an entity instance."""
+    return MODEL_TO_LABELS.get(type(entity), ["Entity"])
+
+
+def entity_to_properties(entity: Entity) -> dict[str, Any]:
+    """Convert a Pydantic entity to a dict of graph node properties.
+
+    Excludes fields listed in EXCLUDED_FIELDS for the entity type,
+    and omits None values.
+    """
+    excluded = EXCLUDED_FIELDS.get(type(entity), set())
+    props = {}
+    for key, value in entity.model_dump().items():
+        if key in excluded:
+            continue
+        if value is None:
+            continue
+        props[key] = value
+    return props
+
+
+def node_to_entity(labels: list[str], properties: dict[str, Any]) -> Entity:
+    """Reconstruct a Pydantic entity from graph node labels and properties.
+
+    Iterates LABEL_TO_MODEL in specificity order (most-specific first)
+    and picks the first matching label.
+
+    Raises QueryError if no matching label is found.
+    """
+    label_set = set(labels)
+    for label, model_cls in LABEL_TO_MODEL.items():
+        if label in label_set:
+            return model_cls(**properties)
+    raise QueryError(f"Cannot deserialize node with labels {labels}: no matching model")
+
+
+# --- CRUD Functions ---
+
+
+async def create_entity(client: GraphClient, entity: Entity) -> Entity:
+    """Create a new entity node in the graph.
+
+    Raises DuplicateEntityError on unique constraint violation.
+    """
+    labels = entity_to_labels(entity)
+    props = entity_to_properties(entity)
+
+    label_str = ":".join(labels)
+    prop_assignments = ", ".join(f"{k}: ${k}" for k in props)
+    cypher = f"CREATE (n:{label_str} {{{prop_assignments}}}) RETURN n"
+
+    logger.info("Creating %s entity id=%s", labels[-1], entity.id)
+    logger.debug("Cypher: %s", cypher)
+
+    try:
+        await client.graph.query(cypher, params=props)
+    except Exception as exc:
+        raise DuplicateEntityError(
+            f"Entity with id '{entity.id}' already exists: {exc}"
+        ) from exc
+
+    return entity
+
+
+async def get_entity(client: GraphClient, entity_id: str) -> Entity | None:
+    """Retrieve an entity by ID, or None if not found."""
+    cypher = "MATCH (n:Entity {id: $id}) RETURN n"
+
+    logger.debug("Getting entity id=%s", entity_id)
+
+    result = await client.graph.query(cypher, params={"id": entity_id})
+
+    if not result.result_set:
+        return None
+
+    node = result.result_set[0][0]
+    return node_to_entity(node.labels, node.properties)
+
+
+async def update_entity(
+    client: GraphClient, entity_id: str, updates: dict[str, Any]
+) -> Entity:
+    """Update specified properties on an entity node.
+
+    Raises EntityNotFoundError if the entity does not exist.
+    Returns the updated entity.
+    """
+    set_clauses = ", ".join(f"n.{k} = ${k}" for k in updates)
+    cypher = f"MATCH (n:Entity {{id: $id}}) SET {set_clauses} RETURN n"
+    params = {"id": entity_id, **updates}
+
+    logger.info("Updating entity id=%s fields=%s", entity_id, list(updates.keys()))
+    logger.debug("Cypher: %s", cypher)
+
+    result = await client.graph.query(cypher, params=params)
+
+    if not result.result_set:
+        raise EntityNotFoundError(f"Entity with id '{entity_id}' not found")
+
+    node = result.result_set[0][0]
+    return node_to_entity(node.labels, node.properties)
+
+
+async def delete_entity(client: GraphClient, entity_id: str) -> None:
+    """Delete an entity and all its relationships.
+
+    Succeeds silently if the entity does not exist.
+    """
+    cypher = "MATCH (n:Entity {id: $id}) DETACH DELETE n"
+
+    logger.info("Deleting entity id=%s", entity_id)
+
+    await client.graph.query(cypher, params={"id": entity_id})
+
+
+async def list_entities(
+    client: GraphClient, entity_type: str | None = None
+) -> list[Entity]:
+    """List all entities, optionally filtered by type label.
+
+    The entity_type string is validated against known labels.
+    """
+    if entity_type is not None:
+        if entity_type not in LABEL_TO_MODEL:
+            raise QueryError(f"Unknown entity type: {entity_type}")
+        cypher = f"MATCH (n:{entity_type}) RETURN n"
+    else:
+        cypher = "MATCH (n:Entity) RETURN n"
+
+    logger.debug("Listing entities type=%s", entity_type)
+
+    result = await client.graph.query(cypher)
+
+    return [node_to_entity(row[0].labels, row[0].properties) for row in result.result_set]
+
+
+async def find_entities(client: GraphClient, **filters: Any) -> list[Entity]:
+    """Find entities matching all given property filters."""
+    if not filters:
+        return await list_entities(client)
+
+    conditions = " AND ".join(f"n.{k} = ${k}" for k in filters)
+    cypher = f"MATCH (n:Entity) WHERE {conditions} RETURN n"
+
+    logger.debug("Finding entities filters=%s", filters)
+
+    result = await client.graph.query(cypher, params=filters)
+
+    return [node_to_entity(row[0].labels, row[0].properties) for row in result.result_set]
diff --git a/tests/unit/test_graph_entities.py b/tests/unit/test_graph_entities.py
new file mode 100644
index 0000000..a0776ea
--- /dev/null
+++ b/tests/unit/test_graph_entities.py
@@ -0,0 +1,317 @@
+"""Unit tests for graph entity CRUD operations."""
+import pytest
+from unittest.mock import AsyncMock, MagicMock, patch
+
+from sidestage.schemas import Character, Location, Item, Scene, Event, ChatMessage
+from sidestage.graph.errors import DuplicateEntityError, EntityNotFoundError
+from sidestage.graph.entities import (
+    create_entity,
+    get_entity,
+    update_entity,
+    delete_entity,
+    list_entities,
+    find_entities,
+)
+
+
+# --- Fixtures ---
+
+
+@pytest.fixture
+def mock_client():
+    """Creates a MagicMock GraphClient with graph.query as AsyncMock."""
+    client = MagicMock()
+    client.graph = MagicMock()
+    client.graph.query = AsyncMock()
+    return client
+
+
+@pytest.fixture
+def sample_character():
+    return Character(
+        id="char_1", name="Alice", body="A brave warrior",
+        location_id="loc_1", inventory=["item_sword"],
+    )
+
+
+@pytest.fixture
+def sample_location():
+    return Location(
+        id="loc_1", name="Tavern", body="A cozy tavern",
+        connected_locations=["loc_2"],
+    )
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
+# --- Create ---
+
+
+@pytest.mark.anyio
+async def test_create_entity_character_cypher(mock_client, sample_character):
+    """create_entity with Character generates correct Cypher with :Entity:Character labels."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[[]])
+
+    await create_entity(mock_client, sample_character)
+
+    call_args = mock_client.graph.query.call_args
+    cypher = call_args[0][0]
+    assert ":Entity:Character" in cypher
+    assert "CREATE" in cypher
+
+
+@pytest.mark.anyio
+async def test_create_entity_location_excludes_connected_locations(mock_client, sample_location):
+    """create_entity with Location does not include connected_locations in Cypher properties."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[[]])
+
+    await create_entity(mock_client, sample_location)
+
+    call_args = mock_client.graph.query.call_args
+    params = call_args[1].get("params", call_args[0][1] if len(call_args[0]) > 1 else {})
+    assert "connected_locations" not in params
+
+
+@pytest.mark.anyio
+async def test_create_entity_chat_message_labels(mock_client):
+    """create_entity with ChatMessage generates Cypher with :Entity:Event:ChatMessage labels."""
+    msg = ChatMessage(
+        id="m1", name="msg", body="desc", scene_id="s1",
+        gametime=100, walltime="2024-01-01T00:00:00",
+        character_id="c1", message="Hello",
+    )
+    mock_client.graph.query.return_value = MagicMock(result_set=[[]])
+
+    await create_entity(mock_client, msg)
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert ":Entity:Event:ChatMessage" in cypher
+
+
+@pytest.mark.anyio
+async def test_create_entity_raises_duplicate_on_constraint_violation(mock_client, sample_character):
+    """create_entity raises DuplicateEntityError on unique constraint violation."""
+    mock_client.graph.query.side_effect = Exception("unique constraint")
+
+    with pytest.raises(DuplicateEntityError):
+        await create_entity(mock_client, sample_character)
+
+
+@pytest.mark.anyio
+async def test_create_entity_returns_entity(mock_client, sample_character):
+    """create_entity returns the created entity."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[[]])
+
+    result = await create_entity(mock_client, sample_character)
+
+    assert result is sample_character
+
+
+# --- Get ---
+
+
+@pytest.mark.anyio
+async def test_get_entity_returns_correct_entity(mock_client):
+    """get_entity returns correct entity when node is found."""
+    node = _make_node_mock(
+        ["Entity", "Character"],
+        {"id": "c1", "name": "Alice", "body": "desc", "unseen": False, "inventory": []},
+    )
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    entity = await get_entity(mock_client, "c1")
+
+    assert isinstance(entity, Character)
+    assert entity.id == "c1"
+    assert entity.name == "Alice"
+
+
+@pytest.mark.anyio
+async def test_get_entity_returns_none_when_not_found(mock_client):
+    """get_entity returns None when result_set is empty."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    result = await get_entity(mock_client, "nonexistent")
+
+    assert result is None
+
+
+@pytest.mark.anyio
+async def test_get_entity_chat_message_reconstructs_correctly(mock_client):
+    """get_entity for ChatMessage node reconstructs as ChatMessage, not Event."""
+    node = _make_node_mock(
+        ["Entity", "Event", "ChatMessage"],
+        {
+            "id": "m1", "name": "msg", "body": "desc", "scene_id": "s1",
+            "gametime": 100, "walltime": "2024-01-01T00:00:00",
+            "character_id": "c1", "message": "Hello",
+        },
+    )
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    entity = await get_entity(mock_client, "m1")
+
+    assert isinstance(entity, ChatMessage)
+
+
+@pytest.mark.anyio
+async def test_get_entity_cypher(mock_client):
+    """get_entity generates correct MATCH Cypher."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    await get_entity(mock_client, "c1")
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "MATCH" in cypher
+    assert ":Entity" in cypher
+    assert "RETURN" in cypher
+
+
+# --- Update ---
+
+
+@pytest.mark.anyio
+async def test_update_entity_sets_specified_properties(mock_client):
+    """update_entity generates Cypher SET for specified properties only."""
+    node = _make_node_mock(
+        ["Entity", "Character"],
+        {"id": "c1", "name": "Bob", "body": "desc", "unseen": False, "inventory": []},
+    )
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    await update_entity(mock_client, "c1", {"name": "Bob"})
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "SET" in cypher
+    assert "n.name" in cypher
+
+
+@pytest.mark.anyio
+async def test_update_entity_raises_not_found(mock_client):
+    """update_entity raises EntityNotFoundError when node not found."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    with pytest.raises(EntityNotFoundError):
+        await update_entity(mock_client, "nonexistent", {"name": "Bob"})
+
+
+@pytest.mark.anyio
+async def test_update_entity_returns_updated_entity(mock_client):
+    """update_entity returns the updated entity."""
+    node = _make_node_mock(
+        ["Entity", "Character"],
+        {"id": "c1", "name": "Bob", "body": "desc", "unseen": False, "inventory": []},
+    )
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    result = await update_entity(mock_client, "c1", {"name": "Bob"})
+
+    assert isinstance(result, Character)
+    assert result.name == "Bob"
+
+
+# --- Delete ---
+
+
+@pytest.mark.anyio
+async def test_delete_entity_uses_detach_delete(mock_client):
+    """delete_entity generates Cypher MATCH + DETACH DELETE."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    await delete_entity(mock_client, "c1")
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "DETACH DELETE" in cypher
+
+
+@pytest.mark.anyio
+async def test_delete_entity_nonexistent_succeeds_silently(mock_client):
+    """delete_entity for non-existent id succeeds silently."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    # Should not raise
+    await delete_entity(mock_client, "nonexistent")
+
+
+# --- List ---
+
+
+@pytest.mark.anyio
+async def test_list_entities_no_filter(mock_client):
+    """list_entities without type filter queries MATCH (n:Entity) RETURN n."""
+    node1 = _make_node_mock(["Entity", "Character"], {"id": "c1", "name": "Alice", "body": "desc", "unseen": False, "inventory": []})
+    node2 = _make_node_mock(["Entity", "Location"], {"id": "l1", "name": "Tavern", "body": "desc"})
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node1], [node2]])
+
+    result = await list_entities(mock_client)
+
+    assert len(result) == 2
+    assert isinstance(result[0], Character)
+    assert isinstance(result[1], Location)
+
+
+@pytest.mark.anyio
+async def test_list_entities_with_type_filter(mock_client):
+    """list_entities with type filter queries MATCH (n:Character) RETURN n."""
+    node = _make_node_mock(["Entity", "Character"], {"id": "c1", "name": "Alice", "body": "desc", "unseen": False, "inventory": []})
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    result = await list_entities(mock_client, entity_type="Character")
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert ":Character" in cypher
+    assert len(result) == 1
+
+
+@pytest.mark.anyio
+async def test_list_entities_returns_empty_list(mock_client):
+    """list_entities returns empty list when result_set is empty."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    result = await list_entities(mock_client)
+
+    assert result == []
+
+
+# --- Find ---
+
+
+@pytest.mark.anyio
+async def test_find_entities_single_filter(mock_client):
+    """find_entities with name='Alice' generates WHERE clause."""
+    node = _make_node_mock(["Entity", "Character"], {"id": "c1", "name": "Alice", "body": "desc", "unseen": False, "inventory": []})
+    mock_client.graph.query.return_value = MagicMock(result_set=[[node]])
+
+    result = await find_entities(mock_client, name="Alice")
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "WHERE" in cypher
+    assert "n.name" in cypher
+    assert len(result) == 1
+
+
+@pytest.mark.anyio
+async def test_find_entities_multiple_filters(mock_client):
+    """find_entities with multiple filters generates AND conditions."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    await find_entities(mock_client, name="Alice", unseen=True)
+
+    cypher = mock_client.graph.query.call_args[0][0]
+    assert "AND" in cypher
+
+
+@pytest.mark.anyio
+async def test_find_entities_returns_empty_list(mock_client):
+    """find_entities returns empty list when no matches."""
+    mock_client.graph.query.return_value = MagicMock(result_set=[])
+
+    result = await find_entities(mock_client, name="Nobody")
+
+    assert result == []
diff --git a/tests/unit/test_graph_serialization.py b/tests/unit/test_graph_serialization.py
new file mode 100644
index 0000000..1501ae3
--- /dev/null
+++ b/tests/unit/test_graph_serialization.py
@@ -0,0 +1,191 @@
+"""Unit tests for entity serialization to/from graph node properties."""
+import pytest
+from unittest.mock import MagicMock
+
+from sidestage.schemas import Character, Location, Item, Scene, Event, ChatMessage
+from sidestage.graph.entities import (
+    LABEL_TO_MODEL,
+    MODEL_TO_LABELS,
+    EXCLUDED_FIELDS,
+    entity_to_labels,
+    entity_to_properties,
+    node_to_entity,
+)
+
+
+# --- Label Registry ---
+
+
+def test_label_registry_contains_all_entity_types():
+    """LABEL_TO_MODEL registry contains all entity types and maps to correct classes."""
+    expected = {
+        "Character": Character,
+        "Location": Location,
+        "Item": Item,
+        "Scene": Scene,
+        "Event": Event,
+        "ChatMessage": ChatMessage,
+    }
+    for label, model_cls in expected.items():
+        assert label in LABEL_TO_MODEL, f"Missing label: {label}"
+        assert LABEL_TO_MODEL[label] is model_cls
+
+
+# --- entity_to_labels ---
+
+
+def test_entity_to_labels_character():
+    """entity_to_labels returns ['Entity', 'Character'] for a Character."""
+    char = Character(id="c1", name="Alice", body="desc")
+    assert entity_to_labels(char) == ["Entity", "Character"]
+
+
+def test_entity_to_labels_location():
+    """entity_to_labels returns ['Entity', 'Location'] for a Location."""
+    loc = Location(id="l1", name="Tavern", body="desc")
+    assert entity_to_labels(loc) == ["Entity", "Location"]
+
+
+def test_entity_to_labels_item():
+    """entity_to_labels returns ['Entity', 'Item'] for an Item."""
+    item = Item(id="i1", name="Sword", body="desc")
+    assert entity_to_labels(item) == ["Entity", "Item"]
+
+
+def test_entity_to_labels_scene():
+    """entity_to_labels returns ['Entity', 'Scene'] for a Scene."""
+    scene = Scene(id="s1", name="Opening", body="desc")
+    assert entity_to_labels(scene) == ["Entity", "Scene"]
+
+
+def test_entity_to_labels_event():
+    """entity_to_labels returns ['Entity', 'Event'] for an Event."""
+    event = Event(id="e1", name="Battle", body="desc", scene_id="s1", gametime=100, walltime="2024-01-01T00:00:00")
+    assert entity_to_labels(event) == ["Entity", "Event"]
+
+
+def test_entity_to_labels_chat_message():
+    """entity_to_labels returns ['Entity', 'Event', 'ChatMessage'] for a ChatMessage."""
+    msg = ChatMessage(
+        id="m1", name="msg", body="desc", scene_id="s1",
+        gametime=100, walltime="2024-01-01T00:00:00",
+        character_id="c1", message="Hello",
+    )
+    assert entity_to_labels(msg) == ["Entity", "Event", "ChatMessage"]
+
+
+# --- entity_to_properties ---
+
+
+def test_entity_to_properties_character():
+    """entity_to_properties converts Character fields to property dict."""
+    char = Character(
+        id="c1", name="Alice", body="A brave warrior",
+        location_id="loc_1", inventory=["item_sword"],
+    )
+    props = entity_to_properties(char)
+    assert props["id"] == "c1"
+    assert props["name"] == "Alice"
+    assert props["body"] == "A brave warrior"
+    assert props["unseen"] is False
+    assert props["location_id"] == "loc_1"
+    assert props["inventory"] == ["item_sword"]
+
+
+def test_entity_to_properties_excludes_connected_locations_for_location():
+    """entity_to_properties excludes connected_locations for Location."""
+    loc = Location(id="l1", name="Tavern", body="desc", connected_locations=["l2"])
+    props = entity_to_properties(loc)
+    assert "connected_locations" not in props
+    assert props["id"] == "l1"
+
+
+def test_entity_to_properties_excludes_messages_for_scene():
+    """entity_to_properties excludes messages for Scene."""
+    scene = Scene(id="s1", name="Opening", body="desc", messages=[])
+    props = entity_to_properties(scene)
+    assert "messages" not in props
+
+
+def test_entity_to_properties_excludes_widget_for_chat_message():
+    """entity_to_properties excludes widget for ChatMessage."""
+    msg = ChatMessage(
+        id="m1", name="msg", body="desc", scene_id="s1",
+        gametime=100, walltime="2024-01-01T00:00:00",
+        character_id="c1", message="Hello", widget={"type": "poll"},
+    )
+    props = entity_to_properties(msg)
+    assert "widget" not in props
+    assert props["message"] == "Hello"
+
+
+def test_entity_to_properties_handles_none_optional_fields():
+    """entity_to_properties omits None optional fields."""
+    char = Character(id="c1", name="Alice", body="desc", location_id=None)
+    props = entity_to_properties(char)
+    assert "location_id" not in props
+
+
+def test_entity_to_properties_includes_array_fields():
+    """entity_to_properties includes list fields like inventory."""
+    char = Character(id="c1", name="Alice", body="desc", inventory=["sword", "shield"])
+    props = entity_to_properties(char)
+    assert props["inventory"] == ["sword", "shield"]
+
+
+# --- node_to_entity ---
+
+
+def test_node_to_entity_reconstructs_character():
+    """node_to_entity reconstructs a Character from labels and properties."""
+    labels = ["Entity", "Character"]
+    properties = {"id": "c1", "name": "Alice", "body": "desc", "unseen": False, "inventory": []}
+    entity = node_to_entity(labels, properties)
+    assert isinstance(entity, Character)
+    assert entity.id == "c1"
+    assert entity.name == "Alice"
+
+
+def test_node_to_entity_reconstructs_chat_message():
+    """node_to_entity reconstructs ChatMessage from multi-label node."""
+    labels = ["Entity", "Event", "ChatMessage"]
+    properties = {
+        "id": "m1", "name": "msg", "body": "desc", "scene_id": "s1",
+        "gametime": 100, "walltime": "2024-01-01T00:00:00",
+        "character_id": "c1", "message": "Hello",
+    }
+    entity = node_to_entity(labels, properties)
+    assert isinstance(entity, ChatMessage)
+    assert entity.message == "Hello"
+
+
+def test_node_to_entity_picks_chat_message_over_event():
+    """node_to_entity picks ChatMessage (most specific) when both Event and ChatMessage labels present."""
+    labels = ["Entity", "Event", "ChatMessage"]
+    properties = {
+        "id": "m1", "name": "msg", "body": "desc", "scene_id": "s1",
+        "gametime": 100, "walltime": "2024-01-01T00:00:00",
+        "character_id": "c1", "message": "Hello",
+    }
+    entity = node_to_entity(labels, properties)
+    assert isinstance(entity, ChatMessage)
+    assert type(entity) is ChatMessage  # Exact type, not bare Event
+
+
+def test_node_to_entity_reconstructs_location():
+    """node_to_entity reconstructs a Location from labels and properties."""
+    labels = ["Entity", "Location"]
+    properties = {"id": "l1", "name": "Tavern", "body": "A cozy tavern"}
+    entity = node_to_entity(labels, properties)
+    assert isinstance(entity, Location)
+    assert entity.name == "Tavern"
+    assert entity.connected_locations == []  # Default empty list
+
+
+def test_node_to_entity_raises_on_unknown_labels():
+    """node_to_entity raises QueryError for unrecognized labels."""
+    from sidestage.graph.errors import QueryError
+    labels = ["Unknown"]
+    properties = {"id": "x1"}
+    with pytest.raises(QueryError):
+        node_to_entity(labels, properties)
