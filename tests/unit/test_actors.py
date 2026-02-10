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
async def test_npc_actor_process_ignores_non_user_events():
    """NPCActor.process() returns without action for non-User-originated events."""
    npc = NPCActor(actor_id="agent:char_1")
    event = _make_event()
    # No character set on event, so it should return without error
    await npc.process(event)


@pytest.mark.anyio
async def test_npc_actor_process_ignores_non_chat_events():
    """NPCActor.process() returns without action for non-CHAT_MESSAGE events."""
    npc = NPCActor(actor_id="agent:char_1")
    event = _make_event(event_type=EventType.JOIN)
    await npc.process(event)


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
