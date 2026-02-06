# Section 01 Code Review Interview

## Auto-fixes (applied without user input)

### Fix 1: Narrow exception catch in connect() (CRITICAL #1 + IMPORTANT #5)
- Change `except (OSError, Exception)` to `except (OSError, redis.exceptions.ConnectionError)`
- Import `redis.exceptions` at module level

### Fix 2: Remove unused `field` import (NITPICK #11)
- Remove `field` from `from dataclasses import dataclass, field`

### Fix 3: Replace `GraphClient.__new__` with proper construction in test (NITPICK #12)
- Use `GraphClient(pool=mock_pool, db=MagicMock(), graph=MagicMock(), graph_name='test')`

## User decisions

### Decision 1: Add placeholder test for schema initialization
- **User chose:** Add placeholder test with TODO comment
- **Action:** Add `test_connect_calls_schema_initialization` that is a documented placeholder

### Decision 2: Add idempotent close guard
- **User chose:** Add guard and test for double-close
- **Action:** Track closed state in GraphClient, guard in close(), add test

## Let go (not fixing)

- #4 Type annotations on GraphClient constructor (pyright will catch)
- #6-#7 Docstring verbosity (subjective, not worth churn)
- #8 frozen=True dataclass (premature optimization)
- #9-#10 Additional test variants (adequate coverage already)
- #13 password=None (redis handles gracefully)
