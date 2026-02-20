# Track 07: Scene Membership — Research

## Bug Summary

Scenes load **ALL characters** instead of filtering by per-scene membership. The graph schema defines a `PARTICIPATES_IN` relationship type (Character → Scene) but it is never created, queried, or used during scene activation. The requirements spec (section 4.2) explicitly states Scene should have `characters: List of characters in the scene`.

## Root Cause

In `src/sidestage/scene.py` lines 127-131, the `activate()` method unconditionally loads all characters:

```python
if self.graph_client is not None:
    from sidestage.graph import list_entities
    all_chars = await list_entities(self.graph_client, entity_type="Character")
else:
    all_chars = self.storage.list_characters()
```

## PARTICIPATES_IN Usage Audit

| Location | Status | Notes |
|---|---|---|
| `src/sidestage/graph/relationships.py` line 28 | Defined | In `VALID_REL_TYPES` frozenset |
| `docs/features.md` line 30 | Documented | "Character present in a Scene" |
| Campaign default seeding (`campaign.py`) | **MISSING** | No edges created |
| Scene activation (`scene.py`) | **MISSING** | Not queried |
| Import (`migration/importer.py`) | **MISSING** | Not created during import |
| Export (`migration/exporter.py`) | **MISSING** | Not exported |
| Graph queries (`graph/queries.py`) | **MISSING** | No `characters_in_scene` function |

## Affected Files

1. `src/sidestage/scene.py` — activate() loads all characters
2. `src/sidestage/campaign.py` — default seeding doesn't create PARTICIPATES_IN edges
3. `src/sidestage/graph/queries.py` — missing `characters_in_scene` query
4. `src/sidestage/migration/importer.py` — doesn't create PARTICIPATES_IN edges
5. `src/sidestage/migration/exporter.py` — doesn't export PARTICIPATES_IN edges
6. `src/sidestage/orchestrator.py` — API endpoints for join/leave scene
7. `src/sidestage/mcp_bridge.py` — MCP tools for scene membership
8. Frontend scene right bar — already has character list UI with drag-and-drop
