diff --git a/frontend/src/EntityBrowser.tsx b/frontend/src/EntityBrowser.tsx
index 5e573b2..1303b84 100644
--- a/frontend/src/EntityBrowser.tsx
+++ b/frontend/src/EntityBrowser.tsx
@@ -255,6 +255,70 @@ export const EntityBrowser: React.FC<EntityBrowserProps> = ({ selectedId, onSele
     }
   };
 
+  const handleCampaignSync = async (type: 'import' | 'backup') => {
+    try {
+      if (type === 'backup') {
+        const response = await fetch('/v1/campaign/backup', { method: 'POST' });
+        if (response.status === 409) {
+          alert('Another operation is in progress. Please wait.');
+          return;
+        }
+        if (response.ok) {
+          const result = await response.json();
+          alert(`Backup complete: ${result.written_entities} entities, ${result.written_memories} memories, ${result.written_chatlogs} chat logs.`);
+        }
+      } else {
+        // Phase 1: Validate
+        const validateResponse = await fetch('/v1/campaign/import', {
+          method: 'POST',
+          headers: { 'Content-Type': 'application/json' },
+          body: JSON.stringify({ action: 'validate' })
+        });
+        if (validateResponse.status === 409) {
+          alert('Another operation is in progress. Please wait.');
+          return;
+        }
+        const validateResult = await validateResponse.json();
+        const validation = validateResult.validation;
+
+        if (!validation.valid) {
+          alert(`Validation failed with ${validation.errors.length} error(s). Fix the issues and try again.`);
+          return;
+        }
+
+        // Show confirmation with counts
+        const counts = Object.entries(validation.entity_counts)
+          .map(([type, count]) => `${count} ${type}(s)`)
+          .join(', ');
+        const confirmed = confirm(
+          `Import will replace all existing data.\n\n` +
+          `Found: ${counts}\n` +
+          `Memories: ${validation.memories_found}\n` +
+          `Warnings: ${validation.warnings.length}\n\n` +
+          `This action cannot be undone. Continue?`
+        );
+
+        if (!confirmed) return;
+
+        // Phase 2: Execute
+        const executeResponse = await fetch('/v1/campaign/import', {
+          method: 'POST',
+          headers: { 'Content-Type': 'application/json' },
+          body: JSON.stringify({ action: 'execute' })
+        });
+        if (executeResponse.ok) {
+          const executeResult = await executeResponse.json();
+          const result = executeResult.result;
+          alert(`Import ${result.phase}: ${result.processed_entities} entities, ${result.processed_memories} memories.`);
+          await loadEntities();
+        }
+      }
+    } catch (error) {
+      console.error(`Campaign ${type} failed:`, error);
+      alert(`Campaign ${type} failed. Check console for details.`);
+    }
+  };
+
   const getEntityIcon = (type: string) => {
     switch (type) {
       case 'Character': return <User size={14} className="text-orange-400" />;
@@ -288,12 +352,24 @@ export const EntityBrowser: React.FC<EntityBrowserProps> = ({ selectedId, onSele
               >
                 Import
               </button>
-              <button 
+              <button
                 onClick={() => handleSync('export')}
                 className="text-[10px] uppercase font-bold text-[#666] hover:text-white transition-colors"
               >
                 Export
               </button>
+              <button
+                onClick={() => handleCampaignSync('import')}
+                className="text-[10px] uppercase font-bold text-[#bb86fc] hover:opacity-80 transition-opacity"
+              >
+                Import Campaign
+              </button>
+              <button
+                onClick={() => handleCampaignSync('backup')}
+                className="text-[10px] uppercase font-bold text-[#bb86fc] hover:opacity-80 transition-opacity"
+              >
+                Backup Campaign
+              </button>
             </div>
           </div>
           <div className="flex gap-1 overflow-x-auto pb-1 scrollbar-none">
diff --git a/planning/03-migration-and-sync/implementation/deep_implement_config.json b/planning/03-migration-and-sync/implementation/deep_implement_config.json
index cf959c5..2872ebc 100644
--- a/planning/03-migration-and-sync/implementation/deep_implement_config.json
+++ b/planning/03-migration-and-sync/implementation/deep_implement_config.json
@@ -41,6 +41,10 @@
     "section-06-exporter": {
       "status": "complete",
       "commit_hash": "2f76567"
+    },
+    "section-07-importer": {
+      "status": "complete",
+      "commit_hash": "c1e3383"
     }
   },
   "pre_commit": {
diff --git a/src/sidestage/orchestrator.py b/src/sidestage/orchestrator.py
index 0d8ee38..6dfb1bc 100644
--- a/src/sidestage/orchestrator.py
+++ b/src/sidestage/orchestrator.py
@@ -10,6 +10,16 @@ import asyncio
 
 from sidestage.campaign import Campaign
 from sidestage.sync import SyncManager
+from sidestage.health import HealthStatus
+from sidestage.migration.models import (
+    MigrationImportRequest,
+    MigrationImportResponse,
+    MigrationBackupResult,
+)
+from sidestage.migration.parser import parse_directory
+from sidestage.migration.validator import validate_parse_result
+from sidestage.migration.importer import import_campaign
+from sidestage.migration.exporter import export_campaign
 from sidestage.schemas import (
     SceneCreateRequest, 
     EntityMarkdownUpdateRequest, 
@@ -220,6 +230,91 @@ class SidestageOrchestrator:
             await self.sync_manager.broadcast({"type": "entities_updated"})
             return {"status": "ok"}
 
+        # Campaign migration (import/backup)
+        @self.fastapi_app.post("/v1/campaign/import")
+        async def import_campaign_route(
+            request: MigrationImportRequest,
+        ) -> MigrationImportResponse:
+            """Import entities and memories from the markdown directory into FalkorDB.
+
+            Two-phase operation:
+            - action='validate': Parse and validate the markdown directory, return report.
+            - action='execute': Parse, validate, and execute the full import.
+
+            Returns 409 if campaign health is DEGRADED (another import is in progress).
+            """
+            if self.campaign.health.status == HealthStatus.DEGRADED:
+                raise HTTPException(
+                    status_code=409,
+                    detail="Campaign operation already in progress",
+                )
+
+            markdown_dir = self.campaign.campaign_dir / "markdown"
+            if not markdown_dir.exists():
+                from sidestage.migration.models import MigrationValidationReport, MigrationValidationIssue
+                return MigrationImportResponse(
+                    action=request.action,
+                    validation=MigrationValidationReport(
+                        valid=False,
+                        entities_found=0,
+                        memories_found=0,
+                        entity_counts={},
+                        errors=[
+                            MigrationValidationIssue(
+                                file_path=str(markdown_dir),
+                                severity="error",
+                                message="Markdown directory does not exist",
+                            )
+                        ],
+                        warnings=[],
+                    ),
+                )
+
+            parse_result = parse_directory(markdown_dir)
+            validation_report = validate_parse_result(parse_result)
+
+            if request.action == "validate":
+                return MigrationImportResponse(
+                    action="validate",
+                    validation=validation_report,
+                )
+
+            # action == "execute"
+            if not validation_report.valid and not request.force:
+                return MigrationImportResponse(
+                    action="execute",
+                    validation=validation_report,
+                )
+
+            result = await import_campaign(
+                campaign=self.campaign,
+                parse_result=parse_result,
+                sync_manager=self.sync_manager,
+                active_scenes=self.active_scenes,
+            )
+            return MigrationImportResponse(
+                action="execute",
+                validation=validation_report,
+                result=result,
+            )
+
+        @self.fastapi_app.post("/v1/campaign/backup")
+        async def backup_campaign_route() -> MigrationBackupResult:
+            """Backup all entities, memories, and chat logs to the markdown directory.
+
+            Returns 409 if campaign health is DEGRADED (import in progress).
+            """
+            if self.campaign.health.status == HealthStatus.DEGRADED:
+                raise HTTPException(
+                    status_code=409,
+                    detail="Campaign operation already in progress",
+                )
+
+            result = await export_campaign(self.campaign)
+            if result.phase == "complete":
+                await self.sync_manager.broadcast({"type": "entities_updated"})
+            return result
+
         # Scenes
         @self.fastapi_app.get("/v1/scenes")
         async def list_scenes():
diff --git a/tests/unit/test_migration_routes.py b/tests/unit/test_migration_routes.py
new file mode 100644
index 0000000..3e8f707
--- /dev/null
+++ b/tests/unit/test_migration_routes.py
@@ -0,0 +1,360 @@
+"""Tests for campaign import/backup API routes in orchestrator.py."""
+
+from unittest.mock import AsyncMock, MagicMock, patch
+from pathlib import Path
+
+import pytest
+from fastapi.testclient import TestClient
+
+from sidestage.health import CampaignHealth, HealthStatus
+from sidestage.migration.models import (
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
+# --- Fixtures ---
+
+
+@pytest.fixture
+def mock_orchestrator(tmp_path):
+    """Create a SidestageOrchestrator with mocked Campaign dependencies."""
+    with patch("sidestage.orchestrator.Campaign") as MockCampaign:
+        mock_campaign = MagicMock()
+        mock_campaign.health = CampaignHealth()
+        mock_campaign.campaign_dir = tmp_path
+        mock_campaign.list_entities = AsyncMock(return_value=[])
+        mock_campaign.list_scenes = AsyncMock(return_value=[])
+        MockCampaign.return_value = mock_campaign
+
+        from sidestage.orchestrator import SidestageOrchestrator
+
+        orch = SidestageOrchestrator("test_campaign", base_dir=tmp_path)
+        return orch
+
+
+@pytest.fixture
+def client(mock_orchestrator):
+    """FastAPI TestClient wrapping mock_orchestrator.fastapi_app."""
+    return TestClient(mock_orchestrator.fastapi_app)
+
+
+@pytest.fixture
+def valid_validation_report():
+    """Return a MigrationValidationReport with valid=True and sample counts."""
+    return MigrationValidationReport(
+        valid=True,
+        entities_found=5,
+        memories_found=3,
+        entity_counts={"Character": 2, "Location": 2, "Item": 1},
+        errors=[],
+        warnings=[],
+    )
+
+
+@pytest.fixture
+def invalid_validation_report():
+    """Return a MigrationValidationReport with valid=False."""
+    return MigrationValidationReport(
+        valid=False,
+        entities_found=5,
+        memories_found=3,
+        entity_counts={"Character": 2, "Location": 2, "Item": 1},
+        errors=[
+            MigrationValidationIssue(
+                entity_id="char_1",
+                file_path="characters/char_1.md",
+                severity="error",
+                message="Missing required field: name",
+            )
+        ],
+        warnings=[],
+    )
+
+
+@pytest.fixture
+def sample_parse_result():
+    """Return a minimal ParseResult."""
+    return ParseResult(
+        entities=[{"id": "char_1", "name": "Test", "type": "Character"}],
+        memories=[],
+        chatlogs={},
+        errors=[],
+        warnings=[],
+    )
+
+
+@pytest.fixture
+def sample_import_result():
+    """Return a MigrationImportResult with phase='complete'."""
+    return MigrationImportResult(
+        phase="complete",
+        total_entities=5,
+        total_memories=3,
+        processed_entities=5,
+        processed_memories=3,
+        errors=[],
+    )
+
+
+@pytest.fixture
+def sample_backup_result():
+    """Return a MigrationBackupResult with phase='complete'."""
+    return MigrationBackupResult(
+        phase="complete",
+        total_entities=5,
+        total_memories=3,
+        written_entities=5,
+        written_memories=3,
+        written_chatlogs=2,
+        errors=[],
+    )
+
+
+# --- Import endpoint: validation phase ---
+
+
+def test_import_validate_returns_validation_report(
+    client, mock_orchestrator, valid_validation_report, sample_parse_result, tmp_path
+):
+    """POST /v1/campaign/import with action=validate calls parse_directory
+    and validate, returning a MigrationImportResponse with the validation report."""
+    # Create the markdown directory so the route doesn't fail
+    (tmp_path / "markdown").mkdir()
+
+    with (
+        patch(
+            "sidestage.orchestrator.parse_directory",
+            return_value=sample_parse_result,
+        ) as mock_parse,
+        patch(
+            "sidestage.orchestrator.validate_parse_result",
+            return_value=valid_validation_report,
+        ) as mock_validate,
+    ):
+        response = client.post(
+            "/v1/campaign/import",
+            json={"action": "validate"},
+        )
+
+    assert response.status_code == 200
+    data = response.json()
+    assert data["action"] == "validate"
+    assert data["validation"]["valid"] is True
+    assert data["validation"]["entities_found"] == 5
+    assert data["result"] is None
+    mock_parse.assert_called_once()
+    mock_validate.assert_called_once()
+
+
+def test_import_validate_with_errors_returns_report(
+    client, mock_orchestrator, invalid_validation_report, sample_parse_result, tmp_path
+):
+    """POST /v1/campaign/import with action=validate when validation finds errors
+    still returns 200 with the validation report showing valid=False."""
+    (tmp_path / "markdown").mkdir()
+
+    with (
+        patch(
+            "sidestage.orchestrator.parse_directory",
+            return_value=sample_parse_result,
+        ),
+        patch(
+            "sidestage.orchestrator.validate_parse_result",
+            return_value=invalid_validation_report,
+        ),
+    ):
+        response = client.post(
+            "/v1/campaign/import",
+            json={"action": "validate"},
+        )
+
+    assert response.status_code == 200
+    data = response.json()
+    assert data["validation"]["valid"] is False
+    assert len(data["validation"]["errors"]) == 1
+
+
+# --- Import endpoint: execute phase ---
+
+
+def test_import_execute_performs_import(
+    client,
+    mock_orchestrator,
+    valid_validation_report,
+    sample_import_result,
+    sample_parse_result,
+    tmp_path,
+):
+    """POST /v1/campaign/import with action=execute calls parse_directory,
+    validate, and import_campaign, returning the import result."""
+    (tmp_path / "markdown").mkdir()
+
+    with (
+        patch(
+            "sidestage.orchestrator.parse_directory",
+            return_value=sample_parse_result,
+        ),
+        patch(
+            "sidestage.orchestrator.validate_parse_result",
+            return_value=valid_validation_report,
+        ),
+        patch(
+            "sidestage.orchestrator.import_campaign",
+            new_callable=AsyncMock,
+            return_value=sample_import_result,
+        ) as mock_import,
+    ):
+        response = client.post(
+            "/v1/campaign/import",
+            json={"action": "execute"},
+        )
+
+    assert response.status_code == 200
+    data = response.json()
+    assert data["action"] == "execute"
+    assert data["validation"]["valid"] is True
+    assert data["result"]["phase"] == "complete"
+    assert data["result"]["processed_entities"] == 5
+    mock_import.assert_called_once()
+
+
+def test_import_execute_with_validation_errors_aborts(
+    client, mock_orchestrator, invalid_validation_report, sample_parse_result, tmp_path
+):
+    """POST /v1/campaign/import with action=execute aborts if validation
+    finds errors (valid=False), returning the validation report without importing."""
+    (tmp_path / "markdown").mkdir()
+
+    with (
+        patch(
+            "sidestage.orchestrator.parse_directory",
+            return_value=sample_parse_result,
+        ),
+        patch(
+            "sidestage.orchestrator.validate_parse_result",
+            return_value=invalid_validation_report,
+        ),
+        patch(
+            "sidestage.orchestrator.import_campaign",
+            new_callable=AsyncMock,
+        ) as mock_import,
+    ):
+        response = client.post(
+            "/v1/campaign/import",
+            json={"action": "execute"},
+        )
+
+    assert response.status_code == 200
+    data = response.json()
+    assert data["validation"]["valid"] is False
+    assert data["result"] is None
+    mock_import.assert_not_called()
+
+
+def test_import_execute_force_bypasses_warnings(
+    client,
+    mock_orchestrator,
+    sample_import_result,
+    sample_parse_result,
+    tmp_path,
+):
+    """POST /v1/campaign/import with action=execute and force=True proceeds
+    even when validation has warnings (but no errors)."""
+    (tmp_path / "markdown").mkdir()
+
+    report_with_warnings = MigrationValidationReport(
+        valid=False,
+        entities_found=5,
+        memories_found=3,
+        entity_counts={"Character": 2, "Location": 3},
+        errors=[],
+        warnings=[
+            MigrationValidationIssue(
+                file_path="characters/char_1.md",
+                severity="warning",
+                message="Optional field missing",
+            )
+        ],
+    )
+
+    with (
+        patch(
+            "sidestage.orchestrator.parse_directory",
+            return_value=sample_parse_result,
+        ),
+        patch(
+            "sidestage.orchestrator.validate_parse_result",
+            return_value=report_with_warnings,
+        ),
+        patch(
+            "sidestage.orchestrator.import_campaign",
+            new_callable=AsyncMock,
+            return_value=sample_import_result,
+        ) as mock_import,
+    ):
+        response = client.post(
+            "/v1/campaign/import",
+            json={"action": "execute", "force": True},
+        )
+
+    assert response.status_code == 200
+    data = response.json()
+    assert data["result"]["phase"] == "complete"
+    mock_import.assert_called_once()
+
+
+# --- Import endpoint: concurrency guard ---
+
+
+def test_import_returns_409_when_degraded(client, mock_orchestrator):
+    """POST /v1/campaign/import returns 409 Conflict when campaign.health.status
+    is DEGRADED (another import is in progress)."""
+    mock_orchestrator.campaign.health.status = HealthStatus.DEGRADED
+
+    response = client.post(
+        "/v1/campaign/import",
+        json={"action": "validate"},
+    )
+
+    assert response.status_code == 409
+    assert "already in progress" in response.json()["detail"].lower()
+
+
+# --- Backup endpoint ---
+
+
+def test_backup_returns_result(
+    client, mock_orchestrator, sample_backup_result
+):
+    """POST /v1/campaign/backup calls export_campaign and returns the backup result."""
+    with patch(
+        "sidestage.orchestrator.export_campaign",
+        new_callable=AsyncMock,
+        return_value=sample_backup_result,
+    ) as mock_export:
+        response = client.post("/v1/campaign/backup")
+
+    assert response.status_code == 200
+    data = response.json()
+    assert data["phase"] == "complete"
+    assert data["written_entities"] == 5
+    assert data["written_memories"] == 3
+    assert data["written_chatlogs"] == 2
+    mock_export.assert_called_once()
+
+
+def test_backup_returns_409_when_degraded(client, mock_orchestrator):
+    """POST /v1/campaign/backup returns 409 Conflict when campaign.health.status
+    is DEGRADED."""
+    mock_orchestrator.campaign.health.status = HealthStatus.DEGRADED
+
+    response = client.post("/v1/campaign/backup")
+
+    assert response.status_code == 409
+    assert "already in progress" in response.json()["detail"].lower()
