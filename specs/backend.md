# backend: Server lifecycle, REST + WS surface, action dispatch

The Sidestage backend is a FastAPI process started by the `sidestage` CLI.
On startup it loads the first campaign found in the config directory, then
serves both the REST API (`/api/*`) and a multiplexed WebSocket
(`/api/campaigns/{cid}/ws`). Per-route invariants (status codes, response
shapes) live in pydoc on the handlers.

## backend-app: App

```python
class App:
    sidestage_dir: str
    campaigns: dict[str, Campaign]
    state: ServerState                        # LOADING | SERVING

    llm_profile: ClassVar[LlmProfile | None] = None
    _actors: ClassVar[dict[str, Actor]] = {}

    @classmethod
    def get_actor(cls, owner: str) -> Actor: ...
    @classmethod
    def run(cls, sidestage_dir, port, llm_profile_name) -> None: ...
    @classmethod
    def _build_and_load(cls, sidestage_dir, llm_profile_name) -> App: ...
```

- backend-state: `state` starts at `LOADING`; flips to `SERVING` after
  the campaign loads. Every REST route gates on this via
  `_require_serving` (returns 503 while loading); the WS handshake
  closes with code 1013 in the same state.
  - .implements: cuj-startup-launch, cuj-startup-load
- backend-llm-profile-slot: `App.llm_profile` is populated immediately
  after the campaign load by reading
  `load_profiles(sidestage_dir)[config.llm_profile]`. Required for
  `App.get_actor("npc")` (raises `RuntimeError` if None).
- backend-get-actor: Single point of singleton resolution.
  `"user" → UserActor()`, `"stub" → StubActor()`,
  `"npc" → NpcActor(cls.llm_profile.models["default"])`. First call
  instantiates and caches; subsequent calls return the cached instance.
  Unknown owner raises `KeyError`.
  - .implements: cuj-startup-ready
- backend-main-loads-dotenv: `main()` calls `python-dotenv`'s
  `load_dotenv()` before resolving config. `.env` (gitignored, repo
  root) contributes to `os.environ` so litellm and other env-reading
  clients see API keys. Variables are NOT pulled into `InstanceConfig`
  unless they carry the `SIDESTAGE_` prefix.
- .implemented-by: App, App.run, App._build_and_load, App.get_actor

`App` holds no factory slot. `Campaign` owns its own entities and
exposes `get`/`add`/`delete` directly (per [[entity-model]]
`entity-campaign`). `Campaign.load(path)` accepts the directory and
returns a fully-loaded `Campaign`; no class-level scaffolding is
needed.

## backend-instance-config: InstanceConfig

```python
class InstanceConfig(BaseSettings):
    sidestage_dir: str = "sidestage/"
    port: int = 8000
    reload: bool = False
    llm_profile: str = "localhost"
```

Typed pydantic-settings model. Resolution precedence (highest to
lowest): **CLI overrides > env vars (`SIDESTAGE_*`) >
`<sidestage_dir>/sidestage.yaml` > Pydantic defaults**.

- backend-instance-config-resolve: `instance_config.resolve(...)` merges
  the four sources. `None` from argparse (unset flag) means "not
  provided" so lower sources still win. Unknown YAML keys are ignored
  for forward-compat.
- backend-instance-config-env-roundtrip: `main()` writes the resolved
  `InstanceConfig` to `SIDESTAGE_INSTANCE_CONFIG` (JSON) before invoking
  uvicorn. The `create_app` factory reads it back via
  `model_validate_json`. Missing env var in `create_app` is a hard
  error.
- .implemented-by: InstanceConfig, instance_config.resolve,
  instance_config.serialize_to_env, instance_config.from_env

## backend-reload: dev hot-reload

When `reload` is true, `main()` dispatches to uvicorn's reload mechanism
instead of the direct `App.run` path.

- backend-reload-factory: `uvicorn.run("sidestage.server:create_app",
  factory=True, reload=True, reload_dirs=[<src/sidestage>], port=...)`.
  uvicorn spawns a worker subprocess that re-imports the module and
  calls `create_app()` on every file change. Config crosses the
  parent → worker boundary via env (`SIDESTAGE_INSTANCE_CONFIG`).
- backend-reload-dirs: Only `src/sidestage/` is watched. Frontend HMR
  is owned by Vite (`:5173`).
- backend-reload-no-state-persistence: Each reload re-imports the module
  → `App._actors` and per-process state start fresh. Scene message
  history (runtime-only) is wiped. The SPA's reconnect re-fetches the
  (now-empty) authoritative state.
- .implemented-by: server.create_app, server.main

## backend-routes: API surface

Two surfaces under `/api/*`:

1. **The WebSocket** at `/api/campaigns/{cid}/ws` — the canonical sync
   protocol. Subscribe-with-initial-state, mutations via EntityAction,
   `entity_changed` notifications. The FE talks only to this. Per
   [[events]] `events-subscription`.
2. **REST read-only mirror** — a small set of GET endpoints that
   project Campaign state into HTTP for debugging and ops inspection.
   The FE never reads from these (per `backend-rest-debug`).

Plus the static SPA bundle at `/`.

### backend-rest-debug: Read-only REST debug mirror

```
GET /                                           SPA bundle (or inline fallback)
GET /api/campaigns                              list[Campaign.Model]
GET /api/campaigns/{cid}                        Campaign.Model
GET /api/campaigns/{cid}/scenes                 list[Scene.Model]
GET /api/campaigns/{cid}/entities/{eid}         Entity.Model (Scene.Model | Character.Model)
GET /api/campaigns/{cid}/scenes/{sid}/messages  list[Message.Model]
```

- backend-rest-debug-readonly: The REST surface is **read-only**.
  There is no mutation REST endpoint. All writes flow through
  EntityAction frames on the WS (per `backend-ws`).
- backend-rest-debug-not-sync-protocol: The REST endpoints are a
  human/ops inspection surface. The FE Campaign does NOT use them
  — it issues subscribe over WS and receives initial state in the
  `subscribed` reply. A grep guard in CI enforces this (per
  [[frontend]] `frontend-no-rest`).
- backend-rest-debug-payloads: Responses are `Entity.Model` /
  `Campaign.Model` instances directly — the same payloads the WS
  delivers — per [[entity-model]] `entity-model-canonical`. No
  parallel `*Response` types.
- backend-rest-debug-503: Every REST handler calls
  `_require_serving()`, which raises 503 while `App.state == LOADING`.
- backend-rest-debug-ws-lameduck: The WS handshake closes with code
  1013 in `LOADING`.
- backend-route-root: GET `/` serves the static SPA (mount
  `html=True` for SPA fallback) when `static/` exists; otherwise
  returns inline HTML or 503 depending on state.
- .implements: cuj-startup-ready
- .implemented-by: App._setup_routes

## backend-action-decorator: `@action`

```python
def action(method):
    """Mark a method as RPC-callable. Registers the method name in the
    declaring class's `_actions: ClassVar[set[str]]` set."""
```

- backend-action-marks-method: `@action` is the only way to expose a
  mutator over the wire. Bare methods on Entity subclasses are
  in-process-only.
- backend-action-validates: `WsConnection`'s `entity_action` dispatcher
  checks `action_name in type(entity)._actions` before invoking;
  unknown actions return an `error` frame.
- backend-action-class-level: Each Entity subclass declares its action
  vocabulary by decoration. No registry file, no runtime configuration —
  static class-level state, discoverable via introspection.
- .implemented-by: action decorator, WsConnection._handle_entity_action

## backend-ws: WsConnection

```python
class WsConnection:
    campaign: Campaign
    websocket: WebSocket
    _queue: asyncio.Queue[EntityChanged]
    _subscriptions: dict[EntityId, QueueListener]
    _pending_acks: dict[str, asyncio.Future]    # request_id → future

    def __init__(self, campaign, websocket): ...
    async def run(self) -> None: ...            # accept + pump
```

The WS handler is a thin wrapper around `WsConnection.run()`. Each
accepted socket gets one instance.

- backend-ws-accept: `run()` accepts the socket, spawns a sender task
  draining `_queue`, then loops on `receive_text` → JSON-parse →
  dispatch by `op`. On any exit the receiver `finally` cancels the
  sender and walks `_subscriptions`, unsubscribing every listener.
- backend-ws-subscribe: `op="subscribe"` carries
  `(entity_ids, request_id)`. For each id: resolve the entity via
  `campaign.get(eid)`, construct a `QueueListener(self._queue)`,
  call `entity.subscribe(listener)`, record under
  `_subscriptions[eid]`. Idempotent — repeating a subscribe for the
  same id is a no-op. After all subscriptions land, send a single
  `subscribed` reply carrying `states: [{entity_id, model}, ...]` —
  the canonical Entity.Model payload for each requested entity, so
  the FE has authoritative initial state without a follow-up
  fetch. Unknown entity ids are returned with `model: null` (FE
  treats as missing).
- backend-ws-unsubscribe: `op="unsubscribe"` pops the listener and
  calls `entity.unsubscribe(listener)`. Fire-and-forget — no ack
  frame.
- backend-ws-entity-action: `op="entity_action"` carries
  `(entity_id, action, kwargs, request_id)`. Handler resolves the
  entity via `campaign.get(entity_id)`, validates
  `action in type(entity)._actions` (per `backend-action-decorator`),
  awaits `getattr(entity, action)(**kwargs)`, sends an `ack` frame
  on success or an `error` frame on validation/dispatch failure.
  Any exception raised by the action body surfaces as an `error`
  frame; the entity's state is unaffected unless the action
  committed before raising.
- backend-ws-send: Each `EntityChanged` dequeued from `_queue` is
  serialised at the wire boundary to
  `{"op":"entity_changed","entity_id": <id>, "attributes": [...],
  "deltas": {<attr>: <delta>}}`. The delta payload is the
  serialised `ListDelta` / `ScalarDelta` (per [[events]]
  `events-attribute-deltas`). Acks/errors are sent the same way,
  keyed by `request_id`.
- backend-ws-lameduck: The route handler closes with code 1013 while
  `App.state == LOADING`, 1008 if `cid` is unknown.
- .implements: cuj-hello-send, cuj-hello-respond
- .implemented-by: WsConnection, App._setup_routes
