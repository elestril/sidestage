#
# Sidestage tasks. Run `just` (no args) to list. `just <target>` to run.
#

# Default: list available targets.
default:
    @just --list

# -------- tests --------

# Inner-loop suite: Python + frontend (with typecheck). No browser tier.
test: test-py test-fe

# Every tier including browser e2e — pre-commit / CI path.
test-all: test test-browser

# Python tests.
test-py:
    uv run pytest

# Frontend tests (typecheck + vitest, one-shot).
test-fe: typecheck
    cd frontend && npm run test:run

# Frontend TypeScript typecheck (no emit).
typecheck:
    cd frontend && npm run typecheck

# Idempotent: install playwright deps + Chromium binary if missing.
_playwright-install:
    #!/usr/bin/env bash
    set -e
    cd tests/playwright
    [ -d node_modules ] || npm install
    # `playwright install chromium` is a no-op if already installed.
    npm run -s install-chromium >/dev/null

# Browser e2e (Playwright + Chromium against the built SPA, ephemeral port).
test-browser: build _playwright-install
    #!/usr/bin/env bash
    set -e
    cd tests/playwright
    export SIDESTAGE_TEST_PORT=$(npm run -s pick-port)
    npm run -s test

# -------- build / spec --------

# Build the frontend SPA into src/sidestage/static/.
build:
    cd frontend && npm run build

# Regenerate the pydoc spec view at specs/generated/api.md.
spec:
    uv run pydoc-markdown

# -------- run --------

# Ensure the Vite dev server is up at :5173. Background-launches it if not.
_vite-up:
    #!/usr/bin/env bash
    set -e
    if curl -fsS http://localhost:5173/__vite_ping >/dev/null 2>&1; then
        exit 0
    fi
    mkdir -p sidestage/logs
    echo "Starting Vite dev server..."
    (cd frontend && nohup npm run dev >../sidestage/logs/vite.log 2>&1 &)
    for _ in $(seq 1 50); do
        sleep 0.2
        if curl -fsS http://localhost:5173/__vite_ping >/dev/null 2>&1; then
            exit 0
        fi
    done
    echo "Vite failed to come up — check sidestage/logs/vite.log" >&2
    exit 1

# Stop the Vite dev server (if started by _vite-up).
stop-vite:
    @pkill -f 'vite' || true

# Dev stack: vite (background) + sidestage (foreground). Ctrl-C stops sidestage.
run: _vite-up
    uv run sidestage --sidestage-dir sidestage/

# -------- housekeeping --------

# Drop build/test caches. Doesn't touch node_modules or .venv.
clean:
    find . -type d -name __pycache__ -prune -exec rm -rf {} +
    rm -rf src/sidestage/static frontend/dist specs/generated sidestage/logs
