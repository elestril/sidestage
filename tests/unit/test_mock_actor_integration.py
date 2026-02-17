"""Tests for the MockLLMAgent integration point in NPCActor."""

import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from sidestage.actors import NPCActor


def test_update_prompt_creates_mock_agent_when_env_set():
    """When SIDESTAGE_MOCK_AGENT=1 is set, _update_prompt() should create a MockLLMAgent."""
    from sidestage.testing.mock_actor import MockLLMAgent

    actor = NPCActor(actor_id="agent:test_npc")
    actor.character = MagicMock()
    actor.character.name = "TestChar"

    with patch.dict(os.environ, {"SIDESTAGE_MOCK_AGENT": "1"}):
        actor._update_prompt()

    assert isinstance(actor.agent, MockLLMAgent)
    assert actor.agent.name == "TestChar"


def test_update_prompt_creates_litellm_agent_when_env_not_set():
    """When SIDESTAGE_MOCK_AGENT is not set, _update_prompt() should proceed to LiteLLMAgent path."""
    actor = NPCActor(actor_id="agent:test_npc")
    actor.character = MagicMock()
    actor.character.name = "TestChar"
    actor.character.unseen = False
    # Without scene_logic (campaign), _update_prompt returns early after LiteLLM path
    actor.scene_logic = None

    env = os.environ.copy()
    env.pop("SIDESTAGE_MOCK_AGENT", None)
    with patch.dict(os.environ, env, clear=True):
        actor._update_prompt()

    # With no scene_logic, agent stays None (LiteLLM path returns early)
    assert actor.agent is None


@pytest.mark.anyio
async def test_mock_agent_processes_chat_and_returns_canned_response():
    """End-to-end: NPCActor with mock agent should process a chat event and return the canned response."""
    from sidestage.testing.mock_actor import MockLLMAgent, MockResponse
    from sidestage.models import EventModel, EventType
    from sidestage.event import Event
    from datetime import datetime, timezone

    actor = NPCActor(actor_id="agent:test_npc")
    actor.character = MagicMock()
    actor.character.name = "TestNPC"
    actor.character.id = "char_test"

    mock_agent = MockLLMAgent(name="TestNPC")
    mock_agent.responses = [MockResponse(body="I am a mock!", delay=0.01)]
    actor.agent = mock_agent

    # Create a chat event from a user
    event_model = EventModel(
        id="evt_test001",
        name="Test Message",
        body="Hello NPC!",
        event_type=EventType.CHAT_MESSAGE,
        scene_id="scene_test",
        gametime=0,
        walltime=datetime.now(timezone.utc),
        character_id="user",
        actor_id="user",
    )
    event = Event.from_model(event_model)

    # Mock the scene to capture the response
    mock_scene = AsyncMock()
    event.scene = mock_scene

    await actor.process(event)

    # The scene.process should have been called with a response event
    mock_scene.process.assert_called_once()
    response_event = mock_scene.process.call_args[0][0]
    assert response_event.model.body == "I am a mock!"
    assert response_event.model.actor_id == "agent:test_npc"
