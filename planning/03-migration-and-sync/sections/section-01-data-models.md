# Section 01: Data Models

## Overview

This section creates the `migration/` package with its foundational data models in `migration/models.py` and `migration/__init__.py`. These Pydantic models are used by every other section in the migration module -- parser, validator, importer, exporter, and API routes -- making this the first section to implement.

All models use Pydantic `BaseModel` and are prefixed with `Migration` (except `BackupStatus` and `ParseResult`). They define the shapes for validation reports, import/export results, API requests/responses, and the intermediate parse output.

## Dependencies

- **None.** This section has no dependencies on other sections and can be implemented first.
- It uses only standard library types and `pydantic.BaseModel`.

## Files to Create

| File | Purpose |
|------|---------|
| `/home/harald/src/sidestage/src/sidestage/migration/__init__.py` | Package init, re-exports key models |
| `/home/harald/src/sidestage/src/sidestage/migration/models.py` | All Pydantic data models for the migration module |
| `/home/harald/src/sidestage/tests/unit/test_migration_models.py` | Unit tests for the data models |

## Tests (Write First)

Create `/home/harald/src/sidestage/tests/unit/test_migration_models.py` with the following test stubs. These tests verify that all models instantiate correctly, serialize to JSON, and enforce their contracts.

```python
"""Unit tests for migration data models."""

from sidestage.migration.models import (
    BackupStatus,
    MigrationBackupResult,
    MigrationImportRequest,
    MigrationImportResponse,
    MigrationImportResult,
    MigrationValidationIssue,
    MigrationValidationReport,
    ParseResult,
)


class TestMigrationValidationIssue:
    """MigrationValidationIssue model tests."""

    def test_accepts_error_severity(self):
        """MigrationValidationIssue can be created with severity='error'."""

    def test_accepts_warning_severity(self):
        """MigrationValidationIssue can be created with severity='warning'."""

    def test_entity_id_is_optional(self):
        """MigrationValidationIssue works with entity_id=None (file-level issues)."""


class TestMigrationValidationReport:
    """MigrationValidationReport model tests."""

    def test_valid_true_when_no_errors(self):
        """Report with empty errors list has valid=True."""

    def test_valid_false_when_errors_present(self):
        """Report with errors has valid=False."""

    def test_entity_counts_dict(self):
        """entity_counts holds per-type counts like {'Character': 3, 'Location': 2}."""

    def test_serializes_to_json(self):
        """model_dump_json() produces valid JSON with all fields."""


class TestMigrationImportResult:
    """MigrationImportResult model tests."""

    def test_phase_complete(self):
        """Result with phase='complete' serializes correctly."""

    def test_phase_failed(self):
        """Result with phase='failed' serializes correctly."""

    def test_serializes_to_json(self):
        """model_dump_json() produces valid JSON with all fields."""


class TestMigrationBackupResult:
    """MigrationBackupResult model tests."""

    def test_includes_written_chatlogs(self):
        """written_chatlogs field is present and serialized."""

    def test_serializes_to_json(self):
        """model_dump_json() produces valid JSON with all fields."""


class TestBackupStatus:
    """BackupStatus model tests (written to status.json during backup)."""

    def test_includes_all_required_fields(self):
        """BackupStatus has timestamp, success, entity_counts, memory_count,
        chatlog_count, errors, and sidestage_version fields."""

    def test_serializes_to_json(self):
        """model_dump_json() produces valid JSON suitable for status.json."""


class TestMigrationImportRequest:
    """MigrationImportRequest API request model tests."""

    def test_default_action_is_validate(self):
        """Default action is 'validate' when not specified."""

    def test_default_force_is_false(self):
        """Default force is False when not specified."""


class TestMigrationImportResponse:
    """MigrationImportResponse API response model tests."""

    def test_validation_only_response(self):
        """Response with action='validate' has validation but no result."""

    def test_execute_response(self):
        """Response with action='execute' has result (and optionally validation)."""


class TestParseResult:
    """ParseResult intermediate model tests."""

    def test_empty_parse_result(self):
        """ParseResult can be created with empty lists (no entities/memories)."""

    def test_holds_entities_memories_chatlogs_errors(self):
        """ParseResult has entities, memories, chatlogs, and errors fields."""
```

## Implementation Details

### Package Init: `migration/__init__.py`

Create `/home/harald/src/sidestage/src/sidestage/migration/__init__.py` as a package initializer that re-exports the key model classes. This makes imports cleaner for other modules:

```python
"""Campaign migration: import and backup operations."""
```

Keep this minimal for now. Other sections will add re-exports as the module grows.

### Data Models: `migration/models.py`

Create `/home/harald/src/sidestage/src/sidestage/migration/models.py` containing all Pydantic models used across the migration module. The models fall into four categories:

#### 1. Validation Models

`MigrationValidationIssue` represents a single validation problem found during pre-import checks:

- `entity_id: str | None` -- the entity ID involved, or `None` for file-level issues
- `file_path: str` -- the filesystem path where the issue was found
- `severity: str` -- either `"error"` (blocks import) or `"warning"` (informational)
- `message: str` -- human-readable description of the issue

`MigrationValidationReport` aggregates all issues from a validation pass:

- `valid: bool` -- `True` if no errors (warnings are acceptable)
- `entities_found: int` -- total entity count parsed
- `memories_found: int` -- total memory count parsed
- `entity_counts: dict[str, int]` -- per-type breakdown, e.g. `{"Character": 3, "Location": 2}`
- `errors: list[MigrationValidationIssue]` -- issues with severity `"error"`
- `warnings: list[MigrationValidationIssue]` -- issues with severity `"warning"`

#### 2. Result Models

`MigrationImportResult` reports the outcome of an import operation:

- `phase: str` -- `"complete"` on success, `"failed"` on error
- `total_entities: int` -- how many entities were in the source
- `total_memories: int` -- how many memories were in the source
- `processed_entities: int` -- how many entities were actually inserted
- `processed_memories: int` -- how many memories were actually inserted
- `errors: list[str]` -- error messages if any steps failed

`MigrationBackupResult` reports the outcome of a backup operation:

- `phase: str` -- `"complete"` on success, `"failed"` on error
- `total_entities: int` -- how many entities were in the graph
- `total_memories: int` -- how many memories were in the graph
- `written_entities: int` -- how many entity files were written
- `written_memories: int` -- how many memory files were written
- `written_chatlogs: int` -- how many chatlog.log files were written
- `errors: list[str]` -- error messages if any steps failed

#### 3. API Request/Response Models

`MigrationImportRequest` is the body for `POST /v1/campaign/import`:

- `action: str = "validate"` -- either `"validate"` (dry run) or `"execute"` (perform import)
- `force: bool = False` -- if `True`, proceed even with validation warnings

`MigrationImportResponse` is returned from the import endpoint:

- `action: str` -- echoes the requested action
- `validation: MigrationValidationReport | None = None` -- present for validate actions
- `result: MigrationImportResult | None = None` -- present for execute actions

#### 4. Backup Status Model

`BackupStatus` is written to `status.json` inside the backup directory:

- `timestamp: str` -- ISO 8601 timestamp of when backup completed
- `success: bool` -- whether the backup completed without errors
- `entity_counts: dict[str, int]` -- per-type entity counts
- `memory_count: int` -- total memories backed up
- `chatlog_count: int` -- total chatlog files written
- `errors: list[str]` -- any non-fatal errors encountered
- `sidestage_version: str` -- version of sidestage that created the backup

#### 5. Parse Result Model

`ParseResult` is the intermediate output from `parser.py` (section 04) consumed by `validator.py` (section 05) and `importer.py` (section 07). It bundles everything parsed from the markdown directory:

- `entities: list` -- list of parsed entity objects (typed as `list[Any]` for now; section 02 will use the concrete Entity types from `schemas.py`)
- `memories: list` -- list of parsed Memory objects (typed as `list[Any]` for now; section 02 will use `Memory` from `memory/models.py`)
- `chatlogs: dict[str, list[str]]` -- mapping of scene ID to list of raw chat log lines
- `errors: list[MigrationValidationIssue]` -- parse-level errors (malformed YAML, missing frontmatter, etc.)

Note: The `entities` and `memories` fields use `list[Any]` to avoid a circular import between `migration/models.py` and `schemas.py`/`memory/models.py`. The parser (section 04) will populate these with concrete `Entity` and `Memory` instances. The type annotations can be tightened in section 04 if desired, or left generic since the validator and importer already know the concrete types.

### Relationship to Existing Code

The existing codebase has these relevant models that the migration models reference conceptually but do not import:

- **`schemas.py`**: `Entity`, `Character`, `Location`, `Item`, `Scene`, `Event`, `ChatMessage`, `JoinEvent`, `LeaveEvent`, `FastForwardEvent` -- the domain entity models. The `ParseResult.entities` list will hold instances of these.
- **`memory/models.py`**: `Memory`, `MemoryType` -- the memory model. The `ParseResult.memories` list will hold `Memory` instances.
- **`health.py`**: `HealthStatus`, `CampaignHealth` -- used by the importer (section 07) for concurrency guards, not directly by models.

The migration models are API-facing Pydantic models that wrap and report on operations involving those domain types.

## Acceptance Criteria

1. `migration/__init__.py` exists and the package is importable via `from sidestage.migration.models import ...`
2. All seven model classes (`MigrationValidationIssue`, `MigrationValidationReport`, `MigrationImportResult`, `MigrationBackupResult`, `BackupStatus`, `MigrationImportRequest`, `MigrationImportResponse`, `ParseResult`) are defined and instantiable
3. All models serialize to JSON via `model_dump_json()` without errors
4. `MigrationImportRequest` defaults: `action="validate"`, `force=False`
5. `MigrationImportResponse` optional fields: `validation=None`, `result=None`
6. `ParseResult` can be created with empty lists and dicts
7. All tests in `test_migration_models.py` pass
