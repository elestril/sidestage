# Deep Project Interview: Sidestage Track 6 - Memory & Graph Database

## Date
2026-02-04

## Scope Clarification
**Focus:** Track 6 only - Memory & Graph Database implementation with FalkorDB

## Project Context

### Existing Architecture
Sidestage is a modular, multi-agent RPG assistant with the following current state:
- **Completed Tracks:** Core Platform, Entity Management, Universal Console, Time/Scenes, NPC Agents/Actor System, Architecture Refactor
- **Storage:** Currently markdown-first with YAML frontmatter for entities, SQLite for chat logs/session memory
- **Tech Stack:** Python 3.12+, Poetry, React frontend, hybrid LLM support (local llama.cpp + cloud Gemini)
- **Entity Model:** Universal structure for Characters, Locations, Items, Scenes, Events
- **Event System:** Message bus for ChatMessage, JoinEvent, LeaveEvent, etc.

### Track 6 Objectives (from requirements.md)
"Transitioning primary storage to FalkorDB for relationship traversal and vector-based memory retrieval"

## Key Questions & Context

### 1. Natural Boundaries
Based on the requirements, Track 6 involves several distinct concerns:
- **FalkorDB Integration:** Setting up connection, configuration, schema design for graph database
- **Entity Storage Migration:** Moving from markdown/YAML to graph nodes and relationships
- **Memory System:** Vector-based memory retrieval (embeddings, similarity search)
- **Relationship Modeling:** Entity relationships, traversal patterns, queries
- **Data Migration:** Bidirectional sync between existing markdown files and graph database

### 2. Foundational Dependencies
Track 6 builds on:
- Existing entity model (Characters, Locations, Items, Scenes, Events)
- Event-driven message bus architecture
- WebSocket sync for real-time updates
- Markdown import/export capability

Track 6 should preserve:
- Bidirectional sync with markdown files (per section 3.1)
- Real-time WebSocket synchronization
- Scene-based context system

### 3. Uncertainty Areas
Not explicitly specified in requirements:
- **Migration strategy:** Dual-write vs. FalkorDB-primary vs. hybrid long-term
- **Memory retrieval specifics:** Embedding model choice, similarity thresholds, context window management
- **Graph schema:** Exact node types, relationship types, property schemas
- **Query patterns:** What graph traversals are most important for gameplay
- **Integration points:** How agent prompts pull from graph memory vs. current scene history

### 4. Technical Constraints
- Python 3.12+ async-focused
- Must integrate with existing Actor system
- Must support real-time WebSocket updates
- Campaign data in `~/.sidestage/<campaign_name>/`
- Both local and cloud LLM support required

## Proposed Work Decomposition

This track appears to involve 3-4 distinct technical domains:

1. **FalkorDB Core Integration**
   - Database setup, connection management, schema design
   - Graph node and relationship modeling
   - Basic CRUD operations for entities

2. **Memory & Embedding System**
   - Vector embeddings for memories/events
   - Similarity search and retrieval
   - Context assembly for agent prompts

3. **Migration & Synchronization**
   - Markdown ↔ FalkorDB bidirectional sync
   - Data migration from existing campaigns
   - Real-time update propagation

4. **Query Patterns & Agent Integration** (possibly combined with #2)
   - Graph traversal patterns for relationship queries
   - Integration with Actor system prompts
   - Context-aware memory retrieval

## Natural Split Candidates

Based on cohesion and clear interfaces:

**Option A: Three Splits**
1. **FalkorDB Foundation** - Database setup, entity graph modeling, core operations
2. **Memory System** - Embeddings, vector search, context retrieval
3. **Migration & Sync** - Markdown bidirectional sync, data migration

**Option B: Two Splits**
1. **Graph Database Core** - FalkorDB setup, entity modeling, basic operations, migration
2. **Memory & Retrieval** - Vector embeddings, similarity search, agent integration

**Option C: Single Coherent Unit**
- All aspects are tightly coupled around "transitioning primary storage to FalkorDB"
- Artificial separation might create overhead
- Better suited for a single comprehensive /deep-plan exploration

## Recommendation
Given that Track 6 is fundamentally about "transitioning primary storage," the components are highly interdependent. The graph schema design affects memory retrieval, which affects migration strategy, which affects query patterns. This suggests **Option C: Single Unit** may be most appropriate, allowing /deep-plan to explore the entire system holistically and make coherent architectural decisions.

However, if the user prefers more granular planning phases, **Option A** provides clear boundaries with well-defined interfaces between splits.
