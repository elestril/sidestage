# scenes

Implements: [sidestage#scene](/specs/sidestage.md#scene),
[sidestage#event](/specs/sidestage.md#event),
[sidestage#time](/specs/sidestage.md#time)

## Overview {#overview}

A scene is a limited, linear series of tightly connected events that take
place at one or more closely connected locations. Each scene has its own
character cast, independent timeline, and chat history.

## Scene Management {#scene-management}

### Multiple Scenes {#multiple-scenes}

The system MUST support organizing a campaign into multiple distinct scenes.

### Scene Creation {#scene-creation}

Creating a scene MUST accept:

- `name` — The scene name (required).
- `description` — A text description (required). Maps to the entity `body`
  field.
- `start_gametime` — When the scene takes place, in seconds (required).
- `current_gametime` — Current gametime in seconds (optional).
- `end_gametime` — End gametime in seconds (optional).

> TODO(<a id="todo-scene-gametimes"></a>todo-scene-gametimes): Add `start_gametime`
> and `end_gametime` fields to `SceneModel`.

## Scene Locations {#scene-locations}

<a id="multi-location"></a>
A scene MUST support referencing multiple locations.

> TODO(<a id="todo-scene-multi-location"></a>todo-scene-multi-location): Change
> `SceneModel` from single `location_id` to `location_ids` list.

Scene-location relationships are explicitly managed by actors, not derived
from character positions.

## Scene Membership {#scene-membership}

### Cast Management {#cast-management}

Each scene MUST have an explicit character cast managed via `PARTICIPATES_IN`
graph edges.

<a id="empty-scene"></a>
Scenes with no members MUST load zero characters.

<a id="cast-modification"></a>
Characters MUST be addable and removable via REST API, MCP tools, or the
frontend UI.

<a id="no-exclusivity"></a>
Scene membership is unconstrained — characters MAY participate in multiple
scenes simultaneously.

### Join and Leave {#join-leave}

<a id="join-broadcast"></a>
Adding a character to a scene MUST create a `PARTICIPATES_IN` edge and
broadcast a `scene_updated` WebSocket event.

<a id="leave-broadcast"></a>
Removing a character from a scene MUST remove the `PARTICIPATES_IN` edge and
broadcast a `scene_updated` WebSocket event.

## Gametime Tracking {#gametime}

### Granularity {#gametime-granularity}

<a id="gametime-seconds"></a>
Time MUST be tracked in seconds.

<a id="gametime-display"></a>
Time MUST be displayed as `Day D, HH:MM:SS`.

### Per-Scene Clocks {#per-scene-clocks}

<a id="independent-clocks"></a>
Different scenes MUST be able to exist at different times independently.
Scenes can overlap in time — concurrent scenes at different locations are
supported.

<a id="gametime-walltime-independent"></a>
The internal timeline is disconnected from wall time. Privileged characters
MAY create or open scenes at any gametime.

### Scene Conclusion {#scene-conclusion}

<a id="start-gametime"></a>
A scene MUST have a `start_gametime` field.

<a id="end-gametime"></a>
A scene MAY have an `end_gametime` field.

> TODO(<a id="todo-scene-time-fields"></a>todo-scene-time-fields): Add
> `start_gametime` and `end_gametime` to `SceneModel`. See
> [scenes#todo-scene-gametimes](/specs/implementation/scenes.md#todo-scene-gametimes).

## Scene Events {#scene-events}

### Event Types {#event-types}

Event entities (see [entities#type-event](/specs/implementation/entities.md#type-event))
MUST support the following `event_type` values:

<a id="event-chat-message"></a>
- `ChatMessage` — A chat message from a user or agent.

<a id="event-join"></a>
- `JoinEvent` — A character joining the scene.

<a id="event-leave"></a>
- `LeaveEvent` — A character leaving the scene.

<a id="event-adjust-gametime"></a>
- `AdjustGametime` — A gametime adjustment.

<a id="event-error"></a>
- `Error` — An error event.

### Chat History {#chat-history}

Chat history MUST be compartmentalized by scene. Each scene MUST maintain its
own independent message history.

### Prose View {#prose-view}

Each scene MUST have a dedicated area for the static description
(`activeScene.body`), rendered as Markdown.

## Chat Log Format {#chatlog-format}

All events MUST be persisted to the chat log. The format depends on
`event_type`:

**ChatMessage:**
```
[2026-01-15T14:30:00Z] (char_1) Character One: "message text"
```

**JoinEvent / LeaveEvent:**
```
[2026-01-15T14:30:10Z] * Character One joined the scene
[2026-01-15T14:31:00Z] * Character One left the scene
```

**AdjustGametime:**
```
[2026-01-15T14:32:00Z] * Gametime adjusted to Day 1, 14:00:00
```

**Error:**
```
[2026-01-15T14:33:00Z] ! Error: error description
```

> TODO(<a id="todo-log-all-events"></a>todo-log-all-events): Persist all event types
> to chat logs, not just `ChatMessage`.
