# Memory & Graph Database (FalkorDB)

**Status:** Draft
**Owner:** @user
**Date:** 2026-02-02

## Goal
To transition Sidestage's primary entity and memory storage to **FalkorDB** (a Redis-based Graph Database). This enables rich semantic queries, relationship traversal ("Who knows whom?"), and efficient retrieval of context for Agents.

## Scope
- **Entities:** All game entities (Characters, Locations, Items, Events) move to Graph Nodes.
- **Relationships:** Connections (Locations), Ownership (Inventory), Knowledge (Memories) move to Graph Edges.
- **Memories:** A new "Memory" node type for storing facts, observations, and summaries.
- **Legacy:** SQLite is retained *only* for:
    - Verbatim `ChatMessage` logs (linear history).
    - User/Auth data.
    - System configuration.

## Schema Strategy

### Nodes
- `Entity` (Label)
    - `Character` (Label)
    - `Location` (Label)
    - `Item` (Label)
    - `Scene` (Label)
- `Memory` (Label)
    - Properties: `content`, `importance`, `embedding` (vector).

### Edges
- `(:Character)-[:LOCATED_AT]->(:Location)`
- `(:Character)-[:HAS]->(:Item)`
- `(:Location)-[:CONNECTS_TO]->(:Location)`
- `(:Character)-[:KNOWS]->(:Memory)`
- `(:Scene)-[:INCLUDES]->(:Event)`

## Integration Points

### Storage Layer
- Create `GraphStorage` class wrapping FalkorDB client.
- `Storage` facade delegates:
    - Entity CRUD -> `GraphStorage`
    - Chat Log -> `SqliteStorage`

### Agent Tools
- `list_npcs` -> `MATCH (n:Character) RETURN n`
- `get_location` -> `MATCH (l:Location {id: $id}) RETURN l`
- `recall_memories(query)` -> Vector search on Memory nodes.

## Technology
- **FalkorDB:** Running via Docker.
- **Client:** `falkordb-py` (or compatible Redis client).
