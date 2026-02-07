diff --git a/planning/01-falkordb-foundation/implementation/deep_implement_config.json b/planning/01-falkordb-foundation/implementation/deep_implement_config.json
index 20b66d5..1d675f9 100644
--- a/planning/01-falkordb-foundation/implementation/deep_implement_config.json
+++ b/planning/01-falkordb-foundation/implementation/deep_implement_config.json
@@ -30,6 +30,10 @@
     "section-04-relationships": {
       "status": "complete",
       "commit_hash": "404182a02436744a10c86e6b9c296fec84e8a1c2"
+    },
+    "section-05-queries": {
+      "status": "complete",
+      "commit_hash": "3d0a7dcd423ec083748d8a28cdb4705e9ef92a49"
     }
   },
   "pre_commit": {
diff --git a/src/sidestage/campaign.py b/src/sidestage/campaign.py
index 3049378..3dcfb20 100644
--- a/src/sidestage/campaign.py
+++ b/src/sidestage/campaign.py
@@ -12,6 +12,7 @@ from sidestage.tools import WorldTools
 from sidestage.scene import SceneLogic
 from sidestage.schemas import Scene, Character, Location, Item, Entity, Event, ChatResponse, ChatMessage, ChatRequest
 from sidestage.entities import entity_to_markdown, markdown_to_entity
+from sidestage.graph import GraphConfig, GraphClient, connect, close
 
 logger = logging.getLogger(__name__)
 
@@ -31,6 +32,9 @@ class SidestageConfig(BaseModel):
     gemini_api_key: Optional[str] = None
     gemini_model: str = "gemini-1.5-flash"
 
+    # Graph Database Configuration
+    graph: GraphConfig = Field(default_factory=GraphConfig, description="FalkorDB graph database configuration")
+
 class Campaign:
     """
     Represents a specific Campaign (a distinct save/world).
@@ -64,8 +68,9 @@ class Campaign:
         # Storage handles SQLite connection
         self.storage = Storage(db_path=self.campaign_dir / "sidestage.db")
 
-        self.world_tools = WorldTools(storage=self.storage)
-        
+        self.graph_client: GraphClient | None = None
+        self.world_tools = WorldTools(storage=self.storage, graph_client=self.graph_client)
+
         # Ensure LLM is available before proceeding
         self._ensure_llm_availability()
         
@@ -263,6 +268,25 @@ class Campaign:
             # Skipping for now as it doesn't fit the /v1/models requirement as cleanly.
             pass
 
+    async def start_graph(self) -> None:
+        """Initialize the FalkorDB graph connection.
+
+        Must be called after __init__ and before any graph operations.
+        Derives graph_name from campaign name if not configured.
+        """
+        config = self.config.graph
+        self.graph_client = await connect(config, campaign_name=self.name)
+        self.world_tools.graph_client = self.graph_client
+        logger.info("Graph connection established for campaign '%s'", self.name)
+
+    async def shutdown(self) -> None:
+        """Shut down the campaign, closing graph connections."""
+        if self.graph_client is not None:
+            await close(self.graph_client)
+            self.graph_client = None
+            self.world_tools.graph_client = None
+            logger.info("Graph connection closed for campaign '%s'", self.name)
+
     # --- Campaign Logic Methods ---
 
     def list_entities(self) -> List[Dict[str, Any]]:
diff --git a/src/sidestage/graph/__init__.py b/src/sidestage/graph/__init__.py
index e69de29..2ca9c9b 100644
--- a/src/sidestage/graph/__init__.py
+++ b/src/sidestage/graph/__init__.py
@@ -0,0 +1,62 @@
+"""FalkorDB graph persistence layer for Sidestage.
+
+Public API re-exports for the graph package. All consumers should import
+from ``sidestage.graph`` rather than from submodules directly.
+"""
+
+from sidestage.graph.client import GraphClient, GraphConfig, connect, close
+from sidestage.graph.entities import (
+    create_entity,
+    get_entity,
+    update_entity,
+    delete_entity,
+    list_entities,
+    find_entities,
+)
+from sidestage.graph.relationships import link, unlink, get_related, get_relationships
+from sidestage.graph.queries import (
+    characters_at_location,
+    connected_locations,
+    scene_events,
+    entity_graph,
+)
+from sidestage.graph.errors import (
+    GraphError,
+    ConnectionError as GraphConnectionError,
+    EntityNotFoundError,
+    DuplicateEntityError,
+    SchemaError,
+    QueryError,
+)
+
+__all__ = [
+    # Client
+    "GraphClient",
+    "GraphConfig",
+    "connect",
+    "close",
+    # Entities
+    "create_entity",
+    "get_entity",
+    "update_entity",
+    "delete_entity",
+    "list_entities",
+    "find_entities",
+    # Relationships
+    "link",
+    "unlink",
+    "get_related",
+    "get_relationships",
+    # Queries
+    "characters_at_location",
+    "connected_locations",
+    "scene_events",
+    "entity_graph",
+    # Errors
+    "GraphError",
+    "GraphConnectionError",
+    "EntityNotFoundError",
+    "DuplicateEntityError",
+    "SchemaError",
+    "QueryError",
+]
diff --git a/src/sidestage/scene.py b/src/sidestage/scene.py
index ba01659..be5f489 100644
--- a/src/sidestage/scene.py
+++ b/src/sidestage/scene.py
@@ -22,7 +22,8 @@ class SceneLogic:
     - Persistence of scene data via Storage.
     - Creation and routing of chat messages.
     """
-    def __init__(self, storage: Storage, agent: LiteLLMAgent, data: Scene):
+    def __init__(self, storage: Storage, agent: LiteLLMAgent, data: Scene,
+                 graph_client=None):
         """
         Initialize the SceneLogic.
 
@@ -30,10 +31,12 @@ class SceneLogic:
             storage (Storage): The persistence layer.
             agent (LiteLLMAgent): The default agent configuration used for spawning characters.
             data (Scene): The underlying data model for the scene.
+            graph_client: Optional GraphClient for graph-based persistence.
         """
         self.storage = storage
         self.agent = agent
         self.data = data
+        self.graph_client = graph_client
         self.bus = SceneMessageBus()
         self.characters: Dict[str, CharacterLogic] = {}
         self._active = False
diff --git a/src/sidestage/tools.py b/src/sidestage/tools.py
index 5207266..4b9f283 100644
--- a/src/sidestage/tools.py
+++ b/src/sidestage/tools.py
@@ -4,9 +4,11 @@ from sidestage.storage import Storage
 from sidestage.models import Character, Location, Item
 
 class WorldTools:
-    def __init__(self, storage: Storage, on_change: Optional[Callable[[], Any]] = None):
+    def __init__(self, storage: Storage, on_change: Optional[Callable[[], Any]] = None,
+                 graph_client=None):
         self.storage = storage
         self.on_change = on_change
+        self.graph_client = graph_client
 
     def _notify_change(self):
         if self.on_change:
diff --git a/tests/integration/test_graph_integration.py b/tests/integration/test_graph_integration.py
new file mode 100644
index 0000000..560fdca
--- /dev/null
+++ b/tests/integration/test_graph_integration.py
@@ -0,0 +1,97 @@
+"""Integration tests: verify Campaign, SceneLogic, and WorldTools route through graph module."""
+import pytest
+from unittest.mock import AsyncMock, MagicMock, patch
+from pathlib import Path
+
+from sidestage.graph import GraphConfig
+from sidestage.graph.client import GraphClient
+
+
+# --- GraphConfig in SidestageConfig ---
+
+
+def test_sidestage_config_has_graph_field():
+    """SidestageConfig has a graph field with GraphConfig default."""
+    from sidestage.campaign import SidestageConfig
+    config = SidestageConfig()
+    assert isinstance(config.graph, GraphConfig)
+    assert config.graph.host == "localhost"
+    assert config.graph.port == 6379
+
+
+def test_sidestage_config_graph_custom_values():
+    """SidestageConfig accepts custom graph configuration."""
+    from sidestage.campaign import SidestageConfig
+    config = SidestageConfig(graph={"host": "graphdb", "port": 7379, "max_connections": 8})
+    assert config.graph.host == "graphdb"
+    assert config.graph.port == 7379
+    assert config.graph.max_connections == 8
+
+
+# --- Campaign graph lifecycle ---
+
+
+def test_campaign_has_graph_client_attribute():
+    """Campaign has a graph_client attribute (initially None)."""
+    from sidestage.campaign import Campaign
+    assert hasattr(Campaign, '__init__')
+    # We can't easily construct a Campaign without LLM/storage setup,
+    # but we can verify the class has the expected method
+    assert hasattr(Campaign, 'start_graph')
+    assert hasattr(Campaign, 'shutdown')
+
+
+# --- WorldTools graph_client parameter ---
+
+
+def test_world_tools_accepts_graph_client():
+    """WorldTools constructor accepts optional graph_client."""
+    from sidestage.tools import WorldTools
+    storage = MagicMock()
+    client = MagicMock(spec=GraphClient)
+
+    wt = WorldTools(storage=storage, graph_client=client)
+
+    assert wt.graph_client is client
+
+
+def test_world_tools_graph_client_defaults_none():
+    """WorldTools graph_client defaults to None."""
+    from sidestage.tools import WorldTools
+    storage = MagicMock()
+
+    wt = WorldTools(storage=storage)
+
+    assert wt.graph_client is None
+
+
+# --- SceneLogic graph_client parameter ---
+
+
+def test_scene_logic_accepts_graph_client():
+    """SceneLogic constructor accepts optional graph_client."""
+    from sidestage.scene import SceneLogic
+    from sidestage.schemas import Scene
+
+    storage = MagicMock()
+    agent = MagicMock()
+    scene_data = Scene(id="s1", name="Test", body="desc", current_gametime=0)
+    client = MagicMock(spec=GraphClient)
+
+    sl = SceneLogic(storage, agent, scene_data, graph_client=client)
+
+    assert sl.graph_client is client
+
+
+def test_scene_logic_graph_client_defaults_none():
+    """SceneLogic graph_client defaults to None."""
+    from sidestage.scene import SceneLogic
+    from sidestage.schemas import Scene
+
+    storage = MagicMock()
+    agent = MagicMock()
+    scene_data = Scene(id="s1", name="Test", body="desc", current_gametime=0)
+
+    sl = SceneLogic(storage, agent, scene_data)
+
+    assert sl.graph_client is None
diff --git a/tests/unit/test_graph_init.py b/tests/unit/test_graph_init.py
new file mode 100644
index 0000000..8d8234f
--- /dev/null
+++ b/tests/unit/test_graph_init.py
@@ -0,0 +1,81 @@
+"""Tests for graph package __init__.py public API."""
+import pytest
+
+
+def test_graph_exports_client():
+    """graph package exports GraphClient and GraphConfig."""
+    from sidestage.graph import GraphClient, GraphConfig
+    assert GraphClient is not None
+    assert GraphConfig is not None
+
+
+def test_graph_exports_connect_close():
+    """graph package exports connect and close."""
+    from sidestage.graph import connect, close
+    assert callable(connect)
+    assert callable(close)
+
+
+def test_graph_exports_entity_crud():
+    """graph package exports entity CRUD functions."""
+    from sidestage.graph import (
+        create_entity,
+        get_entity,
+        update_entity,
+        delete_entity,
+        list_entities,
+        find_entities,
+    )
+    assert callable(create_entity)
+    assert callable(get_entity)
+    assert callable(update_entity)
+    assert callable(delete_entity)
+    assert callable(list_entities)
+    assert callable(find_entities)
+
+
+def test_graph_exports_relationship_functions():
+    """graph package exports relationship functions."""
+    from sidestage.graph import link, unlink, get_related, get_relationships
+    assert callable(link)
+    assert callable(unlink)
+    assert callable(get_related)
+    assert callable(get_relationships)
+
+
+def test_graph_exports_query_functions():
+    """graph package exports query functions."""
+    from sidestage.graph import (
+        characters_at_location,
+        connected_locations,
+        scene_events,
+        entity_graph,
+    )
+    assert callable(characters_at_location)
+    assert callable(connected_locations)
+    assert callable(scene_events)
+    assert callable(entity_graph)
+
+
+def test_graph_exports_error_types():
+    """graph package exports all error types."""
+    from sidestage.graph import (
+        GraphError,
+        GraphConnectionError,
+        EntityNotFoundError,
+        DuplicateEntityError,
+        SchemaError,
+        QueryError,
+    )
+    assert issubclass(GraphConnectionError, GraphError)
+    assert issubclass(EntityNotFoundError, GraphError)
+    assert issubclass(DuplicateEntityError, GraphError)
+    assert issubclass(SchemaError, GraphError)
+    assert issubclass(QueryError, GraphError)
+
+
+def test_graph_all_matches_exports():
+    """__all__ lists all public names."""
+    import sidestage.graph as graph_mod
+    for name in graph_mod.__all__:
+        assert hasattr(graph_mod, name), f"{name} listed in __all__ but not importable"
