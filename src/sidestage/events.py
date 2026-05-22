"""events: EntityChanged pub/sub + delta payloads.

Per `specs/events.md`. Entities emit `EntityChanged` events; Listeners
subscribe to receive them. The event carries the live Entity reference,
the list of changed attribute names, and per-attribute delta payloads
(`ListDelta` for collections, `ScalarDelta` for everything else) so
projections can apply changes without re-reading the entity.

Wire serialization happens at the WS boundary, not in these classes.
"""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from sidestage.entity import Entity


@dataclass
class ListDelta:
    """events-list-delta: Splice-style diff for an `EntityList` attribute.

    `splice(start, len, ...items)` semantics. `start == -1` is the
    sentinel for "at the end" (Python convention); JS receivers translate
    to `push(...items)`.

    .implements: events-attribute-deltas
    """

    start: int
    len: int
    items: list[Any] = field(default_factory=list)


@dataclass
class ScalarDelta:
    """events-scalar-delta: New value for a scalar Model field.

    .implements: events-attribute-deltas
    """

    value: Any


AttributeDelta = ListDelta | ScalarDelta


@dataclass
class EntityChanged:
    """events-event-changed: announces that one or more attributes of
    `entity` have mutated.

    - events-event-changed-entity: `entity` is the live reference (NOT an
      id). Listeners read fresh state via `event.entity.<attr>`.
    - events-event-changed-attributes: `attributes` lists the attribute
      names that mutated.
    - events-event-changed-deltas: `deltas` carries per-attribute
      payloads — `ListDelta` for collection attributes, `ScalarDelta`
      for scalars. Projections apply deltas directly.

    Plain `@dataclass`, NOT a Pydantic model. Wire serialization happens
    at the WS boundary.
    """

    entity: Entity
    attributes: list[str] = field(default_factory=list)
    deltas: dict[str, AttributeDelta] = field(default_factory=dict)


class Listener(Protocol):
    """events-protocol: anything implementing `notify(event)`.

    - events-protocol-sync-or-async: `notify` may be sync or async. The
      bus wraps each listener invocation in a task and awaits the result
      if it is a coroutine.
    """

    def notify(self, event: EntityChanged) -> None | Awaitable[None]: ...
