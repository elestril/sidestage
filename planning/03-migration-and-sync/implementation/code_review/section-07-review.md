# Code Review: Section 07 - Importer

## High Severity

1. **CONNECTS_TO error handling wraps entire loop.** The try/except surrounds the full `for other_id in connected_locations` loop, so one failed `link()` call skips all remaining connections for that location. Should be per-link.

2. **Dead variable `last_accessed`.** The variable is computed but never used in the Cypher string. The feature works by accident because `params` keys are iterated for `prop_parts`. Dead code.

## Medium Severity

3. **Importing private `_TYPE_TO_SUBLABEL` from memory/store.** Leading underscore = private API. Should be local constant or promoted to public.

4. **Missing memory count verification (Step 8).** Plan specifies verifying memory counts via `MATCH (m:Memory) RETURN count(m)`. Only entity counts are verified.

5. **`hasattr(entity, "scene_id")` is redundant.** All `Event` instances have `scene_id` as a required field.

6. **`gametime=0` hardcoded for all restored ChatMessages.** Loses original game time data.

7. **Positional ChatMessage IDs are fragile.** `scene_brawl_msg_0` etc. shifts if unparseable lines are skipped.

## Low Severity

8. No test for partial entity insertion failure.
9. No unit tests for `_parse_chatlog_lines` directly.
10. Schema init failure reported as "Graph drop failed" (misleading).
11. Chatlog regex doesn't handle missing trailing quote gracefully.

## What is done well

- Health transition correctly in try/finally
- CONNECTS_TO deduplication with frozenset
- Parameterized Cypher prevents injection
- Partial import on entity failure
- Good test coverage breadth (16 test functions)
- Correctly reconciles plan's chatlog type inconsistency
