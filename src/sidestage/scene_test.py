from __future__ import annotations

from unittest.mock import MagicMock, call
from sidestage.scene import Scene, SimpleScene
from sidestage.character import Character
from sidestage.actor import StubActor
from sidestage.entity import EntityId, EntityType
from sidestage.message import Message


def make_character(id: str, is_human: bool) -> Character:
    model = Character.Model(
        id=EntityId(id),
        name=id.capitalize(),
        type=EntityType.CHARACTER,
        body="body",
        actor_type="user" if is_human else "npc",
    )
    char = Character.deserialize(model)
    if is_human:
        mock_actor = MagicMock()
        mock_actor.is_human.return_value = True
        char._actor = mock_actor
    else:
        char._actor = StubActor()
    return char


def make_simple_scene(characters: list[Character]) -> SimpleScene:
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


class TestSimpleScene:
    def test_dispatch_appends_to_history(self):
        human = make_character("human", is_human=True)
        npc = make_character("npc", is_human=False)
        scene = make_simple_scene([human, npc])
        msg = Message(sender=human, body="Hello")
        scene.dispatch(msg)
        assert msg in scene.messages

    def test_dispatch_calls_respond_on_non_sender(self):
        human = make_character("human", is_human=True)
        npc = make_character("npc", is_human=False)
        mock_npc_actor = MagicMock()
        mock_npc_actor.is_human.return_value = False
        mock_npc_actor.respond.return_value = None
        npc._actor = mock_npc_actor

        scene = make_simple_scene([human, npc])
        msg = Message(sender=human, body="Hello")
        scene.dispatch(msg)
        mock_npc_actor.respond.assert_called_once_with(msg, npc)

    def test_dispatch_does_not_call_respond_on_sender(self):
        human = make_character("human", is_human=True)
        mock_human_actor = MagicMock()
        mock_human_actor.is_human.return_value = True
        human._actor = mock_human_actor

        npc = make_character("npc", is_human=False)
        mock_npc_actor = MagicMock()
        mock_npc_actor.is_human.return_value = False
        mock_npc_actor.respond.return_value = None
        npc._actor = mock_npc_actor

        scene = make_simple_scene([human, npc])
        msg = Message(sender=human, body="Hello")
        scene.dispatch(msg)
        mock_human_actor.respond.assert_not_called()

    def test_dispatch_appends_response_to_history(self):
        human = make_character("human", is_human=True)
        npc = make_character("npc", is_human=False)
        response = Message(sender=npc, body="Hello User!")

        mock_npc_actor = MagicMock()
        mock_npc_actor.is_human.return_value = False
        mock_npc_actor.respond.return_value = response
        npc._actor = mock_npc_actor

        mock_human_actor = MagicMock()
        mock_human_actor.is_human.return_value = True
        mock_human_actor.respond.return_value = None
        human._actor = mock_human_actor

        scene = make_simple_scene([human, npc])
        msg = Message(sender=human, body="Hello")
        scene.dispatch(msg)

        assert response in scene.messages

    def test_dispatch_delivers_response_to_sender(self):
        human = make_character("human", is_human=True)
        npc = make_character("npc", is_human=False)
        response = Message(sender=npc, body="Hello User!")

        mock_npc_actor = MagicMock()
        mock_npc_actor.is_human.return_value = False
        mock_npc_actor.respond.return_value = response
        npc._actor = mock_npc_actor

        mock_human_actor = MagicMock()
        mock_human_actor.is_human.return_value = True
        mock_human_actor.respond.return_value = None
        human._actor = mock_human_actor

        scene = make_simple_scene([human, npc])
        msg = Message(sender=human, body="Hello")
        scene.dispatch(msg)

        mock_human_actor.respond.assert_called_once_with(response, human)

    def test_dispatch_returns_none(self):
        human = make_character("human", is_human=True)
        npc = make_character("npc", is_human=False)
        scene = make_simple_scene([human, npc])
        msg = Message(sender=human, body="Hello")
        result = scene.dispatch(msg)
        assert result is None

    def test_scene_is_entity(self):
        from sidestage.entity import Entity
        human = make_character("human", is_human=True)
        npc = make_character("npc", is_human=False)
        scene = make_simple_scene([human, npc])
        assert isinstance(scene, Entity)
