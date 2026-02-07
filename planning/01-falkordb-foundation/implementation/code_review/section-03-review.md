# Section 03 Code Review: Entity Operations

## CRITICAL

### 1. `create_entity` catches ALL exceptions as `DuplicateEntityError`
**File:** `src/sidestage/graph/entities.py`, lines 116-121
```python
try:
    await client.graph.query(cypher, params=props)
except Exception as exc:
    raise DuplicateEntityError(
        f"Entity with id '{entity.id}' already exists: {exc}"
    ) from exc
```
Bare `except Exception` wraps every failure -- network errors, Cypher syntax errors, timeouts, memory errors -- as `DuplicateEntityError`. The plan (Error Handling section) explicitly requires differentiating: `DuplicateEntityError` for constraint violations, `QueryError` for unexpected Cypher failures, and proper wrapping of raw FalkorDB/Redis exceptions. This will mask real infrastructure failures in production and make debugging extremely difficult.

### 2. Cypher injection via unvalidated property key names in `update_entity` and `find_entities`
**File:** `src/sidestage/graph/entities.py`, lines 149 and 203
```python
# Line 149
set_clauses = ", ".join(f"n.{k} = ${k}" for k in updates)
# Line 203
conditions = " AND ".join(f"n.{k} = ${k}" for k in filters)
```
Property *values* are safely parameterized via `$k`, but property *keys* are interpolated directly into the Cypher string. A caller passing a key like `"id} DETACH DELETE n //"` could inject arbitrary Cypher. The plan explicitly calls out parameterization to prevent injection. Property keys should be validated against a whitelist of known Entity field names before interpolation.

## IMPORTANT

### 3. Missing Event subtype registrations: JoinEvent, LeaveEvent, FastForwardEvent
**File:** `src/sidestage/graph/entities.py`, lines 32-48
The schemas in `src/sidestage/schemas.py` define `JoinEvent` (line 66), `LeaveEvent` (line 69), and `FastForwardEvent` (line 72) as subclasses of `Event`. None appear in `LABEL_TO_MODEL` or `MODEL_TO_LABELS`. If created via `create_entity`, `entity_to_labels` falls back to `["Entity"]`, losing the Event and subtype labels.

### 4. No exception wrapping on `get_entity`, `delete_entity`, `list_entities`, `find_entities`
**File:** `src/sidestage/graph/entities.py`, lines 126-210
The plan states: "Raw FalkorDB/Redis exceptions are caught and wrapped in the appropriate GraphError subclass with a descriptive message." Only `create_entity` has any try/except (and it is too broad, see issue #1). All other CRUD functions let raw Redis/FalkorDB exceptions propagate unhandled, violating the error handling contract.

### 5. `update_entity` does not validate update keys against excluded fields
**File:** `src/sidestage/graph/entities.py`, lines 141-162
A caller could pass `updates={"messages": [...], "connected_locations": [...]}` and the function would write these as node properties, violating the exclusion rules in `EXCLUDED_FIELDS`.

### 6. `update_entity` crashes on empty updates dict
**File:** `src/sidestage/graph/entities.py`, line 149
If `updates` is `{}`, `set_clauses` becomes an empty string, producing invalid Cypher.

## SUGGESTION

### 7. `node_to_entity` round-trip lossy for None-cleared properties
When `entity_to_properties` omits `None` values, and then a user calls `update_entity` to set `location_id` to `None`, the parameterized query sends `None` to FalkorDB.

### 8. Test does not assert exclusivity of SET clause properties
**File:** `tests/unit/test_graph_entities.py`
The plan says: "Assert Cypher contains SET n.name = ... but not SET n.body = ..." The test only asserts `"n.name" in cypher` but does not assert `"n.body"` is absent.

### 9. No test for `list_entities` with invalid type raising `QueryError`
The implementation validates `entity_type` against `LABEL_TO_MODEL` and raises `QueryError` for unknown types, but there is no test for this error path.

### 10. No test for `find_entities` with no filters delegating to `list_entities`

## NITPICK

### 11. Unused imports
`tests/unit/test_graph_entities.py` -- `patch` imported but never used.
`tests/unit/test_graph_serialization.py` -- `MagicMock` imported but never used.

### 12. `list_entities` does not pass params when filtering by type
When `entity_type` is provided, the query is executed with no params. While safe today (validated against `LABEL_TO_MODEL` keys), it is inconsistent with the parameterized style used everywhere else.

### 13. `graph/__init__.py` does not re-export CRUD functions
The `__init__.py` is empty and does not re-export the new CRUD functions.
