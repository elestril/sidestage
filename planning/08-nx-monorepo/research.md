# Track 08 Research: Nx Monorepo

## Current Project Structure

```
sidestage/
├── src/sidestage/          # Python backend (FastAPI)
├── frontend/               # React/Vite SPA
│   ├── package.json        # name: sidestage-frontend
│   ├── vite.config.ts
│   └── src/
├── tests/
│   ├── unit/
│   └── integration/
├── sidestage.dev/          # Dev instance working dir (gitignored)
├── scripts/dev_instance.sh # Dev server launcher
├── agent-project/          # Git submodule
│   └── agent-project.json  # MCP gateway tool config
├── pyproject.toml          # Backend: sidestage v0.4.0, Python >=3.12
└── .gitignore              # Already ignores node_modules/, sidestage.dev/
```

## Existing Tool Commands

### Backend (from agent-project.json)
- `uv run pytest tests/` — 1000+ tests
- `uv run ruff check src/ tests/` — linting
- `uv run ruff format src/ tests/` — formatting
- `uv run pyright src/` — type checking
- `uv sync` — install deps
- `uv build` — build Python package

### Frontend (from frontend/package.json)
- `npm run build` → `vite build`
- `npm run dev` → `vite`
- `npm run lint` → `eslint .`
- `npm run typecheck` → `tsc --noEmit`

## Key Observations
- No root `package.json` — Nx not installed
- No `nx.json` — fresh start
- `.gitignore` already ignores `node_modules/`
- No `tests/e2e/` directory yet
- Frontend uses Vite 6, React 18, TypeScript 5.6
- `sidestage.dev/` is gitignored (dev instance working directory)

## Lessons from Previous Attempt
- `npm install nx` can trigger `nx init` which overwrites `project.json`
- Use `npm install --ignore-scripts` to prevent this, then write project.json after
- Verify file state with bash, not gateway MCP (caching issues)
- Nx 20.x is latest stable (21.x not released)
