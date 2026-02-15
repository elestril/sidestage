Now I have all the context I need. Let me generate the section content.

# Section 04: Scene Event Loop Refactor

## Overview

This section redesigns the Scene event loop to work with the new Actor system introduced in section-02. The key changes are:

1. Move `EventQueue` from `bus.py` into `event.py` (consolidation, then delete `bus.py`)
2. Simplify `Scene.__init__` -- remove the `agent: LiteLLMAgent` parameter (actors manage their own agents)
3. Refactor `Scene.activate()` to obtain Characters via `Campaign.get_character()`
4. Add `Scene.process(event)` as the public entry point that sets the scene reference and enqueues
5. Rewrite `Scene._process_event()` to persist, then dispatch to ALL actors (not just NPCs)
6. Add `Scene._dispatch()` with actor_id deduplication and thinking indicator lifecycle
7. Replace `create_message()` with `create_event()` factory using `evt_` prefix
8. Replace `Scene.chat(user_message: ChatMessageModel)` with `Scene.chat(actor_id, text, character_id)`

**Dependencies:** This section depends on section-01-event-model (EventModel, EventType, Event wrapper, EventQueue type change) and section-02-actors (Actor hierarchy, Character wrapper, Campaign character registry). Those must be implemented first.

**Blocked by this section:** section-05-tracing (span linking in `_process_event`), section-06-orchestrator (WebSocket integration and API changes).

---

## Files to Modify/Create

| File | Action |
|------|--------|
| `src/sidestage/event.py` | Modify -- add `EventQueue` class (moved from `bus.py`) |
| `src/sidestage/bus.py` | Delete |
| `src/sidestage/scene.py` | Major rewrite |
| `tests/unit/test_scene.py` | Create (new test file) |

---

## Tests First

**Test file:** `tests/unit/test_scene.py` (new file)

All tests are async. The test fixtures should create minimal mocks for dependencies (Storage, Campaign, GraphClient). The `Event` and `EventModel` types come from section-01, and `Actor`, `NPCActor`, `User`, `Character` from section-02.

### Test: Scene.process()

```python
# Test: Scene.process() sets event.scene = self before enqueueing
# Create a Scene instance with a mock queue. Call process(event).
# Assert event.scene is the scene instance.
# Assert the event was put on the queue.

# Test: Scene.process() puts event on the queue
# Create a Scene with a started EventQueue. Call process(event).
# Assert queue.put was called with the event.
```

### Test: Scene._process_event()

```python
# Test: _process_event() persists EventModel to storage
# Create a Scene with a mock storage. Process a CHAT_MESSAGE event.
# Assert storage.update_scene() or equivalent persistence method was called.

# Test: _process_event() creates graph node for the event
# Create a Scene with a mock graph_client. Process an event.
# Assert graph create_entity was called with the event model.
# Assert graph link was called to connect scene -> event.

# Test: _process_event() calls _dispatch() for all event types
# Process events of each EventType. Assert _dispatch() was called for each.

# Test: _process_event() updates current_gametime for ADJUST_GAMETIME events
# Create a Scene. Process an ADJUST_GAMETIME event with gametime=3600.
# Assert scene.data.current_gametime == 3600.

# Test: _process_event() does NOT update gametime for other event types
# Create a Scene with current_gametime=100. Process a CHAT_MESSAGE event with gametime=200.
# Assert scene.data.current_gametime is still 100 (unchanged).
```

### Test: Scene._dispatch()

```python
# Test: _dispatch() calls process() on every present actor
# Create a Scene with 3 characters (2 NPCs, 1 User). Dispatch an event.
# Assert actor.process() was called on all 3 actors.

# Test: _dispatch() deduplicates by actor_id (same User controlling 2 characters dispatched once)
# Create a Scene with 2 characters sharing the same User actor.
# Dispatch an event. Assert User.process() was called exactly once.

# Test: _dispatch() sends thinking status to Users before calling NPCActor.process()
# Create a Scene with 1 NPC and 1 User character. Dispatch a user-originated CHAT_MESSAGE.
# Assert User.send() was called with {"type": "actor_status", "status": "thinking", ...}
# BEFORE NPCActor.process() was called.

# Test: _dispatch() sends idle status to Users after NPCActor.process() completes
# Same setup. Assert User.send() was called with {"type": "actor_status", "status": "idle", ...}
# AFTER NPCActor.process() returns.

# Test: _dispatch() sends idle status even when NPCActor.process() raises
# Mock NPCActor.process() to raise an exception. Dispatch an event.
# Assert idle status was still sent to Users (thinking indicator always clears).

# Test: _dispatch() does NOT send thinking status for User actors
# Create a Scene with only User actors. Dispatch an event.
# Assert no actor_status messages were sent.
```

### Test: Scene.create_event()

```python
# Test: create_event() returns Event wrapping EventModel
# Call scene.create_event(EventType.CHAT_MESSAGE, ...).
# Assert result is an Event instance. Assert result.model is an EventModel.

# Test: create_event() generates ID with evt_ prefix
# Call scene.create_event(). Assert result.model.id starts with "evt_".

# Test: create_event() sets scene_id, gametime, walltime, event_type
# Call scene.create_event(EventType.JOIN, actor_id="user").
# Assert result.model.scene_id == scene.id.
# Assert result.model.gametime == scene.data.current_gametime.
# Assert result.model.walltime is set (a datetime).
# Assert result.model.event_type == EventType.JOIN.
```

### Test: Scene.chat()

```python
# Test: chat() creates CHAT_MESSAGE event with given text and character_id
# Call scene.chat(actor_id="user", text="Hello", character_id="char_alice").
# Verify a CHAT_MESSAGE event was created with body="Hello" and character_id="char_alice".

# Test: chat() enqueues event via self.process()
# Mock scene.process(). Call scene.chat(...).
# Assert scene.process() was called with the created event.

# Test: chat() accepts raw parameters (actor_id, text, character_id)
# Verify the signature is chat(self, actor_id: str, text: str, character_id: str | None = None).
# No ChatMessageModel parameter.
```

---

## Implementation Details

### 1. EventQueue Consolidation

The `EventQueue` class currently lives in `src/sidestage/bus.py`. It must be moved into `src/sidestage/event.py`, alongside the `Event` wrapper class created in section-01.

After the move, delete `src/sidestage/bus.py`.

**Important type change (from section-01):** The queue type changes from `asyncio.Queue[EventModel]` to `asyncio.Queue[Event]`, and `EventHandler` becomes `Callable[[Event], Awaitable[None]]`. The `EventQueue` class body (start/stop/put/_worker pattern) remains the same -- only the type annotations change.

The `EventQueue` class should look like this after the move:

```python
# In src/sidestage/event.py (added to the file created in section-01)

EventHandler = Callable[[Event], Awaitable[None]]

class EventQueue:
    """A simple async event queue for a Scene.
    Events are processed sequentially by a single handler callback."""

    def __init__(self):
        self.queue: asyncio.Queue[Event] = asyncio.Queue()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self, handler: EventHandler) -> None:
        """Start the background worker with the given handler."""
        # Same logic as current bus.py

    async def stop(self) -> None:
        """Stop the background worker."""
        # Same logic as current bus.py

    async def put(self, event: Event) -> None:
        """Add an event to the queue."""
        # Same logic as current bus.py

    async def _worker(self, handler: EventHandler) -> None:
        """Background loop: pull events and pass to handler."""
        # Same logic as current bus.py
```

Update the import in `scene.py` from `from sidestage.bus import EventQueue` to `from sidestage.event import EventQueue`.

### 2. Scene.__init__ Changes

The Scene constructor simplifies significantly. Key changes:

- **Remove** the `agent: LiteLLMAgent` parameter. Actors manage their own LLM agents now. The Scene no longer holds a reference to an agent.
- **Add** a `campaign` parameter. Scene needs access to `Campaign.get_character()` for actor resolution and to `Campaign.user` for finding User actors during dispatch.
- **Remove** `_broadcast_fn` and `set_broadcast()`. There is no separate broadcast mechanism -- dispatching events to User actors IS the broadcast.
- The `characters` dict remains as `Dict[str, Character]` but now uses the refactored `Character` from section-02 (which pairs `CharacterModel` with an `Actor`).

New constructor signature:

```python
class Scene:
    def __init__(
        self,
        storage: Storage,
        data: SceneModel,
        campaign: "Campaign",
        graph_client: "GraphClient | None" = None,
        embed_config: "LLMConfig | None" = None,
        health: "CampaignHealth | None" = None,
        context_limit: int = 4096,
    ):
        self.storage = storage
        self.data = data
        self.campaign = campaign
        self.graph_client = graph_client
        self.embed_config = embed_config
        self.health = health
        self.context_limit = context_limit
        self.queue = EventQueue()
        self.characters: Dict[str, Character] = {}
        self._active = False
```

Note: `self.campaign` gives access to `campaign.user` (the User actor) and `campaign.get_character()` (the character registry). The `agent` parameter is gone.

### 3. Scene.activate()

The activation flow changes to use Campaign's character registry:

```python
async def activate(self) -> None:
    """Activate the scene: start event queue, load and activate characters."""
    if self._active:
        return

    await self.queue.start(self._process_event)

    # Load CharacterModels from graph or storage
    if self.graph_client is not None:
        from sidestage.graph import list_entities
        all_chars = await list_entities(self.graph_client, entity_type="Character")
    else:
        all_chars = self.storage.list_characters()

    # For each CharacterModel, get/create Character via Campaign registry
    for char_data in all_chars:
        character = self.campaign.get_character(cast(CharacterModel, char_data))
        self.characters[char_data.id] = character
        await character.activate()

    self._active = True
```

The key difference from the current code: instead of creating `Character` instances directly with all their dependencies, Scene calls `self.campaign.get_character(model)` which handles actor resolution (NPCActor vs User) and caching. The Character class from section-02 pairs the model with its actor.

### 4. Scene.process() -- Public Entry Point

This is a new method. It is the single public entry point for events entering the scene. Both external callers (Scene.chat, Orchestrator) and internal callers (NPCActor enqueuing responses) use this method.

```python
async def process(self, event: Event) -> None:
    """Enqueue an event into this scene's event loop."""
    event.scene = self
    await self.queue.put(event)
```

Setting `event.scene = self` is critical. It allows actors to enqueue response events by calling `event.scene.process(new_event)` from within their `process()` method. This is how NPCActor sends its LLM responses back into the event loop.

### 5. Scene._process_event() -- Queue Handler

This is the queue worker callback. It replaces the current `_process_event` method. For each event dequeued:

```python
async def _process_event(self, event: Event) -> None:
    """Queue worker handler. Persist, handle event-type-specific logic, dispatch."""
    # 1. Persist EventModel to storage and graph
    self.storage.add_event(event.model)
    if self.graph_client is not None:
        from sidestage.graph import create_entity, link
        try:
            await create_entity(self.graph_client, event.model)
            await link(self.graph_client, self.data.id, "HAS_EVENT", event.model.id)
            if event.model.character_id:
                await link(self.graph_client, event.model.id, "INVOLVES", event.model.character_id)
        except Exception:
            logger.exception("Failed to persist event %s to graph", event.model.id)

    # 2. Event-type-specific processing
    if event.model.event_type == EventType.ADJUST_GAMETIME:
        self.data.current_gametime = event.model.gametime

    # 3. Dispatch to all present actors
    await self._dispatch(event)
```

**Key differences from current code:**

- No `isinstance(event, ChatMessageModel)` check -- all event types are processed.
- Persistence uses `storage.add_event(event.model)` instead of appending to `self.data.messages` (the `messages` field is removed from SceneModel in section-01).
- No separate `_broadcast_fn` call -- broadcasting happens through `_dispatch` -> `User.process()`.
- The `_dispatch_to_npcs` method is replaced by `_dispatch` which sends to ALL actors.

Note: Tracing (span creation, span linking) will be added in section-05. This section should include a basic span for structure but the full span-linking pattern is section-05's responsibility.

### 6. Scene._dispatch() -- Actor Dispatch with Deduplication

This replaces the current `_dispatch_to_npcs()`. It dispatches events to ALL present actors, not just NPCs.

```python
async def _dispatch(self, event: Event) -> None:
    """Dispatch event to all present actors, deduplicating by actor_id."""
    dispatched: set[str] = set()

    for character in self.characters.values():
        actor = character.actor
        if actor.actor_id in dispatched:
            continue
        dispatched.add(actor.actor_id)

        if isinstance(actor, NPCActor):
            # Send thinking status to all present Users
            await self._send_actor_status(character, "thinking")
            try:
                await actor.process(event)
            except Exception:
                logger.exception("Error dispatching to actor %s", actor.actor_id)
            finally:
                # Always send idle status, even on failure
                await self._send_actor_status(character, "idle")
        else:
            # User actors -- send event to WebSocket connections
            try:
                await actor.process(event)
            except Exception:
                logger.exception("Error dispatching to actor %s", actor.actor_id)
```

**Deduplication:** The `dispatched` set tracks actor_ids already processed. If a User controls two characters in the same scene, `User.process(event)` is called only once (the User's `actor_id` is `"user"` for both characters).

**Thinking indicators:** Before calling `NPCActor.process()`, Scene sends a `thinking` status to all present User actors. After `process()` returns (or raises), Scene sends `idle`. These are ephemeral WebSocket signals -- NOT persisted events.

```python
async def _send_actor_status(self, character: Character, status: str) -> None:
    """Send ephemeral actor_status message to all present User actors."""
    message = {
        "type": "actor_status",
        "character_id": character.data.id,
        "scene_id": self.id,
        "status": status,
    }
    dispatched_users: set[str] = set()
    for char in self.characters.values():
        if isinstance(char.actor, User) and char.actor.actor_id not in dispatched_users:
            dispatched_users.add(char.actor.actor_id)
            await char.actor.send(message)
```

The `_send_actor_status` helper iterates present characters, finds User actors, and calls `user.send()` (not `user.process()` -- status messages are not events). It also deduplicates by actor_id to avoid sending duplicate status messages when one User controls multiple characters.

### 7. Scene.create_event() Factory

Replaces `create_message()`. Creates an `EventModel` and wraps it in an `Event`:

```python
def create_event(
    self,
    event_type: EventType,
    actor_id: str,
    body: str = "",
    character_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    name: str | None = None,
) -> Event:
    """Factory to create an Event associated with this scene."""
    if name is None:
        # Follow naming convention per event type
        name = self._default_event_name(event_type, character_id)

    model = EventModel(
        id=f"evt_{str(uuid.uuid4())[:8]}",
        name=name,
        body=body,
        event_type=event_type,
        scene_id=self.id,
        gametime=self.data.current_gametime or 0,
        walltime=datetime.now(),
        actor_id=actor_id,
        character_id=character_id,
        metadata=metadata or {},
    )
    return Event.from_model(model)
```

**Event ID prefix:** All events use `evt_` prefix (replacing the old `msg_` prefix).

**Name convention helper:**

```python
def _default_event_name(self, event_type: EventType, character_id: str | None) -> str:
    """Generate default event name following the naming convention."""
    char_name = ""
    if character_id and character_id in self.characters:
        char_name = self.characters[character_id].data.name

    match event_type:
        case EventType.CHAT_MESSAGE:
            return f"{char_name} Message" if char_name else "Message"
        case EventType.JOIN:
            return f"{char_name} Joins" if char_name else "Join"
        case EventType.LEAVE:
            return f"{char_name} Leaves" if char_name else "Leave"
        case EventType.ADJUST_GAMETIME:
            return "Time Adjustment"
        case EventType.ERROR:
            return "Error"
```

### 8. Scene.chat() -- Raw Parameter Entry Point

The signature changes from accepting a pre-built `ChatMessageModel` to accepting raw parameters:

```python
async def chat(self, actor_id: str, text: str, character_id: str | None = None) -> None:
    """Entry point for user chat. Creates event and enqueues it."""
    if self.health is not None and not self.health.is_accepting_chat:
        logger.warning("Chat rejected: campaign health is UNHEALTHY")
        return

    event = self.create_event(
        event_type=EventType.CHAT_MESSAGE,
        actor_id=actor_id,
        body=text,
        character_id=character_id,
    )
    await self.process(event)
```

Callers (Orchestrator, MCP bridge, REST endpoint) pass raw data -- they no longer construct events themselves. Scene owns event creation.

### 9. Remove Obsolete Properties/Methods

The following should be removed from `Scene`:

- `set_broadcast(fn)` -- no broadcast callback pattern
- `_broadcast_fn` field -- replaced by dispatch to User actors
- `messages` property -- `SceneModel.messages` field is removed (section-01). Events are queried from storage.
- `_dispatch_to_npcs()` -- replaced by `_dispatch()`
- `create_message()` -- replaced by `create_event()`

### 10. Scene.deactivate() Updates

Minor update -- the deactivation loop is similar but uses the new Character type:

```python
async def deactivate(self) -> None:
    """Deactivate the scene: stop queue and deactivate characters."""
    if not self._active:
        return

    for character in self.characters.values():
        await character.deactivate()
    self.characters = {}

    await self.queue.stop()
    self._active = False
```

### 11. Delete bus.py

After moving `EventQueue` into `event.py`, delete `src/sidestage/bus.py`. Update all imports:

- `src/sidestage/scene.py`: change `from sidestage.bus import EventQueue` to `from sidestage.event import EventQueue`
- Any other files importing from `bus.py` (check with grep)

### 12. Campaign.get_scene_object() Update

This method in `src/sidestage/campaign.py` creates Scene instances. It must be updated to match the new constructor:

```python
def get_scene_object(self, scene_id: str) -> Optional[Scene]:
    """Factory to get a Scene object for the given ID."""
    data = self.storage.get_scene(scene_id)
    if not data:
        return None
    embed_config = self.config.llms.get("embed")
    default_llm = self.get_llm_config("default")
    context_limit = getattr(default_llm, "context_limit", None) or 4096
    return Scene(
        storage=self.storage,
        data=data,
        campaign=self,  # Pass self instead of self.agent
        graph_client=self.graph_client,
        embed_config=embed_config,
        health=self.health,
        context_limit=context_limit,
    )
```

Key change: `self.agent` (LiteLLMAgent) is no longer passed. Instead, `campaign=self` is passed so Scene can access `campaign.get_character()` and `campaign.user`.

---

## Import Summary

The new `scene.py` imports will be:

```python
import logging
import uuid
from typing import Optional, Dict, Any, cast
from datetime import datetime

from opentelemetry import trace

from sidestage.models import CharacterModel, SceneModel, EventModel, EventType, Visibility
from sidestage.event import Event, EventQueue
from sidestage.actors import NPCActor, User
from sidestage.character import Character
from sidestage.storage import Storage
from sidestage.tracing.middleware import record_error

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from sidestage.graph.client import GraphClient
    from sidestage.config import LLMConfig
    from sidestage.health import CampaignHealth
    from sidestage.campaign import Campaign
```

Note: `Campaign` is imported under `TYPE_CHECKING` to avoid circular imports (Campaign imports Scene).

---

## Event Flow Summary

The complete event flow after this refactor:

1. **User sends message** via WebSocket or REST endpoint
2. **Orchestrator** calls `scene.chat(actor_id="user", text="Hello", character_id="char_alice")`
3. **Scene.chat()** creates an Event via `create_event()`, calls `self.process(event)`
4. **Scene.process()** sets `event.scene = self`, puts event on the queue
5. **Scene._process_event()** (queue worker) persists the event, handles gametime updates, calls `_dispatch(event)`
6. **Scene._dispatch()** iterates all present characters, deduplicates by actor_id:
   - For **User** actors: calls `user.process(event)` which sends event JSON to WebSocket connections
   - For **NPCActor** actors: sends thinking status to Users, calls `npc.process(event)`, sends idle status
7. **NPCActor.process()** (if it decides to respond) calls `event.scene.process(response_event)` to enqueue a response
8. The response event goes through steps 4-6 again (persist, dispatch to all actors including User)