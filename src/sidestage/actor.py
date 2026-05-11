from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

from sidestage.entity import EntityId

if TYPE_CHECKING:
    from sidestage.character import Character
    from sidestage.message import Message


class SceneUpdatedEvent(BaseModel):
    scene_id: EntityId
    latest_message_index: int


class Actor(ABC):
    """actor-base: Abstract base for the controller of one or more Characters.
    Actors are runtime singletons owned by `App` (not Entity subclasses); each
    Character holds a reference to the shared Actor instance for its `owner`.

    .implements: actor
    """

    @abstractmethod
    def is_human(self) -> bool:
        pass

    @abstractmethod
    async def respond(
        self, message: "Message", character: "Character"
    ) -> Optional["Message"]:
        pass

    def notify(self, event: SceneUpdatedEvent) -> None:
        """actor-notify-default-noop: Default implementation does nothing.
        Subclasses that need to deliver scene updates (e.g. `UserActor`)
        override.

        .implemented-by: UserActor.notify
        """
        return None


class StubActor(Actor):
    """stub-actor: Deterministic scaffold actor for tests and low-cost
    end-to-end runs.

    .implements: actor
    """

    def is_human(self) -> bool:
        """stub-actor-is-human: Returns False."""
        return False

    async def respond(
        self, message: "Message", character: "Character"
    ) -> Optional["Message"]:
        """stub-actor-respond-returns: Returns
        `Message(sender=character, body="Hello World")`. No filtering, no
        conditional — the caller decides when to invoke.

        .implements: message-simplescene-respond
        """
        from sidestage.message import Message as Msg

        return Msg(sender=character, body="Hello World")


class UserActor(Actor):
    """user-actor: Marker actor for user-owned characters. Maintains a
    private list of SSE event queues — one per connected client. `notify`
    broadcasts a `SceneUpdatedEvent` to every queue. Does not generate
    responses; user input arrives via REST POST.

    .implements: actor
    """

    def __init__(self) -> None:
        self._queues: list[asyncio.Queue] = []

    def is_human(self) -> bool:
        """user-actor-is-human: Returns True."""
        return True

    async def respond(
        self, message: "Message", character: "Character"
    ) -> Optional["Message"]:
        """user-actor-respond-noop: Returns None unconditionally. Human
        responses arrive via REST.
        """
        return None

    def add_queue(self, queue: asyncio.Queue) -> None:
        """user-actor-add-queue: Registers `queue` for SSE delivery.

        .implements: sse-dataflow-event
        """
        self._queues.append(queue)

    def remove_queue(self, queue: asyncio.Queue) -> None:
        """user-actor-remove-queue: Deregisters `queue`. No-op if not
        registered.

        .implements: sse-dataflow-event
        """
        try:
            self._queues.remove(queue)
        except ValueError:
            pass

    def notify(self, event: SceneUpdatedEvent) -> None:
        """user-actor-notify-broadcast: Puts `event` onto every registered
        queue via `put_nowait`. The same instance is dispatched to all
        queues — no copying.

        .implements: sse-dataflow-event, message-simplescene-respond
        """
        for queue in self._queues:
            queue.put_nowait(event)
