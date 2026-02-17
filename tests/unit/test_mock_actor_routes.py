"""Tests for the test-only mock agent API endpoints."""

import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from sidestage.testing.mock_actor import MockLLMAgent, MockResponse
from sidestage.testing.routes import register_test_routes


@pytest.fixture
def mock_orchestrator():
    """Create a mock orchestrator with active scenes containing mock agents."""
    orchestrator = MagicMock()

    # Create a mock agent
    mock_agent = MockLLMAgent(name="TestNPC")

    # Set up character -> actor -> agent chain
    mock_actor = MagicMock()
    mock_actor.agent = mock_agent

    mock_character = MagicMock()
    mock_character.actor = mock_actor

    # Set up scene -> characters
    mock_scene = MagicMock()
    mock_scene.characters = {"char_test": mock_character}

    orchestrator.active_scenes = {"scene_test": mock_scene}
    return orchestrator


@pytest.fixture
def test_app(mock_orchestrator):
    """Create a FastAPI app with test routes registered."""
    app = FastAPI()
    register_test_routes(app, mock_orchestrator)
    return app


@pytest.mark.anyio
async def test_configure_sets_response_queue(test_app, mock_orchestrator):
    """POST /v1/test/mock-agent/configure should set the response queue on all active mock agents."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/test/mock-agent/configure",
            json={
                "responses": [{"body": "Hello from mock!"}],
                "default_response": "Default mock",
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["agents_configured"] == 1

    # Verify the agent was configured
    scene = mock_orchestrator.active_scenes["scene_test"]
    char = scene.characters["char_test"]
    agent = char.actor.agent
    assert len(agent.responses) == 1
    assert agent.responses[0].body == "Hello from mock!"
    assert agent.default_response == "Default mock"


@pytest.mark.anyio
async def test_reset_clears_response_queue(test_app, mock_orchestrator):
    """POST /v1/test/mock-agent/reset should clear the response queue on all active mock agents."""
    # Pre-configure the agent
    scene = mock_orchestrator.active_scenes["scene_test"]
    agent = scene.characters["char_test"].actor.agent
    agent.responses = [MockResponse(body="old")]
    agent.default_response = "old default"

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post("/v1/test/mock-agent/reset")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["agents_reset"] == 1

    assert len(agent.responses) == 0
    assert agent.default_response == "Mock response"
    assert agent.response_delay == 0.1


@pytest.mark.anyio
async def test_configure_reaches_active_scene_mock_agents(test_app, mock_orchestrator):
    """Configure endpoint should traverse active_scenes to find and update mock agents."""
    # Add a second scene with a mock agent
    mock_agent2 = MockLLMAgent(name="SecondNPC")
    mock_actor2 = MagicMock()
    mock_actor2.agent = mock_agent2
    mock_char2 = MagicMock()
    mock_char2.actor = mock_actor2
    mock_scene2 = MagicMock()
    mock_scene2.characters = {"char_test2": mock_char2}
    mock_orchestrator.active_scenes["scene_test2"] = mock_scene2

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/test/mock-agent/configure",
            json={"responses": [{"body": "Shared response"}]},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["agents_configured"] == 2


@pytest.mark.anyio
async def test_endpoints_return_404_when_mock_agent_not_set():
    """Test endpoints should return 404 when SIDESTAGE_MOCK_AGENT is not set (routes not registered)."""
    app = FastAPI()
    # Do NOT register test routes — simulates production where SIDESTAGE_MOCK_AGENT is unset

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp_configure = await client.post(
            "/v1/test/mock-agent/configure", json={"responses": []}
        )
        resp_reset = await client.post("/v1/test/mock-agent/reset")
    assert resp_configure.status_code == 404
    assert resp_reset.status_code == 404


@pytest.mark.anyio
async def test_configure_with_no_active_scenes():
    """Configure should succeed with agents_configured=0 when no scenes are active."""
    app = FastAPI()
    orchestrator = MagicMock()
    orchestrator.active_scenes = {}
    register_test_routes(app, orchestrator)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/test/mock-agent/configure",
            json={"responses": [{"body": "No one home"}]},
        )
    assert response.status_code == 200
    assert response.json()["agents_configured"] == 0
