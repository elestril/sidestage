from typing import AsyncIterator

import pytest

from sidestage.actor import NpcActor, UserActor
from sidestage.campaign import Campaign
from sidestage.character import Character
from sidestage.chat_service import ChatService
from sidestage.ids import CampaignId, CharacterId, SceneId
from sidestage.llm_client import LLMMessage
from sidestage.message import Message
from sidestage.message_repository import InMemoryMessageRepository
from sidestage.scene import Scene


class _StubLLMClient:
    """Minimal LLMClient stub used only to satisfy NpcActor's constructor."""

    async def stream(
        self, messages: list[LLMMessage], model: str | None
    ) -> AsyncIterator[str]:
        raise NotImplementedError
        yield  # pragma: no cover


def _make_scene(
    scene_id: str = "scene1",
    campaign_id: str = "camp1",
    active_character_ids: list[CharacterId] | None = None,
) -> Scene:
    return Scene(
        id=SceneId(scene_id),
        campaign_id=CampaignId(campaign_id),
        name="Tavern",
        description="A dim tavern.",
        active_character_ids=active_character_ids
        if active_character_ids is not None
        else [],
        messages=[],
    )


def _make_user_character(char_id: str = "hero", name: str = "Hero") -> Character:
    return Character(
        id=CharacterId(char_id),
        name=name,
        character_sheet=f"You are {name}.",
        actor=UserActor(),
    )


def _make_npc_character(char_id: str = "npc", name: str = "NPC") -> Character:
    return Character(
        id=CharacterId(char_id),
        name=name,
        character_sheet=f"You are {name}.",
        actor=NpcActor(_StubLLMClient(), model=None),
    )


def _make_campaign(
    scene: Scene,
    characters: list[Character],
    campaign_id: str = "camp1",
) -> Campaign:
    return Campaign(
        id=CampaignId(campaign_id),
        name="Lost Mines",
        active_scene_id=scene.id,
        characters={c.id: c for c in characters},
        scenes={scene.id: scene},
    )


async def test_handle_user_message_returns_message_with_matching_character_id_and_content():
    hero = _make_user_character("hero")
    scene = _make_scene(active_character_ids=[hero.id])
    campaign = _make_campaign(scene, [hero])
    repo = InMemoryMessageRepository()
    service = ChatService({campaign.id: campaign}, repo)

    result = await service.handle_user_message(campaign.id, hero.id, "hello there")

    assert isinstance(result, Message), (
        "ChatService.handle_user_message must return a Message instance "
        "(constructed via Message.create(scene.id, character_id, content)). "
        f"Got an object of type {type(result).__name__}: {result!r}."
    )
    assert result.character_id == hero.id, (
        "ChatService.handle_user_message must return a Message whose "
        "character_id equals the character_id argument it was called with; "
        f"expected {hero.id!r}, got {result.character_id!r}."
    )
    assert result.content == "hello there", (
        "ChatService.handle_user_message must return a Message whose content "
        "equals the content argument it was called with; expected "
        f"'hello there', got {result.content!r}."
    )
    assert result.scene_id == scene.id, (
        "ChatService.handle_user_message must build the Message with "
        "scene_id == campaign.get_active_scene().id; expected "
        f"{scene.id!r}, got {result.scene_id!r}."
    )


async def test_handle_user_message_appends_message_to_active_scene_messages():
    hero = _make_user_character("hero")
    scene = _make_scene(active_character_ids=[hero.id])
    campaign = _make_campaign(scene, [hero])
    repo = InMemoryMessageRepository()
    service = ChatService({campaign.id: campaign}, repo)

    result = await service.handle_user_message(campaign.id, hero.id, "hello there")

    assert result in scene.messages, (
        "ChatService.handle_user_message must call scene.add_message(message) "
        "on the active scene so that the returned Message is present in "
        f"scene.messages after the call. Expected {result!r} to be in "
        f"scene.messages, but scene.messages was {scene.messages!r}."
    )


async def test_handle_user_message_persists_message_to_repository():
    hero = _make_user_character("hero")
    scene = _make_scene(active_character_ids=[hero.id])
    campaign = _make_campaign(scene, [hero])
    repo = InMemoryMessageRepository()
    service = ChatService({campaign.id: campaign}, repo)

    result = await service.handle_user_message(campaign.id, hero.id, "hello there")
    persisted = await repo.get_by_scene(scene.id)

    assert result in persisted, (
        "ChatService.handle_user_message must call `await repo.append(message)` "
        "so that the returned Message is retrievable via "
        "`await repo.get_by_scene(scene.id)`. Expected the returned message "
        f"{result!r} to be in the repo's messages for scene {scene.id!r}, "
        f"but get_by_scene returned {persisted!r}."
    )


async def test_handle_user_message_raises_key_error_when_campaign_not_found():
    hero = _make_user_character("hero")
    scene = _make_scene(active_character_ids=[hero.id])
    campaign = _make_campaign(scene, [hero])
    repo = InMemoryMessageRepository()
    service = ChatService({campaign.id: campaign}, repo)

    with pytest.raises(KeyError):
        await service.handle_user_message(
            CampaignId("missing_campaign"), hero.id, "hello"
        )


async def test_handle_user_message_raises_value_error_when_character_actor_is_npc():
    npc = _make_npc_character("npc")
    scene = _make_scene(active_character_ids=[npc.id])
    campaign = _make_campaign(scene, [npc])
    repo = InMemoryMessageRepository()
    service = ChatService({campaign.id: campaign}, repo)

    with pytest.raises(ValueError):
        await service.handle_user_message(campaign.id, npc.id, "hello")


async def test_handle_user_message_raises_value_error_when_character_not_in_active_character_ids():
    hero = _make_user_character("hero")
    # Scene exists but does NOT include hero in active_character_ids.
    scene = _make_scene(active_character_ids=[])
    campaign = _make_campaign(scene, [hero])
    repo = InMemoryMessageRepository()
    service = ChatService({campaign.id: campaign}, repo)

    with pytest.raises(ValueError):
        await service.handle_user_message(campaign.id, hero.id, "hello")
