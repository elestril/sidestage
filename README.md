# Sidestage

Agentic-AI tabletop-RPG assistant. Spec-driven; see `specs/`.

## Setup

One-time after `git clone`:

```bash
# Python deps + dev tooling
uv sync

# Frontend deps (only if you'll run the Vite dev server or build the SPA)
cd frontend && npm install && cd -
```

## Running

The `dev` instance is the only configured instance today.

```bash
# Start (daemonized; PID file at .sidestage-dev.pid, logs at logs/dev.log)
bin/sidestage.sh start dev

# Stop
bin/sidestage.sh stop dev

# Run in foreground (no daemonization)
bin/sidestage.sh run dev
```

`bin/sidestage.sh` is a thin wrapper around `sidestage-ctl`. The runner:
1. Checks Vite is up at `http://localhost:5173/__vite_ping`; starts it via `npm run dev` if not.
2. Loads the first campaign found under `configs/`.
3. Launches the FastAPI server on `:8000`.

## URLs

- **Dev workflow**: open <http://localhost:5173>. Vite serves the React app with hot reload and proxies `/api/*` to `:8000`.
- **API only**: <http://localhost:8000/api/campaigns>, etc.
- **Production**: run `cd frontend && npm run build` to compile the SPA into `src/sidestage/static/`. After that, `:8000` serves both the SPA and the API from one process — open <http://localhost:8000>.

## Tests

```bash
uv run pytest
```

## Specs

Specs are the source of truth (see `specs/spec.md` for the meta-spec). Per-class invariants live in pydoc on the corresponding `.py` files; cross-cutting specs (CUJs, dataflows, REST API) live in `specs/*.md`.

Generate a clean spec view:

```bash
uv run pydoc-markdown
# Output: specs/generated/api.md (gitignored)
```
