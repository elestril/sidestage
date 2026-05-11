"""events: EntityChanged pub/sub.

Per `specs/events.md`. Entities emit `EntityChanged` events; Listeners
subscribe to receive them. The event carries the Entity reference and the
list of changed attribute names — listeners read fresh state via
`event.entity.<attr>`. Wire serialization happens at the SSE boundary,
not in the event class.

System state (server lifecycle, dep health, SSE handshake) is plumbing —
logged, not events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Awaitable, Protocol

if TYPE_CHECKING:
    from sidestage.entity import Entity


@dataclass
class EntityChanged:
    """events-event-changed: announces that one or more attributes of
    `entity` have mutated.

    - events-event-changed-entity: `entity` is the live reference (NOT an
      id). Listeners read fresh state via `event.entity.<attr>`.
    - events-event-changed-attributes: `attributes` is the list of
      attribute names that mutated. Today's only emit point fires
      `attributes=["messages"]` from `Scene.append`.

    Plain `@dataclass`, NOT a Pydantic model. Wire serialization for SSE
    happens at the boundary in the SSE handler.
    """

    entity: "Entity"
    attributes: list[str] = field(default_factory=list)


class Listener(Protocol):
    """events-protocol: anything implementing `notify(event)`.

    - events-protocol-sync-or-async: `notify` may be sync or async. The
      bus wraps each listener invocation in a task (per
      `events-async-tasks`) and awaits the result if it is a coroutine.
    - events-protocol-event-self-contained: The event carries everything
      the listener needs — `event.entity` for fresh state,
      `event.attributes` for the changed-attribute list.
    """

    def notify(self, event: EntityChanged) -> None | Awaitable[None]: ...
