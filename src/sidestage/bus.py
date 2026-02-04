import asyncio
import logging
from typing import Callable, Awaitable, List, Dict, Type, Any, Optional, Coroutine
from sidestage.schemas import Event

logger = logging.getLogger(__name__)

# Type for a listener callback: async function that takes an Event
EventListener = Callable[[Event], Coroutine[Any, Any, None]]
# Type for the insert hook: async function that takes an Event and returns a (possibly modified) Event or None to drop it
InsertHook = Callable[[Event], Awaitable[Optional[Event]]]

class SceneMessageBus:
    """
    An asynchronous message bus for a single Scene.
    Supports multiple listeners and a single insert hook for pre-processing.
    """
    def __init__(self):
        self.listeners: List[EventListener] = []
        self.insert_hook: Optional[InsertHook] = None
        self.queue: asyncio.Queue[Event] = asyncio.Queue()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Starts the background worker to process the queue."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._worker())
        logger.info("SceneMessageBus started.")

    async def stop(self):
        """Stops the background worker."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SceneMessageBus stopped.")

    def subscribe(self, listener: EventListener):
        """Adds a listener to the bus."""
        if listener not in self.listeners:
            self.listeners.append(listener)

    def unsubscribe(self, listener: EventListener):
        """Removes a listener from the bus."""
        if listener in self.listeners:
            self.listeners.remove(listener)

    def set_insert_hook(self, hook: InsertHook):
        """Sets the insert hook for the bus."""
        self.insert_hook = hook

    async def publish(self, event: Event):
        """
        Publishes an event to the bus. 
        It first passes through the insert hook if one is set.
        """
        processed_event: Optional[Event] = event
        if self.insert_hook:
            try:
                processed_event = await self.insert_hook(event)
            except Exception as e:
                logger.error(f"Error in SceneMessageBus insert hook: {e}")
                # We continue with the original event if the hook fails, 
                # or should we drop it? Plan doesn't specify. 
                # Let's keep the original for now but log error.
        
        if processed_event:
            await self.queue.put(processed_event)

    async def _worker(self):
        """Background worker that pulls events from the queue and dispatches to listeners."""
        while self._running:
            try:
                event = await self.queue.get()
                
                # Dispatch to all listeners in parallel
                tasks = [asyncio.create_task(listener(event)) for listener in self.listeners]
                if tasks:
                    await asyncio.wait(tasks)
                
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in SceneMessageBus worker loop: {e}")
                await asyncio.sleep(1) # Prevent tight loop on error
