import pytest

from sidestage.actor import UserActor
from sidestage.campaign import Campaign
from sidestage.character import Character
from sidestage.ids import CampaignId, CharacterId, SceneId
from sidestage.scene import Scene


def _make_scene(scene_id: str = "scene1", name: str = "Tavern") -> Scene:
    return Scene(
        id=SceneId(scene_id),
        campaign_id=CampaignId("camp1"),
        name=name,
        description="A dim tavern.",
        active_character_ids=[],
        messages=[],
    )


def _make_character(char_id: str = "hero", name: str = "Hero") -> Character:
    return Character(
        id=CharacterId(char_id),
        name=name,
        character_sheet=f"You are {name}.",
        actor=UserActor(),
    )


def test_campaign_has_expected_fields():
    scene = _make_scene("scene1")
    character = _make_character("hero")

    campaign = Campaign(
        id=CampaignId("camp1"),
        name="Lost Mines",
        active_scene_id=SceneId("scene1"),
        characters={character.id: character},
        scenes={scene.id: scene},
    )

    assert campaign.id == CampaignId("camp1"), (
        "Campaign.id must equal the CampaignId argument passed to the "
        f"constructor; expected CampaignId('camp1'), got {campaign.id!r}."
    )
    assert campaign.name == "Lost Mines", (
        "Campaign.name must equal the name argument passed to the constructor; "
        f"expected 'Lost Mines', got {campaign.name!r}."
    )
    assert campaign.active_scene_id == SceneId("scene1"), (
        "Campaign.active_scene_id must equal the SceneId argument passed to the "
        f"constructor; expected SceneId('scene1'), got "
        f"{campaign.active_scene_id!r}."
    )
    assert campaign.characters == {character.id: character}, (
        "Campaign.characters must equal the dict passed to the constructor; "
        f"expected {{CharacterId('hero'): <Character>}}, got "
        f"{campaign.characters!r}."
    )
    assert campaign.scenes == {scene.id: scene}, (
        "Campaign.scenes must equal the dict passed to the constructor; "
        f"expected {{SceneId('scene1'): <Scene>}}, got {campaign.scenes!r}."
    )


def test_get_active_scene_returns_scene_matching_active_scene_id():
    scene1 = _make_scene("scene1", name="Tavern")
    scene2 = _make_scene("scene2", name="Forest")
    campaign = Campaign(
        id=CampaignId("camp1"),
        name="Lost Mines",
        active_scene_id=SceneId("scene2"),
        characters={},
        scenes={scene1.id: scene1, scene2.id: scene2},
    )

    result = campaign.get_active_scene()

    assert result is scene2, (
        "Campaign.get_active_scene() must return the Scene from self.scenes "
        "whose key matches self.active_scene_id; with active_scene_id="
        "SceneId('scene2') and scenes={SceneId('scene1'): scene1, "
        "SceneId('scene2'): scene2}, expected the scene2 instance to be "
        f"returned (identity check), got {result!r}."
    )


def test_get_active_scene_raises_value_error_when_active_scene_id_is_none():
    campaign = Campaign(
        id=CampaignId("camp1"),
        name="Lost Mines",
        active_scene_id=None,
        characters={},
        scenes={},
    )

    with pytest.raises(ValueError):
        campaign.get_active_scene()


def test_get_active_scene_raises_key_error_when_active_scene_id_not_in_scenes():
    scene = _make_scene("scene1")
    campaign = Campaign(
        id=CampaignId("camp1"),
        name="Lost Mines",
        active_scene_id=SceneId("missing"),
        characters={},
        scenes={scene.id: scene},
    )

    with pytest.raises(KeyError):
        campaign.get_active_scene()


def test_get_character_returns_character_with_matching_id():
    hero = _make_character("hero", name="Hero")
    villain = _make_character("villain", name="Villain")
    campaign = Campaign(
        id=CampaignId("camp1"),
        name="Lost Mines",
        active_scene_id=None,
        characters={hero.id: hero, villain.id: villain},
        scenes={},
    )

    result = campaign.get_character(CharacterId("villain"))

    assert result is villain, (
        "Campaign.get_character(id) must return the Character from "
        "self.characters whose key equals the given id; with characters="
        "{CharacterId('hero'): hero, CharacterId('villain'): villain} and "
        "id=CharacterId('villain'), expected the villain instance to be "
        f"returned (identity check), got {result!r}."
    )


def test_get_character_raises_key_error_when_id_not_in_characters():
    hero = _make_character("hero")
    campaign = Campaign(
        id=CampaignId("camp1"),
        name="Lost Mines",
        active_scene_id=None,
        characters={hero.id: hero},
        scenes={},
    )

    with pytest.raises(KeyError):
        campaign.get_character(CharacterId("missing"))
