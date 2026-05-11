"""Tier 2 integration: REST round-trips via fastapi.testclient.TestClient.

One test per `api-dataflow-*` invariant. Same 1:1 invariant-to-test mapping
as the Tier 1 dispatch-flow tests. The TestClient runs the FastAPI app
in-process — no real HTTP socket — so every test is fast and deterministic.

.implements: api-dataflow-subscribe, api-dataflow-list-campaigns,
    api-dataflow-campaign, api-dataflow-scene, api-dataflow-entities,
    api-dataflow-history, api-dataflow-send, api-dataflow-dispatch,
    api-dataflow-respond
"""

from __future__ import annotations

import asyncio

import pytest


pytestmark = pytest.mark.integration


_CAMPAIGN_NAME = "Test Campaign"
_SCENE_ID = "parlor"


async def test_api_dataflow_subscribe(test_app) -> None:
    """api-dataflow-subscribe: opening GET /api/events returns 200 + SSE
    content-type.

    TestClient does not flush response headers until the streaming body
    yields its first chunk, so a connect-and-close against `/api/events`
    on an idle scene (no events queued) hangs until the 15 s keepalive.
    We instead use `httpx.AsyncClient` over `ASGITransport`, which lets
    us drive the SSE GET concurrently with a POST that produces an event
    on the subscribed queue. Asserts cover status code, content-type,
    and the SSE framing of the emitted event — that's the
    `api-dataflow-subscribe` invariant: the subscribe path WORKS.
    """
    import asyncio

    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=test_app._fastapi)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        async def open_stream() -> tuple[int, str, bytes]:
            async with client.stream("GET", "/api/events") as resp:
                first = b""
                async for chunk in resp.aiter_bytes():
                    first = chunk
                    break
                return resp.status_code, resp.headers["content-type"], first

        async def poke() -> int:
            # Brief delay so the GET handler reaches App._subscribe before
            # we POST and trigger the npc cycle.
            await asyncio.sleep(0.05)
            r = await client.post(
                f"/api/campaigns/{_CAMPAIGN_NAME}/scenes/{_SCENE_ID}/messages",
                json={"sender_id": "alice", "body": "hi"},
            )
            return r.status_code

        (status, ctype, chunk), post_status = await asyncio.gather(
            open_stream(), poke()
        )

    assert status == 200
    assert ctype.startswith("text/event-stream")
    assert post_status == 201
    assert b"scene_updated" in chunk


def test_api_dataflow_list_campaigns(test_client) -> None:
    """api-dataflow-list-campaigns: GET /api/campaigns returns one entry
    matching the loaded fixture campaign.
    """
    resp = test_client.get("/api/campaigns")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    entry = body[0]
    assert entry["name"] == _CAMPAIGN_NAME
    assert entry["default_scene_id"] == _SCENE_ID


def test_api_dataflow_campaign(test_client) -> None:
    """api-dataflow-campaign: GET /api/campaigns/{cid} returns CampaignResponse."""
    resp = test_client.get(f"/api/campaigns/{_CAMPAIGN_NAME}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == _CAMPAIGN_NAME
    assert body["default_scene_id"] == _SCENE_ID


def test_api_dataflow_scene(test_client) -> None:
    """api-dataflow-scene: GET /api/campaigns/{cid}/scenes/{sid} returns
    SceneResponse with parlor's character_ids and player_character_ids.
    """
    resp = test_client.get(
        f"/api/campaigns/{_CAMPAIGN_NAME}/scenes/{_SCENE_ID}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == _SCENE_ID
    assert body["name"] == "Parlor"
    assert body["character_ids"] == ["alice", "bob"]
    # alice is owner=user (see tests/test_campaign/characters/alice.md).
    assert body["player_character_ids"] == ["alice"]


def test_api_dataflow_entities(test_client) -> None:
    """api-dataflow-entities: GET /api/campaigns/{cid}/entities/{id}
    returns the CharacterModel with the persisted owner.
    """
    alice_resp = test_client.get(
        f"/api/campaigns/{_CAMPAIGN_NAME}/entities/alice"
    )
    assert alice_resp.status_code == 200
    alice = alice_resp.json()
    assert alice["id"] == "alice"
    assert alice["owner"] == "user"

    bob_resp = test_client.get(
        f"/api/campaigns/{_CAMPAIGN_NAME}/entities/bob"
    )
    assert bob_resp.status_code == 200
    bob = bob_resp.json()
    assert bob["id"] == "bob"
    assert bob["owner"] == "stub"


def test_api_dataflow_history(test_client) -> None:
    """api-dataflow-history: GET /api/campaigns/{cid}/scenes/{sid}/messages
    returns 200 with an empty list initially.
    """
    resp = test_client.get(
        f"/api/campaigns/{_CAMPAIGN_NAME}/scenes/{_SCENE_ID}/messages"
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_api_dataflow_send(test_client) -> None:
    """api-dataflow-send: POST a message and observe 201 + MessageAccepted{id}."""
    resp = test_client.post(
        f"/api/campaigns/{_CAMPAIGN_NAME}/scenes/{_SCENE_ID}/messages",
        json={"sender_id": "alice", "body": "Hi"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    # message-id-format: `{scene_id}:{index}`.
    assert body["id"].startswith(f"{_SCENE_ID}:")


def test_api_dataflow_dispatch(test_client, test_app) -> None:
    """api-dataflow-dispatch: a follow-up GET /messages after the POST shows
    BOTH the user message and the npc response (Bob via StubActor).
    """
    post_resp = test_client.post(
        f"/api/campaigns/{_CAMPAIGN_NAME}/scenes/{_SCENE_ID}/messages",
        json={"sender_id": "alice", "body": "Hi"},
    )
    assert post_resp.status_code == 201

    # Let the fire-and-forget npc cycle complete. The TestClient runs the
    # POST handler synchronously inside an event loop, so the spawned task
    # is queued but won't run until we yield back to the loop.
    _drain_npc_cycle(test_app)

    get_resp = test_client.get(
        f"/api/campaigns/{_CAMPAIGN_NAME}/scenes/{_SCENE_ID}/messages"
    )
    assert get_resp.status_code == 200
    msgs = get_resp.json()
    assert len(msgs) == 2
    assert msgs[0]["sender_id"] == "alice"
    assert msgs[0]["body"] == "Hi"
    assert msgs[1]["sender_id"] == "bob"


def test_api_dataflow_respond(test_client, test_app) -> None:
    """api-dataflow-respond: the npc response message body matches Bob's
    character body (StubActor returns `Message(sender, body=character.body)`).
    """
    post_resp = test_client.post(
        f"/api/campaigns/{_CAMPAIGN_NAME}/scenes/{_SCENE_ID}/messages",
        json={"sender_id": "alice", "body": "Hi"},
    )
    assert post_resp.status_code == 201

    _drain_npc_cycle(test_app)

    get_resp = test_client.get(
        f"/api/campaigns/{_CAMPAIGN_NAME}/scenes/{_SCENE_ID}/messages"
    )
    assert get_resp.status_code == 200
    msgs = get_resp.json()
    assert len(msgs) == 2
    response_msg = msgs[1]
    assert response_msg["sender_id"] == "bob"
    assert response_msg["body"] == "*nods quietly*"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _drain_npc_cycle(test_app, timeout_s: float = 1.0) -> None:
    """Yield to the event loop until the scene's npc cycle has settled.

    The TestClient drives the route handler to completion, but the fire-and-
    forget `asyncio.create_task(self._respond(message))` only runs once we
    return control to the loop. We poll `len(scene.messages)` until it
    stabilises (3 consecutive no-growth yields) or the timeout fires.
    """
    campaign = test_app.campaign
    scene = campaign.scene(_SCENE_ID)

    async def _wait() -> None:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_s
        last = len(scene.messages)
        stable = 0
        while loop.time() < deadline and stable < 3:
            await asyncio.sleep(0)
            cur = len(scene.messages)
            if cur == last:
                stable += 1
            else:
                stable = 0
                last = cur

    asyncio.run(_wait())
