# events: EntityChanged pub/sub

Entities emit `EntityChanged` events. A `Listener` — anything implementing
`notify(event)` — subscribes to receive them. Every Entity is a Listener
(default no-op `notify`); non-Entity protocol-satisfiers (e.g. an SSE
handler's queue bridge) work too.

System state (server lifecycle, dep health, SSE handshake) is plumbing —
logged, not events.

## events-event-changed: EntityChanged

```python
@dataclass
class EntityChanged:
    entity: Entity         # the entity that mutated; the listener's source of truth
    attributes: list[str]  # names of attributes that changed
```

In-process the event carries the entity reference directly — listeners
read fresh state via `event.entity.<attr>`. The `attributes` list tells
the listener WHICH attributes changed so it can decide whether to react.
Today's only emit point: `Scene.append` fires
`EntityChanged(entity=self, attributes=["messages"])`.

`EntityChanged` is a plain `@dataclass`, NOT a Pydantic model. Wire
serialization happens at the SSE boundary (per `events-subscription`).

## events-protocol: Listener

```python
class Listener(Protocol):
    def notify(self, event: EntityChanged) -> None | Awaitable[None]: ...
```

- events-protocol-sync-or-async: `notify` may be either sync or async.
  The bus wraps each listener invocation in a task (per
  `events-async-tasks`); a slow or blocking listener cannot stall other
  listeners or the emitter.
- events-protocol-event-self-contained: The event carries everything the
  listener needs — `event.entity` for fresh state, `event.attributes` for
  the changed-attribute list.

## events-async-tasks: Per-listener tasks and idle

`Entity._emit` does NOT call `listener.notify` directly. It wraps each
listener invocation in a tracked task on the emitting entity:

```python
def _emit(self, event):
    for listener in self._listeners:
        self.spawn_task(self._invoke_listener(listener, event))

async def _invoke_listener(self, listener, event):
    try:
        result = listener.notify(event)
        if asyncio.iscoroutine(result):
            await result
    except Exception:
        logger.exception("listener %r raised", listener)
```

The wrapping gives per-listener isolation, lets listeners be sync or
async transparently, and tracks every reaction's task lifetime on the
emitting entity for `idle()`.

```python
def spawn_task(self, coro) -> asyncio.Task:
    """Track a task on this entity. The done-callback removes it from
    `_pending_tasks` and logs `task.exception()` if non-None."""

async def idle(self) -> None:
    """Loop until `_pending_tasks` is empty. Each iteration awaits
    `gather(*pending, return_exceptions=True)`. Bounded by a small
    timeout to fail fast on wedges. Used by tests (per `testing-runner`)
    to wait for cascading reactions to settle."""
```

- events-async-tasks-spawn: `Entity.spawn_task(coro)` registers and
  returns the task; done-callback handles cleanup and exception logging.
- events-async-tasks-idle: `Entity.idle()` is a test-only primitive;
  production never calls it. Awaits cascading reactions.
  - .tested-by: test_events_dataflow
- events-async-tasks-listener-spawn: Listeners can call
  `event.entity.spawn_task(coro)` for additional fan-out work beyond
  their own `notify` (rare but useful). No back-references required.

## events-patterns: Subscription and direct push

- events-pattern-subscription: `entity.subscribe(listener)` registers;
  `entity._emit(event)` fans out by calling `listener.notify(event)` on
  each subscriber.
  - .tested-by: test_events_dataflow
- events-pattern-subscription-lifecycle: The caller of `subscribe` owns
  the listener's lifetime. Subscriptions whose lifetime matches the
  entity (e.g. Scene subscribing its characters in `__init__`) need no
  explicit cleanup; they die when the entity's `_listeners` list is GC'd.
  Subscriptions that should end before the entity (e.g. SSE handlers
  whose request ends) MUST `unsubscribe` explicitly. For SSE specifically,
  the per-user `UserActor` owns the QueueListener's lifecycle — the SSE
  handler calls `user_actor.subscribe_to(entity, queue)` and
  `user_actor.unsubscribe_from(entity, queue)` (in `try/finally`). Notify
  still flows direct entity → QueueListener; UserActor is bookkeeping only.
- events-pattern-direct-push: `target.notify(event)` invoked directly —
  no subscription. Used for character-to-character whispers and other
  targeted notifications. (Future event types beyond `EntityChanged` may
  use this pattern.)

## events-subscription: SSE wire surface

```
GET /api/campaigns/{cid}/entities/{eid}/events
```

Frame: `event: entity_changed\ndata: {"entity_id": "...", "attributes": [...]}\n\n`.

The SSE handler serializes the in-process event by reading `event.entity.id`
and `event.attributes` — JSON-shaping happens at the wire boundary, not
in the event class. One connection per entity; no global firehose today.

## events-multi-window: Worked example — DM in two scenes

The "DM" character is a member of scene A and scene B. The DM player opens
two browser windows, one watching each scene.

Subscriptions formed at runtime:
- `scene_a.subscribe(dm)` and `scene_b.subscribe(dm)` — wired by each
  scene's constructor.
- Window 1 → `GET .../entities/{scene_a_id}/events` → handler resolves
  `App.get_actor(current_user)`, calls `user_actor.subscribe_to(scene_a, queue_1)`.
  UserActor creates `QueueListener(queue_1)`, calls `scene_a.subscribe(listener)`,
  tracks the listener.
- Window 2 → `GET .../entities/{scene_b_id}/events` → same dance with
  `scene_b` and `queue_2`.

Scene A emits an `EntityChanged`:
- DM character's `notify` runs (UserActor.respond is None — no auto-response).
- QueueListener 1 enqueues; window 1's stream yields the event.
- Window 2 is not subscribed to scene A → receives nothing.

No client-side filtering, no cross-scene leakage.

## events-errors: Exception handling

- events-errors-listener-isolation: Each listener runs inside its own
  task (per `events-async-tasks`); the per-listener wrapper catches
  `Exception` and logs. One bad listener cannot abort the fanout. Emit
  never propagates to the emitter — state mutation has already committed.
- events-errors-spawned-task: All tasks created via `Entity.spawn_task`
  carry a done-callback that logs `task.exception()` if non-None. This
  covers both the bus-spawned per-listener tasks AND any tasks listeners
  spawn explicitly (rare). Failed tasks never die silently.
- events-errors-slow-consumer: A QueueListener that hits `QueueFull` (slow
  client) drops the event for that consumer and logs. (Future: disconnect
  on repeated drops.)
- events-errors-test-visibility: `Scene.idle()` awaits pending tasks via
  `gather(*tasks, return_exceptions=True)` and re-raises unexpected
  exceptions so test failures observe the underlying error.
- events-errors-no-policy: The event bus does NOT auto-unsubscribe and
  does NOT retry. Both are policy decisions — they live in the listener
  (which can call `entity.unsubscribe(self)` from inside its `notify`) or
  in the listener's owner (the SSE handler's request loop calls
  `unsubscribe_from` on disconnect). The bus stays dumb so it doesn't
  grow brittle exception-type pattern matching.

## events-dataflow

1. events-dataflow-mutate: Entity state mutates.
   - .tested-by: test_events_dataflow
2. events-dataflow-emit: Entity calls `self._emit(EntityChanged(entity=self, attributes=[...]))`.
   - .tested-by: test_events_dataflow
3. events-dataflow-fan-out: `_emit` wraps each listener call in a tracked
   task via `self.spawn_task(self._invoke_listener(listener, event))`.
   The task catches per-listener exceptions and awaits async listeners.
   - .tested-by: test_events_dataflow
4. events-dataflow-deliver: SSE-handler `QueueListener.notify` does
   `queue.put_nowait(event)`; the response generator yields
   `event: entity_changed\ndata: {"entity_id": ..., "attributes": [...]}\n\n`.
   - .implemented-by: rest-api-get-entity-events
   - .tested-by: cuj-hello-browser
