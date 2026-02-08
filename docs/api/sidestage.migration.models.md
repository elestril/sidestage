# `sidestage.migration.models`

Pydantic data models for campaign migration (import/backup).

## Classes

### `BackupStatus(BaseModel)`

Written to status.json inside the backup directory.

| Field | Type | Default |
|-------|------|---------|
| `timestamp` | `str` | — |
| `success` | `bool` | — |
| `entity_counts` | `dict[str, int]` | — |
| `memory_count` | `int` | — |
| `chatlog_count` | `int` | — |
| `errors` | `list[str]` | — |
| `sidestage_version` | `str` | — |

### `MigrationBackupResult(BaseModel)`

Outcome of a backup operation.

| Field | Type | Default |
|-------|------|---------|
| `phase` | `Literal[complete, failed]` | — |
| `total_entities` | `int` | — |
| `total_memories` | `int` | — |
| `written_entities` | `int` | — |
| `written_memories` | `int` | — |
| `written_chatlogs` | `int` | — |
| `errors` | `list[str]` | — |

### `MigrationImportRequest(BaseModel)`

Request body for POST /v1/campaign/import.

| Field | Type | Default |
|-------|------|---------|
| `action` | `Literal[validate, execute]` | 'validate' |
| `force` | `bool` | False |

### `MigrationImportResponse(BaseModel)`

Response from the import endpoint.

| Field | Type | Default |
|-------|------|---------|
| `action` | `str` | — |
| `validation` | `sidestage.migration.models.MigrationValidationReport | None` | — |
| `result` | `sidestage.migration.models.MigrationImportResult | None` | — |

### `MigrationImportResult(BaseModel)`

Outcome of an import operation.

| Field | Type | Default |
|-------|------|---------|
| `phase` | `Literal[complete, failed]` | — |
| `total_entities` | `int` | — |
| `total_memories` | `int` | — |
| `processed_entities` | `int` | — |
| `processed_memories` | `int` | — |
| `errors` | `list[str]` | — |

### `MigrationValidationIssue(BaseModel)`

A single validation problem found during pre-import checks.

| Field | Type | Default |
|-------|------|---------|
| `entity_id` | `str | None` | — |
| `file_path` | `str` | — |
| `severity` | `Literal[error, warning]` | — |
| `message` | `str` | — |

### `MigrationValidationReport(BaseModel)`

Aggregated validation results from a validation pass.

| Field | Type | Default |
|-------|------|---------|
| `valid` | `bool` | — |
| `entities_found` | `int` | — |
| `memories_found` | `int` | — |
| `entity_counts` | `dict[str, int]` | — |
| `errors` | `list[MigrationValidationIssue]` | — |
| `warnings` | `list[MigrationValidationIssue]` | — |

### `ParseResult(BaseModel)`

Intermediate output from the parser, consumed by validator and importer.

| Field | Type | Default |
|-------|------|---------|
| `entities` | `list[Any]` | — |
| `memories` | `list[Any]` | — |
| `chatlogs` | `dict[str, list[str]]` | — |
| `errors` | `list[MigrationValidationIssue]` | — |
| `warnings` | `list[MigrationValidationIssue]` | [] |
