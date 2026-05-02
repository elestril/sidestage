from fastapi import FastAPI
from fastapi.testclient import TestClient

from sidestage.actor import UserActor
from sidestage.campaign import Campaign
from sidestage.character import Character
from sidestage.ids import CampaignId, CharacterId, SceneId
from sidestage.message import Message
from sidestage.message_repository import InMemoryMessageRepository
from sidestage.rest import create_router
from sidestage.scene import Scene


def _make_character(char_id: str = "hero", name: str = "Hero") -> Character:
    return Character(
        id=CharacterId(char_id),
        name=name,
        character_sheet=f"You are {name}.",
        actor=UserActor(),
    )


def _make_scene(scene_id: str = "scene1", campaign_id: str = "camp1") -> Scene:
    return Scene(
        id=SceneId(scene_id),
        campaign_id=CampaignId(campaign_id),
        name="Tavern",
        description="A dim tavern.",
        active_character_ids=[],
        messages=[],
    )


def _make_campaign(
    campaign_id: str = "camp1",
    name: str = "Lost Mines",
    active_scene_id: str | None = "scene1",
) -> Campaign:
    scene = _make_scene(active_scene_id or "scene1", campaign_id)
    character = _make_character()
    return Campaign(
        id=CampaignId(campaign_id),
        name=name,
        active_scene_id=SceneId(active_scene_id) if active_scene_id else None,
        characters={character.id: character},
        scenes={scene.id: scene},
    )


def _build_client(
    campaigns: dict[CampaignId, Campaign],
    repo: InMemoryMessageRepository,
) -> TestClient:
    app = FastAPI()
    app.include_router(create_router(campaigns, repo))
    return TestClient(app)


def test_get_campaigns_returns_200_with_list_of_campaign_summaries():
    camp1 = _make_campaign("camp1", name="Lost Mines", active_scene_id="scene1")
    camp2 = _make_campaign("camp2", name="Curse of Strahd", active_scene_id="scene1")
    campaigns = {camp1.id: camp1, camp2.id: camp2}
    repo = InMemoryMessageRepository()
    client = _build_client(campaigns, repo)

    response = client.get("/campaigns")

    assert response.status_code == 200, (
        "GET /campaigns must return HTTP 200 OK when campaigns can be listed; "
        f"got status {response.status_code} with body {response.text!r}."
    )
    body = response.json()
    assert isinstance(body, list), (
        "GET /campaigns must return a JSON list (one entry per campaign); "
        f"got body of type {type(body).__name__}: {body!r}."
    )
    assert len(body) == 2, (
        "GET /campaigns must return one entry per campaign in the supplied "
        "campaigns dict; with 2 campaigns provided expected len(body) == 2, "
        f"got len(body) == {len(body)}: {body!r}."
    )
    by_id = {entry["id"]: entry for entry in body}
    assert "camp1" in by_id and "camp2" in by_id, (
        "GET /campaigns entries must each contain an 'id' field whose value "
        "is the CampaignId.value string; expected ids 'camp1' and 'camp2' "
        f"in the response, got entries {body!r}."
    )
    assert by_id["camp1"]["name"] == "Lost Mines", (
        "GET /campaigns entries must include a 'name' field equal to the "
        "Campaign.name value; expected 'Lost Mines' for camp1, got "
        f"{by_id['camp1']!r}."
    )
    assert by_id["camp2"]["name"] == "Curse of Strahd", (
        "GET /campaigns entries must include a 'name' field equal to the "
        "Campaign.name value; expected 'Curse of Strahd' for camp2, got "
        f"{by_id['camp2']!r}."
    )


def test_get_campaign_detail_returns_200_with_id_name_and_active_scene_id():
    camp = _make_campaign("camp1", name="Lost Mines", active_scene_id="scene1")
    campaigns = {camp.id: camp}
    repo = InMemoryMessageRepository()
    client = _build_client(campaigns, repo)

    response = client.get("/campaigns/camp1")

    assert response.status_code == 200, (
        "GET /campaigns/{campaign_id} must return HTTP 200 OK when the "
        "campaign exists; got status "
        f"{response.status_code} with body {response.text!r}."
    )
    body = response.json()
    assert isinstance(body, dict), (
        "GET /campaigns/{campaign_id} must return a JSON object; got body of "
        f"type {type(body).__name__}: {body!r}."
    )
    assert body.get("id") == "camp1", (
        "GET /campaigns/{campaign_id} response must include an 'id' field "
        "equal to the CampaignId.value string; expected 'camp1' got "
        f"{body.get('id')!r} (full body: {body!r})."
    )
    assert body.get("name") == "Lost Mines", (
        "GET /campaigns/{campaign_id} response must include a 'name' field "
        "equal to the Campaign.name value; expected 'Lost Mines' got "
        f"{body.get('name')!r} (full body: {body!r})."
    )
    assert body.get("active_scene_id") == "scene1", (
        "GET /campaigns/{campaign_id} response must include an "
        "'active_scene_id' field equal to the SceneId.value string of the "
        "campaign's active scene; expected 'scene1' got "
        f"{body.get('active_scene_id')!r} (full body: {body!r})."
    )


def test_get_campaign_detail_returns_404_for_unknown_campaign_id():
    camp = _make_campaign("camp1")
    campaigns = {camp.id: camp}
    repo = InMemoryMessageRepository()
    client = _build_client(campaigns, repo)

    response = client.get("/campaigns/does_not_exist")

    assert response.status_code == 404, (
        "GET /campaigns/{campaign_id} must return HTTP 404 Not Found when "
        "the campaign id is not in the campaigns dict; got status "
        f"{response.status_code} with body {response.text!r}."
    )


async def test_get_messages_returns_200_with_messages_in_order():
    camp = _make_campaign("camp1", active_scene_id="scene1")
    campaigns = {camp.id: camp}
    repo = InMemoryMessageRepository()

    msg1 = Message.create(SceneId("scene1"), CharacterId("hero"), "first")
    msg2 = Message.create(SceneId("scene1"), CharacterId("villain"), "second")
    await repo.append(msg1)
    await repo.append(msg2)

    client = _build_client(campaigns, repo)
    response = client.get("/campaigns/camp1/scenes/scene1/messages")

    assert response.status_code == 200, (
        "GET /campaigns/{campaign_id}/scenes/{scene_id}/messages must return "
        "HTTP 200 OK when both campaign and scene exist; got status "
        f"{response.status_code} with body {response.text!r}."
    )
    body = response.json()
    assert isinstance(body, list), (
        "GET /campaigns/{campaign_id}/scenes/{scene_id}/messages must return "
        "a JSON list of message dicts; got body of type "
        f"{type(body).__name__}: {body!r}."
    )
    assert len(body) == 2, (
        "GET /campaigns/{campaign_id}/scenes/{scene_id}/messages must return "
        "every message that the repository has for that scene; with 2 "
        f"messages appended, expected len(body) == 2, got {len(body)}: "
        f"{body!r}."
    )
    assert body[0].get("content") == "first", (
        "GET /campaigns/{campaign_id}/scenes/{scene_id}/messages must "
        "preserve the repository's insertion order; expected the first "
        "returned entry to have content 'first' (the first appended message)"
        f", got body[0] == {body[0]!r}."
    )
    assert body[1].get("content") == "second", (
        "GET /campaigns/{campaign_id}/scenes/{scene_id}/messages must "
        "preserve the repository's insertion order; expected the second "
        "returned entry to have content 'second' (the second appended "
        f"message), got body[1] == {body[1]!r}."
    )
    assert body[0].get("character_id") == "hero", (
        "Each message dict returned by GET .../messages must include a "
        "'character_id' field equal to the CharacterId.value string; "
        f"expected 'hero' for the first message, got {body[0]!r}."
    )
    assert body[1].get("character_id") == "villain", (
        "Each message dict returned by GET .../messages must include a "
        "'character_id' field equal to the CharacterId.value string; "
        f"expected 'villain' for the second message, got {body[1]!r}."
    )
    assert "id" in body[0] and "timestamp" in body[0], (
        "Each message dict returned by GET .../messages must include 'id' "
        "and 'timestamp' fields (alongside 'character_id' and 'content'); "
        f"got body[0] == {body[0]!r}."
    )


def test_get_messages_returns_404_for_unknown_campaign_id():
    camp = _make_campaign("camp1", active_scene_id="scene1")
    campaigns = {camp.id: camp}
    repo = InMemoryMessageRepository()
    client = _build_client(campaigns, repo)

    response = client.get("/campaigns/does_not_exist/scenes/scene1/messages")

    assert response.status_code == 404, (
        "GET /campaigns/{campaign_id}/scenes/{scene_id}/messages must return "
        "HTTP 404 Not Found when the campaign id is not in the campaigns "
        f"dict; got status {response.status_code} with body "
        f"{response.text!r}."
    )
