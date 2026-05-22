from __future__ import annotations

import asyncio
import contextlib
import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, NewType

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

    Collection-typed Model fields registered in `_entity_lists` are wrapped
    in an `EntityList` at construction; every mutator on that collection
    emits `EntityChanged` carrying a `ListDelta` (per
    `entity-list-attribute`).

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

    # entity-list-attribute: subclasses register collection fields that
    # should auto-emit on mutation. Each entry is `attr_name → EntityList
    # subclass` (or the base EntityList for fields with no per-item hook).
    _entity_lists: ClassVar[dict[str, type[EntityList]]] = {}

    # backend-action-class-level: set of `@action`-decorated method names
    # on this class. Built by `__init_subclass__` (which walks each
    # subclass's __dict__ for the `__sidestage_action__` marker). The
    # WS `entity_action` dispatcher validates against this set.
    _actions: ClassVar[set[str]] = set()

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        # Inherit from the nearest base, then add any locally-declared.
        inherited: set[str] = set()
        for base in cls.__mro__[1:]:
            if isinstance(base, type) and issubclass(base, Entity):
                inherited |= getattr(base, "_actions", set())
        local = {
            name
            for name, member in cls.__dict__.items()
            if getattr(member, "__sidestage_action__", False)
        }
        cls._actions = inherited | local

    def __init__(self, model: Entity.Model, campaign: Campaign) -> None:
        """Construct an Entity wrapping `model`, bound to `campaign`.

        Bootstrap: `_model` is set via low-level `object.__setattr__` because
        our own `__setattr__` consults `self._model.model_fields` — that has
        to be in place before any other assignment can flow through. From
        there on, normal `self.x = y` works correctly.

        Any collection field declared in `_entity_lists` is replaced in
        place by an `EntityList` whose mutators auto-emit
        `EntityChanged(deltas=ListDelta(...))`.
        """
        object.__setattr__(self, "_model", model)
        self._campaign = campaign
        self._listeners: list[Listener] = []
        self._pending_tasks: set[asyncio.Task] = set()
        # Wrap registered list fields. `setattr` on the model bypasses our
        # __setattr__ — Pydantic accepts the EntityList because it's a
        # `list` subclass.
        for attr, list_cls in type(self)._entity_lists.items():
            initial = getattr(self._model, attr)
            wrapped = list_cls(self, attr)
            list.extend(wrapped, initial)  # bypass emit on load
            object.__setattr__(self._model, attr, wrapped)

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
        `EntityChanged` with a `ScalarDelta` (or `ListDelta` for a wholesale
        list reassignment). Non-Model attributes are set on `self` directly.

        .implements: entity-impl, events-dataflow-emit
        """
        # `model_fields` is a class-level attribute on the Model — accessing
        # it via the class avoids Pydantic's instance-access deprecation.
        if name in type(self._model).model_fields:
            from sidestage.events import EntityChanged, ListDelta, ScalarDelta

            # If this is a registered EntityList field and the caller is
            # reassigning the whole list, wrap the new value in a fresh
            # EntityList so the "always an EntityList" contract holds.
            list_cls = type(self)._entity_lists.get(name)
            old = getattr(self._model, name)
            if list_cls is not None and not isinstance(value, EntityList):  # noqa: F821
                wrapped = list_cls(self, name)
                list.extend(wrapped, value)
                value = wrapped
            setattr(self._model, name, value)
            if old != value:
                if list_cls is not None:
                    delta = ListDelta(start=0, len=len(old), items=list(value))
                else:
                    delta = ScalarDelta(value=value)
                self._emit(
                    EntityChanged(
                        entity=self,
                        attributes=[name],
                        deltas={name: delta},
                    )
                )
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
            self._spawn_task(self._invoke_listener(listener, event))

    async def _invoke_listener(self, listener: Listener, event: EntityChanged) -> None:
        """Per-listener task body: invoke `listener.notify`, awaiting if it
        returned a coroutine; log any exception."""
        try:
            result = listener.notify(event)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            logger.exception("listener %r raised in notify", listener)

    def _spawn_task(self, coro) -> asyncio.Task:
        """events-async-tasks-private: Track `coro` as a task on this
        entity. Private — `_emit` is the only production caller.

        .implements: events-async-tasks-spawn, events-async-tasks-private
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

    async def _idle(self, timeout: float = 5.0) -> None:
        """events-async-tasks-idle: Wait for all pending listener tasks to
        complete. Internal — production never calls this; tests use the
        public `Scene.idle()` wrapper. Lives on Entity so the same
        machinery can be exercised by Entity-level unit tests, but is
        deliberately not surfaced on the base API.

        .implements: events-async-tasks-idle
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


class EntityList[T](list[T]):
    """entity-list-attribute: list subclass whose mutators emit
    `EntityChanged(deltas={attr: ListDelta(...)})` on the owning Entity.

    A Model field declared as `list[T]` and registered in
    `Entity._entity_lists` is replaced in place at construction by an
    instance of this class (or a subclass that overrides `_on_add` for
    per-item processing).

    The base class is itself non-generic at runtime; subscript with a
    type parameter is for the type checker only.

    .implements: entity-list-attribute
    """

    def __init__(self, owner: Entity, attr: str) -> None:
        super().__init__()
        self._owner = owner
        self._attr = attr

    def _on_add(self, item: T) -> None:
        """Per-item hook before the item is stored. Base is a no-op.
        Subclasses override to assign per-item state (timestamps,
        per-message indices, etc.) at insertion time.
        """
        return None

    def _emit_delta(self, start: int, length: int, items: list[T]) -> None:
        from sidestage.events import EntityChanged, ListDelta

        delta = ListDelta(start=start, len=length, items=items)
        self._owner._emit(
            EntityChanged(
                entity=self._owner,
                attributes=[self._attr],
                deltas={self._attr: delta},
            )
        )

    # ---- mutators ----------------------------------------------------

    def append(self, item: T) -> None:
        self._on_add(item)
        list.append(self, item)
        self._emit_delta(-1, 0, [item])

    def extend(self, items: Iterable[T]) -> None:
        items = list(items)
        for x in items:
            self._on_add(x)
        list.extend(self, items)
        self._emit_delta(-1, 0, items)

    def insert(self, i: int, item: T) -> None:
        pos = i if i >= 0 else max(0, len(self) + i)
        self._on_add(item)
        list.insert(self, i, item)
        self._emit_delta(pos, 0, [item])

    def pop(self, i: int = -1) -> T:
        pos = i if i >= 0 else len(self) + i
        x = list.pop(self, i)
        self._emit_delta(pos, 1, [])
        return x

    def remove(self, item: T) -> None:
        idx = list.index(self, item)
        list.remove(self, item)
        self._emit_delta(idx, 1, [])

    def clear(self) -> None:
        n = len(self)
        list.clear(self)
        self._emit_delta(0, n, [])

    def __setitem__(self, i, item) -> None:  # type: ignore[override]
        if isinstance(i, slice):
            raise NotImplementedError("slice assignment not supported on EntityList")
        pos = i if i >= 0 else len(self) + i
        self._on_add(item)
        list.__setitem__(self, i, item)
        self._emit_delta(pos, 1, [item])

    def __delitem__(self, i) -> None:
        if isinstance(i, slice):
            raise NotImplementedError("slice deletion not supported on EntityList")
        pos = i if i >= 0 else len(self) + i
        list.__delitem__(self, i)
        self._emit_delta(pos, 1, [])

    def __iadd__(self, other) -> EntityList[T]:  # type: ignore[override]
        self.extend(other)
        return self


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
