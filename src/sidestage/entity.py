from __future__ import annotations

import asyncio
import contextlib
import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable
from enum import StrEnum
from typing import TYPE_CHECKING, NewType, Self

from pydantic import BaseModel

if TYPE_CHECKING:
    from sidestage.events import EntityChanged, Listener


logger = logging.getLogger("sidestage.entity")


EntityId = NewType("EntityId", str)
"""entity-id-newtype: All entity references use `EntityId` rather than bare
`str`, so the type checker distinguishes ids from arbitrary strings.

.implements: entity-id
"""


class EntityType(StrEnum):
    """entity-type: Discriminator enum for serialized Entity subclasses.

    Members:
    - entity-type-character: `CHARACTER` — selects `Character.Model` deserialization.
    - entity-type-scene: `SCENE` — selects `Scene.Model` (or subclass) deserialization.
    - entity-type-entity: `ENTITY` — generic Entity, no subclass.

    .implements: entity-impl
    """

    CHARACTER = "character"
    SCENE = "scene"
    ENTITY = "entity"


class UnresolvedEntityError(Exception):
    """unresolved-entity-error: Raised when accessing a non-id field on an
    unresolved ghost (per `entity-ghost-unresolved`).

    .implements: entity-impl
    """


_GHOST_SAFE = {"id", "_loaded"}


class Entity:
    """entity-class: The base object of Sidestage — every world thing (character,
    scene, location, item) is an Entity. All entities belong to a Campaign and
    are managed by an EntityFactory. Entities support lazy loading via the
    ghost pattern: an unresolved entity holds only its `id`; accessing any
    other field raises `UnresolvedEntityError` until the factory hydrates it.

    .implements: entity-impl
    """

    class Model(BaseModel):
        """entity-model: Inner Pydantic model defining the on-disk / on-wire
        schema for an Entity. Every concrete Entity subclass MUST implement
        its own `Model(Entity.Model)` adding subclass-specific fields. Without
        a `Model`, the entity cannot be loaded from disk or serialized to the
        wire.

        .implements: entity-impl
        """

        id: EntityId
        name: str
        type: EntityType
        body: str

    def __init__(self, id: EntityId, *, _loaded: bool = False) -> None:
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "_loaded", _loaded)
        if _loaded:
            object.__setattr__(self, "_listeners", [])
            object.__setattr__(self, "_pending_tasks", set())

    def __getattribute__(self, name: str):
        """Ghost-pattern attribute access guard.

        - entity-ghost-safe: `id` and `_loaded` are accessible on unresolved
          entities.
        - entity-ghost-unresolved: Accessing any other field raises
          `UnresolvedEntityError` if `_loaded` is False.

        .implements: entity-impl
        """
        if name in _GHOST_SAFE or name.startswith("__"):
            return object.__getattribute__(self, name)
        loaded = object.__getattribute__(self, "_loaded")
        if not loaded:
            raise UnresolvedEntityError(
                f"Entity '{object.__getattribute__(self, 'id')}' is not resolved"
            )
        return object.__getattribute__(self, name)

    def serialize(self) -> Entity.Model:
        """Serialize this entity to its `Model`.

        - entity-serialize-fields: Returns `self.Model` populated from this
          entity's public fields.
        - entity-serialize-ghost-rejects: Raises `UnresolvedEntityError` if
          called on an unresolved ghost (enforced indirectly via the ghost
          attribute guard when reading `name`/`type`/`body`).

        .implements: entity-impl
        """
        return self.Model(
            id=self.id,
            name=self.name,
            type=self.type,
            body=self.body,
        )

    @classmethod
    def deserialize(cls, model: Entity.Model) -> Self:
        """Construct a hydrated entity from its `Model`.

        - entity-deserialize-returns: Returns an instance of `cls` (not
          `Entity`) populated from `model`.
        - entity-deserialize-loaded: Sets `_loaded = True` on the returned
          instance.

        .implements: entity-impl
        """
        instance = cls.__new__(cls)
        object.__setattr__(instance, "id", model.id)
        object.__setattr__(instance, "_loaded", True)
        object.__setattr__(instance, "name", model.name)
        object.__setattr__(instance, "type", model.type)
        object.__setattr__(instance, "body", model.body)
        object.__setattr__(instance, "_listeners", [])
        object.__setattr__(instance, "_pending_tasks", set())
        return instance

    # ---------------- events: pub/sub (per specs/events.md) ---------------

    def subscribe(self, listener: Listener) -> None:
        """entity-subscribe: Register `listener` to receive future
        `EntityChanged` events emitted by this entity.

        .implements: events-pattern-subscription
        """
        self._listeners.append(listener)

    def unsubscribe(self, listener: Listener) -> None:
        """entity-unsubscribe: Remove `listener` from this entity's
        subscriber list. No-op if `listener` was not subscribed.

        .implements: events-pattern-subscription-lifecycle
        """
        with contextlib.suppress(ValueError):
            self._listeners.remove(listener)

    def _emit(self, event: EntityChanged) -> None:
        """entity-emit: Fan out `event` by wrapping each listener call in a
        tracked task on this entity (per `events-async-tasks`):
        `for l in self._listeners: self.spawn_task(self._invoke_listener(l, event))`.
        Called from inside state-mutating methods on subclasses (e.g. `Scene.append`).

        Per-listener task wrapping gives isolation (one bad listener can't
        abort the fanout) and lets listeners be sync or async transparently.

        .implements: events-dataflow-fan-out, events-errors-listener-isolation
        """
        # Snapshot — a listener may unsubscribe during emit.
        for listener in list(self._listeners):
            self.spawn_task(self._invoke_listener(listener, event))

    async def _invoke_listener(self, listener: Listener, event: EntityChanged) -> None:
        """Per-listener task body: invoke `listener.notify`, awaiting if it
        returned a coroutine; log any exception so one bad listener cannot
        abort fanout.

        .implements: events-errors-listener-isolation
        """
        try:
            result = listener.notify(event)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            logger.exception("listener %r raised in notify", listener)

    def spawn_task(self, coro) -> asyncio.Task:
        """entity-spawn-task: Track `coro` as a task on this entity.

        Adds the task to `_pending_tasks`; the done-callback removes it on
        completion AND logs `task.exception()` if non-None (per
        `events-errors-spawned-task`). Returns the Task.

        Used by `_emit` for per-listener wrapping; also callable by
        listeners that need to fan out additional async work.

        .implements: events-async-tasks-spawn
        """
        task = asyncio.create_task(coro)
        self._pending_tasks.add(task)
        task.add_done_callback(self._on_task_done)
        return task

    def _on_task_done(self, task: asyncio.Task) -> None:
        """Done-callback for `spawn_task`: discard from `_pending_tasks` and
        log any non-cancellation exception.

        .implements: events-errors-spawned-task
        """
        self._pending_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("spawned task raised", exc_info=exc)

    async def idle(self, timeout: float = 5.0) -> None:
        """entity-idle: Wait for all pending listener tasks to complete.

        Loops until `_pending_tasks` is empty — each iteration awaits
        `gather(*pending, return_exceptions=True)`. Catches cascading
        reactions (a task that triggers another emission that spawns
        another task). Bounded by a small timeout to fail fast on wedges.
        Re-raises unexpected exceptions per
        `events-errors-test-visibility`.

        Test-only primitive; production never calls it.

        .implements: events-async-tasks-idle, testing-runner
        """
        deadline = asyncio.get_running_loop().time() + timeout
        while self._pending_tasks:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("idle: pending tasks did not settle")
            # Snapshot to allow new tasks to be added while waiting.
            snapshot = list(self._pending_tasks)
            # asyncio.wait (unlike gather+wait_for) does NOT cancel pending
            # tasks on timeout — we just loop again and let the deadline check
            # raise.
            await asyncio.wait(snapshot, timeout=remaining)
            # Yield once so done-callbacks scheduled by completed tasks can
            # run and discard themselves from `_pending_tasks` before we
            # re-check the loop condition.
            await asyncio.sleep(0)

    def notify(self, event: EntityChanged) -> None:
        """entity-notify-default-noop: Default Entity listener — does
        nothing. Subclasses (e.g. `Character`) override to react to events
        from entities they've subscribed to. The emitting entity is
        available at `event.entity`.

        .implements: events-protocol
        """
        return None


class EntityFactory(ABC):
    """entity-factory: Abstract registry of every Entity in a Campaign,
    indexed by `EntityId`. Concrete factories back the registry with whatever
    storage suits the deployment (in-memory dict at load time, etc.).

    .implements: entity-factory-impl
    """

    @abstractmethod
    def get(self, id: str) -> Entity | None:
        """Look up an entity by id.

        - entity-factory-get: Returns the entity for the given id, or None if
          unknown.

        .implements: entity-factory-impl
        """
        pass

    @abstractmethod
    def add(self, entity: Entity) -> None:
        """Register a hydrated entity in the factory.

        - entity-factory-add: Registers a hydrated entity; if a ghost with the
          same id exists, hydrates it in place.

        .implements: entity-factory-impl
        """
        pass

    @abstractmethod
    def ghost(self, id: str, type: EntityType) -> Entity:
        """Return (and register, if needed) an unresolved ghost for `id`.

        - entity-factory-ghost: Returns an unresolved ghost entity; creates
          and registers one if not yet known.

        .implements: entity-factory-impl
        """
        pass

    @abstractmethod
    def entities(self) -> Iterable[Entity]:
        """Iterate every registered entity (loaded + ghost).

        - entity-factory-entities: Iteration order is implementation-defined;
          `DictEntityFactory` yields in insertion order.

        .implements: entity-factory-impl
        """
        pass


class DictEntityFactory(EntityFactory):
    """dict-entity-factory: In-memory `EntityFactory` backed by
    `dict[str, Entity]`. Used at load time and as the default factory for
    a running Campaign.

    .implements: entity-factory-impl
    """

    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}

    def get(self, id: str) -> Entity | None:
        """Look up an entity by id in the backing dict.

        - dict-factory-get: Returns entity from the dict, or None if not
          found.

        .implements: entity-factory-get
        """
        return self._entities.get(id)

    def add(self, entity: Entity) -> None:
        """Register `entity`, hydrating an existing ghost in place if present.

        - dict-factory-add: Stores entity in the dict, sets `_loaded = True`;
          hydrates existing ghost if present (copies `name`, `type`, `body`,
          and any subclass-specific extra attributes onto the ghost so that
          forward references already handed out remain valid).

        .implements: entity-factory-add
        """
        existing = self._entities.get(entity.id)
        if existing is not None and not object.__getattribute__(existing, "_loaded"):
            object.__setattr__(existing, "_loaded", True)
            for attr in ("name", "type", "body"):
                object.__setattr__(
                    existing, attr, object.__getattribute__(entity, attr)
                )
            for attr in self._extra_attrs(entity):
                object.__setattr__(
                    existing, attr, object.__getattribute__(entity, attr)
                )
        else:
            object.__setattr__(entity, "_loaded", True)
            self._entities[entity.id] = entity

    def ghost(self, id: str, type: EntityType) -> Entity:
        """Return an unresolved ghost for `id`, creating one if not yet known.

        - dict-factory-ghost: Creates an unresolved Entity with
          `_loaded = False` and stores it; subsequent calls with the same id
          return the same instance so all forward references share identity.

        .implements: entity-factory-ghost
        """
        if id in self._entities:
            return self._entities[id]
        ghost = Entity.__new__(Entity)
        object.__setattr__(ghost, "id", EntityId(id))
        object.__setattr__(ghost, "_loaded", False)
        self._entities[id] = ghost
        return ghost

    def entities(self) -> Iterable[Entity]:
        """Yield every registered entity in insertion order.

        - dict-factory-entities: Returns `self._entities.values()`.

        .implements: entity-factory-entities
        """
        return self._entities.values()

    def _extra_attrs(self, entity: Entity) -> list[str]:
        return []
