from __future__ import annotations

import asyncio
import contextlib
import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, NewType

from pydantic import BaseModel

if TYPE_CHECKING:
    from sidestage.campaign import Campaign
    from sidestage.events import EntityChanged, Listener
    from sidestage.message import Message


logger = logging.getLogger("sidestage.entity")


EntityId = NewType("EntityId", str)
"""entity-id-newtype: branded id type so the type checker distinguishes
entity ids from arbitrary strings.

.implements: entity-id
"""


class EntityType(StrEnum):
    """entity-type: Discriminator enum for serialised Entity subclasses.

    .implements: entity-impl
    """

    CHARACTER = "character"
    SCENE = "scene"
    ENTITY = "entity"


class Entity:
    """entity-class: The base object of Sidestage.

    Wraps a Pydantic `Model` that holds every persistent field, plus
    runtime-only state (campaign reference, listener list, pending tasks).
    Attribute access is redirected to the Model via `__getattr__` /
    `__setattr__` — so `entity.name` reads `entity._model.name`, and
    `entity.name = "..."` writes through to the Model **and auto-emits
    `EntityChanged(attributes=["name"])`** when the value changes. No
    field duplication; no missed emissions.

    .implements: entity-impl
    """

    class Model(BaseModel):
        """entity-model: Inner Pydantic model — the canonical on-disk /
        on-wire shape for an Entity. Subclasses MUST implement their own
        `Model(Entity.Model)` adding subclass-specific fields.

        .implements: entity-impl
        """

        id: EntityId
        name: str
        type: EntityType
        body: str

    def __init__(self, model: Entity.Model, campaign: Campaign) -> None:
        """Construct an Entity wrapping `model`, bound to `campaign`.

        Bootstrap: `_model` is set via low-level `object.__setattr__` because
        our own `__setattr__` consults `self._model.model_fields` — that has
        to be in place before any other assignment can flow through. From
        there on, normal `self.x = y` works correctly.
        """
        object.__setattr__(self, "_model", model)
        self._campaign = campaign
        self._listeners: list[Listener] = []
        self._pending_tasks: set[asyncio.Task] = set()

    # ---------------- public Model accessor ---------------------------

    @property
    def model(self) -> Entity.Model:
        """The Model carrying this entity's serialised state."""
        return self._model

    # ---------------- attribute redirection ---------------------------

    def __getattr__(self, name: str):
        """Only called when normal lookup misses — forward to the model.

        .implements: entity-impl
        """
        return getattr(self._model, name)

    def __setattr__(self, name: str, value) -> None:
        """Public Model field writes go through `_model` and auto-emit
        `EntityChanged` when the value changes. Non-Model attributes are
        set on `self` directly.

        .implements: entity-impl, events-dataflow-emit
        """
        # `model_fields` is a class-level attribute on the Model — accessing
        # it via the class avoids Pydantic's instance-access deprecation.
        if name in type(self._model).model_fields:
            old = getattr(self._model, name)
            setattr(self._model, name, value)
            if old != value:
                from sidestage.events import EntityChanged

                self._emit(EntityChanged(entity=self, attributes=[name]))
            return
        object.__setattr__(self, name, value)

    # ---------------- identity (per entity-hashable-by-id) ------------

    def __hash__(self) -> int:
        """entity-hashable-by-id: hash by EntityId."""
        return hash(self._model.id)

    def __eq__(self, other: object) -> bool:
        """entity-hashable-by-id: compare by EntityId."""
        return isinstance(other, Entity) and self._model.id == other._model.id

    # ---------------- prompt-context contribution --------------------

    def annotate_context(self, ctx: MessageContext) -> None:
        """entity-annotate-context: contribute this entity's prompt text to
        the message context. Default writes `self.body` keyed by `self`.
        Subclasses override to recurse into related entities.

        .implements: entity-annotate-context
        """
        ctx.annotations[self] = self.body

    # ---------------- events: pub/sub (per specs/events.md) ----------

    def subscribe(self, listener: Listener) -> None:
        """entity-subscribe: Register `listener` for `EntityChanged` events
        emitted by this entity.

        .implements: events-pattern-subscription
        """
        self._listeners.append(listener)

    def unsubscribe(self, listener: Listener) -> None:
        """entity-unsubscribe: Remove `listener`. No-op if not subscribed.

        .implements: events-pattern-subscription-lifecycle
        """
        with contextlib.suppress(ValueError):
            self._listeners.remove(listener)

    def _emit(self, event: EntityChanged) -> None:
        """entity-emit: Fan out `event` by wrapping each listener call in a
        tracked task on this entity.

        .implements: events-dataflow-fan-out, events-errors-listener-isolation
        """
        for listener in list(self._listeners):
            self.spawn_task(self._invoke_listener(listener, event))

    async def _invoke_listener(self, listener: Listener, event: EntityChanged) -> None:
        """Per-listener task body: invoke `listener.notify`, awaiting if it
        returned a coroutine; log any exception."""
        try:
            result = listener.notify(event)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            logger.exception("listener %r raised in notify", listener)

    def spawn_task(self, coro) -> asyncio.Task:
        """entity-spawn-task: Track `coro` as a task on this entity.

        .implements: events-async-tasks-spawn
        """
        task = asyncio.create_task(coro)
        self._pending_tasks.add(task)
        task.add_done_callback(self._on_task_done)
        return task

    def _on_task_done(self, task: asyncio.Task) -> None:
        self._pending_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("spawned task raised", exc_info=exc)

    async def idle(self, timeout: float = 5.0) -> None:
        """entity-idle: Wait for all pending listener tasks to complete.
        Test-only primitive.

        .implements: events-async-tasks-idle, testing-runner
        """
        deadline = asyncio.get_running_loop().time() + timeout
        while self._pending_tasks:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("idle: pending tasks did not settle")
            snapshot = list(self._pending_tasks)
            await asyncio.wait(snapshot, timeout=remaining)
            await asyncio.sleep(0)

    def notify(self, event: EntityChanged) -> None:
        """entity-notify-default-noop: Default Entity listener — does nothing.
        Subclasses override to react.

        .implements: events-protocol
        """
        return None


@dataclass
class MessageContext:
    """entity-message-context: per-call accumulator carried through
    `Entity.annotate_context` recursion.

    .implements: entity-message-context
    """

    message: Message
    scene: Entity
    annotations: dict[Entity, str] = field(default_factory=dict)


class EntityFactory(ABC):
    """entity-factory: Abstract storage layer for a Campaign's entities.

    Concrete factories back the registry with whatever storage suits the
    deployment — today `DictEntityFactory` (in-memory dict). Future
    persistent-storage backends are the seam this ABC exists for.

    `Campaign` is the public surface; this factory is an internal
    implementation detail (`Campaign._store`).

    .implements: entity-factory-impl
    """

    @abstractmethod
    def get(self, id: str) -> Entity | None: ...

    @abstractmethod
    def add(self, entity: Entity) -> None: ...

    @abstractmethod
    def delete(self, id: str) -> None: ...

    @abstractmethod
    def entities(self) -> Iterable[Entity]: ...


class DictEntityFactory(EntityFactory):
    """dict-entity-factory: In-memory `EntityFactory` backed by a `dict`.

    .implements: entity-factory-impl
    """

    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}

    def get(self, id: str) -> Entity | None:
        return self._entities.get(id)

    def add(self, entity: Entity) -> None:
        self._entities[entity.id] = entity

    def delete(self, id: str) -> None:
        self._entities.pop(id, None)

    def entities(self) -> Iterable[Entity]:
        return self._entities.values()
