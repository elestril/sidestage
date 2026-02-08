#!/bin/bash

set -euxo pipefail

CAMPAIGN="${1:-dev}"


if [ -f sidestage.pid]; then
  print "sidestage.pid already exists, exiting" 
  exit 0
fi


if [ ! -d "./$CAMPAIGN" ]; then
  cp -rp ../data/dev_campaign/ "$CAMPAIGN"
fi

exec uv run sidestage --sidestage_dir . "$CAMPAIGN"

