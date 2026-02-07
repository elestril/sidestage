# Section 03 Code Review Interview

## Decisions

### #1 (CRITICAL) - create_entity catches ALL exceptions as DuplicateEntityError
**Decision:** Auto-fix. Distinguish constraint violations from other errors. Check for "unique constraint" or similar in exception message, wrap others as QueryError.

### #2 (CRITICAL) - Cypher injection via unvalidated property keys
**Decision:** Auto-fix. Validate property keys against known Entity field names using a whitelist.

### #3 (IMPORTANT) - Missing Event subtypes (JoinEvent, LeaveEvent, FastForwardEvent)
**Decision:** User chose "Add them now". Register all Event subtypes in LABEL_TO_MODEL and MODEL_TO_LABELS.

### #4 (IMPORTANT) - No exception wrapping on other CRUD functions
**Decision:** Auto-fix. Wrap raw exceptions in QueryError for all CRUD functions.

### #5 (IMPORTANT) - update_entity doesn't validate keys against excluded fields
**Decision:** User chose "Validate against model fields". Reject keys that aren't valid non-excluded fields.

### #6 (IMPORTANT) - update_entity crashes on empty updates dict
**Decision:** Auto-fix. Return early or raise ValueError on empty updates.

### #7 (SUGGESTION) - Round-trip lossy for None properties
**Decision:** Let go. FalkorDB null handling will be validated during integration testing.

### #8 (SUGGESTION) - Test doesn't assert exclusivity of SET clause
**Decision:** Auto-fix. Add negative assertion.

### #9 (SUGGESTION) - No test for invalid entity type
**Decision:** Auto-fix. Add test.

### #10 (SUGGESTION) - No test for find_entities with no filters
**Decision:** Let go. Low value.

### #11 (NITPICK) - Unused imports
**Decision:** Auto-fix.

### #12 (NITPICK) - list_entities doesn't use params
**Decision:** Let go. Safe since keys are validated.

### #13 (NITPICK) - __init__.py doesn't re-export
**Decision:** Let go. Deferred to section-06 (integration).
