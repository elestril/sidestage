# events: EntityChanged pub/sub + WS frame schema

Entities emit `EntityChanged` events. A `Listener` — anything implementing
`notify(event)` — subscribes to receive them. Every Entity is itself a
Listener (default no-op `notify`); non-Entity protocol-satisfiers (e.g.
a WS handler's queue bridge) work too.

System state (server lifecycle, dep health, WS handshake) is plumbing —
logged, not events.

## events-event-changed: EntityChanged

```python
@dataclass
class EntityChanged:
    entity: Entity                                    # listener's source of truth
    attributes: list[str]                             # names of attributes that changed
    deltas: dict[str, AttributeDelta] = field(default_factory=dict)
```

In-process the event carries the entity reference directly — listeners
read fresh state via `event.entity.<attr>`. The `attributes` list tells
the listener WHICH attributes changed. The optional `deltas` map
carries the per-attribute payload itself (new scalar value, appended
collection items, etc.) so projections can apply the change directly
without re-reading the entity over REST (per
`events-attribute-deltas`). Today's only emit point is `Scene.append`:
`EntityChanged(entity=self, attributes=["messages"],
deltas={"messages": AppendDelta(items=[msg])})`. Plain `@dataclass`,
NOT a Pydantic model — wire serialisation happens at the WS boundary
(per `events-subscription`).

## events-attribute-deltas: Per-attribute delta payloads

Notifications carry the data, not a fetch hint. Each entry in
`deltas` is a typed payload that a projection can apply directly to
its cached entity state.

```python
@dataclass
class ScalarDelta:
    value: Any                       # new value of a scalar attribute

@dataclass
class AppendDelta:
    items: list                      # items appended at the tail

@dataclass
class InsertDelta:
    items: list[tuple[int, Any]]     # (index, item) pairs at insert positions

@dataclass
class RemoveDelta:
    indices: list[int]               # pre-removal positions of removed items

AttributeDelta = ScalarDelta | AppendDelta | InsertDelta | RemoveDelta
```

- events-attribute-deltas-self-contained: A delta carries everything
  the projection needs to apply the change. There is no follow-up
  fetch on the steady-state path. Initial state arrives in the
  `subscribed` reply; on reconnect, the client re-issues subscribe
  to get a fresh snapshot (per [[frontend]]
  `frontend-campaign-reconnect`).
- events-attribute-deltas-optional: The `deltas` map is optional —
  emitters MAY omit it for an attribute, in which case a projection
  treating its cache as authoritative falls back to "re-read the
  entity over REST." Producers SHOULD emit a delta; the no-delta
  fallback is for emit points that don't yet know how to describe
  their change (or for which a full re-read is cheaper than
  describing the diff).
- events-attribute-deltas-append-today: `Scene.append` is the only
  emit point today and produces `AppendDelta(items=[msg.Model()])`.
  Future collection mutators (`scene.edit_message`,
  `scene.redact_message`) emit `InsertDelta` / `RemoveDelta` /
  `ReplaceDelta` as their semantics demand.
- events-attribute-deltas-references: For attributes that hold
  `EntityId` references (e.g. `Scene.character_ids`), the delta
  carries the id itself; the projection separately fetches or
  subscribes to the referenced entity. Cross-entity hydration is
  not the delta's job.

## events-protocol: Listener

```python
class Listener(Protocol):
    def notify(self, event: EntityChanged) -> None | Awaitable[None]: ...
```

- events-protocol-sync-or-async: `notify` may be sync or async. The bus
  wraps each invocation in a task; a slow listener cannot stall others
  or the emitter.
- events-protocol-event-self-contained: The event carries everything
  the listener needs — `event.entity` for fresh state,
  `event.attributes` for the changed-attribute list.

## events-async-tasks: Per-listener tasks

`Entity._emit` does NOT call `listener.notify` directly. It wraps each
listener invocation in a tracked task so per-listener isolation holds
and the cascade can be awaited from tests:

```python
def _emit(self, event):
    for listener in self._listeners:
        self._spawn_task(self._invoke_listener(listener, event))

async def _invoke_listener(self, listener, event):
    try:
        result = listener.notify(event)
        if asyncio.iscoroutine(result):
            await result
    except Exception:
        logger.exception("listener %r raised", listener)
```

- events-async-tasks-private: `_spawn_task` is a private implementation
  detail of `_emit`. Production listeners that need additional fan-out
  use `asyncio.create_task` like any other async Python code.
- events-async-tasks-idle: `Scene.idle()` is the test-only primitive
  (lives on Scene because Scene is where the cascade depth actually
  matters; Entity has no `idle`). Awaits pending tasks via
  `gather(..., return_exceptions=True)` and re-raises unexpected
  exceptions so failures surface.
  - .tested-by: test_events_dataflow

## events-patterns: Subscription and direct push

- events-pattern-subscription: `entity.subscribe(listener)` registers;
  `entity._emit(event)` fans out by calling each subscriber's `notify`.
  - .tested-by: test_events_dataflow
- events-pattern-subscription-lifecycle: The caller of `subscribe` owns
  the listener's lifetime. Subscriptions whose lifetime matches the
  entity (e.g. Scene subscribing its characters in `__init__`) need no
  explicit cleanup. Subscriptions that end before the entity (e.g. WS
  connections) MUST `unsubscribe` explicitly — the per-socket
  `WsConnection` does this on `unsubscribe` frames and on socket close.
- events-pattern-direct-push: `target.notify(event)` invoked directly,
  no subscription. Used for targeted notifications (e.g. character-to
  -character whispers, future event types beyond `EntityChanged`).

## events-subscription: WS frame schema

The WebSocket is the **only** sync protocol. One connection per
browser tab at `WS /api/campaigns/{cid}/ws`, multiplexed for every
entity the client is observing. The handler is `WsConnection` (per
[[backend]] `backend-ws`). REST endpoints exist as a read-only
debug/ops mirror (per [[backend]] `backend-rest-debug`) but the FE
never reads from them.

**Client → server:**

```
{ "op": "subscribe",     "entity_ids": [...], "request_id": "..." }
{ "op": "unsubscribe",   "entity_ids": [...] }
{ "op": "entity_action", "entity_id": "...", "action": "speak",
                         "kwargs": { "body": "Hi" },
                         "request_id": "..." }
```

**Server → client:**

```
{ "op": "subscribed",     "request_id": "...",
                          "states": [{ "entity_id": "...", "model": {...} }, ...] }
{ "op": "entity_changed", "entity_id": "...", "attributes": [...],
                          "deltas": { "messages": { "kind": "append", "items": [...] } } }
{ "op": "ack",            "request_id": "..." }
{ "op": "error",          "request_id": "...", "code": "...", "message": "..." }
```

The `subscribed` reply carries the **current state** of each
requested entity (its `Entity.Model` payload) plus opens the
subscription. No separate "get" op exists; subscribe is the read
operation.

The `deltas` field on `entity_changed` is optional. Each value is a
tagged record (`kind` plus kind-specific fields) per
`events-attribute-deltas`:

```
{ "kind": "scalar", "value": <any> }
{ "kind": "append", "items": [...] }
{ "kind": "insert", "items": [[<int>, <any>], ...] }
{ "kind": "remove", "indices": [<int>, ...] }
```

- events-subscription-fanout: Fan-out on the server stays per-entity
  (each `QueueListener` is registered on a single entity); the socket
  multiplexes by `entity_id` in the frame envelope.
- events-subscription-initial-state: `subscribe` returns the initial
  state of every requested entity in its `subscribed` reply, then
  streams `entity_changed` frames for subsequent mutations. Clients
  apply the initial state, then apply each delta as it arrives.
  Unsubscribe is fire-and-forget — no ack.
- events-subscription-entity-action: `entity_action` is the single
  wire frame for invoking any RPC-callable method on any Entity. The
  server resolves the entity, validates the action against the
  subclass's `@action` registry (per [[backend]]
  `backend-action-decorator`), awaits
  `getattr(entity, action)(**kwargs)`, then sends a matching `ack`
  (no payload) or `error` frame keyed by `request_id`. `request_id`
  is an opaque client-generated string (uuid recommended).
- events-subscription-serialization: The handler serialises the
  in-process `EntityChanged` by reading `event.entity.id`,
  `event.attributes`, and `event.deltas` into the `entity_changed`
  frame. JSON shaping lives at the wire boundary, not in the event
  class.

## events-multi-window: Worked example — DM in two scenes

The "DM" character is a member of scene A and scene B. The DM player
opens two browser tabs, one per scene.

- `scene_a.subscribe(dm)` and `scene_b.subscribe(dm)` — wired by each
  scene's constructor.
- Tab 1 opens its WS, sends `subscribe(scene_a_id)`. WsConnection_1
  constructs `QueueListener(queue_1)` and calls
  `scene_a.subscribe(listener)`.
- Tab 2 opens its own WS, subscribes to `scene_b_id`. Different socket,
  different queue.

Scene A emits an `EntityChanged`:
- DM character's `notify` runs.
- QueueListener_1 enqueues; tab 1's socket sends the `entity_changed`
  frame.
- Tab 2's socket is not subscribed to scene A → receives nothing, even
  though the DM is a member of both scenes.

No client-side filtering, no cross-scene leakage.

## events-errors: Exception handling

- events-errors-listener-isolation: Each listener runs inside its own
  task; the per-listener wrapper catches `Exception` and logs. One bad
  listener cannot abort the fanout. Emit never propagates to the
  emitter — state mutation has already committed.
- events-errors-spawned-task: Tasks created via `_spawn_task` carry a
  done-callback that logs `task.exception()` if non-None. Failed tasks
  never die silently.
- events-errors-slow-consumer: A `QueueListener` that hits `QueueFull`
  drops the event for that consumer and logs. (Future: disconnect on
  repeated drops.)
- events-errors-action-failure: An `entity_action` whose method raises
  is caught by the WS dispatcher and surfaces as an `error` frame
  carrying `request_id` + a code/message. The exception is logged;
  Campaign state is unaffected (the method either committed before
  raising or didn't commit at all — same in-process semantics).
- events-errors-no-policy: The bus does NOT auto-unsubscribe and does
  NOT retry. Both are policy decisions — they live in the listener
  (it can call `entity.unsubscribe(self)` from inside `notify`) or in
  the listener's owner (the `WsConnection` unsubscribes on socket
  close).

## events-dataflow

1. events-dataflow-mutate: Entity state mutates (typically inside an
   `@action`-decorated method).
   - .tested-by: test_events_dataflow
2. events-dataflow-emit: Entity calls
   `self._emit(EntityChanged(entity=self, attributes=[...]))`.
   - .tested-by: test_events_dataflow
3. events-dataflow-fan-out: `_emit` wraps each listener call in a
   tracked task via `self._spawn_task(self._invoke_listener(...))`.
   - .tested-by: test_events_dataflow
4. events-dataflow-deliver: A `QueueListener` registered by a
   `WsConnection` does `queue.put_nowait(event)`; the connection's
   send loop drains the queue and emits an
   `{op:'entity_changed', entity_id, attributes}` frame on the socket.
   - .implemented-by: backend-ws
   - .tested-by: cuj-hello-browser
