"""Tests for the Actor hierarchy: Actor ABC, NPCActor, User."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from sidestage.actors import Actor, NPCActor, User
from sidestage.event import Event
from sidestage.models import EventModel, EventType, Visibility


def _make_event(**overrides) -> Event:
    """Helper to create an Event with sensible defaults."""
    defaults = dict(
        id="evt_test",
        name="Test",
        body="hello",
        event_type=EventType.CHAT_MESSAGE,
        scene_id="scene_1",
        gametime=0,
        walltime=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    model = EventModel(**defaults)
    return Event(model=model)


# --- Base Actor ---

def test_actor_is_abstract():
    """Actor is abstract, cannot be instantiated directly."""
    with pytest.raises(TypeError):
        Actor(actor_id="test")


def test_actor_requires_process():
    """Subclass that does not implement process() cannot be instantiated."""
    class IncompleteActor(Actor):
        pass

    with pytest.raises(TypeError):
        IncompleteActor(actor_id="test")


def test_actor_concrete_subclass_stores_actor_id():
    """Concrete subclass stores actor_id."""
    class ConcreteActor(Actor):
        async def process(self, event):
            pass

    actor = ConcreteActor(actor_id="test-123")
    assert actor.actor_id == "test-123"


# --- NPCActor ---

def test_npc_actor_is_concrete():
    """NPCActor can be instantiated."""
    npc = NPCActor(actor_id="agent:char_1")
    assert isinstance(npc, Actor)
    assert npc.actor_id == "agent:char_1"


def test_npc_actor_system_actor_default_false():
    """NPCActor.system_actor defaults to False."""
    npc = NPCActor(actor_id="agent:char_1")
    assert npc.system_actor is False


def test_npc_actor_system_actor_true():
    """NPCActor with system_actor=True."""
    npc = NPCActor(actor_id="agent:char_co_author", system_actor=True)
    assert npc.system_actor is True


@pytest.mark.anyio
async def test_npc_actor_process_ignores_non_chat_events():
    """NPCActor.process() returns without action for non-CHAT_MESSAGE events."""
    npc = NPCActor(actor_id="agent:char_1")
    npc.agent = AsyncMock()
    event = _make_event(event_type=EventType.JOIN, actor_id="user")
    await npc.process(event)
    npc.agent.arun.assert_not_called()


@pytest.mark.anyio
async def test_npc_actor_process_ignores_own_events():
    """NPCActor.process() skips events it sent itself."""
    npc = NPCActor(actor_id="agent:char_1")
    npc.agent = AsyncMock()
    event = _make_event(actor_id="agent:char_1")
    await npc.process(event)
    npc.agent.arun.assert_not_called()


@pytest.mark.anyio
async def test_npc_actor_process_ignores_other_npc_events():
    """NPCActor.process() skips CHAT_MESSAGE events from other NPCs."""
    npc = NPCActor(actor_id="agent:char_1")
    npc.agent = AsyncMock()
    event = _make_event(actor_id="agent:char_2")
    await npc.process(event)
    npc.agent.arun.assert_not_called()


@pytest.mark.anyio
async def test_npc_actor_process_ignores_none_actor_id():
    """NPCActor.process() skips events with actor_id=None (unknown source)."""
    npc = NPCActor(actor_id="agent:char_1")
    npc.agent = AsyncMock()
    event = _make_event()  # actor_id defaults to None
    assert event.model.actor_id is None
    await npc.process(event)
    npc.agent.arun.assert_not_called()


@pytest.mark.anyio
async def test_npc_actor_process_responds_to_user_events():
    """NPCActor.process() calls the LLM agent for User-originated events."""
    npc = NPCActor(actor_id="agent:char_1")
    npc.agent = AsyncMock()
    npc.agent.arun.return_value = MagicMock(content="")

    event = _make_event(actor_id="user")
    await npc.process(event)
    npc.agent.arun.assert_called_once()


@pytest.mark.anyio
async def test_npc_actor_process_enqueues_response():
    """NPCActor.process() enqueues a response event when the LLM replies."""
    npc = NPCActor(actor_id="agent:char_1")
    char = MagicMock()
    char.name = "Alice"
    char.id = "char_1"
    npc.character = char
    npc.agent = AsyncMock()
    npc.agent.arun.return_value = MagicMock(content="Hello traveler!")

    mock_scene = AsyncMock()
    event = _make_event(actor_id="user")
    event.scene = mock_scene

    await npc.process(event)

    mock_scene.process.assert_called_once()
    response_event = mock_scene.process.call_args[0][0]
    assert response_event.model.actor_id == "agent:char_1"
    assert response_event.model.body == "Hello traveler!"
    assert response_event.model.event_type == EventType.CHAT_MESSAGE


@pytest.mark.anyio
async def test_npc_does_not_respond_to_other_npc_response():
    """Two NPCs: NPC B must not respond when NPC A's response is dispatched."""
    npc_a = NPCActor(actor_id="agent:char_a")
    npc_b = NPCActor(actor_id="agent:char_b")
    npc_b.agent = AsyncMock()

    # Simulate NPC A's response event being dispatched to NPC B
    event_from_a = _make_event(actor_id="agent:char_a", body="I am NPC A!")
    await npc_b.process(event_from_a)
    npc_b.agent.arun.assert_not_called()


@pytest.mark.anyio
async def test_system_actor_does_not_respond_to_npc():
    """System actor (co-author) must not respond to regular NPC events."""
    co_author = NPCActor(actor_id="agent:char_co_author", system_actor=True)
    co_author.agent = AsyncMock()

    event_from_npc = _make_event(actor_id="agent:char_alice")
    await co_author.process(event_from_npc)
    co_author.agent.arun.assert_not_called()


@pytest.mark.anyio
async def test_npc_does_not_respond_to_system_actor():
    """Regular NPC must not respond to system actor (co-author) events."""
    npc = NPCActor(actor_id="agent:char_alice")
    npc.agent = AsyncMock()

    event_from_coauthor = _make_event(actor_id="agent:char_co_author")
    await npc.process(event_from_coauthor)
    npc.agent.arun.assert_not_called()


# --- User ---

def test_user_is_concrete():
    """User can be instantiated."""
    user = User(actor_id="user")
    assert isinstance(user, Actor)
    assert user.actor_id == "user"


def test_user_connections_starts_empty():
    """User.connections starts empty."""
    user = User(actor_id="user")
    assert user.connections == []


@pytest.mark.anyio
async def test_user_connect_adds_websocket():
    """User.connect() accepts WebSocket and adds to connections."""
    user = User(actor_id="user")
    mock_ws = AsyncMock()
    await user.connect(mock_ws)
    assert mock_ws in user.connections


def test_user_disconnect_removes_websocket():
    """User.disconnect() removes WebSocket from connections."""
    user = User(actor_id="user")
    mock_ws = MagicMock()
    user.connections.append(mock_ws)
    user.disconnect(mock_ws)
    assert mock_ws not in user.connections


@pytest.mark.anyio
async def test_user_process_sends_to_all_connections():
    """User.process() sends event data to all connected WebSockets."""
    user = User(actor_id="user")
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    user.connections = [ws1, ws2]

    event = _make_event(scene_id="scene_test")
    await user.process(event)

    # Both should have been called
    assert ws1.send_json.called
    assert ws2.send_json.called


@pytest.mark.anyio
async def test_user_send_broadcasts_to_all():
    """User.send() broadcasts message to all connections."""
    user = User(actor_id="user")
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    user.connections = [ws1, ws2]

    msg = {"type": "test", "data": "hello"}
    await user.send(msg)

    ws1.send_json.assert_called_once_with(msg)
    ws2.send_json.assert_called_once_with(msg)


@pytest.mark.anyio
async def test_user_send_with_exclude():
    """User.send() with exclude skips the excluded WebSocket."""
    user = User(actor_id="user")
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    user.connections = [ws1, ws2]

    msg = {"type": "test"}
    await user.send(msg, exclude=ws1)

    ws1.send_json.assert_not_called()
    ws2.send_json.assert_called_once_with(msg)


@pytest.mark.anyio
async def test_user_send_removes_broken_connection():
    """User.send() removes WebSocket on send failure."""
    user = User(actor_id="user")
    broken_ws = AsyncMock()
    broken_ws.send_json.side_effect = Exception("connection closed")
    good_ws = AsyncMock()
    user.connections = [broken_ws, good_ws]

    await user.send({"type": "test"})

    assert broken_ws not in user.connections
    assert good_ws in user.connections
