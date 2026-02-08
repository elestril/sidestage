# `sidestage.migration.exporter`

Export campaign data from FalkorDB/SQLite to a structured markdown directory.

## Functions

### `export_campaign(campaign: Campaign) -> MigrationBackupResult` *async*

Backup all entities, memories, and chat logs to the markdown/ directory.

Reads from FalkorDB (entities, memories, relationships) and SQLite (chat logs).
Writes a structured markdown/ directory tree with atomic swap.

Args:
    campaign: The Campaign object (provides graph_client, storage, campaign_dir, health).

Returns:
    MigrationBackupResult with counts of written entities, memories, and chatlogs.
