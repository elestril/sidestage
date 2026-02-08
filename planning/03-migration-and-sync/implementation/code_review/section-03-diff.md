diff --git a/data/test_campaign/markdown/characters/Alice_the_Merchant.d/mem_trade_secret.md b/data/test_campaign/markdown/characters/Alice_the_Merchant.d/mem_trade_secret.md
new file mode 100644
index 0000000..6c1bb01
--- /dev/null
+++ b/data/test_campaign/markdown/characters/Alice_the_Merchant.d/mem_trade_secret.md
@@ -0,0 +1,14 @@
+---
+id: "mem_trade_secret"
+memory_type: "world_fact"
+visibility: "private"
+owner_id: "char_alice"
+target_id: "loc_rusty_tavern"
+gametime: 900
+created_at: 1705800000.0
+updated_at: 1705800000.0
+access_count: 1
+last_accessed_at: 1705900000.0
+---
+
+Alice discovered that the Rusty Tavern has a hidden cellar where smuggled goods are stored. The tavern keeper pays well for discretion about this arrangement.
diff --git a/data/test_campaign/markdown/characters/Alice_the_Merchant.md b/data/test_campaign/markdown/characters/Alice_the_Merchant.md
new file mode 100644
index 0000000..f342124
--- /dev/null
+++ b/data/test_campaign/markdown/characters/Alice_the_Merchant.md
@@ -0,0 +1,10 @@
+---
+name: "Alice the Merchant"
+id: "char_alice"
+type: "Character"
+inventory: []
+location_id: null
+unseen: false
+---
+
+A shrewd merchant who trades in rare goods across the realm. She knows secrets about every market town and has connections in both high and low places.
diff --git a/data/test_campaign/markdown/characters/Eldric_the_Bold.d/mem_knows_alice.md b/data/test_campaign/markdown/characters/Eldric_the_Bold.d/mem_knows_alice.md
new file mode 100644
index 0000000..077a6e1
--- /dev/null
+++ b/data/test_campaign/markdown/characters/Eldric_the_Bold.d/mem_knows_alice.md
@@ -0,0 +1,14 @@
+---
+id: "mem_knows_alice"
+memory_type: "character"
+visibility: "common"
+owner_id: "char_eldric"
+target_id: "char_alice"
+gametime: 1800
+created_at: 1705900000.0
+updated_at: 1705900000.0
+access_count: 2
+last_accessed_at: 1706000000.0
+---
+
+Eldric met Alice at the Town Square market. She sold him a healing potion at a fair price, and they have been on good terms since. He trusts her judgment on matters of trade.
diff --git a/data/test_campaign/markdown/characters/Eldric_the_Bold.d/mem_tavern_brawl.md b/data/test_campaign/markdown/characters/Eldric_the_Bold.d/mem_tavern_brawl.md
new file mode 100644
index 0000000..03e2e50
--- /dev/null
+++ b/data/test_campaign/markdown/characters/Eldric_the_Bold.d/mem_tavern_brawl.md
@@ -0,0 +1,14 @@
+---
+id: "mem_tavern_brawl"
+memory_type: "scene"
+visibility: "private"
+owner_id: "char_eldric"
+target_id: "scene_tavern_brawl"
+gametime: 3600
+created_at: 1706000000.0
+updated_at: 1706000000.0
+access_count: 0
+last_accessed_at: null
+---
+
+Eldric remembers the tavern brawl vividly. A group of mercenaries insulted his honor, and he responded with his fists before drawing his sword. The tavern keeper was not pleased.
diff --git a/data/test_campaign/markdown/characters/Eldric_the_Bold.md b/data/test_campaign/markdown/characters/Eldric_the_Bold.md
new file mode 100644
index 0000000..b11801c
--- /dev/null
+++ b/data/test_campaign/markdown/characters/Eldric_the_Bold.md
@@ -0,0 +1,11 @@
+---
+name: "Eldric the Bold"
+id: "char_eldric"
+type: "Character"
+inventory:
+- "item_flame_tongue"
+location_id: "loc_rusty_tavern"
+unseen: false
+---
+
+A brave warrior who frequents the Rusty Tavern. Known for his fiery temper and his legendary Flame Tongue Sword. He has been involved in more tavern brawls than he can count.
diff --git a/data/test_campaign/markdown/events/Eldric_Joins_Brawl.md b/data/test_campaign/markdown/events/Eldric_Joins_Brawl.md
new file mode 100644
index 0000000..e626c35
--- /dev/null
+++ b/data/test_campaign/markdown/events/Eldric_Joins_Brawl.md
@@ -0,0 +1,11 @@
+---
+name: "Eldric Joins Brawl"
+id: "event_eldric_joins"
+type: "JoinEvent"
+actor_id: "char_eldric"
+gametime: 3600
+scene_id: "scene_tavern_brawl"
+walltime: "2026-01-15T14:30:00Z"
+---
+
+Eldric the Bold strides into the Rusty Tavern and immediately joins the brawl, drawing his Flame Tongue Sword with a battle cry.
diff --git a/data/test_campaign/markdown/items/Flame_Tongue_Sword.md b/data/test_campaign/markdown/items/Flame_Tongue_Sword.md
new file mode 100644
index 0000000..f21319f
--- /dev/null
+++ b/data/test_campaign/markdown/items/Flame_Tongue_Sword.md
@@ -0,0 +1,7 @@
+---
+name: "Flame Tongue Sword"
+id: "item_flame_tongue"
+type: "Item"
+---
+
+A magnificent longsword with a blade that glows with inner fire. When drawn in anger, flames lick along its edge, casting dancing shadows. It was forged by a master smith who infused it with the essence of a fire elemental.
diff --git a/data/test_campaign/markdown/items/Healing_Potion.md b/data/test_campaign/markdown/items/Healing_Potion.md
new file mode 100644
index 0000000..ceaabfa
--- /dev/null
+++ b/data/test_campaign/markdown/items/Healing_Potion.md
@@ -0,0 +1,7 @@
+---
+name: "Healing Potion"
+id: "item_healing_potion"
+type: "Item"
+---
+
+A small glass vial filled with a shimmering red liquid. When consumed, it mends wounds and restores vitality. This particular potion was brewed by a traveling alchemist and purchased by Alice the Merchant.
diff --git a/data/test_campaign/markdown/locations/Castle_Blackmoor.d/mem_castle_legend.md b/data/test_campaign/markdown/locations/Castle_Blackmoor.d/mem_castle_legend.md
new file mode 100644
index 0000000..6ac3357
--- /dev/null
+++ b/data/test_campaign/markdown/locations/Castle_Blackmoor.d/mem_castle_legend.md
@@ -0,0 +1,14 @@
+---
+id: "mem_castle_legend"
+memory_type: "world_fact"
+visibility: "common"
+owner_id: null
+target_id: "loc_castle_blackmoor"
+gametime: null
+created_at: 1705600000.0
+updated_at: 1705600000.0
+access_count: 0
+last_accessed_at: null
+---
+
+Legend has it that Castle Blackmoor was built by a dragon who took human form. The black stone of its walls is said to be dragon scale, transmuted into rock by ancient magic. Some claim the dragon still sleeps beneath the castle foundations.
diff --git a/data/test_campaign/markdown/locations/Castle_Blackmoor.md b/data/test_campaign/markdown/locations/Castle_Blackmoor.md
new file mode 100644
index 0000000..9367bd2
--- /dev/null
+++ b/data/test_campaign/markdown/locations/Castle_Blackmoor.md
@@ -0,0 +1,10 @@
+---
+name: "Castle Blackmoor"
+id: "loc_castle_blackmoor"
+type: "Location"
+connected_locations:
+- "loc_rusty_tavern"
+- "loc_town_square"
+---
+
+A imposing fortress perched on a rocky hill overlooking the valley. Castle Blackmoor has served as the seat of power for the local lord for generations. Its black stone walls are said to be impervious to siege.
diff --git a/data/test_campaign/markdown/locations/The_Rusty_Tavern.d/mem_haunted_history.md b/data/test_campaign/markdown/locations/The_Rusty_Tavern.d/mem_haunted_history.md
new file mode 100644
index 0000000..fe89e61
--- /dev/null
+++ b/data/test_campaign/markdown/locations/The_Rusty_Tavern.d/mem_haunted_history.md
@@ -0,0 +1,14 @@
+---
+id: "mem_haunted_history"
+memory_type: "world_fact"
+visibility: "common"
+owner_id: null
+target_id: "loc_rusty_tavern"
+gametime: null
+created_at: 1705700000.0
+updated_at: 1705700000.0
+access_count: 0
+last_accessed_at: null
+---
+
+The Rusty Tavern was built on the site of an old battlefield. Locals say that on moonless nights, the sounds of clashing swords can be heard from the cellar. The tavern keeper dismisses these stories, but refuses to go downstairs after dark.
diff --git a/data/test_campaign/markdown/locations/The_Rusty_Tavern.md b/data/test_campaign/markdown/locations/The_Rusty_Tavern.md
new file mode 100644
index 0000000..5f613b2
--- /dev/null
+++ b/data/test_campaign/markdown/locations/The_Rusty_Tavern.md
@@ -0,0 +1,10 @@
+---
+name: "The Rusty Tavern"
+id: "loc_rusty_tavern"
+type: "Location"
+connected_locations:
+- "loc_castle_blackmoor"
+- "loc_town_square"
+---
+
+A weathered tavern at the crossroads, known for its cheap ale and frequent brawls. The sign above the door depicts a rusted sword crossed with a tankard. Despite its rough reputation, it serves as a gathering place for adventurers and merchants alike.
diff --git a/data/test_campaign/markdown/locations/Town_Square.md b/data/test_campaign/markdown/locations/Town_Square.md
new file mode 100644
index 0000000..908e07d
--- /dev/null
+++ b/data/test_campaign/markdown/locations/Town_Square.md
@@ -0,0 +1,10 @@
+---
+name: "Town Square"
+id: "loc_town_square"
+type: "Location"
+connected_locations:
+- "loc_rusty_tavern"
+- "loc_castle_blackmoor"
+---
+
+The bustling center of town, where merchants hawk their wares and townsfolk gather to exchange news. A large stone fountain stands in the middle, carved with scenes from the town's founding. Market day brings traders from across the region.
diff --git a/data/test_campaign/markdown/scenes/Castle_Audience.md b/data/test_campaign/markdown/scenes/Castle_Audience.md
new file mode 100644
index 0000000..691b493
--- /dev/null
+++ b/data/test_campaign/markdown/scenes/Castle_Audience.md
@@ -0,0 +1,10 @@
+---
+name: "Castle Audience"
+id: "scene_castle_audience"
+type: "Scene"
+current_gametime: null
+events: []
+location_id: "loc_castle_blackmoor"
+---
+
+A formal audience with the lord of Castle Blackmoor. The great hall is lit by flickering torches, and the lord sits upon a throne of black stone. Petitioners line up to present their cases and seek the lord's judgment.
diff --git a/data/test_campaign/markdown/scenes/Tavern_Brawl.d/chatlog.log b/data/test_campaign/markdown/scenes/Tavern_Brawl.d/chatlog.log
new file mode 100644
index 0000000..f0edea2
--- /dev/null
+++ b/data/test_campaign/markdown/scenes/Tavern_Brawl.d/chatlog.log
@@ -0,0 +1,3 @@
+[2026-01-15T14:30:00Z] (char_eldric) Eldric the Bold: "I challenge you to a duel!"
+[2026-01-15T14:30:05Z] (char_alice) Alice the Merchant: "You'll regret that, Eldric."
+[2026-01-15T14:30:10Z] (char_eldric) Eldric the Bold: "A warrior never backs down from a fight!"
diff --git a/data/test_campaign/markdown/scenes/Tavern_Brawl.d/mem_brawl_outcome.md b/data/test_campaign/markdown/scenes/Tavern_Brawl.d/mem_brawl_outcome.md
new file mode 100644
index 0000000..28b202d
--- /dev/null
+++ b/data/test_campaign/markdown/scenes/Tavern_Brawl.d/mem_brawl_outcome.md
@@ -0,0 +1,14 @@
+---
+id: "mem_brawl_outcome"
+memory_type: "scene"
+visibility: "common"
+owner_id: null
+target_id: "scene_tavern_brawl"
+gametime: 7200
+created_at: 1706100000.0
+updated_at: 1706100000.0
+access_count: 0
+last_accessed_at: null
+---
+
+The tavern brawl ended when the town guard arrived and broke up the fighting. Several tables were destroyed and the tavern keeper demanded compensation. Eldric was recognized as the instigator but was let off with a warning due to his reputation.
diff --git a/data/test_campaign/markdown/scenes/Tavern_Brawl.md b/data/test_campaign/markdown/scenes/Tavern_Brawl.md
new file mode 100644
index 0000000..d620a4b
--- /dev/null
+++ b/data/test_campaign/markdown/scenes/Tavern_Brawl.md
@@ -0,0 +1,11 @@
+---
+name: "Tavern Brawl"
+id: "scene_tavern_brawl"
+type: "Scene"
+current_gametime: 7200
+events:
+- "event_eldric_joins"
+location_id: "loc_rusty_tavern"
+---
+
+A chaotic brawl erupts in the Rusty Tavern after a group of mercenaries challenge the locals. Tables are overturned, tankards fly through the air, and the tavern keeper shouts for order that nobody heeds.
diff --git a/tests/unit/test_campaign_fixture.py b/tests/unit/test_campaign_fixture.py
new file mode 100644
index 0000000..dbf951d
--- /dev/null
+++ b/tests/unit/test_campaign_fixture.py
@@ -0,0 +1,286 @@
+"""Tests that validate the test campaign fixture data is well-formed.
+
+These tests ensure the canonical test campaign at data/test_campaign/markdown/
+can be parsed correctly by the migration serialization layer. They serve as a
+smoke test for the fixture data itself.
+"""
+
+import re
+import shutil
+from pathlib import Path
+
+import pytest
+import yaml
+
+from sidestage.migration.serialization import (
+    frontmatter_dict_to_entity,
+    frontmatter_dict_to_memory,
+)
+
+CAMPAIGN_ROOT = Path(__file__).parent.parent.parent / "data" / "test_campaign" / "markdown"
+
+ENTITY_SUBDIRS = ["characters", "locations", "items", "scenes", "events"]
+
+
+def _parse_frontmatter(path: Path) -> tuple[dict, str]:
+    """Extract YAML frontmatter and body from a markdown file."""
+    text = path.read_text(encoding="utf-8")
+    assert text.startswith("---"), f"{path} does not start with ---"
+    end = text.index("---", 3)
+    fm = yaml.safe_load(text[3:end])
+    body = text[end + 3:].strip()
+    return fm, body
+
+
+def _collect_entity_files(root: Path) -> list[Path]:
+    """Collect all .md files directly inside entity type subdirectories."""
+    files = []
+    for subdir_name in ENTITY_SUBDIRS:
+        subdir = root / subdir_name
+        if subdir.is_dir():
+            files.extend(f for f in subdir.iterdir() if f.suffix == ".md" and f.is_file())
+    return files
+
+
+def _collect_memory_files(root: Path) -> list[Path]:
+    """Collect all .md files inside .d/ companion directories."""
+    files = []
+    for subdir_name in ENTITY_SUBDIRS:
+        subdir = root / subdir_name
+        if not subdir.is_dir():
+            continue
+        for d_dir in subdir.iterdir():
+            if d_dir.is_dir() and d_dir.name.endswith(".d"):
+                files.extend(f for f in d_dir.iterdir() if f.suffix == ".md" and f.is_file())
+    return files
+
+
+def _collect_all_entity_ids(root: Path) -> set[str]:
+    """Parse all entity files and return the set of their IDs."""
+    ids = set()
+    for path in _collect_entity_files(root):
+        fm, _ = _parse_frontmatter(path)
+        ids.add(fm["id"])
+    return ids
+
+
+@pytest.fixture
+def test_campaign_markdown(tmp_path: Path) -> Path:
+    """Copy canonical test campaign to a temp directory for testing."""
+    dst = tmp_path / "markdown"
+    shutil.copytree(CAMPAIGN_ROOT, dst)
+    return dst
+
+
+def test_fixture_directory_structure():
+    """The test campaign root exists and contains all expected type subdirectories."""
+    assert CAMPAIGN_ROOT.is_dir(), f"Campaign root does not exist: {CAMPAIGN_ROOT}"
+    for subdir_name in ENTITY_SUBDIRS:
+        subdir = CAMPAIGN_ROOT / subdir_name
+        assert subdir.is_dir(), f"Missing expected subdirectory: {subdir_name}"
+
+
+def test_all_entity_files_have_valid_frontmatter(test_campaign_markdown):
+    """Every .md file directly inside a type subdirectory has parseable YAML frontmatter."""
+    entity_files = _collect_entity_files(test_campaign_markdown)
+    assert len(entity_files) > 0, "No entity files found"
+    for path in entity_files:
+        fm, body = _parse_frontmatter(path)
+        assert isinstance(fm, dict), f"{path.name}: frontmatter is not a dict"
+        assert "id" in fm, f"{path.name}: missing 'id' field"
+        assert "name" in fm, f"{path.name}: missing 'name' field"
+
+
+def test_all_entity_files_deserialize(test_campaign_markdown):
+    """Every entity .md file produces a valid Entity via frontmatter_dict_to_entity."""
+    entity_files = _collect_entity_files(test_campaign_markdown)
+    for path in entity_files:
+        fm, body = _parse_frontmatter(path)
+        # Determine type_hint from parent directory name
+        type_hint = path.parent.name
+        entity = frontmatter_dict_to_entity(fm, body, type_hint=type_hint)
+        assert entity.id == fm["id"]
+        assert entity.name == fm["name"]
+
+
+def test_all_memory_files_have_valid_frontmatter(test_campaign_markdown):
+    """Every .md file inside a .d/ companion directory has parseable YAML frontmatter."""
+    memory_files = _collect_memory_files(test_campaign_markdown)
+    assert len(memory_files) > 0, "No memory files found"
+    for path in memory_files:
+        fm, body = _parse_frontmatter(path)
+        assert isinstance(fm, dict), f"{path.name}: frontmatter is not a dict"
+        assert "id" in fm, f"{path.name}: missing 'id' field"
+        assert "memory_type" in fm, f"{path.name}: missing 'memory_type' field"
+        assert "target_id" in fm, f"{path.name}: missing 'target_id' field"
+
+
+def test_all_memory_files_deserialize(test_campaign_markdown):
+    """Every memory .md file produces a valid Memory via frontmatter_dict_to_memory."""
+    memory_files = _collect_memory_files(test_campaign_markdown)
+    for path in memory_files:
+        fm, body = _parse_frontmatter(path)
+        memory = frontmatter_dict_to_memory(fm, body)
+        assert memory.id == fm["id"]
+        assert memory.content == body
+
+
+def test_expected_entity_counts(test_campaign_markdown):
+    """The fixture contains exactly: 2 characters, 3 locations, 2 items, 2 scenes, 1 event."""
+    expected = {
+        "characters": 2,
+        "locations": 3,
+        "items": 2,
+        "scenes": 2,
+        "events": 1,
+    }
+    for subdir_name, count in expected.items():
+        subdir = test_campaign_markdown / subdir_name
+        md_files = [f for f in subdir.iterdir() if f.suffix == ".md" and f.is_file()]
+        assert len(md_files) == count, (
+            f"{subdir_name}: expected {count} .md files, found {len(md_files)}"
+        )
+
+
+def test_expected_memory_counts(test_campaign_markdown):
+    """The fixture contains exactly 6 memory files across all .d/ directories."""
+    memory_files = _collect_memory_files(test_campaign_markdown)
+    assert len(memory_files) == 6, f"Expected 6 memory files, found {len(memory_files)}"
+
+
+def test_chatlog_exists_for_tavern_brawl(test_campaign_markdown):
+    """The Tavern_Brawl.d/ directory contains a chatlog.log file with multiple lines."""
+    chatlog = test_campaign_markdown / "scenes" / "Tavern_Brawl.d" / "chatlog.log"
+    assert chatlog.is_file(), "chatlog.log not found in Tavern_Brawl.d/"
+    lines = chatlog.read_text(encoding="utf-8").strip().splitlines()
+    assert len(lines) >= 2, f"chatlog.log should have at least 2 lines, found {len(lines)}"
+
+
+def test_chatlog_format(test_campaign_markdown):
+    """Each line in chatlog.log matches [timestamp] (character_id) Name: 'message' pattern."""
+    chatlog = test_campaign_markdown / "scenes" / "Tavern_Brawl.d" / "chatlog.log"
+    pattern = re.compile(r'^\[.+?\] \(\w+\) .+?: ".+"$')
+    lines = chatlog.read_text(encoding="utf-8").strip().splitlines()
+    for i, line in enumerate(lines):
+        assert pattern.match(line), f"Line {i + 1} does not match expected pattern: {line}"
+
+
+def test_character_location_references(test_campaign_markdown):
+    """Characters with location_id reference IDs that appear in location entity files."""
+    location_ids = set()
+    for path in (test_campaign_markdown / "locations").iterdir():
+        if path.suffix == ".md" and path.is_file():
+            fm, _ = _parse_frontmatter(path)
+            location_ids.add(fm["id"])
+
+    for path in (test_campaign_markdown / "characters").iterdir():
+        if path.suffix == ".md" and path.is_file():
+            fm, _ = _parse_frontmatter(path)
+            loc_id = fm.get("location_id")
+            if loc_id is not None:
+                assert loc_id in location_ids, (
+                    f"{path.name}: location_id '{loc_id}' not found in locations"
+                )
+
+
+def test_character_inventory_references(test_campaign_markdown):
+    """Characters with inventory items reference IDs that appear in item entity files."""
+    item_ids = set()
+    for path in (test_campaign_markdown / "items").iterdir():
+        if path.suffix == ".md" and path.is_file():
+            fm, _ = _parse_frontmatter(path)
+            item_ids.add(fm["id"])
+
+    for path in (test_campaign_markdown / "characters").iterdir():
+        if path.suffix == ".md" and path.is_file():
+            fm, _ = _parse_frontmatter(path)
+            for inv_id in fm.get("inventory", []):
+                assert inv_id in item_ids, (
+                    f"{path.name}: inventory item '{inv_id}' not found in items"
+                )
+
+
+def test_location_connectivity(test_campaign_markdown):
+    """The three locations have connected_locations forming a triangle (each references two others)."""
+    location_data = {}
+    for path in (test_campaign_markdown / "locations").iterdir():
+        if path.suffix == ".md" and path.is_file():
+            fm, _ = _parse_frontmatter(path)
+            location_data[fm["id"]] = set(fm.get("connected_locations", []))
+
+    assert len(location_data) == 3, f"Expected 3 locations, found {len(location_data)}"
+    for loc_id, connected in location_data.items():
+        other_ids = set(location_data.keys()) - {loc_id}
+        assert connected == other_ids, (
+            f"{loc_id}: expected connections to {other_ids}, got {connected}"
+        )
+
+
+def test_scene_location_references(test_campaign_markdown):
+    """Scenes with location_id reference IDs that appear in location entity files."""
+    location_ids = set()
+    for path in (test_campaign_markdown / "locations").iterdir():
+        if path.suffix == ".md" and path.is_file():
+            fm, _ = _parse_frontmatter(path)
+            location_ids.add(fm["id"])
+
+    for path in (test_campaign_markdown / "scenes").iterdir():
+        if path.suffix == ".md" and path.is_file():
+            fm, _ = _parse_frontmatter(path)
+            loc_id = fm.get("location_id")
+            if loc_id is not None:
+                assert loc_id in location_ids, (
+                    f"{path.name}: location_id '{loc_id}' not found in locations"
+                )
+
+
+def test_event_scene_references(test_campaign_markdown):
+    """Events reference scene_id values that appear in scene entity files."""
+    scene_ids = set()
+    for path in (test_campaign_markdown / "scenes").iterdir():
+        if path.suffix == ".md" and path.is_file():
+            fm, _ = _parse_frontmatter(path)
+            scene_ids.add(fm["id"])
+
+    for path in (test_campaign_markdown / "events").iterdir():
+        if path.suffix == ".md" and path.is_file():
+            fm, _ = _parse_frontmatter(path)
+            scene_id = fm.get("scene_id")
+            if scene_id is not None:
+                assert scene_id in scene_ids, (
+                    f"{path.name}: scene_id '{scene_id}' not found in scenes"
+                )
+
+
+def test_memory_entity_references(test_campaign_markdown):
+    """Memory owner_id and target_id values reference entity IDs found in the fixture."""
+    all_entity_ids = _collect_all_entity_ids(test_campaign_markdown)
+    memory_files = _collect_memory_files(test_campaign_markdown)
+
+    for path in memory_files:
+        fm, _ = _parse_frontmatter(path)
+        owner_id = fm.get("owner_id")
+        target_id = fm.get("target_id")
+
+        if owner_id is not None:
+            assert owner_id in all_entity_ids, (
+                f"{path.name}: owner_id '{owner_id}' not found in entities"
+            )
+        assert target_id in all_entity_ids, (
+            f"{path.name}: target_id '{target_id}' not found in entities"
+        )
+
+
+def test_dot_d_naming_matches_parent(test_campaign_markdown):
+    """Every .d/ directory has a corresponding .md file with the same stem in the same type subdir."""
+    for subdir_name in ENTITY_SUBDIRS:
+        subdir = test_campaign_markdown / subdir_name
+        if not subdir.is_dir():
+            continue
+        for entry in subdir.iterdir():
+            if entry.is_dir() and entry.name.endswith(".d"):
+                stem = entry.name[:-2]  # Remove .d suffix
+                expected_md = subdir / f"{stem}.md"
+                assert expected_md.is_file(), (
+                    f"{subdir_name}/{entry.name} has no matching {stem}.md"
+                )
