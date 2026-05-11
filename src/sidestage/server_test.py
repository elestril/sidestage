from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Iterator
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from sidestage.actor import StubActor, UserActor
from sidestage.campaign import CampaignResponse
from sidestage.entity import EntityId
from sidestage.events import EntityChanged
from sidestage.message import Message
from sidestage.scene import SceneResponse
from sidestage.server import (
    App,
    MessageAccepted,
    MessageRequest,
    ServerState,
)

# ---------------------------------------------------------------------------
# Helpers — mock builders for the cross-file deps that may not yet match spec.
# ---------------------------------------------------------------------------


def _reset_actor_registry() -> None:
    """Clear the App-level actor registry between tests."""
    App._actors = {}


@pytest.fixture(autouse=True)
def _clear_app_state() -> Iterator[None]:
    """Each test starts with a clean App class-level registry/factory."""
    _reset_actor_registry()
    if hasattr(App, "factory"):
        with contextlib.suppress(AttributeError):
            del App.factory
    yield
    _reset_actor_registry()
    if hasattr(App, "factory"):
        with contextlib.suppress(AttributeError):
            del App.factory


def make_human_character(id: str = "bob") -> MagicMock:
    """A character whose `has_human_actor()` is True."""
    char = MagicMock(spec=[])
    char.id = EntityId(id)
    char.name = id.capitalize()
    char._actor = StubActor()
    char.has_human_actor = lambda: True
    return char


def make_npc_character(id: str = "elara") -> MagicMock:
    char = MagicMock(spec=[])
    char.id = EntityId(id)
    char.name = id.capitalize()
    char._actor = StubActor()
    char.has_human_actor = lambda: False
    return char


def make_scene(human, npc, scene_id: str = "s1") -> MagicMock:
    """Mock Scene exposing the surface the server now relies on:
    - `to_response()` builds the wire shape (server no longer constructs it).
    - `user_characters` is the player-character subset.
    - `serialize_message`, `messages`, `append` are the message API.
    """
    scene = MagicMock(spec=[])
    scene.id = EntityId(scene_id)
    scene.name = "Test Scene"
    scene.characters = [human, npc]
    scene.user_characters = [c for c in scene.characters if c.has_human_actor()]
    scene.messages = []

    def to_response() -> SceneResponse:
        return SceneResponse(
            id=scene.id,
            name=scene.name,
            character_ids=[c.id for c in scene.characters],
            player_character_ids=[c.id for c in scene.user_characters],
        )

    def serialize_message(idx: int) -> Message.Model:
        m = scene.messages[idx]
        return Message.Model(
            scene_id=scene.id,
            index=idx,
            sender_id=m.sender.id,
            body=m.body,
        )

    def append(msg: Message) -> int:
        scene.messages.append(msg)
        return len(scene.messages) - 1

    scene.to_response = to_response
    scene.serialize_message = serialize_message
    scene.append = MagicMock(side_effect=append)
    return scene


def make_campaign(scene, name: str = "Test Campaign") -> MagicMock:
    """Mock Campaign exposing the new method surface:
    - `scene(id)` is a method (not an attribute) returning Optional[Scene].
    - `scenes()` is a method returning list[Scene].
    - `default_scene_id` replaces the dropped `active_scene_id`.
    - `to_response()` builds the CampaignResponse.
    - `factory.get(id)` still serves the entity route.
    """
    campaign = MagicMock(spec=[])
    campaign.name = name
    campaign.default_scene_id = scene.id

    def _scene(eid) -> MagicMock | None:
        if eid == scene.id:
            return scene
        return None

    campaign.scene = MagicMock(side_effect=_scene)
    campaign.scenes = MagicMock(return_value=[scene])
    campaign.to_response = lambda: CampaignResponse(
        name=campaign.name,
        default_scene_id=campaign.default_scene_id,
    )
    campaign.factory = MagicMock()

    def _factory_get(eid) -> MagicMock | None:
        if eid == scene.id:
            return scene
        return None

    campaign.factory.get = MagicMock(side_effect=_factory_get)
    return campaign


CAMPAIGN_ID = "Test Campaign"


def make_loaded_app(
    scene_id: str = "s1",
) -> tuple[App, MagicMock, MagicMock, MagicMock]:
    human = make_human_character("bob")
    npc = make_npc_character("elara")
    scene = make_scene(human, npc, scene_id=scene_id)
    campaign = make_campaign(scene)
    app = App()
    app.campaigns = {campaign.name: campaign}
    app.state = ServerState.SERVING
    return app, scene, human, npc


def install_mock_user_actor() -> MagicMock:
    """Install a `MagicMock(spec=UserActor)` at `App._actors["user"]`.

    Per `testing-mock-user-actor`: tests never instantiate a real UserActor.
    The mock records `subscribe_to`/`unsubscribe_from` so SSE-handler tests
    can assert delegation without touching QueueListener internals.
    """
    mock_actor = MagicMock(spec=UserActor)
    App._actors["user"] = mock_actor
    return mock_actor


# ---------------------------------------------------------------------------
# server-state
# ---------------------------------------------------------------------------


class TestServerState:
    def test_loading_value(self) -> None:
        # server-state-loading: enum has LOADING.
        assert ServerState.LOADING is not None

    def test_serving_value(self) -> None:
        # server-state-serving: enum has SERVING.
        assert ServerState.SERVING is not None

    def test_states_distinct(self) -> None:
        assert ServerState.LOADING != ServerState.SERVING


# ---------------------------------------------------------------------------
# Wire models — only those still owned by server.py
# ---------------------------------------------------------------------------


class TestMessageRequest:
    def test_fields(self) -> None:
        req = MessageRequest(sender_id=EntityId("c1"), body="hi")
        assert req.sender_id == "c1"
        assert req.body == "hi"


class TestMessageAccepted:
    def test_fields(self) -> None:
        acc = MessageAccepted(scene_id=EntityId("s1"), index=0)
        assert acc.scene_id == "s1"
        assert acc.index == 0


# ---------------------------------------------------------------------------
# server-app construction
# ---------------------------------------------------------------------------


class TestApp:
    def test_app_initial_state_loading(self) -> None:
        # server-state-loading: initial state is LOADING.
        app = App()
        assert app.state == ServerState.LOADING

    def test_server_run_sidestage_dir(self) -> None:
        # server-run-sidestage-dir: default is "sidestage/".
        app = App()
        assert app.sidestage_dir == "sidestage/", (
            "server-run-sidestage-dir: default sidestage_dir MUST be "
            f"'sidestage/'; got {app.sidestage_dir!r}"
        )

    def test_server_run_sidestage_dir_custom(self) -> None:
        # server-run-sidestage-dir: explicit override flows through.
        app = App(sidestage_dir="my/dir/")
        assert app.sidestage_dir == "my/dir/", (
            "server-run-sidestage-dir: explicit override MUST be preserved "
            f"on App.sidestage_dir; got {app.sidestage_dir!r}"
        )

    def test_app_has_fastapi(self) -> None:
        app = App()
        assert isinstance(app._fastapi, FastAPI)

    def test_app_campaigns_initially_empty(self) -> None:
        app = App()
        assert app.campaigns == {}


# ---------------------------------------------------------------------------
# server-get-actor: App.get_actor classmethod (lazy, cached, unknown)
# ---------------------------------------------------------------------------


class TestAppGetActor:
    def test_get_actor_lazy_user(self) -> None:
        # server-get-actor-lazy: first "user" call instantiates a UserActor.
        actor = App.get_actor("user")
        assert isinstance(actor, UserActor)

    def test_get_actor_lazy_stub(self) -> None:
        # server-get-actor-lazy: first "stub" call instantiates a StubActor.
        actor = App.get_actor("stub")
        assert isinstance(actor, StubActor)

    def test_get_actor_cached(self) -> None:
        # server-get-actor-cached: second call returns the same instance.
        a1 = App.get_actor("user")
        a2 = App.get_actor("user")
        assert a1 is a2

    def test_get_actor_cached_per_owner(self) -> None:
        # server-get-actor-cached: separate cache slot per owner.
        u = App.get_actor("user")
        s = App.get_actor("stub")
        assert u is not s
        assert App.get_actor("user") is u
        assert App.get_actor("stub") is s

    def test_get_actor_unknown_raises_keyerror(self) -> None:
        # server-get-actor-unknown: unknown owner → KeyError.
        with pytest.raises(KeyError):
            App.get_actor("totally-unknown-owner")

    def test_actors_dict_class_level(self) -> None:
        # _actors is a class-level dict on App.
        assert isinstance(App._actors, dict)

    def test_factory_class_level_attribute_settable(self) -> None:
        # App.factory is a class-level attribute that can be set
        # before Campaign.load by App.run.
        sentinel = object()
        App.factory = sentinel  # type: ignore[assignment]  # pyright: ignore[reportAttributeAccessIssue]
        assert App.factory is sentinel


# ---------------------------------------------------------------------------
# Private plumbing: App._current_user
# ---------------------------------------------------------------------------


class TestAppPrivatePlumbing:
    def test_current_user_returns_user(self) -> None:
        # _current_user is a classmethod stub returning "user" today.
        assert App._current_user() == "user"


# ---------------------------------------------------------------------------
# rest-api-get-root: GET /
# ---------------------------------------------------------------------------


class TestGetRoot:
    def test_root_503_when_loading(self, tmp_path) -> None:
        # rest-api-root-503: 503 if state == LOADING. The static-mount
        # branch shadows the inline-HTML route, so a pre-built SPA at
        # src/sidestage/static/ would mask the 503 — patch _STATIC_DIR
        # to a missing path so the inline route is registered.
        with patch("sidestage.server._STATIC_DIR", tmp_path / "does-not-exist"):
            app = App()
        with TestClient(app._fastapi) as client:
            response = client.get("/")
        assert response.status_code == 503, (
            "rest-api-root-503: GET / returns 503 while App.state == LOADING; "
            f"got status={response.status_code}"
        )

    def test_root_falls_back_to_inline_when_static_missing(self, tmp_path) -> None:
        # rest-api-root-fallback: inline HTML when static dir is absent.
        # The static-dir decision is made at App construction time, so the
        # patch wraps the App() call inside `make_loaded_app`.
        with patch("sidestage.server._STATIC_DIR", tmp_path / "does-not-exist"):
            app, *_ = make_loaded_app()
            with TestClient(app._fastapi) as client:
                response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "<html" in response.text.lower()

    def test_root_serves_static_index_when_static_dir_exists(self, tmp_path) -> None:
        # frontend-serve-mount: StaticFiles mount serves index.html at `/`
        # when the static dir exists.
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        (static_dir / "index.html").write_text("<!doctype html><h1>STATIC</h1>")
        with patch("sidestage.server._STATIC_DIR", static_dir):
            app, *_ = make_loaded_app()
            with TestClient(app._fastapi) as client:
                response = client.get("/")
        assert response.status_code == 200
        assert "STATIC" in response.text

    def test_root_serves_static_assets(self, tmp_path) -> None:
        # frontend-serve-mount: StaticFiles mount serves assets alongside
        # index.html. `/app.js` is reachable through the same mount.
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        (static_dir / "index.html").write_text("<!doctype html><h1>STATIC</h1>")
        (static_dir / "app.js").write_text("console.log('hi');")
        with patch("sidestage.server._STATIC_DIR", static_dir):
            app, *_ = make_loaded_app()
            with TestClient(app._fastapi) as client:
                response = client.get("/app.js")
        assert response.status_code == 200
        assert "console.log" in response.text

    def test_root_returns_200_when_serving(self) -> None:
        # server-route-root: serves root when SERVING (default: no static dir
        # in the repo, so the inline HTML fallback handles `/`).
        app, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


# ---------------------------------------------------------------------------
# rest-api-list-campaigns: GET /api/campaigns
# ---------------------------------------------------------------------------


class TestListCampaigns:
    def test_list_503_when_loading(self) -> None:
        # rest-api-list-campaigns-503.
        app = App()
        with TestClient(app._fastapi) as client:
            response = client.get("/api/campaigns")
        assert response.status_code == 503

    def test_list_returns_one_entry_today(self) -> None:
        # server-route-list-campaigns: returns list[CampaignResponse] from
        # `App.campaigns.values()`. Today there is exactly one entry.
        app, scene, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.get("/api/campaigns")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["name"] == "Test Campaign"
        assert body[0]["default_scene_id"] == "s1"

    def test_list_empty_returns_empty_list(self) -> None:
        # server-route-list-campaigns: empty App.campaigns -> [].
        app = App()
        app.state = ServerState.SERVING
        with TestClient(app._fastapi) as client:
            response = client.get("/api/campaigns")
        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# rest-api-get-campaign: GET /api/campaigns/{cid}
# ---------------------------------------------------------------------------


class TestGetCampaign:
    def test_campaign_503_when_loading(self) -> None:
        # rest-api-campaign-503.
        app = App()
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}")
        assert response.status_code == 503

    def test_campaign_404_when_unknown(self) -> None:
        # rest-api-campaign-404: campaigns.get returns None -> 404.
        app, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.get("/api/campaigns/no-such-campaign")
        assert response.status_code == 404

    def test_campaign_returns_response(self) -> None:
        # server-route-campaign: returns CampaignResponse from
        # `campaign.to_response()`. Server constructs nothing.
        app, scene, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}")
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Test Campaign"
        assert body["default_scene_id"] == "s1"

    def test_campaign_delegates_to_campaign_to_response(self) -> None:
        # The route must call `campaign.to_response()`, not build its own
        # CampaignResponse.
        app, *_ = make_loaded_app()
        campaign = app.campaigns[CAMPAIGN_ID]
        campaign.to_response = MagicMock(
            return_value=CampaignResponse(name="X", default_scene_id=None)
        )
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}")
        assert response.status_code == 200
        campaign.to_response.assert_called_once()
        assert response.json() == {"name": "X", "default_scene_id": None}


# ---------------------------------------------------------------------------
# rest-api-get-scenes: GET /api/scenes
# ---------------------------------------------------------------------------


class TestGetScenes:
    def test_scenes_503_when_loading(self) -> None:
        # rest-api-scenes-503.
        app = App()
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}/scenes")
        assert response.status_code == 503

    def test_scenes_404_when_campaign_unknown(self) -> None:
        # 404 when campaign id is unknown.
        app, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.get("/api/campaigns/no-such/scenes")
        assert response.status_code == 404

    def test_scenes_returns_list_of_scene_responses(self) -> None:
        # server-route-scenes: returns list[SceneResponse] = one entry per
        # scene in `campaign.scenes()`.
        app, scene, human, npc = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}/scenes")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["id"] == "s1"
        assert body[0]["name"] == "Test Scene"
        assert set(body[0]["character_ids"]) == {"bob", "elara"}
        assert body[0]["player_character_ids"] == ["bob"]

    def test_scenes_delegates_to_campaign_scenes(self) -> None:
        # Server iterates `campaign.scenes()`, not factory internals.
        app, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            client.get(f"/api/campaigns/{CAMPAIGN_ID}/scenes")
        app.campaigns[CAMPAIGN_ID].scenes.assert_called_once()  # type: ignore[attr-defined]

    def test_scenes_empty_campaign_returns_empty_list(self) -> None:
        app, *_ = make_loaded_app()
        app.campaigns[CAMPAIGN_ID].scenes = MagicMock(return_value=[])
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}/scenes")
        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# rest-api-get-scene: GET /api/scenes/{scene_id}
# ---------------------------------------------------------------------------


class TestGetScene:
    def test_scene_503_when_loading(self) -> None:
        # rest-api-scene-503.
        app = App()
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}/scenes/s1")
        assert response.status_code == 503

    def test_scene_404_when_campaign_unknown(self) -> None:
        # 404 when campaign id is unknown.
        app, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.get("/api/campaigns/no-such/scenes/s1")
        assert response.status_code == 404

    def test_scene_returns_response(self) -> None:
        # server-route-scene: returns the SceneResponse from
        # `campaign.scene(id).to_response()`. Server constructs nothing.
        app, scene, human, npc = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}/scenes/s1")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == "s1"
        assert body["name"] == "Test Scene"
        assert set(body["character_ids"]) == {"bob", "elara"}
        assert body["player_character_ids"] == ["bob"]

    def test_scene_404_when_unknown(self) -> None:
        # rest-api-scene-404: campaign.scene returns None -> 404.
        app, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}/scenes/no-such-scene")
        assert response.status_code == 404

    def test_scene_delegates_to_campaign_scene(self) -> None:
        # Server resolves the scene via `campaign.scene(id)`, never via
        # any singular "active scene" helper.
        app, scene, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            client.get(f"/api/campaigns/{CAMPAIGN_ID}/scenes/s1")
        app.campaigns[CAMPAIGN_ID].scene.assert_called_with(EntityId("s1"))  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# rest-api-get-entity: GET /api/entities/{entity_id}
# ---------------------------------------------------------------------------


class TestGetEntity:
    def test_entity_503_when_loading(self) -> None:
        # rest-api-entity-503.
        app = App()
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}/entities/anyid")
        assert response.status_code == 503

    def test_entity_404_when_campaign_unknown(self) -> None:
        # 404 when campaign id is unknown.
        app, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.get("/api/campaigns/no-such/entities/anyid")
        assert response.status_code == 404

    def test_entity_404_when_missing(self) -> None:
        # rest-api-entity-404: factory.get returns None.
        app, *_ = make_loaded_app()
        app.campaigns[CAMPAIGN_ID].factory.get = MagicMock(return_value=None)
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}/entities/missing")
        assert response.status_code == 404

    def test_entity_404_when_unresolved(self) -> None:
        # rest-api-entity-404: ghost (unresolved) entity should 404.
        from sidestage.entity import Entity

        ghost = Entity.__new__(Entity)
        object.__setattr__(ghost, "id", EntityId("ghost-id"))
        object.__setattr__(ghost, "_loaded", False)

        app, *_ = make_loaded_app()
        app.campaigns[CAMPAIGN_ID].factory.get = MagicMock(return_value=ghost)
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}/entities/ghost-id")
        assert response.status_code == 404

    def test_entity_returns_serialized_model(self) -> None:
        # server-route-entity: returns factory.get(id).serialize().
        # Use a hand-built mock entity to avoid coupling to Character internals.
        mock_entity = MagicMock()
        mock_model = MagicMock()
        mock_model.model_dump = MagicMock(
            return_value={
                "id": "alice",
                "name": "Alice",
                "type": "character",
                "body": "Body",
                "owner": "stub",
            }
        )
        mock_entity.serialize = MagicMock(return_value=mock_model)

        app, *_ = make_loaded_app()
        app.campaigns[CAMPAIGN_ID].factory.get = MagicMock(return_value=mock_entity)
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}/entities/alice")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == "alice"
        assert body["name"] == "Alice"
        assert body["owner"] == "stub"


# ---------------------------------------------------------------------------
# rest-api-get-messages: GET /api/scenes/{scene_id}/messages
# ---------------------------------------------------------------------------


class TestGetMessages:
    def _seed_messages(self, scene, count: int = 3) -> None:
        for i in range(count):
            scene.messages.append(Message(sender=scene.characters[0], body=f"m{i}"))

    def test_messages_503_when_loading(self) -> None:
        # rest-api-get-messages-503.
        app = App()
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}/scenes/s1/messages")
        assert response.status_code == 503

    def test_messages_404_when_campaign_unknown(self) -> None:
        # 404 when campaign id is unknown.
        app, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.get("/api/campaigns/no-such/scenes/s1/messages")
        assert response.status_code == 404

    def test_messages_404_when_scene_unknown(self) -> None:
        # rest-api-get-messages-404: campaign.scene returns None.
        app, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}/scenes/other/messages")
        assert response.status_code == 404

    def test_messages_default_full_range(self) -> None:
        # rest-api-get-messages-build: defaults from=0, to=len(messages).
        # Half-open: range(0, n) covers all n messages.
        app, scene, *_ = make_loaded_app()
        self._seed_messages(scene, 3)
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}/scenes/s1/messages")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 3
        assert body[0]["scene_id"] == "s1" and body[0]["index"] == 0, (
            "message-model-fields: serialized messages MUST carry scene_id "
            f"and index on the wire; got body[0]={body[0]!r}"
        )
        assert body[2]["scene_id"] == "s1" and body[2]["index"] == 2
        assert body[1]["body"] == "m1"

    def test_messages_with_from_and_to_half_open(self) -> None:
        # rest-api-get-messages-build: half-open range.
        # ?from=1&to=3 yields indices [1, 2] (3 is exclusive).
        app, scene, *_ = make_loaded_app()
        self._seed_messages(scene, 5)
        with TestClient(app._fastapi) as client:
            response = client.get(
                f"/api/campaigns/{CAMPAIGN_ID}/scenes/s1/messages?from=1&to=3"
            )
        assert response.status_code == 200
        body = response.json()
        assert [(m["scene_id"], m["index"]) for m in body] == [
            ("s1", 1),
            ("s1", 2),
        ]

    def test_messages_to_equals_len(self) -> None:
        # to == len(messages) is valid (half-open upper bound).
        app, scene, *_ = make_loaded_app()
        self._seed_messages(scene, 3)
        with TestClient(app._fastapi) as client:
            response = client.get(
                f"/api/campaigns/{CAMPAIGN_ID}/scenes/s1/messages?from=0&to=3"
            )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 3

    def test_messages_from_equals_to_returns_empty(self) -> None:
        # from == to: empty half-open range.
        app, scene, *_ = make_loaded_app()
        self._seed_messages(scene, 3)
        with TestClient(app._fastapi) as client:
            response = client.get(
                f"/api/campaigns/{CAMPAIGN_ID}/scenes/s1/messages?from=2&to=2"
            )
        assert response.status_code == 200
        assert response.json() == []

    def test_messages_empty_returns_empty_list(self) -> None:
        # rest-api-get-messages-empty: empty scene returns 200 [] (NOT 422).
        # Default is from=0, to=len(messages)=0. range(0,0) yields nothing.
        app, scene, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}/scenes/s1/messages")
        assert response.status_code == 200
        assert response.json() == []

    def test_messages_422_negative_from(self) -> None:
        # rest-api-get-messages-422: negative from.
        app, scene, *_ = make_loaded_app()
        self._seed_messages(scene, 2)
        with TestClient(app._fastapi) as client:
            response = client.get(
                f"/api/campaigns/{CAMPAIGN_ID}/scenes/s1/messages?from=-1&to=1"
            )
        assert response.status_code == 422

    def test_messages_422_negative_to(self) -> None:
        # rest-api-get-messages-422: negative to.
        app, scene, *_ = make_loaded_app()
        self._seed_messages(scene, 2)
        with TestClient(app._fastapi) as client:
            response = client.get(
                f"/api/campaigns/{CAMPAIGN_ID}/scenes/s1/messages?from=0&to=-1"
            )
        assert response.status_code == 422

    def test_messages_422_to_greater_than_len(self) -> None:
        # rest-api-get-messages-422: to > len(messages).
        app, scene, *_ = make_loaded_app()
        self._seed_messages(scene, 2)
        with TestClient(app._fastapi) as client:
            response = client.get(
                f"/api/campaigns/{CAMPAIGN_ID}/scenes/s1/messages?from=0&to=99"
            )
        assert response.status_code == 422

    def test_messages_422_from_greater_than_to(self) -> None:
        # rest-api-get-messages-422: from > to.
        app, scene, *_ = make_loaded_app()
        self._seed_messages(scene, 5)
        with TestClient(app._fastapi) as client:
            response = client.get(
                f"/api/campaigns/{CAMPAIGN_ID}/scenes/s1/messages?from=3&to=1"
            )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# rest-api-post-message: POST /api/scenes/{scene_id}/messages
# ---------------------------------------------------------------------------


class TestPostMessage:
    def test_post_503_when_loading(self) -> None:
        # rest-api-post-503.
        app = App()
        with TestClient(app._fastapi) as client:
            response = client.post(
                f"/api/campaigns/{CAMPAIGN_ID}/scenes/s1/messages",
                json={"sender_id": "bob", "body": "hi"},
            )
        assert response.status_code == 503

    def test_post_404_when_campaign_unknown(self) -> None:
        # 404 when campaign id is unknown.
        app, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.post(
                "/api/campaigns/no-such/scenes/s1/messages",
                json={"sender_id": "bob", "body": "hi"},
            )
        assert response.status_code == 404

    def test_post_404_when_scene_unknown(self) -> None:
        # rest-api-post-404: campaign.scene returns None.
        app, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.post(
                f"/api/campaigns/{CAMPAIGN_ID}/scenes/other/messages",
                json={"sender_id": "bob", "body": "hi"},
            )
        assert response.status_code == 404

    def test_post_422_when_bad_body(self) -> None:
        # rest-api-post-422: pydantic validation failure.
        app, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.post(
                f"/api/campaigns/{CAMPAIGN_ID}/scenes/s1/messages",
                json={"body": "missing sender_id"},
            )
        assert response.status_code == 422

    def test_post_422_when_sender_not_player(self) -> None:
        # rest-api-post-422: sender_id not in user_characters.
        app, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.post(
                f"/api/campaigns/{CAMPAIGN_ID}/scenes/s1/messages",
                json={"sender_id": "elara", "body": "hi"},  # elara is npc, not player
            )
        assert response.status_code == 422

    def test_post_appends_and_returns_id(self) -> None:
        # rest-api-post-dispatch + rest-api-post-returns: server calls
        # `scene.append(message)` and returns the assigned (scene_id, index).
        app, scene, human, npc = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.post(
                f"/api/campaigns/{CAMPAIGN_ID}/scenes/s1/messages",
                json={"sender_id": "bob", "body": "hello"},
            )
        assert response.status_code == 201
        body = response.json()
        assert body["scene_id"] == "s1" and body["index"] == 0, (
            "rest-api-post-returns: response carries (scene_id, index) of the "
            f"appended message; got {body!r}"
        )
        scene.append.assert_called_once()
        msg = scene.append.call_args[0][0]
        assert isinstance(msg, Message)
        assert msg.sender is human
        assert msg.body == "hello"


# ---------------------------------------------------------------------------
# rest-api-get-entity-events: GET /api/campaigns/{cid}/entities/{eid}/events
# ---------------------------------------------------------------------------


class TestGetEntityEvents:
    """Per-entity SSE stream — replaces the old global `/api/events`.

    Per `rest-api-get-entity-events` and `events-subscription`. The handler
    resolves the entity, routes the queue subscription through the
    current-user's UserActor (mocked per `testing-mock-user-actor`),
    yields each `EntityChanged` as `event: entity_changed\\ndata: …\\n\\n`,
    and unsubscribes on disconnect.
    """

    def _entity_events_url(self, eid: str = "s1") -> str:
        return f"/api/campaigns/{CAMPAIGN_ID}/entities/{eid}/events"

    def test_entity_events_503_when_loading(self) -> None:
        # rest-api-events-503: server in LOADING state returns 503.
        app = App()
        with TestClient(app._fastapi) as client:
            response = client.get(self._entity_events_url())
        assert response.status_code == 503

    def test_entity_events_404_unknown_campaign(self) -> None:
        # rest-api-events-404: unknown campaign -> 404.
        app, *_ = make_loaded_app()
        install_mock_user_actor()
        with TestClient(app._fastapi) as client:
            response = client.get("/api/campaigns/no-such-campaign/entities/s1/events")
        assert response.status_code == 404

    def test_entity_events_404_unknown_entity(self) -> None:
        # rest-api-events-404: campaign exists but factory.get returns None.
        app, *_ = make_loaded_app()
        install_mock_user_actor()
        # Force factory miss for any id.
        app.campaigns[CAMPAIGN_ID].factory.get = MagicMock(return_value=None)
        with TestClient(app._fastapi) as client:
            response = client.get(self._entity_events_url("ghost-id"))
        assert response.status_code == 404

    async def test_entity_events_subscribes_via_user_actor(self) -> None:
        # rest-api-events-accept / sse-dataflow-accept: handler resolves
        # `App.get_actor(current_user)` and calls
        # `user_actor.subscribe_to(entity, queue)` synchronously on connect.
        # We drive the route handler directly to avoid streaming-client
        # complications and to inspect the (entity, queue) pair.
        app, scene, *_ = make_loaded_app()
        mock_actor = install_mock_user_actor()

        # Drive a queue we control through subscribe_to so we can later
        # verify unsubscribe_from is called with the same queue.
        captured: dict = {}

        def _capture_subscribe(entity, queue) -> None:
            captured["entity"] = entity
            captured["queue"] = queue

        mock_actor.subscribe_to.side_effect = _capture_subscribe

        # Locate the route handler.
        handler = None
        for r in app._fastapi.routes:
            if (
                getattr(r, "path", None)
                == "/api/campaigns/{cid}/entities/{entity_id}/events"
            ):
                handler = cast(Any, r).endpoint
                break
        assert handler is not None

        # Build a request mock that reports immediate disconnect so the
        # generator drains and the finally block fires unsubscribe.
        request = MagicMock()

        async def is_disconnected() -> bool:
            return True

        request.is_disconnected = is_disconnected

        response = await handler(CAMPAIGN_ID, "s1", request)

        # subscribe_to was called once with the resolved entity and a Queue.
        mock_actor.subscribe_to.assert_called_once()
        assert captured["entity"] is scene
        assert isinstance(captured["queue"], asyncio.Queue)

        # Drain the response so the finally block runs.
        async for _ in response.body_iterator:
            pass

        # rest-api-events-cleanup: unsubscribe_from called with the SAME
        # entity and queue.
        mock_actor.unsubscribe_from.assert_called_once_with(scene, captured["queue"])

    async def test_entity_events_yields_entity_changed_frames(self) -> None:
        # rest-api-events-yield + events-subscription: drive the handler
        # directly with a controlled queue and read one frame off
        # `response.body_iterator`. Streaming over httpx wedges on the
        # 15s keepalive after the frame, since `is_disconnected` doesn't
        # flip synchronously when the test client closes; bypassing the
        # client and using a request mock that flips after one frame
        # keeps the test bounded.
        app, scene, *_ = make_loaded_app()
        mock_actor = install_mock_user_actor()

        controlled_queue: asyncio.Queue = asyncio.Queue()
        await controlled_queue.put(EntityChanged(entity=scene, attributes=["messages"]))

        with patch("sidestage.server.asyncio.Queue", return_value=controlled_queue):
            handler = None
            for r in app._fastapi.routes:
                if (
                    getattr(r, "path", None)
                    == "/api/campaigns/{cid}/entities/{entity_id}/events"
                ):
                    handler = cast(Any, r).endpoint
                    break
            assert handler is not None

            # Flip is_disconnected to True after the first poll so the
            # generator exits its loop after delivering the queued frame.
            disconnect_calls = {"n": 0}

            async def is_disconnected() -> bool:
                disconnect_calls["n"] += 1
                # Pass on the first poll (deliver the queued event), then
                # flip on the second poll (stops the loop cleanly).
                return disconnect_calls["n"] > 1

            request = MagicMock()
            request.is_disconnected = is_disconnected

            response = await handler(CAMPAIGN_ID, "s1", request)

            chunks: list[bytes] = []
            async for chunk in response.body_iterator:
                chunks.append(chunk)

        assert chunks, "expected at least one SSE frame"
        text = b"".join(chunks).decode("utf-8")
        assert "event: entity_changed" in text
        data_line = [line for line in text.splitlines() if line.startswith("data: ")][
            0
        ][len("data: ") :]
        payload = json.loads(data_line)
        assert payload == {"entity_id": "s1", "attributes": ["messages"]}

        # subscribe_to was called for the resolved scene with the queue
        # the handler created (which our patch redirected to ours).
        mock_actor.subscribe_to.assert_called_once()
        called_entity, called_queue = mock_actor.subscribe_to.call_args[0]
        assert called_entity is scene
        assert called_queue is controlled_queue

    async def test_entity_events_unsubscribes_on_disconnect(self) -> None:
        # rest-api-events-cleanup / sse-dataflow-disconnect: on client
        # disconnect, the handler calls
        # `user_actor.unsubscribe_from(entity, queue)` in `try/finally`.
        app, scene, *_ = make_loaded_app()
        mock_actor = install_mock_user_actor()

        handler = None
        for r in app._fastapi.routes:
            if (
                getattr(r, "path", None)
                == "/api/campaigns/{cid}/entities/{entity_id}/events"
            ):
                handler = cast(Any, r).endpoint
                break
        assert handler is not None

        # Disconnected request — the stream generator exits its loop and
        # the finally block must invoke unsubscribe.
        request = MagicMock()

        async def is_disconnected() -> bool:
            return True

        request.is_disconnected = is_disconnected

        response = await handler(CAMPAIGN_ID, "s1", request)

        # Drain the streaming body.
        async for _ in response.body_iterator:
            pass

        mock_actor.unsubscribe_from.assert_called_once()
        ent, q = mock_actor.unsubscribe_from.call_args[0]
        assert ent is scene
        assert isinstance(q, asyncio.Queue)


# ---------------------------------------------------------------------------
# _sse_event_stream helper — wire serialization for EntityChanged
# ---------------------------------------------------------------------------


class TestSseEventStream:
    async def test_sse_event_stream_yields_entity_changed(self) -> None:
        # events-subscription: helper emits a
        # `event: entity_changed\ndata: {"entity_id": "...", "attributes": [...]}\n\n`
        # block per dequeued EntityChanged. EntityChanged is a @dataclass —
        # the SSE boundary builds the wire payload.
        from sidestage.server import _sse_event_stream

        # Minimal entity stand-in: only `id` is read at the wire boundary.
        ent = MagicMock()
        ent.id = "s1"

        queue: asyncio.Queue = asyncio.Queue()
        await queue.put(EntityChanged(entity=ent, attributes=["messages"]))

        gen = _sse_event_stream(queue=queue, request=None, keepalive_interval_s=5.0)
        chunk = await gen.__anext__()
        await gen.aclose()

        text = chunk.decode("utf-8")
        assert "event: entity_changed" in text
        assert "\n\n" in text
        data_line = [line for line in text.splitlines() if line.startswith("data: ")][
            0
        ][len("data: ") :]
        payload = json.loads(data_line)
        assert payload == {"entity_id": "s1", "attributes": ["messages"]}

    async def test_sse_event_stream_keepalive_on_idle(self) -> None:
        # rest-api-events-keepalive: ": keepalive" comment when queue is idle.
        from sidestage.server import _sse_event_stream

        queue: asyncio.Queue = asyncio.Queue()
        gen = _sse_event_stream(queue=queue, request=None, keepalive_interval_s=0.05)
        chunk = await gen.__anext__()
        await gen.aclose()
        assert chunk == b": keepalive\n\n"

    async def test_sse_event_stream_invokes_on_close(self) -> None:
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
    def _make_sidestage_tree(self, tmp_path, campaign_names: list[str]) -> str:
        """Build a `<sidestage>/campaigns/` tree with one subdir per
        campaign name, each carrying an empty `config.yaml` so the walk
        picks it up."""
        root = tmp_path / "sidestage"
        campaigns = root / "campaigns"
        campaigns.mkdir(parents=True)
        for n in campaign_names:
            sub = campaigns / n
            sub.mkdir()
            (sub / "config.yaml").write_text("name: " + n + "\n")
        return str(root) + "/"

    def test_run_loads_first_subdir_with_config_yaml(self, tmp_path) -> None:
        # server-run-load: first subdir (sorted) with config.yaml is loaded.
        sidestage_dir = self._make_sidestage_tree(tmp_path, ["b_camp", "a_camp"])
        loaded_paths: list = []

        def fake_load(path) -> MagicMock:
            loaded_paths.append(path)
            c = MagicMock()
            c.name = path.name
            return c

        with (
            patch("sidestage.server.uvicorn.run") as run_mock,
            patch("sidestage.server.Campaign.load", side_effect=fake_load),
            patch("sidestage.server.DictEntityFactory") as factory_mock,
        ):
            factory_mock.return_value = MagicMock()
            App.run(sidestage_dir=sidestage_dir)

        # Sorted order: a_camp comes first.
        assert len(loaded_paths) == 1
        assert loaded_paths[0].name == "a_camp"
        run_mock.assert_called_once()

    def test_run_skips_subdirs_without_config_yaml(self, tmp_path) -> None:
        # server-run-load: subdirs without config.yaml are skipped.
        root = tmp_path / "sidestage" / "campaigns"
        root.mkdir(parents=True)
        (root / "no_cfg").mkdir()  # no config.yaml — must be skipped
        good = root / "good"
        good.mkdir()
        (good / "config.yaml").write_text("name: good\n")

        loaded_paths: list = []

        def fake_load(path) -> MagicMock:
            loaded_paths.append(path)
            c = MagicMock()
            c.name = path.name
            return c

        with (
            patch("sidestage.server.uvicorn.run"),
            patch("sidestage.server.Campaign.load", side_effect=fake_load),
            patch("sidestage.server.DictEntityFactory") as factory_mock,
        ):
            factory_mock.return_value = MagicMock()
            App.run(sidestage_dir=str(root.parent) + "/")

        assert len(loaded_paths) == 1
        assert loaded_paths[0].name == "good"

    def test_run_raises_when_no_campaign_subdir(self, tmp_path) -> None:
        # server-run-load: empty campaigns/ -> RuntimeError on startup.
        root = tmp_path / "sidestage"
        (root / "campaigns").mkdir(parents=True)

        with (
            patch("sidestage.server.uvicorn.run"),
            patch("sidestage.server.Campaign.load") as load_mock,
            patch("sidestage.server.DictEntityFactory") as factory_mock,
        ):
            factory_mock.return_value = MagicMock()
            with pytest.raises(RuntimeError):
                App.run(sidestage_dir=str(root) + "/")
        load_mock.assert_not_called()

    def test_run_raises_when_campaigns_dir_missing(self, tmp_path) -> None:
        # server-run-load: missing campaigns/ entirely -> RuntimeError.
        root = tmp_path / "sidestage"
        root.mkdir()  # no campaigns/ subdir at all

        with (
            patch("sidestage.server.uvicorn.run"),
            patch("sidestage.server.Campaign.load") as load_mock,
            patch("sidestage.server.DictEntityFactory") as factory_mock,
        ):
            factory_mock.return_value = MagicMock()
            with pytest.raises(RuntimeError):
                App.run(sidestage_dir=str(root) + "/")
        load_mock.assert_not_called()

    def test_run_registers_campaign_by_name(self, tmp_path) -> None:
        # server-app-campaigns: loaded Campaign is keyed by campaign.name.
        sidestage_dir = self._make_sidestage_tree(tmp_path, ["only_camp"])
        captured: dict = {}

        fake_campaign = MagicMock()
        fake_campaign.name = "Only Campaign"

        def fake_uvicorn_run(app_obj, **kwargs) -> None:
            # The FastAPI app is `instance._fastapi`; reach back via the
            # captured `instance` we stash from the constructor.
            captured["called"] = True

        original_init = App.__init__
        instances: list[App] = []

        def capturing_init(self, *args, **kwargs) -> None:
            original_init(self, *args, **kwargs)
            instances.append(self)

        with (
            patch("sidestage.server.uvicorn.run", side_effect=fake_uvicorn_run),
            patch("sidestage.server.Campaign.load", return_value=fake_campaign),
            patch("sidestage.server.DictEntityFactory") as factory_mock,
            patch.object(App, "__init__", capturing_init),
        ):
            factory_mock.return_value = MagicMock()
            App.run(sidestage_dir=sidestage_dir)

        assert captured.get("called") is True
        assert len(instances) == 1
        assert instances[0].campaigns == {"Only Campaign": fake_campaign}

    def test_run_sets_factory_before_load(self, tmp_path) -> None:
        # App.factory is set BEFORE Campaign.load so deserialize-time code
        # can reach the factory via App.factory.
        sidestage_dir = self._make_sidestage_tree(tmp_path, ["a_camp"])
        observed = {}

        def fake_load(path) -> MagicMock:
            # When Campaign.load is invoked, App.factory must already be set.
            observed["factory_set"] = (
                hasattr(App, "factory") and App.factory is not None
            )
            c = MagicMock()
            c.name = "a"
            return c

        with (
            patch("sidestage.server.uvicorn.run"),
            patch("sidestage.server.Campaign.load", side_effect=fake_load),
            patch("sidestage.server.DictEntityFactory") as factory_mock,
        ):
            factory_mock.return_value = MagicMock()
            App.run(sidestage_dir=sidestage_dir)

        assert observed.get("factory_set") is True

    def test_run_state_serving_after_load(self, tmp_path) -> None:
        # server-run-state-serving: state flips to SERVING after Campaign.load.
        sidestage_dir = self._make_sidestage_tree(tmp_path, ["a_camp"])

        observed: dict = {}
        instances: list[App] = []
        original_init = App.__init__

        def capturing_init(self, *args, **kwargs) -> None:
            original_init(self, *args, **kwargs)
            instances.append(self)

        fake_campaign = MagicMock()
        fake_campaign.name = "a"

        def fake_uvicorn_run(*args, **kwargs) -> None:
            observed["state_at_serve"] = instances[-1].state

        with (
            patch("sidestage.server.uvicorn.run", side_effect=fake_uvicorn_run),
            patch("sidestage.server.Campaign.load", return_value=fake_campaign),
            patch("sidestage.server.DictEntityFactory") as factory_mock,
            patch.object(App, "__init__", capturing_init),
        ):
            factory_mock.return_value = MagicMock()
            App.run(sidestage_dir=sidestage_dir)

        assert observed.get("state_at_serve") == ServerState.SERVING

    def test_server_run_port_default(self, tmp_path) -> None:
        # server-run-port: default port is 8000; reaches uvicorn.run.
        sidestage_dir = self._make_sidestage_tree(tmp_path, ["a"])
        observed: dict = {}

        def fake_uvicorn_run(*_args, **kwargs) -> None:
            observed["port"] = kwargs.get("port")

        fake_campaign = MagicMock()
        fake_campaign.name = "a"
        with (
            patch("sidestage.server.uvicorn.run", side_effect=fake_uvicorn_run),
            patch("sidestage.server.Campaign.load", return_value=fake_campaign),
            patch("sidestage.server.DictEntityFactory") as factory_mock,
        ):
            factory_mock.return_value = MagicMock()
            App.run(sidestage_dir=sidestage_dir)

        assert observed.get("port") == 8000, (
            "server-run-port: default port MUST be 8000; "
            f"got port={observed.get('port')!r}"
        )

    def test_server_run_port_custom(self, tmp_path) -> None:
        # server-run-port: explicit override flows through to uvicorn.
        sidestage_dir = self._make_sidestage_tree(tmp_path, ["a"])
        observed: dict = {}

        def fake_uvicorn_run(*_args, **kwargs) -> None:
            observed["port"] = kwargs.get("port")

        fake_campaign = MagicMock()
        fake_campaign.name = "a"
        with (
            patch("sidestage.server.uvicorn.run", side_effect=fake_uvicorn_run),
            patch("sidestage.server.Campaign.load", return_value=fake_campaign),
            patch("sidestage.server.DictEntityFactory") as factory_mock,
        ):
            factory_mock.return_value = MagicMock()
            App.run(sidestage_dir=sidestage_dir, port=54321)

        assert observed.get("port") == 54321, (
            "server-run-port: explicit port reaches uvicorn.run; "
            f"got port={observed.get('port')!r}"
        )


# ---------------------------------------------------------------------------
# create_app: reload-mode ASGI factory
# ---------------------------------------------------------------------------


class TestCreateApp:
    def test_create_app_reads_env_and_builds(self, tmp_path, monkeypatch) -> None:
        # server-create-app: factory reads SIDESTAGE_INSTANCE_CONFIG, builds
        # the App, returns the FastAPI instance with state=SERVING.
        from sidestage.instance_config import InstanceConfig
        from sidestage.server import create_app

        # Build a minimal sidestage tree.
        sd = tmp_path / "sidestage"
        (sd / "campaigns" / "c").mkdir(parents=True)
        (sd / "campaigns" / "c" / "config.yaml").write_text("name: c\n")
        config = InstanceConfig(sidestage_dir=str(sd) + "/", port=8000)
        # Use monkeypatch so the env mutation is undone on teardown — no leak.
        monkeypatch.setenv("SIDESTAGE_INSTANCE_CONFIG", config.model_dump_json())

        fake_campaign = MagicMock()
        fake_campaign.name = "c"
        with (
            patch("sidestage.server.Campaign.load", return_value=fake_campaign),
            patch("sidestage.server.DictEntityFactory") as factory_mock,
        ):
            factory_mock.return_value = MagicMock()
            asgi = create_app()
        assert isinstance(asgi, FastAPI), (
            f"server-create-app: factory MUST return a FastAPI app; got {type(asgi)!r}"
        )

    def test_create_app_missing_env_is_fatal(self, monkeypatch) -> None:
        # server-create-app: factory invoked without SIDESTAGE_INSTANCE_CONFIG
        # is a setup error, not a fallback case.
        monkeypatch.delenv("SIDESTAGE_INSTANCE_CONFIG", raising=False)
        from sidestage.server import create_app

        with pytest.raises(RuntimeError, match="SIDESTAGE_INSTANCE_CONFIG"):
            create_app()


# ---------------------------------------------------------------------------
# api-dataflow / sse-dataflow integration sanity
# ---------------------------------------------------------------------------


class TestEndpointDataflowIntegration:
    def test_subscribe_then_fetch_pattern(self) -> None:
        # api-dataflow-list-campaigns + api-dataflow-campaign + api-dataflow-scene
        # + api-dataflow-history.
        app, scene, human, npc = make_loaded_app()
        scene.messages.append(Message(sender=human, body="hi"))

        with TestClient(app._fastapi) as client:
            r0 = client.get("/api/campaigns")
            r1 = client.get(f"/api/campaigns/{CAMPAIGN_ID}")
            r2 = client.get(f"/api/campaigns/{CAMPAIGN_ID}/scenes/s1")
            r3 = client.get(f"/api/campaigns/{CAMPAIGN_ID}/scenes/s1/messages")
        assert r0.status_code == 200
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 200
        assert r0.json()[0]["name"] == "Test Campaign"
        assert r1.json()["default_scene_id"] == "s1"
        assert r2.json()["id"] == "s1"
        assert len(r3.json()) == 1
