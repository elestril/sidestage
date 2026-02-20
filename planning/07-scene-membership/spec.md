# Track 07: Scene Membership — Spec

**Type:** Bug fix + Feature completion
**Priority:** High — breaks scene isolation, all characters respond in all scenes

## Problem Statement

The requirements spec (section 4.2) defines `Scene.characters` as "List of characters in the scene." The graph schema defines `PARTICIPATES_IN` (Character → Scene) edges. Neither is implemented: `scene.py:activate()` loads ALL characters into every scene unconditionally.

This causes:
- All NPC characters respond to messages in every scene
- Memory context assembled for irrelevant characters
- No way to have scene-specific casts

## Scope

### In Scope

1. **Graph query**: New `characters_in_scene()` function using `PARTICIPATES_IN` edges
2. **Scene activation fix**: `scene.py:activate()` queries scene-specific characters instead of all
3. **Strict membership**: Scenes with no `PARTICIPATES_IN` edges load zero characters (only the user can chat)
4. **REST API endpoints**: Add/remove characters from scene cast
5. **MCP tools**: `join_scene` / `leave_scene` tools for the MCP bridge
6. **Default seeding**: `campaign.py` creates `PARTICIPATES_IN` edges when seeding defaults (co-author → campaign_planning)
7. **Import/export round-trip**: Importer creates `PARTICIPATES_IN` edges; exporter writes them
8. **Frontend**: Scene right sidebar with drag-and-drop to move characters in/out of the active scene cast
9. **WebSocket**: Broadcast `scene_updated` when cast changes so other clients refresh

### Out of Scope

- Scene-specific character prompts or role overrides
- Character visibility/permissions per scene
- SQLite fallback for scene membership (graph-only feature)

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Empty scene behavior | Load zero characters | Strict membership; no surprises |
| Data storage | `PARTICIPATES_IN` graph edges only | Already defined in schema; no SceneModel field needed |
| Scene list display | Show character count per scene | Quick visibility into cast composition |
| Frontend UX | Drag-and-drop in right sidebar | User's stated preference |
| API design | `POST/DELETE /v1/scenes/{id}/characters/{char_id}` | RESTful, explicit join/leave |

## API Changes

### New REST Endpoints

```
POST   /v1/scenes/{scene_id}/characters/{character_id}   — Add character to scene
DELETE /v1/scenes/{scene_id}/characters/{character_id}   — Remove character from scene
GET    /v1/scenes/{scene_id}/characters                  — List scene cast
```

### New MCP Tools

```
join_scene(scene_id, character_id)   — Create PARTICIPATES_IN edge
leave_scene(scene_id, character_id)  — Remove PARTICIPATES_IN edge
```

### Modified Responses

`GET /v1/scenes` and scene entities will include `character_ids: List[str]` populated from graph edges (read-only, computed field).

## Affected Files

| File | Change |
|---|---|
| `src/sidestage/graph/queries.py` | Add `characters_in_scene()` |
| `src/sidestage/scene.py` | Fix `activate()` to use `characters_in_scene()` |
| `src/sidestage/campaign.py` | Create PARTICIPATES_IN edges in default seeding |
| `src/sidestage/orchestrator.py` | Add REST endpoints for scene cast management |
| `src/sidestage/mcp_bridge.py` | Add `join_scene` / `leave_scene` MCP tools |
| `src/sidestage/migration/importer.py` | Create PARTICIPATES_IN edges during import |
| `src/sidestage/migration/exporter.py` | Export PARTICIPATES_IN edges |
| `frontend/src/App.tsx` | Right sidebar drag-and-drop character management |
| `frontend/src/types.ts` | Add `character_ids` to Scene type |
| `docs/http-api.md` | Document new endpoints |
| `docs/features.md` | Update scene membership documentation |
| `docs/api/sidestage.scene.md` | Update API docs |
