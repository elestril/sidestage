#!/usr/bin/env bash
set -euo pipefail

COMMAND="${1:-}"
INSTANCE="${2:-dev}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

PID_FILE="$REPO_ROOT/.sidestage-${INSTANCE}.pid"
LOG_FILE="$REPO_ROOT/.sidestage-${INSTANCE}.log"

case "$INSTANCE" in
  dev) CONFIG_DIR="$REPO_ROOT/configs"; RELOAD_FLAG="--reload" ;;
  *)   echo "Unknown instance: $INSTANCE (only 'dev' is supported)" >&2; exit 1 ;;
esac

case "$COMMAND" in
  run)
    cd "$REPO_ROOT"
    exec uv run sidestage --config "$CONFIG_DIR" $RELOAD_FLAG
    ;;

  start)
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "sidestage[$INSTANCE] already running (pid $(cat "$PID_FILE"))"
      exit 0
    fi
    echo "Starting sidestage[$INSTANCE] → $LOG_FILE"
    cd "$REPO_ROOT"
    nohup uv run sidestage --config "$CONFIG_DIR" $RELOAD_FLAG >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "sidestage[$INSTANCE] started (pid $!)"
    ;;

  stop)
    if [[ ! -f "$PID_FILE" ]]; then
      echo "sidestage[$INSTANCE] not running (no pid file)"
      exit 0
    fi
    PID="$(cat "$PID_FILE")"
    if kill -0 "$PID" 2>/dev/null; then
      kill "$PID"
      rm -f "$PID_FILE"
      echo "sidestage[$INSTANCE] stopped (pid $PID)"
    else
      echo "sidestage[$INSTANCE] not running (stale pid $PID)"
      rm -f "$PID_FILE"
    fi
    ;;

  *)
    echo "Usage: $(basename "$0") <start|stop> [instance]" >&2
    exit 1
    ;;
esac
