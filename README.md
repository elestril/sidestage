# Sidestage

Agentic-AI tabletop-RPG assistant. Spec-driven; see `specs/`.

## Setup

One-time after `git clone`:

```bash
# Python deps + dev tooling
uv sync

# Frontend deps
cd frontend && npm install && cd -

# Task runner
cargo install just   # or `brew install just`, etc. — see https://github.com/casey/just
```

## Running

```bash
just run     # vite (background) + sidestage server (foreground)
```

Stop with `Ctrl-C`. Vite keeps running — `just stop-vite` to kill it.

## URLs

- **Dev workflow**: <http://localhost:5173> — Vite serves the React app with hot reload and proxies `/api/*` to `:8000`.
- **API only**: <http://localhost:8000/api/campaigns>, etc.
- **Production**: `just build` compiles the SPA into `src/sidestage/static/`. After that, `:8000` serves both the SPA and the API — open <http://localhost:8000>.

## Tasks

```bash
just            # list available tasks
just test       # Python + frontend
just test-py    # pytest only
just test-fe    # vitest only
just build      # bundle SPA
just spec       # regenerate specs/generated/api.md
just clean      # drop caches and build outputs
```

## Specs

Specs are the source of truth (see `specs/spec.md` for the meta-spec). Per-class invariants live in pydoc on the corresponding `.py` files; cross-cutting specs (CUJs, dataflows, REST API) live in `specs/*.md`.
