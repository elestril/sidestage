# server: Server startup and configuration

The Sidestage server is a CLI process. On startup it loads a campaign from
the config directory and begins serving the web UI.

- cuj-startup: The user starts the server, which loads the first campaign from the config directory.
  1. cuj-startup-launch: The user runs `sidestage` (typically via `just run`, which also brings up the Vite dev server).
     - .implemented-by: App.run
  2. cuj-startup-load: The server loads the first campaign found in the config directory.
     - .implemented-by: fs-dataflow-config, fs-dataflow-walk, fs-dataflow-classify, fs-dataflow-parse, fs-dataflow-resolve-refs, fs-dataflow-deserialize, fs-dataflow-add, fs-dataflow-finalize, App.run
  3. cuj-startup-ready: The server begins serving the web UI.
     - .implemented-by: frontend-serve, sse-client-scene, sse-client-entities, sse-dataflow-lameduck, sse-dataflow-accept, sse-dataflow-connect, rest-api-get-root, App.run

## server-impl: App

`App` is the FastAPI process container. Owns `state` (LOADING/SERVING),
`campaigns: dict[str, Campaign]`, the class-level `_actors` registry
(via `App.get_actor(owner)`), and the class-level `factory` slot consulted
by `Scene.deserialize` during load. `App.run(sidestage_dir, port)` walks
`<sidestage_dir>/campaigns/` for the first campaign subdir, loads it,
flips state to SERVING, launches uvicorn.

Wire models defined in this module: `SceneResponse`, `MessageRequest`,
`MessageAccepted`. (`CampaignResponse` lives in `campaign.py`;
`SceneResponse` returned from `scene.to_response()` lives in `scene.py`.)

## server-run-reload: dev hot-reload via uvicorn factory

When `instance-config-reload` is true, `main()` dispatches to uvicorn's
reload mechanism instead of the direct `App.run` path.

- server-run-reload-factory: `uvicorn.run("sidestage.server:create_app",
  factory=True, reload=True, reload_dirs=[<src/sidestage>], port=...)`.
  uvicorn's reload spawns a worker subprocess that re-imports
  `sidestage.server` and calls `create_app()` on every file change
  under `reload_dirs`. The factory is zero-arg by contract; config
  crosses the parent → worker boundary via env per
  `instance-config-env-roundtrip`.
- server-run-reload-dirs: Only `src/sidestage/` is watched. Frontend
  HMR is owned by Vite (`:5173`), which watches its own tree.
- server-run-reload-no-state-persistence: Each reload re-imports the
  module → `App._actors`, `App.factory`, and per-process state start
  fresh. Scene message history (runtime-only per `scene-on-disk`) is
  wiped. The SPA's `frontend-be-consistency-on-reconnect` re-fetches
  the (now-empty) authoritative state — chat clears on reload. Known
  dev trade-off; not a bug. Persistence is a separate concern.
- server-run-reload-prod-off: `reload=False` is the production default;
  `App.run` invokes uvicorn directly with the pre-constructed app
  object (no factory, no subprocess).
- .implemented-by: server.create_app, server.main
- .tested-by: test_create_app_reads_env_and_builds, test_create_app_missing_env_is_fatal

## server-routes: HTTP route table

The route handlers themselves are registered by `App._setup_routes`. Each
route is a process-boundary surface and so its spec stays here in markdown
per `spec-location-markdown`. Per-route 503/422/404 details live in
`specs/rest-api.md`.

`GET /`
- server-route-root: Serves SPA or inline HTML fallback.
- .implements: rest-api-get-root

`GET /api/campaigns/{cid}/entities/{entity_id}/events`
- server-route-entity-events: Per-entity SSE stream of `EntityChanged` events.
  Resolves `current_user`, calls `App.get_actor(current_user).subscribe_to(entity, queue)`,
  yields events as `event: entity_changed\ndata: …\n\n`, calls
  `unsubscribe_from` in `finally`. No global `/api/events` endpoint.
- .implements: rest-api-get-entity-events, events-subscription

`GET /api/campaigns`
- server-route-list-campaigns: Returns `list[CampaignResponse]` — one entry
  per loaded campaign in `App.campaigns.values()`. Today the list contains
  exactly one entry; the shape is the multi-campaign scaffold.
- .implements: rest-api-list-campaigns

`GET /api/campaigns/{cid}`
- server-route-campaign: Returns `CampaignResponse` (name + default_scene_id hint); 404 if `App.campaigns.get(cid)` is None.
- .implements: rest-api-get-campaign

`GET /api/campaigns/{cid}/scenes`
- server-route-scenes: Returns `list[SceneResponse]` — every scene in the campaign; 404 if campaign unknown.
- .implements: rest-api-get-scenes

`GET /api/campaigns/{cid}/scenes/{scene_id}`
- server-route-scene: Returns `SceneResponse` for the named scene; 404 if campaign or scene is unknown.
- .implements: rest-api-get-scene

`GET /api/campaigns/{cid}/entities/{entity_id}`
- server-route-entity: Returns `campaign.factory.get(entity_id).serialize()`; 404 if campaign, entity, or resolution is missing.
- .implements: rest-api-get-entity

`GET /api/campaigns/{cid}/scenes/{scene_id}/messages`
- server-route-get-messages: Returns `list[Message.Model]` — the authoritative message history for the scene; 404 if campaign or scene is unknown.
- .implements: rest-api-get-messages

`POST /api/campaigns/{cid}/scenes/{scene_id}/messages`
- server-route-post-message: Accepts `MessageRequest`; constructs `Message`,
  calls `scene.append(message)`, returns `201 Created` with
  `MessageAccepted{scene_id, index}` carrying the appended message's
  composite identity. The npc response cycle
  fires asynchronously via listener fanout (per `events.md`); the POST
  handler does not await it. 404 if campaign or scene is unknown.
- .implements: rest-api-post-message
