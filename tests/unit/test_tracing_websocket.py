"""Tests for WebSocket trace message broadcasting.

The broadcast callback uses asyncio.get_running_loop() internally,
so these tests only run under the asyncio backend.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sidestage.tracing.broadcast import make_trace_broadcast_callback

@pytest.fixture(params=["asyncio"])
def anyio_backend(request):
    return request.param


@pytest.fixture
def mock_sync_manager():
    """Create a mock SyncManager with async broadcast."""
    mgr = MagicMock()
    mgr.broadcast = AsyncMock()
    return mgr


@pytest.fixture
def broadcast_callback(mock_sync_manager):
    """Create a broadcast callback wired to mock_sync_manager."""
    return make_trace_broadcast_callback(mock_sync_manager)


def _make_span_data(
    trace_id="abc123",
    span_id="span_1",
    parent_span_id=None,
    name="scene.process_event",
    scene_id="scene_01",
    event_id="msg_1",
    start_time_ms=1000.0,
    end_time_ms=2000.0,
):
    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "name": name,
        "kind": "INTERNAL",
        "start_time_ms": start_time_ms,
        "end_time_ms": end_time_ms,
        "duration_ms": end_time_ms - start_time_ms,
        "status": {"code": "OK", "description": None},
        "attributes": {
            "sidestage.scene.id": scene_id,
            "sidestage.event.type": "ChatMessage",
        },
        "events": [],
        "scene_id": scene_id,
        "event_id": event_id,
    }


@pytest.mark.anyio
async def test_span_completed_sent_on_any_span(broadcast_callback, mock_sync_manager):
    """When spans are exported, span_completed messages are broadcast."""
    span = _make_span_data(parent_span_id="parent_1")
    broadcast_callback([span])

    # Let scheduled tasks run
    await asyncio.sleep(0.05)

    calls = mock_sync_manager.broadcast.call_args_list
    types = [c.args[0]["type"] for c in calls]
    assert "span_completed" in types


@pytest.mark.anyio
async def test_trace_started_sent_on_root_span(broadcast_callback, mock_sync_manager):
    """When a root span is exported, a trace_started message is broadcast."""
    root_span = _make_span_data(parent_span_id=None)
    broadcast_callback([root_span])

    await asyncio.sleep(0.05)

    calls = mock_sync_manager.broadcast.call_args_list
    types = [c.args[0]["type"] for c in calls]
    assert "trace_started" in types


@pytest.mark.anyio
async def test_trace_completed_sent_on_root_span(broadcast_callback, mock_sync_manager):
    """When a root span finishes, a trace_completed message is broadcast."""
    root_span = _make_span_data(parent_span_id=None)
    broadcast_callback([root_span])

    await asyncio.sleep(0.05)

    calls = mock_sync_manager.broadcast.call_args_list
    types = [c.args[0]["type"] for c in calls]
    assert "trace_completed" in types


@pytest.mark.anyio
async def test_trace_started_payload_format(broadcast_callback, mock_sync_manager):
    """trace_started message has the correct payload shape."""
    root_span = _make_span_data(
        trace_id="t1", scene_id="s1", start_time_ms=5000.0,
    )
    broadcast_callback([root_span])

    await asyncio.sleep(0.05)

    started_calls = [
        c.args[0] for c in mock_sync_manager.broadcast.call_args_list
        if c.args[0]["type"] == "trace_started"
    ]
    assert len(started_calls) == 1
    msg = started_calls[0]
    assert msg["trace_id"] == "t1"
    assert msg["scene_id"] == "s1"
    assert msg["start_time_ms"] == 5000.0


@pytest.mark.anyio
async def test_trace_completed_payload_format(broadcast_callback, mock_sync_manager):
    """trace_completed message has the correct payload shape."""
    root_span = _make_span_data(
        trace_id="t2", scene_id="s2", start_time_ms=1000.0, end_time_ms=3000.0,
    )
    broadcast_callback([root_span])

    await asyncio.sleep(0.05)

    completed_calls = [
        c.args[0] for c in mock_sync_manager.broadcast.call_args_list
        if c.args[0]["type"] == "trace_completed"
    ]
    assert len(completed_calls) == 1
    msg = completed_calls[0]
    assert msg["trace_id"] == "t2"
    assert msg["scene_id"] == "s2"
    assert msg["duration_ms"] == 2000.0


@pytest.mark.anyio
async def test_child_span_no_trace_started(broadcast_callback, mock_sync_manager):
    """Child spans (non-root) do NOT trigger trace_started or trace_completed."""
    child_span = _make_span_data(parent_span_id="parent_1")
    broadcast_callback([child_span])

    await asyncio.sleep(0.05)

    calls = mock_sync_manager.broadcast.call_args_list
    types = [c.args[0]["type"] for c in calls]
    assert "trace_started" not in types
    assert "trace_completed" not in types
    assert "span_completed" in types


@pytest.mark.anyio
async def test_multiple_spans_in_batch(broadcast_callback, mock_sync_manager):
    """Multiple spans in one batch each produce span_completed messages."""
    spans = [
        _make_span_data(span_id="s1", parent_span_id="root"),
        _make_span_data(span_id="s2", parent_span_id="root"),
    ]
    broadcast_callback(spans)

    await asyncio.sleep(0.05)

    completed_calls = [
        c.args[0] for c in mock_sync_manager.broadcast.call_args_list
        if c.args[0]["type"] == "span_completed"
    ]
    assert len(completed_calls) == 2
