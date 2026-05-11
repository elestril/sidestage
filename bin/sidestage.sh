#!/usr/bin/env bash
# Thin wrapper around `sidestage-ctl`. The real lifecycle logic lives in
# `src/sidestage/runner.py` (see specs/runner.md).
#
# Usage: bin/sidestage.sh <run|start|stop> [instance] [--force-backends]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"
exec uv run sidestage-ctl "$@"
