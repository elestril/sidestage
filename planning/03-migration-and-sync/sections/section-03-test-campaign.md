# Section 03: Test Campaign

## Overview

This section creates the canonical test campaign fixture at `/home/harald/src/sidestage/data/test_campaign/markdown/`. This directory tree contains representative entity and memory markdown files that serve as both documentation of the expected backup/import format and as test fixtures for integration tests (section-09).

No Python code is implemented in this section -- only markdown data files and one chat log file. However, a test file is provided to validate that the fixture data is well-formed and parseable.

### Dependencies

- **section-02-serialization**: The file format (YAML frontmatter + markdown body) follows the canonical serialization format defined by `entity_to_frontmatter_dict()` and `memory_to_frontmatter_dict()`. The test in this section imports those functions to validate the fixture data.

### What This Section Produces

- **Directory tree**: `/home/harald/src/sidestage/data/test_campaign/markdown/` with all entity, memory, and chat log files
- **Test file**: `/home/harald/src/sidestage/tests/unit/test_campaign_fixture.py` (validates the fixture data is well-formed)

### What This Section Blocks

- **section-09-integration-tests**: Uses this fixture data for full roundtrip import/backup testing

---

## Tests (Write First)

Create `/home/harald/src/sidestage/tests/unit/test_campaign_fixture.py`. This test validates that every file in the test campaign fixture is well-formed and can be parsed by the serialization layer.

```python
"""Tests that validate the test campaign fixture data is well-formed.

These tests ensure the canonical test campaign at data/test_campaign/markdown/
can be parsed correctly by the migration serialization layer. They serve as a
smoke test for the fixture data itself.
"""

import shutil
from pathlib import Path

import pytest
import yaml

from sidestage.migration.serialization import (
    frontmatter_dict_to_entity,
    frontmatter_dict_to_memory,
)

CAMPAIGN_ROOT = Path(__file__).parent.parent.parent / "data" / "test_campaign" / "markdown"

ENTITY_SUBDIRS = ["characters", "locations", "items", "scenes", "events"]


@pytest.fixture
def test_campaign_markdown(tmp_path: Path) -> Path:
    """Copy canonical test campaign to a temp directory for testing."""
    dst = tmp_path / "markdown"
    shutil.copytree(CAMPAIGN_ROOT, dst)
    return dst


# Test: fixture directory exists and has expected subdirectories
def test_fixture_directory_structure():
    """The test campaign root exists and contains all expected type subdirectories."""
    ...


# Test: all entity .md files have valid YAML frontmatter
def test_all_entity_files_have_valid_frontmatter(test_campaign_markdown):
    """Every .md file directly inside a type subdirectory has parseable YAML frontmatter."""
    ...


# Test: all entity files can be deserialized via frontmatter_dict_to_entity
def test_all_entity_files_deserialize(test_campaign_markdown):
    """Every entity .md file produces a valid Entity via frontmatter_dict_to_entity."""
    ...


# Test: all memory .md files in .d/ directories have valid frontmatter
def test_all_memory_files_have_valid_frontmatter(test_campaign_markdown):
    """Every .md file inside a .d/ companion directory has parseable YAML frontmatter."""
    ...


# Test: all memory files can be deserialized via frontmatter_dict_to_memory
def test_all_memory_files_deserialize(test_campaign_markdown):
    """Every memory .md file produces a valid Memory via frontmatter_dict_to_memory."""
    ...


# Test: expected entity counts match
def test_expected_entity_counts(test_campaign_markdown):
    """The fixture contains exactly: 2 characters, 3 locations, 2 items, 2 scenes, 1 event."""
    ...


# Test: expected memory counts match
def test_expected_memory_counts(test_campaign_markdown):
    """The fixture contains exactly 6 memory files across all .d/ directories."""
    ...


# Test: chatlog.log exists for Tavern_Brawl scene
def test_chatlog_exists_for_tavern_brawl(test_campaign_markdown):
    """The Tavern_Brawl.d/ directory contains a chatlog.log file with multiple lines."""
    ...


# Test: chatlog.log format matches expected pattern
def test_chatlog_format(test_campaign_markdown):
    """Each line in chatlog.log matches [timestamp] (character_id) Name: 'message' pattern."""
    ...


# Test: character references valid location_id
def test_character_location_references(test_campaign_markdown):
    """Characters with location_id reference IDs that appear in location entity files."""
    ...


# Test: character inventory references valid item IDs
def test_character_inventory_references(test_campaign_markdown):
    """Characters with inventory items reference IDs that appear in item entity files."""
    ...


# Test: location connected_locations form expected triangle
def test_location_connectivity(test_campaign_markdown):
    """The three locations have connected_locations forming a triangle (each references two others)."""
    ...


# Test: scene location_id references valid location
def test_scene_location_references(test_campaign_markdown):
    """Scenes with location_id reference IDs that appear in location entity files."""
    ...


# Test: event scene_id references valid scene
def test_event_scene_references(test_campaign_markdown):
    """Events reference scene_id values that appear in scene entity files."""
    ...


# Test: memory owner_id and target_id reference valid entities
def test_memory_entity_references(test_campaign_markdown):
    """Memory owner_id and target_id values reference entity IDs found in the fixture."""
    ...


# Test: companion .d/ directories share stem with parent .md file
def test_dot_d_naming_matches_parent(test_campaign_markdown):
    """Every .d/ directory has a corresponding .md file with the same stem in the same type subdir."""
    ...
```

### Key testing principles

- The `test_campaign_markdown` fixture copies the data to `tmp_path` so tests never modify the checked-in fixture.
- Tests import `frontmatter_dict_to_entity` and `frontmatter_dict_to_memory` from section-02 to validate deserialization. If section-02 is not yet implemented, these tests will fail with import errors -- that is expected and acceptable.
- The tests validate referential integrity within the fixture itself (e.g., `location_id` in a character frontmatter matches an actual location entity ID).
- The YAML frontmatter parsing can be done with `yaml.safe_load()` after extracting between `---` delimiters.

---

## Implementation Details

### Directory Tree

Create the following directory structure under `/home/harald/src/sidestage/data/test_campaign/markdown/`:

```
data/test_campaign/markdown/
├── characters/
│   ├── Eldric_the_Bold.md
│   ├── Eldric_the_Bold.d/
│   │   ├── mem_tavern_brawl.md
│   │   └── mem_knows_alice.md
│   ├── Alice_the_Merchant.md
│   └── Alice_the_Merchant.d/
│       └── mem_trade_secret.md
├── locations/
│   ├── The_Rusty_Tavern.md
│   ├── The_Rusty_Tavern.d/
│   │   └── mem_haunted_history.md
│   ├── Castle_Blackmoor.md
│   ├── Castle_Blackmoor.d/
│   │   └── mem_castle_legend.md
│   └── Town_Square.md
├── items/
│   ├── Flame_Tongue_Sword.md
│   └── Healing_Potion.md
├── scenes/
│   ├── Tavern_Brawl.md
│   ├── Tavern_Brawl.d/
│   │   ├── chatlog.log
│   │   └── mem_brawl_outcome.md
│   └── Castle_Audience.md
└── events/
    └── Eldric_Joins_Brawl.md
```

### Entity IDs

Use consistent, human-readable IDs throughout the fixture. These IDs are referenced across entities and memories for referential integrity.

| Entity | ID | Type |
|---|---|---|
| Eldric the Bold | `char_eldric` | Character |
| Alice the Merchant | `char_alice` | Character |
| The Rusty Tavern | `loc_rusty_tavern` | Location |
| Castle Blackmoor | `loc_castle_blackmoor` | Location |
| Town Square | `loc_town_square` | Location |
| Flame Tongue Sword | `item_flame_tongue` | Item |
| Healing Potion | `item_healing_potion` | Item |
| Tavern Brawl | `scene_tavern_brawl` | Scene |
| Castle Audience | `scene_castle_audience` | Scene |
| Eldric Joins Brawl | `event_eldric_joins` | JoinEvent |

### Memory IDs

| Memory | ID | Type | Visibility | Owner | Target |
|---|---|---|---|---|---|
| Tavern brawl recollection | `mem_tavern_brawl` | scene | private | `char_eldric` | `scene_tavern_brawl` |
| Knows Alice | `mem_knows_alice` | character | common | `char_eldric` | `char_alice` |
| Trade secret | `mem_trade_secret` | world_fact | private | `char_alice` | `loc_rusty_tavern` |
| Haunted history | `mem_haunted_history` | world_fact | common | null | `loc_rusty_tavern` |
| Brawl outcome | `mem_brawl_outcome` | scene | common | null | `scene_tavern_brawl` |
| Castle legend | `mem_castle_legend` | world_fact | common | null | `loc_castle_blackmoor` |

### Relationship Coverage

The fixture exercises the following relationships:

- **LOCATED_IN**: `char_eldric` -> `loc_rusty_tavern` (via `location_id: loc_rusty_tavern` in Eldric's frontmatter)
- **LOCATED_IN**: `char_alice` has no `location_id` (tests optional field)
- **CONNECTS_TO**: Triangle between all three locations. Each location's `connected_locations` lists the other two. This tests CONNECTS_TO deduplication during import (A->B and B->A should produce one bidirectional edge, not two).
- **AT_LOCATION**: `scene_tavern_brawl` -> `loc_rusty_tavern` (via `location_id: loc_rusty_tavern`)
- **AT_LOCATION**: `scene_castle_audience` -> `loc_castle_blackmoor`
- **HAS_EVENT**: `event_eldric_joins` -> `scene_tavern_brawl` (via `scene_id: scene_tavern_brawl`)
- **HAS_MEMORY / ABOUT**: Each memory has `target_id` pointing to the entity it is about, and some have `owner_id` pointing to the entity that "owns" the memory
- **Inventory**: `char_eldric` has `inventory: [item_flame_tongue]`. `item_healing_potion` is standalone (not in anyone's inventory).

---

### File Contents

Each file below should be created exactly as shown. The frontmatter follows the canonical format: `name`, `id`, `type` first, then remaining fields in alphabetical order. The `body` field is the markdown section below the `---` delimiter (not in frontmatter).

#### `/home/harald/src/sidestage/data/test_campaign/markdown/characters/Eldric_the_Bold.md`

```markdown
---
name: "Eldric the Bold"
id: "char_eldric"
type: "Character"
inventory:
- "item_flame_tongue"
location_id: "loc_rusty_tavern"
unseen: false
---

A brave warrior who frequents the Rusty Tavern. Known for his fiery temper and his legendary Flame Tongue Sword. He has been involved in more tavern brawls than he can count.
```

#### `/home/harald/src/sidestage/data/test_campaign/markdown/characters/Alice_the_Merchant.md`

```markdown
---
name: "Alice the Merchant"
id: "char_alice"
type: "Character"
inventory: []
location_id: null
unseen: false
---

A shrewd merchant who trades in rare goods across the realm. She knows secrets about every market town and has connections in both high and low places.
```

#### `/home/harald/src/sidestage/data/test_campaign/markdown/characters/Eldric_the_Bold.d/mem_tavern_brawl.md`

```markdown
---
id: "mem_tavern_brawl"
memory_type: "scene"
visibility: "private"
owner_id: "char_eldric"
target_id: "scene_tavern_brawl"
gametime: 3600
created_at: 1706000000.0
updated_at: 1706000000.0
access_count: 0
last_accessed_at: null
---

Eldric remembers the tavern brawl vividly. A group of mercenaries insulted his honor, and he responded with his fists before drawing his sword. The tavern keeper was not pleased.
```

#### `/home/harald/src/sidestage/data/test_campaign/markdown/characters/Eldric_the_Bold.d/mem_knows_alice.md`

```markdown
---
id: "mem_knows_alice"
memory_type: "character"
visibility: "common"
owner_id: "char_eldric"
target_id: "char_alice"
gametime: 1800
created_at: 1705900000.0
updated_at: 1705900000.0
access_count: 2
last_accessed_at: 1706000000.0
---

Eldric met Alice at the Town Square market. She sold him a healing potion at a fair price, and they have been on good terms since. He trusts her judgment on matters of trade.
```

#### `/home/harald/src/sidestage/data/test_campaign/markdown/characters/Alice_the_Merchant.d/mem_trade_secret.md`

```markdown
---
id: "mem_trade_secret"
memory_type: "world_fact"
visibility: "private"
owner_id: "char_alice"
target_id: "loc_rusty_tavern"
gametime: 900
created_at: 1705800000.0
updated_at: 1705800000.0
access_count: 1
last_accessed_at: 1705900000.0
---

Alice discovered that the Rusty Tavern has a hidden cellar where smuggled goods are stored. The tavern keeper pays well for discretion about this arrangement.
```

#### `/home/harald/src/sidestage/data/test_campaign/markdown/locations/The_Rusty_Tavern.md`

```markdown
---
name: "The Rusty Tavern"
id: "loc_rusty_tavern"
type: "Location"
connected_locations:
- "loc_castle_blackmoor"
- "loc_town_square"
---

A weathered tavern at the crossroads, known for its cheap ale and frequent brawls. The sign above the door depicts a rusted sword crossed with a tankard. Despite its rough reputation, it serves as a gathering place for adventurers and merchants alike.
```

#### `/home/harald/src/sidestage/data/test_campaign/markdown/locations/The_Rusty_Tavern.d/mem_haunted_history.md`

```markdown
---
id: "mem_haunted_history"
memory_type: "world_fact"
visibility: "common"
owner_id: null
target_id: "loc_rusty_tavern"
gametime: null
created_at: 1705700000.0
updated_at: 1705700000.0
access_count: 0
last_accessed_at: null
---

The Rusty Tavern was built on the site of an old battlefield. Locals say that on moonless nights, the sounds of clashing swords can be heard from the cellar. The tavern keeper dismisses these stories, but refuses to go downstairs after dark.
```

#### `/home/harald/src/sidestage/data/test_campaign/markdown/locations/Castle_Blackmoor.md`

```markdown
---
name: "Castle Blackmoor"
id: "loc_castle_blackmoor"
type: "Location"
connected_locations:
- "loc_rusty_tavern"
- "loc_town_square"
---

A imposing fortress perched on a rocky hill overlooking the valley. Castle Blackmoor has served as the seat of power for the local lord for generations. Its black stone walls are said to be impervious to siege.
```

#### `/home/harald/src/sidestage/data/test_campaign/markdown/locations/Castle_Blackmoor.d/mem_castle_legend.md`

```markdown
---
id: "mem_castle_legend"
memory_type: "world_fact"
visibility: "common"
owner_id: null
target_id: "loc_castle_blackmoor"
gametime: null
created_at: 1705600000.0
updated_at: 1705600000.0
access_count: 0
last_accessed_at: null
---

Legend has it that Castle Blackmoor was built by a dragon who took human form. The black stone of its walls is said to be dragon scale, transmuted into rock by ancient magic. Some claim the dragon still sleeps beneath the castle foundations.
```

#### `/home/harald/src/sidestage/data/test_campaign/markdown/locations/Town_Square.md`

```markdown
---
name: "Town Square"
id: "loc_town_square"
type: "Location"
connected_locations:
- "loc_rusty_tavern"
- "loc_castle_blackmoor"
---

The bustling center of town, where merchants hawk their wares and townsfolk gather to exchange news. A large stone fountain stands in the middle, carved with scenes from the town's founding. Market day brings traders from across the region.
```

#### `/home/harald/src/sidestage/data/test_campaign/markdown/items/Flame_Tongue_Sword.md`

```markdown
---
name: "Flame Tongue Sword"
id: "item_flame_tongue"
type: "Item"
---

A magnificent longsword with a blade that glows with inner fire. When drawn in anger, flames lick along its edge, casting dancing shadows. It was forged by a master smith who infused it with the essence of a fire elemental.
```

#### `/home/harald/src/sidestage/data/test_campaign/markdown/items/Healing_Potion.md`

```markdown
---
name: "Healing Potion"
id: "item_healing_potion"
type: "Item"
---

A small glass vial filled with a shimmering red liquid. When consumed, it mends wounds and restores vitality. This particular potion was brewed by a traveling alchemist and purchased by Alice the Merchant.
```

#### `/home/harald/src/sidestage/data/test_campaign/markdown/scenes/Tavern_Brawl.md`

```markdown
---
name: "Tavern Brawl"
id: "scene_tavern_brawl"
type: "Scene"
current_gametime: 7200
events:
- "event_eldric_joins"
location_id: "loc_rusty_tavern"
---

A chaotic brawl erupts in the Rusty Tavern after a group of mercenaries challenge the locals. Tables are overturned, tankards fly through the air, and the tavern keeper shouts for order that nobody heeds.
```

Note: The `messages` field is deliberately excluded from the frontmatter. Messages come from `chatlog.log` in the companion `.d/` directory, not from the entity frontmatter.

#### `/home/harald/src/sidestage/data/test_campaign/markdown/scenes/Tavern_Brawl.d/chatlog.log`

```
[2026-01-15T14:30:00Z] (char_eldric) Eldric the Bold: "I challenge you to a duel!"
[2026-01-15T14:30:05Z] (char_alice) Alice the Merchant: "You'll regret that, Eldric."
[2026-01-15T14:30:10Z] (char_eldric) Eldric the Bold: "A warrior never backs down from a fight!"
```

#### `/home/harald/src/sidestage/data/test_campaign/markdown/scenes/Tavern_Brawl.d/mem_brawl_outcome.md`

```markdown
---
id: "mem_brawl_outcome"
memory_type: "scene"
visibility: "common"
owner_id: null
target_id: "scene_tavern_brawl"
gametime: 7200
created_at: 1706100000.0
updated_at: 1706100000.0
access_count: 0
last_accessed_at: null
---

The tavern brawl ended when the town guard arrived and broke up the fighting. Several tables were destroyed and the tavern keeper demanded compensation. Eldric was recognized as the instigator but was let off with a warning due to his reputation.
```

#### `/home/harald/src/sidestage/data/test_campaign/markdown/scenes/Castle_Audience.md`

```markdown
---
name: "Castle Audience"
id: "scene_castle_audience"
type: "Scene"
current_gametime: null
events: []
location_id: "loc_castle_blackmoor"
---

A formal audience with the lord of Castle Blackmoor. The great hall is lit by flickering torches, and the lord sits upon a throne of black stone. Petitioners line up to present their cases and seek the lord's judgment.
```

This scene has no companion `.d/` directory because it has no memories and no chat log.

#### `/home/harald/src/sidestage/data/test_campaign/markdown/events/Eldric_Joins_Brawl.md`

```markdown
---
name: "Eldric Joins Brawl"
id: "event_eldric_joins"
type: "JoinEvent"
actor_id: "char_eldric"
gametime: 3600
scene_id: "scene_tavern_brawl"
walltime: "2026-01-15T14:30:00Z"
---

Eldric the Bold strides into the Rusty Tavern and immediately joins the brawl, drawing his Flame Tongue Sword with a battle cry.
```

---

### Coverage Summary

The test campaign exercises every aspect of the import/backup system:

**Entity types**: All five types (Character, Location, Item, Scene, Event) plus one Event subtype (JoinEvent).

**Optional and required fields**:
- Character with all fields set (`char_eldric`: `location_id`, `inventory`, `unseen`)
- Character with optional fields at defaults (`char_alice`: no `location_id`, empty `inventory`)
- Location with `connected_locations` populated (all three)
- Location with no companion directory (`Town_Square` -- no memories)
- Scene with `current_gametime` set and `events` populated (`Tavern_Brawl`)
- Scene with `current_gametime: null` and empty `events` (`Castle_Audience`)
- Scene with chat log and memories (Tavern_Brawl) vs. bare scene (Castle_Audience)

**Memory types**: All three `MemoryType` values:
- `scene`: `mem_tavern_brawl`, `mem_brawl_outcome`
- `character`: `mem_knows_alice`
- `world_fact`: `mem_trade_secret`, `mem_haunted_history`, `mem_castle_legend`

**Memory visibility**: Both `private` and `common`.

**Memory ownership**: Memories with `owner_id` set (placed in owner's `.d/`) and memories with `owner_id: null` (placed in target's `.d/`).

**Relationships tested during import**:
- `LOCATED_IN`: Eldric at the Rusty Tavern
- `CONNECTS_TO`: Triangle of three locations (6 directional references, should produce 3 deduplicated edges)
- `AT_LOCATION`: Both scenes at their respective locations
- `HAS_EVENT`: Eldric Joins Brawl event in Tavern Brawl scene
- `HAS_MEMORY` / `ABOUT`: All 6 memories with their target entities

**Chat log**: Multi-line with two speakers, timestamped, follows the `[timestamp] (character_id) Name: "message"` format.

**Edge cases covered**:
- Entity with no companion `.d/` directory (Town_Square, Castle_Audience, both items)
- Companion `.d/` with only memories (all character and location `.d/` dirs)
- Companion `.d/` with both chat log and memory (Tavern_Brawl.d/)
- Inventory referencing an item (`char_eldric` -> `item_flame_tongue`)
- Standalone item not in any inventory (`item_healing_potion`)

### Implementation Notes

- All files should be created with UTF-8 encoding and Unix-style line endings (LF, not CRLF).
- YAML frontmatter uses explicit quoting for string values that might be ambiguous (IDs, names).
- The `null` keyword in YAML represents Python `None` (for optional fields like `location_id`, `owner_id`, `gametime`, `last_accessed_at`).
- Timestamps in memory `created_at`/`updated_at` are Unix epoch floats, deliberately spread across a range to allow testing sort order.
- The `chatlog.log` file does not have YAML frontmatter. It is plain text with one line per message.
