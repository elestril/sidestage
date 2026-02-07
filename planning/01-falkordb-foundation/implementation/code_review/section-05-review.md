# Code Review: Section 05 - Queries

CRITICAL ISSUES:

1. CYPHER INJECTION via f-string in entity_graph. The `depth` parameter is interpolated directly into Cypher via f-string. No runtime validation that it's a positive integer. Must validate before interpolation.

2. RETURN TYPE MISMATCH -- characters_at_location returns list[Character] but node_to_entity returns Entity. No runtime type check. Consistent with entities.py pattern but plan implies type guarantees.

3. MISSING VALIDATION for since_gametime -- no check that it's actually an integer.

4. DUPLICATE QUERY STRINGS in scene_events between if/else branches.

TEST COVERAGE GAPS:

5. No test for depth validation in entity_graph (0, -1, non-integer).

6. No test for multiple characters at a location.

7. No assertion on parameter values passed to graph.query (only Cypher string keywords checked).

8. No test for scene_events params dict containing since_gametime value.

9. Missing test for entity_graph asserting parameterized entity_id.

10. test_connected_locations_both_directions checks full cypher for arrows rather than just MATCH pattern.

MINOR:

11. entity_graph returns plain dict rather than TypedDict.

12. deep_implement_config.json bookkeeping -- section-05 not tracked yet (expected, handled at commit).

13. Positional arg pattern for graph.query is consistent with codebase.
