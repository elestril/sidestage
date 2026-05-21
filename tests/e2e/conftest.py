"""E2E-tier fixtures.

Per `testing-categories-e2e`: a real uvicorn server bound to an ephemeral
127.0.0.1 port. Tests drive it via real TCP — required for streaming
responses (SSE) where httpx's in-process `ASGITransport` buffers the
full response body and deadlocks against an open stream.

.implements: testing-fixture-test-server
"""

from __future__ import annotations

import asyncio

import pytest
import uvicorn

from sidestage.server import App


@pytest.fixture
async def test_server(test_app: App):
    """testing-fixture-test-server: per-test uvicorn on an ephemeral
    127.0.0.1 port. Yields the base URL (e.g. `http://127.0.0.1:54321`).

    Lifecycle: spawn the server as a background asyncio task, busy-wait
    until `server.started`, read the bound port off the asyncio Server's
    socket, yield, then signal `should_exit` and await the serve task.

    `lifespan="off"` because the App has no startup/shutdown events;
    `log_level="error"` to keep test output clean.
    """
    config = uvicorn.Config(
        test_app._fastapi,
        host="127.0.0.1",
        port=0,
        log_level="error",
        loop="asyncio",
        lifespan="off",
        # Multiplexed WS lives at /api/campaigns/{cid}/ws per
        # `specs/events.md`. Use h11 + websockets explicitly — httptools
        # (the default with uvicorn[standard]) rejects some WS handshakes
        # with HTTP 400; the pure-Python h11 parser is lenient and works
        # cleanly alongside the websockets WS implementation.
        http="h11",
        ws="websockets",
    )
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve())
    try:
        while not server.started:
            await asyncio.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await asyncio.wait_for(serve_task, timeout=2.0)
