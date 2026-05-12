#
# Sidestage tasks. Run `just` (no args) to list. `just <target>` to run.
#

# Default: list available targets.
default:
    @just --list

_deps-setup:
    uv sync
    cd frontend && npm install
    cd tests/playwright && npm install
    cd tests/playwright && npm run -s install-chromium
    @echo "Dependencies installed"

_git-setup:
    @mkdir -p .git/hooks
    @ln -sf ../../bin/pre-commit-hook .git/hooks/pre-commit
    @echo "pre-commit hook installed → .git/hooks/pre-commit"


# One-shot setup after `git clone`: deps + git hooks. Idempotent.
setup: _deps-setup  _git-setup 
    @echo "Setup complete"


# -------- tests --------

# Inner-loop suite: lint + Python tests + frontend tests, all in parallel.
[parallel]
test: lint test-py test-fe

# Every tier including browser e2e — pre-commit / CI path.
test-all: test test-browser

# Pre-commit gate — wired into `.git/hooks/pre-commit` by `just setup`.
# Alias for `test-all` today; named separately so the hook contract is
# stable even if the underlying recipe changes.
precommit: test-all

# All linters and type checks (ruff + pyright + tsc), parallel sub-tasks.
[parallel]
lint: _ruff-check _ruff-format-check _pyright _tsc

_ruff-check:
    uv run ruff check src/ tests/

_ruff-format-check:
    uv run ruff format --check src/ tests/

_pyright:
    uv run pyright src/ tests/

_tsc: _gen-types
    cd frontend && npm run typecheck

# Regenerate frontend/src/types.ts from the Pydantic wire models.
# frontend/src/types.ts is gitignored; every consumer (tsc, vitest,
# vite build, vite dev) depends on this recipe so the file is always
# fresh against the current backend. json2ts is the npm binary from
# json-schema-to-typescript (project-local under frontend/node_modules).
#
# Make-style staleness: skip the (slow + log-noisy) pydantic2ts run
# when types.ts already exists and nothing under src/sidestage/ is
# newer. `just` has no built-in timestamp tracking, so we do it in
# bash here.
_gen-types:
    #!/usr/bin/env bash
    set -euo pipefail
    out="frontend/src/types.ts"
    if [ -f "$out" ] && [ -z "$(find src/sidestage -name '*.py' -newer "$out" -print -quit)" ]; then
        exit 0
    fi
    uv run pydantic2ts \
        --module sidestage.server \
        --output "$out" \
        --json2ts-cmd frontend/node_modules/.bin/json2ts

# Apply ruff fixes + formatter (writes changes).
format:
    uv run ruff format src/ tests/
    uv run ruff check --fix src/ tests/

# Python tests (pytest only — lint runs separately).
test-py:
    uv run pytest

# Frontend tests (vitest only — typecheck runs via `just lint`).
test-fe: _gen-types
    cd frontend && npm run test:run

# Browser e2e (Playwright + Chromium against the built SPA, ephemeral port).
test-browser: build
    #!/usr/bin/env bash
    set -e
    cd tests/playwright
    export SIDESTAGE_TEST_PORT=$(npm run -s pick-port)
    npm run -s test

# Focused run of just the live-LLM e2e test. The same test also runs as
# part of `just test` when an OpenAI-compatible endpoint is up on :8080
# (e.g. llama-server, vllm, ollama) — it auto-skips otherwise.
test-live-llm:
    uv run pytest -m live_llm tests/e2e/

# -------- build / spec --------

# Build the frontend SPA into src/sidestage/static/.
build: _gen-types
    cd frontend && npm run build

# Regenerate the pydoc spec view at specs/generated/api.md.
spec:
    uv run pydoc-markdown

# -------- run --------

# Hammer for orphaned vite processes — `just run` owns its own.
stop:
    @pkill -f 'vite' || true

# Dev stack: vite + sidestage. The LLM endpoint(s) declared in the active
# profile must already be reachable — Sidestage does not spawn them.
run profile="localhost": _gen-types
    #!/usr/bin/env bash
    set -euo pipefail

    # PIDs of processes WE started this invocation. cleanup() kills only
    # these — pre-existing services we just consume are not touched.
    started=()

    cleanup() {
        if [ ${#started[@]} -eq 0 ]; then
            return
        fi
        echo
        echo "stopping owned processes: ${started[*]}"
        for pid in "${started[@]}"; do
            kill "$pid" 2>/dev/null || true
        done
    }
    # EXIT alone — it fires regardless of exit cause (Ctrl-C, error,
    # normal end). Adding INT/TERM as well would re-run cleanup twice
    # on Ctrl-C: once from the signal, once from the implicit unwind.
    trap cleanup EXIT

    mkdir -p sidestage/logs

    # Vite — start if not already up at :5173.
    if curl -fsS http://localhost:5173/__vite_ping >/dev/null 2>&1; then
        echo "vite: already up on :5173 (not owned)"
    else
        echo "starting vite..."
        ( cd frontend && exec npm run dev >../sidestage/logs/vite.log 2>&1 ) &
        started+=("$!")
        for _ in $(seq 1 50); do
            sleep 0.2
            if curl -fsS http://localhost:5173/__vite_ping >/dev/null 2>&1; then
                break
            fi
        done
        if ! curl -fsS http://localhost:5173/__vite_ping >/dev/null 2>&1; then
            echo "vite failed to come up — check sidestage/logs/vite.log" >&2
            exit 1
        fi
    fi

    # Sidestage in foreground — Ctrl-C falls into trap → cleanup.
    SIDESTAGE_LLM_PROFILE={{profile}} \
        uv run sidestage --sidestage-dir sidestage/ --reload

# -------- housekeeping --------

# Drop build/test caches. Doesn't touch node_modules or .venv.
clean:
    find . -type d -name __pycache__ -prune -exec rm -rf {} +
    rm -rf src/sidestage/static frontend/dist specs/generated sidestage/logs
