"""Unit tests for scene.py -- Scene event loop, dispatch, and event factory."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sidestage.actors import NPCActor, User
from sidestage.character import Character
from sidestage.event import Event
from sidestage.models import CharacterModel, EventModel, EventType, SceneModel
from sidestage.scene import Scene
from sidestage.storage import Storage


# --- Fixtures ---


@pytest.fixture
def mock_storage(tmp_path: Path) -> Storage:
    return Storage(db_path=tmp_path / "test.db")


@pytest.fixture
def scene_data() -> SceneModel:
    return SceneModel(
        id="scene_test", name="Test Scene", body="A test scene.",
        current_gametime=100,
    )


@pytest.fixture
def mock_campaign() -> MagicMock:
    campaign = MagicMock()
    campaign.user = User(actor_id="user")
    campaign.agent = MagicMock()  # LiteLLMAgent mock
    campaign.get_character = MagicMock()
    return campaign


@pytest.fixture
def scene(mock_storage: Storage, scene_data: SceneModel, mock_campaign: MagicMock) -> Scene:
    return Scene(
        storage=mock_storage,
        data=scene_data,
        campaign=mock_campaign,
    )


@pytest.fixture
def chat_event(scene: Scene) -> Event:
    return scene.create_event(
        event_type=EventType.CHAT_MESSAGE,
        actor_id="user",
        body="Hello world",
        character_id="char_alice",
    )


# --- Scene.process() ---


@pytest.mark.anyio
async def test_process_sets_event_scene(scene: Scene, chat_event: Event):
    """Scene.process() sets event.scene = self before enqueueing."""
    scene.queue = MagicMock()
    scene.queue.put = AsyncMock()

    await scene.process(chat_event)

    assert chat_event.scene is scene


@pytest.mark.anyio
async def test_process_puts_event_on_queue(scene: Scene, chat_event: Event):
    """Scene.process() puts event on the queue."""
    scene.queue = MagicMock()
    scene.queue.put = AsyncMock()

    await scene.process(chat_event)

    scene.queue.put.assert_called_once_with(chat_event)


# --- Scene._process_event() ---


@pytest.mark.anyio
async def test_process_event_persists_to_storage(scene: Scene, chat_event: Event):
    """_process_event() persists EventModel to storage."""
    scene.characters = {}  # No actors to dispatch to

    await scene._process_event(chat_event)

    # Verify event was stored
    events = scene.storage.list_events_by_scene("scene_test")
    assert len(events) == 1
    assert events[0].id == chat_event.model.id


@pytest.mark.anyio
async def test_process_event_creates_graph_node(scene: Scene, chat_event: Event):
    """_process_event() creates graph node and HAS_EVENT edge."""
    mock_client = MagicMock()
    scene.graph_client = mock_client
    scene.characters = {}

    with patch("sidestage.graph.create_entity", new_callable=AsyncMock) as mock_create, \
         patch("sidestage.graph.link", new_callable=AsyncMock) as mock_link:
        await scene._process_event(chat_event)

        mock_create.assert_called_once_with(mock_client, chat_event.model)
        # HAS_EVENT edge + INVOLVES edge
        assert mock_link.call_count == 2


@pytest.mark.anyio
async def test_process_event_dispatches_for_all_event_types(scene: Scene):
    """_process_event() calls _dispatch() for each EventType."""
    scene._dispatch = AsyncMock()
    scene.characters = {}

    for et in EventType:
        event = scene.create_event(
            event_type=et,
            actor_id="user",
            body="test",
        )
        await scene._process_event(event)

    assert scene._dispatch.call_count == len(EventType)


@pytest.mark.anyio
async def test_process_event_updates_gametime_for_adjust(scene: Scene):
    """_process_event() updates current_gametime for ADJUST_GAMETIME events."""
    scene.characters = {}
    event = scene.create_event(
        event_type=EventType.ADJUST_GAMETIME,
        actor_id="user",
    )
    event.model.gametime = 3600

    await scene._process_event(event)

    assert scene.data.current_gametime == 3600
    # Verify scene was persisted to storage
    stored = scene.storage.get_scene("scene_test")
    assert stored is not None
    assert stored.current_gametime == 3600


@pytest.mark.anyio
async def test_process_event_does_not_update_gametime_for_other_types(scene: Scene):
    """_process_event() does NOT update gametime for non-ADJUST_GAMETIME events."""
    scene.characters = {}
    original_gametime = scene.data.current_gametime

    event = scene.create_event(
        event_type=EventType.CHAT_MESSAGE,
        actor_id="user",
        body="hello",
    )
    event.model.gametime = 999

    await scene._process_event(event)

    assert scene.data.current_gametime == original_gametime


# --- Scene._dispatch() ---


@pytest.mark.anyio
async def test_dispatch_calls_process_on_all_actors(scene: Scene, chat_event: Event):
    """_dispatch() calls process() on every present actor."""
    npc1 = NPCActor(actor_id="agent:char_1")
    npc1.process = AsyncMock()
    npc2 = NPCActor(actor_id="agent:char_2")
    npc2.process = AsyncMock()
    user = User(actor_id="user")
    user.process = AsyncMock()

    scene.characters = {
        "char_1": Character(CharacterModel(id="char_1", name="NPC1", body=""), npc1),
        "char_2": Character(CharacterModel(id="char_2", name="NPC2", body=""), npc2),
        "char_user": Character(CharacterModel(id="char_user", name="Player", body=""), user),
    }

    await scene._dispatch(chat_event)

    npc1.process.assert_called_once_with(chat_event)
    npc2.process.assert_called_once_with(chat_event)
    user.process.assert_called_once_with(chat_event)


@pytest.mark.anyio
async def test_dispatch_deduplicates_by_actor_id(scene: Scene, chat_event: Event):
    """_dispatch() deduplicates by actor_id (same User controlling 2 characters)."""
    user = User(actor_id="user")
    user.process = AsyncMock()

    scene.characters = {
        "char_a": Character(CharacterModel(id="char_a", name="Alice", body=""), user),
        "char_b": Character(CharacterModel(id="char_b", name="Bob", body=""), user),
    }

    await scene._dispatch(chat_event)

    user.process.assert_called_once()


@pytest.mark.anyio
async def test_dispatch_sends_thinking_before_npc_process(scene: Scene, chat_event: Event):
    """_dispatch() sends thinking status to Users before calling NPCActor.process()."""
    call_order = []

    npc = NPCActor(actor_id="agent:char_npc")
    async def npc_process(event: Event) -> None:
        call_order.append("npc_process")
    npc.process = npc_process

    user = User(actor_id="user")
    user.process = AsyncMock()
    async def capture_send(msg: dict[str, Any], exclude: Any = None) -> None:
        call_order.append(f"user_send_{msg.get('status', 'event')}")
    object.__setattr__(user, "send", capture_send)

    scene.characters = {
        "char_npc": Character(CharacterModel(id="char_npc", name="NPC", body=""), npc),
        "char_user": Character(CharacterModel(id="char_user", name="Player", body=""), user),
    }

    await scene._dispatch(chat_event)

    # thinking should come before npc_process, idle should come after
    assert "user_send_thinking" in call_order
    assert "npc_process" in call_order
    thinking_idx = call_order.index("user_send_thinking")
    process_idx = call_order.index("npc_process")
    assert thinking_idx < process_idx


@pytest.mark.anyio
async def test_dispatch_sends_idle_after_npc_process(scene: Scene, chat_event: Event):
    """_dispatch() sends idle status after NPCActor.process() completes."""
    statuses = []

    npc = NPCActor(actor_id="agent:char_npc")
    npc.process = AsyncMock()

    user = User(actor_id="user")
    user.process = AsyncMock()
    async def capture_send(msg: dict[str, Any], exclude: Any = None) -> None:
        if msg.get("type") == "actor_status":
            statuses.append(msg["status"])
    object.__setattr__(user, "send", capture_send)

    scene.characters = {
        "char_npc": Character(CharacterModel(id="char_npc", name="NPC", body=""), npc),
        "char_user": Character(CharacterModel(id="char_user", name="Player", body=""), user),
    }

    await scene._dispatch(chat_event)

    assert statuses == ["thinking", "idle"]


@pytest.mark.anyio
async def test_dispatch_sends_idle_even_when_npc_raises(scene: Scene, chat_event: Event):
    """_dispatch() sends idle status even when NPCActor.process() raises."""
    statuses = []

    npc = NPCActor(actor_id="agent:char_npc")
    npc.process = AsyncMock(side_effect=RuntimeError("LLM failed"))

    user = User(actor_id="user")
    user.process = AsyncMock()
    async def capture_send(msg: dict[str, Any], exclude: Any = None) -> None:
        if msg.get("type") == "actor_status":
            statuses.append(msg["status"])
    object.__setattr__(user, "send", capture_send)

    scene.characters = {
        "char_npc": Character(CharacterModel(id="char_npc", name="NPC", body=""), npc),
        "char_user": Character(CharacterModel(id="char_user", name="Player", body=""), user),
    }

    await scene._dispatch(chat_event)

    assert "idle" in statuses


@pytest.mark.anyio
async def test_dispatch_no_thinking_for_user_only(scene: Scene, chat_event: Event):
    """_dispatch() does NOT send thinking status when only User actors are present."""
    send_calls = []

    user = User(actor_id="user")
    user.process = AsyncMock()
    async def capture_send(msg: dict[str, Any], exclude: Any = None) -> None:
        send_calls.append(msg)
    object.__setattr__(user, "send", capture_send)

    scene.characters = {
        "char_user": Character(CharacterModel(id="char_user", name="Player", body=""), user),
    }

    await scene._dispatch(chat_event)

    # No actor_status messages should be sent
    status_msgs = [m for m in send_calls if m.get("type") == "actor_status"]
    assert len(status_msgs) == 0


# --- Scene.create_event() ---


def test_create_event_returns_event(scene: Scene):
    """create_event() returns Event wrapping EventModel."""
    event = scene.create_event(EventType.CHAT_MESSAGE, actor_id="user", body="Hello")
    assert isinstance(event, Event)
    assert isinstance(event.model, EventModel)


def test_create_event_generates_evt_prefix(scene: Scene):
    """create_event() generates ID with evt_ prefix."""
    event = scene.create_event(EventType.CHAT_MESSAGE, actor_id="user")
    assert event.model.id.startswith("evt_")


def test_create_event_sets_scene_fields(scene: Scene):
    """create_event() sets scene_id, gametime, walltime, event_type."""
    event = scene.create_event(EventType.JOIN, actor_id="user")
    assert event.model.scene_id == "scene_test"
    assert event.model.gametime == 100  # scene's current_gametime
    assert event.model.walltime is not None
    assert event.model.event_type == EventType.JOIN


def test_create_event_default_name_chat(scene: Scene):
    """create_event() generates default name for CHAT_MESSAGE."""
    event = scene.create_event(EventType.CHAT_MESSAGE, actor_id="user")
    assert event.model.name == "Message"


def test_create_event_default_name_with_character(scene: Scene):
    """create_event() includes character name in default name."""
    scene.characters["char_alice"] = Character(
        CharacterModel(id="char_alice", name="Alice", body=""), User()
    )
    event = scene.create_event(
        EventType.CHAT_MESSAGE, actor_id="user", character_id="char_alice"
    )
    assert event.model.name == "Alice Message"


# --- Scene.chat() ---


@pytest.mark.anyio
async def test_chat_creates_and_enqueues_event(scene: Scene):
    """chat() creates CHAT_MESSAGE event and enqueues via process()."""
    scene.process = AsyncMock()

    await scene.chat(actor_id="user", text="Hello", character_id="char_alice")

    scene.process.assert_called_once()
    event = scene.process.call_args[0][0]
    assert isinstance(event, Event)
    assert event.model.event_type == EventType.CHAT_MESSAGE
    assert event.model.body == "Hello"
    assert event.model.character_id == "char_alice"


@pytest.mark.anyio
async def test_chat_rejects_when_unhealthy(scene: Scene):
    """chat() rejects messages when health is not accepting chat."""
    from sidestage.health import CampaignHealth, HealthStatus
    scene.health = CampaignHealth()
    scene.health.status = HealthStatus.UNHEALTHY
    scene.process = AsyncMock()

    await scene.chat(actor_id="user", text="Hello")

    scene.process.assert_not_called()


# --- Scene lifecycle ---


@pytest.mark.anyio
async def test_activate_starts_queue(scene: Scene, mock_campaign: MagicMock):
    """activate() starts the event queue."""
    scene.queue = MagicMock()
    scene.queue.start = AsyncMock()

    # Mock character loading to return empty
    with patch("sidestage.graph.list_entities", new_callable=AsyncMock, return_value=[]):
        scene.graph_client = MagicMock()
        await scene.activate()

    scene.queue.start.assert_called_once()
    assert scene._active is True


@pytest.mark.anyio
async def test_deactivate_stops_queue_and_clears_characters(scene: Scene):
    """deactivate() stops queue and clears characters dict."""
    scene._active = True
    scene.queue = MagicMock()
    scene.queue.stop = AsyncMock()

    npc = NPCActor(actor_id="npc:1")
    char = Character(CharacterModel(id="c1", name="NPC", body=""), npc)
    char.deactivate = AsyncMock()
    scene.characters = {"c1": char}

    await scene.deactivate()

    scene.queue.stop.assert_called_once()
    char.deactivate.assert_called_once()
    assert scene.characters == {}
    assert scene._active is False
