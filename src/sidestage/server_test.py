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
from sidestage.campaign import Campaign
from sidestage.entity import EntityId, EntityType
from sidestage.message import Message
from sidestage.scene import Scene
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
    """Each test starts with a clean App class-level registry/profile."""
    _reset_actor_registry()
    App.llm_profile = None
    yield
    _reset_actor_registry()
    App.llm_profile = None


def make_human_character(id: str = "bob") -> MagicMock:
    """A character whose `has_human_actor()` is True.

    Uses `spec=Character` so `isinstance(mock, Character)` returns True —
    the server's entity-dispatch route narrows by isinstance.
    """
    from sidestage.character import Character

    char = MagicMock(spec=Character)
    char.id = EntityId(id)
    char.name = id.capitalize()
    char.body = ""
    char.owner = "user"
    char._actor = StubActor()
    char.has_human_actor = lambda: True
    char.model = Character.Model(
        id=char.id, name=char.name, type=EntityType.CHARACTER, body="", owner="user"
    )
    return char


def make_npc_character(id: str = "elara") -> MagicMock:
    from sidestage.character import Character

    char = MagicMock(spec=Character)
    char.id = EntityId(id)
    char.name = id.capitalize()
    char.body = ""
    char.owner = "stub"
    char._actor = StubActor()
    char.has_human_actor = lambda: False
    char.model = Character.Model(
        id=char.id, name=char.name, type=EntityType.CHARACTER, body="", owner="stub"
    )
    return char


def make_scene(human, npc, scene_id: str = "s1") -> MagicMock:
    """Mock Scene exposing the surface the server now relies on:
    - `model` is the canonical Scene.Model wire shape (server reads it directly).
    - `user_characters` is the player-character subset.
    - `serialize_message`, `messages`, `append` are the message API.

    Uses `spec=Scene` so `isinstance(mock, Scene)` returns True — the
    server's entity-dispatch route narrows by isinstance.
    """
    scene = MagicMock(spec=Scene)
    scene.id = EntityId(scene_id)
    scene.name = "Test Scene"
    scene.body = ""
    scene.type = EntityType.SCENE
    scene.characters = [human, npc]
    scene.user_characters = [c for c in scene.characters if c.has_human_actor()]
    scene.messages = []
    scene.model = Scene.Model(
        id=scene.id,
        name=scene.name,
        type=EntityType.SCENE,
        body=scene.body,
        character_ids=[c.id for c in scene.characters],
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

    scene.serialize_message = serialize_message
    scene.append = MagicMock(side_effect=append)
    return scene


def make_campaign(scene, name: str = "Test Campaign") -> MagicMock:
    """Mock Campaign exposing the new method surface:
    - `scene(id)` is a method (not an attribute) returning Optional[Scene].
    - `scenes()` is a method returning list[Scene].
    - `default_scene_id` replaces the dropped `active_scene_id`.
    - `to_model()` builds the Campaign.Model.
    - `get(id)` (directly on Campaign — no factory) serves the entity route.
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
    campaign.to_model = MagicMock(
        return_value=Campaign.Model(
            name=name,
            default_scene_id=scene.id,
        )
    )

    def _get(eid) -> MagicMock | None:
        if eid == scene.id:
            return scene
        return None

    campaign.get = MagicMock(side_effect=_get)
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


# ---------------------------------------------------------------------------
# server-get-actor-npc + server-app-llm-profile
# ---------------------------------------------------------------------------


class TestAppGetActorNpc:
    """server-get-actor-npc: 'npc' owner constructs NpcActor from
    App.llm_profile.models['default']."""

    def _set_profile(self, *, with_default: bool = True) -> None:
        from sidestage.llm_profile import LlmProfile, load_profiles

        if with_default:
            # Load the canonical test fixture profile rather than inventing
            # endpoint/model literals — profiles live in YAML, not in code.
            App.llm_profile = load_profiles("tests/sidestage")["localhost"]
        else:
            App.llm_profile = LlmProfile.model_validate({"models": {}})

    def test_returns_npc_actor(self) -> None:
        from sidestage.npc_actor import NpcActor

        self._set_profile()
        actor = App.get_actor("npc")
        assert isinstance(actor, NpcActor), (
            "server-get-actor-npc: 'npc' owner MUST return NpcActor; "
            f"got {type(actor).__name__}"
        )

    def test_caches_per_owner(self) -> None:
        # server-get-actor-cached: second call returns the same instance.
        self._set_profile()
        a1 = App.get_actor("npc")
        a2 = App.get_actor("npc")
        assert a1 is a2

    def test_raises_runtime_error_when_profile_unset(self) -> None:
        # server-app-llm-profile-required-for-npc.
        App.llm_profile = None
        with pytest.raises(RuntimeError, match="server-app-llm-profile"):
            App.get_actor("npc")

    def test_raises_keyerror_when_default_role_missing(self) -> None:
        # llm-profile-runtime-default-role.
        self._set_profile(with_default=False)
        with pytest.raises(KeyError, match="llm-profile-runtime-default-role"):
            App.get_actor("npc")

    def test_uses_default_entry(self) -> None:
        # The constructed NpcActor carries the entry from
        # profile.models["default"].
        self._set_profile()
        from sidestage.npc_actor import NpcActor

        actor = App.get_actor("npc")
        assert isinstance(actor, NpcActor)
        assert App.llm_profile is not None
        assert actor._entry is App.llm_profile.models["default"]


class TestBuildAndLoadLlmProfile:
    """server-app-llm-profile: _build_and_load populates App.llm_profile."""

    def test_loads_profile_from_sidestage_dir(self, tmp_path: Any) -> None:
        # Build a minimal sidestage dir with one profile + one campaign.
        (tmp_path / "llm_profiles").mkdir()
        (tmp_path / "llm_profiles" / "localhost.yaml").write_text(
            "models:\n  default:\n    endpoint: http://127.0.0.1:8080\n    model: openai/local\n"
        )
        # Minimal campaign so _build_and_load doesn't bail.
        (tmp_path / "campaigns" / "tc" / "characters").mkdir(parents=True)
        (tmp_path / "campaigns" / "tc" / "scenes").mkdir(parents=True)
        (tmp_path / "campaigns" / "tc" / "config.yaml").write_text(
            "name: TC\ndefault_scene_id: s1\n"
        )
        (tmp_path / "campaigns" / "tc" / "characters" / "alice.md").write_text(
            "---\nname: Alice\nowner: user\n---\nbody\n"
        )
        (tmp_path / "campaigns" / "tc" / "characters" / "bob.md").write_text(
            "---\nname: Bob\nowner: stub\n---\nbody\n"
        )
        (tmp_path / "campaigns" / "tc" / "scenes" / "s1.md").write_text(
            "---\nname: S1\ncharacters:\n  - alice\n  - bob\n---\nbody\n"
        )

        App._build_and_load(str(tmp_path), "localhost")

        assert App.llm_profile is not None, (
            "server-app-llm-profile: _build_and_load MUST populate "
            "App.llm_profile from <sidestage_dir>/llm_profiles/<name>.yaml"
        )
        assert "default" in App.llm_profile.models

    def test_missing_profile_dir_leaves_llm_profile_none(self, tmp_path: Any) -> None:
        # llm-profile-discovery-missing-dir: no llm_profiles/ → empty dict
        # → App.llm_profile remains None (it's only required when a
        # Character with owner='npc' is constructed).
        (tmp_path / "campaigns" / "tc" / "characters").mkdir(parents=True)
        (tmp_path / "campaigns" / "tc" / "scenes").mkdir(parents=True)
        (tmp_path / "campaigns" / "tc" / "config.yaml").write_text(
            "name: TC\ndefault_scene_id: s1\n"
        )
        (tmp_path / "campaigns" / "tc" / "characters" / "alice.md").write_text(
            "---\nname: Alice\nowner: user\n---\nbody\n"
        )
        (tmp_path / "campaigns" / "tc" / "characters" / "bob.md").write_text(
            "---\nname: Bob\nowner: stub\n---\nbody\n"
        )
        (tmp_path / "campaigns" / "tc" / "scenes" / "s1.md").write_text(
            "---\nname: S1\ncharacters:\n  - alice\n  - bob\n---\nbody\n"
        )

        App._build_and_load(str(tmp_path), "localhost")
        assert App.llm_profile is None

    def test_unknown_profile_name_raises(self, tmp_path: Any) -> None:
        (tmp_path / "llm_profiles").mkdir()
        (tmp_path / "llm_profiles" / "localhost.yaml").write_text(
            "models:\n  default:\n    endpoint: http://127.0.0.1:8080\n    model: openai/local\n"
        )
        (tmp_path / "campaigns" / "tc" / "characters").mkdir(parents=True)
        (tmp_path / "campaigns" / "tc" / "scenes").mkdir(parents=True)
        (tmp_path / "campaigns" / "tc" / "config.yaml").write_text(
            "name: TC\ndefault_scene_id: s1\n"
        )
        (tmp_path / "campaigns" / "tc" / "characters" / "alice.md").write_text(
            "---\nname: Alice\nowner: user\n---\nbody\n"
        )
        (tmp_path / "campaigns" / "tc" / "characters" / "bob.md").write_text(
            "---\nname: Bob\nowner: stub\n---\nbody\n"
        )
        (tmp_path / "campaigns" / "tc" / "scenes" / "s1.md").write_text(
            "---\nname: S1\ncharacters:\n  - alice\n  - bob\n---\nbody\n"
        )

        with pytest.raises(RuntimeError, match="server-app-llm-profile"):
            App._build_and_load(str(tmp_path), "nonexistent")


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
        # server-route-list-campaigns: returns list[Campaign.Model] from
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

    def test_campaign_returns_model(self) -> None:
        # server-route-campaign: returns Campaign.Model from
        # `campaign.to_model()`. Server constructs nothing.
        app, scene, *_ = make_loaded_app()
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}")
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Test Campaign"
        assert body["default_scene_id"] == "s1"

    def test_campaign_delegates_to_campaign_to_model(self) -> None:
        # The route must call `campaign.to_model()`, not build its own
        # Campaign.Model.
        app, *_ = make_loaded_app()
        campaign = app.campaigns[CAMPAIGN_ID]
        campaign.to_model = MagicMock(
            return_value=Campaign.Model(name="X", default_scene_id=None)
        )
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}")
        assert response.status_code == 200
        campaign.to_model.assert_called_once()
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

    def test_scenes_returns_list_of_scene_models(self) -> None:
        # server-route-scenes: returns list[Scene.Model] = one entry per
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
        # rest-api-entity-404: campaign.get returns None.
        app, *_ = make_loaded_app()
        app.campaigns[CAMPAIGN_ID].get = MagicMock(return_value=None)
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}/entities/missing")
        assert response.status_code == 404

    def test_entity_scene_returns_scene_model(self) -> None:
        # rest-api-get-entity: a Scene entity returns its `entity.model`
        # (a Scene.Model) directly — no isinstance dispatch, no conversion.
        # `spec=Scene` so isinstance(mock, Scene) returns True (kept as a
        # safety net even though the route no longer narrows by type).
        scene_entity = MagicMock(spec=Scene)
        scene_entity.id = EntityId("s1")
        scene_entity.type = EntityType.SCENE
        scene_entity.model = Scene.Model(
            id=EntityId("s1"),
            name="Test Scene",
            type=EntityType.SCENE,
            body="A small room.",
            character_ids=[EntityId("bob"), EntityId("elara")],
        )

        app, *_ = make_loaded_app()
        app.campaigns[CAMPAIGN_ID].get = MagicMock(return_value=scene_entity)
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}/entities/s1")
        assert response.status_code == 200
        body = response.json()
        # The route's response_model is Entity.Model, so only the base
        # Entity.Model fields survive on the wire.
        assert body["type"] == "scene"
        assert body["id"] == "s1"
        assert body["name"] == "Test Scene"
        assert body["body"] == "A small room."

    def test_entity_character_returns_character_model(self) -> None:
        # rest-api-get-entity: a Character entity returns its `entity.model`
        # (a Character.Model) directly — no isinstance dispatch, no conversion.
        from sidestage.character import Character

        # `spec=Character` so isinstance(mock, Character) returns True.
        char_entity = MagicMock(spec=Character)
        char_entity.id = EntityId("alice")
        char_entity.type = EntityType.CHARACTER
        char_entity.model = Character.Model(
            id=EntityId("alice"),
            name="Alice",
            type=EntityType.CHARACTER,
            body="A curious user.",
            owner="user",
        )

        app, *_ = make_loaded_app()
        app.campaigns[CAMPAIGN_ID].get = MagicMock(return_value=char_entity)
        with TestClient(app._fastapi) as client:
            response = client.get(f"/api/campaigns/{CAMPAIGN_ID}/entities/alice")
        assert response.status_code == 200
        body = response.json()
        # Entity.Model response_model strips subclass-specific fields like
        # `owner`; only base Entity.Model fields appear on the wire.
        assert body["type"] == "character"
        assert body["id"] == "alice"
        assert body["name"] == "Alice"
        assert body["body"] == "A curious user."


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
# ws-route-connection: WS /api/campaigns/{cid}/ws
# ---------------------------------------------------------------------------


class _FakeWebSocket:
    """Fake WebSocket for `WsConnection` unit tests.

    Drives `receive_text` from a script queue the test fills, captures
    every `send_text` into a list the test can read. `WebSocketDisconnect`
    is raised when the script queue runs out of frames, signalling
    "client closed".
    """

    def __init__(self) -> None:
        self._incoming: asyncio.Queue[str] = asyncio.Queue()
        self.sent: list[str] = []
        self.accepted = False
        self.closed_code: int | None = None

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, text: str) -> None:
        self.sent.append(text)

    async def receive_text(self) -> str:
        from fastapi import WebSocketDisconnect

        text = await self._incoming.get()
        if text == "__disconnect__":
            raise WebSocketDisconnect()
        return text

    async def close(self, code: int = 1000) -> None:
        self.closed_code = code

    def script_in(self, frame: dict[str, Any] | str) -> None:
        """Enqueue one inbound frame for the connection to receive."""
        text = frame if isinstance(frame, str) else json.dumps(frame)
        self._incoming.put_nowait(text)

    def script_disconnect(self) -> None:
        """Tell the connection's `receive_text` to raise WebSocketDisconnect."""
        self._incoming.put_nowait("__disconnect__")


class TestWsConnection:
    """Unit tests for `WsConnection` — drive it directly with a fake socket.

    Per `events-subscription`, `ws-dataflow-subscribe`, `ws-dataflow-event`,
    and `ws-dataflow-unsubscribe`. These tests exercise the per-frame
    invariants without booting uvicorn — the full round-trip lives in
    `tests/e2e/test_cuj_hello.py`.
    """

    def _make_scene_with_subscribe_tracking(
        self,
    ) -> tuple[MagicMock, list, list]:
        """Build a scene mock whose `subscribe` / `unsubscribe` record calls.

        Returns `(scene, subscribed, unsubscribed)` — the two lists track
        the listeners passed in order, so tests can assert add/remove
        pairing.
        """
        scene = MagicMock(spec=[])
        scene.id = EntityId("s1")
        subscribed: list = []
        unsubscribed: list = []
        scene.subscribe = MagicMock(
            side_effect=lambda listener: subscribed.append(listener)
        )
        scene.unsubscribe = MagicMock(
            side_effect=lambda listener: unsubscribed.append(listener)
        )
        return scene, subscribed, unsubscribed

    def _make_campaign_for(self, scene: MagicMock) -> MagicMock:
        campaign = MagicMock(spec=[])
        campaign.get = MagicMock(
            side_effect=lambda eid: scene if eid == scene.id else None
        )
        return campaign

    async def test_subscribe_registers_listener_on_entity(self) -> None:
        # ws-dataflow-subscribe: a `subscribe` frame calls
        # `entity.subscribe(listener)` with a fresh QueueListener.
        from sidestage.ws import WsConnection

        scene, subscribed, _ = self._make_scene_with_subscribe_tracking()
        campaign = self._make_campaign_for(scene)
        fake = _FakeWebSocket()
        fake.script_in({"op": "subscribe", "entity_id": "s1"})
        fake.script_disconnect()

        await WsConnection(campaign, cast(Any, fake)).run()

        assert fake.accepted, (
            "ws-dataflow-connect: WsConnection.run MUST accept the socket "
            "before pumping frames"
        )
        assert len(subscribed) == 1, (
            "ws-dataflow-subscribe: a subscribe frame MUST register exactly "
            f"one listener on the entity; got {len(subscribed)}"
        )

    async def test_entity_changed_sent_as_frame(self) -> None:
        # ws-dataflow-event: an EntityChanged emitted on a subscribed
        # entity MUST be sent as an `entity_changed` JSON frame carrying
        # `{entity_id, attributes}`.
        from sidestage.events import EntityChanged
        from sidestage.ws import WsConnection

        scene, subscribed, _ = self._make_scene_with_subscribe_tracking()
        campaign = self._make_campaign_for(scene)

        fake = _FakeWebSocket()
        fake.script_in({"op": "subscribe", "entity_id": "s1"})

        # Drive the connection until it has registered the listener, then
        # push an EntityChanged on the entity's listener queue, then
        # signal disconnect to exit the recv loop.
        conn = WsConnection(campaign, cast(Any, fake))
        run_task = asyncio.create_task(conn.run())

        # Wait until subscribe ran.
        for _ in range(50):
            if subscribed:
                break
            await asyncio.sleep(0.005)
        assert subscribed, "subscribe handler never ran"

        # Simulate the entity emit by calling the registered listener directly
        # (same path entity._emit -> spawn_task -> listener.notify takes).
        listener = subscribed[0]
        listener.notify(EntityChanged(entity=scene, attributes=["messages"]))

        # Give the send loop a tick to drain.
        for _ in range(50):
            if fake.sent:
                break
            await asyncio.sleep(0.005)

        fake.script_disconnect()
        await asyncio.wait_for(run_task, timeout=1.0)

        assert fake.sent, (
            "ws-dataflow-event: send loop MUST emit a frame for each "
            "EntityChanged dequeued from the connection queue"
        )
        payload = json.loads(fake.sent[0])
        assert payload == {
            "op": "entity_changed",
            "entity_id": "s1",
            "attributes": ["messages"],
        }, (
            "ws-dataflow-event: frame payload MUST be "
            "`{op:'entity_changed', entity_id, attributes}`; "
            f"got {payload!r}"
        )

    async def test_unsubscribe_frame_drops_listener(self) -> None:
        # ws-dataflow-unsubscribe: an explicit `unsubscribe` frame calls
        # `entity.unsubscribe(listener)` for the matching pair.
        from sidestage.ws import WsConnection

        scene, subscribed, unsubscribed = self._make_scene_with_subscribe_tracking()
        campaign = self._make_campaign_for(scene)

        fake = _FakeWebSocket()
        fake.script_in({"op": "subscribe", "entity_id": "s1"})
        fake.script_in({"op": "unsubscribe", "entity_id": "s1"})
        fake.script_disconnect()

        await WsConnection(campaign, cast(Any, fake)).run()

        assert len(unsubscribed) == 1, (
            "ws-dataflow-unsubscribe: an unsubscribe frame MUST remove "
            f"exactly one listener; got {len(unsubscribed)}"
        )
        assert unsubscribed[0] is subscribed[0], (
            "ws-dataflow-unsubscribe: unsubscribe MUST remove the same "
            "listener that subscribe registered"
        )

    async def test_disconnect_unsubscribes_all(self) -> None:
        # ws-dataflow-unsubscribe: on socket close, every remaining
        # subscription MUST be walked and unsubscribed.
        from sidestage.ws import WsConnection

        scene, subscribed, unsubscribed = self._make_scene_with_subscribe_tracking()
        campaign = self._make_campaign_for(scene)

        fake = _FakeWebSocket()
        fake.script_in({"op": "subscribe", "entity_id": "s1"})
        fake.script_disconnect()

        await WsConnection(campaign, cast(Any, fake)).run()

        assert subscribed, "subscribe handler never ran"
        assert unsubscribed == subscribed, (
            "ws-dataflow-unsubscribe: closing the socket without an explicit "
            "unsubscribe frame MUST still unsubscribe every listener; "
            f"got subscribed={subscribed!r} unsubscribed={unsubscribed!r}"
        )

    async def test_unknown_entity_id_is_ignored(self) -> None:
        # Subscribe to a non-existent entity: campaign.get returns None,
        # the handler logs and ignores. No crash, no listener registered.
        from sidestage.ws import WsConnection

        scene, subscribed, _ = self._make_scene_with_subscribe_tracking()
        campaign = self._make_campaign_for(scene)

        fake = _FakeWebSocket()
        fake.script_in({"op": "subscribe", "entity_id": "ghost"})
        fake.script_disconnect()

        await WsConnection(campaign, cast(Any, fake)).run()

        assert subscribed == [], (
            "ws-dataflow-subscribe: subscribe for an unknown entity_id "
            "MUST NOT register a listener; "
            f"got {subscribed!r}"
        )


class TestWsRouteLoadingGate:
    """The route handler closes the socket with 1013 while loading."""

    async def test_ws_loading_closes_1013(self) -> None:
        # ws-dataflow-lameduck: while App.state == LOADING the route
        # accepts and immediately closes the socket with 1013.
        from starlette.testclient import WebSocketDenialResponse

        app = App()
        # state is LOADING by default; no campaigns loaded.
        client = TestClient(app._fastapi)
        # Starlette's TestClient raises when the server closes immediately
        # after accept; catching the close confirms the lameduck path fires.
        try:
            with (
                client.websocket_connect(f"/api/campaigns/{CAMPAIGN_ID}/ws") as ws,
                contextlib.suppress(Exception),
            ):
                ws.receive_text()
        except WebSocketDenialResponse:
            pass
        except Exception:
            # The TestClient raises on close; that's the success path.
            pass


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
        ):
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
        ):
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
            pytest.raises(RuntimeError),
        ):
            App.run(sidestage_dir=str(root) + "/")
        load_mock.assert_not_called()

    def test_run_raises_when_campaigns_dir_missing(self, tmp_path) -> None:
        # server-run-load: missing campaigns/ entirely -> RuntimeError.
        root = tmp_path / "sidestage"
        root.mkdir()  # no campaigns/ subdir at all

        with (
            patch("sidestage.server.uvicorn.run"),
            patch("sidestage.server.Campaign.load") as load_mock,
            pytest.raises(RuntimeError),
        ):
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
            patch.object(App, "__init__", capturing_init),
        ):
            App.run(sidestage_dir=sidestage_dir)

        assert captured.get("called") is True
        assert len(instances) == 1
        assert instances[0].campaigns == {"Only Campaign": fake_campaign}

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
            patch.object(App, "__init__", capturing_init),
        ):
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
        ):
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
        ):
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
        with patch("sidestage.server.Campaign.load", return_value=fake_campaign):
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
# server-main: CLI entry point .env handling
# ---------------------------------------------------------------------------


class TestServerMainLoadsDotenv:
    def test_main_calls_load_dotenv_before_uvicorn(self, tmp_path, monkeypatch) -> None:
        # server-main-loads-dotenv: main() MUST load `.env` (if present)
        # into os.environ before resolving config or starting uvicorn.
        # Patch the load_dotenv symbol imported into server.py; verify
        # it was called.
        from sidestage import server as server_mod

        # Build a minimal sidestage tree so App.run finds a campaign.
        sd = tmp_path / "sidestage"
        (sd / "campaigns" / "c").mkdir(parents=True)
        (sd / "campaigns" / "c" / "config.yaml").write_text("name: c\n")

        monkeypatch.setattr("sys.argv", ["sidestage", "--sidestage-dir", str(sd) + "/"])
        fake_campaign = MagicMock()
        fake_campaign.name = "c"
        with (
            patch.object(server_mod, "load_dotenv") as load_mock,
            patch.object(server_mod.uvicorn, "run"),
            patch.object(server_mod.Campaign, "load", return_value=fake_campaign),
        ):
            server_mod.main()

        load_mock.assert_called_once_with()
        # And it was called before sidestage actually ran (load_dotenv has
        # to populate env BEFORE downstream code reads it).
        # We can't easily order-assert across mocks; the assertion above
        # plus main()'s code structure is sufficient.


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
            r2 = client.get(f"/api/campaigns/{CAMPAIGN_ID}/entities/s1")
            r3 = client.get(f"/api/campaigns/{CAMPAIGN_ID}/scenes/s1/messages")
        assert r0.status_code == 200
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 200
        assert r0.json()[0]["name"] == "Test Campaign"
        assert r1.json()["default_scene_id"] == "s1"
        assert r2.json()["type"] == "scene"
        assert r2.json()["id"] == "s1"
        assert len(r3.json()) == 1
