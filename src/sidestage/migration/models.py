"""Pydantic data models for campaign migration (import/backup)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class MigrationValidationIssue(BaseModel):
    """A single validation problem found during pre-import checks."""

    entity_id: str | None = None
    file_path: str
    severity: Literal["error", "warning"]
    message: str


class MigrationValidationReport(BaseModel):
    """Aggregated validation results from a validation pass."""

    valid: bool
    entities_found: int
    memories_found: int
    entity_counts: dict[str, int]
    errors: list[MigrationValidationIssue]
    warnings: list[MigrationValidationIssue]


class MigrationImportResult(BaseModel):
    """Outcome of an import operation."""

    phase: Literal["complete", "failed"]
    total_entities: int
    total_memories: int
    processed_entities: int
    processed_memories: int
    errors: list[str]


class MigrationBackupResult(BaseModel):
    """Outcome of a backup operation."""

    phase: Literal["complete", "failed"]
    total_entities: int
    total_memories: int
    written_entities: int
    written_memories: int
    written_chatlogs: int
    errors: list[str]


class BackupStatus(BaseModel):
    """Written to status.json inside the backup directory."""

    timestamp: str
    success: bool
    entity_counts: dict[str, int]
    memory_count: int
    chatlog_count: int
    errors: list[str]
    sidestage_version: str


class MigrationImportRequest(BaseModel):
    """Request body for POST /v1/campaign/import."""

    action: Literal["validate", "execute"] = "validate"
    force: bool = False


class MigrationImportResponse(BaseModel):
    """Response from the import endpoint."""

    action: str
    validation: MigrationValidationReport | None = None
    result: MigrationImportResult | None = None


class ParseResult(BaseModel):
    """Intermediate output from the parser, consumed by validator and importer."""

    entities: list[Any]
    memories: list[Any]
    chatlogs: dict[str, list[str]]
    errors: list[MigrationValidationIssue]
    warnings: list[MigrationValidationIssue] = []
