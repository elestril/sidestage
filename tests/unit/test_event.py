import asyncio
from datetime import datetime, timezone

import pytest

from sidestage.models import EventModel, EventType
from sidestage.event import Event, EventQueue

# EventQueue uses asyncio.create_task, so restrict async tests to asyncio backend

@pytest.fixture(params=["asyncio"])
def anyio_backend(request):
    return request.param


def _make_event_model(**overrides) -> EventModel:
    """Helper to create an EventModel with sensible defaults."""
    defaults = dict(
        id="evt_test",
        name="Test",
        body="",
        event_type=EventType.CHAT_MESSAGE,
        scene_id="scene_1",
        gametime=0,
        walltime=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return EventModel(**defaults)


# --- Event Wrapper ---

def test_event_wraps_event_model():
    """Event wraps an EventModel instance."""
    model = _make_event_model()
    event = Event(model=model)
    assert event.model is model


def test_event_is_not_pydantic():
    """Event is a plain class, not a Pydantic model."""
    from pydantic import BaseModel
    assert not issubclass(Event, BaseModel)


def test_event_span_context_defaults_none():
    """Event.span_context defaults to None."""
    event = Event(model=_make_event_model())
    assert event.span_context is None


def test_event_scene_defaults_none():
    """Event.scene defaults to None."""
    event = Event(model=_make_event_model())
    assert event.scene is None


def test_event_character_returns_none_when_scene_none():
    """Event.character returns None when scene is not set."""
    model = _make_event_model(character_id="char_1")
    event = Event(model=model)
    assert event.character is None


def test_event_character_returns_none_when_character_id_none():
    """Event.character returns None when model.character_id is None."""
    model = _make_event_model(character_id=None)
    event = Event(model=model)
    event.scene = type("FakeScene", (), {"characters": {}})()
    assert event.character is None


def test_event_character_looks_up_from_scene():
    """Event.character looks up character from scene.characters dict."""
    model = _make_event_model(character_id="char_alice")
    event = Event(model=model)
    fake_char = object()
    event.scene = type("FakeScene", (), {"characters": {"char_alice": fake_char}})()
    assert event.character is fake_char


# --- Factory ---

def test_event_from_model_creates_event():
    """Event.from_model() creates an Event from an EventModel."""
    model = _make_event_model()
    event = Event.from_model(model)
    assert isinstance(event, Event)
    assert event.model is model


def test_event_from_model_scene_is_none():
    """Event.from_model() does NOT set scene reference."""
    model = _make_event_model()
    event = Event.from_model(model)
    assert event.scene is None


def test_event_from_model_span_context_none_without_active_span():
    """Event.from_model() sets span_context=None when no active span."""
    model = _make_event_model()
    event = Event.from_model(model)
    assert event.span_context is None


# --- Queue Integration ---

@pytest.mark.anyio
async def test_event_queue_accepts_event_objects():
    """EventQueue accepts Event objects (not raw EventModel)."""
    received = []

    async def handler(event: Event):
        received.append(event)

    queue = EventQueue()
    await queue.start(handler)

    model = _make_event_model()
    event = Event.from_model(model)
    await queue.put(event)

    await asyncio.sleep(0.05)
    await queue.stop()

    assert len(received) == 1
    assert received[0] is event
    assert isinstance(received[0], Event)


@pytest.mark.anyio
async def test_event_queue_handler_receives_event_objects():
    """EventQueue handler receives Event (not EventModel)."""
    received_types = []

    async def handler(event: Event):
        received_types.append(type(event).__name__)

    queue = EventQueue()
    await queue.start(handler)
    await queue.put(Event.from_model(_make_event_model()))
    await asyncio.sleep(0.05)
    await queue.stop()

    assert received_types == ["Event"]


@pytest.mark.anyio
async def test_event_queue_start_stop_lifecycle():
    """EventQueue start/stop lifecycle works with Event type."""
    queue = EventQueue()

    async def handler(event: Event):
        pass

    await queue.start(handler)
    assert queue._running is True
    await queue.stop()
    assert queue._running is False
