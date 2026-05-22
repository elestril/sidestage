"""E2E: alice posts via WS `entity_action(say)`; bob's reply arrives via WS.

The Phase-2b WS-centric flow. Asserts:
- subscribe carries initial state in the `subscribed` reply
- entity_action dispatches to `Character.say` and returns matching `ack`
- two `entity_changed` frames fire (alice's input + bob's reply) with
  `ListDelta` payloads on `scene.messages`
- the history GET reflects both messages

.tests: cuj-hello-send, cuj-hello-respond, events-dataflow-deliver,
        backend-ws-subscribe, backend-ws-entity-action,
        events-attribute-deltas
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


async def _read_frames(ws, *, ops: set[str], count: int) -> list[dict]:
    """Read until `count` frames matching one of `ops` have arrived."""
    out: list[dict] = []
    while len(out) < count:
        raw = await ws.recv()
        payload = json.loads(raw)
        if payload.get("op") in ops:
            out.append(payload)
    return out


async def test_cuj_hello(test_app: App, test_server: str) -> None:
    campaign_id = next(iter(test_app.campaigns))
    cid_enc = quote(campaign_id, safe="")
    scene_id = "parlor"
    ws_path = f"/api/campaigns/{cid_enc}/ws"
    messages_url = f"/api/campaigns/{cid_enc}/scenes/{scene_id}/messages"

    async with httpx.AsyncClient(base_url=test_server) as client:
        async with websockets.connect(_ws_url(test_server, ws_path)) as ws:
            # backend-ws-subscribe: subscribe carries initial state in the reply.
            await ws.send(
                json.dumps(
                    {
                        "op": "subscribe",
                        "entity_ids": [scene_id],
                        "request_id": "sub-1",
                    }
                )
            )
            subscribed = (await _read_frames(ws, ops={"subscribed"}, count=1))[0]
            assert subscribed["request_id"] == "sub-1"
            assert len(subscribed["states"]) == 1
            initial = subscribed["states"][0]
            assert initial["entity_id"] == scene_id
            assert initial["model"]["messages"] == [], (
                "backend-ws-subscribe: initial state of fresh scene must have "
                "empty messages list"
            )

            # backend-ws-entity-action: alice publishes via Character.say.
            await ws.send(
                json.dumps(
                    {
                        "op": "entity_action",
                        "entity_id": "alice",
                        "action": "say",
                        "kwargs": {"scene_id": scene_id, "body": "Hi"},
                        "request_id": "say-1",
                    }
                )
            )
            # Brief yield so the action lands before we read frames.
            await asyncio.sleep(0.05)

            # We expect: one ack for the action, plus two entity_changed
            # frames (alice's append + bob's reply).
            ack = (await _read_frames(ws, ops={"ack", "error"}, count=1))[0]
            assert ack == {"op": "ack", "request_id": "say-1"}, (
                f"backend-ws-entity-action: expected ack frame; got {ack!r}"
            )

            frames = await _read_frames(ws, ops={"entity_changed"}, count=2)

        assert len(frames) == 2, (
            "events-dataflow-deliver: WS stream must deliver one "
            "entity_changed per scene mutation (alice + bob)"
        )
        for i, frame in enumerate(frames):
            assert frame["entity_id"] == scene_id
            assert frame["attributes"] == ["messages"]
            # events-attribute-deltas: each frame carries a ListDelta append.
            delta = frame["deltas"]["messages"]
            assert delta["start"] == -1, (
                f"frame[{i}].deltas.messages.start must be -1 for append; got {delta!r}"
            )
            assert delta["len"] == 0
            assert len(delta["items"]) == 1

        # History via GET /messages — confirms both landed.
        hist_resp = await client.get(messages_url)

    assert hist_resp.status_code == 200
    messages = hist_resp.json()
    assert len(messages) == 2
    assert messages[0] == {"sender_id": "alice", "body": "Hi"}, (
        "cuj-hello-send: alice's message at index 0"
    )
    assert messages[1]["sender_id"] == "bob", (
        "cuj-hello-respond: bob's stub reply at index 1"
    )
