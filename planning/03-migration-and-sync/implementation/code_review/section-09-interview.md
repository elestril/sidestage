# Code Review: Section 09 - Integration Tests

**Date:** 2026-02-07

## Auto-Fixes (applying without asking)

1. **autouse=True scope**: Remove `autouse=True` from `patch_graph_operations` and apply it only to the test classes that call `import_campaign`.
2. **Backup roundtrip comparison**: Extend `test_backup_parse_matches_original_parse` to also compare memory IDs and entity field values.
3. **Roundtrip type-specific fields**: Add type-specific field comparison to `test_entity_frontmatter_dict_roundtrip_all_types`.
4. **Assert no errors**: Add `assert result.errors == []` to `test_import_completes_successfully`.

## Let Go (not worth changing)

- Missing `backup_dir` fixture, `_read_frontmatter` helper, unused imports: No current tests use them, adding dead code has no value.
- Health restored test: Verifies the key behavior (HEALTHY after failure). The DEGRADED observation is already tested in a separate test.
- Chatlog regex: Implementation is stricter and more correct.
- Embedding availability: Sufficient for the test purpose.
- No export_campaign test: Requires FalkorDB, out of scope for mock-based tests.
