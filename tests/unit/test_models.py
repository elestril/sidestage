from datetime import datetime, timezone

from sidestage.models import (
    CharacterModel,
    EntityModel,
    EventModel,
    EventType,
    ItemModel,
    LocationModel,
    SceneModel,
    Visibility,
)


# --- Existing tests ---

def test_character_model():
    char = CharacterModel(id="test", name="Test", body="Test body")
    assert char.name == "Test"
    assert char.body == "Test body"

def test_location_model():
    loc = LocationModel(id="test", name="Test", body="Test body")
    assert loc.name == "Test"
    assert loc.body == "Test body"

def test_item_model():
    item = ItemModel(id="test", name="Test", body="Test body")
    assert item.name == "Test"
    assert item.body == "Test body"


# --- EventType Enum ---

def test_event_type_enum_values():
    """EventType enum has all expected values with legacy-compatible string values."""
    assert EventType.CHAT_MESSAGE == "ChatMessage"
    assert EventType.JOIN == "JoinEvent"
    assert EventType.LEAVE == "LeaveEvent"
    assert EventType.ADJUST_GAMETIME == "AdjustGametime"
    assert EventType.ERROR == "Error"


def test_event_type_is_str_enum():
    """EventType values are strings (str, Enum mixin)."""
    for member in EventType:
        assert isinstance(member.value, str)


def test_visibility_enum_values():
    """Visibility enum has PUBLIC, GM_ONLY, PRIVATE."""
    assert Visibility.PUBLIC == "public"
    assert Visibility.GM_ONLY == "gm_only"
    assert Visibility.PRIVATE == "private"


# --- Flattened EventModel ---

def test_event_model_entity_type_is_classvar():
    """entity_type is a ClassVar set to 'Event', not an instance field."""
    event = EventModel(
        id="evt_test1",
        name="Test Message",
        body="hello",
        event_type=EventType.CHAT_MESSAGE,
        scene_id="scene_1",
        gametime=0,
        walltime=datetime.now(timezone.utc),
    )
    assert EventModel.entity_type == "Event"
    dumped = event.model_dump()
    assert "entity_type" not in dumped


def test_event_model_event_type_is_instance_field():
    """event_type is a per-instance discriminator field."""
    event = EventModel(
        id="evt_test2",
        name="Test Message",
        body="hello",
        event_type=EventType.CHAT_MESSAGE,
        scene_id="scene_1",
        gametime=0,
        walltime=datetime.now(timezone.utc),
    )
    assert event.event_type == EventType.CHAT_MESSAGE
    dumped = event.model_dump()
    assert "event_type" in dumped
    assert dumped["event_type"] == "ChatMessage"


def test_event_model_inherits_entity_model():
    """EventModel has id, name, body fields from EntityModel."""
    event = EventModel(
        id="evt_test3",
        name="Alice Message",
        body="hello world",
        event_type=EventType.CHAT_MESSAGE,
        scene_id="scene_1",
        gametime=100,
        walltime=datetime.now(timezone.utc),
    )
    assert event.id == "evt_test3"
    assert event.name == "Alice Message"
    assert event.body == "hello world"


def test_event_model_defaults():
    """EventModel defaults: visibility=PUBLIC, body='', metadata={}."""
    event = EventModel(
        id="evt_test4",
        name="Test",
        event_type=EventType.JOIN,
        scene_id="scene_1",
        gametime=0,
        walltime=datetime.now(timezone.utc),
    )
    assert event.visibility == Visibility.PUBLIC
    assert event.body == ""
    assert event.metadata == {}


def test_event_model_with_all_fields():
    """EventModel with character_id, actor_id, metadata, visibility set."""
    now = datetime.now(timezone.utc)
    event = EventModel(
        id="evt_test5",
        name="Bob Message",
        body="some text",
        event_type=EventType.CHAT_MESSAGE,
        scene_id="scene_2",
        gametime=500,
        walltime=now,
        character_id="char_bob",
        actor_id="user",
        metadata={"widget": {"type": "entity_card"}},
        visibility=Visibility.GM_ONLY,
    )
    assert event.character_id == "char_bob"
    assert event.actor_id == "user"
    assert event.metadata == {"widget": {"type": "entity_card"}}
    assert event.visibility == Visibility.GM_ONLY


def test_event_model_serialization():
    """model_dump() includes event_type, excludes entity_type ClassVar."""
    now = datetime.now(timezone.utc)
    event = EventModel(
        id="evt_test6",
        name="Test",
        body="",
        event_type=EventType.ERROR,
        scene_id="scene_1",
        gametime=0,
        walltime=now,
    )
    dumped = event.model_dump()
    assert dumped["event_type"] == "Error"
    assert "entity_type" not in dumped


def test_event_model_walltime_serialization():
    """walltime datetime serializes to ISO string in model_dump(mode='json')."""
    now = datetime.now(timezone.utc)
    event = EventModel(
        id="evt_test7",
        name="Test",
        event_type=EventType.CHAT_MESSAGE,
        scene_id="scene_1",
        gametime=0,
        walltime=now,
    )
    dumped = event.model_dump(mode="json")
    assert isinstance(dumped["walltime"], str)


def test_event_model_each_event_type():
    """EventModel can be instantiated with each EventType value."""
    now = datetime.now(timezone.utc)
    for et in EventType:
        event = EventModel(
            id=f"evt_{et.value}",
            name=f"Test {et.value}",
            event_type=et,
            scene_id="scene_1",
            gametime=0,
            walltime=now,
        )
        assert event.event_type == et


# --- Deleted Subclasses ---

def test_deleted_subclasses_not_importable():
    """ChatMessageModel, JoinEventModel, LeaveEventModel, FastForwardEventModel are removed."""
    import sidestage.models as m
    assert not hasattr(m, "ChatMessageModel")
    assert not hasattr(m, "JoinEventModel")
    assert not hasattr(m, "LeaveEventModel")
    assert not hasattr(m, "FastForwardEventModel")


# --- SceneModel Changes ---

def test_scene_model_no_messages_field():
    """SceneModel no longer has a 'messages' field."""
    scene = SceneModel(
        id="scene_1",
        name="Test Scene",
        body="",
    )
    assert "messages" not in SceneModel.model_fields


def test_scene_model_has_events_field():
    """SceneModel still has 'events' field (list of event IDs)."""
    scene = SceneModel(
        id="scene_1",
        name="Test Scene",
        body="",
        events=["evt_1", "evt_2"],
    )
    assert scene.events == ["evt_1", "evt_2"]


# --- CharacterModel Changes ---

def test_character_model_owner_default():
    """CharacterModel.owner defaults to 'npc'."""
    char = CharacterModel(id="char_1", name="Test", body="")
    assert char.owner == "npc"


def test_character_model_system_actor_default():
    """CharacterModel.system_actor defaults to False."""
    char = CharacterModel(id="char_1", name="Test", body="")
    assert char.system_actor is False


def test_character_model_player_owned():
    """CharacterModel with owner set to a user ID (player character)."""
    char = CharacterModel(id="char_1", name="Player", body="", owner="user-123")
    assert char.owner == "user-123"


def test_character_model_system_actor_true():
    """CharacterModel with system_actor=True (Co-Author character)."""
    char = CharacterModel(id="char_co_author", name="Co-Author", body="", system_actor=True)
    assert char.system_actor is True
