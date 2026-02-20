# Section 03: Default Seeding + Import/Export

## Goal

Ensure `PARTICIPATES_IN` edges are created during default campaign seeding (co-author character placed into campaign_planning scene), persisted during export, and restored during import for full round-trip fidelity.

## Files to Modify

| File | Change |
|---|---|
| `src/sidestage/campaign.py` | In default seeding logic, create `PARTICIPATES_IN` edge: co-author → campaign_planning scene |
| `src/sidestage/migration/importer.py` | After entity import, create `PARTICIPATES_IN` edges from parsed relationship data |
| `src/sidestage/migration/exporter.py` | Export `PARTICIPATES_IN` edges alongside other relationships |
| `tests/unit/test_default_seeding.py` | Test that seeding creates expected membership edges |
| `tests/unit/test_import_export_membership.py` | Round-trip tests for PARTICIPATES_IN edges |

## Tests to Write

**Unit tests** (`tests/unit/test_default_seeding.py`):

| Test name | Verifies |
|---|---|
| `test_default_seeding_creates_participates_in_edge` | After campaign default seeding, a `PARTICIPATES_IN` edge exists from the co-author character to the campaign_planning scene |
| `test_default_seeding_co_author_in_campaign_planning` | `characters_in_scene(campaign_planning_id)` returns the co-author character after seeding |

**Unit tests** (`tests/unit/test_import_export_membership.py`):

| Test name | Verifies |
|---|---|
| `test_export_includes_participates_in_edges` | Exporter output includes `PARTICIPATES_IN` relationship entries |
| `test_import_creates_participates_in_edges` | After import, `PARTICIPATES_IN` edges exist in the graph |
| `test_import_export_round_trip_preserves_membership` | Export → clear → import → verify same characters in same scenes |
| `test_import_validates_participates_in_references` | Import validation warns/errors if PARTICIPATES_IN references nonexistent entity IDs |

## Implementation Steps

1. Write unit tests for default seeding — they fail.
2. Modify `campaign.py` default seeding:
   - After creating default entities, identify the co-author character ID and the campaign_planning scene ID.
   - Call `graph.relationships.link(co_author_id, "PARTICIPATES_IN", campaign_planning_scene_id)`.
3. Run seeding tests — they pass.
4. Write import/export round-trip tests — they fail.
5. Modify `migration/exporter.py`:
   - When exporting relationships, include `PARTICIPATES_IN` edges in the exported data.
6. Modify `migration/importer.py`:
   - When importing relationships, create `PARTICIPATES_IN` edges.
7. Run import/export tests — they pass.
8. Run full test suite.

## Acceptance Criteria

- A fresh campaign seeded with defaults has the co-author character in the campaign_planning scene.
- Export produces `PARTICIPATES_IN` edges in the output.
- Import restores `PARTICIPATES_IN` edges from the exported data.
- Full round-trip: export → wipe → import → `characters_in_scene()` returns the same results.
- All new tests pass; no regressions.
