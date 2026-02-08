# Specification: Tracing Support for Sidestage

## Overview

Implement end-to-end tracing for Sidestage, an AI-powered tabletop RPG co-author tool. Every event arriving at a Scene triggers a new trace. Traces capture the full lifecycle of event processing: LLM calls (with full prompts and parameters), memory reads/writes, tool calls, embedding generation, and all nested operations.

## Core Requirements

### Trace Lifecycle
- Every event arriving at a Scene's EventQueue creates a **new independent trace**
- Each trace captures: event processing, persistence, broadcast, NPC dispatch, LLM calls, tool calls, memory operations, and background embedding
- Traces support **nested spans** for operations like multi-turn agent loops, nested LLM calls, and sub-agent invocations (e.g., DM agent reviewing NPC actions)
- Background embedding tasks (`_fire_embed` via `asyncio.create_task`) are included in the parent trace via context propagation

### Instrumentation
- Use **OpenTelemetry** for instrumentation (opentelemetry-api and opentelemetry-sdk already in pyproject.toml)
- **Manual instrumentation** at key points (not auto-instrumentation) for full control over game-specific attributes
- Follow `gen_ai.*` OpenTelemetry semantic conventions for LLM-related attributes
- Use span events (not attributes) for large text data like prompts and completions

### Instrumentation Points
1. **EventQueue._worker / SceneLogic._process_event** - Root span per event
2. **SceneLogic._dispatch_to_npcs** - Span for NPC dispatch
3. **AgentActor.on_event** - Span per character agent reaction
4. **memory.context.assemble_context** - Span for context assembly
5. **LiteLLMAgent.arun** - Span per agent run (wrapping multi-turn loop)
6. **Each litellm.acompletion call** - Span per LLM API call with prompt/completion events
7. **Tool execution** - Span per tool call within the agent loop
8. **embed_and_update** - Span for background embedding (linked to parent trace)

### Configuration
- Tracing enabled/disabled via `config.yml` with a `tracing` section
- Default is configurable (off by default)
- When tracing is OFF, use OTel's `NoOpTracerProvider` for **zero overhead**
- A `TraceConfig` model controls: enabled, capture_prompts, capture_tool_args, capture_memory_content, max_attribute_length

### Trace Storage
- **In-memory ring buffer** exporter for serving live data to the UI
- **SQLite persistence** for traces to survive server restarts (using the existing SQLite infrastructure)
- Both exporters registered on the same TracerProvider

### API Endpoints
- `GET /v1/traces?scene_id=<id>` - List traces for a scene
- `GET /v1/traces/<trace_id>` - Get full trace detail with all spans
- `POST /v1/tracing/toggle` - Enable/disable tracing at runtime
- `GET /v1/tracing/status` - Get current tracing state

### Frontend: Trace Viewer
- **Dedicated route** at `/sidestage/traces` with a full-screen trace viewer
- Route supports `/sidestage/traces/<scene_id>/<trace_id>` for deep linking
- **Trace list**: Filterable by scene, shows trace summary (event type, duration, timestamp, span count)
- **Trace detail**: Waterfall/timeline view with nested spans
- **Span detail panel**: Attributes, events, full collapsible prompt/completion content
- Color coding by span type (LLM=blue/purple, tool=green, memory=orange, error=red)
- Collapsible tree with expand/collapse for nested spans

### Frontend: Chat Debug Mode
- Toggle switch in chat panel to enable "debug mode"
- When enabled, each chat bubble shows a small link icon
- Link icon navigates directly to `/sidestage/traces/<scene_id>/<trace_id>` for that message's trace
- Chat messages need to carry a `trace_id` field when tracing is active

### Real-time Updates
- Trace viewer updates live as spans complete via **WebSocket**
- Use existing `/v1/ws` WebSocket infrastructure with new message types for trace data
- New WebSocket message types: `trace_started`, `span_completed`, `trace_completed`

## Technical Constraints
- Python 3.12+ async codebase (FastAPI + asyncio)
- OpenTelemetry API/SDK already available as dependencies
- React 19 + TypeScript + Tailwind CSS v4 frontend (no new frontend dependencies)
- Existing WebSocket sync infrastructure via SyncManager
- No external trace backends (Jaeger, Zipkin, etc.) - self-contained

## Non-Goals
- Auto-instrumentation of HTTP/DB libraries
- External trace export (OTLP to external collectors)
- Distributed tracing across multiple services
- Tracing the Co-Author agent (worldbuilding chat) - only scene/NPC event flow
