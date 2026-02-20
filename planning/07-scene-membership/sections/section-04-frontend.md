# Section 04: Frontend

## Goal

Add scene membership management to the React frontend: a right sidebar with drag-and-drop to move characters into/out of the active scene, character count badges on the scene list, and live refresh via WebSocket `scene_updated` events.

## Files to Modify

| File | Change |
|---|---|
| `frontend/src/types.ts` | Add `character_ids: string[]` to the `Scene` type |
| `frontend/src/App.tsx` | Add scene right sidebar with character membership management |
| `frontend/src/components/SceneCastSidebar.tsx` | **New file**: Right sidebar component for scene character management |
| `frontend/src/AppContext.tsx` | Add `joinScene()`, `leaveScene()`, `getSceneCharacters()` API functions |

## Tests to Write

| Test name | Verifies |
|---|---|
| `test_scene_cast_sidebar_renders_members` | Sidebar displays characters currently in the scene |
| `test_scene_cast_sidebar_renders_available` | Sidebar displays characters NOT in the scene as "available" |
| `test_drag_character_to_scene_calls_api` | Dragging a character into the cast area calls `POST /v1/scenes/{id}/characters/{char_id}` |
| `test_remove_character_calls_api` | Clicking remove on a cast member calls `DELETE /v1/scenes/{id}/characters/{char_id}` |
| `test_scene_list_shows_character_count` | Scene list items display the number of characters in each scene |
| `test_websocket_scene_updated_refreshes_cast` | When a `scene_updated` WebSocket event arrives, the cast list re-fetches |

## Implementation Steps

1. Update `frontend/src/types.ts`:
   - Add `character_ids: string[]` field to the Scene interface.
2. Add API functions in AppContext or a dedicated api module:
   - `joinScene(sceneId: string, characterId: string): Promise<void>` — POST.
   - `leaveScene(sceneId: string, characterId: string): Promise<void>` — DELETE.
   - `getSceneCharacters(sceneId: string): Promise<Entity[]>` — GET.
3. Create `SceneCastSidebar.tsx` component:
   - Two panels: "Scene Cast" (top) and "Available Characters" (bottom).
   - Drag-and-drop: dragging from Available to Cast calls `joinScene()`.
   - Drag-and-drop: dragging from Cast to Available calls `leaveScene()`.
   - Click-based add/remove buttons as fallback.
4. Wire into `App.tsx`:
   - Render `SceneCastSidebar` in the right sidebar area.
5. WebSocket integration:
   - Listen for `scene_updated` events, re-fetch scene characters.

## Acceptance Criteria

- Right sidebar shows "Scene Cast" and "Available Characters" lists when a scene is active.
- Drag-and-drop moves characters between the two lists and calls the correct API endpoints.
- Scene list displays character count per scene.
- WebSocket `scene_updated` events trigger a UI refresh of the cast list.
- Existing scene functionality is unaffected.
