# campaign

Implements: [sidestage#campaign](/specs/sidestage.md#campaign)

## Overview {#overview}

The orchestrator manages multiple distinct campaigns concurrently within a
single server process.

## Campaign Lifecycle {#campaign-lifecycle}

### Initialization {#campaign-init}

When a campaign is started via `sidestage <campaign_name>`:

1. The system MUST create the directory `~/.sidestage/<campaign_name>/` if it
   does not exist.
2. The system MUST connect to FalkorDB and initialize the graph schema
   (indexes, constraints, vector index). The schema MUST be versioned to
   support future migrations as the entity model evolves.
3. The system MUST create a default `config.yml` if one does not exist.
4. The system MUST load default entities (scenes, characters) from
   `data/campaign_defaults/markdown/`.

> TODO(<a id="todo-graph-chat-logs"></a>todo-graph-chat-logs): Migrate chat log
> persistence from SQLite to the graph database alongside other campaign data.

> TODO(<a id="todo-schema-versioning"></a>todo-schema-versioning): Implement graph
> schema versioning with a version marker and migration mechanism to handle
> schema evolution.

### Storage Layout {#storage-layout}

Campaign data MUST reside in `~/.sidestage/<campaign_name>/`. The directory
MUST contain:

- A FalkorDB graph for entities, relationships, and chat logs.
- A `config.yml` file for LLM and graph settings.

### Multi-Campaign Support {#multi-campaign}

The orchestrator MUST support managing multiple distinct campaigns
simultaneously. Each campaign MUST operate independently with its own storage,
graph, and configuration.

## Configuration {#config}

Campaign configuration MUST be loaded from `config.yml` within the campaign
directory. The configuration MUST include settings for:

- LLM provider and model selection.
- Graph database connection.
- Logging level.
- Tracing configuration.

## Campaign Health {#health}

The system MUST track campaign health at runtime using three states:

### Health States {#health-states}

<a id="health-healthy"></a>
- **HEALTHY** — Normal operation. Chat, embeddings, and all APIs MUST be
  available.

<a id="health-degraded"></a>
- **DEGRADED** — A non-fatal issue occurred (e.g., embedding failure,
  import/backup in progress). Chat MUST still work. Embedding generation MUST
  be paused. Import/backup endpoints MUST return `409 Conflict`.

<a id="health-unhealthy"></a>
- **UNHEALTHY** — Critical failure. The system MUST NOT serve requests.

### Health Transitions {#health-transitions}

Health state changes MUST be logged. Health changes MAY trigger callbacks for
downstream cleanup.

## Dependency Flow {#dependency-flow}

The module dependency graph MUST follow this structure:

```
server.py → orchestrator.py → campaign.py → agent.py
                                          → scene.py
                                          → character.py
                                          → graph/*
                                          → memory/*
                                          → migration/*
                                          → storage.py
                                          → tools.py
                                          → health.py
orchestrator.py → sync.py (WebSocket manager)
orchestrator.py → mcp_server.py (MCP endpoint)
orchestrator.py → request_context.py + request_context_middleware.py
server.py → tracing/* (middleware)
tracing/middleware.py → request_context.py
logging.py → request_context.py
campaign.py → config.py
scene.py → memory/context.py
agent.py → tools.py + memory/tools.py
```

> TODO(<a id="todo-rename-mcp-module"></a>todo-rename-mcp-module): Rename
> `mcp_bridge.py` to `mcp_server.py`. Remove `bus.py (EventQueue)` which is
> no longer in use.

## Data Flow {#data-flow}

1. **HTTP request** → `server.py` routes → `campaign.py` methods → `graph/*`
   for persistence.
2. **Chat message** → `server.py` → `scene.py` (assembles memory context) →
   `agent.py` (LLM call with tools) → broadcast via `sync.py`.
3. **Import** → `migration/parser.py` → `migration/validator.py` →
   `migration/importer.py` → `graph/*`.
4. **Backup** → `migration/exporter.py` → `migration/serialization.py` →
   markdown files on disk.

## Real-Time Synchronization {#realtime-sync}

### WebSocket Architecture {#websocket-arch}

All connected clients (browser windows) MUST stay in sync via WebSocket.
Changes made by the AI or other users MUST appear immediately on all connected
clients.

### Collaborative Editing {#collaborative-editing}

Multiple users MUST be able to edit entity descriptions simultaneously without
conflicts. Edits MUST be relayed via `entity_content_sync` WebSocket messages.
See [api#ws-content-sync](/specs/implementation/api.md#ws-content-sync).

> TODO(<a id="todo-entity-content-sync"></a>todo-entity-content-sync): Specify
> `entity_content_sync` message payload. See
> [api#ws-content-sync](/specs/implementation/api.md#ws-content-sync).
