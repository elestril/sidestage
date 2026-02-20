# Section 05: Documentation + Dev Campaign Fix

## Goal

Update all relevant documentation to reflect the new scene membership feature, and apply the fix to the dev campaign by adding the co-author character to the campaign_planning scene via the new API.

## Files to Modify

| File | Change |
|---|---|
| `docs/http-api.md` | Document the 3 new REST endpoints |
| `docs/features.md` | Update scene membership description |
| `docs/api/sidestage.graph.queries.md` | Document `characters_in_scene()` |
| `docs/api/sidestage.scene.md` | Update `activate()` docs |
| `docs/api/sidestage.campaign.md` | Document new methods |
| `docs/api/sidestage.orchestrator.md` | Document new endpoints |
| `docs/api/sidestage.mcp_bridge.md` | Document new MCP tools |
| `docs/api/sidestage.migration.importer.md` | Note PARTICIPATES_IN handling |
| `docs/api/sidestage.migration.exporter.md` | Note PARTICIPATES_IN handling |
| `docs/ui_structure.md` | Document SceneCastSidebar |

## Implementation Steps

1. Update `docs/http-api.md` with Scene Membership endpoints.
2. Update `docs/features.md` with membership description.
3. Update per-module API docs in `docs/api/`.
4. Update `docs/ui_structure.md` with SceneCastSidebar.
5. Apply dev campaign fix: add co-author to campaign_planning scene via MCP `join_scene` tool.

## Acceptance Criteria

- All new endpoints documented in `docs/http-api.md`.
- All new Python functions documented in `docs/api/`.
- Dev campaign has co-author in campaign_planning scene.
