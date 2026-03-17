# entities

Implements: [sidestage#principle-markdown-first](/specs/sidestage.md#principle-markdown-first)

## Overview {#overview}

All data objects share a universal entity model. Entities are stored as graph
nodes in FalkorDB and can be edited and exchanged as Markdown files with YAML
frontmatter.

## Universal Entity Model {#entity-model}

All entities MUST share a common base structure:

| Field        | Type    | Description                                              |
|--------------|---------|----------------------------------------------------------|
| `id`         | string  | UUID (prefixed by type, e.g., `char_`, `loc_`, `evt_`)   |
| `name`       | string  | Entity name                                              |
| `body`       | string  | Description/content                                      |
| `type`       | string  | Discriminator: Character, Location, Item, Scene, Event   |
| `visibility` | string  | Access control level (valid values are type-specific)    |

> TODO(<a id="todo-unified-visibility"></a>todo-unified-visibility): Design and
> implement a unified visibility model. Event visibility
> (`public`/`gm_only`/`private`) and memory visibility (`common`/`private`)
> are currently separate systems. Scene-specific logic (e.g., a referee agent)
> will determine which characters can observe which events.

## Entity Types {#entity-types}

### Character {#type-character}

Characters extend the base entity model with:

| Field         | Type      | Description              |
|---------------|-----------|--------------------------|
| `location_id` | string?   | ID of current location   |
| `inventory`   | string[]  | List of item IDs         |

Characters MUST track their current location and inventory.

### Location {#type-location}

Locations extend the base entity model with:

| Field                 | Type      | Description                                              |
|-----------------------|-----------|----------------------------------------------------------|
| `connected_locations` | string[]  | IDs of connected locations (stored as `CONNECTS_TO` edges) |

Locations MUST track connections forming a navigation graph.

### Item {#type-item}

Items use the base entity model with no additional fields.

### Scene {#type-scene}

Scenes extend the base entity model with:

| Field              | Type      | Description                                                  |
|--------------------|-----------|--------------------------------------------------------------|
| `start_gametime`   | int       | When the scene takes place, in seconds (required)            |
| `current_gametime` | int?      | Current gametime in seconds                                  |
| `end_gametime`     | int?      | End gametime in seconds                                      |
| `location_ids`     | string[]  | IDs of locations where the scene takes place (via `AT_LOCATION` edges) |
| `events`           | string[]  | List of event IDs                                            |
| `character_ids`    | string[]  | IDs of participating characters (via `PARTICIPATES_IN` edges) |

> TODO(<a id="todo-scene-fields"></a>todo-scene-fields): Change `location_id`
> (singular) to `location_ids` (list). Add `start_gametime` and
> `end_gametime` fields to `SceneModel`.

### Event {#type-event}

Events are true entities that extend the base entity model. An event is
something that happens within a scene — it is considered instantaneous and
append-only.

Events extend the base entity model with:

| Field          | Type    | Description                                                      |
|----------------|---------|------------------------------------------------------------------|
| `event_type`   | string  | `ChatMessage`, `JoinEvent`, `LeaveEvent`, `AdjustGametime`, or `Error` |
| `scene_id`     | string  | Associated scene ID (stored as `HAS_EVENT` edge)                 |
| `gametime`     | int     | Gametime in seconds                                              |
| `walltime`     | string? | ISO timestamp of real-world time (optional, only for live sessions) |
| `character_id` | string? | ID of the character who originated the event (stored as `INVOLVES` edge) |
| `metadata`     | object  | Arbitrary metadata (e.g., `widget` for entity previews)          |

The base `body` field carries the event content (message text, error
description, etc.). The base `visibility` field uses event-specific values:
`public`, `gm_only`, or `private`.

> TODO(<a id="todo-event-drop-actor-id"></a>todo-event-drop-actor-id): Replace
> `actor_id` with `character_id` only.

> TODO(<a id="todo-event-optional-walltime"></a>todo-event-optional-walltime): Make
> `walltime` optional (only meaningful for live sessions).

> TODO(<a id="todo-events-in-list-entities"></a>todo-events-in-list-entities): Include
> events in `list_all_entities()`. As true entities, events MUST be included
> in generic entity queries, with filtering by type available to callers.
> Callers (especially the frontend) MUST handle the high volume of events
> compared to persistent entities — type filtering and pagination are
> essential.

> TODO(<a id="todo-event-visibility"></a>todo-event-visibility): Reconcile event
> visibility values (`public`/`gm_only`/`private`) with memory visibility
> values (`common`/`private`) under the unified entity visibility model.
> See [entities#todo-unified-visibility](/specs/implementation/entities.md#todo-unified-visibility).

## Graph Storage {#graph-storage}

### Node Structure {#graph-nodes}

Entities MUST be stored as multi-label nodes in FalkorDB (e.g.,
`:Entity:Character`). Properties, relationships, and indexes MUST be managed
via a versioned schema.

### Relationship Types {#relationships}

Entity connections MUST be stored as typed, directed edges:

<a id="rel-located-in"></a>
- `LOCATED_IN` — Character at a Location.

<a id="rel-connects-to"></a>
- `CONNECTS_TO` — Location adjacency (semantically bidirectional).

<a id="rel-at-location"></a>
- `AT_LOCATION` — Scene takes place at a Location (one-to-many).

<a id="rel-has-event"></a>
- `HAS_EVENT` — Scene contains an Event.

<a id="rel-involves"></a>
- `INVOLVES` — Event references a Character.

<a id="rel-participates-in"></a>
- `PARTICIPATES_IN` — Character present in a Scene.

### Graph Queries {#graph-queries}

The system MUST support domain-specific queries over the graph:

- Characters at a location.
- Connected locations.
- Scene events.
- N-hop subgraph extraction.

## Markdown Representation {#markdown-format}

### Markdown-First Principle {#markdown-first}

Entities MUST be editable and exchangeable as Markdown files with YAML
frontmatter.

### Entity File Format {#entity-file-format}

Entity files MUST follow this format:

```markdown
---
name: "Example Character"
id: "char_1"
type: "Character"
location_id: "loc_1"
inventory:
- "item_1"
---

Entity body content in markdown.
```

The frontmatter MUST contain all fields from the entity's Pydantic model plus
a `type` discriminator. The `body` field MUST become the markdown content below
the frontmatter.

