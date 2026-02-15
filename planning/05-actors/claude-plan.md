# Implementation Plan: Actor Restructuring (05-actors)

## 1. Overview

This plan restructures Sidestage's core class hierarchy to introduce a proper Actor system, flatten the EventModel hierarchy, redesign the Scene event loop with proper dispatch and tracing, and update the frontend to match.

### Goals

1. Replace the ad-hoc `AgentActor`/`Character` coupling with a proper Actor hierarchy (`Actor` -> `NPCActor`, `User`)
2. Flatten EventModel: eliminate ChatMessageModel, JoinEventModel, LeaveEventModel, FastForwardEventModel — single EventModel with an EventType enum
3. Introduce a runtime `Event` wrapper carrying OpenTelemetry span context through the queue
4. Redesign Scene event dispatch: all events go to all present actors; actors decide what to react to
5. Integrate the Campaign "Co-Author" agent into the Actor hierarchy as an NPCActor with `system_actor=True`
6. Update the React frontend to consume the new event format

### Non-Goals

- Multi-user support (deferred, but User class is designed for it)
- ACL system (deferred, but `system_actor` property prepares for it)
- Data migration (clean break; wipe both SQLite AND FalkorDB graph)
- Widget embedding in markdown (deferred; `metadata` dict carries structured widget data)
- Concurrent NPC dispatch (deferred; sequential dispatch is kept for event ordering consistency)

---

## 2. EventModel Restructuring

**Files:** `src/sidestage/models.py`, `src/sidestage/schemas.py`

### 2.1 EventType Enum

Add a new enum to `models.py`:

```python
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

EventType values match the old `entity_type` strings for ChatMessage and Join/Leave to ease any residual compatibility.

### 2.2 Flatten EventModel

Replace the current EventModel + 4 subclasses with a single class:

```python
class EventModel(EntityModel):
    entity_type: ClassVar[str] = "Event"  # Preserved as ClassVar for hierarchy consistency

    event_type: EventType  # Per-instance discriminator
    scene_id: str
    gametime: int
    walltime: datetime  # Real-world timestamp; Pydantic serializes to ISO string automatically
    character_id: Optional[str] = None
    actor_id: Optional[str] = None
    body: str = ""  # Rich markdown content (chat message, error details). Overrides EntityModel.body.
    metadata: Dict[str, Any] = Field(default_factory=dict)  # Structured data for mechanics/widgets
    visibility: Visibility = Visibility.PUBLIC  # public, gm_only, private
```

**Key design decisions (informed by review feedback):**

- **`entity_type` stays as ClassVar** — all EntityModel subclasses use `entity_type: ClassVar[str]`. EventModel keeps `entity_type = "Event"` like before. The new `event_type: EventType` instance field serves as the per-event discriminator. This preserves consistency with `entity_to_markdown()`, `model_dump()`, and the graph label system.

**`name` field convention:** EventModel inherits `name: str` from EntityModel (required). Convention by event type:
- CHAT_MESSAGE: `"{character_name} Message"`
- JOIN/LEAVE: `"{character_name} Joins/Leaves"`
- ADJUST_GAMETIME: `"Time Adjustment"`
- ERROR: `"Error"`

**Removed fields:** `message` (use `body`), `widget` (use `metadata`), `duration_str` (use `gametime` directly for ADJUST_GAMETIME; `body` for human-readable description).

### 2.3 Delete Subclasses

Remove: `ChatMessageModel`, `JoinEventModel`, `LeaveEventModel`, `FastForwardEventModel`.

### 2.4 SceneModel Changes

Remove the `messages` field from SceneModel. Events are tracked via `events: List[str]` (event IDs).

### 2.5 CharacterModel Changes

Add two new fields to `CharacterModel`:

- `owner: str = "npc"` — `"npc"` for NPC characters (default), a user_id string for player characters
- `system_actor: bool = False` — `True` for the Campaign Co-Author character. Set in the character's default data file.

### 2.6 Update Schemas

In `schemas.py`:
- `ChatResponse` currently references `ChatMessageModel` — change to reference `EventModel`
- `WebSocketMessage` schema may need updates for the flattened event structure

### 2.7 Downstream Impact

Every file importing `ChatMessageModel` needs updating. Key consumers:
- `scene.py` — create_message, _process_event, _dispatch_to_npcs, chat
- `character.py` — AgentActor.on_event
- `orchestrator.py` — WebSocket handler updated (scene.chat takes raw params), remove SyncManager and _broadcast_chat_event
- `campaign.py` — User actor creation, get_scene_object updated
- `sync.py` — removed (User owns connections now)
- `bus.py` — removed (EventQueue moves to event.py)
- `storage.py` — scene persistence
- `schemas.py` — ChatResponse
- `entities.py` — entity_to_markdown (add event_type to frontmatter for events)
- `migration/serialization.py` — TYPE_MAP, TYPE_TO_SUBDIR, entity/frontmatter conversion
- `migration/importer.py` — _parse_chatlog_lines, _restore_chatlogs
- `migration/exporter.py` — scene chatlog export (query events, not SceneModel.messages)
- `mcp_bridge.py` — send_chat_message, message type references
- `tests/` — all test files referencing these models

---

## 3. Event Wrapper Class

**New file:** `src/sidestage/event.py`

### 3.1 Purpose

The `Event` class wraps an `EventModel` with runtime context (OpenTelemetry span context) that should NOT be persisted. The queue passes `Event` objects, not raw `EventModel`.

### 3.2 Design

```python
class Event:
    """Runtime event wrapper carrying model data, tracing context, and scene reference."""
    model: EventModel
    span_context: SpanContext | None = None
    scene: "Scene | None" = None  # set by Scene.process() when event enters a scene

    @property
    def character(self) -> "Character | None":
        """Look up the originating Character via the scene's character registry."""
        if self.scene and self.model.character_id:
            return self.scene.characters.get(self.model.character_id)
        return None
```

This is a simple dataclass/attrs-style class, NOT a Pydantic model (it's not persisted).

The `scene` reference allows actors to enqueue events at any time via `event.scene.process(new_event)`. The `character` property enables actors to inspect the originator (e.g., `isinstance(event.character.actor, User)`).

### 3.3 Factory

`Event.from_model(model: EventModel) -> Event` — captures the current span context at creation time. Called when events enter the system (from HTTP/WebSocket handlers or from NPCActor responses). The `scene` reference is NOT set at creation — `Scene.process()` sets it when the event enters the scene.

### 3.4 Queue Integration

`EventQueue` (currently in `bus.py`) changes its queue type from `asyncio.Queue[EventModel]` to `asyncio.Queue[Event]`. The `EventHandler` type alias updates to `Callable[[Event], Awaitable[None]]`.

---

## 4. Actor Hierarchy

**Files:** `src/sidestage/character.py` (major refactor), new `src/sidestage/actors.py`

### 4.1 Base Actor Class

```python
class Actor(ABC):
    """Base class for anything that controls Characters in a Scene."""
    actor_id: str

    @abstractmethod
    async def process(self, event: Event) -> None:
        """Handle an event. May enqueue response events via event.scene.process()."""
```

Actor is abstract. It has an `actor_id` and the `process` method. **`process()` returns `None`**. Actors can enqueue response events at any time by calling `event.scene.process(new_event)` — they are not limited to returning events only when process() completes.

### 4.2 NPCActor

Replaces `AgentActor`. One NPCActor per NPC Character (1:1 mapping for NPCs).

```python
class NPCActor(Actor):
    """LLM-driven actor controlling an NPC character."""
    system_actor: bool = False

    async def process(self, event: Event) -> None:
        """React to events from User actors by generating LLM responses."""
```

**Context access:** NPCActor receives a reference to Scene's runtime `events: list[EventModel]` list during initialization (same pattern as current AgentActor receiving `scene_logic`). This is a read-only reference to a data structure, not a back-reference to Scene itself. `assemble_context()` uses this list for chat history.

**process() logic:**
1. Check if `isinstance(event.character.actor, User)` and event is CHAT_MESSAGE. If not, return.
2. Assemble memory context (existing `assemble_context` from `memory/context.py`), using `self.recent_events` for chat history
3. Call LLM agent (`LiteLLMAgent.arun()`)
4. If response: create an EventModel with `event_type=CHAT_MESSAGE`, wrap in Event, enqueue via `await event.scene.process(response_event)`
5. On LLM failure: create an EventModel with `event_type=ERROR`, wrap in Event, enqueue via `await event.scene.process(error_event)`

**system_actor and tool/prompt differentiation:** NPCActor checks the `system_actor` flag to determine its tool set and prompt template:
- `system_actor=True` (Co-Author): loads system prompt template (`system_agent.txt`), gets Campaign-level tools (world-building: `create_character`, `list_characters`, `create_location`, etc.)
- `system_actor=False` (regular NPCs): loads character prompt template (`default_npc.txt` / `unseen_npc.txt`), gets memory tools only

**Prompt loading:** Preserves the existing pattern from AgentActor — loads prompt templates from `data/prompts/` based on character's `unseen` status and `system_actor` flag.

### 4.3 User

```python
class User(Actor):
    """Represents a human player. Owns WebSocket connections."""
    connections: list[WebSocket] = []

    async def process(self, event: Event) -> None:
        """Send event to all WebSocket connections."""
        await self.send({"type": "event", "event": event.model.model_dump(), "scene_id": event.model.scene_id})

    async def send(self, message: dict, exclude: WebSocket | None = None) -> None:
        """Send to all connections, optionally excluding sender."""
        for ws in self.connections:
            if ws is not exclude:
                try:
                    await ws.send_json(message)
                except Exception:
                    self.connections.remove(ws)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.connections.remove(ws)
```

- One User per Campaign, created at Campaign startup
- The User's `actor_id` is a stable identifier (e.g., `"user"` or a UUID)
- `process()` sends events to WebSocket clients — this IS the broadcast mechanism
- When User plays multiple Characters in same scene: dispatch deduplicates by actor_id (Section 6.6)

### 4.4 File Organization

Create `src/sidestage/actors.py` for the Actor base class, NPCActor, and User. This is a new file because the responsibility is fundamentally different from the current `character.py`, which becomes focused solely on the Character runtime wrapper.

---

## 5. Character System Refactor

**File:** `src/sidestage/character.py`

### 5.1 Character Registry (Campaign-Scoped)

The Character registry is **scoped per Campaign**, not global. This prevents ID collisions between campaigns and ensures clean shutdown isolation.

```python
class Character:
    """Runtime wrapper for a CharacterModel with an associated Actor."""

    def __init__(self, model: CharacterModel, actor: Actor):
        self.data = model
        self.actor = actor
```

The registry lives on Campaign:

```python
class Campaign:
    def __init__(self, ...):
        self.characters: Dict[str, Character] = {}
        self.user = User(actor_id="user")

    def get_character(self, model: CharacterModel) -> Character:
        """Get or create a Character instance for the given model."""
        if model.id in self.characters:
            return self.characters[model.id]
        # Create new Character with resolved Actor
        actor = self._resolve_actor(model)
        char = Character(model=model, actor=actor)
        self.characters[model.id] = char
        return char

    def _resolve_actor(self, model: CharacterModel) -> Actor:
        if model.owner == "npc":
            return NPCActor(actor_id=f"agent:{model.id}", system_actor=model.system_actor, ...)
        else:
            return self.user  # Player characters are controlled by the User
```

### 5.2 Actor Resolution

When `Campaign.get_character()` creates a new Character:
- If `model.owner == "npc"`: create an NPCActor and assign to `character.actor`. Check `model.system_actor` to configure tool set.
- If `model.owner` is a user_id: assign `campaign.user` as the actor.

### 5.3 Lifecycle

- `activate()`: Initializes the actor's LLM agent (for NPCActor), adds Character to the Scene
- `deactivate()`: Cleans up actor state
- Registry cleanup: clearing `campaign.characters` dict on Campaign shutdown; tests use fresh Campaign instances

---

## 6. Scene Event Loop Refactor

**Files:** `src/sidestage/scene.py`, `src/sidestage/event.py`

### 6.1 EventQueue Consolidation

Move `EventQueue` from `bus.py` into `event.py` (alongside the Event wrapper class). Delete `bus.py`.

Updated EventQueue:
- Change queue type: `asyncio.Queue[Event]` (not `EventModel`)
- Update `EventHandler` type: `Callable[[Event], Awaitable[None]]`
- Keep the existing start/stop/put/_worker pattern — it's clean and correct

### 6.2 Scene.__init__ Changes

Scene constructor simplifies:
- Remove `agent: LiteLLMAgent` parameter (actors manage their own agents)
- Characters are obtained via `Campaign.get_character()` instead of being directly instantiated

### 6.3 Scene.activate()

1. Start EventQueue with `self._process_event` handler
2. Load CharacterModels from graph/storage
3. For each CharacterModel: call `campaign.get_character(model)` to get/create Character instance
4. Activate each Character (initializes its Actor's LLM agent)
5. Track present Characters in `self.characters` dict

### 6.4 Scene.process(event: Event)

Public entry point. Sets the scene reference and enqueues:

```python
async def process(self, event: Event) -> None:
    """Enqueue an event into this scene's event loop."""
    event.scene = self
    await self.queue.put(event)
```

This is what actors call to enqueue response events (`event.scene.process(new_event)`). Also called by `Scene.chat()` for incoming user messages.

### 6.5 Scene._process_event(event: Event)

The queue worker handler. For each event:

1. **Tracing:** Create a NEW root span linked to the incoming event's span context
   ```
   link = trace.Link(event.span_context)
   with tracer.start_as_current_span("scene.process_event", links=[link]):
   ```
2. **Persist:** Save EventModel to storage and graph (create entity node, link edges)
3. **Event-type-specific processing:**
   - `ADJUST_GAMETIME`: Set `self.current_gametime = event.model.gametime`
   - Other types: no special handling
4. **Dispatch:** Call `self._dispatch(event)` — sends to ALL present actors (including Users)

No separate broadcast step. Dispatching to Users IS the broadcast — `User.process()` sends events to WebSocket connections.

### 6.6 Scene._dispatch(event: Event)

```python
async def _dispatch(self, event: Event) -> None:
    """Dispatch event to all present actors."""
```

Calls `actor.process(event)` on every present Character's actor. This dispatches to ALL actors — Users and NPCs alike. **Users send events to WebSocket connections. NPCs generate LLM responses and enqueue them back via `event.scene.process()`.**

**Deduplication:** Track which actors have already been dispatched to (since multiple Characters may share the same Actor, e.g., a User playing 2 characters). Use a set of actor_id to avoid calling `process()` twice on the same Actor.

**Thinking indicators:** Scene owns the thinking status lifecycle. Before calling `actor.process(event)` on an NPCActor, Scene sends a `thinking` status to all present Users via `user.send({"type": "actor_status", ...})`. After `process()` returns (or raises), Scene sends `idle`. These are ephemeral WebSocket signals — NOT persisted events. User actors are skipped (no thinking status for humans). Scene reaches Users through its character registry.

### 6.7 Scene.create_event() Factory

Replaces `create_message()`. Creates an `EventModel` and wraps it in an `Event`:

```python
def create_event(self, event_type: EventType, actor_id: str, ...) -> Event:
    """Factory to create an Event associated with this scene."""
```

**Event ID prefix:** All events use the `evt_` prefix: `evt_{uuid8}`.

### 6.8 Scene.chat()

Entry point for user chat. Signature changes from `chat(user_message: ChatMessageModel)` to accept raw parameters:

```python
async def chat(self, actor_id: str, text: str, character_id: str | None = None) -> None:
```

Creates a CHAT_MESSAGE event via `create_event()`, enqueues via `self.process(event)`. Scene owns event creation — callers (Orchestrator._handle_ws_message, MCP bridge, REST endpoint) pass raw data, not pre-built events. The health check remains.

---

## 7. Tracing Integration

**Files:** `src/sidestage/event.py`, `src/sidestage/scene.py`, `src/sidestage/actors.py`

### 7.1 Event Span Lifecycle

1. **Event creation:** `Event.from_model()` captures current span context via `trace.get_current_span().get_span_context()`
2. **Queue transit:** Event carries span_context through asyncio.Queue
3. **Processing:** Scene._process_event creates a NEW root span, links to the carried span context
4. **Dispatch:** Each actor.process() runs within the scene's processing span (child spans)

### 7.2 Span Linking Pattern

```python
from opentelemetry import trace

tracer = trace.get_tracer("sidestage.scene")

async def _process_event(self, event: Event) -> None:
    links = []
    if event.span_context:
        links.append(trace.Link(event.span_context))

    with tracer.start_as_current_span("scene.process_event", links=links) as span:
        # New root span, linked to (not child of) the incoming event's trace
        span.set_attribute("sidestage.scene.id", self.id)
        span.set_attribute("sidestage.event.type", event.model.event_type.value)
        # ... persist, broadcast, dispatch
```

### 7.3 NPCActor Tracing

NPCActor.process() creates a child span of the scene's processing span:
```
scene.process_event (root, linked to incoming)
  └── npc_actor.process (child)
       └── agent.llm_call (child)
```

Full LLM call data (prompts, parameters, responses) recorded via existing `add_trace_event()` with capture flags.

### 7.4 Error Event Tracing

When NPCActor catches an LLM error, the error span is recorded, and the error event returned from `process()` gets its own span context linking to the failed span.

---

## 8. User & WebSocket Integration

**Files:** `src/sidestage/actors.py`, `src/sidestage/scene.py`, `src/sidestage/orchestrator.py`

### 8.1 User Actor Owns Connections

User holds its WebSocket connections directly (see Section 4.3 for full class). Campaign creates a single User at startup. The Orchestrator's WebSocket endpoint calls `user.connect(ws)` / `user.disconnect(ws)`.

### 8.2 Dispatch IS Broadcast

There is no separate broadcast mechanism. Scene._dispatch() calls `actor.process(event)` on all present actors (Section 6.6). When dispatched to a User, `User.process()` sends the event to all its WebSocket connections. This unifies broadcast and dispatch into a single path.

For `entity_content_sync` (keystroke sync between tabs), the Orchestrator handles it directly via `user.send(message, exclude=websocket)` — this is not an event, just a WebSocket relay.

### 8.3 Incoming Message Handling

Orchestrator's WebSocket endpoint is simplified:

```python
@self.fastapi_app.websocket("/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    user = self.campaign.user
    await user.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await self._handle_ws_message(websocket, data)
    except WebSocketDisconnect:
        user.disconnect(websocket)
```

`_handle_ws_message()` updated for the new model:
- `chat_message`: route to `scene.chat(actor_id="user", text=..., character_id=...)`
- `entity_content_sync`: rebroadcast via `user.send(message, exclude=websocket)`

### 8.4 Orchestrator Changes

- **Remove** `SyncManager` dependency and `sync.py` — User owns connections now
- **Remove** `_broadcast_chat_event()` — dispatch to Users IS the broadcast
- **Remove** `set_broadcast()` callback pattern — Scene reaches Users through its character registry
- `_handle_ws_message()`: Updated to call `scene.chat()` with raw parameters; handles `entity_content_sync` via `user.send()`
- `get_active_scene()`: Simplified — lazy activation only, no callback wiring


---

## 9. Campaign Agent Integration

**File:** `src/sidestage/campaign.py`

### 9.1 Co-Author as NPCActor

The current `Campaign.agent` (LiteLLMAgent) becomes an NPCActor with `system_actor=True`.

The Co-Author Character entity already exists in the default campaign data. Its CharacterModel gets `owner="npc"` and `system_actor=True` set in the character's default data file (`data/campaign_defaults/markdown/characters/co_author.md`). `Campaign.get_character()` creates an NPCActor for it, which reads `system_actor=True` from the model and configures world-building tools accordingly.

**Data file changes:**
- Update `data/campaign_defaults/markdown/characters/co-author.md` frontmatter: add `owner: npc` and `system_actor: true`
- Create `data/prompts/system_agent.txt` — system-level prompt template for the Co-Author (world-building instructions, distinct from NPC character prompts)

### 9.2 Scene Participation

The Co-Author NPCActor participates in scenes like any other NPC. It receives all events and responds via its LLM agent. Its distinct behavior comes from its tool set (world-building tools) and prompt template (`system_agent.txt`), not from special dispatch logic.

### 9.3 Campaign-Level Agent Removal

The `Campaign.agent` field (a raw LiteLLMAgent) is removed. The Co-Author's agent is managed by its NPCActor, which is managed by its Character.

---

## 10. Storage and Persistence

**Files:** `src/sidestage/storage.py`, `src/sidestage/graph/entities.py`

### 10.1 SQLite Storage

- `update_scene()` no longer persists embedded messages (messages field removed from SceneModel)
- Events are persisted individually (already partially the case via graph)
- `list_messages()` / scene message retrieval: query events by scene_id and event_type

### 10.2 Graph Entities

Update the graph label system for flattened EventModel:

- **`entity_to_labels()`:** When the entity is an EventModel, inspect `event_type` to generate specific labels. For example, `event_type=EventType.CHAT_MESSAGE` produces `["Entity", "Event", "ChatMessage"]`. This preserves query granularity (`MATCH (n:ChatMessage)` still works).

- **`MODEL_TO_LABELS` registry:** Add a single `EventModel` entry with base labels `["Entity", "Event"]`. Override in `entity_to_labels()` by appending `event_type.value` as the most-specific label.

- **`node_to_entity()`:** When deserializing Event nodes, populate the `event_type` instance field from the most-specific graph label (the one that's not "Entity" or "Event").

- **`LABEL_TO_MODEL` registry:** Map each EventType value string (`"ChatMessage"`, `"JoinEvent"`, etc.) to `EventModel` class. This allows `node_to_entity()` to construct the correct class.

### 10.3 Entity Serialization (Markdown Export/Import)

**Files:** `src/sidestage/entities.py`, `src/sidestage/migration/serialization.py`

`entity_to_markdown()` writes `entity.entity_type` as the `type` field in frontmatter. Since all events now have `entity_type = "Event"` (ClassVar), the `event_type` discriminator must be explicitly serialized:

- **`entity_to_markdown()`:** For EventModel instances, add `event_type` to the frontmatter dict alongside `type`. This ensures the specific event type survives export/reimport.
- **`markdown_to_entity()` / `frontmatter_dict_to_entity()`:** When `type == "Event"`, look for `event_type` in frontmatter to populate the instance field.

**`migration/serialization.py` updates:**
- `TYPE_MAP`: Remove entries for deleted subclasses (`ChatMessageModel`, `JoinEventModel`, `LeaveEventModel`, `FastForwardEventModel`). Map all EventType value strings (`"ChatMessage"`, `"JoinEvent"`, etc.) to `EventModel`.
- `TYPE_TO_SUBDIR`: Remove per-subclass entries; all map to `"events"`.
- `entity_to_frontmatter_dict()`: For EventModel, include `event_type` in the frontmatter.
- `frontmatter_dict_to_entity()`: When type is `"Event"` or an EventType value, construct EventModel with the appropriate `event_type`.

**`migration/importer.py` updates:**
- `_parse_chatlog_lines()`: Construct `EventModel` with `event_type=EventType.CHAT_MESSAGE` instead of `ChatMessageModel`. Use `evt_` ID prefix.
- `_restore_chatlogs()`: Remove `existing.messages = messages` (field removed from SceneModel). Instead, persist each event individually to storage/graph.
- `import_campaign()`: Remove `sync_manager` parameter (SyncManager eliminated). Broadcast via User if needed, or skip broadcast during import.

**`migration/exporter.py` updates:**
- Scene chatlog export: Query events from storage/graph by scene_id instead of reading `SceneModel.messages`.

### 10.4 Graph Property Handling

- **`metadata` field:** Nested `Dict[str, Any]` cannot be stored as flat FalkorDB node properties. Serialize `metadata` as a JSON string property in `entity_to_properties()`. Deserialize in `node_to_entity()`.
- **`walltime` field:** `datetime` objects may not be handled natively by FalkorDB. Serialize to ISO string in `entity_to_properties()`, parse back in `node_to_entity()`.
- **`visibility` and `event_type` fields:** Both are `str` enums — their `.value` works as flat string properties.

### 10.5 Clean Break

No migration. **Wipe both SQLite AND FalkorDB graph** on upgrade. Existing data with embedded `messages` on SceneModel and old event subclass nodes will not load correctly. Users re-import from markdown.

As a safety net, configure EventModel with `model_config = ConfigDict(extra='ignore')` to gracefully handle stale properties (e.g., `message` from old graph nodes) if the graph is not fully wiped.

---

## 11. Frontend Changes

**Files:** `frontend/src/types.ts`, `frontend/src/AppContext.tsx`, `frontend/src/ChatWidget.tsx`

### 11.1 Type Definitions

Update `types.ts`:

```typescript
export type EventType = 'ChatMessage' | 'JoinEvent' | 'LeaveEvent' | 'AdjustGametime' | 'Error';

export interface EventModel {
    id: string;
    event_type: EventType;
    scene_id: string;
    gametime: number;
    walltime: string;
    character_id?: string;
    actor_id?: string;
    body: string;
    metadata: Record<string, any>;
    visibility: 'public' | 'gm_only' | 'private';
    name: string;
}
```

Remove the `ChatMessage` interface. Replace references with `EventModel`.

### 11.2 WebSocket Messages

Update `ChatMessageBroadcast`:

```typescript
export interface EventBroadcast {
    type: 'event';
    event: EventModel;
    scene_id: string;
}

export interface ActorStatusMessage {
    type: 'actor_status';
    character_id: string;
    scene_id: string;
    status: 'thinking' | 'idle';
}
```

The `actor_status` messages are ephemeral (not persisted). They signal when an NPC starts/stops processing so the UI can show a thinking indicator.

### 11.3 AppContext

- `messages` state: change type from `ChatMessage[]` to `EventModel[]`
- `thinkingActors` state: `Set<string>` of character_ids currently thinking
- `loadMessages()`: adapt to new API response format
- WebSocket `onmessage`: handle `'event'` type instead of `'chat_message'`; handle `'actor_status'` to update `thinkingActors` set

### 11.4 ChatWidget

- Render `event.body` instead of `event.message` for chat content (rich markdown)
- The `character_id` field remains for identifying the speaker
- **Widget rendering:** Entity card widgets are extracted from `event.metadata` (e.g., `metadata.widget`). Same click-to-select behavior as before.
- **Thinking indicator:** For each character_id in `thinkingActors`, render a placeholder chat bubble with the character's avatar and an animated three-dot ellipsis ("..."). The bubble appears at the bottom of the message list and disappears when the `idle` status arrives (replaced by the actual response event). CSS animation for the dots (e.g., `@keyframes blink`).
- **Error event rendering:** ERROR events render as system messages with a distinct warning/error styling (red/amber background, no character avatar)
- **Visibility filtering:** Events with `visibility: "gm_only"` or `"private"` may be filtered or styled differently in the UI
- Trace links: the `trace_id` attribute can be extracted from event metadata if needed (trace links on the backend side still work via the span context)

### 11.5 Scene Messages Endpoint

The `/v1/scenes/{scene_id}/messages` endpoint needs updating to return events filtered by scene_id, potentially filtered to CHAT_MESSAGE type for the chat view. This may become `/v1/scenes/{scene_id}/events` with optional type filtering.

---

## 12. API Changes

**Files:** `src/sidestage/orchestrator.py`, `src/sidestage/schemas.py`

### 12.1 REST Endpoints

| Endpoint | Change |
|---|---|
| `POST /v1/chat` | Response changes from `ChatResponse(user_message, agent_message)` to returning the created event |
| `GET /v1/scenes/{id}/messages` | Returns `List[EventModel]` filtered by scene, optionally by event_type |
| WebSocket broadcast | Message type changes from `chat_message` to `event` with EventModel payload |

### 12.2 Schema Updates

```python
class ChatResponse(BaseModel):
    event: EventModel  # The created user event (agent response comes async via WebSocket)
```

### 12.3 MCP Bridge

Update `mcp_bridge.py` to work with EventModel instead of ChatMessageModel.

**Specific changes:**
- `send_chat_message` tool: call `scene.chat()` with raw parameters instead of `scene.create_message()`. Return value changes from `{"user_message": user_msg.model_dump()}` to `{"event": event.model_dump()}`
- Tool descriptions and parameter schemas update to reference EventModel fields (`body` instead of `message`, `event_type` instead of class-based discrimination)
- All `orchestrator.sync_manager.broadcast()` call sites (~6: entity updates, imports, exports) change to `campaign.user.send()` — SyncManager is eliminated

---

## 13. Testing Strategy

### 13.1 Unit Tests

- **EventModel:** Test creation with each EventType, field validation, serialization. Verify `entity_type` ClassVar is `"Event"` and `event_type` instance field holds the discriminator.
- **Event wrapper:** Test from_model() captures span context
- **Actor hierarchy:** Test Actor/NPCActor/User instantiation, process() return values
- **Character registry:** Test Campaign.get_character() caching, Actor resolution based on owner and system_actor fields
- **Scene dispatch:** Test _dispatch sends to all actors, deduplicates by actor_id. Test thinking status broadcasts (thinking before process, idle after). Test that actor-enqueued events (via event.scene.process) flow through the event loop.
- **EventQueue:** Test Event (not EventModel) flows through queue correctly
- **Graph labels:** Test entity_to_labels() generates correct labels for each EventType. Test node_to_entity() round-trips correctly.

### 13.2 Integration Tests

- **Chat flow end-to-end:** User sends message -> event created -> queued -> persisted -> broadcast -> NPC responds -> response event broadcast
- **Tracing:** Verify span linking (new root span links to incoming span context)
- **Error handling:** LLM failure -> error event returned from process() -> enqueued -> broadcast to frontend
- **WebSocket:** Verify new event format received by client
- **Thinking indicator:** Verify `actor_status` thinking/idle messages bracket NPC processing; verify idle is sent even on LLM failure

### 13.3 Existing Test Updates

Many existing tests reference `ChatMessageModel`. These need updating to use `EventModel` with `event_type=EventType.CHAT_MESSAGE`.

---

## 14. Implementation Order

The implementation should follow this dependency order:

1. **EventModel restructuring** (Section 2) — most foundational change; everything else depends on it
2. **Event wrapper** (Section 3) — needed before Scene refactor
3. **Actor hierarchy** (Section 4) — needed before Character and Scene refactors
4. **Character system** (Section 5) — depends on Actor hierarchy
5. **Scene event loop** (Section 6) — depends on Event wrapper, Actors, Characters
6. **Tracing integration** (Section 7) — depends on Event wrapper and Scene refactor
7. **Storage and persistence** (Section 10) — depends on EventModel changes
8. **User & WebSocket** (Section 8) — depends on Actor hierarchy
9. **Campaign agent integration** (Section 9) — depends on NPCActor and Character registry
10. **API changes** (Section 12) — depends on EventModel, Scene, and User
11. **Frontend changes** (Section 11) — depends on API changes
12. **Testing** (Section 13) — throughout, but bulk of integration tests at end
