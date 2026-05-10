# server: Server startup and configuration

The Sidestage server is a CLI process. On startup it loads a campaign from
the config directory and begins serving the web UI.

- cuj-startup: The user starts the server, which loads the first campaign from the config directory.
  1. cuj-startup-launch: The user runs `sidestage-ctl`; it reads the instance config
     - .implemented-by: InstanceConfig, App.run, runner-entrypoint
  2. cuj-startup-deps: The runner checks, starts, and validates all required dependencies
     - .implemented-by: runner-dep-health-check, runner-dep-start, runner-dep-wait, runner-dep-cwd-check, runner-dep-version-check, runner-dep-force-restart, Runner.check_deps, Runner.run, Runner.start
  3. cuj-startup-load: The server loads the first campaign found in the config directory
     - .implemented-by: fs-dataflow-config, fs-dataflow-walk, fs-dataflow-classify, fs-dataflow-parse, fs-dataflow-resolve-refs, fs-dataflow-deserialize, fs-dataflow-add, fs-dataflow-finalize, App.run, Runner.run, Runner.start
  4. cuj-startup-ready: The server begins serving the web UI
     - .implemented-by: frontend-serve, sse-client-scene, sse-client-entities, sse-dataflow-lameduck, sse-dataflow-accept, api-dataflow-subscribe, api-dataflow-scene, api-dataflow-entities, rest-api-get-root, App.run, Runner.run, Runner.start

## server-state: ServerState

`ServerState = Enum('ServerState', ['LOADING', 'SERVING'])`
- server-state-loading: Initial state during campaign load; all API endpoints return 503.
- server-state-serving: Set once the campaign is fully loaded; API endpoints are active.

## server-impl: App class

### server-app: App

FastAPI application and CLI entry point.

`config_dir: str`
`campaign: Campaign`
`state: ServerState`

`run(cls, config_dir: str = "configs/") -> None` *(classmethod)*
- server-run-config: The `--config` flag sets `config_dir`; defaults to `"configs/"`.
- server-run-state-loading: Sets `state = LOADING` before campaign load.
- server-run-load: Loads the single Campaign from `config_dir` on startup.
- server-run-state-serving: Sets `state = SERVING` after the campaign is fully loaded.
- server-run-serve: Starts the FastAPI server.
- .implements: cuj-startup-launch, cuj-startup-load, cuj-startup-ready

`GET /`
- server-route-root: Serves SPA or inline HTML fallback.
- .implements: rest-api-get-root

`GET /api/events`
- server-route-events: SSE notification stream.
- .implements: rest-api-get-events

`GET /api/scenes/active`
- server-route-scene: Returns `SceneResponse` for the active scene.
- .implements: rest-api-get-scene

`GET /api/entities/{entity_id}`
- server-route-entity: Returns `factory.get(entity_id).serialize()`; 404 if unknown.
- .implements: rest-api-get-entity

`GET /api/scenes/{scene_id}/messages`
- server-route-get-messages: Returns `list[Message.Model]` — the authoritative message history for the scene.
- .implements: rest-api-get-messages

`POST /api/scenes/{scene_id}/messages`
- server-route-post-message: Accepts `MessageRequest`; calls `scene.dispatch(message)`; returns `201 Created` with `MessageAccepted{id}`.
- .implements: rest-api-post-message
