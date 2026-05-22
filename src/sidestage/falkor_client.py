"""falkor_client: Open and close the per-campaign FalkorDBLite engine.

Per [[specs/persistence.md]] `persistence-engine-redislite`. A single
`redislite` subprocess per campaign hosts both the FalkorDB Cypher
module and Redis Streams. The Redis client is reachable via
`FalkorDB.client`; callers that need stream ops (notably `Scene`'s
`MessageList`) use it directly, no second client needed.

Server-mode FalkorDB (`redis://`) is out of scope; this module is the
narrow seam where a future connector would slot in
(per `persistence-engine-no-server-mode`).
"""

from __future__ import annotations

import os
import signal
import time
from pathlib import Path

from redislite import FalkorDB


def open_falkor(path: Path) -> FalkorDB:
    """Open the campaign's FalkorDBLite engine at `path`.

    The parent directory is created if missing. AOF is enabled so chat
    loses ≤1s on crash (per `persistence-engine-aof`).

    .implements: persistence-engine-redislite, persistence-engine-aof
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    return FalkorDB(
        dbfilename=str(path),
        serverconfig={"appendonly": "yes"},
    )


def close_falkor(falkor: FalkorDB) -> None:
    """Stop the embedded redis subprocess.

    Sends `SIGTERM` to the redis pid and polls for exit. Redis handles
    SIGTERM as a clean shutdown — it flushes the AOF and removes its
    pidfile before exiting. The whole thing typically completes in
    ~10ms.

    The default `redislite` close path goes through the Redis
    `SHUTDOWN` command, which is much slower in practice (~5-10s)
    because the redis-py client retries on the connection drop that
    SHUTDOWN deliberately causes.

    Called from `App`'s shutdown hook so `--reload` worker tear-down
    doesn't leave a stale socket (per `persistence-engine-shutdown`).

    .implements: persistence-engine-shutdown
    """
    pid = falkor.client.pid
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return  # Already gone.
        # Poll for exit. Redis usually exits in <50ms after SIGTERM.
        for _ in range(200):  # 200 × 10ms = 2s budget
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.01)
