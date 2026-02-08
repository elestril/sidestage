diff --git a/src/sidestage/migration/models.py b/src/sidestage/migration/models.py
index 1fea207..c6b68e8 100644
--- a/src/sidestage/migration/models.py
+++ b/src/sidestage/migration/models.py
@@ -84,3 +84,4 @@ class ParseResult(BaseModel):
     memories: list[Any]
     chatlogs: dict[str, list[str]]
     errors: list[MigrationValidationIssue]
+    warnings: list[MigrationValidationIssue] = []
diff --git a/src/sidestage/migration/parser.py b/src/sidestage/migration/parser.py
new file mode 100644
index 0000000..b126716
--- /dev/null
+++ b/src/sidestage/migration/parser.py
@@ -0,0 +1,255 @@
+"""Parse markdown/ directory tree into entities, memories, and chat logs."""
+
+from __future__ import annotations
+
+import logging
+import re
+from pathlib import Path
+
+import yaml
+
+from sidestage.memory.models import Memory
+from sidestage.migration.models import MigrationValidationIssue, ParseResult
+from sidestage.migration.serialization import (
+    SUBDIR_TO_DEFAULT_TYPE,
+    frontmatter_dict_to_entity,
+    frontmatter_dict_to_memory,
+)
+from sidestage.schemas import Entity, Scene
+
+logger = logging.getLogger(__name__)
+
+_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
+
+SUBDIR_TO_TYPE: dict[str, str] = {
+    "characters": "Character",
+    "locations": "Location",
+    "items": "Item",
+    "scenes": "Scene",
+    "events": "Event",
+}
+
+
+def _parse_frontmatter(content: str, file_path: str) -> tuple[dict, str] | None:
+    """Split markdown content into (frontmatter_dict, body).
+
+    Returns None if the content has no valid frontmatter.
+    """
+    match = _FRONTMATTER_RE.match(content)
+    if not match:
+        return None
+    raw_yaml, body = match.group(1), match.group(2).strip()
+    data = yaml.safe_load(raw_yaml)
+    if not isinstance(data, dict):
+        raise yaml.YAMLError(f"Frontmatter is not a mapping in {file_path}")
+    return data, body
+
+
+def _parse_entity_file(
+    file_path: Path,
+    subdir_type: str,
+    errors: list[MigrationValidationIssue],
+    warnings: list[MigrationValidationIssue],
+) -> Entity | None:
+    """Parse a single entity .md file. Returns entity or None on failure."""
+    path_str = str(file_path)
+    content = file_path.read_text()
+
+    try:
+        result = _parse_frontmatter(content, path_str)
+    except yaml.YAMLError as exc:
+        errors.append(MigrationValidationIssue(
+            file_path=path_str, severity="error",
+            message=f"Malformed YAML: {exc}",
+        ))
+        return None
+
+    if result is None:
+        errors.append(MigrationValidationIssue(
+            file_path=path_str, severity="error",
+            message="Missing YAML frontmatter",
+        ))
+        return None
+
+    data, body = result
+
+    # Type inference
+    if "type" not in data:
+        inferred = SUBDIR_TO_TYPE.get(subdir_type)
+        if inferred:
+            data["type"] = inferred
+            warnings.append(MigrationValidationIssue(
+                file_path=path_str, severity="warning",
+                message=f"Type field missing, inferred as {inferred} from subdirectory.",
+            ))
+        # If subdir_type not recognized, let frontmatter_dict_to_entity handle it
+
+    # Strip messages from Scene frontmatter
+    type_name = data.get("type", "")
+    if type_name == "Scene":
+        data.pop("messages", None)
+
+    # Use type_hint for subdirectory-based fallback in serialization
+    type_hint = subdir_type if "type" not in data else None
+
+    try:
+        entity = frontmatter_dict_to_entity(data, body, type_hint=type_hint)
+    except Exception as exc:
+        errors.append(MigrationValidationIssue(
+            file_path=path_str, severity="error",
+            message=f"Failed to construct entity: {exc}",
+        ))
+        return None
+
+    return entity
+
+
+def _parse_memory_file(
+    file_path: Path,
+    errors: list[MigrationValidationIssue],
+) -> Memory | None:
+    """Parse a single memory .md file from a .d/ directory."""
+    path_str = str(file_path)
+    content = file_path.read_text()
+
+    try:
+        result = _parse_frontmatter(content, path_str)
+    except yaml.YAMLError as exc:
+        errors.append(MigrationValidationIssue(
+            file_path=path_str, severity="error",
+            message=f"Malformed YAML: {exc}",
+        ))
+        return None
+
+    if result is None:
+        errors.append(MigrationValidationIssue(
+            file_path=path_str, severity="error",
+            message="Missing YAML frontmatter",
+        ))
+        return None
+
+    data, body = result
+
+    try:
+        return frontmatter_dict_to_memory(data, body)
+    except Exception as exc:
+        errors.append(MigrationValidationIssue(
+            file_path=path_str, severity="error",
+            message=f"Failed to construct memory: {exc}",
+        ))
+        return None
+
+
+def _read_chatlog(file_path: Path) -> list[str]:
+    """Read chatlog.log and return non-empty lines."""
+    return [line for line in file_path.read_text().splitlines() if line.strip()]
+
+
+def parse_directory(markdown_dir: Path) -> ParseResult:
+    """Parse the markdown/ directory tree into entities, memories, and chat logs.
+
+    Reads all type subdirectories (characters/, locations/, items/, scenes/,
+    events/), parses .md files as entities, reads .d/ companion directories
+    for memories and chat logs.
+
+    Args:
+        markdown_dir: Path to the markdown/ directory.
+
+    Returns:
+        ParseResult with parsed entities, memories, chatlogs, and any
+        errors/warnings encountered during parsing. Never raises exceptions
+        for bad input -- all issues are reported in the result.
+    """
+    errors: list[MigrationValidationIssue] = []
+    warnings: list[MigrationValidationIssue] = []
+    entities: list[Entity] = []
+    memories: list[Memory] = []
+    chatlogs: dict[str, list[str]] = {}
+
+    # entity ID -> index in entities list, for duplicate detection
+    seen_ids: dict[str, str] = {}
+    id_to_index: dict[str, int] = {}
+    # file stem -> entity ID, for .d/ association
+    stem_to_entity: dict[str, tuple[str, str]] = {}  # stem -> (entity_id, entity_type_name)
+
+    # Step 1 & 2: Parse entity files from each type subdirectory
+    for subdir_name in SUBDIR_TO_TYPE:
+        subdir_path = markdown_dir / subdir_name
+        if not subdir_path.is_dir():
+            continue
+
+        for md_file in sorted(subdir_path.glob("*.md")):
+            if not md_file.is_file():
+                continue
+
+            entity = _parse_entity_file(md_file, subdir_name, errors, warnings)
+            if entity is None:
+                continue
+
+            entity_id = entity.id
+            file_str = str(md_file)
+
+            # Duplicate ID check
+            if entity_id in seen_ids:
+                warnings.append(MigrationValidationIssue(
+                    entity_id=entity_id, file_path=file_str, severity="warning",
+                    message=f"Duplicate entity ID '{entity_id}', previously in {seen_ids[entity_id]}. Last-wins.",
+                ))
+                # Replace previous entity
+                entities[id_to_index[entity_id]] = entity
+            else:
+                id_to_index[entity_id] = len(entities)
+                entities.append(entity)
+
+            seen_ids[entity_id] = file_str
+            stem_to_entity[md_file.stem] = (entity_id, type(entity).__name__)
+
+    # Step 3: Parse companion .d/ directories
+    for subdir_name in SUBDIR_TO_TYPE:
+        subdir_path = markdown_dir / subdir_name
+        if not subdir_path.is_dir():
+            continue
+
+        for entry in sorted(subdir_path.iterdir()):
+            if not entry.is_dir() or not entry.name.endswith(".d"):
+                continue
+
+            stem = entry.name[:-2]  # strip .d
+            entity_info = stem_to_entity.get(stem)
+
+            if entity_info is None:
+                warnings.append(MigrationValidationIssue(
+                    file_path=str(entry), severity="warning",
+                    message=f"Orphaned .d/ directory: {entry.name} has no matching entity file.",
+                ))
+                entity_id = None
+                entity_type_name = None
+            else:
+                entity_id, entity_type_name = entity_info
+
+            # Parse memory .md files in .d/
+            for mem_file in sorted(entry.glob("*.md")):
+                if not mem_file.is_file():
+                    continue
+                mem = _parse_memory_file(mem_file, errors)
+                if mem is not None:
+                    memories.append(mem)
+
+            # Handle chatlog.log
+            chatlog_path = entry / "chatlog.log"
+            if chatlog_path.is_file():
+                if entity_type_name == "Scene" and entity_id is not None:
+                    chatlogs[entity_id] = _read_chatlog(chatlog_path)
+                else:
+                    warnings.append(MigrationValidationIssue(
+                        file_path=str(chatlog_path), severity="warning",
+                        message=f"chatlog.log found in non-scene .d/ directory '{entry.name}', ignoring.",
+                    ))
+
+    return ParseResult(
+        entities=entities,
+        memories=memories,
+        chatlogs=chatlogs,
+        errors=errors,
+        warnings=warnings,
+    )
diff --git a/tests/unit/test_migration_parser.py b/tests/unit/test_migration_parser.py
new file mode 100644
index 0000000..d4c1a54
--- /dev/null
+++ b/tests/unit/test_migration_parser.py
@@ -0,0 +1,243 @@
+"""Tests for migration/parser.py -- parse markdown directory tree into models."""
+
+from pathlib import Path
+
+import pytest
+import yaml
+
+from sidestage.migration.parser import parse_directory
+
+
+# --- Helper to write a markdown file with YAML frontmatter ---
+
+def _write_md(path: Path, frontmatter: dict, body: str = "") -> None:
+    """Write a markdown file with YAML frontmatter and body."""
+    fm = yaml.dump(frontmatter, sort_keys=False).strip()
+    path.parent.mkdir(parents=True, exist_ok=True)
+    path.write_text(f"---\n{fm}\n---\n\n{body}")
+
+
+def _write_chatlog(path: Path, lines: list[str]) -> None:
+    """Write a chatlog.log file."""
+    path.parent.mkdir(parents=True, exist_ok=True)
+    path.write_text("\n".join(lines) + "\n")
+
+
+# --- Fixtures ---
+
+@pytest.fixture
+def markdown_dir(tmp_path: Path) -> Path:
+    """Return an empty markdown/ directory with type subdirectories."""
+    md = tmp_path / "markdown"
+    for subdir in ("characters", "locations", "items", "scenes", "events"):
+        (md / subdir).mkdir(parents=True)
+    return md
+
+
+@pytest.fixture
+def populated_dir(markdown_dir: Path) -> Path:
+    """Return a markdown/ directory with sample entities and memories."""
+    # Character with body
+    _write_md(
+        markdown_dir / "characters" / "Eldric_the_Bold.md",
+        {"name": "Eldric the Bold", "id": "char_eldric", "type": "Character",
+         "location_id": "loc_tavern", "inventory": ["item_sword"], "unseen": False},
+        body="A brave warrior.",
+    )
+    # Character memory in .d/
+    _write_md(
+        markdown_dir / "characters" / "Eldric_the_Bold.d" / "mem_tavern_brawl.md",
+        {"id": "mem_tavern_brawl", "memory_type": "scene", "visibility": "private",
+         "owner_id": "char_eldric", "target_id": "scene_brawl",
+         "gametime": 3600, "created_at": 1706000000.0, "updated_at": 1706000000.0,
+         "access_count": 0},
+        body="Eldric saw a fierce brawl.",
+    )
+    # Location
+    _write_md(
+        markdown_dir / "locations" / "The_Rusty_Tavern.md",
+        {"name": "The Rusty Tavern", "id": "loc_tavern", "type": "Location",
+         "connected_locations": ["loc_castle", "loc_square"]},
+        body="A dimly lit tavern.",
+    )
+    # Scene with chatlog
+    _write_md(
+        markdown_dir / "scenes" / "Tavern_Brawl.md",
+        {"name": "Tavern Brawl", "id": "scene_brawl", "type": "Scene",
+         "location_id": "loc_tavern"},
+        body="A chaotic brawl erupts.",
+    )
+    _write_chatlog(
+        markdown_dir / "scenes" / "Tavern_Brawl.d" / "chatlog.log",
+        [
+            '[2026-01-15T14:30:00Z] (char_eldric) Eldric: "I challenge you!"',
+            '[2026-01-15T14:30:05Z] (char_alice) Alice: "You\'ll regret that."',
+        ],
+    )
+    # Item
+    _write_md(
+        markdown_dir / "items" / "Flame_Tongue_Sword.md",
+        {"name": "Flame Tongue Sword", "id": "item_sword", "type": "Item"},
+        body="A sword wreathed in flame.",
+    )
+    # Event (JoinEvent subtype)
+    _write_md(
+        markdown_dir / "events" / "Eldric_Joins_Brawl.md",
+        {"name": "Eldric Joins Brawl", "id": "evt_join_1", "type": "JoinEvent",
+         "scene_id": "scene_brawl", "gametime": 3600,
+         "walltime": "2026-01-15T14:30:00Z", "actor_id": "actor_1"},
+        body="Eldric enters the fray.",
+    )
+    return markdown_dir
+
+
+# --- Core parsing tests ---
+
+def test_parse_directory_reads_all_entity_types(populated_dir):
+    """parse_directory finds entities from all type subdirectories."""
+    result = parse_directory(populated_dir)
+    entity_types = {type(e).__name__ for e in result.entities}
+    assert "Character" in entity_types
+    assert "Location" in entity_types
+    assert "Item" in entity_types
+    assert "Scene" in entity_types
+    assert "JoinEvent" in entity_types
+
+
+def test_parse_directory_reads_memories_from_dot_d(populated_dir):
+    """parse_directory reads memory files from .d/ companion directories."""
+    result = parse_directory(populated_dir)
+    assert len(result.memories) >= 1
+    mem_ids = {m.id for m in result.memories}
+    assert "mem_tavern_brawl" in mem_ids
+
+
+def test_parse_directory_reads_chatlog_from_scene_dot_d(populated_dir):
+    """parse_directory reads chatlog.log from scene .d/ directories."""
+    result = parse_directory(populated_dir)
+    assert "scene_brawl" in result.chatlogs
+    assert len(result.chatlogs["scene_brawl"]) == 2
+
+
+def test_parse_directory_associates_memories_with_parent_entity(populated_dir):
+    """Memories parsed from entity_name.d/ are associated with that entity."""
+    result = parse_directory(populated_dir)
+    # The memory in Eldric_the_Bold.d/ should have owner_id = char_eldric
+    mem = next(m for m in result.memories if m.id == "mem_tavern_brawl")
+    assert mem.owner_id == "char_eldric"
+
+
+def test_parse_directory_infers_type_from_subdirectory(markdown_dir):
+    """When type field is missing from frontmatter, infer from subdirectory name."""
+    _write_md(
+        markdown_dir / "characters" / "No_Type.md",
+        {"name": "No Type", "id": "char_no_type", "unseen": False},
+        body="A character without explicit type.",
+    )
+    result = parse_directory(markdown_dir)
+    entity = next(e for e in result.entities if e.id == "char_no_type")
+    assert type(entity).__name__ == "Character"
+    # Should also produce a warning
+    assert any("type" in w.message.lower() for w in result.warnings)
+
+
+def test_parse_directory_warns_orphaned_dot_d(markdown_dir):
+    """Warn on .d/ without parent .md (orphaned memories)."""
+    orphan_dir = markdown_dir / "characters" / "Ghost.d"
+    _write_md(
+        orphan_dir / "mem_orphan.md",
+        {"id": "mem_orphan", "memory_type": "scene", "visibility": "common",
+         "owner_id": None, "target_id": "char_ghost",
+         "created_at": 1706000000.0, "updated_at": 1706000000.0, "access_count": 0},
+        body="An orphan memory.",
+    )
+    result = parse_directory(markdown_dir)
+    assert any("orphan" in w.message.lower() for w in result.warnings)
+
+
+def test_parse_directory_warns_chatlog_in_non_scene_dot_d(markdown_dir):
+    """Warn on chatlog.log in a non-scene .d/ directory (ignored)."""
+    _write_md(
+        markdown_dir / "characters" / "Char_With_Log.md",
+        {"name": "Char With Log", "id": "char_log", "type": "Character", "unseen": False},
+        body="A character.",
+    )
+    _write_chatlog(
+        markdown_dir / "characters" / "Char_With_Log.d" / "chatlog.log",
+        ["[2026-01-15T14:30:00Z] (char_log) Char: \"Hello\""],
+    )
+    result = parse_directory(markdown_dir)
+    assert any("chatlog" in w.message.lower() for w in result.warnings)
+    assert "char_log" not in result.chatlogs
+
+
+def test_parse_directory_handles_malformed_yaml(markdown_dir):
+    """Malformed YAML produces an error in ParseResult, not an exception."""
+    bad_file = markdown_dir / "characters" / "Bad_Yaml.md"
+    bad_file.write_text("---\n: invalid: yaml: {{{\n---\n\nBody text.")
+    result = parse_directory(markdown_dir)
+    assert len(result.errors) >= 1
+    assert any("Bad_Yaml" in e.file_path for e in result.errors)
+
+
+def test_parse_directory_handles_missing_frontmatter(markdown_dir):
+    """File without frontmatter delimiters produces an error."""
+    bad_file = markdown_dir / "characters" / "No_Frontmatter.md"
+    bad_file.write_text("Just a plain markdown file with no frontmatter.")
+    result = parse_directory(markdown_dir)
+    assert len(result.errors) >= 1
+    assert any("No_Frontmatter" in e.file_path for e in result.errors)
+
+
+def test_parse_directory_warns_duplicate_entity_ids(markdown_dir):
+    """Duplicate entity IDs produce a warning; last-wins."""
+    _write_md(
+        markdown_dir / "characters" / "First.md",
+        {"name": "First", "id": "char_dup", "type": "Character", "unseen": False},
+        body="First character.",
+    )
+    _write_md(
+        markdown_dir / "characters" / "Second.md",
+        {"name": "Second", "id": "char_dup", "type": "Character", "unseen": False},
+        body="Second character (same ID).",
+    )
+    result = parse_directory(markdown_dir)
+    dup_entities = [e for e in result.entities if e.id == "char_dup"]
+    assert len(dup_entities) == 1  # last-wins deduplication
+    assert any("duplicate" in w.message.lower() for w in result.warnings)
+
+
+def test_parse_directory_ignores_scene_messages_in_frontmatter(markdown_dir):
+    """Scene.messages in frontmatter is ignored; messages come from chatlog.log."""
+    _write_md(
+        markdown_dir / "scenes" / "Scene_With_Messages.md",
+        {"name": "Scene With Messages", "id": "scene_msg", "type": "Scene",
+         "messages": [{"name": "msg", "id": "msg_1", "body": "", "scene_id": "scene_msg",
+                        "gametime": 0, "walltime": "2026-01-01T00:00:00Z",
+                        "character_id": "c1", "message": "hello"}]},
+        body="A scene.",
+    )
+    result = parse_directory(markdown_dir)
+    scene = next(e for e in result.entities if e.id == "scene_msg")
+    # messages should be empty (stripped from frontmatter before entity construction)
+    assert len(scene.messages) == 0
+
+
+def test_parse_directory_handles_empty_directory(markdown_dir):
+    """Empty directory tree (no entities) returns empty ParseResult with no errors."""
+    result = parse_directory(markdown_dir)
+    assert len(result.entities) == 0
+    assert len(result.memories) == 0
+    assert len(result.chatlogs) == 0
+    assert len(result.errors) == 0
+
+
+def test_parse_directory_handles_missing_type_subdirectories(tmp_path):
+    """Missing type subdirectories are handled gracefully (no crash)."""
+    md = tmp_path / "markdown"
+    md.mkdir()
+    # Only create one subdirectory
+    (md / "characters").mkdir()
+    result = parse_directory(md)
+    assert len(result.entities) == 0
+    assert len(result.errors) == 0
