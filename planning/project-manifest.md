<!-- SPLIT_MANIFEST
01-falkordb-foundation
02-memory-and-embedding
03-migration-and-sync
END_MANIFEST -->

# Sidestage Track 6: Memory & Graph Database Implementation

**Project Goal:** Transition primary storage to FalkorDB for relationship traversal and vector-based memory retrieval, while maintaining bidirectional synchronization with existing markdown-based entity files.

---

## Split Structure Overview

Track 6 is decomposed into three focused implementation units that progress logically from foundation to integration:

### Split 1: FalkorDB Foundation
**Purpose:** Establish the graph database core and entity graph model

**Scope:**
- FalkorDB connection management and configuration
- Entity node modeling (Character, Location, Item, Scene, Event)
- Relationship types and property schemas
- Basic CRUD operations for entities
- Schema initialization and migrations

**Deliverables:**
- FalkorDB connection pool and lifecycle management
- Entity node types with properties
- Relationship graph structure
- Query interface for basic entity operations

**Interfaces Provided:**
- Database initialization function
- Entity query/update API
- Transaction management

---

### Split 2: Memory and Embedding System
**Purpose:** Implement vector-based memory retrieval with embedding support

**Scope:**
- Embedding generation for memories and events
- Vector similarity search
- Memory context retrieval and assembly
- Integration with Agent system for prompt enrichment
- Context window management and scoring

**Dependencies:**
- Requires `01-falkordb-foundation` for entity node access
- Uses existing Event message bus
- Integrates with Actor system from Track 5

**Deliverables:**
- Embedding model selection and integration
- Memory node type with vector properties
- Similarity search queries
- Context assembly functions for agent prompts

**Interfaces Provided:**
- Embedding generation API
- Memory search function
- Context retrieval for agents

---

### Split 3: Migration and Synchronization
**Purpose:** Migrate existing markdown data to graph database and maintain bidirectional sync

**Scope:**
- Data migration from markdown files → FalkorDB
- Bidirectional synchronization (markdown ↔ graph)
- Real-time WebSocket update propagation
- Data validation and conflict resolution
- Rollback and recovery mechanisms

**Dependencies:**
- Requires `01-falkordb-foundation` for entity operations
- Requires `02-memory-and-embedding` for memory node creation
- Works with existing campaign data structure
- Integrates with WebSocket sync system

**Deliverables:**
- Migration script and progress tracking
- Bidirectional sync engine
- Change detection and propagation
- Data validation utilities

**Interfaces Provided:**
- Migration orchestration API
- Real-time sync subscription/publish
- Conflict resolution strategies

---

## Execution Recommendation

### Sequential Ordering
1. **Phase 1:** Implement `01-falkordb-foundation` - establishes database contract and entity model
2. **Phase 2:** Implement `02-memory-and-embedding` - leverages foundation for memory storage
3. **Phase 3:** Implement `03-migration-and-sync` - finalizes integration with existing systems

### Rationale
- Foundation must be in place before other splits can store/query data
- Memory system builds on entity operations from foundation
- Migration uses both foundation and memory features
- Sequential execution minimizes rework and integration issues

### No Parallel Opportunities
These splits are sequentially dependent; each requires the previous to be functional. No parallelization is recommended.

---

## Dependency Matrix

| Split | Depends On | Interface Type |
|-------|-----------|-----------------|
| 01-falkordb-foundation | None (standalone) | Provides: DB API, entity ops |
| 02-memory-and-embedding | 01 | Requires: entity queries, transaction mgmt |
| 03-migration-and-sync | 01, 02 | Requires: entity ops, memory API |

---

## Key Design Decisions to Explore

During /deep-plan for each split, clarify:

**Foundation (Split 1):**
- Graph schema normalization (entity properties, relationship cardinality)
- Transaction boundaries for consistency
- Index strategy for performance

**Memory System (Split 2):**
- Embedding model selection (local vs cloud)
- Vector dimension and similarity metric
- Memory node lifecycle (creation, expiration, scoring)

**Migration (Split 3):**
- Dual-write strategy (parallel operation period)
- Conflict resolution (markdown vs graph source of truth)
- Rollback mechanisms and data integrity checks

---

## Cross-Cutting Concerns

All splits must respect:
- Real-time WebSocket synchronization for connected clients
- Python 3.12+ async patterns (existing in codebase)
- Campaign-scoped data isolation (`~/.sidestage/<campaign_name>/`)
- Both local (llama.cpp) and cloud (Gemini) LLM support
- Preservation of existing Actor system integration

---

## Next Steps

1. **User Confirmation:** Review this split structure for approval/changes
2. **For each approved split:** Run `/deep-plan @01-name/spec.md` to generate detailed implementation plans
3. **Implementation:** Use `/deep-implement` for each split following TDD patterns

---

## Notes

This decomposition prioritizes:
- **Clear interfaces** between splits to minimize coupling
- **Sequential ordering** to avoid integration complexity
- **Logical progression** from foundation → features → integration
- **Well-bounded complexity** suitable for focused /deep-plan sessions

The splits are sized appropriately for thorough architectural planning without becoming unwieldy monolithic units.
