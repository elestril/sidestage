# Code Review: Section 09 - Integration Tests

## HIGH SEVERITY

1. **`autouse=True` on `patch_graph_operations` contaminates all tests** — Patches graph ops for every test including parse/validate-only tests that don't need them.

2. **`test_health_restored_on_import_failure` doesn't verify DEGRADED before failure** — Only checks post-failure HEALTHY state.

## MEDIUM SEVERITY

3. **Missing `backup_dir` fixture** — Plan specifies it but no test currently uses it.

4. **Missing `_read_frontmatter` helper** — Plan specifies 4 helpers, only 3 implemented.

5. **Missing plan-specified imports** (`json`, `Item`, `frontmatter_dict_to_memory`) — Not used by current tests.

6. **`test_backup_parse_matches_original_parse` only compares entity IDs** — Plan says to also compare memory IDs and field values.

7. **`test_backup_parse_matches_original_parse` doesn't use `backup_dir` fixture** — Uses `tmp_path` directly.

## LOW SEVERITY

8. **`test_entity_frontmatter_dict_roundtrip_all_types` doesn't compare type-specific fields** — Only checks id, name, body, type name.

9. **Regex in chatlog format test differs from plan** — Actually stricter/more correct than plan.

10. **`test_is_embedding_available_false_during_import` could be more robust** — Only checks False appeared in list.

11. **No test verifies `export_campaign()` end-to-end** — Manual serialization used instead.

12. **No negative assertion on `test_import_completes_successfully` errors field** — Doesn't check `errors == []`.
