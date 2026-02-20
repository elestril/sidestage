# Track 08: Nx Monorepo Build System

## Type
Chore

## Description
Set up Nx as the monorepo build system for sidestage. Four projects wrap existing tools via `nx:run-commands` — no new build tooling, just unified task orchestration with caching and dependency awareness.

## Projects

| Project | Root | Type | Tools Wrapped |
|---------|------|------|--------------|
| backend | `.` | application | uv run pytest, ruff, pyright |
| frontend | `frontend/` | application | npm run build/lint/typecheck (Vite) |
| dev-instance | `sidestage.dev/` | application | Dev server orchestration |
| e2e | `tests/e2e/` | library | E2E test runner (scaffold only) |

## Constraints
- **Wrap commands only** — no install targets, no @nx/* packages beyond core
- **Dev instance always runs in dev mode** — uvicorn reload, frontend from source, no build dependency
- **Nx packages production instances** — `nx build frontend` produces dist/
- **Use `command` shorthand** in project.json targets (Nx 20+ feature)
- **Named inputs** for cache invalidation granularity (python-source, python-tests, frontend-source)

## User Decisions (from previous session)
- Track type: Chore
- Dependency management: Wrap commands only (no install targets)
- Dev instance: Always dev mode, Nx for production builds
- Scope: Full monorepo including dev orchestration and E2E
