# Architecture — Source to Documentation Map

## Module Index

| Source file | API doc | Description |
|---|---|---|
| `src/sidestage/server.py` | `docs/api/sidestage.server.md` | FastAPI app factory, CLI entry point, Uvicorn launcher |
| `src/sidestage/orchestrator.py` | `docs/api/sidestage.orchestrator.md` | Multi-campaign lifecycle manager, startup/shutdown |
| `src/sidestage/campaign.py` | `docs/api/sidestage.campaign.md` | Campaign container: config, storage, agent, entity ops |
| `src/sidestage/agent.py` | `docs/api/sidestage.agent.md` | LiteLLM-based AI agent with tool use |
| `src/sidestage/scene.py` | `docs/api/sidestage.scene.md` | Scene logic: chat flow, context assembly, message persistence |
| `src/sidestage/entities.py` | `docs/api/sidestage.entities.md` | Entity ↔ markdown serialization |
| `src/sidestage/schemas.py` | `docs/api/sidestage.schemas.md` | Pydantic models: Entity, Character, Location, Scene, Event, etc. |
| `src/sidestage/config.py` | `docs/api/sidestage.config.md` | Config loading from `config.yml` |
| `src/sidestage/bus.py` | `docs/api/sidestage.bus.md` | EventQueue for decoupled internal events |
| `src/sidestage/storage.py` | `docs/api/sidestage.storage.md` | SQLite storage for chat logs |
| `src/sidestage/sync.py` | `docs/api/sidestage.sync.md` | WebSocket connection manager, broadcast |
| `src/sidestage/health.py` | `docs/api/sidestage.health.md` | Campaign health states (HEALTHY/DEGRADED/UNHEALTHY) |
| `src/sidestage/character.py` | `docs/api/sidestage.character.md` | Character-specific logic |
| `src/sidestage/time.py` | `docs/api/sidestage.time.md` | Gametime formatting and tracking |
| `src/sidestage/tools.py` | `docs/api/sidestage.tools.md` | Agent tool definitions (entity queries, memory updates) |

### Graph subpackage (`src/sidestage/graph/`)

| Source file | API doc | Description |
|---|---|---|
| `graph/client.py` | `docs/api/sidestage.graph.client.md` | Async FalkorDB client wrapper |
| `graph/schema.py` | `docs/api/sidestage.graph.schema.md` | Graph schema versioning, indexes, constraints |
| `graph/entities.py` | `docs/api/sidestage.graph.entities.md` | Entity CRUD on graph nodes |
| `graph/queries.py` | `docs/api/sidestage.graph.queries.md` | Domain queries (characters at location, subgraph, etc.) |
| `graph/relationships.py` | `docs/api/sidestage.graph.relationships.md` | Relationship edge management |
| `graph/errors.py` | `docs/api/sidestage.graph.errors.md` | Graph-specific exceptions |

### Memory subpackage (`src/sidestage/memory/`)

| Source file | API doc | Description |
|---|---|---|
| `memory/models.py` | `docs/api/sidestage.memory.models.md` | Memory Pydantic model, types, visibility |
| `memory/store.py` | `docs/api/sidestage.memory.store.md` | Memory CRUD on graph nodes |
| `memory/context.py` | `docs/api/sidestage.memory.context.md` | Context assembly with token budgeting |
| `memory/embeddings.py` | `docs/api/sidestage.memory.embeddings.md` | Vector embedding generation via LiteLLM |
| `memory/tools.py` | `docs/api/sidestage.memory.tools.md` | Agent memory tools (update scene, character, world) |

### Migration subpackage (`src/sidestage/migration/`)

| Source file | API doc | Description |
|---|---|---|
| `migration/parser.py` | `docs/api/sidestage.migration.parser.md` | Parse markdown directory tree into entities |
| `migration/importer.py` | `docs/api/sidestage.migration.importer.md` | Two-phase import (validate → execute) |
| `migration/exporter.py` | `docs/api/sidestage.migration.exporter.md` | Atomic backup to markdown directory |
| `migration/validator.py` | `docs/api/sidestage.migration.validator.md` | Cross-reference validation |
| `migration/serialization.py` | `docs/api/sidestage.migration.serialization.md` | Entity/memory serialization for export |
| `migration/models.py` | `docs/api/sidestage.migration.models.md` | Import/export result models |

### Tracing subpackage (`src/sidestage/tracing/`)

| Source file | API doc | Description |
|---|---|---|
| `tracing/provider.py` | `docs/api/sidestage.tracing.provider.md` | OpenTelemetry provider setup and configuration |
| `tracing/middleware.py` | `docs/api/sidestage.tracing.middleware.md` | FastAPI middleware for request tracing |

## Dependency Flow

```
server.py → orchestrator.py → campaign.py → agent.py
                                          → scene.py
                                          → graph/*
                                          → memory/*
                                          → migration/*
                                          → storage.py
                                          → tools.py
                                          → health.py
orchestrator.py → sync.py (WebSocket manager)
server.py → tracing/* (middleware)
campaign.py → config.py
campaign.py → bus.py (EventQueue)
scene.py → memory/context.py (context assembly)
agent.py → tools.py + memory/tools.py (tool definitions)
```

## Key Data Flow

1. **HTTP request** → `server.py` routes → `campaign.py` methods → `graph/*` for persistence
2. **Chat message** → `server.py` → `scene.py` (assembles memory context) → `agent.py` (LLM call with tools) → broadcast via `sync.py`
3. **Import** → `migration/parser.py` → `migration/validator.py` → `migration/importer.py` → `graph/*`
4. **Backup** → `migration/exporter.py` → `migration/serialization.py` → markdown files on disk
