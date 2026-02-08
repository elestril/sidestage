# Interview Transcript: Migration and Synchronization

## Q1: Source of Truth
**Question:** The codebase already has dual-path logic in WorldTools (graph_client check). Should the migration make FalkorDB the primary source of truth, with markdown files as an export/backup layer? Or should markdown remain primary with FalkorDB as a derived cache?

**Answer:** FalkorDB-primary. The graph DB is the source of truth; markdown files are generated exports for user editing/backup.

## Q2: File Watching / Sync Direction
**Question:** For the file watcher, should we watch the entities/ directory for external edits (e.g., user editing .md files in their text editor) and sync those changes into FalkorDB? Or is sync only needed from FalkorDB -> markdown export?

**Answer:** There should be explicit "backup campaign" and "import campaign" commands. Otherwise the campaign runs entirely off the DB. No real-time file watching or bidirectional sync needed.

## Q3: Chat Log Migration to Memories
**Question:** How should we handle the existing chat logs in SQLite for memory migration? Should we convert all historical chat messages to memory nodes with embeddings, or only create memories going forward?

**Answer:** Chat logs are never memories. They are indexed by scene, and can be retrieved as additional context. No chat-to-memory migration needed.

## Q4: Import Mode (Merge vs Replace)
**Question:** For the 'import campaign' command: should it handle merging (updating existing entities while preserving ones not in the import), or should it be a full replacement (wipe graph and reimport everything from markdown)?

**Answer:** For now: replace the whole campaign. Versioning/merging will be implemented later.

## Q5: Backup Scope
**Question:** For the 'backup campaign' command: should it export ALL entity types (Characters, Locations, Items, Scenes, Events) or just the core world-building entities?

**Answer:** All entities.

## Q6: Relationship Handling During Import
**Question:** When importing from markdown, should relationships be inferred from the YAML frontmatter fields (e.g., Character.location_id -> LOCATED_IN, Location.connected_locations -> CONNECTS_TO), or should relationships be stored separately?

**Answer:** Infer from frontmatter + validation. Parse location_id, inventory, connected_locations etc. and create graph relationships, but validate referential integrity during import.

## Q7: Building on Existing Code
**Question:** The existing import_entities() and export_entities() in campaign.py already do markdown <-> Pydantic model conversion. Should the new commands build on top of these existing functions?

**Answer:** Create a new, unified implementation. Don't extend the existing functions.

## Q8: Command Interface
**Question:** How should the import/backup commands be exposed? As CLI subcommands, API endpoints, or both?

**Answer:** As API endpoints, with temporary UI buttons. Security and access control is not yet a concern.

## Q9: Validation Error Handling
**Question:** What should happen when validation finds issues during import (e.g., a Character references a location_id that doesn't exist in the markdown files)?

**Answer:** Report then ask. Run validation first, report all issues, then ask user to proceed or abort.

## Q10: Graph Cleanup on Import
**Question:** For the 'replace' import: should it drop and recreate the FalkorDB graph entirely, or delete all Entity nodes while preserving the schema/indexes and Memory nodes?

**Answer:** Drop graph entirely. Delete the graph and recreate from scratch (loses all data including Memories).

## Q11: Backup Location
**Question:** Should the backup/export write to the existing entities/ directory in the campaign folder, or to a separate timestamped backup location?

**Answer:** entities/ directory. Overwrite the existing entities/ folder (same as current export_entities behavior).
