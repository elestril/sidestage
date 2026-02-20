# Track 07: Scene Membership — Implementation Plan

**Track:** 07-scene-membership
**Type:** Bug fix + Feature completion
**Approach:** TDD — tests first, then implementation, per section

---

## Section 01: Graph Query + Scene Fix (Backend Core)

### Goal

Add a `characters_in_scene()` graph query that returns characters connected to a scene via `PARTICIPATES_IN` edges, and fix `scene.py:activate()` to use it instead of loading all characters unconditionally. Scenes with no membership edges load zero characters.

### Files to Modify

| File | Change |
|---|---|
| `src/sidestage/graph/queries.py` | Add `characters_in_scene(client, scene_id) -> list[EntityModel]` |
| `src/sidestage/scene.py` | Fix `activate()` to call `characters_in_scene()` instead of `list_entities(type="Character")` |
| `tests/unit/test_graph_queries.py` | New unit tests for the query |
| `tests/integration/test_scene_membership.py` | Integration test for scene activation with membership filtering |

### Tests to Write

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

### Implementation Steps

1. Write and run unit tests for `characters_in_scene()` — they fail (no function yet).
2. Implement `characters_in_scene()` in `graph/queries.py`:
   - Cypher query: `MATCH (c:Entity:Character)-[:PARTICIPATES_IN]->(s:Entity:Scene {id: $scene_id}) RETURN c`
   - Parse results into `EntityModel` list using the same pattern as existing queries.
3. Run unit tests — they pass.
4. Write integration tests for `scene.py:activate()` — they fail.
5. Modify `scene.py:activate()`:
   - Replace the `list_entities(entity_type="Character")` call with `characters_in_scene(self.graph_client, self.scene_id)`.
   - Handle the non-graph fallback path: if `self.graph_client is None`, fall back to `self.storage.list_characters()` (preserve existing behavior for SQLite-only mode, noting this path doesn't support membership filtering).
6. Run integration tests — they pass.
7. Run full test suite to confirm no regressions.

### Acceptance Criteria

- `characters_in_scene()` is a public async function in `graph/queries.py`.
- `scene.py:activate()` only loads characters with `PARTICIPATES_IN` edges to the active scene.
- A scene with zero membership edges activates with an empty character list (no errors).
- All new tests pass; existing test suite has no regressions.

---

## Section 02: REST API + MCP Tools

### Goal

Expose scene membership management through REST endpoints (add/remove/list characters in a scene) and MCP tools (`join_scene`, `leave_scene`), wired through the orchestrator and MCP bridge.

### Files to Modify

| File | Change |
|---|---|
| `src/sidestage/orchestrator.py` | Add `POST /v1/scenes/{scene_id}/characters/{character_id}`, `DELETE /v1/scenes/{scene_id}/characters/{character_id}`, `GET /v1/scenes/{scene_id}/characters` endpoints |
| `src/sidestage/campaign.py` | Add `add_character_to_scene(scene_id, character_id)` and `remove_character_from_scene(scene_id, character_id)` and `list_scene_characters(scene_id)` methods |
| `src/sidestage/graph/relationships.py` | Ensure `create_relationship` / `delete_relationship` work for `PARTICIPATES_IN` (they should already since it's in `VALID_REL_TYPES`) |
| `src/sidestage/mcp_bridge.py` | Add `join_scene` and `leave_scene` MCP tools |
| `src/sidestage/sync.py` | Broadcast `scene_updated` event when cast changes |
| `tests/unit/test_scene_membership_api.py` | Unit tests for campaign methods |
| `tests/integration/test_scene_membership_api.py` | Integration tests for REST endpoints |

### Tests to Write

**Unit tests** (`tests/unit/test_scene_membership_api.py`):

| Test name | Verifies |
|---|---|
| `test_add_character_to_scene_creates_edge` | `campaign.add_character_to_scene()` creates a `PARTICIPATES_IN` edge |
| `test_add_character_to_scene_idempotent` | Adding the same character twice does not error or create duplicate edges |
| `test_remove_character_from_scene_deletes_edge` | `campaign.remove_character_from_scene()` removes the `PARTICIPATES_IN` edge |
| `test_remove_character_not_in_scene_no_error` | Removing a character not in the scene does not raise an exception |
| `test_list_scene_characters_returns_member_ids` | `campaign.list_scene_characters()` returns character entity IDs |

**Integration tests** (`tests/integration/test_scene_membership_api.py`):

| Test name | Verifies |
|---|---|
| `test_post_character_to_scene_201` | `POST /v1/scenes/{id}/characters/{char_id}` returns 201 and character is now in scene |
| `test_post_character_to_scene_idempotent_200` | Repeated POST returns 200 (already exists), no error |
| `test_delete_character_from_scene_200` | `DELETE /v1/scenes/{id}/characters/{char_id}` returns 200 and character is removed |
| `test_delete_character_not_in_scene_404` | DELETE for a character not in the scene returns 404 |
| `test_get_scene_characters_returns_list` | `GET /v1/scenes/{id}/characters` returns list of character entities |
| `test_get_scene_characters_empty_scene` | GET on scene with no members returns empty list |
| `test_scene_updated_broadcast_on_join` | WebSocket receives `scene_updated` event when a character is added |
| `test_scene_updated_broadcast_on_leave` | WebSocket receives `scene_updated` event when a character is removed |
| `test_mcp_join_scene_tool` | MCP `join_scene` tool creates PARTICIPATES_IN edge |
| `test_mcp_leave_scene_tool` | MCP `leave_scene` tool removes PARTICIPATES_IN edge |

### Implementation Steps

1. Write unit tests for `campaign.add_character_to_scene()`, `remove_character_from_scene()`, `list_scene_characters()` — they fail.
2. Implement the three methods in `campaign.py`:
   - `add_character_to_scene`: Call `graph.relationships.create_relationship(character_id, scene_id, "PARTICIPATES_IN")`. Broadcast `scene_updated` via `self.bus`.
   - `remove_character_from_scene`: Call `graph.relationships.delete_relationship(character_id, scene_id, "PARTICIPATES_IN")`. Broadcast `scene_updated`.
   - `list_scene_characters`: Call `graph.queries.characters_in_scene(client, scene_id)`.
3. Run unit tests — they pass.
4. Write integration tests for REST endpoints — they fail.
5. Add REST endpoints in `orchestrator.py`:
   - `POST /v1/scenes/{scene_id}/characters/{character_id}` → calls `campaign.add_character_to_scene()`, returns 201.
   - `DELETE /v1/scenes/{scene_id}/characters/{character_id}` → calls `campaign.remove_character_from_scene()`, returns 200.
   - `GET /v1/scenes/{scene_id}/characters` → calls `campaign.list_scene_characters()`, returns list.
6. Add MCP tools in `mcp_bridge.py`:
   - `join_scene(scene_id: str, character_id: str)` → delegates to `campaign.add_character_to_scene()`.
   - `leave_scene(scene_id: str, character_id: str)` → delegates to `campaign.remove_character_from_scene()`.
7. Ensure `scene_updated` WebSocket broadcast includes the scene ID so frontends can refresh.
8. Run integration tests — they pass.
9. Run full test suite.

### Acceptance Criteria

- All three REST endpoints are functional and return correct HTTP status codes.
- Both MCP tools are registered and functional.
- Adding/removing a character triggers a `scene_updated` WebSocket broadcast.
- Idempotent add (no error on duplicate), graceful remove (no error if not present or 404 as appropriate).
- All new tests pass; no regressions.

---

## Section 03: Default Seeding + Import/Export

### Goal

Ensure `PARTICIPATES_IN` edges are created during default campaign seeding (co-author character placed into campaign_planning scene), persisted during export, and restored during import for full round-trip fidelity.

### Files to Modify

| File | Change |
|---|---|
| `src/sidestage/campaign.py` | In default seeding logic, create `PARTICIPATES_IN` edge: co-author → campaign_planning scene |
| `src/sidestage/migration/importer.py` | After entity import, create `PARTICIPATES_IN` edges from parsed relationship data |
| `src/sidestage/migration/exporter.py` | Export `PARTICIPATES_IN` edges alongside other relationships |
| `tests/unit/test_default_seeding.py` | Test that seeding creates expected membership edges |
| `tests/unit/test_import_export_membership.py` | Round-trip tests for PARTICIPATES_IN edges |

### Tests to Write

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

### Implementation Steps

1. Write unit tests for default seeding — they fail.
2. Modify `campaign.py` default seeding:
   - After creating default entities, identify the co-author character ID and the campaign_planning scene ID.
   - Call `graph.relationships.create_relationship(co_author_id, campaign_planning_scene_id, "PARTICIPATES_IN")`.
3. Run seeding tests — they pass.
4. Write import/export round-trip tests — they fail.
5. Modify `migration/exporter.py`:
   - When exporting relationships, ensure `PARTICIPATES_IN` edges are included in the exported data. Check if the existing relationship export logic already covers this (since `PARTICIPATES_IN` is in `VALID_REL_TYPES`). If not, add explicit handling.
6. Modify `migration/importer.py`:
   - When importing relationships, ensure `PARTICIPATES_IN` edges are created. Again, check if the generic relationship import already handles this. If there's type-specific filtering that excludes it, add it.
7. Run import/export tests — they pass.
8. Run full test suite.

### Acceptance Criteria

- A fresh campaign seeded with defaults has the co-author character in the campaign_planning scene.
- Export produces `PARTICIPATES_IN` edges in the output.
- Import restores `PARTICIPATES_IN` edges from the exported data.
- Full round-trip: export → wipe → import → `characters_in_scene()` returns the same results.
- All new tests pass; no regressions.

---

## Section 04: Frontend

### Goal

Add scene membership management to the React frontend: a right sidebar with drag-and-drop to move characters into/out of the active scene, character count badges on the scene list, and live refresh via WebSocket `scene_updated` events.

### Files to Modify

| File | Change |
|---|---|
| `frontend/src/types.ts` | Add `character_ids: string[]` to the `Scene` type |
| `frontend/src/App.tsx` | Add scene right sidebar with character membership management |
| `frontend/src/components/SceneCastSidebar.tsx` | **New file**: Right sidebar component for scene character management |
| `frontend/src/components/SceneList.tsx` | Display character count badge per scene in the scene list |
| `frontend/src/api.ts` (or equivalent API layer) | Add `joinScene()`, `leaveScene()`, `getSceneCharacters()` API functions |

### Tests to Write

Frontend tests are typically lighter; focus on integration behavior:

| Test name | File | Verifies |
|---|---|---|
| `test_scene_cast_sidebar_renders_members` | Component test | Sidebar displays characters currently in the scene |
| `test_scene_cast_sidebar_renders_available` | Component test | Sidebar displays characters NOT in the scene as "available" |
| `test_drag_character_to_scene_calls_api` | Component test | Dragging a character into the cast area calls `POST /v1/scenes/{id}/characters/{char_id}` |
| `test_remove_character_calls_api` | Component test | Clicking remove on a cast member calls `DELETE /v1/scenes/{id}/characters/{char_id}` |
| `test_scene_list_shows_character_count` | Component test | Scene list items display the number of characters in each scene |
| `test_websocket_scene_updated_refreshes_cast` | Integration test | When a `scene_updated` WebSocket event arrives, the cast list re-fetches |

### Implementation Steps

1. Update `frontend/src/types.ts`:
   - Add `character_ids: string[]` field to the Scene interface.

2. Add API functions:
   - `joinScene(sceneId: string, characterId: string): Promise<void>` — POST to the new endpoint.
   - `leaveScene(sceneId: string, characterId: string): Promise<void>` — DELETE to the new endpoint.
   - `getSceneCharacters(sceneId: string): Promise<Entity[]>` — GET from the new endpoint.

3. Create `SceneCastSidebar.tsx` component:
   - Two panels: "Scene Cast" (top, characters in scene) and "Available Characters" (bottom, characters not in scene).
   - Drag-and-drop: dragging from Available to Cast calls `joinScene()`.
   - Drag-and-drop: dragging from Cast to Available calls `leaveScene()`.
   - Alternative: click-based add/remove buttons as a fallback for non-drag interactions.
   - Fetch cast on mount and when scene changes.

4. Wire into `App.tsx`:
   - Render `SceneCastSidebar` in the right sidebar area when a scene is active.
   - Pass active scene ID as a prop.

5. Update scene list component:
   - Display character count badge (e.g., "3 characters") using `character_ids.length` from the scene entity.

6. WebSocket integration:
   - Listen for `scene_updated` events.
   - When received, re-fetch the scene's character list to update the sidebar.

### Acceptance Criteria

- Right sidebar shows "Scene Cast" and "Available Characters" lists when a scene is active.
- Drag-and-drop moves characters between the two lists and calls the correct API endpoints.
- Scene list displays character count per scene.
- WebSocket `scene_updated` events trigger a UI refresh of the cast list.
- Existing scene functionality (chat, prose, entity editing) is unaffected.

---

## Section 05: Documentation + Dev Campaign Fix

### Goal

Update all relevant documentation to reflect the new scene membership feature, and apply the fix to the dev campaign by adding the co-author character to the campaign_planning scene via the new REST API.

### Files to Modify

| File | Change |
|---|---|
| `docs/http-api.md` | Document the 3 new REST endpoints and their request/response formats |
| `docs/features.md` | Update scene membership section to describe the feature as implemented |
| `docs/api/sidestage.graph.queries.md` | Document `characters_in_scene()` function |
| `docs/api/sidestage.scene.md` | Update `activate()` documentation to reflect membership filtering |
| `docs/api/sidestage.campaign.md` | Document `add_character_to_scene()`, `remove_character_from_scene()`, `list_scene_characters()` |
| `docs/api/sidestage.orchestrator.md` | Document new REST endpoints |
| `docs/api/sidestage.mcp_bridge.md` | Document `join_scene` and `leave_scene` MCP tools |
| `docs/api/sidestage.migration.importer.md` | Note PARTICIPATES_IN edge handling |
| `docs/api/sidestage.migration.exporter.md` | Note PARTICIPATES_IN edge handling |
| `docs/ui_structure.md` | Document SceneCastSidebar component |

### Tests to Write

No new code tests. Validation is manual/doc review.

| Verification | Method |
|---|---|
| All new endpoints documented in http-api.md | Manual review |
| All new Python functions documented in api/ docs | Manual review |
| Dev campaign has co-author in campaign_planning scene | Verify via `GET /v1/scenes/{campaign_planning_id}/characters` |

### Implementation Steps

1. Update `docs/http-api.md`:
   - Add Scene Membership section under the Scenes API area.
   - Document `POST /v1/scenes/{scene_id}/characters/{character_id}` (request: none, response: 201 with edge confirmation).
   - Document `DELETE /v1/scenes/{scene_id}/characters/{character_id}` (request: none, response: 200).
   - Document `GET /v1/scenes/{scene_id}/characters` (response: list of character entities).
   - Update the Scene data model to note `character_ids` computed field.

2. Update `docs/features.md`:
   - In the Scene section, describe membership filtering: scenes only load characters with `PARTICIPATES_IN` edges.
   - Note: empty scenes load zero characters.
   - Describe the REST API for managing membership.
   - Describe the drag-and-drop UI.

3. Update per-module API docs (`docs/api/`):
   - `sidestage.graph.queries.md`: Add `characters_in_scene(client, scene_id)` signature, return type, Cypher query used.
   - `sidestage.scene.md`: Update `activate()` to note it now uses `characters_in_scene()`.
   - `sidestage.campaign.md`: Add the three new methods with signatures and descriptions.
   - `sidestage.orchestrator.md`: Add the three new REST endpoint registrations.
   - `sidestage.mcp_bridge.md`: Add `join_scene` and `leave_scene` tool definitions.
   - `sidestage.migration.importer.md`: Note that `PARTICIPATES_IN` edges are created during import.
   - `sidestage.migration.exporter.md`: Note that `PARTICIPATES_IN` edges are included in export.

4. Update `docs/ui_structure.md`:
   - Document the SceneCastSidebar component, its location in the layout, and its props.

5. Apply dev campaign fix:
   - Use the new REST API to add the co-author character to the campaign_planning scene:
     ```
     POST /v1/scenes/{campaign_planning_scene_id}/characters/{co_author_character_id}
     ```
   - Verify with `GET /v1/scenes/{campaign_planning_scene_id}/characters` that the co-author appears.
   - Verify by opening the scene in the UI and confirming only the co-author responds in chat.

### Acceptance Criteria

- All new REST endpoints are fully documented in `docs/http-api.md`.
- All new/modified Python functions are documented in the corresponding `docs/api/*.md` files.
- `docs/features.md` describes scene membership as an implemented feature.
- `docs/ui_structure.md` includes the SceneCastSidebar component.
- The dev campaign's campaign_planning scene contains the co-author character.
- Opening the campaign_planning scene in the dev instance shows only the co-author responding (not all characters).

---

## Dependency Graph

```
Section 01 (Graph Query + Scene Fix)
    ↓
Section 02 (REST API + MCP Tools)  ← depends on Section 01 (uses characters_in_scene)
    ↓
Section 03 (Default Seeding + Import/Export)  ← depends on Section 02 (uses campaign methods)
    ↓
Section 04 (Frontend)  ← depends on Section 02 (calls REST endpoints)
    ↓
Section 05 (Documentation + Dev Fix)  ← depends on all prior sections
```

Sections 03 and 04 can be worked in parallel since they depend on Section 02 but not on each other. Section 05 must come last.

---

## Risk Notes

- **Graph fallback path**: `scene.py` has a non-graph codepath (`self.graph_client is None`) that falls back to SQLite's `list_characters()`. This path does not support membership filtering. The plan preserves it as-is for backward compatibility, but a warning log should be emitted if this path is taken.
- **Empty scene UX**: An empty scene (zero characters) will mean the AI co-author has nobody to speak as. The frontend should display a clear message ("No characters in this scene. Add characters to begin.") and the chat should still function for user-only messages.
- **PARTICIPATES_IN idempotency**: The `create_relationship` function must handle duplicate edges gracefully (MERGE semantics in Cypher rather than CREATE) to avoid graph pollution from repeated API calls.
