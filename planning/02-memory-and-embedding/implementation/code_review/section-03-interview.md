# Code Review: Section 03 - Memory Store

**Date:** 2026-02-07

## Discussed with User

### Sequential vs parallel queries in get_memories_for_context
- **Decision:** Keep sequential. User decided Redis pool may serialize anyway, and sequential is simpler to test.

## Auto-Fixes

### FIX: Add :Entity labels to OPTIONAL MATCH in upsert (HIGH)
- Add `:Entity` labels to `OPTIONAL MATCH (owner {id: $owner_id})` → `OPTIONAL MATCH (owner:Entity {id: $owner_id})`
- Same for target node. Prevents full graph scan.

### FIX: Replace fallback Memory construction with QueryError (HIGH)
- If `result.result_set` is empty after MERGE+RETURN, raise QueryError instead of constructing a potentially wrong Memory.

### FIX: Narrow exception handling in search_similar (HIGH)
- Change `except Exception` to catch only QueryError and common FalkorDB errors.

### FIX: Add type annotations to convenience wrappers (LOW)
- Add `client: GraphClient` type hints to wrapper functions.

## Let Go

- #3 MEMORY_REL_TYPES unused internally (exported for consumers)
- #4 _node_to_memory Pydantic coercion (standard pattern)
- #6 Common memory owner_id NULL edge case (extremely unlikely)
- #7 Tests verify Cypher strings (matches existing codebase pattern)
- #8 Test coupling to query-skipping (acceptable)
- #10 No __all__ (consistent with rest of codebase)
