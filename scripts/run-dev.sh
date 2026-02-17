#!/bin/bash

set -euxo pipefail

CAMPAIGN="${1:-dev}"

cd $(dirname $(realpath "$0"))/../sidestage.dev

if [ -f "sidestage.pid" ]; then
  print "sidestage.pid already exists, exiting" 
  exit 0
fi


if [ ! -d "./$CAMPAIGN" ]; then
  cp -rp ../data/dev_campaign/ "$CAMPAIGN"
fi

PORT_ARGS=""
if [ -n "${SIDESTAGE_PORT:-}" ]; then
  PORT_ARGS="--port $SIDESTAGE_PORT"
fi

exec uv run sidestage --sidestage_dir . $PORT_ARGS "$CAMPAIGN"

