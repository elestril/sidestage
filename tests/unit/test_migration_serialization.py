"""Tests for migration/serialization.py -- canonical frontmatter serialization."""

import pytest

from sidestage.models import (
    CharacterModel,
    ChatMessageModel,
    EventModel,
    FastForwardEventModel,
    ItemModel,
    JoinEventModel,
    LeaveEventModel,
    LocationModel,
    SceneModel,
)
from sidestage.memory.models import Memory, MemoryType
from sidestage.migration.serialization import (
    entity_to_frontmatter_dict,
    frontmatter_dict_to_entity,
    memory_to_frontmatter_dict,
    frontmatter_dict_to_memory,
    sanitize_filename,
    entity_type_to_subdir,
    resolve_filename,
)


# --- entity_to_frontmatter_dict tests ---


def test_entity_to_frontmatter_dict_character_all_fields():
    """entity_to_frontmatter_dict returns (dict, body) for CharacterModel with all fields populated."""
    char = CharacterModel(
        id="char_eldric",
        name="Eldric the Bold",
        body="A brave warrior.",
        location_id="loc_tavern",
        inventory=["item_sword"],
        unseen=False,
    )
    fm, body = entity_to_frontmatter_dict(char)
    assert body == "A brave warrior."
    assert fm["name"] == "Eldric the Bold"
    assert fm["id"] == "char_eldric"
    assert fm["type"] == "Character"
    assert fm["location_id"] == "loc_tavern"
    assert fm["inventory"] == ["item_sword"]
    assert "body" not in fm


def test_entity_to_frontmatter_dict_location_with_connected():
    """entity_to_frontmatter_dict returns (dict, body) for LocationModel with connected_locations."""
    loc = LocationModel(
        id="loc_tavern",
        name="Rusty Tavern",
        body="A dingy tavern.",
        connected_locations=["loc_castle", "loc_square"],
    )
    fm, body = entity_to_frontmatter_dict(loc)
    assert fm["type"] == "Location"
    assert fm["connected_locations"] == ["loc_castle", "loc_square"]
    assert body == "A dingy tavern."


def test_entity_to_frontmatter_dict_item_minimal():
    """entity_to_frontmatter_dict returns (dict, body) for ItemModel with minimal fields."""
    item = ItemModel(id="item_sword", name="Sword", body="Sharp.")
    fm, body = entity_to_frontmatter_dict(item)
    assert fm["type"] == "Item"
    assert fm["id"] == "item_sword"
    assert body == "Sharp."


def test_entity_to_frontmatter_dict_scene_excludes_messages():
    """entity_to_frontmatter_dict excludes messages list from SceneModel frontmatter."""
    scene = SceneModel(
        id="scene_brawl",
        name="Tavern Brawl",
        body="A brawl breaks out.",
        location_id="loc_tavern",
        messages=[],
    )
    fm, body = entity_to_frontmatter_dict(scene)
    assert fm["type"] == "Scene"
    assert "messages" not in fm


def test_entity_to_frontmatter_dict_event_subtypes():
    """entity_to_frontmatter_dict handles ChatMessageModel and JoinEventModel subtypes."""
    chat = ChatMessageModel(
        id="evt_chat_1",
        name="Chat",
        body="",
        scene_id="scene_brawl",
        gametime=100,
        walltime="2026-01-15T14:30:00Z",
        character_id="char_eldric",
        message="Hello!",
    )
    fm, body = entity_to_frontmatter_dict(chat)
    assert fm["type"] == "ChatMessage"
    assert fm["character_id"] == "char_eldric"
    assert fm["message"] == "Hello!"

    join = JoinEventModel(
        id="evt_join_1",
        name="Join",
        body="",
        scene_id="scene_brawl",
        gametime=50,
        walltime="2026-01-15T14:29:00Z",
        actor_id="actor_1",
    )
    fm_j, body_j = entity_to_frontmatter_dict(join)
    assert fm_j["type"] == "JoinEvent"
    assert fm_j["actor_id"] == "actor_1"


def test_entity_to_frontmatter_dict_matches_model_dump_plus_type():
    """Frontmatter dict is identical to model_dump() + type, minus body."""
    char = CharacterModel(
        id="char_test",
        name="Test",
        body="Body text.",
        location_id="loc_1",
        inventory=["item_a"],
        unseen=True,
    )
    fm, body = entity_to_frontmatter_dict(char)
    expected = char.model_dump()
    expected.pop("body")
    expected["type"] = "Character"
    # Same key-value pairs, ignoring ordering
    assert dict(fm) == expected


def test_entity_to_frontmatter_dict_field_ordering():
    """Field ordering is deterministic: name, id, type first, then remaining."""
    char = CharacterModel(
        id="char_test",
        name="Test",
        body="Body.",
        location_id="loc_1",
        inventory=[],
    )
    fm, _ = entity_to_frontmatter_dict(char)
    keys = list(fm.keys())
    assert keys[0] == "name"
    assert keys[1] == "id"
    assert keys[2] == "type"


# --- frontmatter_dict_to_entity tests ---


def test_frontmatter_dict_to_entity_character():
    """frontmatter_dict_to_entity reconstructs CharacterModel from dict + body."""
    data = {
        "name": "Eldric",
        "id": "char_eldric",
        "type": "Character",
        "location_id": "loc_tavern",
        "inventory": ["item_sword"],
        "unseen": False,
    }
    entity = frontmatter_dict_to_entity(data, "A brave warrior.")
    assert isinstance(entity, CharacterModel)
    assert entity.name == "Eldric"
    assert entity.body == "A brave warrior."
    assert entity.location_id == "loc_tavern"


def test_frontmatter_dict_to_entity_location_connected():
    """frontmatter_dict_to_entity reconstructs LocationModel with connected_locations."""
    data = {
        "name": "Tavern",
        "id": "loc_tavern",
        "type": "Location",
        "connected_locations": ["loc_castle"],
    }
    entity = frontmatter_dict_to_entity(data, "A tavern.")
    assert isinstance(entity, LocationModel)
    assert entity.connected_locations == ["loc_castle"]


def test_frontmatter_dict_to_entity_infers_type_from_subdir():
    """When type field missing, infers from subdirectory hint."""
    data = {"name": "Sword", "id": "item_sword"}
    entity = frontmatter_dict_to_entity(data, "Sharp.", type_hint="items")
    assert isinstance(entity, ItemModel)


def test_frontmatter_dict_to_entity_raises_on_unknown_type():
    """Raises ValueError on unknown type string."""
    data = {"name": "X", "id": "x_1", "type": "UnknownType"}
    with pytest.raises((ValueError, KeyError)):
        frontmatter_dict_to_entity(data, "")


def test_frontmatter_dict_to_entity_raises_on_missing_required():
    """Raises on missing required fields (id, name)."""
    data = {"type": "Character"}  # missing name and id
    with pytest.raises(Exception):
        frontmatter_dict_to_entity(data, "body")


# --- memory_to_frontmatter_dict tests ---


def test_memory_to_frontmatter_dict_excludes_embedding():
    """memory_to_frontmatter_dict excludes embedding field."""
    mem = Memory(
        id="mem_1",
        content="A fact.",
        memory_type=MemoryType.WORLD_FACT,
        visibility="common",
        target_id="loc_tavern",
        embedding=[0.1, 0.2, 0.3],
    )
    fm, content = memory_to_frontmatter_dict(mem)
    assert "embedding" not in fm
    assert content == "A fact."


def test_memory_to_frontmatter_dict_includes_all_fields():
    """memory_to_frontmatter_dict includes all Memory fields except embedding and content."""
    mem = Memory(
        id="mem_2",
        content="Something happened.",
        memory_type=MemoryType.SCENE,
        visibility="private",
        owner_id="char_eldric",
        target_id="scene_brawl",
        gametime=3600,
        access_count=5,
    )
    fm, content = memory_to_frontmatter_dict(mem)
    assert fm["id"] == "mem_2"
    assert fm["memory_type"] == "scene"
    assert fm["visibility"] == "private"
    assert fm["owner_id"] == "char_eldric"
    assert fm["target_id"] == "scene_brawl"
    assert fm["gametime"] == 3600
    assert fm["access_count"] == 5
    assert "content" not in fm
    assert content == "Something happened."


def test_frontmatter_dict_to_memory_reconstructs():
    """frontmatter_dict_to_memory reconstructs Memory from dict + body."""
    data = {
        "id": "mem_1",
        "memory_type": "world_fact",
        "visibility": "common",
        "target_id": "loc_tavern",
        "owner_id": None,
        "gametime": None,
        "access_count": 0,
        "created_at": 1706000000.0,
        "updated_at": 1706000000.0,
    }
    mem = frontmatter_dict_to_memory(data, "A fact about the tavern.")
    assert isinstance(mem, Memory)
    assert mem.content == "A fact about the tavern."
    assert mem.memory_type == MemoryType.WORLD_FACT
    assert mem.embedding is None


def test_memory_roundtrip():
    """Full roundtrip: Memory -> frontmatter_dict -> Memory preserves all fields."""
    original = Memory(
        id="mem_rt",
        content="Roundtrip content.",
        memory_type=MemoryType.CHARACTER,
        visibility="private",
        owner_id="char_1",
        target_id="char_2",
        gametime=7200,
        access_count=3,
        created_at=1706000000.0,
        updated_at=1706001000.0,
    )
    fm, content = memory_to_frontmatter_dict(original)
    restored = frontmatter_dict_to_memory(fm, content)
    assert restored.id == original.id
    assert restored.content == original.content
    assert restored.memory_type == original.memory_type
    assert restored.visibility == original.visibility
    assert restored.owner_id == original.owner_id
    assert restored.target_id == original.target_id
    assert restored.gametime == original.gametime
    assert restored.access_count == original.access_count
    assert restored.embedding is None


# --- Full entity roundtrip tests ---


def test_entity_roundtrip_all_types():
    """Full roundtrip entity -> frontmatter_dict -> entity for all entity types."""
    entities = [
        CharacterModel(id="c1", name="C", body="B", location_id="l1", inventory=["i1"]),
        LocationModel(id="l1", name="L", body="B", connected_locations=["l2"]),
        ItemModel(id="i1", name="I", body="B"),
        SceneModel(id="s1", name="S", body="B", location_id="l1"),
        EventModel(id="e1", name="E", body="B", scene_id="s1", gametime=0, walltime="2026-01-01T00:00:00Z"),
        JoinEventModel(id="j1", name="J", body="B", scene_id="s1", gametime=0, walltime="2026-01-01T00:00:00Z", actor_id="a1"),
        LeaveEventModel(id="le1", name="Leave", body="B", scene_id="s1", gametime=0, walltime="2026-01-01T00:00:00Z", actor_id="a1"),
        FastForwardEventModel(id="ff1", name="FF", body="B", scene_id="s1", gametime=0, walltime="2026-01-01T00:00:00Z", duration_str="2 hours"),
        ChatMessageModel(id="cm1", name="Chat", body="B", scene_id="s1", gametime=0, walltime="2026-01-01T00:00:00Z", character_id="c1", message="Hello"),
    ]
    for original in entities:
        fm, body = entity_to_frontmatter_dict(original)
        restored = frontmatter_dict_to_entity(fm, body)
        assert type(restored) is type(original)
        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.body == original.body


# --- Filename sanitization tests ---


def test_sanitize_filename_replaces_special_chars():
    """Special characters replaced with underscore."""
    assert sanitize_filename("Hello World!") == "Hello_World"


def test_sanitize_filename_collapses_multiple_underscores():
    """Multiple consecutive underscores collapse to one."""
    assert sanitize_filename("a  b!!c") == "a_b_c"


def test_sanitize_filename_preserves_hyphens_and_underscores():
    """Hyphens and underscores pass through."""
    assert sanitize_filename("my-entity_name") == "my-entity_name"


def test_sanitize_filename_handles_empty_string():
    """Empty string produces a fallback name."""
    result = sanitize_filename("")
    assert len(result) > 0  # Should not be empty


# --- entity_type_to_subdir tests ---


def test_entity_type_to_subdir_mapping():
    """Maps entity type names to correct subdirectories."""
    assert entity_type_to_subdir("Character") == "characters"
    assert entity_type_to_subdir("Location") == "locations"
    assert entity_type_to_subdir("Item") == "items"
    assert entity_type_to_subdir("Scene") == "scenes"
    assert entity_type_to_subdir("Event") == "events"


def test_entity_type_to_subdir_event_subtypes():
    """EventModel subtypes all map to events/."""
    assert entity_type_to_subdir("ChatMessage") == "events"
    assert entity_type_to_subdir("JoinEvent") == "events"
    assert entity_type_to_subdir("LeaveEvent") == "events"
    assert entity_type_to_subdir("FastForwardEvent") == "events"


# --- resolve_filename tests ---


def test_resolve_filename_no_collision():
    """Returns original name when no collision."""
    used: set[str] = set()
    result = resolve_filename("MyEntity", used)
    assert result == "MyEntity"


def test_resolve_filename_appends_suffix_on_collision():
    """Appends _2, _3 on collision."""
    used = {"MyEntity"}
    result = resolve_filename("MyEntity", used)
    assert result == "MyEntity_2"

    used.add("MyEntity_2")
    result = resolve_filename("MyEntity", used)
    assert result == "MyEntity_3"
