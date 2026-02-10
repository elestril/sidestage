# Code Review Interview: Section 01 - Event Model

**Date:** 2026-02-09

## User Decisions

### 1. ChatResponse schema breaks orchestrator
**Decision:** Keep broken. Accept that /v1/chat is non-functional until section-06 refactors the orchestrator. Matches the plan's clean-break approach.

### 2. EntityModel.body default changed to ""
**Decision:** Keep body=''. Empty body is reasonable for all entity types.

## Auto-Fixes

### 3. Stale docstring in graph/queries.py
Fix docstring referencing 'ChatMessage subtype based on node labels'.

### 11. EventModel.metadata needs EXCLUDED_FIELDS entry
Add `EventModel: {"metadata"}` to EXCLUDED_FIELDS in graph/entities.py to prevent nested dicts being written to FalkorDB.

## Let Go (No Action)

- #2: Old graph node deserialization (clean break assumes graph wipe)
- #5: EventQueue exception handling (pre-existing bug, not this section's scope)
- #6: Event.character duck typing (works fine, avoids circular imports)
- #7-9: Test coverage gaps (plan-specified tests pass)
- #10: anyio vs asyncio markers (already resolved)
- #12: Two EventQueues (by design, bus.py deleted in section-04)
- #13: No __all__ export (not a project pattern)
- #14: SpanContext TYPE_CHECKING (works correctly)
