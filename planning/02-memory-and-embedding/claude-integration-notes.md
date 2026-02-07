# Integration Notes: Opus Review Feedback

## Changes Integrated

### 1. Memory/Entity Label Architecture (Critical #1) — INTEGRATED
**Decision**: Option (c) — `memory/store.py` contains its own Cypher for memory CRUD and relationship creation. Memory nodes do NOT carry the `:Entity` label. The new relationship types are removed from `VALID_REL_TYPES` in `relationships.py` since they'll never flow through that path. Memory-specific relationship Cypher lives in `store.py` and matches on `:Memory` for one side and `:Entity` for the other.

### 2. Health Status / Chat Blocking (Critical #2) — INTEGRATED
**Decision**: Embedding failure transitions to `DEGRADED`, not `UNHEALTHY`. `is_accepting_chat` returns True for both HEALTHY and DEGRADED. Only a full graph database failure would warrant UNHEALTHY + chat blocking. Memory operations are gated by a separate `is_embedding_available` check.

### 3. Concurrent Embedding Backpressure (Critical #3) — INTEGRATED
**Decision**: MemoryListener uses an internal `asyncio.Queue` + background worker with a semaphore (max 3 concurrent embedding calls). Events are enqueued immediately (non-blocking) and processed in order. If queue exceeds a threshold (e.g., 100), oldest entries are dropped with a warning.

### 4. Vector Dimension Propagation (Significant #4) — INTEGRATED
**Decision**: Add `vector_dimension` field to `GraphConfig`. At startup, `Campaign.start_graph()` makes a test embedding call to determine the actual dimension, sets it on `GraphConfig`, and passes it through to `initialize_schema()` which accepts an optional `vector_dimension` parameter. The migration stores the dimension as a graph property for future reference.

### 5. Memory Context Injection (Significant #5) — INTEGRATED
**Decision**: Add a `context` parameter to `LiteLLMAgent.arun()`. In `AgentActor.on_event()`, call `assemble_context()` with the incoming message text, then pass the result as `context` to `arun()`. The agent inserts the context as a system message between the main system prompt and the user message. Clean, no mutation of shared state.

### 6. Memory Scoping Rules (Moderate #10) — INTEGRATED
**Decision**: Memories are scoped to characters via graph traversal. A character can recall:
- Memories with REMEMBERS edge to themselves
- Memories that OCCURRED_AT a location the character is currently at or has visited
- Memories DERIVED_FROM events in scenes the character participated in
Post-filtering applies these rules after vector search.

### 7. Game-Time Recency (Moderate #9) — INTEGRATED
**Decision**: Use game time (`gametime` field) as the primary recency basis. Add `gametime` field to Memory model. Fall back to wall-clock time only when gametime is unavailable.

### 8. Fact Extraction Deduplication (Significant #7) — INTEGRATED
**Decision**: Before creating a fact memory, check if a semantically similar fact exists (cosine similarity > 0.95 with existing fact memories for the same entity). If duplicate found, increment the existing fact's access_count instead. Entity name matching is case-insensitive with whitespace normalization.

### 9. `get_memory` Side Effect (Significant #8) — INTEGRATED
**Decision**: `get_memory()` does NOT increment access_count. A separate `touch_memory()` function handles access tracking. Only `search_similar()` and `assemble_context()` call `touch_memory()`.

### 10. Event/Memory Redundancy (Moderate #11) — INTEGRATED
**Decision**: This redundancy is intentional and documented. Event nodes are structural graph data (split 01). Memory nodes are the retrieval layer with embeddings. The DERIVED_FROM relationship links them. The plan now explicitly documents this design decision.

### 11. Batched Memory at Scene Deactivation (Minor #20) — INTEGRATED
**Decision**: Add a brief note that batch summarization on scene deactivation is deferred to future work. The current scope is real-time memory creation only.

## Changes NOT Integrated

### FalkorDB API Verification (Significant #6) — DEFERRED
This is a valid concern but is an implementation-time verification, not a plan-level issue. The implementer should verify the exact FalkorDB server version and API syntax during development. The plan uses the documented FalkorDB 4.0+ API syntax.

### Token Budget Heuristic (Minor #17) — NOT INTEGRATED
The 4-char heuristic is acceptable for initial implementation. Over-engineering token counting at this stage adds complexity without proportional benefit.

### Embedding Model Consistency (Minor #18) — DEFERRED
Model change detection is a future concern. Worth noting but not in scope for this split.

### Test Strategy — NOTE
The review correctly notes the plan lacks a testing section. This will be addressed by the TDD plan (Step 16) which creates the full test strategy.
