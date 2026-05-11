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

# All linters and type checks (ruff + pyright + tsc), parallel sub-tasks.
[parallel]
lint: _ruff-check _ruff-format-check _pyright _tsc

_ruff-check:
    uv run ruff check src/ tests/

_ruff-format-check:
    uv run ruff format --check src/ tests/

_pyright:
    uv run pyright src/ tests/

_tsc:
    cd frontend && npm run typecheck

# Apply ruff fixes + formatter (writes changes).
format:
    uv run ruff format src/ tests/
    uv run ruff check --fix src/ tests/

# Python tests (pytest only — lint runs separately).
test-py:
    uv run pytest

# Frontend tests (vitest only — typecheck runs via `just lint`).
test-fe:
    cd frontend && npm run test:run

# Browser e2e (Playwright + Chromium against the built SPA, ephemeral port).
test-browser: build
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

# Dev stack: vite (background) + sidestage (foreground, hot-reload). Ctrl-C stops.
run: _vite-up
    uv run sidestage --sidestage-dir sidestage/ --reload

# -------- housekeeping --------

# Drop build/test caches. Doesn't touch node_modules or .venv.
clean:
    find . -type d -name __pycache__ -prune -exec rm -rf {} +
    rm -rf src/sidestage/static frontend/dist specs/generated sidestage/logs
