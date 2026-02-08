# Sidestage — AI Agent Instructions

Sidestage is a real-time, AI-enhanced tabletop RPG campaign manager. Python/FastAPI backend, React SPA frontend, FalkorDB graph database, SQLite for chat logs.

## Mandatory: Documentation Workflow

**Before reading source code**, read the relevant documentation first:

1. Start with `docs/architecture.md` for the source-to-doc map
2. Read the relevant `docs/*.md` file for domain context
3. Read the relevant `docs/api/<module>.md` for function signatures
4. Then read the actual source code

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

While working, you can run a dev server against `./sidestage.dev/`

```
cd sidestage.dev && ./run.sh

```
