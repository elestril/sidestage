"""Runtime event wrapper and async event queue.

The Event class carries an EventModel plus runtime context (tracing, scene
reference) that should NOT be persisted. The EventQueue processes Event
objects sequentially through a handler callback.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

from opentelemetry import trace

from sidestage.models import EventModel

if TYPE_CHECKING:
    from opentelemetry.trace import SpanContext

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Runtime event wrapper carrying model data, tracing context, and scene reference."""

    model: EventModel
    span_context: SpanContext | None = None
    scene: object | None = field(default=None, repr=False)

    @property
    def character(self):
        """Look up the originating Character via the scene's character registry."""
        if self.scene and self.model.character_id:
            characters = getattr(self.scene, "characters", {})
            return characters.get(self.model.character_id)
        return None

    @classmethod
    def from_model(cls, model: EventModel) -> Event:
        """Create an Event from an EventModel, capturing the current span context."""
        span = trace.get_current_span()
        ctx = span.get_span_context() if span else None
        if ctx and not ctx.is_valid:
            ctx = None
        return cls(model=model, span_context=ctx)


EventHandler = Callable[[Event], Awaitable[None]]


class EventQueue:
    """Async event queue for sequential event processing.

    Events (Event wrappers, not raw EventModel) are processed one at a time
    by a single handler callback.
    """

    def __init__(self):
        self.queue: asyncio.Queue[Event] = asyncio.Queue()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self, handler: EventHandler) -> None:
        """Start the background worker with the given handler."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._worker(handler))
        logger.info("EventQueue started.")

    async def stop(self) -> None:
        """Stop the background worker."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("EventQueue stopped.")

    async def put(self, event: Event) -> None:
        """Add an event to the queue."""
        await self.queue.put(event)

    async def _worker(self, handler: EventHandler) -> None:
        """Background loop: pull events and pass to handler."""
        while self._running:
            try:
                event = await self.queue.get()
                await handler(event)
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("EventQueue worker error")
