from fastapi import FastAPI
from fastapi.testclient import TestClient

from sidestage.actor import UserActor
from sidestage.app import create_app
from sidestage.campaign import Campaign
from sidestage.character import Character
from sidestage.ids import CampaignId, CharacterId, SceneId
from sidestage.message_repository import InMemoryMessageRepository
from sidestage.scene import Scene


def _make_campaign(
    campaign_id: str = "camp1",
    name: str = "Lost Mines",
    scene_id: str = "scene1",
) -> Campaign:
    character = Character(
        id=CharacterId("hero"),
        name="Hero",
        character_sheet="You are Hero.",
        actor=UserActor(),
    )
    scene = Scene(
        id=SceneId(scene_id),
        campaign_id=CampaignId(campaign_id),
        name="Tavern",
        description="A dim tavern.",
        active_character_ids=[character.id],
        messages=[],
    )
    return Campaign(
        id=CampaignId(campaign_id),
        name=name,
        active_scene_id=SceneId(scene_id),
        characters={character.id: character},
        scenes={scene.id: scene},
    )


def test_create_app_returns_fastapi_instance():
    camp = _make_campaign()
    campaigns = {camp.id: camp}
    repo = InMemoryMessageRepository()

    app = create_app(campaigns, repo)

    assert isinstance(app, FastAPI), (
        "create_app(campaigns, repo) must return a fastapi.FastAPI instance "
        "so the resulting object can be served by uvicorn and mounted with "
        "FastAPI middleware/routes; got an object of type "
        f"{type(app).__name__}: {app!r}."
    )


def test_create_app_wires_rest_router_get_campaigns_returns_200():
    camp = _make_campaign("camp1", name="Lost Mines", scene_id="scene1")
    campaigns = {camp.id: camp}
    repo = InMemoryMessageRepository()

    app = create_app(campaigns, repo)
    client = TestClient(app)

    response = client.get("/campaigns")

    assert response.status_code == 200, (
        "create_app must wire the REST router from sidestage.rest into the "
        "returned FastAPI app so that GET /campaigns is reachable and "
        "returns HTTP 200 OK; got status "
        f"{response.status_code} with body {response.text!r}. This indicates "
        "create_app did not include the rest router (or mounted it under a "
        "different prefix)."
    )


def test_create_app_wires_rest_router_get_campaign_detail_returns_200():
    camp = _make_campaign("camp1", name="Lost Mines", scene_id="scene1")
    campaigns = {camp.id: camp}
    repo = InMemoryMessageRepository()

    app = create_app(campaigns, repo)
    client = TestClient(app)

    response = client.get("/campaigns/camp1")

    assert response.status_code == 200, (
        "create_app must wire the REST router so that "
        "GET /campaigns/{campaign_id} resolves an existing campaign and "
        "returns HTTP 200 OK; for campaign 'camp1' supplied via the "
        "campaigns dict, got status "
        f"{response.status_code} with body {response.text!r}. This indicates "
        "create_app did not pass the campaigns dict through to the rest "
        "router or did not include the router at all."
    )
