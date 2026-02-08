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
def mock_orchestrator(tmp_path):
    """Create a SidestageOrchestrator with mocked Campaign dependencies."""
    with patch("sidestage.orchestrator.Campaign") as MockCampaign:
        mock_campaign = MagicMock()
        mock_campaign.health = CampaignHealth()
        mock_campaign.campaign_dir = tmp_path
        mock_campaign.list_entities = AsyncMock(return_value=[])
        mock_campaign.list_scenes = AsyncMock(return_value=[])
        MockCampaign.return_value = mock_campaign

        from sidestage.orchestrator import SidestageOrchestrator

        orch = SidestageOrchestrator("test_campaign", base_dir=tmp_path)
        return orch


@pytest.fixture
def client(mock_orchestrator):
    """FastAPI TestClient wrapping mock_orchestrator.fastapi_app."""
    return TestClient(mock_orchestrator.fastapi_app)


@pytest.fixture
def valid_validation_report():
    """Return a MigrationValidationReport with valid=True and sample counts."""
    return MigrationValidationReport(
        valid=True,
        entities_found=5,
        memories_found=3,
        entity_counts={"Character": 2, "Location": 2, "Item": 1},
        errors=[],
        warnings=[],
    )


@pytest.fixture
def invalid_validation_report():
    """Return a MigrationValidationReport with valid=False."""
    return MigrationValidationReport(
        valid=False,
        entities_found=5,
        memories_found=3,
        entity_counts={"Character": 2, "Location": 2, "Item": 1},
        errors=[
            MigrationValidationIssue(
                entity_id="char_1",
                file_path="characters/char_1.md",
                severity="error",
                message="Missing required field: name",
            )
        ],
        warnings=[],
    )


@pytest.fixture
def sample_parse_result():
    """Return a minimal ParseResult."""
    return ParseResult(
        entities=[{"id": "char_1", "name": "Test", "type": "Character"}],
        memories=[],
        chatlogs={},
        errors=[],
        warnings=[],
    )


@pytest.fixture
def sample_import_result():
    """Return a MigrationImportResult with phase='complete'."""
    return MigrationImportResult(
        phase="complete",
        total_entities=5,
        total_memories=3,
        processed_entities=5,
        processed_memories=3,
        errors=[],
    )


@pytest.fixture
def sample_backup_result():
    """Return a MigrationBackupResult with phase='complete'."""
    return MigrationBackupResult(
        phase="complete",
        total_entities=5,
        total_memories=3,
        written_entities=5,
        written_memories=3,
        written_chatlogs=2,
        errors=[],
    )


# --- Import endpoint: validation phase ---


def test_import_validate_returns_validation_report(
    client, mock_orchestrator, valid_validation_report, sample_parse_result, tmp_path
):
    """POST /v1/campaign/import with action=validate calls parse_directory
    and validate, returning a MigrationImportResponse with the validation report."""
    # Create the markdown directory so the route doesn't fail
    (tmp_path / "markdown").mkdir()

    with (
        patch(
            "sidestage.orchestrator.parse_directory",
            return_value=sample_parse_result,
        ) as mock_parse,
        patch(
            "sidestage.orchestrator.validate_parse_result",
            return_value=valid_validation_report,
        ) as mock_validate,
    ):
        response = client.post(
            "/v1/campaign/import",
            json={"action": "validate"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "validate"
    assert data["validation"]["valid"] is True
    assert data["validation"]["entities_found"] == 5
    assert data["result"] is None
    mock_parse.assert_called_once()
    mock_validate.assert_called_once()


def test_import_validate_with_errors_returns_report(
    client, mock_orchestrator, invalid_validation_report, sample_parse_result, tmp_path
):
    """POST /v1/campaign/import with action=validate when validation finds errors
    still returns 200 with the validation report showing valid=False."""
    (tmp_path / "markdown").mkdir()

    with (
        patch(
            "sidestage.orchestrator.parse_directory",
            return_value=sample_parse_result,
        ),
        patch(
            "sidestage.orchestrator.validate_parse_result",
            return_value=invalid_validation_report,
        ),
    ):
        response = client.post(
            "/v1/campaign/import",
            json={"action": "validate"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["validation"]["valid"] is False
    assert len(data["validation"]["errors"]) == 1


# --- Import endpoint: execute phase ---


def test_import_execute_performs_import(
    client,
    mock_orchestrator,
    valid_validation_report,
    sample_import_result,
    sample_parse_result,
    tmp_path,
):
    """POST /v1/campaign/import with action=execute calls parse_directory,
    validate, and import_campaign, returning the import result."""
    (tmp_path / "markdown").mkdir()

    with (
        patch(
            "sidestage.orchestrator.parse_directory",
            return_value=sample_parse_result,
        ),
        patch(
            "sidestage.orchestrator.validate_parse_result",
            return_value=valid_validation_report,
        ),
        patch(
            "sidestage.orchestrator.import_campaign",
            new_callable=AsyncMock,
            return_value=sample_import_result,
        ) as mock_import,
    ):
        response = client.post(
            "/v1/campaign/import",
            json={"action": "execute"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "execute"
    assert data["validation"]["valid"] is True
    assert data["result"]["phase"] == "complete"
    assert data["result"]["processed_entities"] == 5
    mock_import.assert_called_once()


def test_import_execute_with_validation_errors_aborts(
    client, mock_orchestrator, invalid_validation_report, sample_parse_result, tmp_path
):
    """POST /v1/campaign/import with action=execute aborts if validation
    finds errors (valid=False), returning the validation report without importing."""
    (tmp_path / "markdown").mkdir()

    with (
        patch(
            "sidestage.orchestrator.parse_directory",
            return_value=sample_parse_result,
        ),
        patch(
            "sidestage.orchestrator.validate_parse_result",
            return_value=invalid_validation_report,
        ),
        patch(
            "sidestage.orchestrator.import_campaign",
            new_callable=AsyncMock,
        ) as mock_import,
    ):
        response = client.post(
            "/v1/campaign/import",
            json={"action": "execute"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["validation"]["valid"] is False
    assert data["result"] is None
    mock_import.assert_not_called()


def test_import_execute_force_bypasses_warnings(
    client,
    mock_orchestrator,
    sample_import_result,
    sample_parse_result,
    tmp_path,
):
    """POST /v1/campaign/import with action=execute and force=True proceeds
    even when validation has warnings (but no errors)."""
    (tmp_path / "markdown").mkdir()

    report_with_warnings = MigrationValidationReport(
        valid=False,
        entities_found=5,
        memories_found=3,
        entity_counts={"Character": 2, "Location": 3},
        errors=[],
        warnings=[
            MigrationValidationIssue(
                file_path="characters/char_1.md",
                severity="warning",
                message="Optional field missing",
            )
        ],
    )

    with (
        patch(
            "sidestage.orchestrator.parse_directory",
            return_value=sample_parse_result,
        ),
        patch(
            "sidestage.orchestrator.validate_parse_result",
            return_value=report_with_warnings,
        ),
        patch(
            "sidestage.orchestrator.import_campaign",
            new_callable=AsyncMock,
            return_value=sample_import_result,
        ) as mock_import,
    ):
        response = client.post(
            "/v1/campaign/import",
            json={"action": "execute", "force": True},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["result"]["phase"] == "complete"
    mock_import.assert_called_once()


# --- Import endpoint: concurrency guard ---


def test_import_returns_409_when_degraded(client, mock_orchestrator):
    """POST /v1/campaign/import returns 409 Conflict when campaign.health.status
    is DEGRADED (another import is in progress)."""
    mock_orchestrator.campaign.health.status = HealthStatus.DEGRADED

    response = client.post(
        "/v1/campaign/import",
        json={"action": "validate"},
    )

    assert response.status_code == 409
    assert "already in progress" in response.json()["detail"].lower()


# --- Backup endpoint ---


def test_backup_returns_result(
    client, mock_orchestrator, sample_backup_result
):
    """POST /v1/campaign/backup calls export_campaign and returns the backup result."""
    with patch(
        "sidestage.orchestrator.export_campaign",
        new_callable=AsyncMock,
        return_value=sample_backup_result,
    ) as mock_export:
        response = client.post("/v1/campaign/backup")

    assert response.status_code == 200
    data = response.json()
    assert data["phase"] == "complete"
    assert data["written_entities"] == 5
    assert data["written_memories"] == 3
    assert data["written_chatlogs"] == 2
    mock_export.assert_called_once()


def test_backup_returns_409_when_degraded(client, mock_orchestrator):
    """POST /v1/campaign/backup returns 409 Conflict when campaign.health.status
    is DEGRADED."""
    mock_orchestrator.campaign.health.status = HealthStatus.DEGRADED

    response = client.post("/v1/campaign/backup")

    assert response.status_code == 409
    assert "already in progress" in response.json()["detail"].lower()
