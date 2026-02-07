# Code Review Interview: Section 04 - Relationships

**Date:** 2026-02-06

## Auto-Fixes (applying without discussion)

### Fix 1: Validate property keys in link() to prevent Cypher injection
- Add regex validation for property keys before interpolating into Cypher
- Reuse the `_VALID_KEY_RE` pattern from entities.py
- **Status:** FIX

### Fix 2: Prevent parameter namespace collision in link()
- Prefix property parameter names with `prop_` to avoid overwriting source_id/target_id
- **Status:** FIX

### Fix 3: Fix test_link_raises_entity_not_found_for_target mock
- Change mock return from `[[None, None]]` to `[["char_1", None]]` so it correctly tests target-not-found
- Add assertion that error message mentions the target ID
- **Status:** FIX

### Fix 4: Strengthen bidirectional pattern assertion
- Replace weak tautological assertion with explicit check that neither `->` nor `<-` appears
- **Status:** FIX

### Fix 5: Use INFO-level logging for mutations
- Change `link` and `unlink` completion logging from DEBUG to INFO, matching entities.py pattern
- **Status:** FIX

## Discussed with User

### Issue: Additional QueryError test coverage
- **Decision:** Add QueryError tests for all 4 functions
- **Status:** FIX

## Let Go

- Issue 3 (OPTIONAL MATCH dead code): Defensive check is fine to keep
- Issue 6 (get_relationships no rel_type validation): By design, returns all
- Issue 9 (No __all__): Consistent with codebase
