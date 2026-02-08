diff --git a/.claude/settings.json b/.claude/settings.json
index 25f9ef6..c72c6b7 100644
--- a/.claude/settings.json
+++ b/.claude/settings.json
@@ -1,7 +1,3 @@
 {
-  "enabledPlugins": {
-    "deep-project@piercelamb-plugins": true,
-    "deep-plan@piercelamb-plugins": true,
-    "deep-implement@piercelamb-plugins": true
-  }
+  "enabledPlugins": {}
 }
diff --git a/src/sidestage/migration/__init__.py b/src/sidestage/migration/__init__.py
new file mode 100644
index 0000000..6cd7e26
--- /dev/null
+++ b/src/sidestage/migration/__init__.py
@@ -0,0 +1 @@
+"""Campaign migration: import and backup operations."""
diff --git a/src/sidestage/migration/models.py b/src/sidestage/migration/models.py
new file mode 100644
index 0000000..d9e58cf
--- /dev/null
+++ b/src/sidestage/migration/models.py
@@ -0,0 +1,86 @@
+"""Pydantic data models for campaign migration (import/backup)."""
+
+from __future__ import annotations
+
+from typing import Any
+
+from pydantic import BaseModel
+
+
+class MigrationValidationIssue(BaseModel):
+    """A single validation problem found during pre-import checks."""
+
+    entity_id: str | None
+    file_path: str
+    severity: str  # "error" or "warning"
+    message: str
+
+
+class MigrationValidationReport(BaseModel):
+    """Aggregated validation results from a validation pass."""
+
+    valid: bool
+    entities_found: int
+    memories_found: int
+    entity_counts: dict[str, int]
+    errors: list[MigrationValidationIssue]
+    warnings: list[MigrationValidationIssue]
+
+
+class MigrationImportResult(BaseModel):
+    """Outcome of an import operation."""
+
+    phase: str  # "complete" or "failed"
+    total_entities: int
+    total_memories: int
+    processed_entities: int
+    processed_memories: int
+    errors: list[str]
+
+
+class MigrationBackupResult(BaseModel):
+    """Outcome of a backup operation."""
+
+    phase: str  # "complete" or "failed"
+    total_entities: int
+    total_memories: int
+    written_entities: int
+    written_memories: int
+    written_chatlogs: int
+    errors: list[str]
+
+
+class BackupStatus(BaseModel):
+    """Written to status.json inside the backup directory."""
+
+    timestamp: str
+    success: bool
+    entity_counts: dict[str, int]
+    memory_count: int
+    chatlog_count: int
+    errors: list[str]
+    sidestage_version: str
+
+
+class MigrationImportRequest(BaseModel):
+    """Request body for POST /v1/campaign/import."""
+
+    action: str = "validate"
+    force: bool = False
+
+
+class MigrationImportResponse(BaseModel):
+    """Response from the import endpoint."""
+
+    action: str
+    validation: MigrationValidationReport | None = None
+    result: MigrationImportResult | None = None
+
+
+class ParseResult(BaseModel):
+    """Intermediate output from the parser, consumed by validator and importer."""
+
+    entities: list[Any]
+    memories: list[Any]
+    chatlogs: dict[str, list[str]]
+    errors: list[MigrationValidationIssue]
diff --git a/tests/unit/test_migration_models.py b/tests/unit/test_migration_models.py
new file mode 100644
index 0000000..2c1a05f
--- /dev/null
+++ b/tests/unit/test_migration_models.py
@@ -0,0 +1,325 @@
+"""Unit tests for migration data models."""
+
+import json
+
+from sidestage.migration.models import (
+    BackupStatus,
+    MigrationBackupResult,
+    MigrationImportRequest,
+    MigrationImportResponse,
+    MigrationImportResult,
+    MigrationValidationIssue,
+    MigrationValidationReport,
+    ParseResult,
+)
+
+
+class TestMigrationValidationIssue:
+    """MigrationValidationIssue model tests."""
+
+    def test_accepts_error_severity(self):
+        """MigrationValidationIssue can be created with severity='error'."""
+        issue = MigrationValidationIssue(
+            entity_id="char-1",
+            file_path="characters/hero.md",
+            severity="error",
+            message="Missing required field: name",
+        )
+        assert issue.severity == "error"
+        assert issue.entity_id == "char-1"
+
+    def test_accepts_warning_severity(self):
+        """MigrationValidationIssue can be created with severity='warning'."""
+        issue = MigrationValidationIssue(
+            entity_id="loc-1",
+            file_path="locations/tavern.md",
+            severity="warning",
+            message="Description is empty",
+        )
+        assert issue.severity == "warning"
+
+    def test_entity_id_is_optional(self):
+        """MigrationValidationIssue works with entity_id=None (file-level issues)."""
+        issue = MigrationValidationIssue(
+            entity_id=None,
+            file_path="bad_file.md",
+            severity="error",
+            message="Malformed frontmatter",
+        )
+        assert issue.entity_id is None
+
+
+class TestMigrationValidationReport:
+    """MigrationValidationReport model tests."""
+
+    def test_valid_true_when_no_errors(self):
+        """Report with empty errors list has valid=True."""
+        report = MigrationValidationReport(
+            valid=True,
+            entities_found=5,
+            memories_found=3,
+            entity_counts={"Character": 2, "Location": 3},
+            errors=[],
+            warnings=[],
+        )
+        assert report.valid is True
+        assert report.errors == []
+
+    def test_valid_false_when_errors_present(self):
+        """Report with errors has valid=False."""
+        issue = MigrationValidationIssue(
+            entity_id="char-1",
+            file_path="characters/hero.md",
+            severity="error",
+            message="Duplicate ID",
+        )
+        report = MigrationValidationReport(
+            valid=False,
+            entities_found=5,
+            memories_found=3,
+            entity_counts={"Character": 2, "Location": 3},
+            errors=[issue],
+            warnings=[],
+        )
+        assert report.valid is False
+        assert len(report.errors) == 1
+
+    def test_entity_counts_dict(self):
+        """entity_counts holds per-type counts like {'Character': 3, 'Location': 2}."""
+        report = MigrationValidationReport(
+            valid=True,
+            entities_found=5,
+            memories_found=0,
+            entity_counts={"Character": 3, "Location": 2},
+            errors=[],
+            warnings=[],
+        )
+        assert report.entity_counts == {"Character": 3, "Location": 2}
+
+    def test_serializes_to_json(self):
+        """model_dump_json() produces valid JSON with all fields."""
+        report = MigrationValidationReport(
+            valid=True,
+            entities_found=5,
+            memories_found=3,
+            entity_counts={"Character": 2, "Location": 3},
+            errors=[],
+            warnings=[],
+        )
+        data = json.loads(report.model_dump_json())
+        assert "valid" in data
+        assert "entities_found" in data
+        assert "memories_found" in data
+        assert "entity_counts" in data
+        assert "errors" in data
+        assert "warnings" in data
+
+
+class TestMigrationImportResult:
+    """MigrationImportResult model tests."""
+
+    def test_phase_complete(self):
+        """Result with phase='complete' serializes correctly."""
+        result = MigrationImportResult(
+            phase="complete",
+            total_entities=10,
+            total_memories=5,
+            processed_entities=10,
+            processed_memories=5,
+            errors=[],
+        )
+        assert result.phase == "complete"
+
+    def test_phase_failed(self):
+        """Result with phase='failed' serializes correctly."""
+        result = MigrationImportResult(
+            phase="failed",
+            total_entities=10,
+            total_memories=5,
+            processed_entities=3,
+            processed_memories=0,
+            errors=["Schema creation failed"],
+        )
+        assert result.phase == "failed"
+        assert len(result.errors) == 1
+
+    def test_serializes_to_json(self):
+        """model_dump_json() produces valid JSON with all fields."""
+        result = MigrationImportResult(
+            phase="complete",
+            total_entities=10,
+            total_memories=5,
+            processed_entities=10,
+            processed_memories=5,
+            errors=[],
+        )
+        data = json.loads(result.model_dump_json())
+        assert "phase" in data
+        assert "total_entities" in data
+        assert "total_memories" in data
+        assert "processed_entities" in data
+        assert "processed_memories" in data
+        assert "errors" in data
+
+
+class TestMigrationBackupResult:
+    """MigrationBackupResult model tests."""
+
+    def test_includes_written_chatlogs(self):
+        """written_chatlogs field is present and serialized."""
+        result = MigrationBackupResult(
+            phase="complete",
+            total_entities=10,
+            total_memories=5,
+            written_entities=10,
+            written_memories=5,
+            written_chatlogs=3,
+            errors=[],
+        )
+        assert result.written_chatlogs == 3
+
+    def test_serializes_to_json(self):
+        """model_dump_json() produces valid JSON with all fields."""
+        result = MigrationBackupResult(
+            phase="complete",
+            total_entities=10,
+            total_memories=5,
+            written_entities=10,
+            written_memories=5,
+            written_chatlogs=3,
+            errors=[],
+        )
+        data = json.loads(result.model_dump_json())
+        assert "written_chatlogs" in data
+        assert "phase" in data
+
+
+class TestBackupStatus:
+    """BackupStatus model tests (written to status.json during backup)."""
+
+    def test_includes_all_required_fields(self):
+        """BackupStatus has timestamp, success, entity_counts, memory_count,
+        chatlog_count, errors, and sidestage_version fields."""
+        status = BackupStatus(
+            timestamp="2026-02-07T12:00:00Z",
+            success=True,
+            entity_counts={"Character": 2, "Location": 3},
+            memory_count=5,
+            chatlog_count=2,
+            errors=[],
+            sidestage_version="0.1.0",
+        )
+        assert status.timestamp == "2026-02-07T12:00:00Z"
+        assert status.success is True
+        assert status.entity_counts == {"Character": 2, "Location": 3}
+        assert status.memory_count == 5
+        assert status.chatlog_count == 2
+        assert status.errors == []
+        assert status.sidestage_version == "0.1.0"
+
+    def test_serializes_to_json(self):
+        """model_dump_json() produces valid JSON suitable for status.json."""
+        status = BackupStatus(
+            timestamp="2026-02-07T12:00:00Z",
+            success=True,
+            entity_counts={"Character": 2, "Location": 3},
+            memory_count=5,
+            chatlog_count=2,
+            errors=[],
+            sidestage_version="0.1.0",
+        )
+        data = json.loads(status.model_dump_json())
+        assert "timestamp" in data
+        assert "success" in data
+        assert "sidestage_version" in data
+
+
+class TestMigrationImportRequest:
+    """MigrationImportRequest API request model tests."""
+
+    def test_default_action_is_validate(self):
+        """Default action is 'validate' when not specified."""
+        req = MigrationImportRequest()
+        assert req.action == "validate"
+
+    def test_default_force_is_false(self):
+        """Default force is False when not specified."""
+        req = MigrationImportRequest()
+        assert req.force is False
+
+
+class TestMigrationImportResponse:
+    """MigrationImportResponse API response model tests."""
+
+    def test_validation_only_response(self):
+        """Response with action='validate' has validation but no result."""
+        report = MigrationValidationReport(
+            valid=True,
+            entities_found=5,
+            memories_found=3,
+            entity_counts={"Character": 2, "Location": 3},
+            errors=[],
+            warnings=[],
+        )
+        resp = MigrationImportResponse(
+            action="validate",
+            validation=report,
+            result=None,
+        )
+        assert resp.action == "validate"
+        assert resp.validation is not None
+        assert resp.result is None
+
+    def test_execute_response(self):
+        """Response with action='execute' has result (and optionally validation)."""
+        import_result = MigrationImportResult(
+            phase="complete",
+            total_entities=10,
+            total_memories=5,
+            processed_entities=10,
+            processed_memories=5,
+            errors=[],
+        )
+        resp = MigrationImportResponse(
+            action="execute",
+            validation=None,
+            result=import_result,
+        )
+        assert resp.action == "execute"
+        assert resp.result is not None
+
+
+class TestParseResult:
+    """ParseResult intermediate model tests."""
+
+    def test_empty_parse_result(self):
+        """ParseResult can be created with empty lists (no entities/memories)."""
+        pr = ParseResult(
+            entities=[],
+            memories=[],
+            chatlogs={},
+            errors=[],
+        )
+        assert pr.entities == []
+        assert pr.memories == []
+        assert pr.chatlogs == {}
+        assert pr.errors == []
+
+    def test_holds_entities_memories_chatlogs_errors(self):
+        """ParseResult has entities, memories, chatlogs, and errors fields."""
+        issue = MigrationValidationIssue(
+            entity_id=None,
+            file_path="bad.md",
+            severity="error",
+            message="Parse error",
+        )
+        pr = ParseResult(
+            entities=["entity1"],
+            memories=["memory1"],
+            chatlogs={"scene-1": ["line1", "line2"]},
+            errors=[issue],
+        )
+        assert len(pr.entities) == 1
+        assert len(pr.memories) == 1
+        assert "scene-1" in pr.chatlogs
+        assert len(pr.errors) == 1
