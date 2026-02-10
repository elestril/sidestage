I now have all the context I need. Let me generate the section content.

# Section 01: Event Model Restructuring and Event Wrapper

## Overview

This section implements the foundational type changes that all other sections depend on. It covers:

1. **EventType and Visibility enums** -- new discriminator enums in `models.py`
2. **Flattened EventModel** -- replacing 4 subclasses (`ChatMessageModel`, `JoinEventModel`, `LeaveEventModel`, `FastForwardEventModel`) with a single `EventModel` class using an `event_type` instance field
3. **SceneModel changes** -- removing the embedded `messages` field
4. **CharacterModel changes** -- adding `owner` and `system_actor` fields
5. **Schema updates** -- updating `ChatResponse` in `schemas.py`
6. **Event runtime wrapper** -- new `Event` class in `src/sidestage/event.py` carrying OpenTelemetry span context
7. **EventQueue update** -- changing the queue type from `EventModel` to `Event`

No downstream consumers (Scene, Character, storage, etc.) are updated here. Those are handled in later sections. This section focuses exclusively on the data model layer and the `Event` wrapper.

---

## Files to Create

- `/home/harald/src/sidestage/src/sidestage/event.py` -- new file for the `Event` wrapper class and relocated `EventQueue`
- `/home/harald/src/sidestage/tests/unit/test_event.py` -- new test file for Event wrapper and EventQueue

## Files to Modify

- `/home/harald/src/sidestage/src/sidestage/models.py` -- add enums, flatten EventModel, update SceneModel and CharacterModel
- `/home/harald/src/sidestage/src/sidestage/schemas.py` -- update ChatResponse to reference EventModel
- `/home/harald/src/sidestage/tests/unit/test_models.py` -- extend with EventModel, enum, and CharacterModel tests

## Files NOT Modified Yet (Downstream -- Later Sections)

- `bus.py` -- deleted in section-04 (EventQueue moves to `event.py`)
- `scene.py`, `character.py`, `orchestrator.py`, `campaign.py`, `storage.py`, etc. -- updated in later sections
- These files still import the old types and will break until their respective sections are implemented. That is expected.

---

## Tests First

### Test file: `/home/harald/src/sidestage/tests/unit/test_models.py`

Extend the existing test file with tests for the new enums, flattened EventModel, SceneModel changes, and CharacterModel changes.

```python
from datetime import datetime, timezone

from sidestage.models import (
    EventType,
    Visibility,
    EventModel,
    CharacterModel,
    SceneModel,
)


# --- 2.1 EventType Enum ---

def test_event_type_enum_values():
    """EventType enum has all expected values with legacy-compatible string values."""
    assert EventType.CHAT_MESSAGE == "ChatMessage"
    assert EventType.JOIN == "JoinEvent"
    assert EventType.LEAVE == "LeaveEvent"
    assert EventType.ADJUST_GAMETIME == "AdjustGametime"
    assert EventType.ERROR == "Error"


def test_event_type_is_str_enum():
    """EventType values are strings (str, Enum mixin)."""
    for member in EventType:
        assert isinstance(member.value, str)


def test_visibility_enum_values():
    """Visibility enum has PUBLIC, GM_ONLY, PRIVATE."""
    assert Visibility.PUBLIC == "public"
    assert Visibility.GM_ONLY == "gm_only"
    assert Visibility.PRIVATE == "private"


# --- 2.2 Flattened EventModel ---

def test_event_model_entity_type_is_classvar():
    """entity_type is a ClassVar set to 'Event', not an instance field."""
    event = EventModel(
        id="evt_test1",
        name="Test Message",
        body="hello",
        event_type=EventType.CHAT_MESSAGE,
        scene_id="scene_1",
        gametime=0,
        walltime=datetime.now(timezone.utc),
    )
    assert EventModel.entity_type == "Event"
    # entity_type should NOT appear in model_dump output (it's a ClassVar)
    dumped = event.model_dump()
    assert "entity_type" not in dumped


def test_event_model_event_type_is_instance_field():
    """event_type is a per-instance discriminator field."""
    event = EventModel(
        id="evt_test2",
        name="Test Message",
        body="hello",
        event_type=EventType.CHAT_MESSAGE,
        scene_id="scene_1",
        gametime=0,
        walltime=datetime.now(timezone.utc),
    )
    assert event.event_type == EventType.CHAT_MESSAGE
    dumped = event.model_dump()
    assert "event_type" in dumped
    assert dumped["event_type"] == "ChatMessage"


def test_event_model_inherits_entity_model():
    """EventModel has id, name, body fields from EntityModel."""
    event = EventModel(
        id="evt_test3",
        name="Alice Message",
        body="hello world",
        event_type=EventType.CHAT_MESSAGE,
        scene_id="scene_1",
        gametime=100,
        walltime=datetime.now(timezone.utc),
    )
    assert event.id == "evt_test3"
    assert event.name == "Alice Message"
    assert event.body == "hello world"


def test_event_model_defaults():
    """EventModel defaults: visibility=PUBLIC, body='', metadata={}."""
    event = EventModel(
        id="evt_test4",
        name="Test",
        event_type=EventType.JOIN,
        scene_id="scene_1",
        gametime=0,
        walltime=datetime.now(timezone.utc),
    )
    assert event.visibility == Visibility.PUBLIC
    assert event.body == ""
    assert event.metadata == {}


def test_event_model_with_all_fields():
    """EventModel with character_id, actor_id, metadata, visibility set."""
    now = datetime.now(timezone.utc)
    event = EventModel(
        id="evt_test5",
        name="Bob Message",
        body="some text",
        event_type=EventType.CHAT_MESSAGE,
        scene_id="scene_2",
        gametime=500,
        walltime=now,
        character_id="char_bob",
        actor_id="user",
        metadata={"widget": {"type": "entity_card"}},
        visibility=Visibility.GM_ONLY,
    )
    assert event.character_id == "char_bob"
    assert event.actor_id == "user"
    assert event.metadata == {"widget": {"type": "entity_card"}}
    assert event.visibility == Visibility.GM_ONLY


def test_event_model_serialization():
    """model_dump() includes event_type, excludes entity_type ClassVar."""
    now = datetime.now(timezone.utc)
    event = EventModel(
        id="evt_test6",
        name="Test",
        body="",
        event_type=EventType.ERROR,
        scene_id="scene_1",
        gametime=0,
        walltime=now,
    )
    dumped = event.model_dump()
    assert dumped["event_type"] == "Error"
    assert "entity_type" not in dumped


def test_event_model_walltime_serialization():
    """walltime datetime serializes to ISO string in model_dump(mode='json')."""
    now = datetime.now(timezone.utc)
    event = EventModel(
        id="evt_test7",
        name="Test",
        event_type=EventType.CHAT_MESSAGE,
        scene_id="scene_1",
        gametime=0,
        walltime=now,
    )
    dumped = event.model_dump(mode="json")
    # Should be an ISO format string
    assert isinstance(dumped["walltime"], str)


def test_event_model_each_event_type():
    """EventModel can be instantiated with each EventType value."""
    now = datetime.now(timezone.utc)
    for et in EventType:
        event = EventModel(
            id=f"evt_{et.value}",
            name=f"Test {et.value}",
            event_type=et,
            scene_id="scene_1",
            gametime=0,
            walltime=now,
        )
        assert event.event_type == et


# --- 2.3 Deleted Subclasses ---

def test_deleted_subclasses_not_importable():
    """ChatMessageModel, JoinEventModel, LeaveEventModel, FastForwardEventModel are removed."""
    import sidestage.models as m
    assert not hasattr(m, "ChatMessageModel")
    assert not hasattr(m, "JoinEventModel")
    assert not hasattr(m, "LeaveEventModel")
    assert not hasattr(m, "FastForwardEventModel")


# --- 2.4 SceneModel Changes ---

def test_scene_model_no_messages_field():
    """SceneModel no longer has a 'messages' field."""
    scene = SceneModel(
        id="scene_1",
        name="Test Scene",
        body="",
    )
    assert not hasattr(scene, "messages") or "messages" not in SceneModel.model_fields


def test_scene_model_has_events_field():
    """SceneModel still has 'events' field (list of event IDs)."""
    scene = SceneModel(
        id="scene_1",
        name="Test Scene",
        body="",
        events=["evt_1", "evt_2"],
    )
    assert scene.events == ["evt_1", "evt_2"]


# --- 2.5 CharacterModel Changes ---

def test_character_model_owner_default():
    """CharacterModel.owner defaults to 'npc'."""
    char = CharacterModel(id="char_1", name="Test", body="")
    assert char.owner == "npc"


def test_character_model_system_actor_default():
    """CharacterModel.system_actor defaults to False."""
    char = CharacterModel(id="char_1", name="Test", body="")
    assert char.system_actor is False


def test_character_model_player_owned():
    """CharacterModel with owner set to a user ID (player character)."""
    char = CharacterModel(id="char_1", name="Player", body="", owner="user-123")
    assert char.owner == "user-123"


def test_character_model_system_actor_true():
    """CharacterModel with system_actor=True (Co-Author character)."""
    char = CharacterModel(id="char_co_author", name="Co-Author", body="", system_actor=True)
    assert char.system_actor is True
```

### Test file: `/home/harald/src/sidestage/tests/unit/test_schemas.py`

A small test (create if needed, or add to existing) for the updated ChatResponse.

```python
from sidestage.schemas import ChatResponse
from sidestage.models import EventModel, EventType
from datetime import datetime, timezone


def test_chat_response_references_event_model():
    """ChatResponse schema references EventModel, not ChatMessageModel."""
    now = datetime.now(timezone.utc)
    event = EventModel(
        id="evt_1",
        name="Test Message",
        body="hello",
        event_type=EventType.CHAT_MESSAGE,
        scene_id="scene_1",
        gametime=0,
        walltime=now,
        character_id="char_1",
        actor_id="user",
    )
    resp = ChatResponse(event=event)
    assert resp.event.id == "evt_1"
    assert resp.event.event_type == EventType.CHAT_MESSAGE
```

### Test file: `/home/harald/src/sidestage/tests/unit/test_event.py` (new)

Tests for the `Event` wrapper class and the updated `EventQueue`.

```python
import asyncio
from datetime import datetime, timezone

import pytest

from sidestage.models import EventModel, EventType
from sidestage.event import Event, EventQueue


def _make_event_model(**overrides) -> EventModel:
    """Helper to create an EventModel with sensible defaults."""
    defaults = dict(
        id="evt_test",
        name="Test",
        body="",
        event_type=EventType.CHAT_MESSAGE,
        scene_id="scene_1",
        gametime=0,
        walltime=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return EventModel(**defaults)


# --- 3.1-3.2 Event Wrapper ---

def test_event_wraps_event_model():
    """Event wraps an EventModel instance."""
    model = _make_event_model()
    event = Event(model=model)
    assert event.model is model


def test_event_is_not_pydantic():
    """Event is a plain class, not a Pydantic model."""
    from pydantic import BaseModel
    assert not issubclass(Event, BaseModel)


def test_event_span_context_defaults_none():
    """Event.span_context defaults to None."""
    event = Event(model=_make_event_model())
    assert event.span_context is None


def test_event_scene_defaults_none():
    """Event.scene defaults to None."""
    event = Event(model=_make_event_model())
    assert event.scene is None


def test_event_character_returns_none_when_scene_none():
    """Event.character returns None when scene is not set."""
    model = _make_event_model(character_id="char_1")
    event = Event(model=model)
    assert event.character is None


def test_event_character_returns_none_when_character_id_none():
    """Event.character returns None when model.character_id is None."""
    model = _make_event_model(character_id=None)
    event = Event(model=model)
    event.scene = type("FakeScene", (), {"characters": {}})()
    assert event.character is None


def test_event_character_looks_up_from_scene():
    """Event.character looks up character from scene.characters dict."""
    model = _make_event_model(character_id="char_alice")
    event = Event(model=model)
    fake_char = object()  # stand-in for Character instance
    event.scene = type("FakeScene", (), {"characters": {"char_alice": fake_char}})()
    assert event.character is fake_char


# --- 3.3 Factory ---

def test_event_from_model_creates_event():
    """Event.from_model() creates an Event from an EventModel."""
    model = _make_event_model()
    event = Event.from_model(model)
    assert isinstance(event, Event)
    assert event.model is model


def test_event_from_model_scene_is_none():
    """Event.from_model() does NOT set scene reference."""
    model = _make_event_model()
    event = Event.from_model(model)
    assert event.scene is None


def test_event_from_model_span_context_none_without_active_span():
    """Event.from_model() sets span_context=None when no active span."""
    model = _make_event_model()
    event = Event.from_model(model)
    assert event.span_context is None


# --- 3.4 Queue Integration ---

@pytest.mark.asyncio
async def test_event_queue_accepts_event_objects():
    """EventQueue accepts Event objects (not raw EventModel)."""
    received = []

    async def handler(event: Event):
        received.append(event)

    queue = EventQueue()
    await queue.start(handler)

    model = _make_event_model()
    event = Event.from_model(model)
    await queue.put(event)

    # Give the worker time to process
    await asyncio.sleep(0.05)
    await queue.stop()

    assert len(received) == 1
    assert received[0] is event
    assert isinstance(received[0], Event)


@pytest.mark.asyncio
async def test_event_queue_handler_receives_event_objects():
    """EventQueue handler receives Event (not EventModel)."""
    received_types = []

    async def handler(event: Event):
        received_types.append(type(event).__name__)

    queue = EventQueue()
    await queue.start(handler)
    await queue.put(Event.from_model(_make_event_model()))
    await asyncio.sleep(0.05)
    await queue.stop()

    assert received_types == ["Event"]


@pytest.mark.asyncio
async def test_event_queue_start_stop_lifecycle():
    """EventQueue start/stop lifecycle works with Event type."""
    queue = EventQueue()

    async def handler(event: Event):
        pass

    await queue.start(handler)
    assert queue._running is True
    await queue.stop()
    assert queue._running is False
```

---

## Implementation Details

### 1. EventType and Visibility Enums

**File:** `/home/harald/src/sidestage/src/sidestage/models.py`

Add two new enums at the top of the file (after imports, before the domain models):

```python
from enum import Enum

class EventType(str, Enum):
    CHAT_MESSAGE = "ChatMessage"
    JOIN = "JoinEvent"
    LEAVE = "LeaveEvent"
    ADJUST_GAMETIME = "AdjustGametime"
    ERROR = "Error"

class Visibility(str, Enum):
    PUBLIC = "public"
    GM_ONLY = "gm_only"
    PRIVATE = "private"
```

The `EventType` values are deliberately chosen to match the old `entity_type` strings for `ChatMessage` and `JoinEvent`/`LeaveEvent` so that any residual compatibility (graph labels, serialization) is easier to maintain.

### 2. Flatten EventModel

**File:** `/home/harald/src/sidestage/src/sidestage/models.py`

Replace the current `EventModel` and its 4 subclasses with a single class:

```python
from datetime import datetime
from pydantic import ConfigDict

class EventModel(EntityModel):
    model_config = ConfigDict(extra="ignore")  # Safety net for stale graph properties

    entity_type: ClassVar[str] = "Event"

    event_type: EventType
    scene_id: str
    gametime: int = Field(..., description="Gametime in seconds when the event occurred")
    walltime: datetime = Field(..., description="Real-world timestamp")
    character_id: Optional[str] = None
    actor_id: Optional[str] = None
    body: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    visibility: Visibility = Visibility.PUBLIC
```

Key points:
- `entity_type` remains a `ClassVar[str] = "Event"` -- consistent with all other EntityModel subclasses.
- `event_type` is the per-instance discriminator -- this is what distinguishes a chat message from a join event.
- `walltime` changes from `str` to `datetime`. Pydantic automatically serializes to ISO format in JSON mode.
- `body` overrides the inherited `body` from `EntityModel`. For `CHAT_MESSAGE` events, this holds the message text. For `ERROR` events, error details. For other types, it can be empty.
- `metadata: Dict[str, Any]` replaces the old `widget` field. Structured data for mechanics/widgets goes here.
- `model_config = ConfigDict(extra="ignore")` is a safety net: if old graph nodes have extra properties (like `message` from `ChatMessageModel`), they are silently ignored instead of causing validation errors.

**`name` field convention** (inherited from EntityModel, required):
- `CHAT_MESSAGE`: `"{character_name} Message"`
- `JOIN`/`LEAVE`: `"{character_name} Joins"` / `"{character_name} Leaves"`
- `ADJUST_GAMETIME`: `"Time Adjustment"`
- `ERROR`: `"Error"`

### 3. Delete Subclasses

**File:** `/home/harald/src/sidestage/src/sidestage/models.py`

Remove these class definitions entirely:
- `ChatMessageModel` (lines 63-105 in current file)
- `JoinEventModel` (lines 108-111)
- `LeaveEventModel` (lines 114-117)
- `FastForwardEventModel` (lines 120-126)

The `backfill_legacy_fields` model_validator from `ChatMessageModel` is no longer needed. Old data formats are not supported (clean break, section 10.5 of the plan).

### 4. SceneModel Changes

**File:** `/home/harald/src/sidestage/src/sidestage/models.py`

Remove the `messages` field from `SceneModel`. The `events: List[str]` field (list of event IDs) remains and becomes the sole tracking mechanism.

Current:
```python
class SceneModel(EntityModel):
    ...
    events: List[str] = Field(default_factory=list, ...)
    messages: List[ChatMessageModel] = Field(default_factory=list, ...)  # REMOVE THIS
```

After:
```python
class SceneModel(EntityModel):
    entity_type: ClassVar[str] = "Scene"

    current_gametime: Optional[int] = Field(default=None, ...)
    location_id: Optional[str] = Field(default=None, ...)
    events: List[str] = Field(default_factory=list, description="IDs of events in this scene")
    # messages field removed -- events are tracked by ID only
```

### 5. CharacterModel Changes

**File:** `/home/harald/src/sidestage/src/sidestage/models.py`

Add two new fields to `CharacterModel`:

```python
class CharacterModel(EntityModel):
    entity_type: ClassVar[str] = "Character"

    unseen: bool = Field(default=False, ...)
    location_id: Optional[str] = Field(default=None, ...)
    inventory: List[str] = Field(default_factory=list, ...)
    owner: str = Field(default="npc", description="'npc' for NPC characters, a user_id string for player characters")
    system_actor: bool = Field(default=False, description="True for the Campaign Co-Author character")
```

Both fields have safe defaults (`"npc"` and `False`), so existing CharacterModel data without these fields will still load correctly.

### 6. Update Schemas

**File:** `/home/harald/src/sidestage/src/sidestage/schemas.py`

Change the import and `ChatResponse` class:

Before:
```python
from sidestage.models import ChatMessageModel

class ChatResponse(BaseModel):
    user_message: ChatMessageModel
    agent_message: Optional[ChatMessageModel] = None
```

After:
```python
from sidestage.models import EventModel

class ChatResponse(BaseModel):
    event: EventModel  # The created user event; agent response arrives async via WebSocket
```

The schema changes from returning `user_message`/`agent_message` pair to returning a single `event`. Agent responses are no longer synchronous -- they arrive asynchronously via WebSocket dispatch. The `WebSocketMessage` schema may also need minor updates but can be addressed when the orchestrator is refactored in section-06.

### 7. Event Runtime Wrapper

**New file:** `/home/harald/src/sidestage/src/sidestage/event.py`

This file contains two things:
1. The `Event` wrapper class (runtime context, not persisted)
2. The `EventQueue` (relocated from `bus.py`, updated to use `Event` type)

The `Event` class is a plain dataclass (or attrs-style class), NOT a Pydantic model. It wraps an `EventModel` with:
- `span_context`: OpenTelemetry span context captured at creation time
- `scene`: back-reference to the Scene, set when the event enters processing
- `character` property: convenience lookup via `scene.characters`

```python
"""Runtime event wrapper and async event queue.

The Event class carries an EventModel plus runtime context (tracing, scene
reference) that should NOT be persisted. The EventQueue processes Event
objects sequentially through a handler callback.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

from opentelemetry import trace

from sidestage.models import EventModel

if TYPE_CHECKING:
    from opentelemetry.trace import SpanContext

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Runtime event wrapper carrying model data, tracing context, and scene reference."""

    model: EventModel
    span_context: SpanContext | None = None
    scene: object | None = field(default=None, repr=False)  # Set by Scene.process()

    @property
    def character(self):
        """Look up the originating Character via the scene's character registry."""
        if self.scene and self.model.character_id:
            characters = getattr(self.scene, "characters", {})
            return characters.get(self.model.character_id)
        return None

    @classmethod
    def from_model(cls, model: EventModel) -> Event:
        """Create an Event from an EventModel, capturing the current span context."""
        span = trace.get_current_span()
        ctx = span.get_span_context() if span else None
        # Only store valid (non-invalid) span contexts
        if ctx and not ctx.is_valid:
            ctx = None
        return cls(model=model, span_context=ctx)


# Type alias for the event handler callback
EventHandler = Callable[[Event], Awaitable[None]]


class EventQueue:
    """Async event queue for sequential event processing.

    Events (Event wrappers, not raw EventModel) are processed one at a time
    by a single handler callback. No subscriptions, no hooks.
    """

    def __init__(self):
        self.queue: asyncio.Queue[Event] = asyncio.Queue()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self, handler: EventHandler) -> None:
        """Start the background worker with the given handler."""
        ...

    async def stop(self) -> None:
        """Stop the background worker."""
        ...

    async def put(self, event: Event) -> None:
        """Add an event to the queue."""
        ...

    async def _worker(self, handler: EventHandler) -> None:
        """Background loop: pull events and pass to handler."""
        ...
```

The `start`, `stop`, `put`, and `_worker` methods follow the same pattern as the existing `EventQueue` in `/home/harald/src/sidestage/src/sidestage/bus.py`, but with the type changed from `EventModel` to `Event`. The implementation logic (create_task, cancel, queue.get, task_done) is identical.

### 8. Relationship to bus.py

The existing `/home/harald/src/sidestage/src/sidestage/bus.py` is NOT deleted in this section. It will be deleted in section-04 (Scene Event Loop Refactor) when all consumers are migrated. During this transitional period, both `bus.py` (old) and `event.py` (new) exist. Downstream code in `scene.py` and `campaign.py` still references `bus.EventQueue` until section-04 migrates them.

---

## Design Decisions and Rationale

**Why `datetime` for `walltime` instead of `str`?** The old EventModel used `str` for walltime (ISO format). Changing to `datetime` provides type safety and lets Pydantic handle serialization automatically. When serialized via `model_dump(mode="json")`, it produces an ISO string. For graph storage (section-03), explicit ISO string conversion is needed.

**Why `ConfigDict(extra="ignore")`?** This is a safety net for the clean-break migration. If old graph nodes contain properties like `message` (from `ChatMessageModel`) or `duration_str` (from `FastForwardEventModel`), Pydantic will silently ignore them instead of raising validation errors. This reduces the blast radius if the graph is not fully wiped.

**Why keep `body` with a default of `""`?** The `body` field serves different purposes depending on `event_type`: message text for `CHAT_MESSAGE`, error details for `ERROR`, empty for `JOIN`/`LEAVE`. Making it optional with a default of `""` means callers don't need to specify it for event types where body is irrelevant.

**Why is `Event` a `dataclass` and not Pydantic?** The `Event` wrapper is purely a runtime object. It carries references to live objects (`scene`, `span_context`) that cannot and should not be serialized. Using a plain `dataclass` makes this distinction clear and avoids accidentally trying to serialize it.

**Why does `Event.from_model()` not set `scene`?** The scene reference is set later by `Scene.process()` when the event enters processing. At creation time, the event may not yet be associated with any scene (e.g., it could be created by an HTTP handler before being routed to a scene).

---

## Downstream Impact Summary

After this section is complete, the following imports will be broken (to be fixed in later sections):

| File | Broken Import | Fixed In |
|------|--------------|----------|
| `scene.py` | `ChatMessageModel` | section-04 |
| `character.py` | `ChatMessageModel` | section-02 |
| `orchestrator.py` | `ChatMessageModel`, `SyncManager` | section-06 |
| `campaign.py` | various | section-06 |
| `storage.py` | `ChatMessageModel` | section-03 |
| `migration/serialization.py` | old model classes | section-03 |
| `migration/importer.py` | old model classes | section-03 |
| `mcp_bridge.py` | `ChatMessageModel` | section-06 |
| `tests/` | old model references | section-08 |

This is expected and by design. Each section fixes the imports relevant to its scope.

---

## Implementation Notes

**Additional files modified (not in original plan):**

- `graph/entities.py` — Updated `LABEL_TO_MODEL`, `MODEL_TO_LABELS`, and `EXCLUDED_FIELDS` registries. Removed old subclass mappings. Added `EventModel: {"metadata"}` to `EXCLUDED_FIELDS` to prevent nested dicts being written to FalkorDB. This was necessary because the conftest import chain (`conftest.py → config → graph → graph/entities.py`) blocked ALL test execution.
- `graph/queries.py` — Updated stale docstring in `scene_events()` that referenced ChatMessage subtype.

**`EntityModel.body` default changed to `""`:** The plan only discussed `body: str = ""` for EventModel, but since EventModel inherits from EntityModel and overrides `body`, the default was applied at the EntityModel level for consistency. All entity types now accept empty body by default (user confirmed this is acceptable).

**Async tests use `@pytest.mark.anyio`** with `anyio_backend` fixture restricted to asyncio (project uses pytest-anyio, not pytest-asyncio as the plan specified).

**35 tests total:** 21 in test_models.py, 1 in test_schemas.py, 13 in test_event.py (3 async).