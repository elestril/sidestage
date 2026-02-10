diff --git a/src/sidestage/event.py b/src/sidestage/event.py
new file mode 100644
index 0000000..b899b0c
--- /dev/null
+++ b/src/sidestage/event.py
@@ -0,0 +1,99 @@
+"""Runtime event wrapper and async event queue.
+
+The Event class carries an EventModel plus runtime context (tracing, scene
+reference) that should NOT be persisted. The EventQueue processes Event
+objects sequentially through a handler callback.
+"""
+
+from __future__ import annotations
+
+import asyncio
+import logging
+from dataclasses import dataclass, field
+from typing import TYPE_CHECKING, Awaitable, Callable, Optional
+
+from opentelemetry import trace
+
+from sidestage.models import EventModel
+
+if TYPE_CHECKING:
+    from opentelemetry.trace import SpanContext
+
+logger = logging.getLogger(__name__)
+
+
+@dataclass
+class Event:
+    """Runtime event wrapper carrying model data, tracing context, and scene reference."""
+
+    model: EventModel
+    span_context: SpanContext | None = None
+    scene: object | None = field(default=None, repr=False)
+
+    @property
+    def character(self):
+        """Look up the originating Character via the scene's character registry."""
+        if self.scene and self.model.character_id:
+            characters = getattr(self.scene, "characters", {})
+            return characters.get(self.model.character_id)
+        return None
+
+    @classmethod
+    def from_model(cls, model: EventModel) -> Event:
+        """Create an Event from an EventModel, capturing the current span context."""
+        span = trace.get_current_span()
+        ctx = span.get_span_context() if span else None
+        if ctx and not ctx.is_valid:
+            ctx = None
+        return cls(model=model, span_context=ctx)
+
+
+EventHandler = Callable[[Event], Awaitable[None]]
+
+
+class EventQueue:
+    """Async event queue for sequential event processing.
+
+    Events (Event wrappers, not raw EventModel) are processed one at a time
+    by a single handler callback.
+    """
+
+    def __init__(self):
+        self.queue: asyncio.Queue[Event] = asyncio.Queue()
+        self._running = False
+        self._task: Optional[asyncio.Task] = None
+
+    async def start(self, handler: EventHandler) -> None:
+        """Start the background worker with the given handler."""
+        if self._running:
+            return
+        self._running = True
+        self._task = asyncio.create_task(self._worker(handler))
+        logger.info("EventQueue started.")
+
+    async def stop(self) -> None:
+        """Stop the background worker."""
+        self._running = False
+        if self._task:
+            self._task.cancel()
+            try:
+                await self._task
+            except asyncio.CancelledError:
+                pass
+        logger.info("EventQueue stopped.")
+
+    async def put(self, event: Event) -> None:
+        """Add an event to the queue."""
+        await self.queue.put(event)
+
+    async def _worker(self, handler: EventHandler) -> None:
+        """Background loop: pull events and pass to handler."""
+        while self._running:
+            try:
+                event = await self.queue.get()
+                await handler(event)
+                self.queue.task_done()
+            except asyncio.CancelledError:
+                break
+            except Exception:
+                logger.exception("EventQueue worker error")
diff --git a/src/sidestage/graph/entities.py b/src/sidestage/graph/entities.py
index 56c9d6b..6917d42 100644
--- a/src/sidestage/graph/entities.py
+++ b/src/sidestage/graph/entities.py
@@ -15,12 +15,8 @@ from sidestage.graph.errors import DuplicateEntityError, EntityNotFoundError, Qu
 from sidestage.models import (
     EntityModel,
     CharacterModel,
-    ChatMessageModel,
     EventModel,
-    FastForwardEventModel,
     ItemModel,
-    JoinEventModel,
-    LeaveEventModel,
     LocationModel,
     SceneModel,
 )
@@ -34,10 +30,6 @@ logger = logging.getLogger(__name__)
 
 # Ordered most-specific first so deserialization picks the right model.
 LABEL_TO_MODEL: dict[str, type[EntityModel]] = {
-    "ChatMessage": ChatMessageModel,
-    "JoinEvent": JoinEventModel,
-    "LeaveEvent": LeaveEventModel,
-    "FastForwardEvent": FastForwardEventModel,
     "Character": CharacterModel,
     "Location": LocationModel,
     "Item": ItemModel,
@@ -51,17 +43,11 @@ MODEL_TO_LABELS: dict[type[EntityModel], list[str]] = {
     ItemModel: ["Entity", "Item"],
     SceneModel: ["Entity", "Scene"],
     EventModel: ["Entity", "Event"],
-    ChatMessageModel: ["Entity", "Event", "ChatMessage"],
-    JoinEventModel: ["Entity", "Event", "JoinEvent"],
-    LeaveEventModel: ["Entity", "Event", "LeaveEvent"],
-    FastForwardEventModel: ["Entity", "Event", "FastForwardEvent"],
 }
 
 # Fields that should NOT be stored as graph node properties.
 EXCLUDED_FIELDS: dict[type[EntityModel], set[str]] = {
     LocationModel: {"connected_locations"},
-    SceneModel: {"messages"},
-    ChatMessageModel: {"widget"},
 }
 
 # Valid property key pattern for Cypher safety.
diff --git a/src/sidestage/models.py b/src/sidestage/models.py
index fb96dd9..10788a6 100644
--- a/src/sidestage/models.py
+++ b/src/sidestage/models.py
@@ -4,9 +4,28 @@ All persistent domain objects (entities, events, scenes) are defined here.
 API request/response schemas live in schemas.py.
 """
 
+from datetime import datetime
+from enum import Enum
 from typing import Any, ClassVar, Dict, List, Optional
 
-from pydantic import BaseModel, Field, model_validator
+from pydantic import BaseModel, ConfigDict, Field
+
+
+# --- Enums ---
+
+
+class EventType(str, Enum):
+    CHAT_MESSAGE = "ChatMessage"
+    JOIN = "JoinEvent"
+    LEAVE = "LeaveEvent"
+    ADJUST_GAMETIME = "AdjustGametime"
+    ERROR = "Error"
+
+
+class Visibility(str, Enum):
+    PUBLIC = "public"
+    GM_ONLY = "gm_only"
+    PRIVATE = "private"
 
 
 # --- Domain Models ---
@@ -16,7 +35,7 @@ class EntityModel(BaseModel):
     entity_type: ClassVar[str] = "Entity"
 
     name: str
-    body: str
+    body: str = ""
     id: str = Field(..., description="Unique identifier for the entity")
 
 
@@ -46,83 +65,33 @@ class CharacterModel(EntityModel):
     inventory: List[str] = Field(
         default_factory=list, description="IDs of items in possession"
     )
+    owner: str = Field(
+        default="npc",
+        description="'npc' for NPC characters, a user_id string for player characters",
+    )
+    system_actor: bool = Field(
+        default=False, description="True for the Campaign Co-Author character"
+    )
 
 
 class EventModel(EntityModel):
+    model_config = ConfigDict(extra="ignore")
+
     entity_type: ClassVar[str] = "Event"
 
+    event_type: EventType
     scene_id: str
     gametime: int = Field(
         ..., description="Gametime in seconds when the event occurred"
     )
-    walltime: str = Field(
-        ..., description="ISO formatted walltime when the event occurred"
-    )
-
-
-class ChatMessageModel(EventModel):
-    entity_type: ClassVar[str] = "ChatMessage"
-
-    character_id: str = Field(
-        ..., description="ID of the Character persona who sent the message"
-    )
-    actor_id: Optional[str] = Field(
-        default=None,
-        description="ID of the Actor who originated the message (for audit)",
-    )
-    message: str = Field(..., description="The content of the chat message")
-    widget: Optional[Dict[str, Any]] = Field(
-        default=None, description="Optional interactive widget data"
-    )
-
-    @model_validator(mode="before")
-    @classmethod
-    def backfill_legacy_fields(cls, data: Any) -> Any:
-        if isinstance(data, dict):
-            # Handle missing character_id
-            if "character_id" not in data:
-                # Legacy data might have 'actor' field
-                actor = data.get("actor")
-                if actor:
-                    # Map 'actor' to 'actor_id' if missing
-                    if "actor_id" not in data:
-                        data["actor_id"] = actor
-
-                    # Map 'actor' to 'character_id'
-                    if actor == "agent":
-                        data["character_id"] = "char_co_author"
-                    elif actor == "user":
-                        data["character_id"] = "user"
-                    else:
-                        data["character_id"] = actor
-                else:
-                    data["character_id"] = "unknown"
-
-            # Handle missing actor_id if we just have character_id
-            if "actor_id" not in data and "actor" in data:
-                data["actor_id"] = data["actor"]
-
-        return data
-
-
-class JoinEventModel(EventModel):
-    entity_type: ClassVar[str] = "JoinEvent"
-
-    actor_id: str = Field(..., description="ID of the Actor who joined")
-
-
-class LeaveEventModel(EventModel):
-    entity_type: ClassVar[str] = "LeaveEvent"
-
-    actor_id: str = Field(..., description="ID of the Actor who left")
-
-
-class FastForwardEventModel(EventModel):
-    entity_type: ClassVar[str] = "FastForwardEvent"
-
-    duration_str: str = Field(
-        ..., description="A string describing the time jump, e.g. '2 hours'"
+    walltime: datetime = Field(
+        ..., description="Real-world timestamp when the event occurred"
     )
+    character_id: Optional[str] = None
+    actor_id: Optional[str] = None
+    body: str = ""
+    metadata: Dict[str, Any] = Field(default_factory=dict)
+    visibility: Visibility = Visibility.PUBLIC
 
 
 class SceneModel(EntityModel):
@@ -137,6 +106,3 @@ class SceneModel(EntityModel):
     events: List[str] = Field(
         default_factory=list, description="IDs of events in this scene"
     )
-    messages: List[ChatMessageModel] = Field(
-        default_factory=list, description="List of messages in this scene"
-    )
diff --git a/src/sidestage/schemas.py b/src/sidestage/schemas.py
index 2ee429f..68d5c6e 100644
--- a/src/sidestage/schemas.py
+++ b/src/sidestage/schemas.py
@@ -7,7 +7,7 @@ from typing import Any, Dict, Literal, Optional
 
 from pydantic import BaseModel
 
-from sidestage.models import ChatMessageModel
+from sidestage.models import EventModel
 
 
 # --- API Request/Response Models ---
@@ -60,5 +60,4 @@ class ChatRequest(BaseModel):
 
 
 class ChatResponse(BaseModel):
-    user_message: ChatMessageModel
-    agent_message: Optional[ChatMessageModel] = None
+    event: EventModel
diff --git a/tests/unit/test_event.py b/tests/unit/test_event.py
new file mode 100644
index 0000000..84122f6
--- /dev/null
+++ b/tests/unit/test_event.py
@@ -0,0 +1,159 @@
+import asyncio
+from datetime import datetime, timezone
+
+import pytest
+
+from sidestage.models import EventModel, EventType
+from sidestage.event import Event, EventQueue
+
+# EventQueue uses asyncio.create_task, so restrict async tests to asyncio backend
+
+@pytest.fixture(params=["asyncio"])
+def anyio_backend(request):
+    return request.param
+
+
+def _make_event_model(**overrides) -> EventModel:
+    """Helper to create an EventModel with sensible defaults."""
+    defaults = dict(
+        id="evt_test",
+        name="Test",
+        body="",
+        event_type=EventType.CHAT_MESSAGE,
+        scene_id="scene_1",
+        gametime=0,
+        walltime=datetime.now(timezone.utc),
+    )
+    defaults.update(overrides)
+    return EventModel(**defaults)
+
+
+# --- Event Wrapper ---
+
+def test_event_wraps_event_model():
+    """Event wraps an EventModel instance."""
+    model = _make_event_model()
+    event = Event(model=model)
+    assert event.model is model
+
+
+def test_event_is_not_pydantic():
+    """Event is a plain class, not a Pydantic model."""
+    from pydantic import BaseModel
+    assert not issubclass(Event, BaseModel)
+
+
+def test_event_span_context_defaults_none():
+    """Event.span_context defaults to None."""
+    event = Event(model=_make_event_model())
+    assert event.span_context is None
+
+
+def test_event_scene_defaults_none():
+    """Event.scene defaults to None."""
+    event = Event(model=_make_event_model())
+    assert event.scene is None
+
+
+def test_event_character_returns_none_when_scene_none():
+    """Event.character returns None when scene is not set."""
+    model = _make_event_model(character_id="char_1")
+    event = Event(model=model)
+    assert event.character is None
+
+
+def test_event_character_returns_none_when_character_id_none():
+    """Event.character returns None when model.character_id is None."""
+    model = _make_event_model(character_id=None)
+    event = Event(model=model)
+    event.scene = type("FakeScene", (), {"characters": {}})()
+    assert event.character is None
+
+
+def test_event_character_looks_up_from_scene():
+    """Event.character looks up character from scene.characters dict."""
+    model = _make_event_model(character_id="char_alice")
+    event = Event(model=model)
+    fake_char = object()
+    event.scene = type("FakeScene", (), {"characters": {"char_alice": fake_char}})()
+    assert event.character is fake_char
+
+
+# --- Factory ---
+
+def test_event_from_model_creates_event():
+    """Event.from_model() creates an Event from an EventModel."""
+    model = _make_event_model()
+    event = Event.from_model(model)
+    assert isinstance(event, Event)
+    assert event.model is model
+
+
+def test_event_from_model_scene_is_none():
+    """Event.from_model() does NOT set scene reference."""
+    model = _make_event_model()
+    event = Event.from_model(model)
+    assert event.scene is None
+
+
+def test_event_from_model_span_context_none_without_active_span():
+    """Event.from_model() sets span_context=None when no active span."""
+    model = _make_event_model()
+    event = Event.from_model(model)
+    assert event.span_context is None
+
+
+# --- Queue Integration ---
+
+@pytest.mark.anyio
+async def test_event_queue_accepts_event_objects():
+    """EventQueue accepts Event objects (not raw EventModel)."""
+    received = []
+
+    async def handler(event: Event):
+        received.append(event)
+
+    queue = EventQueue()
+    await queue.start(handler)
+
+    model = _make_event_model()
+    event = Event.from_model(model)
+    await queue.put(event)
+
+    await asyncio.sleep(0.05)
+    await queue.stop()
+
+    assert len(received) == 1
+    assert received[0] is event
+    assert isinstance(received[0], Event)
+
+
+@pytest.mark.anyio
+async def test_event_queue_handler_receives_event_objects():
+    """EventQueue handler receives Event (not EventModel)."""
+    received_types = []
+
+    async def handler(event: Event):
+        received_types.append(type(event).__name__)
+
+    queue = EventQueue()
+    await queue.start(handler)
+    await queue.put(Event.from_model(_make_event_model()))
+    await asyncio.sleep(0.05)
+    await queue.stop()
+
+    assert received_types == ["Event"]
+
+
+@pytest.mark.anyio
+async def test_event_queue_start_stop_lifecycle():
+    """EventQueue start/stop lifecycle works with Event type."""
+    queue = EventQueue()
+
+    async def handler(event: Event):
+        pass
+
+    await queue.start(handler)
+    assert queue._running is True
+    await queue.stop()
+    assert queue._running is False
diff --git a/tests/unit/test_models.py b/tests/unit/test_models.py
index 09f4aaf..1a1e5db 100644
--- a/tests/unit/test_models.py
+++ b/tests/unit/test_models.py
@@ -1,4 +1,18 @@
-from sidestage.models import CharacterModel, LocationModel, ItemModel
+from datetime import datetime, timezone
+
+from sidestage.models import (
+    CharacterModel,
+    EntityModel,
+    EventModel,
+    EventType,
+    ItemModel,
+    LocationModel,
+    SceneModel,
+    Visibility,
+)
+
+
+# --- Existing tests ---
 
 def test_character_model():
     char = CharacterModel(id="test", name="Test", body="Test body")
@@ -14,3 +28,222 @@ def test_item_model():
     item = ItemModel(id="test", name="Test", body="Test body")
     assert item.name == "Test"
     assert item.body == "Test body"
+
+
+# --- EventType Enum ---
+
+def test_event_type_enum_values():
+    """EventType enum has all expected values with legacy-compatible string values."""
+    assert EventType.CHAT_MESSAGE == "ChatMessage"
+    assert EventType.JOIN == "JoinEvent"
+    assert EventType.LEAVE == "LeaveEvent"
+    assert EventType.ADJUST_GAMETIME == "AdjustGametime"
+    assert EventType.ERROR == "Error"
+
+
+def test_event_type_is_str_enum():
+    """EventType values are strings (str, Enum mixin)."""
+    for member in EventType:
+        assert isinstance(member.value, str)
+
+
+def test_visibility_enum_values():
+    """Visibility enum has PUBLIC, GM_ONLY, PRIVATE."""
+    assert Visibility.PUBLIC == "public"
+    assert Visibility.GM_ONLY == "gm_only"
+    assert Visibility.PRIVATE == "private"
+
+
+# --- Flattened EventModel ---
+
+def test_event_model_entity_type_is_classvar():
+    """entity_type is a ClassVar set to 'Event', not an instance field."""
+    event = EventModel(
+        id="evt_test1",
+        name="Test Message",
+        body="hello",
+        event_type=EventType.CHAT_MESSAGE,
+        scene_id="scene_1",
+        gametime=0,
+        walltime=datetime.now(timezone.utc),
+    )
+    assert EventModel.entity_type == "Event"
+    dumped = event.model_dump()
+    assert "entity_type" not in dumped
+
+
+def test_event_model_event_type_is_instance_field():
+    """event_type is a per-instance discriminator field."""
+    event = EventModel(
+        id="evt_test2",
+        name="Test Message",
+        body="hello",
+        event_type=EventType.CHAT_MESSAGE,
+        scene_id="scene_1",
+        gametime=0,
+        walltime=datetime.now(timezone.utc),
+    )
+    assert event.event_type == EventType.CHAT_MESSAGE
+    dumped = event.model_dump()
+    assert "event_type" in dumped
+    assert dumped["event_type"] == "ChatMessage"
+
+
+def test_event_model_inherits_entity_model():
+    """EventModel has id, name, body fields from EntityModel."""
+    event = EventModel(
+        id="evt_test3",
+        name="Alice Message",
+        body="hello world",
+        event_type=EventType.CHAT_MESSAGE,
+        scene_id="scene_1",
+        gametime=100,
+        walltime=datetime.now(timezone.utc),
+    )
+    assert event.id == "evt_test3"
+    assert event.name == "Alice Message"
+    assert event.body == "hello world"
+
+
+def test_event_model_defaults():
+    """EventModel defaults: visibility=PUBLIC, body='', metadata={}."""
+    event = EventModel(
+        id="evt_test4",
+        name="Test",
+        event_type=EventType.JOIN,
+        scene_id="scene_1",
+        gametime=0,
+        walltime=datetime.now(timezone.utc),
+    )
+    assert event.visibility == Visibility.PUBLIC
+    assert event.body == ""
+    assert event.metadata == {}
+
+
+def test_event_model_with_all_fields():
+    """EventModel with character_id, actor_id, metadata, visibility set."""
+    now = datetime.now(timezone.utc)
+    event = EventModel(
+        id="evt_test5",
+        name="Bob Message",
+        body="some text",
+        event_type=EventType.CHAT_MESSAGE,
+        scene_id="scene_2",
+        gametime=500,
+        walltime=now,
+        character_id="char_bob",
+        actor_id="user",
+        metadata={"widget": {"type": "entity_card"}},
+        visibility=Visibility.GM_ONLY,
+    )
+    assert event.character_id == "char_bob"
+    assert event.actor_id == "user"
+    assert event.metadata == {"widget": {"type": "entity_card"}}
+    assert event.visibility == Visibility.GM_ONLY
+
+
+def test_event_model_serialization():
+    """model_dump() includes event_type, excludes entity_type ClassVar."""
+    now = datetime.now(timezone.utc)
+    event = EventModel(
+        id="evt_test6",
+        name="Test",
+        body="",
+        event_type=EventType.ERROR,
+        scene_id="scene_1",
+        gametime=0,
+        walltime=now,
+    )
+    dumped = event.model_dump()
+    assert dumped["event_type"] == "Error"
+    assert "entity_type" not in dumped
+
+
+def test_event_model_walltime_serialization():
+    """walltime datetime serializes to ISO string in model_dump(mode='json')."""
+    now = datetime.now(timezone.utc)
+    event = EventModel(
+        id="evt_test7",
+        name="Test",
+        event_type=EventType.CHAT_MESSAGE,
+        scene_id="scene_1",
+        gametime=0,
+        walltime=now,
+    )
+    dumped = event.model_dump(mode="json")
+    assert isinstance(dumped["walltime"], str)
+
+
+def test_event_model_each_event_type():
+    """EventModel can be instantiated with each EventType value."""
+    now = datetime.now(timezone.utc)
+    for et in EventType:
+        event = EventModel(
+            id=f"evt_{et.value}",
+            name=f"Test {et.value}",
+            event_type=et,
+            scene_id="scene_1",
+            gametime=0,
+            walltime=now,
+        )
+        assert event.event_type == et
+
+
+# --- Deleted Subclasses ---
+
+def test_deleted_subclasses_not_importable():
+    """ChatMessageModel, JoinEventModel, LeaveEventModel, FastForwardEventModel are removed."""
+    import sidestage.models as m
+    assert not hasattr(m, "ChatMessageModel")
+    assert not hasattr(m, "JoinEventModel")
+    assert not hasattr(m, "LeaveEventModel")
+    assert not hasattr(m, "FastForwardEventModel")
+
+
+# --- SceneModel Changes ---
+
+def test_scene_model_no_messages_field():
+    """SceneModel no longer has a 'messages' field."""
+    scene = SceneModel(
+        id="scene_1",
+        name="Test Scene",
+        body="",
+    )
+    assert "messages" not in SceneModel.model_fields
+
+
+def test_scene_model_has_events_field():
+    """SceneModel still has 'events' field (list of event IDs)."""
+    scene = SceneModel(
+        id="scene_1",
+        name="Test Scene",
+        body="",
+        events=["evt_1", "evt_2"],
+    )
+    assert scene.events == ["evt_1", "evt_2"]
+
+
+# --- CharacterModel Changes ---
+
+def test_character_model_owner_default():
+    """CharacterModel.owner defaults to 'npc'."""
+    char = CharacterModel(id="char_1", name="Test", body="")
+    assert char.owner == "npc"
+
+
+def test_character_model_system_actor_default():
+    """CharacterModel.system_actor defaults to False."""
+    char = CharacterModel(id="char_1", name="Test", body="")
+    assert char.system_actor is False
+
+
+def test_character_model_player_owned():
+    """CharacterModel with owner set to a user ID (player character)."""
+    char = CharacterModel(id="char_1", name="Player", body="", owner="user-123")
+    assert char.owner == "user-123"
+
+
+def test_character_model_system_actor_true():
+    """CharacterModel with system_actor=True (Co-Author character)."""
+    char = CharacterModel(id="char_co_author", name="Co-Author", body="", system_actor=True)
+    assert char.system_actor is True
diff --git a/tests/unit/test_schemas.py b/tests/unit/test_schemas.py
new file mode 100644
index 0000000..69809c9
--- /dev/null
+++ b/tests/unit/test_schemas.py
@@ -0,0 +1,23 @@
+from datetime import datetime, timezone
+
+from sidestage.models import EventModel, EventType
+from sidestage.schemas import ChatResponse
+
+
+def test_chat_response_references_event_model():
+    """ChatResponse schema references EventModel, not ChatMessageModel."""
+    now = datetime.now(timezone.utc)
+    event = EventModel(
+        id="evt_1",
+        name="Test Message",
+        body="hello",
+        event_type=EventType.CHAT_MESSAGE,
+        scene_id="scene_1",
+        gametime=0,
+        walltime=now,
+        character_id="char_1",
+        actor_id="user",
+    )
+    resp = ChatResponse(event=event)
+    assert resp.event.id == "evt_1"
+    assert resp.event.event_type == EventType.CHAT_MESSAGE
