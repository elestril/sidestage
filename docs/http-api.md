# Sidestage API Reference

This document provides a reference for the Sidestage JSON API and WebSocket protocol.

## Base URL
Defaults to `http://localhost:8000`.

## WebSocket

**Endpoint:** `/v1/ws`

Used for real-time updates and synchronization.

### Server-to-Client Messages

**Entity Update**
Triggered when any entity is created or updated via tools or API.
```json
{
  "type": "entities_updated"
}
```

**Scene Update**
Triggered when a scene is created or updated.
```json
{
  "type": "scene_updated"
}
```

**Chat Message**
Broadcasted during chat interactions.
```json
{
  "type": "chat_message",
  "scene_id": "scene_id",
  "message": {
    "id": "msg_123",
    "actor": "user" | "agent" | "npc_id",
    "message": "Hello world",
    "gametime": 12345,
    "walltime": "2026-02-02T...",
    "widget": { ... } // Optional entity widget data if the agent mentions an entity
  }
}
```

**Content Sync**
Relayed from other clients (e.g., for collaborative editing).
```json
{
  "type": "entity_content_sync",
  # ... arbitrary payload
}
```

### Client-to-Server Messages

**Content Sync**
Sent by client when editing entity markdown content.
```json
{
  "type": "entity_content_sync",
  # ... arbitrary payload
}
```

## REST API

### Entities

#### List Entities
**GET** `/v1/entities`

Returns a list of all entities in the campaign.

**Response:** `List[Entity]`
```json
[
  {
    "id": "npc_123",
    "name": "Gandalf",
    "body": "A wizard.",
    "type": "Character",
    "location_id": "loc_1",
    "inventory": []
  }
]
```

#### Get Entity Markdown
**GET** `/v1/entities/{entity_id}/markdown`

Returns the full markdown representation of an entity (including frontmatter).

**Response:**
```json
{
  "markdown": "---\nname: Gandalf\n...\n"
}
```

#### Update Entity Markdown
**POST** `/v1/entities/{entity_id}/markdown`

Updates an entity entirely from its markdown representation.

**Request:**
```json
{
  "markdown": "---\nname: Gandalf\n...\n"
}
```

**Response:**
```json
{ "status": "ok" }
```

#### Update Entity Data
**POST** `/v1/entities/{entity_id}`

Updates specific fields of an entity. The `type` field is optional if it can be inferred.

**Request:**
```json
{
  "name": "Gandalf the White",
  "type": "Character" // Optional
}
```

**Response:**
```json
{ "status": "ok" }
```

#### Export Entities (Legacy)
**POST** `/v1/entities/export`

Exports all entities to markdown files in the campaign's `entities/` directory. Deprecated — use `POST /v1/campaign/backup` instead.

**Response:**
```json
{ "message": "Exported X entities to ..." }
```

#### Import Entities (Legacy)
**POST** `/v1/entities/import`

Imports entities from markdown files in the campaign's `entities/` directory. Deprecated — use `POST /v1/campaign/import` instead.

**Response:**
```json
{ "message": "Successfully imported X entities." }
```

#### Reload Defaults
**POST** `/v1/campaign/reload-defaults`

Reloads default entities from `data/campaign_defaults/markdown/` into the campaign.

**Response:**
```json
{ "status": "ok" }
```

### Campaign Migration

#### Import Campaign
**POST** `/v1/campaign/import`

Two-phase import from the campaign's `markdown/` directory tree. The import is destructive — it drops and recreates the graph.

Returns `409 Conflict` if campaign health is DEGRADED (another operation is in progress).

**Request:**
```json
{
  "action": "validate",  // "validate" or "execute"
  "force": false          // Skip validation on execute (default false)
}
```

**Response (validate):**
```json
{
  "action": "validate",
  "validation": {
    "valid": true,
    "entities_found": 15,
    "memories_found": 8,
    "entity_counts": { "Character": 5, "Location": 4, "Item": 3, "Scene": 2, "Event": 1 },
    "errors": [],
    "warnings": [
      {
        "entity_id": "npc_1",
        "file_path": "characters/gandalf.md",
        "severity": "warning",
        "message": "Referenced location 'loc_99' not found"
      }
    ]
  },
  "result": null
}
```

**Response (execute):**
```json
{
  "action": "execute",
  "validation": null,
  "result": {
    "phase": "complete",
    "total_entities": 15,
    "total_memories": 8,
    "processed_entities": 15,
    "processed_memories": 8,
    "errors": []
  }
}
```

#### Backup Campaign
**POST** `/v1/campaign/backup`

Exports all entities, relationships, memories, and chat logs to the `markdown/` directory tree with atomic swap. Writes a `status.json` with backup metadata.

Returns `409 Conflict` if campaign health is DEGRADED.

**Response:**
```json
{
  "phase": "complete",
  "total_entities": 15,
  "total_memories": 8,
  "written_entities": 15,
  "written_memories": 8,
  "written_chatlogs": 3,
  "errors": []
}
```

### Scenes

#### List Scenes
**GET** `/v1/scenes`

Returns a list of all scenes.

**Response:** `List[Scene]`

#### Create Scene
**POST** `/v1/scenes`

Creates a new scene.

**Request:**
```json
{
  "name": "The Tavern",
  "description": "A noisy place.",
  "current_gametime": 123456 // Optional
}
```

**Response:** `Scene`

#### Get Scene Messages
**GET** `/v1/scenes/{scene_id}/messages`

Returns the message history for a scene.

**Response:** `List[ChatMessage]`
```json
[
  {
    "id": "msg_1",
    "actor": "user",
    "message": "Hello",
    "gametime": 0,
    "walltime": "2026-02-02T..."
  },
  {
    "id": "msg_2",
    "actor": "agent",
    "message": "Hi there",
    "gametime": 0,
    "walltime": "2026-02-02T..."
  }
]
```

### Chat

#### Send Chat Message
**POST** `/v1/chat`

Sends a message to the AI agent within a specific scene context. The agent's prompt is enriched with assembled memory context (scene recollections, character impressions, world facts) before responding.

**Request:**
```json
{
  "message": "Describe the room.",
  "scene_id": "scene_123"
}
```

**Response:** `ChatResponse`
```json
{
  "user_message": { ...ChatMessage... },
  "agent_message": { ...ChatMessage... }
}
```

## Data Models

### Entity (Base)
| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier |
| `name` | string | Entity name |
| `body` | string | Description/Content |
| `type` | string | Discriminator (Character, Location, Item, Scene, Event) |

### Character (extends Entity)
| Field | Type | Description |
|-------|------|-------------|
| `location_id` | string? | ID of current location |
| `inventory` | string[] | List of item IDs |

### Location (extends Entity)
| Field | Type | Description |
|-------|------|-------------|
| `connected_locations` | string[] | IDs of connected locations (stored as `CONNECTS_TO` edges in graph) |

### Item (extends Entity)
(No additional fields)

### Scene (extends Entity)
| Field | Type | Description |
|-------|------|-------------|
| `current_gametime` | int? | Gametime in seconds |
| `location_id` | string? | Primary location ID |
| `events` | string[] | List of event IDs |
| `messages` | object[] | Chat history |

### Event (extends Entity)
| Field | Type | Description |
|-------|------|-------------|
| `scene_id` | string | Associated scene ID |
| `gametime` | int | Gametime in seconds |
| `walltime` | string | ISO timestamp of real world time |

### ChatMessage (extends Event)
| Field | Type | Description |
|-------|------|-------------|
| `character_id` | string | ID of the Character persona who sent the message |
| `actor_id` | string? | ID of the Actor who originated the message |
| `message` | string | The content of the chat message |
| `widget` | object? | Optional interactive widget data |

### JoinEvent (extends Event)
| Field | Type | Description |
|-------|------|-------------|
| `actor_id` | string | ID of the Actor who joined |

### LeaveEvent (extends Event)
| Field | Type | Description |
|-------|------|-------------|
| `actor_id` | string | ID of the Actor who left |

### FastForwardEvent (extends Event)
| Field | Type | Description |
|-------|------|-------------|
| `duration_str` | string | A string describing the time jump (e.g., "2 hours") |

### Memory
| Field | Type | Description |
|-------|------|-------------|
| `id` | string | UUID |
| `content` | string | The living document text |
| `memory_type` | string | `scene`, `character`, or `world_fact` |
| `visibility` | string | `common` or `private` |
| `embedding` | float[]? | Vector embedding for similarity search |
| `owner_id` | string? | Character who owns this memory |
| `target_id` | string | Entity this memory is about |
| `created_at` | float | Unix timestamp |
| `updated_at` | float | Unix timestamp |
| `gametime` | int? | In-game time of the memory |
| `access_count` | int | Number of times accessed |
| `last_accessed_at` | float? | Unix timestamp of last access |

## Markdown Directory Layout

The `POST /v1/campaign/backup` and `POST /v1/campaign/import` endpoints use a structured directory tree under `~/.sidestage/<campaign_name>/markdown/`:

```
markdown/
├── status.json                    # Backup metadata (timestamp, counts, version)
├── characters/
│   ├── Character_Name.md          # Entity file (YAML frontmatter + markdown body)
│   └── Character_Name.d/          # Companion directory (memories)
│       └── mem_id.md
├── locations/
│   ├── Location_Name.md
│   └── Location_Name.d/
│       └── mem_id.md
├── items/
│   └── Item_Name.md
├── scenes/
│   ├── Scene_Name.md
│   └── Scene_Name.d/
│       ├── chatlog.log            # Chat log for this scene
│       └── mem_id.md
└── events/
    └── Event_Name.md
```

### Entity File Format

```markdown
---
name: "Eldric the Bold"
id: "char_eldric"
type: "Character"
location_id: "loc_rusty_tavern"
inventory:
- "item_flame_tongue"
---

A brave warrior who frequents the Rusty Tavern.
```

The frontmatter contains all fields from the entity's Pydantic model plus a `type` discriminator. The `body` field becomes the markdown content below the frontmatter.

### Memory File Format

```markdown
---
id: "mem_abc123"
memory_type: "scene"
visibility: "common"
owner_id: "char_eldric"
target_id: "scene_tavern_brawl"
gametime: 3600
created_at: 1706000000.0
updated_at: 1706000000.0
access_count: 0
---

Eldric witnessed a fierce brawl break out in the tavern...
```

The `embedding` field is excluded from disk — embeddings are regenerated on import.

### Chat Log Format

```
[2026-01-15T14:30:00Z] (char_eldric) Eldric the Bold: "I challenge you to a duel!"
[2026-01-15T14:30:05Z] (char_alice) Alice the Merchant: "You'll regret that, Eldric."
```

Each line: `[walltime] (character_id) display_name: "message"`
