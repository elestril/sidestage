# Research Findings: Tracing for Sidestage

## Part 1: Codebase Research

### 1. Project Structure and Architecture

**Project Type:** AI-powered co-author assistant for tabletop RPG campaign management
**Language/Framework:** Python 3.12+ with FastAPI backend, React 19 TypeScript frontend
**Organization:**
```
sidestage/
├── src/sidestage/              # Main Python package
│   ├── agent.py               # LiteLLMAgent (LLM integration)
│   ├── orchestrator.py         # FastAPI app + route coordination
│   ├── campaign.py            # Campaign lifecycle and LLM config
│   ├── scene.py               # Scene logic with EventQueue
│   ├── character.py           # AgentActor (NPC behavior)
│   ├── bus.py                 # EventQueue for async event processing
│   ├── schemas.py             # Pydantic data models
│   ├── config.py              # Configuration management (YAML)
│   ├── health.py              # Campaign health tracking
│   ├── storage.py             # SQLite persistence
│   ├── graph/                 # FalkorDB graph layer
│   │   ├── client.py          # Connection management
│   │   ├── entities.py        # CRUD for graph entities
│   │   ├── relationships.py   # Graph edge operations
│   │   ├── queries.py         # Domain queries
│   │   └── schema.py          # Graph initialization
│   ├── memory/                # Memory system
│   │   ├── models.py          # Memory data types
│   │   ├── store.py           # Memory CRUD in graph
│   │   ├── context.py         # Context assembly
│   │   ├── tools.py           # Memory manipulation tools
│   │   └── embeddings.py      # Vector generation
│   ├── tools.py               # WorldTools (entity CRUD for agents)
│   └── migration/             # Import/export system
├── frontend/                   # React SPA (Vite + TypeScript)
├── tests/                      # pytest suite (44+ test files)
├── data/                       # Prompt templates and defaults
├── docs/                       # API reference and architecture
└── pyproject.toml             # Dependencies
```

**Key Dependencies (from pyproject.toml):**
- `openai>=2.16.0` - OpenAI API
- `google-generativeai>=0.8.6` - Google Gemini
- `fastapi>=0.128.0` - Web framework
- `uvicorn[standard]>=0.40.0` - ASGI server
- `opentelemetry-api>=1.39.1` - **Tracing SDK (ALREADY PRESENT)**
- `opentelemetry-sdk>=1.39.1` - **Tracing SDK implementation**
- `falkordb>=1.4.0` - Graph database
- `sqlalchemy>=2.0.46` - ORM
- `litellm>=1.81.6` - LLM abstraction
- `websockets>=16.0` - Real-time sync

### 2. Scene and Event System

**Critical for tracing** - every user interaction follows this flow:

#### Event Queue Architecture (bus.py)
- **EventQueue:** Simple async queue with background worker
- **EventHandler:** Async callback processing events sequentially
- Single handler processes all events for a scene

#### Event Processing Flow (scene.py)
1. **User sends message** -> FastAPI `/v1/chat` endpoint
2. **SceneLogic.chat(user_message)** -> Puts message on EventQueue
3. **EventQueue worker** calls `_process_event()`:
   - **(a) Persist:** Save to Storage and Graph
   - **(b) Broadcast:** Send to all WebSocket clients via SyncManager
   - **(c) Dispatch:** Route to NPC AgentActors via `_dispatch_to_npcs()`

#### Event Types (schemas.py)
- **ChatMessage** - user/NPC dialogue (extends Event)
- **JoinEvent** - actor joins scene
- **LeaveEvent** - actor leaves
- **FastForwardEvent** - time jump
- All events have: `id`, `scene_id`, `gametime`, `walltime`

### 3. LLM Integration and Agent System

#### LiteLLMAgent (agent.py)
Wrapper around litellm supporting multiple providers:
- `async def arun(message, context) -> AgentResponse`
- Tool support: dynamically converts Python functions to OpenAI tool schemas
- Tool calls handled in agentic loop (up to 5 turns)

#### Character Agents (character.py: AgentActor)
- Each character gets its own `LiteLLMAgent` instance
- Prompt templates in `data/prompts/` (`default_npc.txt`, `unseen_npc.txt`)
- `on_event(ChatMessage)` -> agent generates response -> puts reply on EventQueue

#### Prompt Assembly (memory/context.py)
- Token Budget: Default 4096 tokens, 20% allocated to chat history
- Memory sections: world facts, common scene memory, private scene memory, character memories, recent chat

### 4. Memory System

#### Memory Models (memory/models.py)
- Memory types: SCENE | CHARACTER | WORLD_FACT
- Visibility: "common" or "private"
- Stored in FalkorDB graph with vector embeddings

#### Memory Tools (memory/tools.py)
- `MemoryTools` - per-character memory operations (update_scene_memory, update_character_memory)
- `DmMemoryTools` - DM/Co-Author memory (update_common_memory, update_canonical_memory, add_world_fact)
- Background embedding via `asyncio.create_task(embed_and_update(...))`

### 5. Configuration System

#### Config Flow
- **File:** `~/.sidestage/<campaign_name>/config.yml`
- **Model:** `SidestageConfig` (Pydantic BaseModel) with loglevel, llms, graph sections
- **Singleton:** `config.init()` / `config.get()`

### 6. UI/Frontend

- **Framework:** React 19 with TypeScript, Vite build
- **Styling:** Tailwind CSS v4
- **Editor:** TipTap v3
- **State:** AppContext with WebSocket connection management
- **Routes:** `/sidestage/scenes/:sceneId`, `/sidestage/entities/:entityId`
- **WebSocket:** `/v1/ws` for real-time sync (chat_message, entities_updated, scene_updated)

### 7. Testing Setup

- **Framework:** pytest v9+ with pytest-anyio for async tests
- **Structure:** 44+ test files in `tests/unit/`, `tests/integration/`, `tests/meta/`
- **Key fixture:** `_init_config(tmp_path)` for per-test config initialization
- **LLM tests:** `@pytest.mark.llm` marker, auto-skipped if LLM unreachable

### 8. Existing Logging

- **114 log calls across 19 files** using Python `logging` module
- File logging to `~/.sidestage/<campaign_name>/server.log`
- Configurable level via config.yml

### 9. Critical Integration Points for Tracing

```
HTTP POST /v1/chat
  -> orchestrator.chat_endpoint()
  -> scene.chat(user_message)
  -> EventQueue.put(user_message)
  -> EventQueue worker: _process_event()
    |-- Persist (Storage/Graph)
    |-- Broadcast (WebSocket)
    |-- Dispatch to NPCs
  -> AgentActor.on_event()
  -> agent.arun() (LLM call)
  -> Scene.queue.put(reply_message)
  -> _process_event() again
  -> Broadcast to clients
```

---

## Part 2: Web Research - OpenTelemetry Python Tracing

### Core Setup
- `opentelemetry-api` and `opentelemetry-sdk` already in pyproject.toml
- Standard init: `TracerProvider` -> `SpanProcessor` -> `Exporter` -> register globally
- For Sidestage (low-volume game tool): `SimpleSpanProcessor` is appropriate (immediate export, no batching complexity)

### Creating Spans and Attributes
- Context manager: `with tracer.start_as_current_span("name") as span:`
- Attribute naming: lowercase dot-separated namespaces (e.g., `sidestage.scene.id`)
- Use `gen_ai.*` semantic conventions for LLM attributes (emerging standard)

### Span Events for Large Data
- Full prompts/completions should use `span.add_event()` not attributes
- Token counts, model names as attributes (small, always useful)

### Context Propagation in Async Code
- OpenTelemetry uses `contextvars` internally - works with asyncio automatically
- `asyncio.create_task()` copies context (since Python 3.7)
- For explicit control, use `context.get_current()` + `attach()`

### Exporters for Local Use
1. **In-Memory Exporter** (primary) - ring-buffer for serving via API to React frontend
2. **File Exporter** (optional) - JSON files per trace for persistence
3. **Console Exporter** - for debugging

### Manual vs Auto-Instrumentation
**Recommendation: Manual instrumentation** because:
- Auto-instrumentation captures generic HTTP-level data, not game-specific attributes
- The agent loop has complex multi-turn logic needing semantic understanding
- Memory tools, context assembly are custom business logic
- Codebase is small enough that 5-8 instrumentation points provide full coverage

---

## Part 3: Web Research - LLM Observability Patterns

### Standard Span Structure for Agent Systems
```
[Root Span: "scene.process_event"]
  |-- [Span: "agent.on_event" (character="Gandalf")]
  |     |-- [Span: "memory.assemble_context"]
  |     |-- [Span: "llm.completion" (turn=1)]
  |     |     |-- Event: gen_ai.prompt (system)
  |     |     |-- Event: gen_ai.completion (assistant, tool_calls)
  |     |-- [Span: "tool.execute" (tool="update_scene_memory")]
  |     |-- [Span: "llm.completion" (turn=2)]
  |-- [Span: "agent.on_event" (character="Aragorn")]
```

### Key Attributes per Layer
- **LLM calls:** `gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
- **Tool calls:** `tool.name`, `tool.arguments`, `tool.result`, `tool.status`
- **Agent:** `agent.name`, `agent.turn_count`, `agent.total_tokens`
- **Scene/Event:** `sidestage.scene.id`, `sidestage.event.id`, `sidestage.event.type`

### What to Capture vs. Skip
- **Always:** model name, token counts, latency, tool names, errors, identifiers
- **Conditional (config flag):** full prompts, completions, tool arguments, memory content
- **Never:** raw embedding vectors, API keys, binary content

### Existing Libraries Evaluated
- **OpenLLMetry** (Traceloop) - auto-instrumentation for LLM frameworks. Not recommended (manual gives more control).
- **Arize Phoenix** - heavyweight dependency. Not recommended.
- **LangFuse** - requires PostgreSQL. Too heavy.
- **Recommendation:** Manual OTel instrumentation with `gen_ai.*` conventions

---

## Part 4: Web Research - Trace Viewer UI

### Finding: No Standalone React Trace Viewer Library Exists
- Jaeger UI, Grafana, Zipkin are all full applications, not embeddable components
- `react-flame-graph` is for CPU profiling, not trace visualization

### Recommended: Custom Component
- Trace structures are simple (5-50 spans per trace)
- Existing stack (React 19, Tailwind CSS) provides everything needed
- No additional frontend dependencies required

### Component Architecture
```
TraceViewer
  |-- TraceList          (filterable by scene)
  |-- TraceDetail
        |-- TraceTimeline      (waterfall/timeline view)
        |     |-- SpanBar      (nested by depth)
        |-- SpanDetailPanel
              |-- AttributeTable
              |-- EventList
              |-- PromptViewer
```

### Key UX Patterns (from Jaeger, Zipkin, Arize Phoenix)
1. Collapsible tree with expand/collapse
2. Click-to-inspect span detail panel
3. Duration labels on bars
4. Relative timing (all bars relative to trace start)
5. Color coding by type (LLM=blue, tool=green, memory=orange, error=red)
6. Prompt viewer with markdown rendering

---

## Synthesis: Architecture Recommendation

```
┌─────────────────────────────────────────────────────┐
│                Sidestage Backend                     │
│                                                     │
│  TracerProvider -> SimpleSpanProcessor               │
│       |              -> InMemoryTraceExporter        │
│  [manual instrumentation]        |                  │
│  EventQueue._worker()     /v1/traces API            │
│  AgentActor.on_event()    GET /traces               │
│  LiteLLMAgent.arun()      GET /traces/:id           │
│  tool execution                  |                  │
│  memory operations               |                  │
└──────────────────────────────────┼──────────────────┘
                                   v
                          React TraceViewer
                          (custom component)
```

### Key Decisions
1. **Manual instrumentation** for full control
2. **In-memory exporter** as primary (serves the UI)
3. **Config-driven** tracing (enabled/disabled via config.yml + UI toggle)
4. **Custom trace viewer** (React/Tailwind, no new deps)
5. **`gen_ai.*` semantic conventions** for LLM attributes
6. **Span events** for large text (prompts/completions)
7. **No additional Python or frontend packages needed**
