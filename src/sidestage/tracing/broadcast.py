"""WebSocket broadcast callback for trace events."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sidestage.sync import SyncManager

logger = logging.getLogger(__name__)


def make_trace_broadcast_callback(sync_manager: SyncManager):
    """Create a callback for InMemoryTraceExporter that broadcasts trace events.

    The callback is called synchronously from the span export pipeline.
    It schedules the async broadcast onto the running event loop.

    Args:
        sync_manager: SyncManager instance for WebSocket broadcasting.

    Returns:
        A callback function suitable for InMemoryTraceExporter.on_export_callback.
    """

    def callback(span_data_list: list[dict]) -> None:
        messages: list[dict] = []

        for sd in span_data_list:
            is_root = sd.get("parent_span_id") is None

            # Every span triggers a span_completed message
            messages.append({
                "type": "span_completed",
                **sd,
            })

            if is_root:
                # Root spans trigger trace_started and trace_completed
                messages.append({
                    "type": "trace_started",
                    "trace_id": sd["trace_id"],
                    "scene_id": sd.get("scene_id"),
                    "event_type": sd.get("attributes", {}).get("sidestage.event.type"),
                    "start_time_ms": sd["start_time_ms"],
                })
                messages.append({
                    "type": "trace_completed",
                    "trace_id": sd["trace_id"],
                    "scene_id": sd.get("scene_id"),
                    "duration_ms": sd["duration_ms"],
                })

        if messages:
            try:
                loop = asyncio.get_running_loop()
                for msg in messages:
                    loop.create_task(sync_manager.broadcast(msg))
            except RuntimeError:
                logger.debug("No running event loop for trace broadcast")

    return callback
