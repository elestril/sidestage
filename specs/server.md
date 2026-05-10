# server: Server startup and configuration

The Sidestage server is a CLI process. On startup it loads a campaign from
the config directory and begins serving the web UI.

- cuj-startup: The user starts the server, which loads the first campaign from the config directory.
  1. cuj-startup-launch: The user runs the server; --config defaults to config/
  2. cuj-startup-load: The server loads the first campaign found in the config directory
  3. cuj-startup-ready: The server begins serving the web UI

## server-state: ServerState

`ServerState = Enum('ServerState', ['LOADING', 'SERVING'])`
- server-state-loading: Initial state during campaign load; WS upgrades are rejected with 503.
- server-state-serving: Set once the campaign is fully loaded; WS upgrades are accepted.

## ws-dataflow: WebSocket dataflow

The chat UI communicates with the server over a single WebSocket per browser
session. The connection's lifecycle crosses the process boundary between the
browser and the FastAPI server.

1. ws-dataflow-connect: Browser opens WS to `/ws`.
   - .implements: cuj-hello-send
2. ws-dataflow-lameduck: If `App.state == LOADING`, the server rejects the WS upgrade with HTTP 503.
   - .implements: cuj-startup-ready
3. ws-dataflow-accept: If `App.state == SERVING`, the server accepts the upgrade and instantiates a `UserActor` bound to the active scene's human character.
   - .implements: cuj-startup-ready
4. ws-dataflow-init: The server sends an `InitEvent` carrying the active scene id and the serialized character entities currently in scope. No message history is sent — the client maintains its own.
   - .implements: cuj-startup-ready
5. ws-dataflow-inbound: `UserActor.run()` awaits a `MessageEvent` from the WebSocket and constructs a domain `Message` whose `sender` is the actor's character.
   - .implements: message-dataflow-receive, message-dataflow-deserialize
6. ws-dataflow-dispatch: `UserActor.run()` calls `scene.dispatch(message)` on the constructed domain `Message`.
   - .implements: message-dataflow-dispatch
7. ws-dataflow-outbound: For each domain `Message` delivered to the user via `UserActor.respond()`, the actor serializes it into `MessageEvent { sender_id, body }` and sends it over the WS.
   - .implements: message-dataflow-route
8. ws-dataflow-disconnect: On WS close, the `UserActor` is removed from the scene.
9. ws-dataflow-reconnect: A new connection re-enters at `ws-dataflow-connect`. Missed messages are NOT replayed; the client retains its local history.

## ws-events: Wire format

`InitEvent` and `MessageEvent` are Pydantic models co-located with `App` in
the server module.

### init-event: InitEvent

`scene_id: EntityId`
`characters: list[Character.Model]`
- init-event-scene: `scene_id` identifies the active scene on the client.
- init-event-characters: `characters` lists every character the client may need to render as a sender, serialized via `Character.serialize()`.

### message-event: MessageEvent

`sender_id: EntityId`
`body: str`
- message-event-sender: `sender_id` references a character previously delivered via `InitEvent`.
- message-event-body: `body` is the message text; client resolves `sender_id` against its entity cache for display.

## server-impl: App class

### server-app: App

FastAPI application and CLI entry point.

`config_dir: str`
`campaign: Campaign`
`state: ServerState`

`run(cls, config_dir: str = "config/") -> None` *(classmethod)*
- server-run-config: The `--config` flag sets `config_dir`; defaults to `"config/"`.
- server-run-state-loading: Sets `state = LOADING` before campaign load.
- server-run-load: Loads the single Campaign from `config_dir` on startup.
- server-run-state-serving: Sets `state = SERVING` after the campaign is fully loaded.
- server-run-serve: Starts the FastAPI server.
- .implements: cuj-startup-launch, cuj-startup-load, cuj-startup-ready

`GET /`
- server-route-root: Serves the chat UI HTML page.
- .implements: cuj-startup-ready

`WS /ws`
- server-route-ws-lameduck: Rejects upgrade with HTTP 503 if `state == LOADING`.
- server-route-ws-accept: Accepts upgrade if `state == SERVING` and instantiates a `UserActor` bound to the active scene's human character.
- server-route-ws-init: Sends `InitEvent` over the new socket before delegating to `UserActor.run()`.
- server-route-ws-disconnect: On WS close (normal or error), removes the `UserActor` from the scene.
- .implements: ws-dataflow-lameduck, ws-dataflow-accept, ws-dataflow-init, ws-dataflow-disconnect
