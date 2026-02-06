# Interview Transcript: FalkorDB Foundation

## Round 1

### Q1: Connection Management
**Question:** FalkorDB requires a Redis-compatible server running. How should the connection be managed per campaign? Options: (a) single shared FalkorDB instance with graph-per-campaign namespacing, (b) separate FalkorDB instance per campaign, (c) something else?

**Answer:** Configurable - support both patterns via campaign config.

### Q2: Transaction Consistency
**Question:** Research shows FalkorDB has no multi-query transactions in the Python client - each query is atomic. For complex operations like 'character moves from location A to B' (remove LOCATED_IN edge + create new one), how should we handle consistency?

**Answer:** Best effort with logging - accept eventual consistency for non-critical relationship updates, log failures.

### Q3: SQLite Coexistence
**Question:** Should the FalkorDB layer completely replace SQLite for entity storage, or should they coexist? Currently SQLite stores entities as JSON blobs.

**Answer:** Replace SQLite for entities - FalkorDB becomes the source of truth for all entity data. SQLite kept only for chat logs/config.

## Round 2

### Q4: Entity-to-Node Modeling
**Question:** For the entity-to-node mapping, research suggests multi-label nodes (e.g. :Entity:Character). The spec mentions Character has inventory (list of item IDs) and Location has connected_locations (list of location IDs). Should these lists be stored as node properties (arrays) or modeled as relationships (edges)?

**Answer:** Hybrid approach - connected_locations as :CONNECTS_TO edges (natural graph), inventory as array property (simpler for now).

### Q5: Expected Scale
**Question:** What's the expected scale for a single campaign?

**Answer:** Large (thousands+) - long-running campaigns or procedural generation: thousands of entities and events.

### Q6: API Design
**Question:** Should the graph storage module expose a clean async interface that mirrors the current Storage class methods, or should it provide a richer graph-native API?

**Answer:** Graph-native API - new API with graph operations (traverse, query_related, etc.). More powerful but requires updating consumers.

## Round 3

### Q7: Error Handling
**Question:** For error handling when FalkorDB is unreachable (server down, connection lost), what behavior do you want?

**Answer:** Fail fast with clear error - operations raise immediately. Campaign can't function without graph DB.

### Q8: Event Bus Integration
**Question:** Should the FalkorDB module listen directly to the SceneMessageBus for entity updates, or should the calling code explicitly call graph storage methods?

**Answer:** Explicit calls from Campaign - Campaign/SceneLogic calls graph storage directly. Simpler, more predictable. Current pattern.

### Q9: Schema Initialization
**Question:** Should schema initialization (creating indexes, constraints) happen automatically on first connection, or be a separate setup/migration step?

**Answer:** Auto with version check - auto-initialize but track schema version. Run migrations if version mismatch.
