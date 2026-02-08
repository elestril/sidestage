# Section 04: Parser

## Overview

This section implements `src/sidestage/migration/parser.py`, which reads the `markdown/` directory tree, parses entity and memory markdown files using the canonical serialization functions from `migration/serialization.py`, associates memories with parent entities via `.d/` companion directory naming, and handles chat log files. It produces a `ParseResult` containing all parsed entities, memories, chat logs, and any errors or warnings encountered during parsing.

### Dependencies

- **section-01-data-models**: Provides `ParseResult` from `migration/models.py`. The `ParseResult` model holds the parsed entities, memories, chat logs, and lists of errors/warnings.
- **section-02-serialization**: Provides `frontmatter_dict_to_entity()` and `frontmatter_dict_to_memory()` from `migration/serialization.py`. Also provides filename/directory utility functions like `entity_type_to_subdir()`.

Both must be implemented before this section.

### What This Section Produces

- **File**: `/home/harald/src/sidestage/src/sidestage/migration/parser.py`
- **Test file**: `/home/harald/src/sidestage/tests/unit/test_migration_parser.py`

---

## Tests (Write First)

Create `/home/harald/src/sidestage/tests/unit/test_migration_parser.py` with the following test stubs. Tests use `pytest` and the `tmp_path` fixture for filesystem isolation. No FalkorDB or external services are needed -- the parser operates purely on local files.

```python
"""Tests for migration/parser.py -- parse markdown directory tree into models."""

from pathlib import Path

import pytest
import yaml

from sidestage.migration.parser import parse_directory


# --- Helper to write a markdown file with YAML frontmatter ---

def _write_md(path: Path, frontmatter: dict, body: str = "") -> None:
    """Write a markdown file with YAML frontmatter and body."""
    fm = yaml.dump(frontmatter, sort_keys=False).strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{fm}\n---\n\n{body}")


def _write_chatlog(path: Path, lines: list[str]) -> None:
    """Write a chatlog.log file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


# --- Fixtures ---

@pytest.fixture
def markdown_dir(tmp_path: Path) -> Path:
    """Return an empty markdown/ directory with type subdirectories."""
    md = tmp_path / "markdown"
    for subdir in ("characters", "locations", "items", "scenes", "events"):
        (md / subdir).mkdir(parents=True)
    return md


@pytest.fixture
def populated_dir(markdown_dir: Path) -> Path:
    """Return a markdown/ directory with sample entities and memories."""
    # Character with body
    _write_md(
        markdown_dir / "characters" / "Eldric_the_Bold.md",
        {"name": "Eldric the Bold", "id": "char_eldric", "type": "Character",
         "location_id": "loc_tavern", "inventory": ["item_sword"], "unseen": False},
        body="A brave warrior.",
    )
    # Character memory in .d/
    _write_md(
        markdown_dir / "characters" / "Eldric_the_Bold.d" / "mem_tavern_brawl.md",
        {"id": "mem_tavern_brawl", "memory_type": "scene", "visibility": "private",
         "owner_id": "char_eldric", "target_id": "scene_brawl",
         "gametime": 3600, "created_at": 1706000000.0, "updated_at": 1706000000.0,
         "access_count": 0},
        body="Eldric saw a fierce brawl.",
    )
    # Location
    _write_md(
        markdown_dir / "locations" / "The_Rusty_Tavern.md",
        {"name": "The Rusty Tavern", "id": "loc_tavern", "type": "Location",
         "connected_locations": ["loc_castle", "loc_square"]},
        body="A dimly lit tavern.",
    )
    # Scene with chatlog
    _write_md(
        markdown_dir / "scenes" / "Tavern_Brawl.md",
        {"name": "Tavern Brawl", "id": "scene_brawl", "type": "Scene",
         "location_id": "loc_tavern"},
        body="A chaotic brawl erupts.",
    )
    _write_chatlog(
        markdown_dir / "scenes" / "Tavern_Brawl.d" / "chatlog.log",
        [
            '[2026-01-15T14:30:00Z] (char_eldric) Eldric: "I challenge you!"',
            '[2026-01-15T14:30:05Z] (char_alice) Alice: "You\'ll regret that."',
        ],
    )
    # Item
    _write_md(
        markdown_dir / "items" / "Flame_Tongue_Sword.md",
        {"name": "Flame Tongue Sword", "id": "item_sword", "type": "Item"},
        body="A sword wreathed in flame.",
    )
    # Event (JoinEvent subtype)
    _write_md(
        markdown_dir / "events" / "Eldric_Joins_Brawl.md",
        {"name": "Eldric Joins Brawl", "id": "evt_join_1", "type": "JoinEvent",
         "scene_id": "scene_brawl", "gametime": 3600,
         "walltime": "2026-01-15T14:30:00Z", "actor_id": "actor_1"},
        body="Eldric enters the fray.",
    )
    return markdown_dir


# --- Core parsing tests ---

def test_parse_directory_reads_all_entity_types(populated_dir):
    """parse_directory finds entities from all type subdirectories."""
    result = parse_directory(populated_dir)
    entity_types = {type(e).__name__ for e in result.entities}
    assert "Character" in entity_types
    assert "Location" in entity_types
    assert "Item" in entity_types
    assert "Scene" in entity_types
    assert "JoinEvent" in entity_types


def test_parse_directory_reads_memories_from_dot_d(populated_dir):
    """parse_directory reads memory files from .d/ companion directories."""
    result = parse_directory(populated_dir)
    assert len(result.memories) >= 1
    mem_ids = {m.id for m in result.memories}
    assert "mem_tavern_brawl" in mem_ids


def test_parse_directory_reads_chatlog_from_scene_dot_d(populated_dir):
    """parse_directory reads chatlog.log from scene .d/ directories."""
    result = parse_directory(populated_dir)
    assert "scene_brawl" in result.chatlogs
    assert len(result.chatlogs["scene_brawl"]) == 2


def test_parse_directory_associates_memories_with_parent_entity(populated_dir):
    """Memories parsed from entity_name.d/ are associated with that entity."""
    result = parse_directory(populated_dir)
    # The memory in Eldric_the_Bold.d/ should have owner_id = char_eldric
    mem = next(m for m in result.memories if m.id == "mem_tavern_brawl")
    assert mem.owner_id == "char_eldric"


def test_parse_directory_infers_type_from_subdirectory(markdown_dir):
    """When type field is missing from frontmatter, infer from subdirectory name."""
    _write_md(
        markdown_dir / "characters" / "No_Type.md",
        {"name": "No Type", "id": "char_no_type", "unseen": False},
        body="A character without explicit type.",
    )
    result = parse_directory(markdown_dir)
    entity = next(e for e in result.entities if e.id == "char_no_type")
    assert type(entity).__name__ == "Character"
    # Should also produce a warning
    assert any("type" in w.message.lower() for w in result.warnings)


def test_parse_directory_warns_orphaned_dot_d(markdown_dir):
    """Warn on .d/ without parent .md (orphaned memories)."""
    orphan_dir = markdown_dir / "characters" / "Ghost.d"
    _write_md(
        orphan_dir / "mem_orphan.md",
        {"id": "mem_orphan", "memory_type": "scene", "visibility": "common",
         "owner_id": None, "target_id": "char_ghost",
         "created_at": 1706000000.0, "updated_at": 1706000000.0, "access_count": 0},
        body="An orphan memory.",
    )
    result = parse_directory(markdown_dir)
    assert any("orphan" in w.message.lower() for w in result.warnings)


def test_parse_directory_warns_chatlog_in_non_scene_dot_d(markdown_dir):
    """Warn on chatlog.log in a non-scene .d/ directory (ignored)."""
    _write_md(
        markdown_dir / "characters" / "Char_With_Log.md",
        {"name": "Char With Log", "id": "char_log", "type": "Character", "unseen": False},
        body="A character.",
    )
    _write_chatlog(
        markdown_dir / "characters" / "Char_With_Log.d" / "chatlog.log",
        ["[2026-01-15T14:30:00Z] (char_log) Char: \"Hello\""],
    )
    result = parse_directory(markdown_dir)
    assert any("chatlog" in w.message.lower() for w in result.warnings)
    assert "char_log" not in result.chatlogs


def test_parse_directory_handles_malformed_yaml(markdown_dir):
    """Malformed YAML produces an error in ParseResult, not an exception."""
    bad_file = markdown_dir / "characters" / "Bad_Yaml.md"
    bad_file.write_text("---\n: invalid: yaml: {{{\n---\n\nBody text.")
    result = parse_directory(markdown_dir)
    assert len(result.errors) >= 1
    assert any("Bad_Yaml" in e.file_path for e in result.errors)


def test_parse_directory_handles_missing_frontmatter(markdown_dir):
    """File without frontmatter delimiters produces an error."""
    bad_file = markdown_dir / "characters" / "No_Frontmatter.md"
    bad_file.write_text("Just a plain markdown file with no frontmatter.")
    result = parse_directory(markdown_dir)
    assert len(result.errors) >= 1
    assert any("No_Frontmatter" in e.file_path for e in result.errors)


def test_parse_directory_warns_duplicate_entity_ids(markdown_dir):
    """Duplicate entity IDs produce a warning; last-wins."""
    _write_md(
        markdown_dir / "characters" / "First.md",
        {"name": "First", "id": "char_dup", "type": "Character", "unseen": False},
        body="First character.",
    )
    _write_md(
        markdown_dir / "characters" / "Second.md",
        {"name": "Second", "id": "char_dup", "type": "Character", "unseen": False},
        body="Second character (same ID).",
    )
    result = parse_directory(markdown_dir)
    dup_entities = [e for e in result.entities if e.id == "char_dup"]
    assert len(dup_entities) == 1  # last-wins deduplication
    assert any("duplicate" in w.message.lower() for w in result.warnings)


def test_parse_directory_ignores_scene_messages_in_frontmatter(markdown_dir):
    """Scene.messages in frontmatter is ignored; messages come from chatlog.log."""
    _write_md(
        markdown_dir / "scenes" / "Scene_With_Messages.md",
        {"name": "Scene With Messages", "id": "scene_msg", "type": "Scene",
         "messages": [{"name": "msg", "id": "msg_1", "body": "", "scene_id": "scene_msg",
                        "gametime": 0, "walltime": "2026-01-01T00:00:00Z",
                        "character_id": "c1", "message": "hello"}]},
        body="A scene.",
    )
    result = parse_directory(markdown_dir)
    scene = next(e for e in result.entities if e.id == "scene_msg")
    # messages should be empty (stripped from frontmatter before entity construction)
    assert len(scene.messages) == 0


def test_parse_directory_handles_empty_directory(markdown_dir):
    """Empty directory tree (no entities) returns empty ParseResult with no errors."""
    result = parse_directory(markdown_dir)
    assert len(result.entities) == 0
    assert len(result.memories) == 0
    assert len(result.chatlogs) == 0
    assert len(result.errors) == 0


def test_parse_directory_handles_missing_type_subdirectories(tmp_path):
    """Missing type subdirectories are handled gracefully (no crash)."""
    md = tmp_path / "markdown"
    md.mkdir()
    # Only create one subdirectory
    (md / "characters").mkdir()
    result = parse_directory(md)
    assert len(result.entities) == 0
    assert len(result.errors) == 0
```

### Key testing principles

- All tests are synchronous since the parser does pure filesystem I/O (no async needed).
- Tests write real files to `tmp_path` and call `parse_directory()` to verify the output `ParseResult`.
- The `_write_md` helper creates properly formatted YAML frontmatter + body markdown files.
- Edge case tests (malformed YAML, missing frontmatter, duplicate IDs, orphaned `.d/`) each verify that the appropriate error or warning is recorded in the `ParseResult` rather than raising an exception.
- The parser should never raise exceptions for bad input -- it should always return a `ParseResult` with errors/warnings.

---

## Implementation Details

### File: `/home/harald/src/sidestage/src/sidestage/migration/parser.py`

The parser module provides a single top-level function `parse_directory()` that reads a `markdown/` directory tree and returns a `ParseResult` containing all parsed data.

### ParseResult model (from section-01-data-models)

The `ParseResult` model is defined in `migration/models.py` (section-01). It should have at minimum:

```python
class ParseResult(BaseModel):
    entities: list[Entity]
    memories: list[Memory]
    chatlogs: dict[str, list[str]]  # scene_id -> list of chatlog lines
    errors: list[MigrationValidationIssue]
    warnings: list[MigrationValidationIssue]
```

Where `entities` is a list of Pydantic entity objects (`Character`, `Location`, `Item`, `Scene`, `Event`, and Event subtypes), `memories` is a list of `Memory` objects, `chatlogs` maps scene entity IDs to their chat log lines, and `errors`/`warnings` are structured issues using the `MigrationValidationIssue` model.

### Function signature

```python
def parse_directory(markdown_dir: Path) -> ParseResult:
    """Parse the markdown/ directory tree into entities, memories, and chat logs.

    Reads all type subdirectories (characters/, locations/, items/, scenes/,
    events/), parses .md files as entities, reads .d/ companion directories
    for memories and chat logs.

    Args:
        markdown_dir: Path to the markdown/ directory.

    Returns:
        ParseResult with parsed entities, memories, chatlogs, and any
        errors/warnings encountered during parsing. Never raises exceptions
        for bad input -- all issues are reported in the result.
    """
```

### Parse process (step by step)

**Step 1 -- Iterate type subdirectories**

Define a mapping from subdirectory name to the expected entity type string:

```python
SUBDIR_TO_TYPE: dict[str, str] = {
    "characters": "Character",
    "locations": "Location",
    "items": "Item",
    "scenes": "Scene",
    "events": "Event",
}
```

For each subdirectory in `SUBDIR_TO_TYPE`:
1. Check if `markdown_dir / subdir_name` exists. If not, skip it gracefully (no error).
2. Iterate all `.md` files in the subdirectory (not recursive -- only top-level files).
3. Parse each file (see Step 2).

**Step 2 -- Parse entity files**

For each `.md` file in a type subdirectory:

1. Read the file content as text.
2. Split into YAML frontmatter and markdown body using a regex pattern:
   ```python
   pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
   ```
   This is the same pattern used in the existing `markdown_to_entity()` function in `entities.py`.
3. If no frontmatter match: record an error in `ParseResult.errors` with the file path and message "Missing YAML frontmatter". Continue to next file.
4. Parse the YAML using `yaml.safe_load()`. If parsing fails: record an error with "Malformed YAML" and the exception message. Continue.
5. Check for `type` field in frontmatter:
   - If present: use it as-is.
   - If missing: infer from the subdirectory name using `SUBDIR_TO_TYPE`. Record a warning: "Type field missing, inferred as {type} from subdirectory."
6. **Strip `messages` from Scene frontmatter**: If the entity type is `Scene` and `messages` is present in the frontmatter dict, remove it before constructing the entity. Messages come from `chatlog.log`, not from the frontmatter.
7. Call `frontmatter_dict_to_entity(data, body)` from `migration/serialization.py` to reconstruct the entity. If this raises an exception (e.g., missing required fields, unknown type), record an error and continue.
8. Check for duplicate entity IDs: maintain a `seen_ids: dict[str, str]` mapping from entity ID to file path. If the ID was already seen:
   - Record a warning: "Duplicate entity ID '{id}', previously in {prev_file}. Last-wins."
   - Replace the previous entity in the result list.
9. Track the entity file stem to entity ID mapping for `.d/` association: `stem_to_entity_id[file.stem] = entity.id`.

**Step 3 -- Parse companion directories (.d/)**

After all entity files are parsed, iterate the type subdirectories again looking for `.d/` directories:

1. For each directory entry in a type subdirectory that ends with `.d`:
   - Extract the stem: `dir_name[:-2]` (strip `.d`).
   - Look up the corresponding entity ID from `stem_to_entity_id`.
   - If no matching entity file exists: record a warning "Orphaned .d/ directory: {dir_name} has no matching entity file." Still parse the contents.
2. Parse `.md` files inside the `.d/` directory as memories (see Step 4).
3. If `chatlog.log` exists in the `.d/` directory:
   - Determine whether the parent entity is a Scene. Look up the entity from `stem_to_entity_id` and check its type.
   - If the parent is a Scene: read the file and store the lines in `chatlogs[entity_id]`.
   - If the parent is NOT a Scene: record a warning "chatlog.log found in non-scene .d/ directory '{dir_name}', ignoring."

**Step 4 -- Parse memory files**

For each `.md` file in a `.d/` directory:

1. Read and split into frontmatter + body (same as entity parsing).
2. If frontmatter parsing fails: record an error, continue.
3. Call `frontmatter_dict_to_memory(data, body)` from `migration/serialization.py` to reconstruct the `Memory` object. If this raises: record an error, continue.
4. Add the memory to `ParseResult.memories`.

**Step 5 -- Return ParseResult**

Assemble and return the `ParseResult` with all collected entities, memories, chatlogs, errors, and warnings.

### Internal helper functions

The module should define helpers to keep `parse_directory()` readable:

```python
def _parse_frontmatter(content: str, file_path: str) -> tuple[dict, str] | None:
    """Split markdown content into (frontmatter_dict, body).

    Returns None if the content has no valid frontmatter. Error details
    should be handled by the caller.
    """
    ...

def _parse_entity_file(
    file_path: Path,
    subdir_type: str,
    errors: list[MigrationValidationIssue],
    warnings: list[MigrationValidationIssue],
) -> Entity | None:
    """Parse a single entity .md file.

    Returns the entity on success, None on failure (error recorded).
    """
    ...

def _parse_memory_file(
    file_path: Path,
    errors: list[MigrationValidationIssue],
) -> Memory | None:
    """Parse a single memory .md file from a .d/ directory.

    Returns the Memory on success, None on failure (error recorded).
    """
    ...

def _read_chatlog(file_path: Path) -> list[str]:
    """Read chatlog.log and return non-empty lines."""
    ...
```

### Chat log format

The parser reads `chatlog.log` files and stores the raw lines. The format is:

```
[2026-01-15T14:30:00Z] (char_john) John: "I challenge you to a duel!"
[2026-01-15T14:30:05Z] (char_alice) Alice: "You'll regret that."
```

The parser does not parse the chat log lines into structured data -- it stores them as raw strings in `ParseResult.chatlogs[scene_id]`. The importer (section-07) is responsible for converting these lines back into `ChatMessage` objects. This keeps the parser simple and focused on I/O.

### Type inference from subdirectory

When the `type` field is missing from frontmatter, the parser infers it from the subdirectory name:

| Subdirectory | Inferred Type |
|---|---|
| `characters/` | `Character` |
| `locations/` | `Location` |
| `items/` | `Item` |
| `scenes/` | `Scene` |
| `events/` | `Event` |

Note that Event subtypes (`ChatMessage`, `JoinEvent`, `LeaveEvent`, `FastForwardEvent`) cannot be reliably inferred from the subdirectory alone since they all live in `events/`. If the `type` field is missing from an event file, it defaults to `Event`. The validator (section-05) may flag this as a warning if event-subtype-specific fields are present but the type is generic.

### Duplicate entity ID handling

When two entity files have the same `id` in their frontmatter:
1. Record a warning with both file paths.
2. Apply "last-wins" semantics: the entity parsed later replaces the earlier one.
3. Since file iteration order depends on the filesystem, the behavior is deterministic within a single run but may vary across platforms. This is acceptable since duplicate IDs indicate a user error.

### Scene.messages stripping

The `Scene` Pydantic model has a `messages: List[ChatMessage]` field. During import, messages are reconstructed from `chatlog.log`, not from frontmatter. The parser explicitly removes `messages` from the frontmatter dict before constructing the Scene entity to avoid:
- Importing stale message data from frontmatter
- Validation errors from incomplete ChatMessage objects in YAML

### Error handling philosophy

The parser is deliberately lenient. It should:
- Never raise exceptions for bad input files
- Record all issues as `MigrationValidationIssue` objects in `errors` (for problems that prevent parsing) or `warnings` (for non-fatal issues)
- Continue parsing remaining files after encountering an error in one file
- Return a `ParseResult` even if every file failed to parse

This allows the validator (section-05) and the UI to present a comprehensive report of all issues, rather than stopping at the first error.

### Imports needed

```python
from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

from sidestage.memory.models import Memory
from sidestage.migration.models import MigrationValidationIssue, ParseResult
from sidestage.migration.serialization import (
    frontmatter_dict_to_entity,
    frontmatter_dict_to_memory,
)
from sidestage.schemas import Entity

logger = logging.getLogger(__name__)
```

### Relationship to existing code

- **`markdown_to_entity()` in `entities.py`**: The existing parser function. The new parser does NOT reuse this function because: (a) it needs different error handling (return errors, not raise), (b) it uses the new canonical `frontmatter_dict_to_entity()` from `migration/serialization.py`, (c) it handles type inference from subdirectory. The old function remains for backward compatibility with the existing API endpoints.
- **`entity_to_markdown()` in `entities.py`**: Not used by the parser (only by the exporter). Mentioned here for context since both use the same YAML frontmatter format.
- **`LABEL_TO_MODEL` in `graph/entities.py`**: Maps type strings to Pydantic model classes. The serialization module (section-02) may reuse or mirror this mapping in `frontmatter_dict_to_entity()`. The parser itself does not need this mapping directly -- it delegates type resolution to `frontmatter_dict_to_entity()`.
- **`Memory` in `memory/models.py`**: The Memory Pydantic model. Has fields: `id`, `content`, `memory_type` (enum: scene/character/world_fact), `visibility`, `embedding` (excluded from disk), `owner_id`, `target_id`, `created_at`, `updated_at`, `gametime`, `access_count`, `last_accessed_at`.

### Edge cases to handle

1. **Empty `markdown/` directory**: All subdirectories exist but have no files. Return empty ParseResult with no errors.
2. **Missing subdirectories**: Some or all type subdirectories are absent. Skip missing ones gracefully, no errors.
3. **Non-`.md` files in type subdirectories**: Ignore silently (e.g., `.DS_Store`, `.gitkeep`).
4. **Empty `.md` files**: Record an error "Empty file" and continue.
5. **`.d/` directory with no `.md` files inside**: Valid but produces no memories. No warning needed.
6. **Nested directories inside type subdirectories**: Ignore directories that are not `.d/` companion directories.
7. **Memory file with `embedding` field in frontmatter**: The `frontmatter_dict_to_memory()` function should handle this (either strip it or pass it through for Memory model to accept). The parser does not need special handling.
8. **Very large files**: No special handling needed. The parser reads files into memory.
9. **Unicode filenames and content**: Python's `Path.read_text()` handles UTF-8 by default.
