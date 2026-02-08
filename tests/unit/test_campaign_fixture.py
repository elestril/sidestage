"""Tests that validate the test campaign fixture data is well-formed.

These tests ensure the canonical test campaign at data/dev_campaign/markdown/
can be parsed correctly by the migration serialization layer. They serve as a
smoke test for the fixture data itself.
"""

import re
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from sidestage.migration.serialization import (
    frontmatter_dict_to_entity,
    frontmatter_dict_to_memory,
)

CAMPAIGN_ROOT = Path(__file__).parent.parent.parent / "data" / "dev_campaign" / "markdown"

ENTITY_SUBDIRS = ["characters", "locations", "items", "scenes", "events"]


def _parse_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter and body from a markdown file."""
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---"), f"{path} does not start with ---"
    end = text.index("---", 3)
    fm = yaml.safe_load(text[3:end])
    body = text[end + 3:].strip()
    return fm, body


def _collect_entity_files(root: Path) -> list[Path]:
    """Collect all .md files directly inside entity type subdirectories."""
    files = []
    for subdir_name in ENTITY_SUBDIRS:
        subdir = root / subdir_name
        if subdir.is_dir():
            files.extend(f for f in subdir.iterdir() if f.suffix == ".md" and f.is_file())
    return files


def _collect_memory_files(root: Path) -> list[Path]:
    """Collect all .md files inside .d/ companion directories."""
    files = []
    for subdir_name in ENTITY_SUBDIRS:
        subdir = root / subdir_name
        if not subdir.is_dir():
            continue
        for d_dir in subdir.iterdir():
            if d_dir.is_dir() and d_dir.name.endswith(".d"):
                files.extend(f for f in d_dir.iterdir() if f.suffix == ".md" and f.is_file())
    return files


def _collect_all_entity_ids(root: Path) -> set[str]:
    """Parse all entity files and return the set of their IDs."""
    ids = set()
    for path in _collect_entity_files(root):
        fm, _ = _parse_frontmatter(path)
        ids.add(fm["id"])
    return ids


@pytest.fixture
def test_campaign_markdown(tmp_path: Path) -> Path:
    """Copy canonical test campaign to a temp directory for testing."""
    dst = tmp_path / "markdown"
    shutil.copytree(CAMPAIGN_ROOT, dst)
    return dst


def test_fixture_directory_structure():
    """The test campaign root exists and contains all expected type subdirectories."""
    assert CAMPAIGN_ROOT.is_dir(), f"Campaign root does not exist: {CAMPAIGN_ROOT}"
    for subdir_name in ENTITY_SUBDIRS:
        subdir = CAMPAIGN_ROOT / subdir_name
        assert subdir.is_dir(), f"Missing expected subdirectory: {subdir_name}"


def test_all_entity_files_have_valid_frontmatter(test_campaign_markdown: Path):
    """Every .md file directly inside a type subdirectory has parseable YAML frontmatter."""
    entity_files = _collect_entity_files(test_campaign_markdown)
    assert len(entity_files) > 0, "No entity files found"
    for path in entity_files:
        fm, body = _parse_frontmatter(path)
        assert isinstance(fm, dict), f"{path.name}: frontmatter is not a dict"
        assert "id" in fm, f"{path.name}: missing 'id' field"
        assert "name" in fm, f"{path.name}: missing 'name' field"


def test_all_entity_files_deserialize(test_campaign_markdown: Path):
    """Every entity .md file produces a valid Entity via frontmatter_dict_to_entity."""
    entity_files = _collect_entity_files(test_campaign_markdown)
    for path in entity_files:
        fm, body = _parse_frontmatter(path)
        # Determine type_hint from parent directory name
        type_hint = path.parent.name
        entity = frontmatter_dict_to_entity(fm, body, type_hint=type_hint)
        assert entity.id == fm["id"]
        assert entity.name == fm["name"]


def test_all_memory_files_have_valid_frontmatter(test_campaign_markdown: Path):
    """Every .md file inside a .d/ companion directory has parseable YAML frontmatter."""
    memory_files = _collect_memory_files(test_campaign_markdown)
    assert len(memory_files) > 0, "No memory files found"
    for path in memory_files:
        fm, body = _parse_frontmatter(path)
        assert isinstance(fm, dict), f"{path.name}: frontmatter is not a dict"
        assert "id" in fm, f"{path.name}: missing 'id' field"
        assert "memory_type" in fm, f"{path.name}: missing 'memory_type' field"
        assert "target_id" in fm, f"{path.name}: missing 'target_id' field"


def test_all_memory_files_deserialize(test_campaign_markdown: Path):
    """Every memory .md file produces a valid Memory via frontmatter_dict_to_memory."""
    memory_files = _collect_memory_files(test_campaign_markdown)
    for path in memory_files:
        fm, body = _parse_frontmatter(path)
        memory = frontmatter_dict_to_memory(fm, body)
        assert memory.id == fm["id"]
        assert memory.content == body


def test_expected_entity_counts(test_campaign_markdown: Path):
    """The fixture contains exactly: 2 characters, 3 locations, 2 items, 2 scenes, 1 event."""
    expected = {
        "characters": 2,
        "locations": 3,
        "items": 2,
        "scenes": 2,
        "events": 1,
    }
    for subdir_name, count in expected.items():
        subdir = test_campaign_markdown / subdir_name
        md_files = [f for f in subdir.iterdir() if f.suffix == ".md" and f.is_file()]
        assert len(md_files) == count, (
            f"{subdir_name}: expected {count} .md files, found {len(md_files)}"
        )


def test_expected_memory_counts(test_campaign_markdown: Path):
    """The fixture contains exactly 6 memory files across all .d/ directories."""
    memory_files = _collect_memory_files(test_campaign_markdown)
    assert len(memory_files) == 6, f"Expected 6 memory files, found {len(memory_files)}"


def test_chatlog_exists_for_tavern_brawl(test_campaign_markdown: Path):
    """The Tavern_Brawl.d/ directory contains a chatlog.log file with multiple lines."""
    chatlog = test_campaign_markdown / "scenes" / "Tavern_Brawl.d" / "chatlog.log"
    assert chatlog.is_file(), "chatlog.log not found in Tavern_Brawl.d/"
    lines = chatlog.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2, f"chatlog.log should have at least 2 lines, found {len(lines)}"


def test_chatlog_format(test_campaign_markdown: Path):
    """Each line in chatlog.log matches [timestamp] (character_id) Name: 'message' pattern."""
    chatlog = test_campaign_markdown / "scenes" / "Tavern_Brawl.d" / "chatlog.log"
    pattern = re.compile(r'^\[.+?\] \(\w+\) .+?: ".+"$')
    lines = chatlog.read_text(encoding="utf-8").strip().splitlines()
    for i, line in enumerate(lines):
        assert pattern.match(line), f"Line {i + 1} does not match expected pattern: {line}"


def test_character_location_references(test_campaign_markdown: Path):
    """Characters with location_id reference IDs that appear in location entity files."""
    location_ids = set()
    for path in (test_campaign_markdown / "locations").iterdir():
        if path.suffix == ".md" and path.is_file():
            fm, _ = _parse_frontmatter(path)
            location_ids.add(fm["id"])

    for path in (test_campaign_markdown / "characters").iterdir():
        if path.suffix == ".md" and path.is_file():
            fm, _ = _parse_frontmatter(path)
            loc_id = fm.get("location_id")
            if loc_id is not None:
                assert loc_id in location_ids, (
                    f"{path.name}: location_id '{loc_id}' not found in locations"
                )


def test_character_inventory_references(test_campaign_markdown: Path):
    """Characters with inventory items reference IDs that appear in item entity files."""
    item_ids = set()
    for path in (test_campaign_markdown / "items").iterdir():
        if path.suffix == ".md" and path.is_file():
            fm, _ = _parse_frontmatter(path)
            item_ids.add(fm["id"])

    for path in (test_campaign_markdown / "characters").iterdir():
        if path.suffix == ".md" and path.is_file():
            fm, _ = _parse_frontmatter(path)
            for inv_id in fm.get("inventory", []):
                assert inv_id in item_ids, (
                    f"{path.name}: inventory item '{inv_id}' not found in items"
                )


def test_location_connectivity(test_campaign_markdown: Path):
    """The three locations have connected_locations forming a triangle (each references two others)."""
    location_data = {}
    for path in (test_campaign_markdown / "locations").iterdir():
        if path.suffix == ".md" and path.is_file():
            fm, _ = _parse_frontmatter(path)
            location_data[fm["id"]] = set(fm.get("connected_locations", []))

    assert len(location_data) == 3, f"Expected 3 locations, found {len(location_data)}"
    for loc_id, connected in location_data.items():
        other_ids = set(location_data.keys()) - {loc_id}
        assert connected == other_ids, (
            f"{loc_id}: expected connections to {other_ids}, got {connected}"
        )


def test_scene_location_references(test_campaign_markdown: Path):
    """Scenes with location_id reference IDs that appear in location entity files."""
    location_ids = set()
    for path in (test_campaign_markdown / "locations").iterdir():
        if path.suffix == ".md" and path.is_file():
            fm, _ = _parse_frontmatter(path)
            location_ids.add(fm["id"])

    for path in (test_campaign_markdown / "scenes").iterdir():
        if path.suffix == ".md" and path.is_file():
            fm, _ = _parse_frontmatter(path)
            loc_id = fm.get("location_id")
            if loc_id is not None:
                assert loc_id in location_ids, (
                    f"{path.name}: location_id '{loc_id}' not found in locations"
                )


def test_event_scene_references(test_campaign_markdown: Path):
    """Events reference scene_id values that appear in scene entity files."""
    scene_ids = set()
    for path in (test_campaign_markdown / "scenes").iterdir():
        if path.suffix == ".md" and path.is_file():
            fm, _ = _parse_frontmatter(path)
            scene_ids.add(fm["id"])

    for path in (test_campaign_markdown / "events").iterdir():
        if path.suffix == ".md" and path.is_file():
            fm, _ = _parse_frontmatter(path)
            scene_id = fm.get("scene_id")
            if scene_id is not None:
                assert scene_id in scene_ids, (
                    f"{path.name}: scene_id '{scene_id}' not found in scenes"
                )


def test_memory_entity_references(test_campaign_markdown: Path):
    """Memory owner_id and target_id values reference entity IDs found in the fixture."""
    all_entity_ids = _collect_all_entity_ids(test_campaign_markdown)
    memory_files = _collect_memory_files(test_campaign_markdown)

    for path in memory_files:
        fm, _ = _parse_frontmatter(path)
        owner_id = fm.get("owner_id")
        target_id = fm.get("target_id")

        if owner_id is not None:
            assert owner_id in all_entity_ids, (
                f"{path.name}: owner_id '{owner_id}' not found in entities"
            )
        assert target_id in all_entity_ids, (
            f"{path.name}: target_id '{target_id}' not found in entities"
        )


def test_dot_d_naming_matches_parent(test_campaign_markdown: Path):
    """Every .d/ directory has a corresponding .md file with the same stem in the same type subdir."""
    for subdir_name in ENTITY_SUBDIRS:
        subdir = test_campaign_markdown / subdir_name
        if not subdir.is_dir():
            continue
        for entry in subdir.iterdir():
            if entry.is_dir() and entry.name.endswith(".d"):
                stem = entry.name[:-2]  # Remove .d suffix
                expected_md = subdir / f"{stem}.md"
                assert expected_md.is_file(), (
                    f"{subdir_name}/{entry.name} has no matching {stem}.md"
                )
