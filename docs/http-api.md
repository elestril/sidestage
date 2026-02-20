# Sidestage API Reference

This document provides a reference for the Sidestage JSON API and WebSocket protocol.

## Base URL
Defaults to `http://localhost:8000`.

## MCP (Model Context Protocol)

**Endpoint:** `/v1/mcp`

Streamable HTTP transport endpoint for MCP-compatible AI clients (e.g. Claude Code, Claude Desktop). Exposes the same operations as the REST API below as MCP tools.

### Available Tools

| Tool | Description |
|---|---|
| `list_entities` | List all entities in the campaign |
| `get_entity_markdown` | Get markdown representation of an entity |
| `update_entity_markdown` | Update entity from markdown with YAML frontmatter |
| `update_entity` | Update specific entity fields (JSON string) |
| `reload_defaults` | Reload default entities from data directory |
| `import_campaign` | Two-phase campaign import (validate/execute) |
| `backup_campaign` | Backup campaign to markdown directory |
| `list_scenes` | List all scenes |
| `create_scene` | Create a new scene |
| `get_scene_messages` | Get message history for a scene |
| `send_chat_message` | Send a chat message to the AI co-author |
| `join_scene` | Add a character to a scene's cast |
| `leave_scene` | Remove a character from a scene's cast |

### Client Configuration

For Claude Code (`~/.claude/settings.json`):
```json
{
  "mcpServers": {
    "sidestage": {
      "url": "http://localhost:8000/v1/mcp"
    }
  }
}
```

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

**Event**
Broadcasted when an event is created in a scene (chat messages, joins, errors, etc.).
```json
{
  "type": "event",
  "scene_id": "scene_id",
  "event": {
    "id": "evt_abc12345",
    "event_type": "ChatMessage",
    "scene_id": "scene_id",
    "gametime": 12345,
    "walltime": "2026-02-02T...",
    "actor_id": "user",
    "character_id": "char_co_author",
    "body": "Hello world",
    "metadata": {},
    "visibility": "public",
    "name": "Co-Author Message"
  }
}
```

**Actor Status**
Sent when an NPC actor starts or finishes processing an event.
```json
{
  "type": "actor_status",
  "character_id": "char_co_author",
  "scene_id": "scene_id",
  "status": "thinking"
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

**Response:** `List[EntityModel]`
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

#### List Scene Characters
**GET** `/v1/scenes/{scene_id}/characters`

Returns characters participating in the scene (via `PARTICIPATES_IN` edges).

**Response:** `List[CharacterModel]`
```json
[
  {
    "id": "char_co_author",
    "name": "Co-Author",
    "body": "The AI co-author.",
    "type": "Character",
    "location_id": null,
    "inventory": []
  }
]
```

#### Add Character to Scene
**POST** `/v1/scenes/{scene_id}/characters/{character_id}`

Creates a `PARTICIPATES_IN` edge from the character to the scene. Broadcasts a `scene_updated` WebSocket event.

**Response (201):**
```json
{ "status": "ok" }
```

#### Remove Character from Scene
**DELETE** `/v1/scenes/{scene_id}/characters/{character_id}`

Removes the `PARTICIPATES_IN` edge from the character to the scene. Broadcasts a `scene_updated` WebSocket event.

**Response:**
```json
{ "status": "ok" }
```

#### List Scenes
**GET** `/v1/scenes`

Returns a list of all scenes.

**Response:** `List[SceneModel]`

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

**Response:** `SceneModel`

#### Get Scene Messages
**GET** `/v1/scenes/{scene_id}/messages`

Returns the message history for a scene.

**Response:** `List[EventModel]`
```json
[
  {
    "id": "evt_abc12345",
    "event_type": "ChatMessage",
    "scene_id": "scene_id",
    "gametime": 0,
    "walltime": "2026-02-02T...",
    "actor_id": "user",
    "character_id": "user",
    "body": "Hello",
    "metadata": {},
    "visibility": "public",
    "name": "Message"
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
  "event": {
    "id": "evt_abc12345",
    "event_type": "ChatMessage",
    "scene_id": "scene_123",
    "gametime": 0,
    "walltime": "2026-02-02T...",
    "actor_id": "user",
    "character_id": "user",
    "body": "Describe the room.",
    "metadata": {},
    "visibility": "public",
    "name": "Message"
  }
}
```

### Tracing

#### `GET /v1/tracing/status`

Returns current tracing status, configuration, and any error.

**Response:**
```json
{
  "enabled": false,
  "config": {
    "enabled": true,
    "otlp_endpoint": "http://localhost:4318",
    "capture_prompts": true,
    "capture_tool_args": true,
    "capture_memory_content": true,
    "max_attribute_length": 4096
  },
  "error": "OTLP endpoint unreachable at http://localhost:4318: [Errno 111] Connection refused"
}
```

The `error` field is `null` when tracing is healthy. A non-null value means tracing was requested but could not be enabled.

#### `POST /v1/tracing/toggle`

Enable or disable tracing at runtime. Validates the OTLP endpoint is reachable before enabling.

**Request:**
```json
{ "enabled": true }
```

**Response (success):**
```json
{ "tracing_enabled": true }
```

**Response (502 Bad Gateway):** Returned when enabling tracing but the OTLP endpoint is unreachable.
```json
{ "detail": "OTLP endpoint unreachable at http://localhost:4318: [Errno 111] Connection refused" }
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
| `character_ids` | string[] | IDs of characters participating in this scene (via `PARTICIPATES_IN` edges) |
### EventModel
All events use a single flattened model with an `event_type` discriminator.

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Event ID (e.g., `evt_abc12345`) |
| `event_type` | string | `ChatMessage`, `JoinEvent`, `LeaveEvent`, `AdjustGametime`, or `Error` |
| `scene_id` | string | Associated scene ID |
| `gametime` | int | Gametime in seconds |
| `walltime` | string | ISO timestamp of real world time |
| `actor_id` | string? | ID of the Actor who originated the event |
| `character_id` | string? | ID of the Character persona involved |
| `body` | string | Event content (message text, error description, etc.) |
| `metadata` | object | Arbitrary metadata (e.g., `widget` for entity previews) |
| `visibility` | string | `public`, `gm_only`, or `private` |
| `name` | string | Human-readable event name |

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
