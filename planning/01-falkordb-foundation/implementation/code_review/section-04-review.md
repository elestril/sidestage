# Code Review: Section 04 - Relationships

CRITICAL AND HIGH SEVERITY ISSUES:

1. [SECURITY / Cypher Injection via Property Keys in link()] In relationships.py lines 117-122, the `properties` dict keys are interpolated directly into the Cypher string via `prop_assignments = ", ".join(f"{k}: ${k}" for k in properties)`. Unlike `rel_type`, which is validated against `VALID_REL_TYPES`, property keys undergo ZERO validation. A caller could pass `properties={"}: 1}) MATCH (x) DETACH DELETE x //": "val"}` and inject arbitrary Cypher. The existing codebase in `entities.py` has `_validate_property_keys()` (line 76) that validates keys against `_ALL_ENTITY_FIELDS` and checks against a regex `_VALID_KEY_RE`. The relationships module does not call this or any equivalent validation before string-interpolating property keys. This is a clear injection vector.

2. [SECURITY / Property Value Parameter Namespace Collision] In relationships.py lines 123-127, properties are merged into the params dict via `**properties`. If a caller passes `properties={"source_id": "evil_id", "target_id": "evil_target"}`, the spread will OVERWRITE the legitimate `source_id` and `target_id` parameters. The CREATE query would then match different nodes than the ones verified in the existence check, creating edges between unintended entities. This is a parameter collision vulnerability that could cause data corruption.

3. [CORRECTNESS / OPTIONAL MATCH Behavior May Be Wrong] The existence check uses two separate `OPTIONAL MATCH` clauses. With OPTIONAL MATCH, the result always contains at least one row with nulls rather than an empty result_set. The code checks `if not result.result_set` which may be dead code. The test `test_link_raises_entity_not_found_no_results` tests a scenario that likely cannot occur with real OPTIONAL MATCH semantics.

4. [CORRECTNESS / test_link_raises_entity_not_found_for_target Tests Wrong Scenario] The mock returns `[[None, None]]` (both entities missing) but the test description says it tests 'target doesn't exist'. With `row[0] is None` checked first, the error message will mention the SOURCE id, not the target. The mock should return `[["char_1", None]]` to properly test the target-not-found case.

5. [MISSING FEATURE / No QueryError Tests] The test file never tests `QueryError` being raised when queries fail. The plan specifies link raises QueryError if the Cypher query fails. Missing coverage for all functions.

6. [MISSING FEATURE / get_relationships Has No rel_type Validation] The `get_relationships` function queries all relationship types generically. Returned values could include unexpected relationship types.

7. [TEST QUALITY / Weak Assertion on Bidirectional Pattern] The assertion for 'both' direction is `assert "]-(" in cypher or "->" not in cypher`. A tautology. Should explicitly check no directed arrows appear.

8. [CODE QUALITY / Inconsistent Logging Levels] All operations use `logger.debug()`. The existing `entities.py` uses `logger.info()` for mutating operations. Inconsistent.

9. [CODE QUALITY / No __all__ Export] Consistent with entities.py - minor.

10. [TEST COVERAGE / Missing Test for link() QueryError on CREATE Step] Tests do not cover when existence check succeeds but CREATE fails.
