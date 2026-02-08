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
