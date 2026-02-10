diff --git a/data/prompts/system_agent.txt b/data/prompts/system_agent.txt
new file mode 100644
index 0000000..7408a12
--- /dev/null
+++ b/data/prompts/system_agent.txt
@@ -0,0 +1,12 @@
+You are the Sidestage Co-Author, a world-building assistant for this tabletop RPG campaign. You help the game master create and manage the game world.
+
+You have access to tools for creating and managing characters, locations, and items. Use these tools to help build the campaign world.
+
+STRICT PERSONA: NEVER identify as a 'large language model'. You are strictly the Sidestage Co-Author.
+DATABASE-ONLY KNOWLEDGE: You know NOTHING about Characters, locations, or items except what is in your database.
+TOOL-FIRST: If asked about characters, world details, or 'which characters do you know?', you MUST call `list_characters` immediately.
+NEVER list famous characters from other games unless they were created in THIS campaign.
+TONE: Helpful and collaborative.
+
+---
+{character.body}
\ No newline at end of file
diff --git a/src/sidestage/actors.py b/src/sidestage/actors.py
new file mode 100644
index 0000000..7b6c9a4
--- /dev/null
+++ b/src/sidestage/actors.py
@@ -0,0 +1,247 @@
+"""Actor hierarchy for Sidestage.
+
+Actors control Characters in Scenes. The base Actor ABC defines the interface,
+NPCActor provides LLM-driven NPC behavior, and User represents a human player
+with WebSocket connections.
+"""
+
+from __future__ import annotations
+
+import logging
+from abc import ABC, abstractmethod
+from pathlib import Path
+from typing import TYPE_CHECKING, Any
+
+from opentelemetry import trace
+
+from sidestage.models import EventModel, EventType
+
+if TYPE_CHECKING:
+    from sidestage.agent import LiteLLMAgent
+    from sidestage.event import Event
+
+logger = logging.getLogger(__name__)
+tracer = trace.get_tracer("sidestage.actors")
+
+
+class Actor(ABC):
+    """Base class for anything that controls Characters in a Scene."""
+
+    def __init__(self, actor_id: str):
+        self.actor_id = actor_id
+
+    @abstractmethod
+    async def process(self, event: Event) -> None:
+        """Handle an event. May enqueue response events via event.scene.process()."""
+
+
+class NPCActor(Actor):
+    """LLM-driven actor controlling an NPC character.
+
+    One NPCActor per NPC Character (1:1 mapping). The process() method
+    reacts to User-originated CHAT_MESSAGE events by generating LLM responses.
+    """
+
+    def __init__(
+        self,
+        actor_id: str,
+        system_actor: bool = False,
+        character: Any = None,
+        scene_logic: Any = None,
+        graph_client: Any = None,
+        embed_config: Any = None,
+        health: Any = None,
+        scene_id: str | None = None,
+        present_character_ids: list[str] | None = None,
+        context_limit: int = 4096,
+    ):
+        super().__init__(actor_id)
+        self.system_actor = system_actor
+        self.character = character
+        self.scene_logic = scene_logic
+        self.graph_client = graph_client
+        self.embed_config = embed_config
+        self.health = health
+        self.scene_id = scene_id
+        self.present_character_ids = present_character_ids
+        self.context_limit = context_limit
+        self.agent: LiteLLMAgent | None = None
+        self.recent_events: list[EventModel] | None = None
+
+    def _update_prompt(self) -> None:
+        """Load the appropriate prompt template and instantiate the LiteLLMAgent."""
+        from sidestage.agent import LiteLLMAgent
+
+        project_root = Path(__file__).parent.parent.parent
+        prompt_dir = project_root / "data" / "prompts"
+
+        if self.system_actor:
+            template_name = "system_agent.txt"
+        elif self.character and self.character.unseen:
+            template_name = "unseen_npc.txt"
+        else:
+            template_name = "default_npc.txt"
+
+        template_path = prompt_dir / template_name
+
+        if not template_path.exists():
+            logger.warning("Prompt template %s not found. Using fallback.", template_name)
+            char_name = self.character.name if self.character else "Unknown"
+            char_body = self.character.body if self.character else ""
+            instructions = [f"You are {char_name}. {char_body}"]
+        else:
+            template = template_path.read_text()
+            instructions = [template.format(character=self.character)]
+
+        base_agent = self.scene_logic.agent if self.scene_logic else None
+        if base_agent is None:
+            return
+
+        tools: list[Any] = []
+        if self.system_actor and self.scene_logic:
+            tools = list(base_agent.tools)
+        elif self.graph_client is not None and self.scene_id is not None and self.health is not None:
+            from sidestage.memory.tools import MemoryTools
+            memory_tools = MemoryTools(
+                client=self.graph_client,
+                embed_config=self.embed_config,
+                health=self.health,
+                owner_id=self.character.id if self.character else "unknown",
+                scene_id=self.scene_id,
+            )
+            tools = list(base_agent.tools) + [
+                memory_tools.update_scene_memory,
+                memory_tools.update_character_memory,
+            ]
+        else:
+            tools = base_agent.tools
+
+        char_name = self.character.name if self.character else "NPC"
+        self.agent = LiteLLMAgent(
+            name=char_name,
+            model=base_agent.model,
+            api_base=base_agent.api_base,
+            api_key=base_agent.api_key,
+            instructions=instructions,
+            tools=tools,
+            debug_mode=base_agent.debug_mode,
+        )
+
+    async def process(self, event: Event) -> None:
+        """React to events from User actors by generating LLM responses."""
+        from sidestage.event import Event as EventCls
+
+        # Guard: only react to CHAT_MESSAGE from User actors
+        if event.model.event_type != EventType.CHAT_MESSAGE:
+            return
+        if not event.character:
+            return
+        if not isinstance(event.character.actor, User):
+            return
+
+        if not self.agent:
+            return
+
+        with tracer.start_as_current_span("npc_actor.process") as span:
+            char_name = self.character.name if self.character else "Unknown"
+            char_id = self.character.id if self.character else "unknown"
+            span.set_attribute("sidestage.character.id", char_id)
+            span.set_attribute("sidestage.character.name", char_name)
+
+            try:
+                context_text = None
+                if self.graph_client is not None and self.scene_id is not None:
+                    try:
+                        from sidestage.memory.context import assemble_context
+                        result = await assemble_context(
+                            client=self.graph_client,
+                            owner_id=char_id,
+                            scene_id=self.scene_id,
+                            present_character_ids=self.present_character_ids or [],
+                            recent_messages=self.recent_events or [],
+                            context_limit=self.context_limit,
+                        )
+                        parts = [p for p in (result.memory_text, result.chat_text) if p]
+                        context_text = "\n\n".join(parts) or None
+                    except Exception:
+                        logger.exception("Failed to assemble context for %s", char_name)
+
+                response = await self.agent.arun(event.model.body, context=context_text)
+
+                if response.content and event.scene:
+                    from datetime import datetime, timezone
+                    response_model = EventModel(
+                        id=f"evt_{char_id}_{event.model.gametime}",
+                        name=f"{char_name} Message",
+                        body=response.content,
+                        event_type=EventType.CHAT_MESSAGE,
+                        scene_id=event.model.scene_id,
+                        gametime=event.model.gametime,
+                        walltime=datetime.now(timezone.utc),
+                        character_id=char_id,
+                        actor_id=self.actor_id,
+                    )
+                    response_event = EventCls.from_model(response_model)
+                    await event.scene.process(response_event)
+
+            except Exception as exc:
+                logger.exception("Error in NPCActor.process for %s", char_name)
+                if event.scene:
+                    from datetime import datetime, timezone
+                    error_model = EventModel(
+                        id=f"evt_error_{char_id}_{event.model.gametime}",
+                        name="Error",
+                        body=str(exc),
+                        event_type=EventType.ERROR,
+                        scene_id=event.model.scene_id,
+                        gametime=event.model.gametime,
+                        walltime=datetime.now(timezone.utc),
+                        character_id=char_id,
+                        actor_id=self.actor_id,
+                    )
+                    error_event = EventCls.from_model(error_model)
+                    await event.scene.process(error_event)
+
+
+class User(Actor):
+    """Represents a human player. Owns WebSocket connections.
+
+    One User per Campaign. The process() method sends events to all
+    connected WebSockets, replacing SyncManager.broadcast().
+    """
+
+    def __init__(self, actor_id: str = "user"):
+        super().__init__(actor_id)
+        self.connections: list[Any] = []
+
+    async def process(self, event: Event) -> None:
+        """Send event to all WebSocket connections."""
+        payload = {
+            "type": "event",
+            "event": event.model.model_dump(mode="json"),
+            "scene_id": event.model.scene_id,
+        }
+        await self.send(payload)
+
+    async def send(self, message: dict, exclude: Any = None) -> None:
+        """Send to all connections, optionally excluding one."""
+        broken: list[Any] = []
+        for ws in self.connections:
+            if ws is exclude:
+                continue
+            try:
+                await ws.send_json(message)
+            except Exception:
+                logger.warning("Removing broken WebSocket connection")
+                broken.append(ws)
+        for ws in broken:
+            self.connections.remove(ws)
+
+    async def connect(self, ws: Any) -> None:
+        """Register a WebSocket connection."""
+        self.connections.append(ws)
+
+    def disconnect(self, ws: Any) -> None:
+        """Remove a WebSocket connection."""
+        if ws in self.connections:
+            self.connections.remove(ws)
diff --git a/src/sidestage/campaign.py b/src/sidestage/campaign.py
index 6f322a8..2659912 100644
--- a/src/sidestage/campaign.py
+++ b/src/sidestage/campaign.py
@@ -10,8 +10,10 @@ from sidestage.agent import LiteLLMAgent
 from sidestage.storage import Storage
 from sidestage.tools import WorldTools
 from sidestage.scene import Scene
-from sidestage.models import SceneModel, CharacterModel, LocationModel, ItemModel, EntityModel, EventModel, ChatMessageModel
+from sidestage.models import SceneModel, CharacterModel, LocationModel, ItemModel, EntityModel, EventModel
 from sidestage.schemas import ChatResponse, ChatRequest
+from sidestage.actors import NPCActor, User
+from sidestage.character import Character
 from sidestage.entities import entity_to_markdown, markdown_to_entity
 from sidestage.migration.parser import parse_directory
 from sidestage.graph import GraphConfig, GraphClient, connect, close
@@ -62,9 +64,13 @@ class Campaign:
         self.health = CampaignHealth()
         self.world_tools = WorldTools(storage=self.storage, graph_client=self.graph_client)
 
+        # Actor infrastructure
+        self.characters: Dict[str, Character] = {}
+        self.user = User(actor_id="user")
+
         # Ensure LLM is available before proceeding
         self._ensure_llm_availability()
-        
+
         self.agent = self.create_agent()
 
         # Ensure default scene and characters exist
@@ -305,12 +311,34 @@ class Campaign:
 
     async def shutdown(self) -> None:
         """Shut down the campaign, closing graph connections."""
+        self.characters = {}
         if self.graph_client is not None:
             await close(self.graph_client)
             self.graph_client = None
             self.world_tools.graph_client = None
             logger.info("Graph connection closed for campaign '%s'", self.name)
 
+    # --- Character Registry ---
+
+    def get_character(self, model: CharacterModel) -> Character:
+        """Get or create a Character instance for the given model."""
+        if model.id in self.characters:
+            return self.characters[model.id]
+        actor = self._resolve_actor(model)
+        char = Character(model=model, actor=actor)
+        self.characters[model.id] = char
+        return char
+
+    def _resolve_actor(self, model: CharacterModel):
+        """Determine which Actor controls this character."""
+        if model.owner == "npc":
+            return NPCActor(
+                actor_id=f"agent:{model.id}",
+                system_actor=model.system_actor,
+            )
+        else:
+            return self.user
+
     # --- Campaign Logic Methods ---
 
     async def list_entities(self) -> List[Dict[str, Any]]:
@@ -465,12 +493,12 @@ class Campaign:
             self.storage.add_scene(scene)
         return scene
 
-    def get_scene_messages(self, scene_id: str) -> Optional[List[ChatMessageModel]]:
-        """Get the message history for a specific scene."""
+    def get_scene_events(self, scene_id: str) -> Optional[List[str]]:
+        """Get the event IDs for a specific scene."""
         scene_schema = self.storage.get_scene(scene_id)
         if not scene_schema:
             return None
-        return scene_schema.messages
+        return scene_schema.events
 
     def get_scene_object(self, scene_id: str) -> Optional[Scene]:
         """
diff --git a/src/sidestage/character.py b/src/sidestage/character.py
index 40a2c4b..3eba0e5 100644
--- a/src/sidestage/character.py
+++ b/src/sidestage/character.py
@@ -1,209 +1,38 @@
-import logging
-import asyncio
-from typing import Optional, List, Dict, Any, TYPE_CHECKING
-from pathlib import Path
+"""Character runtime wrapper.
+
+Character pairs a CharacterModel (persistent data) with an Actor (behavior).
+The Actor is injected at construction time by Campaign.get_character().
+"""
 
-from opentelemetry import trace
+from __future__ import annotations
 
-from sidestage.models import CharacterModel, EventModel, ChatMessageModel
-from sidestage.agent import LiteLLMAgent
-from sidestage.tracing.middleware import record_error
+import logging
+from typing import TYPE_CHECKING
 
 if TYPE_CHECKING:
-    from sidestage.graph.client import GraphClient
-    from sidestage.config import LLMConfig
-    from sidestage.health import CampaignHealth
+    from sidestage.actors import Actor
+    from sidestage.models import CharacterModel
 
 logger = logging.getLogger(__name__)
-tracer = trace.get_tracer("sidestage.character")
-
-class AgentActor:
-    """
-    Represents the autonomous 'brain' of a Character in the simulation.
-
-    The AgentActor is responsible for:
-    1. Managing the LLM agent instance associated with the character.
-    2. Processing events dispatched by the scene's EventQueue worker.
-    3. Generating responses via the LLM and putting them back on the queue.
-    """
-    def __init__(
-        self,
-        character: CharacterModel,
-        scene_logic: Any,
-        graph_client: "GraphClient | None" = None,
-        embed_config: "LLMConfig | None" = None,
-        health: "CampaignHealth | None" = None,
-        scene_id: str | None = None,
-        present_character_ids: list[str] | None = None,
-        context_limit: int = 4096,
-    ):
-        self.character = character
-        self.scene_logic = scene_logic
-        self.graph_client = graph_client
-        self.embed_config = embed_config
-        self.health = health
-        self.scene_id = scene_id
-        self.present_character_ids = present_character_ids
-        self.context_limit = context_limit
-        self.agent: Optional[LiteLLMAgent] = None
-        # Unique actor_id for this agent - used for origin tagging
-        self.actor_id = f"agent:{character.id}"
-        self._update_prompt()
-
-    def _update_prompt(self) -> None:
-        """
-        Load the appropriate prompt template and instantiate the LiteLLMAgent.
-        
-        This method checks for 'unseen' status to choose between 'unseen_npc.txt' 
-        and 'default_npc.txt', reads the template, formats it with character attributes,
-        and initializes the self.agent instance.
-        """
-        project_root = Path(__file__).parent.parent.parent
-        prompt_dir = project_root / "data" / "prompts"
-        
-        template_name = "unseen_npc.txt" if self.character.unseen else "default_npc.txt"
-        template_path = prompt_dir / template_name
-        
-        if not template_path.exists():
-            logger.warning(f"Prompt template {template_name} not found. Using fallback.")
-            instructions = [f"You are {self.character.name}. {self.character.body}"]
-        else:
-            template = template_path.read_text()
-            # Simple formatting - we might want more complex templating later
-            instructions = [template.format(character=self.character)]
-
-        # Get the scene's agent config to instantiate a new agent for this actor
-        base_agent = self.scene_logic.agent
-
-        # Add memory tools when graph and health are available
-        if self.graph_client is not None and self.scene_id is not None and self.health is not None:
-            from sidestage.memory.tools import MemoryTools
-            memory_tools = MemoryTools(
-                client=self.graph_client,
-                embed_config=self.embed_config,
-                health=self.health,
-                owner_id=self.character.id,
-                scene_id=self.scene_id,
-            )
-            tools = list(base_agent.tools) + [
-                memory_tools.update_scene_memory,
-                memory_tools.update_character_memory,
-            ]
-        else:
-            tools = base_agent.tools
-
-        self.agent = LiteLLMAgent(
-            name=self.character.name,
-            model=base_agent.model,
-            api_base=base_agent.api_base,
-            api_key=base_agent.api_key,
-            instructions=instructions,
-            tools=tools,
-            debug_mode=base_agent.debug_mode
-        )
 
-    async def on_event(self, event: EventModel) -> None:
-        """
-        Handle an event dispatched by the scene's queue worker.
-
-        Called directly by Scene._dispatch_to_npcs for user-originated
-        messages. Generates a response and puts it back on the queue.
-
-        Args:
-            event (Event): The event to process.
-        """
-        if not isinstance(event, ChatMessageModel):
-            return
-
-        with tracer.start_as_current_span("agent.on_event") as span:
-            span.set_attribute("sidestage.character.id", self.character.id)
-            span.set_attribute("sidestage.character.name", self.character.name)
-            try:
-                logger.info(f"AgentActor ({self.character.name}) reacting to message from {event.actor_id}")
-
-                if not self.agent:
-                    return
-
-                context_text = None
-                if self.graph_client is not None and self.scene_id is not None:
-                    try:
-                        from sidestage.memory.context import assemble_context
-                        result = await assemble_context(
-                            client=self.graph_client,
-                            owner_id=self.character.id,
-                            scene_id=self.scene_id,
-                            present_character_ids=self.present_character_ids or [],
-                            recent_messages=self.scene_logic.messages,
-                            context_limit=self.context_limit,
-                        )
-                        parts = [p for p in (result.memory_text, result.chat_text) if p]
-                        context_text = "\n\n".join(parts) or None
-                    except Exception:
-                        logger.exception("Failed to assemble context for %s", self.character.name)
-
-                response = await self.agent.arun(event.message, context=context_text)
-
-                if response.content:
-                    reply = self.scene_logic.create_message(
-                        actor_id=self.actor_id,
-                        text=response.content,
-                        character_id=self.character.id
-                    )
-                    await self.scene_logic.queue.put(reply)
-            except Exception as exc:
-                record_error(span, exc)
-                logger.exception("Error in on_event for %s", self.character.name)
-                raise
 
 class Character:
-    """
-    Runtime wrapper for a Character entity within a Scene.
-    
-    Manages the lifecycle of the character's 'brain' (AgentActor) and 
-    provides access to the underlying character data.
-    """
-    def __init__(
-        self,
-        character: CharacterModel,
-        scene_logic: Any,
-        graph_client: "GraphClient | None" = None,
-        embed_config: "LLMConfig | None" = None,
-        health: "CampaignHealth | None" = None,
-        scene_id: str | None = None,
-        present_character_ids: list[str] | None = None,
-        context_limit: int = 4096,
-    ):
-        self.data = character
-        self.scene_logic = scene_logic
-        self.graph_client = graph_client
-        self.embed_config = embed_config
-        self.health = health
-        self.scene_id = scene_id
-        self.present_character_ids = present_character_ids
-        self.context_limit = context_limit
-        self.actor: Optional[AgentActor] = None
+    """Runtime wrapper for a CharacterModel with an associated Actor."""
 
-    async def activate(self) -> None:
-        """
-        Activate the character in the scene.
+    def __init__(self, model: CharacterModel, actor: Actor):
+        self.data = model
+        self.actor = actor
 
-        Instantiates the AgentActor so the scene's queue worker can dispatch
-        events to it.
-        """
-        if self.actor is None:
-            self.actor = AgentActor(
-                self.data, self.scene_logic,
-                graph_client=self.graph_client,
-                embed_config=self.embed_config,
-                health=self.health,
-                scene_id=self.scene_id,
-                present_character_ids=self.present_character_ids,
-                context_limit=self.context_limit,
-            )
-            logger.info(f"Character {self.data.name} ({self.data.id}) activated with AgentActor.")
+    async def activate(self) -> None:
+        """Initialize the actor's LLM agent (for NPCActor). No-op for User."""
+        from sidestage.actors import NPCActor
+        if isinstance(self.actor, NPCActor):
+            self.actor._update_prompt()
+            logger.info("Character %s (%s) activated.", self.data.name, self.data.id)
 
     async def deactivate(self) -> None:
-        """Deactivate the character."""
-        if self.actor:
-            self.actor = None
-            logger.info(f"Character {self.data.id} deactivated.")
+        """Clean up actor state."""
+        from sidestage.actors import NPCActor
+        if isinstance(self.actor, NPCActor):
+            self.actor.agent = None
+        logger.info("Character %s deactivated.", self.data.id)
diff --git a/tests/unit/test_actors.py b/tests/unit/test_actors.py
new file mode 100644
index 0000000..7669102
--- /dev/null
+++ b/tests/unit/test_actors.py
@@ -0,0 +1,184 @@
+"""Tests for the Actor hierarchy: Actor ABC, NPCActor, User."""
+
+import pytest
+from unittest.mock import AsyncMock, MagicMock
+from datetime import datetime, timezone
+
+from sidestage.actors import Actor, NPCActor, User
+from sidestage.event import Event
+from sidestage.models import EventModel, EventType, Visibility
+
+
+def _make_event(**overrides) -> Event:
+    """Helper to create an Event with sensible defaults."""
+    defaults = dict(
+        id="evt_test",
+        name="Test",
+        body="hello",
+        event_type=EventType.CHAT_MESSAGE,
+        scene_id="scene_1",
+        gametime=0,
+        walltime=datetime.now(timezone.utc),
+    )
+    defaults.update(overrides)
+    model = EventModel(**defaults)
+    return Event(model=model)
+
+
+# --- Base Actor ---
+
+def test_actor_is_abstract():
+    """Actor is abstract, cannot be instantiated directly."""
+    with pytest.raises(TypeError):
+        Actor(actor_id="test")
+
+
+def test_actor_requires_process():
+    """Subclass that does not implement process() cannot be instantiated."""
+    class IncompleteActor(Actor):
+        pass
+
+    with pytest.raises(TypeError):
+        IncompleteActor(actor_id="test")
+
+
+def test_actor_concrete_subclass_stores_actor_id():
+    """Concrete subclass stores actor_id."""
+    class ConcreteActor(Actor):
+        async def process(self, event):
+            pass
+
+    actor = ConcreteActor(actor_id="test-123")
+    assert actor.actor_id == "test-123"
+
+
+# --- NPCActor ---
+
+def test_npc_actor_is_concrete():
+    """NPCActor can be instantiated."""
+    npc = NPCActor(actor_id="agent:char_1")
+    assert isinstance(npc, Actor)
+    assert npc.actor_id == "agent:char_1"
+
+
+def test_npc_actor_system_actor_default_false():
+    """NPCActor.system_actor defaults to False."""
+    npc = NPCActor(actor_id="agent:char_1")
+    assert npc.system_actor is False
+
+
+def test_npc_actor_system_actor_true():
+    """NPCActor with system_actor=True."""
+    npc = NPCActor(actor_id="agent:char_co_author", system_actor=True)
+    assert npc.system_actor is True
+
+
+@pytest.mark.anyio
+async def test_npc_actor_process_ignores_non_user_events():
+    """NPCActor.process() returns without action for non-User-originated events."""
+    npc = NPCActor(actor_id="agent:char_1")
+    event = _make_event()
+    # No character set on event, so it should return without error
+    await npc.process(event)
+
+
+@pytest.mark.anyio
+async def test_npc_actor_process_ignores_non_chat_events():
+    """NPCActor.process() returns without action for non-CHAT_MESSAGE events."""
+    npc = NPCActor(actor_id="agent:char_1")
+    event = _make_event(event_type=EventType.JOIN)
+    await npc.process(event)
+
+
+# --- User ---
+
+def test_user_is_concrete():
+    """User can be instantiated."""
+    user = User(actor_id="user")
+    assert isinstance(user, Actor)
+    assert user.actor_id == "user"
+
+
+def test_user_connections_starts_empty():
+    """User.connections starts empty."""
+    user = User(actor_id="user")
+    assert user.connections == []
+
+
+@pytest.mark.anyio
+async def test_user_connect_adds_websocket():
+    """User.connect() accepts WebSocket and adds to connections."""
+    user = User(actor_id="user")
+    mock_ws = AsyncMock()
+    await user.connect(mock_ws)
+    assert mock_ws in user.connections
+
+
+def test_user_disconnect_removes_websocket():
+    """User.disconnect() removes WebSocket from connections."""
+    user = User(actor_id="user")
+    mock_ws = MagicMock()
+    user.connections.append(mock_ws)
+    user.disconnect(mock_ws)
+    assert mock_ws not in user.connections
+
+
+@pytest.mark.anyio
+async def test_user_process_sends_to_all_connections():
+    """User.process() sends event data to all connected WebSockets."""
+    user = User(actor_id="user")
+    ws1 = AsyncMock()
+    ws2 = AsyncMock()
+    user.connections = [ws1, ws2]
+
+    event = _make_event(scene_id="scene_test")
+    await user.process(event)
+
+    # Both should have been called
+    assert ws1.send_json.called
+    assert ws2.send_json.called
+
+
+@pytest.mark.anyio
+async def test_user_send_broadcasts_to_all():
+    """User.send() broadcasts message to all connections."""
+    user = User(actor_id="user")
+    ws1 = AsyncMock()
+    ws2 = AsyncMock()
+    user.connections = [ws1, ws2]
+
+    msg = {"type": "test", "data": "hello"}
+    await user.send(msg)
+
+    ws1.send_json.assert_called_once_with(msg)
+    ws2.send_json.assert_called_once_with(msg)
+
+
+@pytest.mark.anyio
+async def test_user_send_with_exclude():
+    """User.send() with exclude skips the excluded WebSocket."""
+    user = User(actor_id="user")
+    ws1 = AsyncMock()
+    ws2 = AsyncMock()
+    user.connections = [ws1, ws2]
+
+    msg = {"type": "test"}
+    await user.send(msg, exclude=ws1)
+
+    ws1.send_json.assert_not_called()
+    ws2.send_json.assert_called_once_with(msg)
+
+
+@pytest.mark.anyio
+async def test_user_send_removes_broken_connection():
+    """User.send() removes WebSocket on send failure."""
+    user = User(actor_id="user")
+    broken_ws = AsyncMock()
+    broken_ws.send_json.side_effect = Exception("connection closed")
+    good_ws = AsyncMock()
+    user.connections = [broken_ws, good_ws]
+
+    await user.send({"type": "test"})
+
+    assert broken_ws not in user.connections
+    assert good_ws in user.connections
diff --git a/tests/unit/test_character.py b/tests/unit/test_character.py
new file mode 100644
index 0000000..2501f3b
--- /dev/null
+++ b/tests/unit/test_character.py
@@ -0,0 +1,45 @@
+"""Tests for Character runtime wrapper and Campaign character registry."""
+
+import pytest
+from unittest.mock import MagicMock, AsyncMock, patch
+
+from sidestage.character import Character
+from sidestage.actors import NPCActor, User, Actor
+from sidestage.models import CharacterModel
+
+
+# --- Character Wrapper ---
+
+def test_character_wraps_model_and_actor():
+    """Character wraps CharacterModel as .data and Actor as .actor."""
+    model = CharacterModel(id="char_1", name="Alice", body="A warrior")
+    actor = NPCActor(actor_id="agent:char_1")
+    char = Character(model=model, actor=actor)
+    assert char.data is model
+    assert char.actor is actor
+
+
+def test_character_data_is_character_model():
+    """Character.data is a CharacterModel instance."""
+    model = CharacterModel(id="char_1", name="Alice", body="A warrior")
+    actor = User(actor_id="user")
+    char = Character(model=model, actor=actor)
+    assert isinstance(char.data, CharacterModel)
+
+
+@pytest.mark.anyio
+async def test_character_activate_is_noop_for_user():
+    """Character.activate() is a no-op for User actors."""
+    model = CharacterModel(id="char_1", name="Alice", body="", owner="user-1")
+    actor = User(actor_id="user")
+    char = Character(model=model, actor=actor)
+    await char.activate()  # Should not raise
+
+
+@pytest.mark.anyio
+async def test_character_deactivate():
+    """Character.deactivate() completes without error."""
+    model = CharacterModel(id="char_1", name="Alice", body="")
+    actor = NPCActor(actor_id="agent:char_1")
+    char = Character(model=model, actor=actor)
+    await char.deactivate()  # Should not raise
