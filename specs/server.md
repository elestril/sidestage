# server: Server startup and configuration

The Sidestage server is a CLI process. On startup it loads a campaign from
the config directory and begins serving the web UI.

- cuj-startup: The user starts the server, which loads the first campaign from the config directory.
  1. cuj-startup-launch: The user runs the server; --config defaults to config/
  2. cuj-startup-load: The server loads the first campaign found in the config directory
  3. cuj-startup-ready: The server begins serving the web UI

## server-impl: Implementation specs

- server-cli-config: The `--config` flag sets the config directory; defaults to `config/`
  - .implements: cuj-startup-launch
- server-load-campaign: On startup loads the single Campaign found in the config directory
  - .implements: cuj-startup-load
- server-route-root: `GET /` serves the chat UI HTML page
  - .implements: cuj-startup-ready
- server-route-ws: `WS /ws` accepts WebSocket connections and creates a UserActor per connection
  - .implements: cuj-hello-send
