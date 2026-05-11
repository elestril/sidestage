"""actor: Edge-state holder for a Character.

Per `specs/actor.md`. Actor is a runtime singleton owned by `App` and
holds external-state — LLM connections, SSE subscriptions, future auth.
Character carries world-data; Actor carries the I/O.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sidestage.character import Character
    from sidestage.entity import Entity
    from sidestage.message import Message


class Actor(ABC):
    """actor-base: Abstract base for the controller of one or more
    Characters. Actors are runtime singletons owned by `App` (NOT Entity
    subclasses); each Character holds a reference to the shared Actor
    instance for its `owner`. Actor is NOT a Listener — the listener role
    for a Character belongs to `Character.notify`.
    """

    @abstractmethod
    def is_human(self) -> bool: ...

    @abstractmethod
    async def respond(
        self, message: "Message", character: "Character"
    ) -> Optional["Message"]: ...


class StubActor(Actor):
    """stub-actor: Deterministic test scaffold. No edge state. `respond`
    returns the character body verbatim — content comes from the character,
    not from the actor.
    """

    def is_human(self) -> bool:
        """stub-actor-is-human: Returns False."""
        return False

    async def respond(
        self, message: "Message", character: "Character"
    ) -> Optional["Message"]:
        """stub-actor-respond-returns: Returns
        `Message(sender=character, body=character.body)`.
        """
        from sidestage.message import Message as Msg

        return Msg(sender=character, body=character.body)


class UserActor(Actor):
    """user-actor: Per-user SSE subscription manager. Holds the
    `QueueListener`s spawned by SSE handlers on this user's behalf and
    manages their lifecycle. `respond` returns `None` (humans answer via
    REST POST, not via the listener path).

    Notify still flows direct entity → QueueListener (per
    `events-multi-window`); UserActor is bookkeeping for the QueueListener
    lifecycle, NOT a router.
    """

    def __init__(self) -> None:
        # Tracks (entity, listener) pairs subscribed on this user's behalf.
        # Exact shape is implementation detail; tests use a mock.
        self._subscriptions: list = []

    def is_human(self) -> bool:
        """user-actor-is-human: Returns True."""
        return True

    async def respond(
        self, message: "Message", character: "Character"
    ) -> Optional["Message"]:
        """user-actor-respond-noop: Returns `None` unconditionally — humans
        respond via REST.
        """
        return None

    def subscribe_to(
        self, entity: "Entity", queue: asyncio.Queue
    ) -> None:
        """user-actor-subscribe-to: Wrap `queue` in a `QueueListener`,
        register it on `entity` via `entity.subscribe(listener)`, and
        track the (entity, listener) pair for lifecycle management.

        Called by the SSE handler per `sse-dataflow-accept`.

        .implements: events-pattern-subscription-lifecycle
        """
        raise NotImplementedError

    def unsubscribe_from(
        self, entity: "Entity", queue: asyncio.Queue
    ) -> None:
        """user-actor-unsubscribe-from: Find the QueueListener tracking
        `queue` for `entity`, call `entity.unsubscribe(listener)`, and
        drop the tracked pair. No-op if not subscribed.

        Called by the SSE handler in `try/finally` per
        `sse-dataflow-disconnect`.

        .implements: events-pattern-subscription-lifecycle
        """
        raise NotImplementedError

    def cancel_all(self) -> None:
        """user-actor-cancel-all: Unsubscribe every tracked pair. Used on
        session end / future logout.

        .implements: events-pattern-subscription-lifecycle
        """
        raise NotImplementedError
