# Plan: Memory & FalkorDB Migration

## Phase 1: Infrastructure
- [ ] Add `falkordb` to `pyproject.toml` (and `redis` if needed).
- [ ] Update `docker-compose.yml` (if applicable) or provide instructions to run FalkorDB.
- [ ] Implement `GraphStorage` class in `src/sidestage/storage/graph.py`.
    - Connection handling.
    - Basic Node CRUD.

## Phase 2: Entity Migration
- [ ] Implement `migrate_sqlite_to_graph()` script.
    - Read all entities from SQLite.
    - Create Nodes with appropriate Labels.
    - Create Edges (Location links, Inventory).
- [ ] Update `Campaign` to initialize `GraphStorage`.
- [ ] Switch `WorldTools` to use `GraphStorage` for Entity queries.

## Phase 3: Semantic Memory
- [ ] Define `Memory` node schema.
- [ ] Implement `add_memory(actor_id, content)` tool.
- [ ] Implement `search_memories(query, actor_id)` tool (using Vector Search if available in FalkorDB or manual filtering).

## Phase 4: Hybrid Architecture
- [ ] Refactor `Storage` facade to route requests:
    - `get_scene_messages` -> SQLite.
    - `get_character` -> FalkorDB.
- [ ] Ensure strict consistency (Graph is source of truth for World State).

## Phase 5: Cleanup
- [ ] Remove Entity tables (npcs, locations, items) from SQLite after successful migration verification.
