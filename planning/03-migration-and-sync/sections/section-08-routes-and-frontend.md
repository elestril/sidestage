# Section 08: Routes and Frontend

## Overview

This section adds the two new FastAPI endpoints (`POST /v1/campaign/import` and `POST /v1/campaign/backup`) to the existing `SidestageOrchestrator` in `orchestrator.py`, and adds "Import Campaign" / "Backup Campaign" buttons to the frontend. The import endpoint implements a two-phase flow (validate, then execute). Both endpoints return 409 Conflict when the campaign health is DEGRADED (indicating another import is already in progress). After successful operations, a WebSocket broadcast of `entities_updated` notifies all connected clients.

### Dependencies

- **section-01-data-models**: Provides `MigrationImportRequest`, `MigrationImportResponse`, `MigrationValidationReport`, `MigrationImportResult`, `MigrationBackupResult`, `ParseResult` from `migration/models.py`
- **section-04-parser**: Provides `parse_directory()` from `migration/parser.py`
- **section-05-validator**: Provides `validate()` from `migration/validator.py`
- **section-06-exporter**: Provides `export_campaign()` from `migration/exporter.py`
- **section-07-importer**: Provides `import_campaign()` from `migration/importer.py`

All must be implemented before this section.

### What This Section Produces

- **Modified file**: `/home/harald/src/sidestage/src/sidestage/orchestrator.py` (add two new routes inside `_setup_routes()`)
- **Modified file**: `/home/harald/src/sidestage/frontend/src/EntityBrowser.tsx` (add import/backup campaign buttons)
- **Modified file**: `/home/harald/src/sidestage/frontend/src/types.ts` (no changes needed -- existing `WebSocketMessage` types cover `entities_updated`)
- **Test file**: `/home/harald/src/sidestage/tests/unit/test_migration_routes.py`

---

## Tests (Write First)

Create `/home/harald/src/sidestage/tests/unit/test_migration_routes.py` with the following test stubs. Tests use `pytest` with `httpx.AsyncClient` via FastAPI's `TestClient` or `pytest-anyio` with `httpx.ASGITransport` for async endpoint testing. All underlying campaign, parser, validator, importer, and exporter operations are mocked.

```python
"""Tests for campaign import/backup API routes in orchestrator.py."""

from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sidestage.health import CampaignHealth, HealthStatus
from sidestage.migration.models import (
    MigrationBackupResult,
    MigrationImportRequest,
    MigrationImportResponse,
    MigrationImportResult,
    MigrationValidationIssue,
    MigrationValidationReport,
    ParseResult,
)


# --- Fixtures ---

@pytest.fixture
def mock_orchestrator():
    """Create a SidestageOrchestrator with mocked Campaign dependencies.

    Patches Campaign.__init__ and LLM availability checks to avoid
    requiring real services. Sets up campaign.health as a real
    CampaignHealth instance and campaign.campaign_dir as a temp path.
    Returns the orchestrator with a fully registered FastAPI app.
    """
    ...


@pytest.fixture
def client(mock_orchestrator):
    """FastAPI TestClient wrapping mock_orchestrator.fastapi_app."""
    ...


@pytest.fixture
def valid_validation_report():
    """Return a MigrationValidationReport with valid=True and sample counts."""
    ...


@pytest.fixture
def sample_import_result():
    """Return a MigrationImportResult with phase='complete' and realistic counts."""
    ...


@pytest.fixture
def sample_backup_result():
    """Return a MigrationBackupResult with phase='complete' and realistic counts."""
    ...


# --- Import endpoint: validation phase ---

def test_import_validate_returns_validation_report(client, valid_validation_report):
    """POST /v1/campaign/import with action=validate calls parse_directory
    and validate, returning a MigrationImportResponse with the validation report."""
    ...


def test_import_validate_with_errors_returns_report(client):
    """POST /v1/campaign/import with action=validate when validation finds errors
    still returns 200 with the validation report showing valid=False."""
    ...


# --- Import endpoint: execute phase ---

def test_import_execute_performs_import(client, valid_validation_report, sample_import_result):
    """POST /v1/campaign/import with action=execute calls parse_directory,
    validate, and import_campaign, returning the import result."""
    ...


def test_import_execute_with_validation_errors_aborts(client):
    """POST /v1/campaign/import with action=execute aborts if validation
    finds errors (valid=False), returning the validation report without importing."""
    ...


def test_import_execute_force_bypasses_warnings(client, sample_import_result):
    """POST /v1/campaign/import with action=execute and force=True proceeds
    even when validation has warnings (but no errors)."""
    ...


# --- Import endpoint: concurrency guard ---

def test_import_returns_409_when_degraded(client):
    """POST /v1/campaign/import returns 409 Conflict when campaign.health.status
    is DEGRADED (another import is in progress)."""
    ...


# --- Backup endpoint ---

def test_backup_returns_result(client, sample_backup_result):
    """POST /v1/campaign/backup calls export_campaign and returns the backup result."""
    ...


def test_backup_returns_409_when_degraded(client):
    """POST /v1/campaign/backup returns 409 Conflict when campaign.health.status
    is DEGRADED."""
    ...
```

### Key testing principles

- **Use FastAPI `TestClient`**: The `SidestageOrchestrator` registers routes on `self.fastapi_app`. Create a `TestClient(mock_orchestrator.fastapi_app)` to send HTTP requests. `TestClient` is synchronous, which simplifies test code.
- **Patch dependencies at the module level**: Patch `migration.parser.parse_directory`, `migration.validator.validate`, `migration.importer.import_campaign`, and `migration.exporter.export_campaign` where they are imported in `orchestrator.py` (or in the route handlers themselves).
- **Use a real `CampaignHealth`**: The health object is lightweight. Set its status to DEGRADED via `await campaign.health.set_status(HealthStatus.DEGRADED, "test")` before making requests to test the 409 guard.
- **Mock Campaign construction**: `SidestageOrchestrator.__init__` calls `Campaign()` which requires an LLM endpoint and filesystem. Patch `Campaign.__init__` or use `MagicMock` for the campaign, but keep `campaign.health` as a real `CampaignHealth` and `campaign.campaign_dir` as a `Path`.
- **Verify response shapes**: The import endpoint returns `MigrationImportResponse` serialized as JSON. Assert that the response contains the expected `action`, `validation`, and `result` fields.

---

## Implementation Details

### File: `/home/harald/src/sidestage/src/sidestage/orchestrator.py`

Two new route handlers are added inside the existing `_setup_routes()` method of `SidestageOrchestrator`. They are placed after the existing entity routes and before the scene routes.

#### New imports to add at the top of `orchestrator.py`

```python
from sidestage.migration.models import (
    MigrationImportRequest,
    MigrationImportResponse,
    MigrationBackupResult,
)
from sidestage.health import HealthStatus
```

#### Route: `POST /v1/campaign/import`

Add this route handler inside `_setup_routes()`, after the existing entity import/export routes:

```python
@self.fastapi_app.post("/v1/campaign/import")
async def import_campaign_route(
    request: MigrationImportRequest,
) -> MigrationImportResponse:
    """Import entities and memories from the markdown directory into FalkorDB.

    Two-phase operation:
    - action='validate': Parse and validate the markdown directory, return report.
    - action='execute': Parse, validate, and execute the full import.

    Returns 409 if campaign health is DEGRADED (another import is in progress).
    """
```

**Route logic (step by step):**

1. **Check concurrency guard**: If `self.campaign.health.status == HealthStatus.DEGRADED`, raise `HTTPException(status_code=409, detail="Import already in progress")`. This prevents concurrent imports and prevents backup during import.

2. **Resolve markdown directory**: The markdown directory to import from is `self.campaign.campaign_dir / "markdown"`. If this directory does not exist, return a response with a validation report containing an error about the missing directory.

3. **Parse the directory**: Call `parse_directory()` from `migration/parser.py`:
   ```python
   from sidestage.migration.parser import parse_directory
   parse_result = parse_directory(markdown_dir)
   ```

4. **Validate**: Call `validate_parse_result()` from `migration/validator.py`:
   ```python
   from sidestage.migration.validator import validate_parse_result
   validation_report = validate_parse_result(parse_result)
   ```

5. **If action is "validate"**: Return `MigrationImportResponse(action="validate", validation=validation_report)`. No import is performed.

6. **If action is "execute"**:
   - Check validation result. If `validation_report.valid is False` and `request.force is False`, return the response with the validation report but no import result (the frontend will display errors and ask the user to fix them or force).
   - If valid (or force is True), call `import_campaign()` from `migration/importer.py`:
     ```python
     from sidestage.migration.importer import import_campaign
     result = await import_campaign(
         campaign=self.campaign,
         parse_result=parse_result,
         sync_manager=self.sync_manager,
         active_scenes=self.active_scenes,
     )
     ```
   - Return `MigrationImportResponse(action="execute", validation=validation_report, result=result)`.

**Notes on the import endpoint:**
- The `parse_directory` function is synchronous (it reads files from disk). It should be called in a thread pool via `asyncio.to_thread()` if blocking is a concern, but for the initial implementation a direct call is acceptable since the import is already a heavy operation.
- The `validate_parse_result` function is also synchronous and fast.
- The `import_campaign` function is async and handles its own error recovery (setting health DEGRADED/HEALTHY, dropping graph, etc.).

#### Route: `POST /v1/campaign/backup`

```python
@self.fastapi_app.post("/v1/campaign/backup")
async def backup_campaign_route() -> MigrationBackupResult:
    """Backup all entities, memories, and chat logs to the markdown directory.

    Returns 409 if campaign health is DEGRADED (import in progress).
    """
```

**Route logic:**

1. **Check concurrency guard**: Same as import -- if `self.campaign.health.status == HealthStatus.DEGRADED`, raise `HTTPException(status_code=409, detail="Operation in progress")`.

2. **Call exporter**:
   ```python
   from sidestage.migration.exporter import export_campaign
   result = await export_campaign(self.campaign)
   ```

3. **Broadcast entities_updated**: After a successful backup, broadcast a WebSocket message so frontends know data may have changed:
   ```python
   if result.phase == "complete":
       await self.sync_manager.broadcast({"type": "entities_updated"})
   ```

4. **Return result**: Return the `MigrationBackupResult` directly.

#### Where to place the routes

Inside `_setup_routes()`, the new routes should be placed after the existing entity routes (after the `@self.fastapi_app.post("/v1/entities/{entity_id}")` handler) and before the `@self.fastapi_app.post("/v1/campaign/reload-defaults")` handler. This groups campaign-level operations together:

```
existing:  POST /v1/entities/export         (old, deprecated)
existing:  POST /v1/entities/import         (old, deprecated)
existing:  POST /v1/entities/{entity_id}
existing:  POST /v1/campaign/reload-defaults
NEW:       POST /v1/campaign/import         (new migration import)
NEW:       POST /v1/campaign/backup         (new migration backup)
```

### Concurrency guard details

The concurrency guard uses the existing `CampaignHealth` from `/home/harald/src/sidestage/src/sidestage/health.py`. The `HealthStatus` enum has three values: `HEALTHY`, `DEGRADED`, `UNHEALTHY`. The guard checks:

```python
if self.campaign.health.status == HealthStatus.DEGRADED:
    raise HTTPException(
        status_code=409,
        detail="Campaign operation already in progress"
    )
```

This check happens at the START of both the import and backup route handlers, BEFORE any parsing or exporting begins. The importer (section-07) sets health to DEGRADED at the beginning of its process and restores it to HEALTHY in a `finally` block. This means:

- While an import is running, both import and backup requests get 409.
- After import completes (success or failure), health returns to HEALTHY and new requests are accepted.
- The backup endpoint does NOT set health to DEGRADED -- it is a read-only operation that does not modify the graph. However, it is guarded against running during an import because the graph state would be inconsistent.

### WebSocket broadcast

After a successful import, the importer itself (section-07) already broadcasts `entities_updated` via the sync_manager passed to it. The import route handler does NOT need to broadcast again.

After a successful backup, the backup route handler broadcasts `entities_updated`. This may seem unnecessary (backup does not change data), but it signals to the frontend that the backup directory has been updated and allows the UI to refresh its display (e.g., showing "backup complete" status). The broadcast is only sent if `result.phase == "complete"`.

The existing WebSocket handler in `AppContext.tsx` already listens for `entities_updated` messages and calls `loadEntities()` to refresh the entity list. No changes are needed to the WebSocket handling logic.

---

## Frontend Changes

### File: `/home/harald/src/sidestage/frontend/src/EntityBrowser.tsx`

The existing `EntityBrowser` component already has "Import" and "Export" buttons that call the old `/v1/entities/import` and `/v1/entities/export` endpoints. Add two new buttons for the migration-based "Import Campaign" and "Backup Campaign" operations.

#### What to add

Add a new function `handleCampaignSync` alongside the existing `handleSync` function in the `EntityBrowser` component. This function handles the two-phase import flow and the one-click backup:

```typescript
const handleCampaignSync = async (type: 'import' | 'backup') => {
    // For 'backup': POST /v1/campaign/backup, show result
    // For 'import': two-phase:
    //   1. POST /v1/campaign/import {action: "validate"}
    //   2. Show validation results (counts, warnings, data-loss warning)
    //   3. If user confirms: POST /v1/campaign/import {action: "execute"}
    //   4. Show import result
};
```

**Import flow (UI):**

1. User clicks "Import Campaign".
2. Frontend sends `POST /v1/campaign/import` with `{"action": "validate"}`.
3. If the response comes back with `validation.valid === false`, display errors using `window.alert()` or a simple modal.
4. If `validation.valid === true`, show a confirmation dialog with:
   - Entity counts (e.g., "Found 5 Characters, 3 Locations...")
   - Number of memories
   - Any warnings
   - A data-loss warning: "This will replace all existing campaign data. This action cannot be undone."
5. If user confirms, send `POST /v1/campaign/import` with `{"action": "execute"}`.
6. Show result (success/failure, counts).

**Backup flow (UI):**

1. User clicks "Backup Campaign".
2. Frontend sends `POST /v1/campaign/backup`.
3. Show result (success/failure, counts) via `window.alert()` or inline status.

**409 handling:**

If either endpoint returns 409, display a message like "Another operation is in progress. Please wait."

#### Where to place the buttons

Add the "Import Campaign" and "Backup Campaign" buttons next to the existing "Import" and "Export" buttons in the EntityBrowser's header area. The existing buttons are in a flex container with `gap-2`:

```tsx
<div className="flex gap-2">
  <button
    onClick={() => handleSync('import')}
    className="text-[10px] uppercase font-bold text-[#03dac6] hover:opacity-80 transition-opacity"
  >
    Import
  </button>
  <button
    onClick={() => handleSync('export')}
    className="text-[10px] uppercase font-bold text-[#666] hover:text-white transition-colors"
  >
    Export
  </button>
  {/* NEW: Campaign-level import/backup */}
  <button
    onClick={() => handleCampaignSync('import')}
    className="text-[10px] uppercase font-bold text-[#bb86fc] hover:opacity-80 transition-opacity"
  >
    Import Campaign
  </button>
  <button
    onClick={() => handleCampaignSync('backup')}
    className="text-[10px] uppercase font-bold text-[#bb86fc] hover:opacity-80 transition-opacity"
  >
    Backup Campaign
  </button>
</div>
```

Use the `#bb86fc` (purple) color to visually distinguish the new campaign-level buttons from the old entity-level import/export buttons, which use `#03dac6` (teal) and `#666` (gray).

#### Frontend function stubs

```typescript
const handleCampaignSync = async (type: 'import' | 'backup') => {
  try {
    if (type === 'backup') {
      const response = await fetch('/v1/campaign/backup', { method: 'POST' });
      if (response.status === 409) {
        alert('Another operation is in progress. Please wait.');
        return;
      }
      if (response.ok) {
        const result = await response.json();
        alert(`Backup complete: ${result.written_entities} entities, ${result.written_memories} memories, ${result.written_chatlogs} chat logs.`);
      }
    } else {
      // Phase 1: Validate
      const validateResponse = await fetch('/v1/campaign/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'validate' })
      });
      if (validateResponse.status === 409) {
        alert('Another operation is in progress. Please wait.');
        return;
      }
      const validateResult = await validateResponse.json();
      const validation = validateResult.validation;

      if (!validation.valid) {
        alert(`Validation failed with ${validation.errors.length} error(s). Fix the issues and try again.`);
        return;
      }

      // Show confirmation with counts
      const counts = Object.entries(validation.entity_counts)
        .map(([type, count]) => `${count} ${type}(s)`)
        .join(', ');
      const confirmed = confirm(
        `Import will replace all existing data.\n\n` +
        `Found: ${counts}\n` +
        `Memories: ${validation.memories_found}\n` +
        `Warnings: ${validation.warnings.length}\n\n` +
        `This action cannot be undone. Continue?`
      );

      if (!confirmed) return;

      // Phase 2: Execute
      const executeResponse = await fetch('/v1/campaign/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'execute' })
      });
      if (executeResponse.ok) {
        const executeResult = await executeResponse.json();
        const result = executeResult.result;
        alert(`Import ${result.phase}: ${result.processed_entities} entities, ${result.processed_memories} memories.`);
        await loadEntities();
      }
    }
  } catch (error) {
    console.error(`Campaign ${type} failed:`, error);
    alert(`Campaign ${type} failed. Check console for details.`);
  }
};
```

This uses `window.alert()` and `window.confirm()` for simplicity. A more polished UI (modals, progress indicators) can be added later but is not in scope for this section.

### No changes needed to `types.ts`

The existing `WebSocketMessage` type union already includes `EntitiesUpdatedBroadcast` with `type: 'entities_updated'`, which is the message broadcast after import/backup operations. No new TypeScript types are needed.

### No changes needed to `AppContext.tsx`

The existing WebSocket message handler in `AppContext.tsx` already handles `entities_updated` by calling `loadEntities()`. When the import completes and the server broadcasts `entities_updated`, all connected frontends will automatically refresh their entity lists. No changes are needed.

---

## Error handling in routes

### Import endpoint errors

| Scenario | HTTP Status | Response |
|----------|-------------|----------|
| Health is DEGRADED | 409 | `{"detail": "Campaign operation already in progress"}` |
| Markdown directory missing | 200 | `MigrationImportResponse` with validation errors |
| Parse errors | 200 | `MigrationImportResponse` with validation errors |
| Validation errors (action=validate) | 200 | `MigrationImportResponse` with `valid=False` |
| Validation errors (action=execute, force=False) | 200 | `MigrationImportResponse` with validation only, no result |
| Import succeeds | 200 | `MigrationImportResponse` with `phase="complete"` |
| Import partially fails | 200 | `MigrationImportResponse` with `phase="failed"` and errors |

Note: The import endpoint always returns 200 (not 4xx/5xx) for application-level errors because the error details are structured in the response body. Only the concurrency guard uses 409.

### Backup endpoint errors

| Scenario | HTTP Status | Response |
|----------|-------------|----------|
| Health is DEGRADED | 409 | `{"detail": "Campaign operation already in progress"}` |
| No graph client | 200 | `MigrationBackupResult` with `phase="failed"` |
| Backup succeeds | 200 | `MigrationBackupResult` with `phase="complete"` |
| Backup partially fails | 200 | `MigrationBackupResult` with errors |

---

## Acceptance Criteria

1. `POST /v1/campaign/import` with `action=validate` parses and validates the markdown directory, returning a `MigrationImportResponse` with a `MigrationValidationReport`
2. `POST /v1/campaign/import` with `action=execute` performs the full import (parse, validate, import) and returns the result
3. `POST /v1/campaign/import` with `action=execute` aborts if validation fails (unless `force=True`)
4. `POST /v1/campaign/backup` calls `export_campaign` and returns the `MigrationBackupResult`
5. Both endpoints return 409 when `campaign.health.status == HealthStatus.DEGRADED`
6. After successful import, `entities_updated` is broadcast (handled by the importer, not the route)
7. After successful backup, `entities_updated` is broadcast by the route handler
8. Frontend EntityBrowser has "Import Campaign" and "Backup Campaign" buttons
9. Frontend import flow is two-phase: validate with preview, then confirm and execute
10. Frontend handles 409 responses with user-facing messages
11. All tests in `test_migration_routes.py` pass
