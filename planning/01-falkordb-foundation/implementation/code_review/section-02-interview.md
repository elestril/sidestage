# Code Review Interview: Section 02 - Schema

## Finding 1: connect() not wired to initialize_schema
- **Decision:** ASKED USER -> Wire it now
- **Action:** Uncomment the initialize_schema call in connect(), add import

## Finding 2: No guard against version > CURRENT_VERSION
- **Decision:** AUTO-FIX
- **Action:** Add guard in initialize_schema to raise SchemaError if current version exceeds CURRENT_VERSION

## Finding 3: Missing updated_at assertion in test
- **Decision:** AUTO-FIX
- **Action:** Add assertion that params["updated_at"] exists and is a valid ISO 8601 string

## Finding 4: Weak migration test
- **Decision:** LET GO
- **Rationale:** With CURRENT_VERSION=1, fresh graph and "behind" are identical scenarios. Test structure is correct for when version increases.

## Finding 5: Bare Callable type
- **Decision:** LET GO
- **Rationale:** Nitpick. Adding complex Coroutine type adds noise for no practical benefit.

## Finding 6: Granular error messages in _migrate_v1
- **Decision:** AUTO-FIX
- **Action:** Wrap individual query failures in SchemaError with context about which index/constraint failed

## Finding 7: Cypher injection validation
- **Decision:** LET GO
- **Rationale:** Values are hardcoded module-level constants. Validation is over-engineering.

## Finding 8: Missing __init__.py exports
- **Decision:** LET GO
- **Rationale:** Will be handled when integration section wires everything together.

## Finding 9: Unused `call` import
- **Decision:** AUTO-FIX
- **Action:** Remove unused import
