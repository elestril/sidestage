"""E2E: alice POSTs via REST; bob's reply arrives via WS; history check.

Same domain scenario as `test_events_dataflow` but driven through the API
boundary against a real uvicorn (per `testing-fixture-test-server`).
Asserts the WS wire delivery step (`events-dataflow-deliver`) plus the
two CUJ steps (`cuj-hello-send`, `cuj-hello-respond`).

.tests: cuj-hello-send, cuj-hello-respond, events-dataflow-deliver,
        ws-dataflow-connect, ws-dataflow-subscribe, ws-dataflow-event,
        rest-api-post-message
"""

from __future__ import annotations

import asyncio
import json
from urllib.parse import quote, urlparse

import httpx
import pytest
import websockets

from sidestage.server import App

pytestmark = pytest.mark.e2e


def _ws_url(base_url: str, path: str) -> str:
    """Convert an http(s) test_server base URL to a ws(s) URL with `path`."""
    p = urlparse(base_url)
    scheme = "wss" if p.scheme == "https" else "ws"
    return f"{scheme}://{p.netloc}{path}"


async def _read_entity_changed_frames(ws, n: int) -> list[dict]:
    """Read n `entity_changed` frames off a WS, ignoring others."""
    frames: list[dict] = []
    while len(frames) < n:
        raw = await ws.recv()
        payload = json.loads(raw)
        if payload.get("op") == "entity_changed":
            frames.append(payload)
    return frames


async def test_cuj_hello(test_app: App, test_server: str) -> None:
    # The test fixture loads exactly one campaign — single entry in
    # `App.campaigns` keyed by `campaign.name`. Pull the id from the
    # iteration order rather than threading the Campaign object through.
    campaign_id = next(iter(test_app.campaigns))
    cid_enc = quote(campaign_id, safe="")
    scene_id = "parlor"
    ws_path = f"/api/campaigns/{cid_enc}/ws"
    post_url = f"/api/campaigns/{cid_enc}/scenes/{scene_id}/messages"
    messages_url = f"/api/campaigns/{cid_enc}/scenes/{scene_id}/messages"

    async with httpx.AsyncClient(base_url=test_server) as client:
        async with websockets.connect(_ws_url(test_server, ws_path)) as ws:
            # ws-dataflow-subscribe: register interest in the scene
            # entity before the POST so we don't miss the emit.
            await ws.send(json.dumps({"op": "subscribe", "entity_id": scene_id}))

            # Brief yield so the subscribe frame is processed before the
            # POST fires the emit. Without this, the POST can race the
            # subscription and the listener misses event #1.
            await asyncio.sleep(0.05)

            post_resp = await client.post(
                post_url, json={"sender_id": "alice", "body": "Hi"}
            )

            frames = await _read_entity_changed_frames(ws, n=2)

        assert post_resp.status_code == 201, (
            "rest-api-post-message: POST /messages MUST return 201 on the "
            f"happy path; got status={post_resp.status_code} "
            f"body={post_resp.text!r}"
        )
        accepted = post_resp.json()
        assert accepted == {"scene_id": "parlor", "index": 0}, (
            "rest-api-post-returns: response carries (scene_id, index) of "
            f"the appended message; got {accepted!r}"
        )
        assert len(frames) == 2, (
            "events-dataflow-deliver: WS stream must deliver one "
            "`entity_changed` frame per `Scene.append` (alice's input "
            f"plus bob's reply); got {len(frames)} frames"
        )
        for i, frame in enumerate(frames):
            assert frame == {
                "op": "entity_changed",
                "entity_id": "parlor",
                "attributes": ["messages"],
            }, (
                "events-dataflow-deliver: WS frame payload for a Scene "
                "message append MUST be "
                "`{op:'entity_changed', entity_id, attributes}` with "
                f"`attributes=['messages']`; got frame[{i}]={frame!r}"
            )

        # History check via GET /messages — confirms alice + bob landed.
        hist_resp = await client.get(messages_url)

    assert hist_resp.status_code == 200, (
        "rest-api-get-messages: GET /messages MUST return 200 on the "
        f"happy path; got status={hist_resp.status_code}"
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
