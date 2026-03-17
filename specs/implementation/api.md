# api

Implements: [sidestage#actor-user](/specs/sidestage.md#actor-user),
[debugging#mcp-interface](/specs/debugging.md#mcp-interface)

## Overview {#overview}

The server exposes a JSON REST API, a WebSocket protocol for real-time
updates, and an MCP endpoint for AI client integration. The default base URL
is `http://localhost:8000`.

## MCP (Model Context Protocol) {#mcp}

### Endpoint {#mcp-endpoint}

<a id="mcp-url"></a>
The server MUST expose an MCP endpoint at `/v1/mcp` using Streamable HTTP
transport. The MCP server is served by the sidestage binary so that external
coding agents can interact with the campaign.

<a id="mcp-in-process"></a>
The MCP endpoint MUST run inside the same FastAPI server — no separate process
or proxy.

### Available Tools {#mcp-tools}

The MCP endpoint MUST expose the same tools that are available to in-game
agents (see [agent#agent-tools](/specs/implementation/agent.md#agent-tools)), plus the
following administrative tools for external coding agents:

| Tool                    | Description                                     |
|-------------------------|-------------------------------------------------|
| `update_entity_markdown`| Update entity from markdown with YAML frontmatter|
| `update_entity`         | Update specific entity fields (JSON string)      |
| `reload_defaults`       | Reload default entities from data directory      |
| `import_campaign`       | Two-phase campaign import (validate/execute)     |
| `backup_campaign`       | Backup campaign to markdown directory            |
| `create_scene`          | Create a new scene                               |

## WebSocket Protocol {#websocket}

### Endpoint {#ws-endpoint}

<a id="ws-url"></a>
The WebSocket endpoint MUST be at `/v1/ws`.

### Server-to-Client Messages {#ws-server-messages}

#### Entity Update {#ws-entities-updated}

MUST be sent when any entity is created or updated via tools or API.

```json
{
  "type": "entities_updated"
}
```

#### Scene Update {#ws-scene-updated}

MUST be sent when a scene is created or updated.

```json
{
  "type": "scene_updated"
}
```

#### Event {#ws-event}

MUST be broadcast when an event is created in a scene (chat messages, joins,
errors, etc.).

```json
{
  "type": "event",
  "scene_id": "scene_id",
  "event": {
    "id": "evt_abc12345",
    "type": "Event",
    "name": "",
    "event_type": "ChatMessage",
    "scene_id": "scene_id",
    "gametime": 12345,
    "character_id": "char_1",
    "body": "Hello world",
    "metadata": {},
    "visibility": "public"
  }
}
```

#### Actor Status {#ws-actor-status}

MUST be sent when an actor starts or finishes processing an event.

```json
{
  "type": "actor_status",
  "character_id": "char_1",
  "scene_id": "scene_id",
  "status": "thinking"
}
```

#### Content Sync {#ws-content-sync}

> TODO(<a id="todo-entity-content-sync"></a>todo-entity-content-sync): Specify the
> `entity_content_sync` message payload (entity ID, diff, or content) for
> collaborative editing relay between clients.

## REST API {#rest-api}

### Entities {#rest-entities}

#### List Entities {#rest-list-entities}

**GET** `/v1/entities`

MUST return a list of all entities in the campaign.

**Response:** `List[EntityModel]`

#### Get Entity Markdown {#rest-get-entity-markdown}

**GET** `/v1/entities/{entity_id}/markdown`

MUST return the full markdown representation of an entity (including
frontmatter).

**Response:**
```json
{
  "markdown": "---\nname: Example\n...\n"
}
```

#### Update Entity Markdown {#rest-update-entity-markdown}

**POST** `/v1/entities/{entity_id}/markdown`

MUST update an entity entirely from its markdown representation.

**Request:**
```json
{
  "markdown": "---\nname: Example\n...\n"
}
```

**Response:**
```json
{ "status": "ok" }
```

#### Update Entity Data {#rest-update-entity}

**POST** `/v1/entities/{entity_id}`

MUST update specific fields of an entity. The `type` field is optional if it
can be inferred.

**Request:**
```json
{
  "name": "Updated Name",
  "type": "Character"
}
```

**Response:**
```json
{ "status": "ok" }
```

#### Export Entities (Legacy) {#rest-export-entities}

**POST** `/v1/entities/export`

Exports all entities to markdown files in the campaign's `entities/` directory.

<a id="export-entities-deprecated"></a>
This endpoint is DEPRECATED — use `POST /v1/campaign/backup` instead.

#### Import Entities (Legacy) {#rest-import-entities}

**POST** `/v1/entities/import`

Imports entities from markdown files in the campaign's `entities/` directory.

<a id="import-entities-deprecated"></a>
This endpoint is DEPRECATED — use `POST /v1/campaign/import` instead.

#### Reload Defaults {#rest-reload-defaults}

**POST** `/v1/campaign/reload-defaults`

MUST reload default entities from `data/campaign_defaults/markdown/` into the
campaign.

**Response:**
```json
{ "status": "ok" }
```

### Campaign Migration {#rest-migration}

#### Import Campaign {#rest-import-campaign}

**POST** `/v1/campaign/import`

Two-phase import from the campaign's `markdown/` directory tree.

<a id="import-destructive"></a>
The import MUST be destructive — it drops and recreates the graph.

<a id="import-conflict"></a>
MUST return `409 Conflict` if campaign health is DEGRADED.

**Request:**
```json
{
  "action": "validate",
  "force": false
}
```

The `action` field MUST be either `"validate"` or `"execute"`. The `force`
field MAY skip validation on execute (default `false`).

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
    "warnings": []
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

#### Backup Campaign {#rest-backup-campaign}

**POST** `/v1/campaign/backup`

MUST export all entities, relationships, memories, and chat logs to the
`markdown/` directory tree with atomic swap. MUST write a `status.json` with
backup metadata.

<a id="backup-conflict"></a>
MUST return `409 Conflict` if campaign health is DEGRADED.

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

### Scenes {#rest-scenes}

#### List Scenes {#rest-list-scenes}

**GET** `/v1/scenes`

MUST return a list of all scenes.

**Response:** `List[SceneModel]`

#### Create Scene {#rest-create-scene}

**POST** `/v1/scenes`

MUST create a new scene. The `description` field maps to the entity `body`
field.

**Request:**
```json
{
  "name": "Scene Name",
  "description": "Scene description.",
  "start_gametime": 100000,
  "current_gametime": 123456,
  "end_gametime": 234567
}
```

> TODO(<a id="todo-scene-creation-fields"></a>todo-scene-creation-fields): Accept
> `start_gametime`, `end_gametime`, and `location_ids` on scene creation.

**Response:** `SceneModel`

#### List Scene Characters {#rest-scene-characters}

**GET** `/v1/scenes/{scene_id}/characters`

MUST return characters participating in the scene (via `PARTICIPATES_IN`
edges).

**Response:** `List[CharacterModel]`

#### Add Character to Scene {#rest-join-scene}

**POST** `/v1/scenes/{scene_id}/characters/{character_id}`

MUST create a `PARTICIPATES_IN` edge and broadcast a `scene_updated` WebSocket
event.

**Response (201):**
```json
{ "status": "ok" }
```

#### Remove Character from Scene {#rest-leave-scene}

**DELETE** `/v1/scenes/{scene_id}/characters/{character_id}`

MUST remove the `PARTICIPATES_IN` edge and broadcast a `scene_updated`
WebSocket event.

**Response:**
```json
{ "status": "ok" }
```

#### Get Scene Messages {#rest-scene-messages}

**GET** `/v1/scenes/{scene_id}/messages`

MUST return the message history for a scene.

**Response:** `List[Event]`

> TODO(<a id="todo-event-entity-response"></a>todo-event-entity-response):
> Return Event entities conforming to the base entity structure instead of
> `List[EventModel]`.

### Chat {#rest-chat}

#### Send Chat Message {#rest-send-chat}

**POST** `/v1/chat`

MUST send a message to the agent within a specific scene context. The agent's
prompt MUST be enriched with assembled memory context before responding.

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
    "type": "Event",
    "name": "",
    "event_type": "ChatMessage",
    "scene_id": "scene_123",
    "gametime": 0,
    "character_id": "char_1",
    "body": "Describe the room.",
    "metadata": {},
    "visibility": "public"
  }
}
```

### Tracing {#rest-tracing}

#### Get Tracing Status {#rest-tracing-status}

**GET** `/v1/tracing/status`

MUST return current tracing status, configuration, and any error.

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
  "error": null
}
```

The `error` field MUST be `null` when tracing is healthy. A non-null value
MUST indicate tracing was requested but could not be enabled.

#### Toggle Tracing {#rest-tracing-toggle}

**POST** `/v1/tracing/toggle`

MUST enable or disable tracing at runtime.

<a id="tracing-toggle-validation"></a>
MUST validate that the OTLP endpoint is reachable before enabling.

**Request:**
```json
{ "enabled": true }
```

**Response (success):**
```json
{ "tracing_enabled": true }
```

<a id="tracing-toggle-502"></a>
MUST return `502 Bad Gateway` when enabling tracing but the OTLP endpoint is
unreachable.
