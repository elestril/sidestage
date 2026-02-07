# Code Review: Section 02 - Schema Migration

1. **Missing test for invalid vector_dimension** (e.g., 0, -1) - No test coverage for the SchemaError raised by validation.
2. **Missing test for graceful degradation** when vector index creation fails - plan says non-fatal, no test verifies it.
3. **Security concern in _set_schema_version** - Dynamic SET clause uses f-string for key names from **extra_props, potential Cypher injection.
4. **Hardcoded migration version dispatch** - `if version == 2` doesn't scale; should use **kwargs or similar.
5. **Test fragility with magic numbers** - Idempotent test hardcodes exact _ok() count instead of generous padding.
6. **Docstrings removed from existing tests** - Gratuitous churn reducing documentation quality.
7. **Simplified SchemaVersion dimension check** - Only checks params, not query text.
8. **No negative test for dimension=None not storing** - Missing test that SchemaVersion doesn't get vector_dimension when None.
