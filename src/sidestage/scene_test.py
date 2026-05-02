import pytest

from sidestage.ids import CampaignId, CharacterId, SceneId
from sidestage.message import Message
from sidestage.scene import Scene


def _make_scene(scene_id: str = "scene1") -> Scene:
    return Scene(
        id=SceneId(scene_id),
        campaign_id=CampaignId("camp1"),
        name="Tavern",
        description="A dim tavern.",
        active_character_ids=[],
        messages=[],
    )


def test_add_message_appends_when_scene_id_matches():
    scene = _make_scene("scene1")
    msg = Message.create(SceneId("scene1"), CharacterId("hero"), "hello")

    scene.add_message(msg)

    assert scene.messages == [msg], (
        "Scene.add_message(msg) must append msg to self.messages when "
        "msg.scene_id == self.id; expected scene.messages == [msg] after a "
        f"single add_message call, got {scene.messages!r}."
    )


def test_add_message_preserves_insertion_order_across_multiple_calls():
    scene = _make_scene("scene1")
    msg1 = Message.create(SceneId("scene1"), CharacterId("hero"), "first")
    msg2 = Message.create(SceneId("scene1"), CharacterId("hero"), "second")
    msg3 = Message.create(SceneId("scene1"), CharacterId("villain"), "third")

    scene.add_message(msg1)
    scene.add_message(msg2)
    scene.add_message(msg3)

    assert scene.messages == [msg1, msg2, msg3], (
        "Multiple Scene.add_message calls must preserve insertion order; "
        "after appending msg1, msg2, msg3 in that order, scene.messages must "
        f"equal [msg1, msg2, msg3]; got {scene.messages!r}."
    )


def test_add_message_raises_value_error_when_scene_id_mismatches():
    scene = _make_scene("scene1")
    foreign_msg = Message.create(
        SceneId("other_scene"), CharacterId("hero"), "hello"
    )

    with pytest.raises(ValueError):
        scene.add_message(foreign_msg)


def test_add_message_does_not_append_when_scene_id_mismatches():
    scene = _make_scene("scene1")
    foreign_msg = Message.create(
        SceneId("other_scene"), CharacterId("hero"), "hello"
    )

    with pytest.raises(ValueError):
        scene.add_message(foreign_msg)

    assert scene.messages == [], (
        "Scene.add_message must not append the message when msg.scene_id does "
        "not match self.id (it must raise ValueError instead); expected "
        f"scene.messages == [], got {scene.messages!r}."
    )


def test_scene_has_expected_fields():
    scene = Scene(
        id=SceneId("scene1"),
        campaign_id=CampaignId("camp1"),
        name="Tavern",
        description="A dim tavern.",
        active_character_ids=[CharacterId("hero"), CharacterId("villain")],
        messages=[],
    )

    assert scene.id == SceneId("scene1"), (
        "Scene.id must equal the SceneId argument passed to the constructor; "
        f"expected SceneId('scene1'), got {scene.id!r}."
    )
    assert scene.campaign_id == CampaignId("camp1"), (
        "Scene.campaign_id must equal the CampaignId argument passed to the "
        f"constructor; expected CampaignId('camp1'), got {scene.campaign_id!r}."
    )
    assert scene.name == "Tavern", (
        "Scene.name must equal the name argument passed to the constructor; "
        f"expected 'Tavern', got {scene.name!r}."
    )
    assert scene.description == "A dim tavern.", (
        "Scene.description must equal the description argument passed to the "
        f"constructor; expected 'A dim tavern.', got {scene.description!r}."
    )
    assert scene.active_character_ids == [
        CharacterId("hero"),
        CharacterId("villain"),
    ], (
        "Scene.active_character_ids must equal the list passed to the "
        "constructor; expected [CharacterId('hero'), CharacterId('villain')], "
        f"got {scene.active_character_ids!r}."
    )
    assert scene.messages == [], (
        "Scene.messages must equal the messages list passed to the "
        f"constructor; expected [], got {scene.messages!r}."
    )
