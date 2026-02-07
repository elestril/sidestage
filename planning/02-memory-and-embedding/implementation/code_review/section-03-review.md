# Code Review: Section 03 - Memory Store (CRUD + Search)

The implementation is largely faithful to the plan but has several issues ranging from moderate to significant.

**1. Missing asyncio.gather for get_memories_for_context -- Sequential queries where parallelism was specified (MEDIUM)**
The plan explicitly says: 'These can be run with asyncio.gather for parallelism.' The implementation runs all four queries sequentially with individual awaits. This is a performance concern for the critical context assembly path.

**2. Label-less OPTIONAL MATCH in upsert is a full graph scan -- potential performance catastrophe (HIGH)**
The Cypher for the private memory path uses `OPTIONAL MATCH (owner {id: $owner_id})` and `OPTIONAL MATCH (target {id: $target_id})` without any label. This matches ANY node in the entire graph with that id property. These OPTIONAL MATCH clauses should use `:Entity` labels.

**3. MEMORY_REL_TYPES is defined but never actually validated or used (MEDIUM)**
MEMORY_REL_TYPES is defined but never referenced anywhere in the actual store logic. The relationship types 'HAS_MEMORY' and 'ABOUT' are hardcoded as string literals in the Cypher queries.

**4. _node_to_memory does not handle missing optional fields gracefully (MEDIUM)**
`Memory(**props)` is called directly. This relies on Pydantic coercing string values to MemoryType enum, which works but is fragile.

**5. Fallback Memory construction in upsert_memory returns wrong id on update (HIGH)**
When `result.result_set` is empty, a fallback Memory object is constructed using the freshly generated `mem_id`. On an UPDATE this would be wrong. The fallback should raise QueryError instead.

**6. Common memory upsert does not set owner_id to NULL explicitly (LOW-MEDIUM)**
The common memory MERGE does not set owner_id. Edge case if node was previously private.

**7. Tests verify Cypher string contents rather than behavior (MEDIUM)**
Many tests only check that certain strings appear in the Cypher query, which is brittle.

**8. get_memories_for_context skips character memory query -- test coupling (LOW)**
Test knows implementation detail of query-skipping.

**9. search_similar swallows ALL exceptions silently (HIGH)**
The `except Exception` clause catches every possible error and silently returns an empty list. Should be narrowed.

**10. No __all__ export list (LOW)**
Minor packaging concern.

**11. Type annotations missing on convenience wrapper parameters (LOW)**
Convenience wrappers lack type annotations.
