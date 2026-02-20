# Section 02: REST API + MCP Tools

## Goal

Expose scene membership management through REST endpoints (add/remove/list characters in a scene) and MCP tools (`join_scene`, `leave_scene`), wired through the orchestrator and MCP bridge.

## Files to Modify

| File | Change |
|---|---|
| `src/sidestage/orchestrator.py` | Add `POST /v1/scenes/{scene_id}/characters/{character_id}`, `DELETE /v1/scenes/{scene_id}/characters/{character_id}`, `GET /v1/scenes/{scene_id}/characters` endpoints |
| `src/sidestage/campaign.py` | Add `add_character_to_scene(scene_id, character_id)` and `remove_character_from_scene(scene_id, character_id)` and `list_scene_characters(scene_id)` methods |
| `src/sidestage/mcp_bridge.py` | Add `join_scene` and `leave_scene` MCP tools |
| `tests/unit/test_scene_membership_api.py` | Unit tests for campaign methods |
| `tests/integration/test_scene_membership_api.py` | Integration tests for REST endpoints |

## Tests to Write

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

## Implementation Steps

1. Write unit tests for `campaign.add_character_to_scene()`, `remove_character_from_scene()`, `list_scene_characters()` — they fail.
2. Implement the three methods in `campaign.py`:
   - `add_character_to_scene`: Call `graph.relationships.link(character_id, "PARTICIPATES_IN", scene_id)`. Broadcast `scene_updated`.
   - `remove_character_from_scene`: Call `graph.relationships.unlink(character_id, "PARTICIPATES_IN", scene_id)`. Broadcast `scene_updated`.
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

## Acceptance Criteria

- All three REST endpoints are functional and return correct HTTP status codes.
- Both MCP tools are registered and functional.
- Adding/removing a character triggers a `scene_updated` WebSocket broadcast.
- Idempotent add (no error on duplicate), graceful remove (no error if not present or 404 as appropriate).
- All new tests pass; no regressions.
