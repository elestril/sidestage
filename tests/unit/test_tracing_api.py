"""Tests for tracing REST API endpoints in orchestrator.py."""

from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sidestage.health import CampaignHealth
from sidestage.orchestrator import SidestageOrchestrator


# --- Fixtures ---


@pytest.fixture
def mock_memory_exporter():
    """Create a mock InMemoryTraceExporter."""
    exporter = MagicMock()
    exporter.get_traces.return_value = []
    exporter.get_trace.return_value = None
    exporter.get_traces_for_scene.return_value = []
    return exporter


@pytest.fixture
def mock_sqlite_exporter():
    """Create a mock SQLiteTraceExporter."""
    exporter = MagicMock()
    exporter.query_traces.return_value = []
    exporter.query_spans.return_value = []
    return exporter


@pytest.fixture
def mock_orchestrator(tmp_path: Path, mock_memory_exporter, mock_sqlite_exporter):
    """Create a SidestageOrchestrator with mocked Campaign and tracing dependencies."""
    with (
        patch("sidestage.orchestrator.Campaign") as MockCampaign,
        patch("sidestage.orchestrator.get_in_memory_exporter", return_value=mock_memory_exporter),
        patch("sidestage.orchestrator.get_sqlite_exporter", return_value=mock_sqlite_exporter),
        patch("sidestage.orchestrator.get_tracing_enabled", return_value=True),
    ):
        mock_campaign = MagicMock()
        mock_campaign.health = CampaignHealth()
        mock_campaign.campaign_dir = tmp_path
        mock_campaign.list_entities = AsyncMock(return_value=[])
        mock_campaign.list_scenes = AsyncMock(return_value=[])
        MockCampaign.return_value = mock_campaign

        orch = SidestageOrchestrator("test_campaign", base_dir=tmp_path)
        yield orch


@pytest.fixture
def client(mock_orchestrator: SidestageOrchestrator) -> TestClient:
    """FastAPI TestClient wrapping mock_orchestrator.fastapi_app."""
    return TestClient(mock_orchestrator.fastapi_app)


# --- GET /v1/traces ---


def test_get_traces_returns_list(client, mock_sqlite_exporter):
    """GET /v1/traces returns a JSON list of trace summaries."""
    mock_sqlite_exporter.query_traces.return_value = [
        {
            "trace_id": "abc123",
            "scene_id": "scene_01",
            "event_id": "msg_1",
            "event_type": "ChatMessage",
            "start_time_ms": 1707307200000.0,
            "end_time_ms": 1707307201234.0,
            "root_span_name": "scene.process_event",
            "span_count": 5,
            "created_at": "2025-02-07T12:00:00",
        }
    ]
    resp = client.get("/v1/traces")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["trace_id"] == "abc123"


def test_get_traces_filter_by_scene_id(client, mock_sqlite_exporter):
    """GET /v1/traces?scene_id=X passes the filter to the SQLite exporter."""
    mock_sqlite_exporter.query_traces.return_value = []
    resp = client.get("/v1/traces?scene_id=scene_01")
    assert resp.status_code == 200
    mock_sqlite_exporter.query_traces.assert_called_once_with(
        scene_id="scene_01", event_id=None, limit=50, offset=0,
    )


def test_get_traces_filter_by_event_id(client, mock_sqlite_exporter):
    """GET /v1/traces?event_id=X passes the filter."""
    mock_sqlite_exporter.query_traces.return_value = []
    resp = client.get("/v1/traces?event_id=msg_x")
    assert resp.status_code == 200
    mock_sqlite_exporter.query_traces.assert_called_once_with(
        scene_id=None, event_id="msg_x", limit=50, offset=0,
    )


def test_get_traces_respects_limit_and_offset(client, mock_sqlite_exporter):
    """GET /v1/traces?limit=5&offset=10 passes pagination params."""
    mock_sqlite_exporter.query_traces.return_value = []
    resp = client.get("/v1/traces?limit=5&offset=10")
    assert resp.status_code == 200
    mock_sqlite_exporter.query_traces.assert_called_once_with(
        scene_id=None, event_id=None, limit=5, offset=10,
    )


def test_get_traces_returns_empty_when_no_exporter(client):
    """GET /v1/traces returns [] when SQLite exporter is not available."""
    with patch("sidestage.orchestrator.get_sqlite_exporter", return_value=None):
        resp = client.get("/v1/traces")
    assert resp.status_code == 200
    assert resp.json() == []


# --- GET /v1/traces/{trace_id} ---


def test_get_trace_detail_from_memory(client, mock_memory_exporter):
    """GET /v1/traces/{trace_id} returns full trace from in-memory exporter."""
    mock_memory_exporter.get_trace.return_value = [
        {
            "trace_id": "abc123",
            "span_id": "span_1",
            "parent_span_id": None,
            "name": "scene.process_event",
            "kind": "INTERNAL",
            "start_time_ms": 1000.0,
            "end_time_ms": 2000.0,
            "duration_ms": 1000.0,
            "status": {"code": "OK", "description": None},
            "attributes": {},
            "events": [],
            "scene_id": None,
            "event_id": None,
        }
    ]

    resp = client.get("/v1/traces/abc123")
    assert resp.status_code == 200
    data = resp.json()
    assert data["trace_id"] == "abc123"
    assert len(data["spans"]) == 1


def test_get_trace_detail_falls_back_to_sqlite(
    client, mock_memory_exporter, mock_sqlite_exporter,
):
    """GET /v1/traces/{trace_id} falls back to SQLite when not in memory."""
    mock_memory_exporter.get_trace.return_value = None
    mock_sqlite_exporter.query_spans.return_value = [
        {
            "trace_id": "old_trace",
            "span_id": "span_2",
            "parent_span_id": None,
            "name": "root",
            "kind": "INTERNAL",
            "start_time_ms": 500.0,
            "end_time_ms": 600.0,
            "duration_ms": 100.0,
            "status_code": "OK",
            "attributes": {},
            "events": [],
            "scene_id": None,
            "event_id": None,
        }
    ]

    resp = client.get("/v1/traces/old_trace")
    assert resp.status_code == 200
    data = resp.json()
    assert data["trace_id"] == "old_trace"


def test_get_trace_detail_not_found(client, mock_memory_exporter, mock_sqlite_exporter):
    """GET /v1/traces/{trace_id} returns 404 when trace doesn't exist."""
    mock_memory_exporter.get_trace.return_value = None
    mock_sqlite_exporter.query_spans.return_value = []

    resp = client.get("/v1/traces/nonexistent")
    assert resp.status_code == 404


# --- POST /v1/tracing/toggle ---


def test_toggle_tracing_enable(client):
    """POST /v1/tracing/toggle with enabled=true calls toggle_tracing."""
    with patch("sidestage.orchestrator.toggle_tracing", return_value=True) as mock_toggle:
        resp = client.post("/v1/tracing/toggle", json={"enabled": True})
    assert resp.status_code == 200
    assert resp.json()["tracing_enabled"] is True
    mock_toggle.assert_called_once_with(True)


def test_toggle_tracing_disable(client):
    """POST /v1/tracing/toggle with enabled=false calls toggle_tracing."""
    with patch("sidestage.orchestrator.toggle_tracing", return_value=False) as mock_toggle:
        resp = client.post("/v1/tracing/toggle", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["tracing_enabled"] is False
    mock_toggle.assert_called_once_with(False)


# --- GET /v1/tracing/status ---


def test_get_tracing_status(client, mock_memory_exporter):
    """GET /v1/tracing/status returns enabled, config, and trace_count."""
    mock_memory_exporter.get_traces.return_value = [{"trace_id": "t1"}, {"trace_id": "t2"}]

    with patch("sidestage.orchestrator.get_tracing_enabled", return_value=True):
        resp = client.get("/v1/tracing/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert "config" in data
    assert data["trace_count"] == 2


def test_get_tracing_status_when_disabled(client, mock_memory_exporter):
    """GET /v1/tracing/status works when tracing is disabled."""
    mock_memory_exporter.get_traces.return_value = []

    with patch("sidestage.orchestrator.get_tracing_enabled", return_value=False):
        resp = client.get("/v1/tracing/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    assert data["trace_count"] == 0


def test_get_tracing_status_no_exporter(client):
    """GET /v1/tracing/status returns trace_count=0 when no exporter."""
    with (
        patch("sidestage.orchestrator.get_tracing_enabled", return_value=False),
        patch("sidestage.orchestrator.get_in_memory_exporter", return_value=None),
    ):
        resp = client.get("/v1/tracing/status")

    assert resp.status_code == 200
    assert resp.json()["trace_count"] == 0
