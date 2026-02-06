# Section 01 Code Review

## CRITICAL

### 1. Exception handler catches everything, masking real bugs
**File:** `src/sidestage/graph/client.py`, line 71
```python
except (OSError, Exception) as exc:
```
`Exception` is the superclass of `OSError`, so listing `OSError` is redundant. Catching bare `Exception` means every error during pool/db/graph creation is wrapped as `ConnectionError`. Plan says to catch `redis.exceptions.ConnectionError` and `OSError` only.

## IMPORTANT

### 2. Missing test: `test_connect_calls_schema_initialization`
The plan explicitly lists this test. Even though schema init is a placeholder in section-01, the test should exist.

### 3. `close()` claims idempotency but has no guard
Docstring says "Safe to call multiple times" but no guard exists. Double-close on `BlockingConnectionPool` may raise.

### 4. `GraphClient` lacks type annotations on constructor parameters
Plan specifies typed attributes. Implementation has bare `pool, db, graph` with no annotations. Project uses pyright.

### 5. `redis.exceptions.ConnectionError` not explicitly caught
Plan error wrapping section says to catch `redis.exceptions.ConnectionError` or `OSError`. Implementation catches `(OSError, Exception)`.

## SUGGESTION

### 6. `errors.py` docstrings abbreviated vs plan
Plan provides multi-line docstrings for each exception. Implementation uses single-line only.

### 7. `errors.py` module docstring is minimal
Plan has design principles block. Implementation has only one-line docstring.

### 8. `GraphConfig` could be `frozen=True` dataclass

### 9. Connect test only tests `OSError`, not `redis.exceptions.ConnectionError`

### 10. No test for full `GraphClient` attributes shape

## NITPICK

### 11. Unused import `field` from `dataclasses`
### 12. `GraphClient.__new__` usage in test is fragile
### 13. `connect()` passes `password=None` unconditionally
