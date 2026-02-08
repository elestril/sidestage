# Code Review Interview: Section 01 - Data Models

**Date:** 2026-02-07

## Auto-Fixes (applying without asking)

1. **Use Literal types for constrained string fields.** Switching `severity`, `phase`, and `action` from bare `str` to `Literal` types for runtime validation.

2. **Add default `None` for `entity_id`.** Making `entity_id: str | None = None` so callers don't have to explicitly pass `None` for file-level issues.

3. **Unstage unrelated `.claude/settings.json` change.** This file modification is unrelated to the data models section.

## Let Go (not fixing)

- `valid` invariant enforcement: Plan specifies it as a manual field. The validator (section 05) will construct it correctly.
- `BackupStatus.timestamp` as datetime: Plan specifies `str` type. Simpler for JSON serialization.
- Negative test coverage: Plan's test stubs are sufficient for foundational data models.
- `ParseResult` using `list[Any]`: Plan acknowledges this is intentional to avoid circular imports.
- `ParseResult` JSON serialization: Plan acknowledges this tradeoff.
