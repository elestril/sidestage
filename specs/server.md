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

## server-impl: App

`App` is the FastAPI process container. Owns `state` (LOADING/SERVING),
`campaigns: dict[str, Campaign]`, the class-level `_actors` registry
(via `App.get_actor(owner)`), and the class-level `factory` slot consulted
by `Scene.deserialize` during load. `App.run(config_dir, reload)` walks
`config_dir` for the first campaign subdir, loads it, flips state to
SERVING, launches uvicorn.

Wire models defined in this module: `SceneResponse`, `MessageRequest`,
`MessageAccepted`. (`CampaignResponse` lives in `campaign.py`;
`SceneResponse` returned from `scene.to_response()` lives in `scene.py`.)

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
  `MessageAccepted{id}` carrying the appended id. The npc response cycle
  fires asynchronously via listener fanout (per `events.md`); the POST
  handler does not await it. 404 if campaign or scene is unknown.
- .implements: rest-api-post-message
