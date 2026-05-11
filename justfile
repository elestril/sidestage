#
# Sidestage tasks. Run `just` (no args) to list. `just <target>` to run.
#

# Default: list available targets.
default:
    @just --list

# -------- tests --------

# Run the whole test suite (Python + frontend, with FE typecheck).
test: test-py test-fe

# Python tests.
test-py:
    uv run pytest

# Frontend tests (typecheck + vitest, one-shot).
test-fe: typecheck
    cd frontend && npm run test:run

# Frontend TypeScript typecheck (no emit).
typecheck:
    cd frontend && npm run typecheck

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
    mkdir -p logs
    echo "Starting Vite dev server..."
    (cd frontend && nohup npm run dev >../logs/vite.log 2>&1 &)
    for _ in $(seq 1 50); do
        sleep 0.2
        if curl -fsS http://localhost:5173/__vite_ping >/dev/null 2>&1; then
            exit 0
        fi
    done
    echo "Vite failed to come up — check logs/vite.log" >&2
    exit 1

# Stop the Vite dev server (if started by _vite-up).
stop-vite:
    @pkill -f 'vite' || true

# Start the dev stack: vite (background) + sidestage server (foreground).
# Ctrl-C stops the server. Vite keeps running — use `just stop-vite` to kill it.
run: _vite-up
    uv run sidestage --config configs/

# -------- housekeeping --------

# Drop build/test caches. Doesn't touch node_modules or .venv.
clean:
    find . -type d -name __pycache__ -prune -exec rm -rf {} +
    rm -rf src/sidestage/static frontend/dist specs/generated logs
