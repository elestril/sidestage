"""E2E: alice posts via REST; bob's reply arrives via SSE; history check.

Same domain scenario as `test_events_dataflow` but driven through the REST
boundary against a real uvicorn (per `testing-fixture-test-server`).
Asserts the SSE wire delivery step (`events-dataflow-deliver`) plus the
two CUJ steps (`cuj-hello-send`, `cuj-hello-respond`).

.tests: cuj-hello-send, cuj-hello-respond, events-dataflow-deliver,
        sse-dataflow-connect, rest-api-post-message, rest-api-get-entity-events
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from sidestage.server import App


pytestmark = pytest.mark.e2e


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
            pending_event = line[len("event: "):]
        elif line.startswith("data: ") and pending_event == "entity_changed":
            frames.append(json.loads(line[len("data: "):]))
            pending_event = None
            if len(frames) >= n:
                return frames
    return frames


async def test_cuj_hello(test_app: App, test_server: str) -> None:
    campaign_id = test_app.campaign.name
    scene_id = "parlor"
    events_url = f"/api/campaigns/{campaign_id}/entities/{scene_id}/events"
    post_url = f"/api/campaigns/{campaign_id}/scenes/{scene_id}/messages"
    messages_url = f"/api/campaigns/{campaign_id}/scenes/{scene_id}/messages"

    async with httpx.AsyncClient(base_url=test_server) as client:

        async def stream_frames() -> tuple[int, str, list[dict]]:
            async with client.stream("GET", events_url) as resp:
                status = resp.status_code
                ctype = resp.headers.get("content-type", "")
                frames = await _read_entity_changed_frames(resp, n=2)
                return status, ctype, frames

        async def post_after_subscribed() -> httpx.Response:
            # Brief yield so the SSE handler reaches subscribe_to before
            # the POST fires the emit. Without this, the POST can race
            # the subscription and the QueueListener misses event #1.
            await asyncio.sleep(0.05)
            return await client.post(
                post_url, json={"sender_id": "alice", "body": "Hi"}
            )

        (status, ctype, frames), post_resp = await asyncio.gather(
            stream_frames(), post_after_subscribed()
        )

        assert status == 200, (
            "sse-dataflow-connect: SSE subscribe returns 200; "
            f"got status={status}"
        )
        assert "text/event-stream" in ctype, (
            "sse-dataflow-connect: response content-type must be "
            f"text/event-stream; got {ctype!r}"
        )
        assert post_resp.status_code == 201, (
            "rest-api-post-message: POST /messages returns 201 on the "
            f"happy path; got status={post_resp.status_code} "
            f"body={post_resp.text!r}"
        )
        assert post_resp.json()["id"] == "parlor:0", (
            "rest-api-post-message: response carries the assigned "
            f"MessageId; got id={post_resp.json().get('id')!r}"
        )
        assert len(frames) == 2, (
            "events-dataflow-deliver: SSE stream must deliver one "
            "`entity_changed` frame per `Scene.append` (alice's input "
            f"plus bob's reply); got {len(frames)} frames"
        )
        for i, frame in enumerate(frames):
            assert frame == {
                "entity_id": "parlor",
                "attributes": ["messages"],
            }, (
                "events-dataflow-deliver: SSE frame payload is "
                "`{entity_id, attributes}` with `attributes=['messages']` "
                f"for a Scene message append; frame[{i}]={frame!r}"
            )

        # History check via GET /messages — confirms alice + bob landed.
        hist_resp = await client.get(messages_url)

    assert hist_resp.status_code == 200, (
        "rest-api-get-messages: GET /messages returns 200; "
        f"got status={hist_resp.status_code}"
    )
    messages = hist_resp.json()
    assert len(messages) == 2, (
        "cuj-hello-respond: scene history must contain alice's input plus "
        f"bob's reply after the listener cycle settles; got {len(messages)} "
        f"messages: {messages!r}"
    )
    assert messages[0]["sender_id"] == "alice" and messages[0]["body"] == "Hi", (
        "cuj-hello-send: alice's message must be at index 0 with body 'Hi'; "
        f"got {messages[0]!r}"
    )
    assert messages[1]["sender_id"] == "bob", (
        "cuj-hello-respond: bob (stub) must reply at index 1; "
        f"got sender_id={messages[1]['sender_id']!r}"
    )
