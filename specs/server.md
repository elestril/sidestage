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

## server-impl: App class and wire models

The `App` class spec, the `ServerState` enum spec, and the per-route wire
model specs (`SceneResponse`, `MessageRequest`, `MessageAccepted`) live in
pydoc on `src/sidestage/server.py` per `spec-location-pydoc`.

Run `uv run pydoc-markdown`
to render the generated markdown view at `specs/generated/api.md`.

Key labels defined in pydoc (for cross-reference from this and other markdown specs):

- `server-state`, `server-state-loading`, `server-state-serving` — the `ServerState` enum and its members
- `server-app` — the `App` class
- `server-app-config-dir`, `server-app-campaign`, `server-app-state`, `server-app-factory` — `App` attributes
- `server-get-actor`, `server-get-actor-lazy`, `server-get-actor-cached`, `server-get-actor-unknown` — `App.get_actor`
- `server-run`, `server-run-config`, `server-run-state-loading`, `server-run-load`, `server-run-state-serving`, `server-run-serve` — `App.run`
- `server-scene-response` (+ `-id`, `-name`, `-character-ids`, `-player-character-ids`) — `SceneResponse` wire model
- `server-message-request` (+ `-sender-id`, `-body`) — `MessageRequest` wire model
- `server-message-accepted` (+ `-id`) — `MessageAccepted` wire model

## server-routes: HTTP route table

The route handlers themselves are registered by `App._setup_routes`. Each
route is a process-boundary surface and so its spec stays here in markdown
per `spec-location-markdown`. Per-route 503/422/404 details live in
`specs/rest-api.md`.

`GET /`
- server-route-root: Serves SPA or inline HTML fallback.
- .implements: rest-api-get-root

`GET /api/events`
- server-route-events: SSE notification stream.
- .implements: rest-api-get-events

`GET /api/campaign`
- server-route-campaign: Returns `CampaignResponse` (name + default_scene_id hint).
- .implements: rest-api-get-campaign

`GET /api/scenes`
- server-route-scenes: Returns `list[SceneResponse]` — every scene in the campaign.
- .implements: rest-api-get-scenes

`GET /api/scenes/{scene_id}`
- server-route-scene: Returns `SceneResponse` for the named scene; 404 if unknown.
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
