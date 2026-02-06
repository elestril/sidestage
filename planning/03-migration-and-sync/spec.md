# Spec: Migration and Synchronization

## Overview
Implement bidirectional synchronization between markdown files and FalkorDB, including data migration from existing campaigns. This split integrates the FalkorDB foundation (split 01) and memory system (split 02) with the existing markdown-based storage, enabling a smooth transition to graph database while preserving user data and maintaining real-time sync.

## Context & Requirements

### From Project Requirements (planning/requirements.md)
- **Section 2.3:** Markdown-first entities (current storage) transitioning to FalkorDB
- **Section 2.3:** File system storage: `~/.sidestage/<campaign_name>/`
- **Section 3.1:** Bidirectional synchronization between database and local Markdown files
- **Section 3.1:** Real-time synchronization of entity content across multiple connected clients via WebSockets
- **Section 4.1:** Event-driven message bus for change notifications
- Track 6 goal: "Transitioning primary storage to FalkorDB" (implies safe migration, not replacement)

### Existing Architecture Context
- Entity files: `characters/`, `locations/`, `items/`, `scenes/` directories with `.md` files
- YAML frontmatter for structured data (id, name, type, relationships)
- Markdown body for rich descriptions
- WebSocket infrastructure for real-time client sync (built in Track 3)
- Event bus for ChatMessage, JoinEvent, LeaveEvent, etc.
- SQLite for chat logs (separate from entity storage)

### Design Principles
- **Preserve data:** No data loss during migration
- **Bidirectional:** Changes in markdown files sync to graph, and vice versa
- **Non-disruptive:** Can run alongside existing markdown-first system during transition
- **Conflict resolution:** Handle concurrent edits from markdown and graph sources
- **Rollback capability:** Support reverting to markdown-only if needed
- **Event-driven:** Leverage existing message bus for consistency

## Key Decisions to Explore in Deep-Plan

### 1. Migration Strategy & Phases
- **Question:** How do we migrate existing campaigns to FalkorDB?
  - Option A: Batch migration (one-time import, then switch to FalkorDB-primary)
  - Option B: Dual-write phase (parallel operation, gradually retire markdown)
  - Option C: Markdown-primary with FalkorDB cache (markdown source of truth)
- **Question:** Rollback strategy if migration fails?
  - Keep markdown files as backup?
  - Version control for campaign data?
  - Point-in-time recovery?
- **Impact:** User data safety, complexity, transition timeline
- **Design considerations:**
  - Existing campaigns may have malformed or inconsistent data
  - Users may be actively editing during migration
  - Must not block gameplay during transition

### 2. Bidirectional Sync Architecture
- **Question:** What is the source of truth?
  - FalkorDB-primary: Markdown files are cache/export
  - Markdown-primary: FalkorDB is derived copy
  - Hybrid: Depends on operation (split by entity type, operation type?)
- **Question:** How do we detect changes?
  - File system watcher for markdown file changes (fswatch library)?
  - FalkorDB hooks/triggers for graph changes?
  - Event bus subscription for all writes?
- **Question:** How do we handle conflicts?
  - Last-write-wins?
  - Timestamp-based resolution?
  - Manual conflict resolution UI?
  - Merge strategies?
- **Impact:** Complexity, data consistency guarantees, user experience
- **Design considerations:**
  - Real-time WebSocket clients must see consistent view
  - Multiple editors could update same file/entity concurrently
  - Network partitions could create temporary divergence

### 3. Data Transformation & Validation
- **Question:** How do we map markdown YAML ↔ FalkorDB nodes?
  - Character.md → Character node + location_id relationship + inventory relationships
  - Scene.md → Scene node + character relationships + event relationships
  - Transform logic: Markdown parser → domain model → FalkorDB nodes
- **Question:** Validation during migration?
  - Schema validation (required fields present)?
  - Referential integrity (location_id points to valid location)?
  - Data type coercion (gametime must be float)?
  - Cleanup of invalid/orphaned data?
- **Impact:** Data quality, migration success rate, error handling
- **Design considerations:**
  - YAML parsing errors in existing files
  - Missing or broken references
  - Type inconsistencies (some gametimes as int, others as float)

### 4. Memory Node Creation from Events
- **Question:** How do we create memory nodes from existing event history?
  - Migrate SQLite chat logs → memory nodes with embeddings
  - Migrate scene events (JoinEvent, LeaveEvent) → memory nodes
  - Extract facts from character descriptions → memory nodes?
- **Question:** Temporal consistency?
  - Memories need accurate timestamps for context assembly
  - Which events to include? All or filtered?
- **Impact:** Memory quality, context relevance, storage requirements
- **Design considerations:**
  - Chat logs may be large (months of messages)
  - Memory creation requires embedding generation (potentially expensive)
  - Batch processing needed for performance

### 5. Real-Time Sync Protocol
- **Question:** How do we propagate changes to connected clients?
  - Existing WebSocket infrastructure (built in Track 3)
  - New sync messages for graph updates?
  - How to handle client conflicts (user A edits markdown, user B edits graph)?
- **Question:** Ordering & causality?
  - Ensure clients receive updates in consistent order
  - Vector clocks or lamport timestamps for ordering?
- **Impact:** Client coherence, latency, complexity
- **Design considerations:**
  - Multiple clients may be viewing same scene/entity
  - Edits from web UI vs CLI vs markdown file
  - WebSocket reconnection and catch-up

### 6. Operational Concerns
- **Question:** Monitoring & observability?
  - How do we track migration progress?
  - Alert on sync failures or divergence?
  - Audit trail of changes?
- **Question:** Performance during migration?
  - Bulk import of entities/memories could be slow
  - Concurrent file watching + WebSocket updates + embedding generation
  - Parallel processing strategy?
- **Question:** Cleanup after migration?
  - Keep markdown files as read-only archive?
  - Delete after successful migration?
  - Dual-storage for safety period?
- **Impact:** Deployment risk, user confidence, storage requirements

## Scope & Deliverables

### In Scope
- Data migration script for entities from markdown → FalkorDB
- Data migration for chat logs → memory nodes (with embeddings via split 02)
- Bidirectional change detection (markdown files ↔ FalkorDB)
- Sync engine to propagate changes between storage layers
- WebSocket integration to broadcast changes to clients
- Conflict detection and resolution strategies
- Rollback mechanisms for recovery
- Data validation and integrity checks
- Migration progress tracking and logging
- Campaign-scoped migration (per campaign in `~/.sidestage/`)
- Unit and integration tests

### Out of Scope
- UI for manual conflict resolution (can be added later)
- Incremental/streaming migration (one-time batch OK for now)
- Full audit trail with change history (can layer on later)
- Performance optimization beyond basic parallelization
- Markdown export/download features (can add later if needed)

## API Surface (Preliminary)

### Migration Orchestration
```python
async def migrate_campaign(campaign_path: str, db_client, embedding_model) -> MigrationResult
    # Main entry point: orchestrates entity + memory migration
    # Returns: {entities_migrated, memories_created, errors, warnings}

async def migrate_entities(campaign_path: str, db_client) -> list[str]  # entity_ids
async def migrate_memories(campaign_path: str, db_client, embedding_model) -> int  # count
async def rollback_migration(campaign_path: str) -> None  # restore markdown as primary
```

### Bidirectional Sync
```python
async def start_sync_watcher(campaign_path: str, db_client, emit_change_event: Callable) -> Watcher
    # Watches markdown files for changes, emits events

async def handle_entity_change(entity_id: str, source: "markdown" | "graph", updates: dict,
                              db_client) -> None
    # Syncs change from one source to the other

async def stop_sync_watcher(watcher: Watcher) -> None
```

### Conflict Detection & Resolution
```python
async def detect_divergence(campaign_path: str, db_client) -> list[DivergenceReport]
    # Checks for entities where markdown and graph differ

async def resolve_conflict(entity_id: str, strategy: "markdown_wins" | "graph_wins" | "merge") -> None
```

### Validation & Integrity
```python
async def validate_migration(campaign_path: str, db_client) -> ValidationReport
    # Checks for data consistency, missing references, etc.

async def repair_referential_integrity(campaign_path: str, db_client) -> RepairReport
    # Fixes broken references
```

### Progress & Monitoring
```python
class MigrationProgress:
    total_entities: int
    entities_migrated: int
    memories_created: int
    errors: list[str]

async def get_migration_status(campaign_path: str) -> MigrationProgress
```

## Integration Points

### Upstream Dependencies
- Split 01 (FalkorDB Foundation): Create/update entity nodes, transaction API
- Split 02 (Memory & Embedding): Create memory nodes from events, embed text

### Downstream Dependencies
- Existing entity browser: Must continue to work during/after migration
- WebSocket sync (Track 3): Broadcasts entity changes to clients
- Event bus (Track 5): Listens for entity changes, publishes sync events
- Actor system: Accesses entities (could come from markdown or graph)

### File System Integration
- Watch markdown files in `~/.sidestage/<campaign_name>/` subdirectories
- Parse YAML frontmatter + body
- Handle file creation, modification, deletion
- Preserve file structure/format

### Database Integration
- Create entity nodes in FalkorDB
- Create relationships (location, inventory, participation)
- Create memory nodes with embeddings
- Handle transaction rollback on errors

### Event System Integration
- Subscribe to EntityChanged events from markdown watcher
- Publish EntityChanged events when graph is updated
- Ensure bidirectional event flow

## Testing Strategy
- Unit tests for data transformation (markdown → node, node → markdown)
- Unit tests for conflict detection and resolution
- Integration tests with test campaign data
- Migration end-to-end test with sample campaign
- Sync watcher tests with simulated file changes
- Referential integrity validation tests
- Performance tests with large campaigns (1000+ entities)

## Success Criteria
1. Existing campaign data can be migrated to FalkorDB without data loss
2. Entity relationships are preserved during migration (references resolve)
3. Memory nodes are created from chat logs with embeddings
4. Markdown file changes are detected and synced to FalkorDB
5. FalkorDB entity changes are synced to markdown files
6. Connected clients receive consistent view of changes
7. Conflicts between markdown and graph are detected and can be resolved
8. Migration can be rolled back (markdown files restored)
9. Validation identifies data integrity issues
10. Tests provide >80% code coverage
11. Migration of 1000-entity campaign completes in reasonable time (TBD: <5 min)
12. No data loss or corruption during concurrent sync operations
