# Section 01: Graph Query + Scene Fix (Backend Core)

## Goal

Add a `characters_in_scene()` graph query that returns characters connected to a scene via `PARTICIPATES_IN` edges, and fix `scene.py:activate()` to use it instead of loading all characters unconditionally. Scenes with no membership edges load zero characters.

## Files to Modify

| File | Change |
|---|---|
| `src/sidestage/graph/queries.py` | Add `characters_in_scene(client, scene_id) -> list[EntityModel]` |
| `src/sidestage/scene.py` | Fix `activate()` to call `characters_in_scene()` instead of `list_entities(type="Character")` |
| `tests/unit/test_graph_queries.py` | New unit tests for the query |
| `tests/integration/test_scene_membership.py` | Integration test for scene activation with membership filtering |

## Tests to Write

**Unit tests** (`tests/unit/test_graph_queries.py`):

| Test name | Verifies |
|---|---|
| `test_characters_in_scene_returns_members` | Query returns only characters with `PARTICIPATES_IN` edges to the target scene |
| `test_characters_in_scene_empty_scene` | Query returns empty list when scene has no membership edges |
| `test_characters_in_scene_multiple_scenes_isolation` | Characters in scene A are not returned when querying scene B |
| `test_characters_in_scene_nonexistent_scene` | Query returns empty list (not an error) for a scene ID that doesn't exist |

**Integration tests** (`tests/integration/test_scene_membership.py`):

| Test name | Verifies |
|---|---|
| `test_activate_loads_only_scene_members` | After `activate()`, only characters with `PARTICIPATES_IN` edges are present in the scene's character list |
| `test_activate_empty_scene_loads_no_characters` | Scene with no edges activates successfully with zero characters |
| `test_activate_excludes_characters_from_other_scenes` | Characters assigned to scene B do not appear when scene A is activated |

## Implementation Steps

1. Write and run unit tests for `characters_in_scene()` — they fail (no function yet).
2. Implement `characters_in_scene()` in `graph/queries.py`:
   - Cypher query: `MATCH (c:Entity:Character)-[:PARTICIPATES_IN]->(s:Entity:Scene {id: $scene_id}) RETURN c`
   - Parse results into `EntityModel` list using the same pattern as existing queries.
3. Run unit tests — they pass.
4. Write integration tests for `scene.py:activate()` — they fail.
5. Modify `scene.py:activate()`:
   - Replace the `list_entities(entity_type="Character")` call with `characters_in_scene(self.graph_client, self.data.id)`.
   - Handle the non-graph fallback path: if `self.graph_client is None`, fall back to `self.storage.list_characters()` (preserve existing behavior for SQLite-only mode, noting this path doesn't support membership filtering).
6. Run integration tests — they pass.
7. Run full test suite to confirm no regressions.

## Acceptance Criteria

- `characters_in_scene()` is a public async function in `graph/queries.py`.
- `scene.py:activate()` only loads characters with `PARTICIPATES_IN` edges to the active scene.
- A scene with zero membership edges activates with an empty character list (no errors).
- All new tests pass; existing test suite has no regressions.
