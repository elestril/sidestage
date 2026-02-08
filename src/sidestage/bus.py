import asyncio
import logging
from typing import Callable, Awaitable, Optional
from sidestage.schemas import Event

logger = logging.getLogger(__name__)

# Type for the event handler callback
EventHandler = Callable[[Event], Awaitable[None]]

class EventQueue:
    """
    A simple async event queue for a Scene.

    Events are processed sequentially by a single handler callback.
    No subscriptions, no hooks — the handler does all the work.
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
