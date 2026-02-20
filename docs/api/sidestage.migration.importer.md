# `sidestage.migration.importer`

Import parsed campaign data into FalkorDB, replacing the existing graph.

## Functions

### `import_campaign(campaign: Campaign, parse_result: ParseResult, active_scenes: dict[str, Any] | None = None) -> MigrationImportResult` *async*

Import parsed entities and memories into FalkorDB, replacing the existing graph.

This is a destructive operation: the existing graph is dropped and recreated.

Args:
    campaign: The Campaign object (provides graph_client, storage, health, config).
    parse_result: The parsed directory tree (entities, memories, chatlogs, errors).
    active_scenes: Optional dict of active scenes to clear after import.

Returns:
    MigrationImportResult with counts of processed entities and memories.

Handles `PARTICIPATES_IN` edges: for each `SceneModel` with `character_ids`,
creates `PARTICIPATES_IN` edges from each character to the scene.
