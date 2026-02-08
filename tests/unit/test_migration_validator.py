"""Tests for migration/validator.py -- referential integrity and schema validation."""

import pytest

from sidestage.memory.models import Memory, MemoryType
from sidestage.migration.models import ParseResult
from sidestage.migration.validator import validate_parse_result
from sidestage.migration.models import MigrationValidationIssue
from sidestage.schemas import Character, ChatMessage, Event, Item, Location, Scene


# --- Fixtures ---


@pytest.fixture
def valid_location():
    """A Location with all required fields."""
    return Location(id="loc_tavern", name="The Rusty Tavern", body="A dusty old tavern.", connected_locations=["loc_castle"])


@pytest.fixture
def valid_location_2():
    """A second Location for connectivity tests."""
    return Location(id="loc_castle", name="Castle Blackmoor", body="A dark foreboding castle.", connected_locations=["loc_tavern"])


@pytest.fixture
def valid_character(valid_location):
    """A Character at a valid location with a valid inventory item."""
    return Character(
        id="char_eldric", name="Eldric", body="A brave warrior.",
        location_id="loc_tavern", inventory=["item_sword"],
    )


@pytest.fixture
def valid_item():
    """An Item with all required fields."""
    return Item(id="item_sword", name="Flame Tongue Sword", body="A magical sword.")


@pytest.fixture
def valid_scene(valid_location):
    """A Scene at a valid location."""
    return Scene(id="scene_brawl", name="Tavern Brawl", body="A brawl breaks out.", location_id="loc_tavern")


@pytest.fixture
def valid_event(valid_scene):
    """An Event in a valid scene."""
    return Event(id="evt_join", name="Eldric Joins", body="Eldric enters the fray.",
                 scene_id="scene_brawl", gametime=3600, walltime="2026-01-15T14:30:00Z")


@pytest.fixture
def valid_memory():
    """A Memory with valid owner and target references."""
    return Memory(id="mem_1", content="A memory.", memory_type=MemoryType.SCENE,
                  visibility="common", owner_id="char_eldric", target_id="scene_brawl")


@pytest.fixture
def valid_parse_result(valid_character, valid_location, valid_location_2, valid_item, valid_scene, valid_event, valid_memory):
    """A fully valid ParseResult with consistent references."""
    return ParseResult(
        entities=[valid_character, valid_location, valid_location_2, valid_item, valid_scene, valid_event],
        memories=[valid_memory],
        chatlogs={},
        errors=[],
    )


# --- Validation success tests ---

def test_validates_successfully_with_correct_references(valid_parse_result):
    """validate_parse_result returns a report with valid=True and no errors when all references are consistent."""
    report = validate_parse_result(valid_parse_result)
    assert report.valid is True
    assert len(report.errors) == 0
    assert report.entities_found == 6
    assert report.memories_found == 1
    assert report.entity_counts["Character"] == 1
    assert report.entity_counts["Location"] == 2
    assert report.entity_counts["Item"] == 1
    assert report.entity_counts["Scene"] == 1
    assert report.entity_counts["Event"] == 1


# --- Entity ID checks ---

def test_detects_duplicate_entity_ids():
    """Two entities with the same ID produce an error-severity issue."""
    loc1 = Location(id="loc_dup", name="Place A", body="A place.")
    loc2 = Location(id="loc_dup", name="Place B", body="Another place.")
    pr = ParseResult(entities=[loc1, loc2], memories=[], chatlogs={}, errors=[])
    report = validate_parse_result(pr)
    assert report.valid is False
    error_messages = [e.message for e in report.errors]
    assert any("loc_dup" in m for m in error_messages)


# --- Character reference checks ---

def test_detects_character_location_id_referencing_nonexistent_location():
    """Character.location_id pointing to a non-existent Location ID produces an error."""
    char = Character(id="char_1", name="Hero", body="A hero.", location_id="loc_nowhere")
    pr = ParseResult(entities=[char], memories=[], chatlogs={}, errors=[])
    report = validate_parse_result(pr)
    assert report.valid is False
    assert any("loc_nowhere" in e.message for e in report.errors)
    assert any(e.entity_id == "char_1" for e in report.errors)


def test_detects_character_inventory_referencing_nonexistent_item():
    """Character.inventory containing an Item ID that does not exist produces an error."""
    char = Character(id="char_1", name="Hero", body="A hero.", inventory=["item_ghost"])
    pr = ParseResult(entities=[char], memories=[], chatlogs={}, errors=[])
    report = validate_parse_result(pr)
    assert report.valid is False
    assert any("item_ghost" in e.message for e in report.errors)


# --- Location reference checks ---

def test_detects_location_connected_locations_referencing_nonexistent_location():
    """Location.connected_locations containing a non-existent Location ID produces an error."""
    loc = Location(id="loc_1", name="Place", body="A place.", connected_locations=["loc_missing"])
    pr = ParseResult(entities=[loc], memories=[], chatlogs={}, errors=[])
    report = validate_parse_result(pr)
    assert report.valid is False
    assert any("loc_missing" in e.message for e in report.errors)


# --- Scene reference checks ---

def test_detects_scene_location_id_referencing_nonexistent_location():
    """Scene.location_id pointing to a non-existent Location ID produces an error."""
    scene = Scene(id="scene_1", name="Scene", body="A scene.", location_id="loc_void")
    pr = ParseResult(entities=[scene], memories=[], chatlogs={}, errors=[])
    report = validate_parse_result(pr)
    assert report.valid is False
    assert any("loc_void" in e.message for e in report.errors)


# --- Event reference checks ---

def test_detects_event_scene_id_referencing_nonexistent_scene():
    """Event.scene_id pointing to a non-existent Scene ID produces an error."""
    evt = Event(id="evt_1", name="Event", body="An event.", scene_id="scene_gone", gametime=0, walltime="2026-01-01T00:00:00Z")
    pr = ParseResult(entities=[evt], memories=[], chatlogs={}, errors=[])
    report = validate_parse_result(pr)
    assert report.valid is False
    assert any("scene_gone" in e.message for e in report.errors)


def test_detects_chat_message_scene_id_referencing_nonexistent_scene():
    """ChatMessage (Event subtype) with bad scene_id triggers an error via isinstance(Event) check."""
    msg = ChatMessage(
        id="msg_1", name="Message", body="Hello.", scene_id="scene_missing",
        gametime=0, walltime="2026-01-01T00:00:00Z",
        character_id="char_1", message="Hello.",
    )
    pr = ParseResult(entities=[msg], memories=[], chatlogs={}, errors=[])
    report = validate_parse_result(pr)
    assert report.valid is False
    assert any("scene_missing" in e.message for e in report.errors)


# --- Required field checks ---

def test_detects_missing_required_entity_fields():
    """Entities with empty id or name produce an error."""
    loc = Location(id="", name="Place", body="A place.")
    pr = ParseResult(entities=[loc], memories=[], chatlogs={}, errors=[])
    report = validate_parse_result(pr)
    assert report.valid is False
    assert any("id" in e.message.lower() for e in report.errors)


def test_detects_empty_entity_name():
    """Entity with empty name produces an error."""
    loc = Location(id="loc_1", name="", body="A place.")
    pr = ParseResult(entities=[loc], memories=[], chatlogs={}, errors=[])
    report = validate_parse_result(pr)
    assert report.valid is False
    assert any("name" in e.message.lower() for e in report.errors)


# --- Memory reference checks ---

def test_detects_memory_owner_id_referencing_nonexistent_entity():
    """Memory.owner_id set to a non-existent entity ID produces an error."""
    loc = Location(id="loc_1", name="Place", body="A place.")
    mem = Memory(id="mem_1", content="A memory.", memory_type=MemoryType.SCENE,
                 visibility="common", owner_id="char_nobody", target_id="loc_1")
    pr = ParseResult(entities=[loc], memories=[mem], chatlogs={}, errors=[])
    report = validate_parse_result(pr)
    assert report.valid is False
    assert any("char_nobody" in e.message for e in report.errors)


def test_detects_memory_target_id_referencing_nonexistent_entity():
    """Memory.target_id set to a non-existent entity ID produces an error."""
    loc = Location(id="loc_1", name="Place", body="A place.")
    mem = Memory(id="mem_1", content="A memory.", memory_type=MemoryType.SCENE,
                 visibility="common", owner_id="loc_1", target_id="entity_missing")
    pr = ParseResult(entities=[loc], memories=[mem], chatlogs={}, errors=[])
    report = validate_parse_result(pr)
    assert report.valid is False
    assert any("entity_missing" in e.message for e in report.errors)


def test_allows_memory_owner_id_null():
    """Memory with owner_id=None is valid (world facts may have no owner)."""
    loc = Location(id="loc_1", name="Place", body="A place.")
    mem = Memory(id="mem_1", content="A memory.", memory_type=MemoryType.WORLD_FACT,
                 visibility="common", owner_id=None, target_id="loc_1")
    pr = ParseResult(entities=[loc], memories=[mem], chatlogs={}, errors=[])
    report = validate_parse_result(pr)
    assert report.valid is True
    assert len(report.errors) == 0


def test_detects_invalid_memory_type():
    """Memory with an invalid memory_type string produces an error.
    Since Pydantic enforces MemoryType at construction, we test by injecting
    a raw dict memory with a bad type into the parse result."""
    loc = Location(id="loc_1", name="Place", body="A place.")
    # Build a memory-like object with an invalid type by bypassing Pydantic
    mem = Memory.model_construct(
        id="mem_1", content="A memory.", memory_type="invalid_type",
        visibility="common", owner_id=None, target_id="loc_1",
    )
    pr = ParseResult(entities=[loc], memories=[mem], chatlogs={}, errors=[])
    report = validate_parse_result(pr)
    assert report.valid is False
    assert any("memory_type" in e.message.lower() for e in report.errors)


def test_detects_missing_required_memory_fields():
    """Memories with empty id, content, or target_id produce errors."""
    loc = Location(id="loc_1", name="Place", body="A place.")
    mem = Memory.model_construct(
        id="", content="", memory_type=MemoryType.SCENE,
        visibility="common", owner_id=None, target_id="",
    )
    pr = ParseResult(entities=[loc], memories=[mem], chatlogs={}, errors=[])
    report = validate_parse_result(pr)
    assert report.valid is False
    # Should flag empty id, content, and target_id
    assert len([e for e in report.errors if e.severity == "error"]) >= 3


# --- Warning checks ---

def test_empty_parse_result_is_valid_with_zero_counts():
    """Empty ParseResult returns valid=True with zero counts and only the data-loss warning."""
    pr = ParseResult(entities=[], memories=[], chatlogs={}, errors=[])
    report = validate_parse_result(pr)
    assert report.valid is True
    assert report.entities_found == 0
    assert report.memories_found == 0
    assert report.entity_counts == {}
    assert len(report.errors) == 0
    assert len(report.warnings) >= 1


def test_parse_errors_carried_forward_make_report_invalid():
    """Pre-existing errors in ParseResult.errors appear in the report and set valid=False."""
    parse_error = MigrationValidationIssue(
        entity_id=None, file_path="bad_file.md", severity="error",
        message="Malformed YAML frontmatter",
    )
    pr = ParseResult(entities=[], memories=[], chatlogs={}, errors=[parse_error])
    report = validate_parse_result(pr)
    assert report.valid is False
    assert any("Malformed YAML" in e.message for e in report.errors)


def test_always_includes_data_loss_warning():
    """Every validation report includes a warning about data loss on import."""
    pr = ParseResult(entities=[], memories=[], chatlogs={}, errors=[])
    report = validate_parse_result(pr)
    assert len(report.warnings) >= 1
    assert any("cannot be undone" in w.message.lower() or "data" in w.message.lower() for w in report.warnings)


def test_distinguishes_errors_from_warnings():
    """Errors prevent import (valid=False); warnings are informational (valid can still be True)."""
    # Valid parse result with no errors should have warnings but still be valid
    pr = ParseResult(entities=[], memories=[], chatlogs={}, errors=[])
    report = validate_parse_result(pr)
    assert report.valid is True
    assert len(report.warnings) >= 1

    # Parse result with a reference error should be invalid
    char = Character(id="char_1", name="Hero", body="A hero.", location_id="loc_nonexistent")
    pr2 = ParseResult(entities=[char], memories=[], chatlogs={}, errors=[])
    report2 = validate_parse_result(pr2)
    assert report2.valid is False
    assert len(report2.errors) >= 1
