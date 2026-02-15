import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone

from sidestage.actors import NPCActor
from sidestage.event import Event
from sidestage.models import CharacterModel, EventModel, EventType


def _make_event(actor_id: str = "user", body: str = "Hi", scene_id: str = "s1") -> Event:
    """Build an Event with a mock scene for testing NPCActor.process()."""
    model = EventModel(
        id="evt_test",
        name="Test Msg",
        body=body,
        event_type=EventType.CHAT_MESSAGE,
        scene_id=scene_id,
        gametime=0,
        walltime=datetime.now(timezone.utc),
        actor_id=actor_id,
        character_id="user",
    )
    event = Event(model=model)
    event.scene = MagicMock()
    event.scene.process = AsyncMock()
    return event


@pytest.mark.anyio
async def test_agent_responds_to_user():
    """Test that agents respond to user messages."""
    char = CharacterModel(id="c1", name="Alice", body="I am Alice")
    actor = NPCActor(actor_id="agent:c1", character=char)
    actor.agent = MagicMock()
    actor.agent.arun = AsyncMock(return_value=MagicMock(content="Hello"))

    event = _make_event()
    await actor.process(event)

    assert actor.agent.arun.called
    assert event.scene is not None
    event.scene.process.assert_awaited_once()


@pytest.mark.anyio
async def test_agent_puts_reply_on_scene():
    """Test that agent replies are routed back through event.scene.process()."""
    char = CharacterModel(id="c1", name="Alice", body="I am Alice")
    actor = NPCActor(actor_id="agent:c1", character=char)
    actor.agent = MagicMock()
    actor.agent.arun = AsyncMock(return_value=MagicMock(content="Hello from Alice"))

    event = _make_event()
    await actor.process(event)

    # Verify the reply was routed through scene.process with the agent's actor_id
    assert event.scene is not None
    event.scene.process.assert_awaited_once()
    reply_event = event.scene.process.call_args[0][0]
    assert reply_event.model.actor_id == "agent:c1"
    assert reply_event.model.character_id == "c1"


@pytest.mark.anyio
async def test_multiple_agents_unique_actor_ids():
    """
    Test that each agent has a unique actor_id based on character ID,
    and both respond when dispatched a user message.
    """
    char1 = CharacterModel(id="c1", name="Alice", body="I am Alice")
    char2 = CharacterModel(id="c2", name="Bob", body="I am Bob")

    actor1 = NPCActor(actor_id="agent:c1", character=char1)
    actor2 = NPCActor(actor_id="agent:c2", character=char2)

    # Verify unique actor_ids
    assert actor1.actor_id == "agent:c1"
    assert actor2.actor_id == "agent:c2"

    actor1.agent = MagicMock()
    actor1.agent.arun = AsyncMock(return_value=MagicMock(content="Hello from Alice"))
    actor2.agent = MagicMock()
    actor2.agent.arun = AsyncMock(return_value=MagicMock(content="Hello from Bob"))

    # User speaks - both should reply
    event1 = _make_event()
    event2 = _make_event()

    await actor1.process(event1)
    await actor2.process(event2)

    assert actor1.agent.arun.called
    assert actor2.agent.arun.called
