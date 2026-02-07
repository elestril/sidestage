# Code Review Interview: Section 05 - Queries

**Date:** 2026-02-06

## Auto-Fixes (applying without discussion)

### Fix 1: Validate `depth` parameter in entity_graph
- Add runtime validation that depth is a positive integer before f-string interpolation
- Add test for invalid depth values
- **Status:** FIX

### Fix 2: DRY up scene_events query construction
- Build query incrementally instead of duplicating the base Cypher
- **Status:** FIX

## Let Go

- Issue 2 (return type mismatch): Consistent with entities.py pattern
- Issue 3 (since_gametime validation): FalkorDB handles type coercion
- Issues 6-10 (test improvements): Current approach consistent with existing tests
- Issue 11 (TypedDict): Plain dict matches plan signature
