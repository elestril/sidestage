# Combined Spec: Actor Restructuring (05-actors)

## Overview

Restructure the Sidestage class hierarchy to introduce a proper Actor system, flatten the EventModel hierarchy, implement an event-driven Scene dispatch loop with tracing, and update the frontend to match.

## Actor Hierarchy

### Base: `class Actor`
- Abstract base class for anything that controls Characters
- Has `actor_id: str`, `async process(event: Event) -> None`
- Can manage multiple Characters (though NPCs are 1:1)
- Subclasses: NPCActor, User

### `class NPCActor(Actor)`
- Replaces current `AgentActor`
- Manages one Character's LLM "brain"
- `process(event)` checks if event.character's actor is a User; if so, calls LLM agent, enqueues response back to scene
- Has `system_actor: bool = False` property — the Campaign Co-Author agent becomes an NPCActor with `system_actor=True`
- On LLM failure: enqueues an error event back to the scene

### `class User(Actor)`
- Represents a player
- One User per Campaign, created at startup
- All WebSocket connections bind to the Campaign's User on connect
- Can control multiple Characters (typically one, but supports multi-character play)
- When playing 2+ characters in same scene, WebSocket messages dispatched only once

## Character System

### `Character` class
- Runtime wrapper around CharacterModel
- `Character.getCharacter(model: CharacterModel) -> Character` classmethod
  - Global registry: `Character._instances: Dict[str, Character]`
  - Returns existing instance or creates new one
  - On create: retrieves or instantiates the appropriate Actor based on `model.owner`
- Each Character has exactly one Actor reference
- `activate()` / `deactivate()` lifecycle methods

### `CharacterModel` changes
- New field: `owner: str` — user_id for player characters, `"npc"` for NPCs
- Used by Character.getCharacter() to determine Actor type

## EventModel Restructuring

### Flattened EventModel
- **No subclasses** — single `EventModel` class
- `entity_type` becomes per-instance `EventType` enum field (not ClassVar)
- EventType values: `CHAT_MESSAGE`, `JOIN`, `LEAVE`, `ADJUST_GAMETIME`, `ERROR`
- **Removed fields:** `message`, `widget` (from old ChatMessageModel)
- **Kept/added fields:** `body` (rich markdown with embedded widgets), `character_id`, `actor_id`, `gametime`, `walltime`, `scene_id`
- All event-specific fields are Optional on the single class

### Deleted classes
- `ChatMessageModel` — replaced by EventModel with entity_type=CHAT_MESSAGE
- `JoinEventModel` — replaced by EventModel with entity_type=JOIN
- `LeaveEventModel` — replaced by EventModel with entity_type=LEAVE
- `FastForwardEventModel` — replaced by ADJUST_GAMETIME event type

### Widget embedding
- Widgets are now embedded in the markdown body as special markdown syntax
- No separate widget field on EventModel

### Gametime adjustment
- ADJUST_GAMETIME event: `gametime` field carries the target gametime value
- Scene.current_gametime = event.gametime when processing this event type

## Event Wrapper Class

### `class Event`
- **Runtime wrapper** around EventModel (not persisted)
- Fields: `model: EventModel`, `span_context: SpanContext | None`
- Queue passes Event objects, not raw EventModel
- Created when events enter the system, carries tracing context through the queue

## Scene Event Loop

### `async Scene.process(event: Event) -> None`
- Enqueues the Event into the Scene's asyncio.Queue
- Queue worker is a background asyncio task (via `asyncio.create_task()`)
- Worker calls `Scene._dispatch(event)`

### `Scene._dispatch(event: Event) -> None`
- Default implementation: calls `process()` on ALL present actors
- Every actor receives every event — actors decide internally what to react to
- Persists EventModel to storage
- Broadcasts to WebSocket clients

### Graceful shutdown
- Uses asyncio.Queue shutdown pattern
- `task_done()` + `join()` for coordinated completion
- Handle `CancelledError` for graceful cleanup

## Tracing

### Event span lifecycle
- Event class has an OpenTelemetry span
- `Scene.process()` creates a NEW root span, but links to the incoming event's span context
- Pattern: capture incoming span context -> create new root span with `links=[Link(incoming_ctx)]`
- Spans contain full, unabridged LLM calls, prompts, parameters, responses
- Uses existing TraceConfig capture flags

### Local traces
- Written to separate `telemetry.db` SQLite in campaign dir (existing infrastructure)
- Frontend trace viewer is functional, trace links on chat UI work

## WebSocket / User Integration

- SyncManager updated to track User association per WebSocket
- Campaign creates single User at startup
- On WebSocket connect: bind connection to Campaign's User
- When User plays multiple characters in same scene: deduplicate WebSocket dispatches

## Campaign Agent Integration

- Current Campaign.agent (Co-Author) becomes an NPCActor with `system_actor=True`
- Participates in the Actor hierarchy
- `system_actor` property will later integrate with a proper ACL system

## Frontend Changes

- Update React components to handle new EventModel format (no ChatMessageModel)
- Chat messages now come as EventModel with entity_type=CHAT_MESSAGE, body field for content
- Remove widget field handling, adapt to widget-in-markdown format
- Trace links continue to work (span linking preserves trace association)

## Data Migration

- Clean break — no migration needed
- Existing dev data can be wiped and re-imported

## Deleted / Removed

- `SceneModel.messages` field — events are in `SceneModel.events` list
- `ChatMessageModel`, `JoinEventModel`, `LeaveEventModel`, `FastForwardEventModel` classes
- `AgentActor` class (replaced by NPCActor)
- `message` and `widget` fields from event models
