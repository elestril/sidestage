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
    "type": "NPC",
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
  "type": "NPC" // Optional
}
```

**Response:**
```json
{ "status": "ok" }
```

#### Export Entities
**POST** `/v1/entities/export`

Exports all entities to markdown files in the campaign's `entities/` directory.

**Response:**
```json
{ "message": "Exported X entities to ..." }
```

#### Import Entities
**POST** `/v1/entities/import`

Imports entities from markdown files in the campaign's `entities/` directory.

**Response:**
```json
{ "message": "Successfully imported X entities." }
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

Sends a message to the AI agent within a specific scene context.

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
| `type` | string | Discriminator (NPC, Location, Item, Scene, Event) |

### NPC (extends Entity)
| Field | Type | Description |
|-------|------|-------------|
| `location_id` | string? | ID of current location |
| `inventory` | string[] | List of item IDs |

### Location (extends Entity)
| Field | Type | Description |
|-------|------|-------------|
| `connected_locations` | string[] | IDs of connected locations |

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
