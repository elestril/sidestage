from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from sidestage.actor import SceneUpdatedEvent, StubActor, UserActor
from sidestage.entity import EntityId, EntityType
from sidestage.message import Message, MessageId
from sidestage.server import (
    App,
    MessageAccepted,
    MessageRequest,
    SceneResponse,
    ServerState,
)


# ---------------------------------------------------------------------------
# Helpers — mock builders for the cross-file deps that may not yet match spec.
# ---------------------------------------------------------------------------


def _reset_actor_registry() -> None:
    """Clear the App-level actor registry between tests."""
    App._actors = {}


@pytest.fixture(autouse=True)
def _clear_app_state():
    """Each test starts with a clean App class-level registry/factory."""
    _reset_actor_registry()
    if hasattr(App, "factory"):
        try:
            del App.factory
        except AttributeError:
            pass
    yield
    _reset_actor_registry()
    if hasattr(App, "factory"):
        try:
            del App.factory
        except AttributeError:
            pass


def make_human_character(id: str = "bob") -> MagicMock:
    """A character with owner='user'. Spec character-class field is `owner`."""
    char = MagicMock(spec=[])
    char.id = EntityId(id)
    char.name = id.capitalize()
    char.owner = "user"
    char._actor = StubActor()
    char.has_human_actor = lambda: char.owner == "user"
    return char


def make_npc_character(id: str = "elara") -> MagicMock:
    char = MagicMock(spec=[])
    char.id = EntityId(id)
    char.name = id.capitalize()
    char.owner = "npc"
    char._actor = StubActor()
    char.has_human_actor = lambda: False
    return char


def make_scene(human, npc, scene_id: str = "s1") -> MagicMock:
    scene = MagicMock(spec=[])
    scene.id = EntityId(scene_id)
    scene.name = "Test Scene"
    scene.characters = [human, npc]
    scene.messages = []

    def serialize_message(idx: int) -> Message.Model:
        m = scene.messages[idx]
        return Message.Model(
            id=MessageId(f"{scene.id}:{idx}"),
            sender_id=m.sender.id,
            body=m.body,
        )

    def dispatch(msg: Message) -> MessageId:
        scene.messages.append(msg)
        return MessageId(f"{scene.id}:{len(scene.messages) - 1}")

    scene.serialize_message = serialize_message
    scene.dispatch = MagicMock(side_effect=dispatch)
    return scene


def make_campaign(scene) -> MagicMock:
    """Spec'd Campaign no longer carries `.scene` — the active Scene is
    resolved at call time via `campaign.factory.get(campaign.active_scene_id)`.
    Mock that lookup here so server routes can resolve the active scene.
    """
    campaign = MagicMock(spec=[])
    campaign.name = "Test Campaign"
    campaign.active_scene_id = scene.id
    campaign.factory = MagicMock()

    def _factory_get(eid):
        if eid == scene.id:
            return scene
        return None

    campaign.factory.get = MagicMock(side_effect=_factory_get)
    return campaign


def make_loaded_app(scene_id: str = "s1") -> tuple[App, MagicMock, MagicMock, MagicMock]:
    human = make_human_character("bob")
    npc = make_npc_character("elara")
    scene = make_scene(human, npc, scene_id=scene_id)
    campaign = make_campaign(scene)
    app = App()
    app.campaign = campaign
    app.state = ServerState.SERVING
    return app, scene, human, npc


# ---------------------------------------------------------------------------
# server-state
# ---------------------------------------------------------------------------


class TestServerState:
    def test_loading_value(self):
        # server-state-loading: enum has LOADING.
        assert ServerState.LOADING is not None

    def test_serving_value(self):
        # server-state-serving: enum has SERVING.
        assert ServerState.SERVING is not None

    def test_states_distinct(self):
        assert ServerState.LOADING != ServerState.SERVING


# ---------------------------------------------------------------------------
# Wire models
# ---------------------------------------------------------------------------


class TestSceneResponse:
    def test_fields(self):
        resp = SceneResponse(
            id=EntityId("s1"),
            name="Test",
            character_ids=[EntityId("a"), EntityId("b")],
            player_character_ids=[EntityId("a")],
        )
        assert resp.id == "s1"
        assert resp.name == "Test"
        assert resp.character_ids == ["a", "b"]
        assert resp.player_character_ids == ["a"]


class TestMessageRequest:
    def test_fields(self):
        req = MessageRequest(sender_id=EntityId("c1"), body="hi")
        assert req.sender_id == "c1"
        assert req.body == "hi"


class TestMessageAccepted:
    def test_fields(self):
        acc = MessageAccepted(id=MessageId("s1:0"))
        assert acc.id == "s1:0"


# ---------------------------------------------------------------------------
# server-app construction
# ---------------------------------------------------------------------------


class TestApp:
    def test_app_initial_state_loading(self):
        # server-state-loading: initial state is LOADING.
        app = App()
        assert app.state == ServerState.LOADING

    def test_app_default_config_dir(self):
        # server-run-config: default config_dir is "configs/".
        app = App()
        assert app.config_dir == "configs/"

    def test_app_custom_config_dir(self):
        app = App(config_dir="my/dir/")
        assert app.config_dir == "my/dir/"

    def test_app_has_fastapi(self):
        app = App()
        assert isinstance(app._fastapi, FastAPI)

    def test_app_campaign_initially_none(self):
        app = App()
        assert app.campaign is None


# ---------------------------------------------------------------------------
# server-get-actor: App.get_actor classmethod (lazy, cached, unknown)
# ---------------------------------------------------------------------------


class TestAppGetActor:
    def test_get_actor_lazy_user(self):
        # server-get-actor-lazy: first "user" call instantiates a UserActor.
        actor = App.get_actor("user")
        assert isinstance(actor, UserActor)

    def test_get_actor_lazy_stub(self):
        # server-get-actor-lazy: first "stub" call instantiates a StubActor.
        actor = App.get_actor("stub")
        assert isinstance(actor, StubActor)

    def test_get_actor_cached(self):
        # server-get-actor-cached: second call returns the same instance.
        a1 = App.get_actor("user")
        a2 = App.get_actor("user")
        assert a1 is a2

    def test_get_actor_cached_per_owner(self):
        # server-get-actor-cached: separate cache slot per owner.
        u = App.get_actor("user")
        s = App.get_actor("stub")
        assert u is not s
        assert App.get_actor("user") is u
        assert App.get_actor("stub") is s

    def test_get_actor_unknown_raises_keyerror(self):
        # server-get-actor-unknown: unknown owner → KeyError.
        with pytest.raises(KeyError):
            App.get_actor("totally-unknown-owner")

    def test_actors_dict_class_level(self):
        # _actors is a class-level dict on App.
        assert isinstance(App._actors, dict)

    def test_factory_class_level_attribute_settable(self):
        # App.factory is a class-level attribute that can be set
        # before Campaign.load by App.run.
        sentinel = object()
        App.factory = sentinel
        assert App.factory is sentinel


# ---------------------------------------------------------------------------
# rest-api-get-root: GET /
# ---------------------------------------------------------------------------


class TestGetRoot:
    def test_root_503_when_loading(self):
        # rest-api-root-503: 503 if state == LOADING.
        app = App()
        with TestClient(app._fastapi) as client:
            response = client.get("/")
        assert response.status_code == 503

    def test_root_inline_html_fallback(self, tmp_path, monkeypatch):
        # rest-api-root-fallback: inline HTML if static dir absent.
        app, *_ = make_loaded_app()
        with patch("sidestage.server._STATIC_DIR", tmp_path / "does-not-exist"):
            with TestClient(app._fastapi) as client:
                response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "<html" in response.text.lower()

    def test_root_serves_static_when_present(self, tmp_path):
        # rest-api-root-static: serves static index.html when dir exists.
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        (static_dir / "index.html").write_text("<!doctype html><h1>STATIC</h1>")
        app, *_ = make_loaded_app()
        with patch("sidestage.server._STATIC_DIR", static_dir):
            with TestClient(app._fastapi) as client:
                response = client.get("/")
        assert response.status_code == 200
        assert "STATIC" in response.text

    def test_root_returns_200_when_serving(self):
        # server-route-root: serves root when SERVING.
        app, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


# ---------------------------------------------------------------------------
# rest-api-get-scene: GET /api/scenes/active
# ---------------------------------------------------------------------------


class TestGetActiveScene:
    def test_scene_503_when_loading(self):
        # rest-api-scene-503.
        app = App()
        with TestClient(app._fastapi) as client:
            response = client.get("/api/scenes/active")
        assert response.status_code == 503

    def test_scene_returns_response(self):
        # server-route-scene: returns SceneResponse for active scene.
        # Player ids derive from `owner == "user"` per character spec.
        app, scene, human, npc = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.get("/api/scenes/active")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == "s1"
        assert body["name"] == "Test Scene"
        assert set(body["character_ids"]) == {"bob", "elara"}
        assert body["player_character_ids"] == ["bob"]


# ---------------------------------------------------------------------------
# rest-api-get-entity: GET /api/entities/{entity_id}
# ---------------------------------------------------------------------------


class TestGetEntity:
    def test_entity_503_when_loading(self):
        # rest-api-entity-503.
        app = App()
        with TestClient(app._fastapi) as client:
            response = client.get("/api/entities/anyid")
        assert response.status_code == 503

    def test_entity_404_when_missing(self):
        # rest-api-entity-404: factory.get returns None.
        app, *_ = make_loaded_app()
        app.campaign.factory.get = MagicMock(return_value=None)
        with TestClient(app._fastapi) as client:
            response = client.get("/api/entities/missing")
        assert response.status_code == 404

    def test_entity_404_when_unresolved(self):
        # rest-api-entity-404: ghost (unresolved) entity should 404.
        from sidestage.entity import Entity, UnresolvedEntityError

        ghost = Entity.__new__(Entity)
        object.__setattr__(ghost, "id", EntityId("ghost-id"))
        object.__setattr__(ghost, "_loaded", False)

        app, *_ = make_loaded_app()
        app.campaign.factory.get = MagicMock(return_value=ghost)
        with TestClient(app._fastapi) as client:
            response = client.get("/api/entities/ghost-id")
        assert response.status_code == 404

    def test_entity_returns_serialized_model(self):
        # server-route-entity: returns factory.get(id).serialize().
        # Use a hand-built mock entity to avoid coupling to Character internals.
        mock_entity = MagicMock()
        mock_model = MagicMock()
        mock_model.model_dump = MagicMock(return_value={
            "id": "alice",
            "name": "Alice",
            "type": "character",
            "body": "Body",
            "owner": "npc",
        })
        mock_entity.serialize = MagicMock(return_value=mock_model)

        app, *_ = make_loaded_app()
        app.campaign.factory.get = MagicMock(return_value=mock_entity)
        with TestClient(app._fastapi) as client:
            response = client.get("/api/entities/alice")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == "alice"
        assert body["name"] == "Alice"
        assert body["owner"] == "npc"


# ---------------------------------------------------------------------------
# rest-api-get-messages: GET /api/scenes/{scene_id}/messages
# ---------------------------------------------------------------------------


class TestGetMessages:
    def _seed_messages(self, scene, count: int = 3) -> None:
        for i in range(count):
            scene.messages.append(Message(sender=scene.characters[0], body=f"m{i}"))

    def test_messages_503_when_loading(self):
        # rest-api-get-messages-503.
        app = App()
        with TestClient(app._fastapi) as client:
            response = client.get("/api/scenes/s1/messages")
        assert response.status_code == 503

    def test_messages_404_when_scene_id_mismatch(self):
        # rest-api-get-messages-404.
        app, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.get("/api/scenes/other/messages")
        assert response.status_code == 404

    def test_messages_default_full_range(self):
        # rest-api-get-messages-build: defaults from=0, to=len(messages).
        # Half-open: range(0, n) covers all n messages.
        app, scene, *_ = make_loaded_app()
        self._seed_messages(scene, 3)
        with TestClient(app._fastapi) as client:
            response = client.get("/api/scenes/s1/messages")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 3
        assert body[0]["id"] == "s1:0"
        assert body[2]["id"] == "s1:2"
        assert body[1]["body"] == "m1"

    def test_messages_with_from_and_to_half_open(self):
        # rest-api-get-messages-build: half-open range.
        # ?from=1&to=3 yields indices [1, 2] (3 is exclusive).
        app, scene, *_ = make_loaded_app()
        self._seed_messages(scene, 5)
        with TestClient(app._fastapi) as client:
            response = client.get("/api/scenes/s1/messages?from=1&to=3")
        assert response.status_code == 200
        body = response.json()
        assert [m["id"] for m in body] == ["s1:1", "s1:2"]

    def test_messages_to_equals_len(self):
        # to == len(messages) is valid (half-open upper bound).
        app, scene, *_ = make_loaded_app()
        self._seed_messages(scene, 3)
        with TestClient(app._fastapi) as client:
            response = client.get("/api/scenes/s1/messages?from=0&to=3")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 3

    def test_messages_from_equals_to_returns_empty(self):
        # from == to: empty half-open range.
        app, scene, *_ = make_loaded_app()
        self._seed_messages(scene, 3)
        with TestClient(app._fastapi) as client:
            response = client.get("/api/scenes/s1/messages?from=2&to=2")
        assert response.status_code == 200
        assert response.json() == []

    def test_messages_empty_returns_empty_list(self):
        # rest-api-get-messages-empty: empty scene returns 200 [] (NOT 422).
        # Default is from=0, to=len(messages)=0. range(0,0) yields nothing.
        app, scene, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.get("/api/scenes/s1/messages")
        assert response.status_code == 200
        assert response.json() == []

    def test_messages_422_negative_from(self):
        # rest-api-get-messages-422: negative from.
        app, scene, *_ = make_loaded_app()
        self._seed_messages(scene, 2)
        with TestClient(app._fastapi) as client:
            response = client.get("/api/scenes/s1/messages?from=-1&to=1")
        assert response.status_code == 422

    def test_messages_422_negative_to(self):
        # rest-api-get-messages-422: negative to.
        app, scene, *_ = make_loaded_app()
        self._seed_messages(scene, 2)
        with TestClient(app._fastapi) as client:
            response = client.get("/api/scenes/s1/messages?from=0&to=-1")
        assert response.status_code == 422

    def test_messages_422_to_greater_than_len(self):
        # rest-api-get-messages-422: to > len(messages).
        app, scene, *_ = make_loaded_app()
        self._seed_messages(scene, 2)
        with TestClient(app._fastapi) as client:
            response = client.get("/api/scenes/s1/messages?from=0&to=99")
        assert response.status_code == 422

    def test_messages_422_from_greater_than_to(self):
        # rest-api-get-messages-422: from > to.
        app, scene, *_ = make_loaded_app()
        self._seed_messages(scene, 5)
        with TestClient(app._fastapi) as client:
            response = client.get("/api/scenes/s1/messages?from=3&to=1")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# rest-api-post-message: POST /api/scenes/{scene_id}/messages
# ---------------------------------------------------------------------------


class TestPostMessage:
    def test_post_503_when_loading(self):
        # rest-api-post-503.
        app = App()
        with TestClient(app._fastapi) as client:
            response = client.post(
                "/api/scenes/s1/messages",
                json={"sender_id": "bob", "body": "hi"},
            )
        assert response.status_code == 503

    def test_post_404_when_scene_id_mismatch(self):
        # rest-api-post-404.
        app, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.post(
                "/api/scenes/other/messages",
                json={"sender_id": "bob", "body": "hi"},
            )
        assert response.status_code == 404

    def test_post_422_when_bad_body(self):
        # rest-api-post-422: pydantic validation failure.
        app, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.post(
                "/api/scenes/s1/messages",
                json={"body": "missing sender_id"},
            )
        assert response.status_code == 422

    def test_post_422_when_sender_not_player(self):
        # rest-api-post-422: sender_id not in player_character_ids.
        app, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.post(
                "/api/scenes/s1/messages",
                json={"sender_id": "elara", "body": "hi"},  # elara is npc, not player
            )
        assert response.status_code == 422

    def test_post_dispatches_and_returns_id(self):
        # rest-api-post-dispatch + rest-api-post-returns.
        app, scene, human, npc = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.post(
                "/api/scenes/s1/messages",
                json={"sender_id": "bob", "body": "hello"},
            )
        assert response.status_code == 201
        body = response.json()
        assert body["id"] == "s1:0"
        scene.dispatch.assert_called_once()
        msg = scene.dispatch.call_args[0][0]
        assert isinstance(msg, Message)
        assert msg.sender is human
        assert msg.body == "hello"


# ---------------------------------------------------------------------------
# rest-api-get-events: GET /api/events
# ---------------------------------------------------------------------------


class TestGetEvents:
    def test_events_503_when_loading(self):
        # rest-api-events-503.
        app = App()
        with TestClient(app._fastapi) as client:
            response = client.get("/api/events")
        assert response.status_code == 503

    def test_events_route_registered(self):
        # rest-api-get-events: route GET /api/events exists on the FastAPI app.
        app, *_ = make_loaded_app()
        paths = {route.path for route in app._fastapi.routes if hasattr(route, "path")}
        assert "/api/events" in paths

    async def test_events_accept_calls_add_queue_on_user_actor_singleton(self):
        # rest-api-events-accept: on connect, gets the user actor via
        # App.get_actor("user") and calls add_queue(queue) on it. NO actor swap
        # on the character. Drive the route directly (avoid sync TestClient
        # which can't open and close an SSE generator cleanly).
        # UserActor is now constructed with NO arguments per the spec change.
        app, scene, human, npc = make_loaded_app()
        user_actor_singleton = UserActor()
        App._actors["user"] = user_actor_singleton

        original_actor = human._actor

        # Locate the get_events route handler.
        handler = None
        for r in app._fastapi.routes:
            if getattr(r, "path", None) == "/api/events":
                handler = r.endpoint
                break
        assert handler is not None

        # Build a minimal request stub. The handler only needs `is_disconnected`
        # to be awaitable in the streaming generator (called inside the loop).
        request = MagicMock()

        async def is_disconnected() -> bool:
            return True

        request.is_disconnected = is_disconnected

        response = await handler(request)
        # The streaming response carries the body iterator; the route handler
        # itself has already called add_queue on the singleton.
        # `_queues` is the (private) backing list per actor-spec.
        assert len(user_actor_singleton._queues) == 1
        # Drain the iterator so the `finally` block fires `on_close` ->
        # remove_queue. is_disconnected returns True so the loop exits at top.
        body_iter = response.body_iterator
        async for _ in body_iter:
            pass

        assert user_actor_singleton._queues == []
        # Character actor is untouched (no actor swap).
        assert human._actor is original_actor

    async def test_events_cleanup_calls_remove_queue(self):
        # rest-api-events-cleanup: on disconnect, the queue is removed from
        # the UserActor singleton. The singleton itself remains in App._actors
        # for any other connected clients.
        # UserActor is now constructed with NO arguments per the spec change.
        app, scene, human, npc = make_loaded_app()
        user_actor_singleton = UserActor()
        App._actors["user"] = user_actor_singleton

        handler = None
        for r in app._fastapi.routes:
            if getattr(r, "path", None) == "/api/events":
                handler = r.endpoint
                break
        assert handler is not None

        request = MagicMock()

        async def is_disconnected() -> bool:
            return True

        request.is_disconnected = is_disconnected

        response = await handler(request)
        async for _ in response.body_iterator:
            pass

        assert user_actor_singleton._queues == []
        # Singleton stays put for any other (or future) connected clients.
        assert App._actors.get("user") is user_actor_singleton

    async def test_sse_event_stream_yields_scene_updated(self):
        # rest-api-events-yield + sse-dataflow-event: helper emits a
        # `event: scene_updated\ndata: {json}\n\n` block per dequeued event.
        from sidestage.server import _sse_event_stream

        queue: asyncio.Queue = asyncio.Queue()
        await queue.put(
            SceneUpdatedEvent(scene_id=EntityId("s1"), latest_message_index=2)
        )

        gen = _sse_event_stream(queue=queue, request=None, keepalive_interval_s=5.0)
        chunk = await gen.__anext__()
        await gen.aclose()

        text = chunk.decode("utf-8")
        assert "event: scene_updated" in text
        assert "\n\n" in text
        data_line = [
            line for line in text.splitlines() if line.startswith("data: ")
        ][0][len("data: "):]
        payload = json.loads(data_line)
        assert payload["scene_id"] == "s1"
        assert payload["latest_message_index"] == 2

    async def test_sse_event_stream_keepalive_on_idle(self):
        # rest-api-events-keepalive: ": keepalive" comment when queue is idle.
        from sidestage.server import _sse_event_stream

        queue: asyncio.Queue = asyncio.Queue()
        gen = _sse_event_stream(
            queue=queue, request=None, keepalive_interval_s=0.05
        )
        chunk = await gen.__anext__()
        await gen.aclose()
        assert chunk == b": keepalive\n\n"

    async def test_sse_event_stream_invokes_on_close(self):
        # rest-api-events-cleanup: on_close called when the generator exits.
        from sidestage.server import _sse_event_stream

        called: list[bool] = []
        queue: asyncio.Queue = asyncio.Queue()
        gen = _sse_event_stream(
            queue=queue,
            request=None,
            on_close=lambda: called.append(True),
            keepalive_interval_s=0.05,
        )
        # Drain one keepalive then close.
        await gen.__anext__()
        await gen.aclose()
        assert called == [True]


# ---------------------------------------------------------------------------
# server-run-*: App.run classmethod behaviour.
# ---------------------------------------------------------------------------


class TestAppRun:
    def test_run_default_config_dir(self):
        # server-run-config: default "configs/".
        with patch("sidestage.server.uvicorn.run") as run_mock, patch(
            "sidestage.server.Campaign.load"
        ) as load_mock, patch(
            "sidestage.server.Path"
        ) as path_mock, patch(
            "sidestage.server.DictEntityFactory"
        ) as factory_mock:
            path_mock.return_value.iterdir.return_value = iter([MagicMock()])
            load_mock.return_value = MagicMock()
            factory_mock.return_value = MagicMock()
            App.run()
        run_mock.assert_called_once()

    def test_run_custom_config_dir(self):
        with patch("sidestage.server.uvicorn.run") as run_mock, patch(
            "sidestage.server.Campaign.load"
        ) as load_mock, patch(
            "sidestage.server.Path"
        ) as path_mock, patch(
            "sidestage.server.DictEntityFactory"
        ) as factory_mock:
            path_mock.return_value.iterdir.return_value = iter([MagicMock()])
            load_mock.return_value = MagicMock()
            factory_mock.return_value = MagicMock()
            App.run(config_dir="my/configs/")
            path_mock.assert_called_with("my/configs/")
        run_mock.assert_called_once()

    def test_run_loads_campaign_and_serves(self):
        # server-run-state-loading + server-run-load + server-run-state-serving + server-run-serve.
        captured = {}

        def fake_uvicorn_run(app_obj, **kwargs):
            captured["called"] = True

        fake_campaign = MagicMock()

        with patch("sidestage.server.uvicorn.run", side_effect=fake_uvicorn_run), patch(
            "sidestage.server.Campaign.load", return_value=fake_campaign
        ) as load_mock, patch(
            "sidestage.server.Path"
        ) as path_mock, patch(
            "sidestage.server.DictEntityFactory"
        ) as factory_mock:
            path_mock.return_value.iterdir.return_value = iter([MagicMock()])
            factory_mock.return_value = MagicMock()
            App.run(config_dir="cfgs/")

        load_mock.assert_called_once()
        assert captured.get("called") is True

    def test_run_sets_factory_before_load(self):
        # App.factory is set BEFORE Campaign.load so deserialize-time code
        # can reach the factory via App.factory.
        observed = {}

        def fake_load(path):
            # When Campaign.load is invoked, App.factory must already be set.
            observed["factory_set"] = hasattr(App, "factory") and App.factory is not None
            return MagicMock()

        with patch("sidestage.server.uvicorn.run"), patch(
            "sidestage.server.Campaign.load", side_effect=fake_load
        ), patch(
            "sidestage.server.Path"
        ) as path_mock, patch(
            "sidestage.server.DictEntityFactory"
        ) as factory_mock:
            path_mock.return_value.iterdir.return_value = iter([MagicMock()])
            factory_mock.return_value = MagicMock()
            App.run(config_dir="cfgs/")

        assert observed.get("factory_set") is True


# ---------------------------------------------------------------------------
# api-dataflow / sse-dataflow integration sanity
# ---------------------------------------------------------------------------


class TestEndpointDataflowIntegration:
    def test_subscribe_then_fetch_pattern(self):
        # api-dataflow-subscribe + api-dataflow-scene + api-dataflow-history.
        app, scene, human, npc = make_loaded_app()
        scene.messages.append(Message(sender=human, body="hi"))

        with TestClient(app._fastapi) as client:
            r1 = client.get("/api/scenes/active")
            r2 = client.get("/api/scenes/s1/messages")
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["id"] == "s1"
        assert len(r2.json()) == 1
