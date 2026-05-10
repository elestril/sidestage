from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sidestage.server import (
    App,
    InitEvent,
    MessageEvent,
    ServerState,
    UserActor,
)
from sidestage.actor import Actor, StubActor
from sidestage.character import Character
from sidestage.entity import EntityId, EntityType
from sidestage.message import Message
from sidestage.scene import SimpleScene


def make_character(id: str, actor_type: str = "npc") -> Character:
    model = Character.Model(
        id=EntityId(id),
        name=id.capitalize(),
        type=EntityType.CHARACTER,
        body="body",
        actor_type=actor_type,
    )
    return Character.deserialize(model)


def make_scene(characters: list[Character]) -> SimpleScene:
    model = SimpleScene.Model(
        id=EntityId("s1"),
        name="Test Scene",
        type=EntityType.SCENE,
        body="scene body",
        active_character_ids=[c.id for c in characters],
    )
    scene = SimpleScene.deserialize(model)
    object.__setattr__(scene, "characters", characters)
    return scene


class TestServerState:
    def test_loading_state(self):
        assert ServerState.LOADING is not None

    def test_serving_state(self):
        assert ServerState.SERVING is not None

    def test_states_are_distinct(self):
        assert ServerState.LOADING != ServerState.SERVING


class TestInitEvent:
    def test_init_event_has_scene_id(self):
        event = InitEvent(scene_id=EntityId("s1"), characters=[], player_character_ids=[])
        assert event.scene_id == "s1"

    def test_init_event_has_characters(self):
        char = make_character("c1")
        model = char.serialize()
        event = InitEvent(scene_id=EntityId("s1"), characters=[model], player_character_ids=[])
        assert len(event.characters) == 1
        assert event.characters[0] is model

    def test_init_event_model_dump(self):
        event = InitEvent(scene_id=EntityId("s1"), characters=[], player_character_ids=[])
        data = event.model_dump()
        assert data["scene_id"] == "s1"
        assert data["type"] == "init"
        assert data["characters"] == []


class TestMessageEvent:
    def test_message_event_has_sender_id_and_body(self):
        event = MessageEvent(sender_id=EntityId("c1"), body="Hello")
        assert event.sender_id == "c1"
        assert event.body == "Hello"

    def test_message_event_model_dump(self):
        event = MessageEvent(sender_id=EntityId("c1"), body="Hello")
        data = event.model_dump()
        assert data["sender_id"] == "c1"
        assert data["body"] == "Hello"
        assert data["type"] == "message"

    def test_message_event_model_validate(self):
        data = {"sender_id": "c1", "body": "Hello"}
        event = MessageEvent.model_validate(data)
        assert event.sender_id == "c1"
        assert event.body == "Hello"


class TestUserActor:
    def test_user_actor_is_human(self):
        ws = MagicMock()
        scene = MagicMock()
        char = make_character("c1")
        actor = UserActor(websocket=ws, scene=scene, character=char)
        assert actor.is_human() is True

    def test_user_actor_implements_actor(self):
        ws = MagicMock()
        scene = MagicMock()
        char = make_character("c1")
        actor = UserActor(websocket=ws, scene=scene, character=char)
        assert isinstance(actor, Actor)

    def test_user_actor_respond_returns_none(self):
        ws = MagicMock()
        ws.send_json = AsyncMock()
        scene = MagicMock()
        char = make_character("c1")
        actor = UserActor(websocket=ws, scene=scene, character=char)
        sender = make_character("s1")
        msg = Message(sender=sender, body="Hello")
        result = actor.respond(msg, char)
        assert result is None

    async def test_user_actor_run_dispatches(self):
        ws = MagicMock()
        ws.iter_json.return_value = aiter([{"sender_id": "c1", "body": "Hello"}])
        scene = MagicMock()
        char = make_character("c1")
        actor = UserActor(websocket=ws, scene=scene, character=char)
        await actor.run()
        scene.dispatch.assert_called_once()
        call_args = scene.dispatch.call_args[0][0]
        assert isinstance(call_args, Message)
        assert call_args.sender is char
        assert call_args.body == "Hello"

    async def test_user_actor_run_sets_sender_to_own_character(self):
        messages = [{"sender_id": "c1", "body": "test body"}]
        ws = MagicMock()
        ws.iter_json.return_value = aiter(messages)
        scene = MagicMock()
        char = make_character("c1")
        actor = UserActor(websocket=ws, scene=scene, character=char)
        await actor.run()
        dispatched = scene.dispatch.call_args[0][0]
        assert dispatched.sender is char


async def aiter(items):
    for item in items:
        yield item


class TestAppState:
    def test_app_initial_state_loading(self):
        app = App()
        assert app.state == ServerState.LOADING

    def test_app_has_fastapi(self):
        from fastapi import FastAPI
        app = App()
        assert isinstance(app._fastapi, FastAPI)

    def test_app_default_config_dir(self):
        app = App()
        assert app.config_dir == "config/"

    def test_app_custom_config_dir(self):
        app = App(config_dir="my/config/")
        assert app.config_dir == "my/config/"


class TestAppRoutes:
    def test_root_returns_html(self):
        from starlette.testclient import TestClient
        app = App()
        with TestClient(app._fastapi) as client:
            response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_ws_rejects_when_loading(self):
        from starlette.testclient import TestClient
        app = App()
        app.state = ServerState.LOADING
        with TestClient(app._fastapi) as client:
            with pytest.raises(Exception):
                with client.websocket_connect("/ws") as ws:
                    pass

    def test_ws_accepts_when_serving(self):
        from starlette.testclient import TestClient
        human = make_character("bob", actor_type="user")
        npc = make_character("elara", actor_type="npc")
        scene = make_scene([human, npc])

        mock_campaign = MagicMock()
        mock_campaign.scene = scene

        app = App()
        app.state = ServerState.SERVING
        app.campaign = mock_campaign

        with TestClient(app._fastapi) as client:
            with client.websocket_connect("/ws") as ws:
                data = ws.receive_json()
                assert data["type"] == "init"


class TestWsDataflow:
    def test_ws_sends_init_event_on_connect(self):
        from starlette.testclient import TestClient
        human = make_character("bob", actor_type="user")
        npc = make_character("elara", actor_type="npc")
        scene = make_scene([human, npc])

        mock_campaign = MagicMock()
        mock_campaign.scene = scene

        app = App()
        app.state = ServerState.SERVING
        app.campaign = mock_campaign

        with TestClient(app._fastapi) as client:
            with client.websocket_connect("/ws") as ws:
                data = ws.receive_json()

        assert data["type"] == "init"
        assert data["scene_id"] == "s1"
        assert len(data["characters"]) == 2

    def test_ws_init_event_has_character_models(self):
        from starlette.testclient import TestClient
        human = make_character("bob", actor_type="user")
        npc = make_character("elara", actor_type="npc")
        scene = make_scene([human, npc])

        mock_campaign = MagicMock()
        mock_campaign.scene = scene

        app = App()
        app.state = ServerState.SERVING
        app.campaign = mock_campaign

        with TestClient(app._fastapi) as client:
            with client.websocket_connect("/ws") as ws:
                data = ws.receive_json()

        char_ids = {c["id"] for c in data["characters"]}
        assert "bob" in char_ids
        assert "elara" in char_ids
