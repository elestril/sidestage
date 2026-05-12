"""E2E live-LLM: bob posts to The Cracked Tankard; Marigold (NpcActor)
replies via SSE. Same shape as `test_cuj_hello` — real uvicorn, REST
POST, SSE read, GET history — with the npc owner wired to a real LLM
endpoint instead of `StubActor`.

Per `testing-categories-e2e-live-llm`: the single e2e test that
validates `NpcActor`. Always part of the default suite; auto-skips when
the LLM endpoint declared by `sidestage/llm_profiles/localhost.yaml`
isn't answering `/health`. No env-var opt-in required — if the server
is up, the test runs; otherwise it skips cleanly.

The fixture loads the production `sidestage/` instance directly so the
test exercises exactly what `just run` runs — Marigold's character file
and the tavern scene live in `sidestage/campaigns/dragons_lair/`.

.tests: cuj-hello-respond, npc-actor-respond, events-dataflow-deliver,
        sse-dataflow-connect, rest-api-post-message, rest-api-get-messages
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from urllib.parse import quote

import httpx
import pytest
import uvicorn

from sidestage.server import App

_LLM_HEALTH_URL = "http://127.0.0.1:8080/health"


def _llm_endpoint_up() -> bool:
    """Pre-flight /health on the LLM endpoint declared by localhost.yaml.

    Skipping here gives a clear "your LLM isn't running" message instead
    of a 60s timeout deep inside litellm when the test actually fires.
    """
    try:
        r = httpx.get(_LLM_HEALTH_URL, timeout=2.0)
        return 200 <= r.status_code < 300
    except (httpx.HTTPError, OSError):
        return False


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.live_llm,
    pytest.mark.skipif(
        not _llm_endpoint_up(),
        reason=(
            f"no OpenAI-compatible endpoint reachable on {_LLM_HEALTH_URL} — "
            "start llama-server / vllm / ollama / etc. to run this test"
        ),
    ),
    pytest.mark.timeout(90),
]


@pytest.fixture
def live_app() -> Iterator[App]:
    """Build a fresh `App` from the production `sidestage/` instance.

    Same path as `just run` — `_build_and_load` loads
    `sidestage/llm_profiles/localhost.yaml` into `App.llm_profile`
    before walking `sidestage/campaigns/`. Marigold's
    `owner: npc` then constructs an `NpcActor` wired to the localhost
    endpoint at deserialize time.

    Snapshots class-level App state on setup and restores on teardown so
    this fixture doesn't leak into any subsequent test in the same
    session.
    """
    saved_actors = App._actors.copy()
    saved_llm_profile = App.llm_profile
    saved_factory = App.factory
    App._actors.clear()
    App.llm_profile = None
    App.factory = None
    try:
        app = App._build_and_load("sidestage", "localhost")
        yield app
    finally:
        App._actors.clear()
        App._actors.update(saved_actors)
        App.llm_profile = saved_llm_profile
        App.factory = saved_factory


@pytest.fixture
async def live_server(live_app: App) -> AsyncIterator[str]:
    """Per-test uvicorn against `live_app` on an ephemeral port. Mirrors
    `testing-fixture-test-server` but binds the live (dragons_lair) App
    instead of the test fixture App.
    """
    config = uvicorn.Config(
        live_app._fastapi,
        host="127.0.0.1",
        port=0,
        log_level="error",
        loop="asyncio",
        lifespan="off",
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


async def _read_entity_changed_frames(response: httpx.Response, n: int) -> list[dict]:
    """Read n `event: entity_changed` frames off an SSE stream.

    SSE frames are 3 lines: `event:`, `data:`, blank. Keepalive comments
    (`: keepalive`) are skipped. Bounded by the enclosing pytest timeout.
    """
    frames: list[dict] = []
    pending_event: str | None = None
    async for raw in response.aiter_lines():
        line = raw.rstrip("\r")
        if line.startswith("event: "):
            pending_event = line[len("event: ") :]
        elif line.startswith("data: ") and pending_event == "entity_changed":
            frames.append(json.loads(line[len("data: ") :]))
            pending_event = None
            if len(frames) >= n:
                return frames
    return frames


async def test_marigold_replies_to_bob(live_app: App, live_server: str) -> None:
    """Bob posts a line in the tavern; Marigold's NpcActor produces a
    real LLM-backed reply that lands in scene history via the SSE
    pipeline.
    """
    # Campaign id is `campaign.name` ("Dragon's Lair") — URL-encode the
    # space and apostrophe so the path lands on the FastAPI route.
    campaign_id = quote(next(iter(live_app.campaigns)), safe="")
    scene_id = "tavern"
    events_url = f"/api/campaigns/{campaign_id}/entities/{scene_id}/events"
    messages_url = f"/api/campaigns/{campaign_id}/scenes/{scene_id}/messages"

    async with httpx.AsyncClient(base_url=live_server, timeout=80.0) as client:

        async def stream_frames() -> list[dict]:
            async with client.stream("GET", events_url) as resp:
                return await _read_entity_changed_frames(resp, n=2)

        async def post_after_subscribed() -> httpx.Response:
            # Brief yield so the SSE handler reaches subscribe_to before
            # the POST fires the emit (per test_cuj_hello's note).
            await asyncio.sleep(0.05)
            return await client.post(
                messages_url,
                json={"sender_id": "bob", "body": "What's the gossip tonight?"},
            )

        frames, post_resp = await asyncio.gather(
            stream_frames(), post_after_subscribed()
        )

        assert post_resp.status_code == 201, (
            "rest-api-post-message: POST /messages MUST return 201 on the "
            f"happy path; got status={post_resp.status_code} "
            f"body={post_resp.text!r}"
        )
        assert len(frames) == 2, (
            "events-dataflow-deliver: SSE stream MUST deliver one "
            "`entity_changed` frame per Scene.append (bob's input plus "
            f"marigold's reply); got {len(frames)} frames"
        )

        hist_resp = await client.get(messages_url)

    assert hist_resp.status_code == 200, (
        "rest-api-get-messages: GET /messages MUST return 200 on the "
        f"happy path; got status={hist_resp.status_code}"
    )
    messages = hist_resp.json()
    assert len(messages) == 2, (
        "cuj-hello-respond: scene history MUST contain bob's input plus "
        f"marigold's reply after the listener cycle settles; got "
        f"{len(messages)} messages: {messages!r}"
    )
    assert messages[0]["sender_id"] == "bob" and messages[0]["body"] == (
        "What's the gossip tonight?"
    ), (
        "rest-api-post-message: bob's message MUST land at index 0 with "
        f"the posted body; got {messages[0]!r}"
    )
    assert messages[1]["sender_id"] == "marigold", (
        "npc-actor-respond: marigold MUST reply at index 1; "
        f"got sender_id={messages[1]['sender_id']!r}"
    )
    assert messages[1]["body"].strip() != "", (
        "npc-actor-respond: marigold's reply body MUST be non-empty; "
        f"got body={messages[1]['body']!r}"
    )
