# Section 05: Validator

## Overview

This section implements `src/sidestage/migration/validator.py`, which performs referential integrity and schema validation on the output of `parse_directory()` (from `migration/parser.py`). The validator checks that all cross-references between entities and memories are consistent, required fields are present, and data-loss warnings are communicated. It returns a `MigrationValidationReport` model.

### Dependencies

- **section-01-data-models**: Provides `MigrationValidationIssue`, `MigrationValidationReport`, and `ParseResult` from `migration/models.py`
- **section-04-parser**: Provides `parse_directory()` from `migration/parser.py`, which returns a `ParseResult` containing parsed entities, memories, chat logs, and parse-level errors

Both must be implemented before this section.

### What This Section Produces

- **File**: `/home/harald/src/sidestage/src/sidestage/migration/validator.py`
- **Test file**: `/home/harald/src/sidestage/tests/unit/test_migration_validator.py`

---

## Tests (Write First)

Create `/home/harald/src/sidestage/tests/unit/test_migration_validator.py` with the following test stubs. Tests use `pytest` and build `ParseResult` objects directly (no filesystem interaction, no mocks). Each test constructs a minimal set of entities and/or memories to exercise a single validation check.

```python
"""Tests for migration/validator.py -- referential integrity and schema validation."""

import pytest

from sidestage.memory.models import Memory, MemoryType
from sidestage.migration.models import ParseResult
from sidestage.migration.validator import validate_parse_result
from sidestage.schemas import Character, Event, Item, Location, Scene


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
    ...


# --- Entity ID checks ---

def test_detects_duplicate_entity_ids():
    """Two entities with the same ID produce an error-severity issue."""
    ...


# --- Character reference checks ---

def test_detects_character_location_id_referencing_nonexistent_location():
    """Character.location_id pointing to a non-existent Location ID produces an error."""
    ...


def test_detects_character_inventory_referencing_nonexistent_item():
    """Character.inventory containing an Item ID that does not exist produces an error."""
    ...


# --- Location reference checks ---

def test_detects_location_connected_locations_referencing_nonexistent_location():
    """Location.connected_locations containing a non-existent Location ID produces an error."""
    ...


# --- Scene reference checks ---

def test_detects_scene_location_id_referencing_nonexistent_location():
    """Scene.location_id pointing to a non-existent Location ID produces an error."""
    ...


# --- Event reference checks ---

def test_detects_event_scene_id_referencing_nonexistent_scene():
    """Event.scene_id pointing to a non-existent Scene ID produces an error."""
    ...


# --- Required field checks ---

def test_detects_missing_required_entity_fields():
    """Entities missing 'id' or 'name' produce an error. (Pydantic may catch this at parse time;
    validator should still flag it if entity somehow has empty id/name.)"""
    ...


# --- Memory reference checks ---

def test_detects_memory_owner_id_referencing_nonexistent_entity():
    """Memory.owner_id set to a non-existent entity ID produces an error."""
    ...


def test_detects_memory_target_id_referencing_nonexistent_entity():
    """Memory.target_id set to a non-existent entity ID produces an error."""
    ...


def test_allows_memory_owner_id_null():
    """Memory with owner_id=None is valid (world facts may have no owner)."""
    ...


def test_detects_invalid_memory_type():
    """Memory with a memory_type not in the MemoryType enum produces an error.
    (Pydantic may catch this at parse time; the validator should catch it if the
    ParseResult contains a memory with a raw string memory_type somehow.)"""
    ...


def test_detects_missing_required_memory_fields():
    """Memories missing id, content, memory_type, or target_id produce errors.
    (These are Pydantic-required fields; the validator catches them as a fallback
    if they appear as empty strings.)"""
    ...


# --- Warning checks ---

def test_always_includes_data_loss_warning():
    """Every validation report includes a warning about data loss on import (embeddings
    will be regenerated, existing graph data will be dropped)."""
    ...


def test_distinguishes_errors_from_warnings():
    """Errors prevent import (valid=False); warnings are informational (valid can still be True)."""
    ...
```

### Key testing principles

- Build `ParseResult` objects directly in each test -- no filesystem, no mocking, no parser calls.
- Each test should exercise exactly one validation check (or one positive case).
- The `validate_parse_result()` function is synchronous (no async).
- Check both the `valid` field on the report and the contents of `errors` / `warnings` lists.
- For reference-error tests, assert that the `MigrationValidationIssue` contains the offending entity/memory ID and a human-readable message.

---

## Implementation Details

### File: `/home/harald/src/sidestage/src/sidestage/migration/validator.py`

The validator module provides a single top-level function `validate_parse_result()` that takes a `ParseResult` and returns a `MigrationValidationReport`.

### Function signature

```python
def validate_parse_result(parse_result: ParseResult) -> MigrationValidationReport:
    """Validate referential integrity and required fields in parsed campaign data.

    Checks:
    - Entity ID uniqueness
    - Character.location_id references valid Location
    - Character.inventory references valid Items
    - Location.connected_locations references valid Locations
    - Scene.location_id references valid Location
    - Event.scene_id references valid Scene
    - Required entity fields (id, name)
    - Memory.owner_id references valid entity (or is None)
    - Memory.target_id references valid entity
    - Memory has valid memory_type
    - Required memory fields (id, content, memory_type, target_id)
    - Always includes data-loss warning

    Args:
        parse_result: Output of parse_directory(), containing entities, memories, chatlogs, and parse-level errors.

    Returns:
        MigrationValidationReport with valid flag, counts, errors, and warnings.
    """
```

### Validation process (step by step)

**Step 1 -- Build lookup indices**

Build `dict[str, Entity]` keyed by entity ID from `parse_result.entities`. Also build type-specific sets for quick membership tests:

- `entity_ids: set[str]` -- all entity IDs
- `location_ids: set[str]` -- IDs of Location entities only
- `item_ids: set[str]` -- IDs of Item entities only
- `scene_ids: set[str]` -- IDs of Scene entities only

**Step 2 -- Check entity ID uniqueness**

Iterate through `parse_result.entities` and detect duplicates. If two entities share the same ID, emit an error-severity `MigrationValidationIssue` with `severity="error"`, the `entity_id` set to the duplicate ID, a descriptive `message` (e.g., `"Duplicate entity ID: {id}"`), and `file_path` set to `""` (the validator does not track file paths -- those come from the parser).

**Step 3 -- Check entity cross-references**

For each entity, check type-specific reference fields:

- **Character**: If `location_id` is not None, verify it exists in `location_ids`. If `inventory` is non-empty, verify each item ID exists in `item_ids`.
- **Location**: For each ID in `connected_locations`, verify it exists in `location_ids`.
- **Scene**: If `location_id` is not None, verify it exists in `location_ids`.
- **Event** (and subtypes ChatMessage, JoinEvent, LeaveEvent, FastForwardEvent): Verify `scene_id` exists in `scene_ids`.

Each failed check produces an error-severity issue.

**Step 4 -- Check required entity fields**

For each entity, verify that `id` and `name` are non-empty strings. While Pydantic models enforce these at construction time, the validator serves as a safety net for edge cases where entities might have been constructed with empty string values.

**Step 5 -- Check memory references**

For each memory in `parse_result.memories`:

- If `owner_id` is not None, verify it exists in `entity_ids`. If not, produce an error.
- Verify `target_id` exists in `entity_ids`. If not, produce an error.
- Verify `memory_type` is a valid `MemoryType` value (one of `"scene"`, `"character"`, `"world_fact"`). If not, produce an error.
- Verify required fields (`id`, `content`, `memory_type`, `target_id`) are present and non-empty. Produce an error for each missing/empty required field.

**Step 6 -- Add data-loss warning**

Always add a warning-severity `MigrationValidationIssue` with a message like `"Importing will drop the existing graph and regenerate all embeddings. This operation cannot be undone."`. This ensures the user sees a clear warning before confirming an import.

**Step 7 -- Carry forward parse errors**

Any errors already present in `parse_result.errors` (from the parser) should be included in the report. Convert each parse error string into a `MigrationValidationIssue` with `severity="error"` and `entity_id=None`.

**Step 8 -- Build and return the report**

Construct a `MigrationValidationReport`:

- `valid`: `True` if the `errors` list is empty, `False` otherwise. Warnings do not affect validity.
- `entities_found`: `len(parse_result.entities)`
- `memories_found`: `len(parse_result.memories)`
- `entity_counts`: A dict counting entities by type name (e.g., `{"Character": 2, "Location": 3, "Item": 1, "Scene": 1, "Event": 1}`). Use `type(entity).__name__` as the key.
- `errors`: All collected error-severity issues.
- `warnings`: All collected warning-severity issues.

### Type-checking helpers

Use `isinstance()` checks to dispatch type-specific validation:

```python
from sidestage.schemas import Character, Location, Scene, Event

if isinstance(entity, Character):
    # check location_id, inventory
elif isinstance(entity, Location):
    # check connected_locations
elif isinstance(entity, Scene):
    # check location_id
elif isinstance(entity, Event):
    # check scene_id (covers ChatMessage, JoinEvent, etc. since they inherit from Event)
```

Note that `Event` subclasses (ChatMessage, JoinEvent, LeaveEvent, FastForwardEvent) all inherit `scene_id` from `Event`, so the `isinstance(entity, Event)` check covers them all. Check `Event` after `Scene` to avoid false matches since both have `location_id` / `scene_id` but are different types.

### Imports needed

```python
from __future__ import annotations

from sidestage.memory.models import Memory, MemoryType
from sidestage.migration.models import (
    MigrationValidationIssue,
    MigrationValidationReport,
    ParseResult,
)
from sidestage.schemas import Character, Entity, Event, Location, Scene
```

### Data models referenced (from section-01-data-models)

The validator uses these models from `migration/models.py`:

```python
class MigrationValidationIssue(BaseModel):
    entity_id: str | None
    file_path: str
    severity: str          # "error" or "warning"
    message: str

class MigrationValidationReport(BaseModel):
    valid: bool
    entities_found: int
    memories_found: int
    entity_counts: dict[str, int]
    errors: list[MigrationValidationIssue]
    warnings: list[MigrationValidationIssue]
```

And the `ParseResult` model (also from `migration/models.py`):

```python
class ParseResult(BaseModel):
    entities: list[Entity]
    memories: list[Memory]
    chatlogs: dict[str, list[ChatMessage]]  # scene_id -> messages
    errors: list[str]
```

### The `MigrationValidationIssue.file_path` field

The validator does not have direct access to file paths (those are a parser concern). For issues created by the validator, set `file_path` to `""` (empty string). Parse-level errors carried forward from `ParseResult.errors` also use `file_path=""` since those are already plain string messages from the parser. If the `ParseResult` is later extended to carry file path information alongside errors, the validator can incorporate that.

### Edge cases to handle

1. **Empty `ParseResult`**: No entities, no memories. Should return `valid=True` with zero counts and only the data-loss warning.
2. **Character with `location_id=None`**: Valid -- no reference check needed for location.
3. **Character with empty `inventory` list**: Valid -- no reference checks needed.
4. **Location with empty `connected_locations`**: Valid -- no reference checks needed.
5. **Scene with `location_id=None`**: Valid -- scenes can exist without a location.
6. **Memory with `owner_id=None`**: Valid -- world facts may have no explicit owner.
7. **Duplicate entity IDs**: The validator reports all duplicates. It does not de-duplicate; that is the parser's responsibility (last-wins). The validator flags the situation for the user's awareness.
8. **Event subtypes**: All Event subclasses (ChatMessage, JoinEvent, LeaveEvent, FastForwardEvent) are checked via the `isinstance(entity, Event)` branch. The `scene_id` field is defined on the base `Event` class.
9. **Parse errors in `ParseResult.errors`**: These are already error-level issues from the parser (malformed YAML, missing frontmatter, etc.). They are included as errors in the validation report, which means `valid=False` if any parse errors exist.

### Relationship to existing code

- **`schemas.py`**: Provides the entity model hierarchy (`Entity`, `Character`, `Location`, `Item`, `Scene`, `Event` and subtypes). The validator uses `isinstance()` checks against these.
- **`memory/models.py`**: Provides `Memory` and `MemoryType`. The validator checks `memory_type` membership in `MemoryType`.
- **`migration/models.py`** (section-01): Provides all data models used by the validator (`ParseResult`, `MigrationValidationIssue`, `MigrationValidationReport`).
- **`migration/parser.py`** (section-04): Produces the `ParseResult` that is the sole input to the validator. The validator does not call the parser; it receives the already-parsed result.
- **`migration/importer.py`** (section-07, downstream): The importer calls `validate_parse_result()` before proceeding with the graph import. If `report.valid` is `False`, the import is aborted and the report is returned to the user.
