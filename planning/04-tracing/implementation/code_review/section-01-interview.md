# Code Review Interview: Section 01 - TraceConfig

**Date:** 2026-02-07

## Auto-Fixes

- **Finding 1 (Weak exception assertions):** Changing `pytest.raises(Exception)` to `pytest.raises(pydantic.ValidationError)` for all validation tests. This makes the tests assert the specific Pydantic validation path rather than catching any exception.

## Let Go

- **Finding 2 (Roundtrip fixture):** The autouse fixture and test both use `tmp_path` but pytest generates unique paths. Works correctly.
- **Finding 3 (Type-coercion tests):** Testing Pydantic internals, out of scope.
- **Finding 4 (Invalid-type tests):** The existing `init()` fallback behavior predates this section, not in scope.
- **Finding 5 (Cross-field validation):** Over-engineering. Not specified in the plan.
- **Finding 6 (Immutability):** Pre-existing pattern across all config models, out of scope.
- **Finding 7 (YAML key order):** Cosmetic concern about alphabetical YAML output.
