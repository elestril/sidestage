# Sidestage

Agentic-AI tabletop-RPG assistant. Spec-driven; see `specs/`.

## Setup

One-time after `git clone`:

```bash
# Task runner — needed first; everything else is `just …`.
cargo install just   # or `brew install just`, etc. — see https://github.com/casey/just

# Python deps + frontend deps + Playwright (+ Chromium) + git pre-commit hook.
just setup
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
just              # list available tasks
just setup        # one-shot install (deps + hooks); idempotent
just test         # lint + Python + frontend (parallel, ~3s)
just test-all     # adds browser e2e — what the pre-commit hook runs
just test-browser # Playwright + Chromium against the built SPA
just lint         # ruff + pyright + tsc, all linters & type checks
just format       # apply ruff fixes + formatter
just build        # bundle SPA into src/sidestage/static/
just spec         # regenerate specs/generated/api.md
just clean        # drop caches and build outputs
```

A `pre-commit` hook runs `just test-all` before every commit (installed
by `just setup`). Skip with `git commit --no-verify` only when you
genuinely need to.

## Specs

Specs are the source of truth (see `specs/spec.md` for the meta-spec). Per-class invariants live in pydoc on the corresponding `.py` files; cross-cutting specs (CUJs, dataflows, REST API) live in `specs/*.md`.
