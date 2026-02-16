# Sidestage — AI Agent Instructions

Sidestage is a real-time, AI-enhanced tabletop RPG campaign manager. Python/FastAPI backend, React SPA frontend, FalkorDB graph database, SQLite for chat logs.

## CRITICAL: Research Workflow

**DO NOT explore or read source code until you have consulted docs and the code index.** This applies to every task, including when using Explore agents or planning.

Follow this order strictly:

1. **Read `docs/architecture.md`** — source-to-doc map, module overview
2. **Read the relevant `docs/*.md`** — domain context for the area you're working in
4. **Use the code-index MCP** to locate symbols, files, and call sites before reading source
5. **Only then** read actual source code

### Code Index MCP

A `code-index` MCP server is configured in `.mcp.json`. Use it to navigate the codebase efficiently:

- **`find_files(pattern)`** — find files by glob (e.g. `"*.py"`, `"test_*.py"`, `"provider.py"`)
- **`search_code_advanced(pattern)`** — regex search across files (like grep but indexed)
- **`get_file_summary(file_path)`** — line count, functions, classes, imports for a file
- **`get_symbol_body(file_path, symbol_name)`** — get the source of a specific function/class without reading the whole file

Prefer these over `Glob`/`Grep`/`Read` when possible — they are faster and keep context small.

**After changing any code**, update documentation to reflect the new behavior:

| What changed | Update |
|---|---|
| Python module API (new/changed functions, classes, signatures) | `docs/api/sidestage.<module>.md` |
| HTTP endpoints or WebSocket messages | `docs/http-api.md` |
| Data models (Entity, Memory, etc.) | `docs/http-api.md` (Data Models section) |
| New feature or changed behavior | `docs/features.md` |
| Observability, logging, tracing, health | `docs/observability.md` |
| UI layout, routes, components | `docs/ui_structure.md` |
| User workflows | `docs/user_journeys.md` |
| Markdown import/export format | `docs/http-api.md` (Markdown Directory Layout section) |
| New module added | Create `docs/api/sidestage.<module>.md`, add to `docs/api/index.md`, add to `docs/architecture.md` |

## Documentation Map

See `docs/architecture.md` for the complete source file to documentation file mapping.

### docs/ structure

| File | Purpose |
|---|---|
| `docs/architecture.md` | Source-to-doc map, module descriptions, dependency graph |
| `docs/http-api.md` | REST + WebSocket API reference, data models, file formats |
| `docs/features.md` | Feature overview — what the system does |
| `docs/observability.md` | Logging, health tracking, tracing |
| `docs/ui_structure.md` | Frontend layout, routes, components |
| `docs/user_journeys.md` | End-to-end user workflows |
| `docs/dev_instance.md` | Local development setup guide |
| `docs/api/` | Per-module Python API docs (classes, functions, signatures) |
| `docs/api/index.md` | Index of all module API docs |

## Project Conventions

- **Python 3.12+**, managed with `uv`. Run: `uv sync`, `uv run sidestage dev`
- **Tests**: `uv run pytest tests/` — unit tests in `tests/unit/`, integration in `tests/integration/`
- **Type checking**: `uv run pyright src/`
- **Pydantic models** for all data structures (`src/sidestage/schemas.py`, `src/sidestage/memory/models.py`)
- **Async throughout** — FastAPI async endpoints, async graph client, async agent
- **Graph patterns**: Entities as multi-label FalkorDB nodes (`:Entity:Character`), relationships as typed edges
- **Memory visibility**: `common` (everyone sees) or `private` (owner only)
- **Campaign data dir**: `~/.sidestage/<campaign_name>/`
- **Default entities**: loaded from `data/campaign_defaults/markdown/`

## Dev Instance

There is a dev instance, with working directory `./sidestage.dev/` , which uses uvicorn's `reload=true` and thus always has the current state of the repository running. Your mcp server grants direct access to this instance, and you should read it's logs as appropriate.

- Constantly monitor the dev instannce for unexpected behavior everytime you change anything.
- If the mcp server isn't responding, you must ask the user to start the dev instance.