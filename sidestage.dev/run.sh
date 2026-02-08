#!/bin/bash

set -euxo pipefail

CAMPAIGN="${1:-dev}"

if [ ! -d "./$CAMPAIGN" ]; then
  cp -rp ../data/dev_campaign/ "$CAMPAIGN"
fi

exec uv run sidestage --sidestage_dir . "$CAMPAIGN"

