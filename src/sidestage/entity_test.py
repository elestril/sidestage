from __future__ import annotations

import asyncio
import contextlib
import logging

import pytest

from sidestage.action import action
from sidestage.campaign import Campaign
from sidestage.entity import (
    DictEntityFactory,
    Entity,
    EntityId,
    EntityList,
    EntityType,
    MessageContext,
)
from sidestage.events import EntityChanged, ListDelta, ScalarDelta


def make_campaign() -> Campaign:
    return Campaign(name="test")


def make_entity(
    id: str = "e1",
    name: str = "Test",
    body: str = "body",
    campaign: Campaign | None = None,
) -> Entity:
    model = Entity.Model(id=EntityId(id), name=name, type=EntityType.ENTITY, body=body)
    return Entity(model, campaign if campaign is not None else make_campaign())


class _SyncListener:
    def __init__(self) -> None:
        self.received: list[EntityChanged] = []

    def notify(self, event: EntityChanged) -> None:
        self.received.append(event)


class _AsyncListener:
    def __init__(self) -> None:
        self.received: list[EntityChanged] = []

    async def notify(self, event: EntityChanged) -> None:
        # Yield control once so we exercise the async path.
        await asyncio.sleep(0)
        self.received.append(event)


class _RaisingListener:
    def __init__(self, message: str = "boom") -> None:
        self.message = message

    def notify(self, event: EntityChanged) -> None:
        raise RuntimeError(self.message)


# ----------------------------------------------------------------------
# id, model, factory
# ----------------------------------------------------------------------


class TestEntityId:
    def test_newtype_is_str(self) -> None:
        eid = EntityId("abc")
        assert isinstance(eid, str)
        assert eid == "abc"


class TestEntityConstruction:
    """Entity wraps a Model bound to a Campaign — `__init__` stores both."""

    def test_stores_model_and_campaign(self) -> None:
        campaign = make_campaign()
        model = Entity.Model(
            id=EntityId("e1"), name="N", type=EntityType.ENTITY, body="b"
        )
        entity = Entity(model, campaign)
        assert entity._model is model
        assert entity._campaign is campaign

    def test_reads_forward_to_model(self) -> None:
        model = Entity.Model(
            id=EntityId("abc"), name="Foo", type=EntityType.ENTITY, body="bar"
        )
        entity = Entity(model, make_campaign())
        assert entity.id == "abc"
        assert entity.name == "Foo"
        assert entity.body == "bar"
        assert entity.type == EntityType.ENTITY

    def test_writes_to_model_field_emit_entity_changed(self) -> None:
        entity = make_entity(id="e1", body="original")
        listener = _SyncListener()
        entity.subscribe(listener)

        async def run() -> None:
            entity.body = "new"
            await entity.idle()

        asyncio.run(run())

        assert len(listener.received) == 1
        event = listener.received[0]
        assert event.entity is entity
        assert event.attributes == ["body"]
        # The scalar delta carries the new value.
        delta = event.deltas["body"]
        assert isinstance(delta, ScalarDelta)
        assert delta.value == "new"
        # The model was updated.
        assert entity.body == "new"

    def test_writes_to_model_field_same_value_no_emit(self) -> None:
        entity = make_entity(id="e1", body="same")
        listener = _SyncListener()
        entity.subscribe(listener)

        async def run() -> None:
            entity.body = "same"
            await entity.idle()

        asyncio.run(run())

        assert listener.received == []

    def test_non_model_attribute_writes_go_to_dict(self) -> None:
        entity = make_entity()
        listener = _SyncListener()
        entity.subscribe(listener)

        entity._foo = 1  # type: ignore[attr-defined]
        assert entity._foo == 1  # type: ignore[attr-defined]
        # No EntityChanged emitted for non-Model attribute.
        assert listener.received == []


class TestDictEntityFactory:
    def test_get_returns_none_for_missing(self) -> None:
        factory = DictEntityFactory()
        assert factory.get("missing") is None

    def test_add_and_get(self) -> None:
        factory = DictEntityFactory()
        entity = make_entity("e1")
        factory.add(entity)
        assert factory.get("e1") is entity

    def test_delete_removes(self) -> None:
        factory = DictEntityFactory()
        entity = make_entity("e1")
        factory.add(entity)
        factory.delete("e1")
        assert factory.get("e1") is None

    def test_delete_missing_is_noop(self) -> None:
        factory = DictEntityFactory()
        # Should not raise.
        factory.delete("missing")

    def test_entities_returns_all_added(self) -> None:
        factory = DictEntityFactory()
        e1 = make_entity("e1")
        e2 = make_entity("e2")
        factory.add(e1)
        factory.add(e2)
        assert set(factory.entities()) == {e1, e2}

    def test_add_registers_new_entity(self) -> None:
        factory = DictEntityFactory()
        entity = make_entity("e1")
        factory.add(entity)
        assert factory.get("e1") is entity


# ----------------------------------------------------------------------
# Event machinery tests — one per labeled invariant
# ----------------------------------------------------------------------


class TestEntitySubscribe:
    """entity-subscribe: subscribe appends to listener list."""

    def test_subscribe_appends_listener(self) -> None:
        entity = make_entity()
        listener = _SyncListener()
        entity.subscribe(listener)
        assert listener in entity._listeners

    def test_subscribe_appends_multiple_in_order(self) -> None:
        entity = make_entity()
        l1 = _SyncListener()
        l2 = _SyncListener()
        l3 = _SyncListener()
        entity.subscribe(l1)
        entity.subscribe(l2)
        entity.subscribe(l3)
        assert entity._listeners == [l1, l2, l3]


class TestEntityUnsubscribe:
    """entity-unsubscribe: removes listener; no-op if not subscribed."""

    def test_unsubscribe_removes_listener(self) -> None:
        entity = make_entity()
        listener = _SyncListener()
        entity.subscribe(listener)
        entity.unsubscribe(listener)
        assert listener not in entity._listeners

    def test_unsubscribe_not_subscribed_is_noop(self) -> None:
        entity = make_entity()
        listener = _SyncListener()
        # Should not raise.
        entity.unsubscribe(listener)
        assert entity._listeners == []


class TestEntityEmit:
    """entity-emit: wraps each listener call in a tracked task via spawn_task;
    per-listener isolation."""

    async def test_emit_invokes_each_listener(self) -> None:
        entity = make_entity()
        l1 = _SyncListener()
        l2 = _SyncListener()
        entity.subscribe(l1)
        entity.subscribe(l2)

        event = EntityChanged(entity=entity, attributes=["test_attr"])
        entity._emit(event)
        await entity.idle()

        assert l1.received == [event]
        assert l2.received == [event]

    async def test_emit_wraps_in_tracked_tasks(self) -> None:
        entity = make_entity()
        # Use an async listener so the task is observably alive after _emit.
        listener = _AsyncListener()
        entity.subscribe(listener)

        event = EntityChanged(entity=entity, attributes=["test_attr"])
        entity._emit(event)
        # Immediately after _emit (no awaits), there should be a pending task.
        assert len(entity._pending_tasks) == 1
        await entity.idle()
        assert listener.received == [event]

    async def test_emit_per_listener_isolation(self, caplog) -> None:
        entity = make_entity()
        bad = _RaisingListener("emit-isolation")
        good = _SyncListener()
        entity.subscribe(bad)
        entity.subscribe(good)

        event = EntityChanged(entity=entity, attributes=["test_attr"])
        with caplog.at_level(logging.ERROR):
            entity._emit(event)
            await entity.idle()

        # The good listener still received the event despite the bad one raising.
        assert good.received == [event]


class TestEntitySpawnTask:
    """entity-spawn-task: tracks task in _pending_tasks; done-callback removes
    on completion + logs exception."""

    async def test_spawn_task_returns_task(self) -> None:
        entity = make_entity()

        async def coro() -> str:
            return "ok"

        task = entity.spawn_task(coro())
        assert isinstance(task, asyncio.Task)
        await task

    async def test_spawn_task_tracks_in_pending(self) -> None:
        entity = make_entity()

        async def coro() -> None:
            await asyncio.sleep(0.01)

        task = entity.spawn_task(coro())
        assert task in entity._pending_tasks
        await entity.idle()
        assert task not in entity._pending_tasks

    async def test_spawn_task_done_callback_removes(self) -> None:
        entity = make_entity()

        async def coro() -> None:
            return None

        task = entity.spawn_task(coro())
        await task
        # Allow the done-callback to fire.
        await asyncio.sleep(0)
        assert task not in entity._pending_tasks

    async def test_spawn_task_done_callback_logs_exception(self, caplog) -> None:
        entity = make_entity()

        async def coro() -> None:
            raise RuntimeError("spawn-task-boom")

        with caplog.at_level(logging.ERROR, logger="sidestage.entity"):
            task = entity.spawn_task(coro())
            with contextlib.suppress(RuntimeError):
                await task
            # Allow the done-callback to fire.
            await asyncio.sleep(0)

        # An error should have been logged.
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert any(
            "spawn-task-boom" in (r.exc_text or "")
            or "spawned task raised" in r.getMessage()
            for r in error_records
        ), f"expected error log for failed spawned task, got: {error_records}"


class TestEntityIdle:
    """entity-idle: loops until _pending_tasks empty; bounded by timeout;
    handles cascading tasks."""

    async def test_idle_returns_immediately_when_empty(self) -> None:
        entity = make_entity()
        # No pending tasks — idle should return immediately.
        await entity.idle()
        assert entity._pending_tasks == set()

    async def test_idle_waits_for_pending(self) -> None:
        entity = make_entity()
        completed: list[bool] = []

        async def slow() -> None:
            await asyncio.sleep(0.01)
            completed.append(True)

        entity.spawn_task(slow())
        await entity.idle()
        assert completed == [True]
        assert entity._pending_tasks == set()

    async def test_idle_bounded_by_timeout(self) -> None:
        entity = make_entity()

        async def forever() -> None:
            await asyncio.sleep(2.0)

        entity.spawn_task(forever())
        with pytest.raises(asyncio.TimeoutError):
            await entity.idle(timeout=0.05)

    async def test_idle_handles_cascading_tasks(self) -> None:
        """A task that spawns another task (cascading) should still be awaited."""
        entity = make_entity()
        order: list[str] = []

        async def second() -> None:
            await asyncio.sleep(0)
            order.append("second")

        async def first() -> None:
            await asyncio.sleep(0)
            order.append("first")
            entity.spawn_task(second())

        entity.spawn_task(first())
        await entity.idle(timeout=1.0)
        assert "first" in order
        assert "second" in order
        assert entity._pending_tasks == set()


class TestEntityNotifyDefaultNoop:
    """entity-notify-default-noop: default Entity.notify returns None / does nothing."""

    def test_default_notify_returns_none(self) -> None:
        entity = make_entity()
        event = EntityChanged(entity=entity, attributes=["test_attr"])
        result = entity.notify(event)
        assert result is None

    def test_default_notify_does_not_raise(self) -> None:
        entity = make_entity()
        event = EntityChanged(entity=entity, attributes=["test_attr"])
        # Should not raise for any input.
        entity.notify(event)


# ----------------------------------------------------------------------
# events.md protocol & error invariants
# ----------------------------------------------------------------------


class TestEventsProtocolSyncOrAsync:
    """events-protocol-sync-or-async: notify can be sync or async; bus awaits if coroutine."""

    async def test_sync_listener_invoked(self) -> None:
        entity = make_entity()
        listener = _SyncListener()
        entity.subscribe(listener)

        event = EntityChanged(entity=entity, attributes=["test_attr"])
        entity._emit(event)
        await entity.idle()

        assert listener.received == [event]

    async def test_async_listener_awaited(self) -> None:
        entity = make_entity()
        listener = _AsyncListener()
        entity.subscribe(listener)

        event = EntityChanged(entity=entity, attributes=["test_attr"])
        entity._emit(event)
        await entity.idle()

        # If the bus did not await the coroutine, .received would be empty
        # because the await asyncio.sleep(0) in _AsyncListener.notify would
        # not have scheduled the append.
        assert listener.received == [event]


class TestEventsErrorsListenerIsolation:
    """events-errors-listener-isolation: a raising listener doesn't abort the
    fanout; logs via caplog."""

    async def test_raising_listener_does_not_abort_fanout(self, caplog) -> None:
        entity = make_entity()
        bad = _RaisingListener("isolation-test")
        good = _SyncListener()
        entity.subscribe(bad)
        entity.subscribe(good)

        event = EntityChanged(entity=entity, attributes=["test_attr"])
        with caplog.at_level(logging.ERROR, logger="sidestage.entity"):
            entity._emit(event)
            await entity.idle()

        assert good.received == [event]

    async def test_raising_listener_logs_error(self, caplog) -> None:
        entity = make_entity()
        bad = _RaisingListener("listener-log-check")
        entity.subscribe(bad)

        event = EntityChanged(entity=entity, attributes=["test_attr"])
        with caplog.at_level(logging.ERROR, logger="sidestage.entity"):
            entity._emit(event)
            await entity.idle()

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, "expected at least one ERROR log for raising listener"
        # Either the message or formatted exc_text should mention the failure.
        joined = " ".join(
            (r.getMessage() + " " + (r.exc_text or "")) for r in error_records
        )
        assert "listener-log-check" in joined or "raised" in joined


class TestEventsErrorsSpawnedTask:
    """events-errors-spawned-task: failed spawned task logs via done-callback."""

    async def test_failed_spawned_task_is_logged(self, caplog) -> None:
        entity = make_entity()

        async def boom() -> None:
            raise RuntimeError("spawned-task-log-check")

        with caplog.at_level(logging.ERROR, logger="sidestage.entity"):
            task = entity.spawn_task(boom())
            with contextlib.suppress(RuntimeError):
                await task
            # Done-callback runs after the task finishes; yield once.
            await asyncio.sleep(0)

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, "expected at least one ERROR log for failed spawned task"


class TestEventsAsyncTasksSpawn:
    """events-async-tasks-spawn: spawn_task returns the task; cleanup on done."""

    async def test_spawn_task_returns_the_task(self) -> None:
        entity = make_entity()

        async def coro() -> int:
            return 42

        task = entity.spawn_task(coro())
        assert isinstance(task, asyncio.Task)
        result = await task
        assert result == 42

    async def test_spawn_task_cleanup_on_done(self) -> None:
        entity = make_entity()

        async def coro() -> None:
            return None

        task = entity.spawn_task(coro())
        assert task in entity._pending_tasks
        await task
        # The done-callback runs in the same loop iteration after task completion.
        await asyncio.sleep(0)
        assert task not in entity._pending_tasks


class TestEntityHashableById:
    """entity-hashable-by-id: __hash__ and __eq__ key off self.id."""

    def test_same_id_hashes_equal(self) -> None:
        a = make_entity(id="x")
        b = make_entity(id="x")
        assert hash(a) == hash(b), (
            "entity-hashable-by-id: entities with the same id MUST hash "
            f"equal; got hash(a)={hash(a)} hash(b)={hash(b)}"
        )

    def test_different_id_hashes_differ(self) -> None:
        a = make_entity(id="x")
        b = make_entity(id="y")
        # Hash collisions are theoretically possible but vanishingly rare for
        # short distinct strings — sanity check.
        assert hash(a) != hash(b)

    def test_eq_compares_id(self) -> None:
        a = make_entity(id="x", name="Alice")
        b = make_entity(id="x", name="Different name, same id")
        assert a == b, (
            "entity-hashable-by-id: entities with the same id MUST compare "
            f"equal regardless of other fields; got a={a.name!r} b={b.name!r}"
        )

    def test_eq_distinguishes_different_ids(self) -> None:
        a = make_entity(id="x")
        b = make_entity(id="y")
        assert a != b

    def test_eq_returns_false_for_non_entity(self) -> None:
        a = make_entity(id="x")
        assert a != "x"
        assert a != 42

    def test_keyable_in_dict(self) -> None:
        # The whole point: an Entity can key a dict (used by MessageContext).
        a = make_entity(id="x")
        d: dict[Entity, str] = {a: "hello"}
        # Lookup with a SECOND instance of the same id finds the entry.
        b = make_entity(id="x")
        assert d[b] == "hello"


class TestMessageContext:
    """entity-message-context: dataclass shape and defaults."""

    def test_default_annotations_is_empty_dict(self) -> None:
        scene = make_entity(id="scene-1")
        # Use a MagicMock for Message — MessageContext doesn't read it.
        from unittest.mock import MagicMock

        msg = MagicMock()
        ctx = MessageContext(message=msg, scene=scene)
        assert ctx.annotations == {}

    def test_annotations_are_per_instance(self) -> None:
        # Each MessageContext gets its own dict — no cross-pollination.
        from unittest.mock import MagicMock

        scene = make_entity(id="scene-1")
        ctx1 = MessageContext(message=MagicMock(), scene=scene)
        ctx2 = MessageContext(message=MagicMock(), scene=scene)
        ctx1.annotations[scene] = "x"
        assert ctx2.annotations == {}


class TestEntityAnnotateContextDefault:
    """entity-annotate-context: default writes self.body keyed by self."""

    def test_writes_body_keyed_by_self(self) -> None:
        from unittest.mock import MagicMock

        entity = make_entity(id="e1", body="my body text")
        scene = make_entity(id="scene-1")
        ctx = MessageContext(message=MagicMock(), scene=scene)

        entity.annotate_context(ctx)

        assert entity in ctx.annotations, (
            "entity-annotate-context: default impl MUST write self.body "
            f"keyed by self; got annotations={ctx.annotations!r}"
        )
        assert ctx.annotations[entity] == "my body text"

    def test_multiple_entities_each_contribute(self) -> None:
        from unittest.mock import MagicMock

        e1 = make_entity(id="e1", body="one")
        e2 = make_entity(id="e2", body="two")
        scene = make_entity(id="scene-1")
        ctx = MessageContext(message=MagicMock(), scene=scene)

        e1.annotate_context(ctx)
        e2.annotate_context(ctx)

        assert ctx.annotations[e1] == "one"
        assert ctx.annotations[e2] == "two"

    def test_idempotent_via_id_keying(self) -> None:
        # entity-annotate-context-idempotent: same id → same dict key →
        # second annotation overwrites (or is a no-op when value unchanged).
        from unittest.mock import MagicMock

        e1 = make_entity(id="dup", body="original")
        e2 = make_entity(id="dup", body="original")  # same id, same body
        scene = make_entity(id="scene-1")
        ctx = MessageContext(message=MagicMock(), scene=scene)

        e1.annotate_context(ctx)
        e2.annotate_context(ctx)

        assert len(ctx.annotations) == 1, (
            "entity-annotate-context-idempotent: multiple paths to the "
            "same entity MUST collapse to one annotation entry; "
            f"got annotations={ctx.annotations!r}"
        )


# ----------------------------------------------------------------------
# entity-list-attribute: EntityList mutators emit ListDelta
# ----------------------------------------------------------------------


class _EntityWithList(Entity):
    """An Entity subclass with a registered `items` EntityList field.

    Uses `list[str]` so Pydantic can schema-validate the field; the
    EntityList mutator path is independent of the element type, so
    strings are sufficient to exercise every code path.
    """

    class Model(Entity.Model):
        items: list[str] = []  # type: ignore[assignment]

    _entity_lists = {"items": EntityList}


def _make_list_entity(items: list[str] | None = None) -> _EntityWithList:
    model = _EntityWithList.Model(
        id=EntityId("le1"),
        name="L",
        type=EntityType.ENTITY,
        body="b",
        items=items or [],
    )
    return _EntityWithList(model, Campaign(name="t"))


class TestEntityListAppend:
    """entity-list-attribute: `append` emits `ListDelta(start=-1, len=0, items=[x])`."""

    def test_append_stores_item(self) -> None:
        entity = _make_list_entity()
        entity.items.append("x")
        assert list(entity.items) == ["x"]

    def test_append_emits_list_delta(self) -> None:
        entity = _make_list_entity()
        listener = _SyncListener()
        entity.subscribe(listener)

        async def run() -> None:
            entity.items.append("x")
            await entity.idle()

        asyncio.run(run())

        assert len(listener.received) == 1
        event = listener.received[0]
        assert event.entity is entity
        assert event.attributes == ["items"]
        delta = event.deltas["items"]
        assert isinstance(delta, ListDelta)
        assert delta.start == -1
        assert delta.len == 0
        assert delta.items == ["x"]


class TestEntityListInsert:
    def test_insert_emits_list_delta_with_position(self) -> None:
        entity = _make_list_entity(items=["a", "b"])
        listener = _SyncListener()
        entity.subscribe(listener)

        async def run() -> None:
            entity.items.insert(1, "x")
            await entity.idle()

        asyncio.run(run())

        assert list(entity.items) == ["a", "x", "b"]
        delta = listener.received[0].deltas["items"]
        assert isinstance(delta, ListDelta)
        assert delta.start == 1
        assert delta.len == 0
        assert delta.items == ["x"]


class TestEntityListExtend:
    def test_extend_emits_single_list_delta(self) -> None:
        entity = _make_list_entity()
        listener = _SyncListener()
        entity.subscribe(listener)

        async def run() -> None:
            entity.items.extend(["a", "b"])
            await entity.idle()

        asyncio.run(run())

        # extend emits ONE event carrying every appended item.
        assert len(listener.received) == 1
        delta = listener.received[0].deltas["items"]
        assert isinstance(delta, ListDelta)
        assert delta.start == -1
        assert delta.len == 0
        assert delta.items == ["a", "b"]


class TestEntityListPop:
    def test_pop_emits_list_delta_with_len_one(self) -> None:
        entity = _make_list_entity(items=["a", "b"])
        listener = _SyncListener()
        entity.subscribe(listener)

        async def run() -> None:
            entity.items.pop()
            await entity.idle()

        asyncio.run(run())

        delta = listener.received[0].deltas["items"]
        assert isinstance(delta, ListDelta)
        assert delta.start == 1  # -1 of len=2 resolves to position 1
        assert delta.len == 1
        assert delta.items == []


class TestEntityListRemove:
    def test_remove_emits_list_delta(self) -> None:
        entity = _make_list_entity(items=["a", "b"])
        listener = _SyncListener()
        entity.subscribe(listener)

        async def run() -> None:
            entity.items.remove("a")
            await entity.idle()

        asyncio.run(run())

        delta = listener.received[0].deltas["items"]
        assert isinstance(delta, ListDelta)
        assert delta.start == 0
        assert delta.len == 1
        assert delta.items == []


class TestEntityListClear:
    def test_clear_emits_list_delta(self) -> None:
        entity = _make_list_entity(items=["a", "b"])
        listener = _SyncListener()
        entity.subscribe(listener)

        async def run() -> None:
            entity.items.clear()
            await entity.idle()

        asyncio.run(run())

        delta = listener.received[0].deltas["items"]
        assert isinstance(delta, ListDelta)
        assert delta.start == 0
        assert delta.len == 2
        assert delta.items == []


class TestEntityListIsWrappedAtConstruction:
    """entity-list-attribute: Model fields declared in `_entity_lists`
    are replaced in place by an `EntityList` at construction."""

    def test_initial_field_becomes_entity_list(self) -> None:
        entity = _make_list_entity(items=["a"])
        assert isinstance(entity.items, EntityList)
        assert list(entity.items) == ["a"]


# ----------------------------------------------------------------------
# backend-action-decorator + backend-action-class-level
# ----------------------------------------------------------------------


class TestActionRegistry:
    """backend-action-class-level: `@action`-decorated methods on a subclass
    are collected into `cls._actions` by `__init_subclass__`."""

    def test_action_decorator_marks_method(self) -> None:
        # backend-action-marks-method: the decorator sets the
        # `__sidestage_action__` marker on the method object.
        @action
        def some_method() -> None:
            return None

        assert getattr(some_method, "__sidestage_action__", False) is True

    def test_subclass_collects_action_names(self) -> None:
        class _Decorated(Entity):
            class Model(Entity.Model):
                pass

            @action
            def alpha(self) -> None:
                return None

            @action
            def beta(self) -> None:
                return None

            def not_an_action(self) -> None:
                return None

        assert "alpha" in _Decorated._actions
        assert "beta" in _Decorated._actions
        assert "not_an_action" not in _Decorated._actions

    def test_subclass_without_actions_has_empty_set(self) -> None:
        class _Bare(Entity):
            class Model(Entity.Model):
                pass

        # An Entity subclass that declares no `@action` methods inherits
        # only whatever its bases declared. The base Entity declares
        # none, so the set is empty.
        assert "alpha" not in _Bare._actions

    def test_subclass_inherits_parent_actions(self) -> None:
        class _Parent(Entity):
            class Model(Entity.Model):
                pass

            @action
            def shared(self) -> None:
                return None

        class _Child(_Parent):
            @action
            def extra(self) -> None:
                return None

        assert "shared" in _Child._actions
        assert "extra" in _Child._actions


class TestEventsAsyncTasksIdle:
    """events-async-tasks-idle: handles cascading tasks (a task that triggers
    another task)."""

    async def test_cascading_emit_settles_via_idle(self) -> None:
        """A listener that itself spawns a task on the entity — idle should
        wait for the cascaded task too."""
        entity = make_entity()
        cascaded: list[str] = []

        async def cascaded_work() -> None:
            await asyncio.sleep(0)
            cascaded.append("done")

        class CascadingListener:
            def notify(self, event: EntityChanged) -> None:
                event.entity.spawn_task(cascaded_work())

        entity.subscribe(CascadingListener())

        event = EntityChanged(entity=entity, attributes=["test_attr"])
        entity._emit(event)
        await entity.idle(timeout=1.0)

        assert cascaded == ["done"]
        assert entity._pending_tasks == set()

    async def test_idle_waits_for_chained_spawn_tasks(self) -> None:
        entity = make_entity()
        completed: list[str] = []

        async def grandchild() -> None:
            await asyncio.sleep(0)
            completed.append("grandchild")

        async def child() -> None:
            await asyncio.sleep(0)
            completed.append("child")
            entity.spawn_task(grandchild())

        entity.spawn_task(child())
        await entity.idle(timeout=1.0)

        assert completed == ["child", "grandchild"]
        assert entity._pending_tasks == set()
