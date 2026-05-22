from __future__ import annotations

import argparse
import logging
from enum import Enum
from pathlib import Path
from urllib.parse import quote

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from sidestage.actor import Actor, StubActor, UserActor
from sidestage.campaign import Campaign
from sidestage.entity import Entity, EntityId
from sidestage.instance_config import (
    from_env as _instance_config_from_env,
)
from sidestage.instance_config import (
    resolve as _instance_config_resolve,
)
from sidestage.instance_config import (
    serialize_to_env as _instance_config_serialize_to_env,
)
from sidestage.llm_profile import LlmProfile, load_profiles
from sidestage.npc_actor import NpcActor
from sidestage.scene import Scene
from sidestage.ws import WsConnection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# server-state
# ---------------------------------------------------------------------------


class ServerState(Enum):
    """server-state: Lifecycle state of the running server.

    The server transitions LOADING -> SERVING exactly once per process,
    inside `App.run`. The state is consulted by every API route handler
    via `_require_serving` to gate access during startup.

    Members:
    - server-state-loading: `LOADING` — initial state during campaign load;
      all API endpoints return 503.
    - server-state-serving: `SERVING` — set once the campaign is fully
      loaded; API endpoints are active.

    .implements: cuj-startup-launch, cuj-startup-load, cuj-startup-ready
    """

    LOADING = 1
    SERVING = 2


# ---------------------------------------------------------------------------
# Static directory and inline HTML fallback.
# ---------------------------------------------------------------------------


_STATIC_DIR: Path = Path(__file__).parent / "static"

_INLINE_HTML = """<!DOCTYPE html>
<html>
<head><title>Sidestage</title></head>
<body><h1>Sidestage</h1></body>
</html>
"""


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


class App:
    """server-app: The Sidestage FastAPI application and CLI entry point.

    Owns the running campaign, the lifecycle state, and the FastAPI route
    table. Holds two class-level slots: the actor registry (`_actors`,
    private, accessed via `App.get_actor`) and the active `llm_profile`
    (consulted by `App.get_actor("npc")`). Entity storage and forward-ref
    resolution live on `Campaign` itself — see `entity-campaign`.

    HTTP route handlers are registered by `_setup_routes`; their per-route
    invariants live in `specs/backend.md`. Routes are deliberately thin:
    they call domain methods and return the result.

    .implements: cuj-startup-launch, cuj-startup-load, cuj-startup-ready
    .implemented-by: App.run, App.get_actor
    """

    sidestage_dir: str
    """server-app-sidestage-dir: Filesystem path to the instance state
    root; set by `__init__` from the `--sidestage-dir` CLI flag (default
    `"sidestage/"`). Layout:

    ```
    <sidestage_dir>/
    ├── sidestage.yaml          # instance-level config (today: unused)
    ├── campaigns/<name>/...    # one or more campaign trees
    └── logs/                   # instance logs (future)
    ```

    .implements: server-run-sidestage-dir
    """

    campaigns: dict[str, Campaign]
    """server-app-campaigns: Loaded campaigns keyed by `campaign.name`. Today
    contains at most one entry (per `App.run` loading the first subdir found
    in `<sidestage_dir>/campaigns/`). The dict shape is the scaffold for
    future multi-campaign support.

    .implements: cuj-startup-load
    """

    state: ServerState
    """server-app-state: Lifecycle state of this server instance. Starts at
    `LOADING`; flipped to `SERVING` by `App.run` after the campaign is fully
    loaded. Every API route gates on this via `_require_serving`.

    .implements: server-state-loading, server-state-serving
    """

    llm_profile: LlmProfile | None = None
    """server-app-llm-profile: Class-level slot holding the resolved
    `LlmProfile` for this instance. Set by `_build_and_load` immediately
    after `factory`, by reading
    `load_profiles(sidestage_dir)[config.llm_profile]`. Parallel to
    `server-app-factory`. `None` until the first load.

    `App.get_actor("npc")` reads `cls.llm_profile.models["default"]` to
    construct the `NpcActor` (per `server-app-llm-profile-required-for-npc`).

    .implements: server-app-llm-profile
    """

    # server-app: class-level Actor registry. Private (leading underscore) per
    # `spec-link-targets-private`; the public surface is `App.get_actor`.
    _actors: dict[str, Actor] = {}

    def __init__(self, sidestage_dir: str = "sidestage/") -> None:
        # server-run-sidestage-dir: default instance state root is "sidestage/".
        self.sidestage_dir = sidestage_dir
        self.campaigns = {}
        # server-state-loading: initial state is LOADING.
        self.state = ServerState.LOADING
        self._fastapi: FastAPI = FastAPI()
        self._setup_routes()

    # ----------------------- actor registry -----------------------

    @classmethod
    def get_actor(cls, owner: str) -> Actor:
        """server-get-actor: Return the process-wide `Actor` singleton for
        `owner`, lazy-creating it on first call.

        Encodes the owner-string -> Actor-class mapping in one place so that
        every `Character` with the same `owner` shares one Actor instance —
        which is what lets the WebSocket / SSE layer fan one queue out to all
        user-controlled characters.

        - server-get-actor-lazy: First call for a given `owner` instantiates
          the matching Actor (`"user" → UserActor()`, `"stub" → StubActor()`,
          `"npc" → NpcActor()` once it lands) and caches it in `cls._actors`.
        - server-get-actor-cached: Subsequent calls return the cached instance
          — all characters with the same `owner` share one Actor.
        - server-get-actor-unknown: Raises `KeyError` for an owner with no
          registered Actor class.

        .implements: cuj-startup-ready
        """
        cached = cls._actors.get(owner)
        if cached is not None:
            return cached

        # Build the matching Actor (per server-get-actor-* invariants).
        if owner == "user":
            # UserActor takes no constructor args. The Scene wires up
            # broadcast targets via `add_queue` / `remove_queue`; `notify` is
            # invoked by Scene with a fully-formed `SceneUpdatedEvent`.
            actor: Actor = UserActor()
        elif owner == "stub":
            actor = StubActor()
        elif owner == "npc":
            # server-get-actor-npc: requires App.llm_profile to have been
            # populated by _build_and_load. If not, that's a load-order
            # bug, not a runtime fallback.
            if cls.llm_profile is None:
                raise RuntimeError(
                    "server-app-llm-profile-required-for-npc: "
                    "App.llm_profile is None — _build_and_load must "
                    "populate it before any Character with owner='npc' "
                    "is constructed."
                )
            entry = cls.llm_profile.models.get("default")
            if entry is None:
                raise KeyError(
                    "llm-profile-runtime-default-role: profile must "
                    "define a 'default' role for NpcActor; "
                    f"got models={sorted(cls.llm_profile.models)!r}"
                )
            actor = NpcActor(entry)
        else:
            # server-get-actor-unknown.
            raise KeyError(f"no Actor registered for owner={owner!r}")

        cls._actors[owner] = actor
        return actor

    # ----------------------- private plumbing -----------------------

    @classmethod
    def _current_user(cls) -> str:
        """Return the id of the user owning the current request.

        Stub: today returns `"user"` unconditionally. Future: extract from
        `Authorization: Bearer <token>` so multiple human users can be
        distinguished. The returned id is always a key into `cls._actors`.
        """
        return "user"

    # ----------------------- helpers -----------------------

    def _require_serving(self) -> None:
        """Raise 503 if state == LOADING (per all rest-api-*-503 invariants)."""
        if self.state == ServerState.LOADING:
            raise HTTPException(status_code=503, detail="server loading")

    # ----------------------- routes -----------------------

    def _setup_routes(self) -> None:
        app = self._fastapi

        # rest-api-get-root: GET / redirects to /<cid> for the loaded
        # campaign. Single-campaign today; future multi-campaign will
        # have a real selector page here. Registered BEFORE the static
        # mount so it always takes precedence over the SPA fallback.
        @app.get("/")
        async def get_root() -> Response:
            self._require_serving()
            if self.campaigns:
                cid = next(iter(self.campaigns))
                return RedirectResponse(url=f"/{quote(cid, safe='')}", status_code=302)
            # rest-api-root-fallback: no campaigns loaded → inline HTML.
            return HTMLResponse(_INLINE_HTML)

        # rest-api-list-campaigns: GET /api/campaigns
        @app.get("/api/campaigns")
        async def list_campaigns() -> list[Campaign.Model]:
            self._require_serving()
            return [c.to_model() for c in self.campaigns.values()]

        # rest-api-get-campaign: GET /api/campaigns/{cid}
        @app.get("/api/campaigns/{cid}")
        async def get_campaign(cid: str) -> Campaign.Model:
            self._require_serving()
            campaign = self.campaigns.get(cid)
            if campaign is None:
                raise HTTPException(status_code=404, detail="campaign not found")
            return campaign.to_model()

        # rest-api-get-scenes: GET /api/campaigns/{cid}/scenes
        @app.get("/api/campaigns/{cid}/scenes")
        async def get_scenes(cid: str) -> list[Scene.Model]:
            self._require_serving()
            campaign = self.campaigns.get(cid)
            if campaign is None:
                raise HTTPException(status_code=404, detail="campaign not found")
            return [s.model for s in campaign.scenes()]

        # rest-api-get-entity: GET /api/campaigns/{cid}/entities/{entity_id}.
        # response_model=None: returning a subclass of Entity.Model (e.g.
        # Character.Model with `owner`). FastAPI would otherwise project
        # onto the base class and strip subclass fields.
        @app.get("/api/campaigns/{cid}/entities/{entity_id}", response_model=None)
        async def get_entity(cid: str, entity_id: str) -> Entity.Model:
            self._require_serving()
            campaign = self.campaigns.get(cid)
            if campaign is None:
                raise HTTPException(status_code=404, detail="campaign not found")
            entity = campaign.get(entity_id)
            if entity is None:
                raise HTTPException(status_code=404, detail="entity not found")
            return entity.model

        # rest-api-get-messages: GET /api/campaigns/{cid}/scenes/{scene_id}/messages
        @app.get("/api/campaigns/{cid}/scenes/{scene_id}/messages")
        async def get_messages(
            cid: str,
            scene_id: str,
            request: Request,
        ) -> Response:
            self._require_serving()
            campaign = self.campaigns.get(cid)
            if campaign is None:
                raise HTTPException(status_code=404, detail="campaign not found")
            scene = campaign.scene(EntityId(scene_id))
            # rest-api-get-messages-404
            if scene is None:
                raise HTTPException(status_code=404, detail="scene not found")

            params = request.query_params
            n = len(scene.messages)
            try:
                from_idx = int(params["from"]) if "from" in params else 0
                # Default `to` is len(scene.messages) — the half-open upper
                # bound. Empty scene -> default to=0 -> range(0,0) -> [].
                to_idx = int(params["to"]) if "to" in params else n
            except ValueError as exc:
                raise HTTPException(
                    status_code=422, detail="from/to must be integers"
                ) from exc

            # rest-api-get-messages-422: negative bounds, from > to, to > len.
            if from_idx < 0 or to_idx < 0:
                raise HTTPException(status_code=422, detail="negative bound")
            if from_idx > to_idx:
                raise HTTPException(status_code=422, detail="from > to")
            if to_idx > n:
                raise HTTPException(status_code=422, detail="to > len(messages)")

            # rest-api-get-messages-build: half-open range, Python slice
            # semantics. `from == to` (incl. the empty-scene default) yields [].
            payload = [
                scene.messages[i].model_dump(mode="json")
                for i in range(from_idx, to_idx)
            ]
            return JSONResponse(content=payload)

        # ws-route-connection: WS /api/campaigns/{cid}/ws — multiplexed
        # subscription endpoint per `specs/events.md#events-subscription`.
        @app.websocket("/api/campaigns/{cid}/ws")
        async def get_entity_ws(websocket: WebSocket, cid: str) -> None:
            """Multiplexed WS for entity subscriptions and (Phase 2) mutations.

            Frame schema lives in `specs/events.md`. This handler is a thin
            wrapper around `WsConnection.run()`; per-frame invariants live
            in `sidestage.ws`.
            """
            # ws-dataflow-lameduck: close with 1013 (Try Again Later) while
            # the server is still loading. Accept first so the client sees
            # a proper close frame rather than a TCP reset.
            if self.state == ServerState.LOADING:
                await websocket.accept()
                await websocket.close(code=1013)
                return
            campaign = self.campaigns.get(cid)
            if campaign is None:
                await websocket.accept()
                await websocket.close(code=1008)  # policy violation: unknown cid
                return
            await WsConnection(campaign, websocket).run()

        # rest-api-get-campaign-spa: GET /<cid> serves the SPA HTML for
        # any loaded campaign. The static mount's `html=True` only
        # serves index.html at the literal `/`; a campaign-scoped URL
        # needs an explicit handler so the FE can read its `cid` from
        # `window.location.pathname` (per `frontend-workspace-cid-from-url`).
        #
        # This route also catches single-segment root-level files
        # (favicon.ico, robots.txt, …) by checking the static dir first.
        @app.get("/{cid}")
        async def get_campaign_spa(cid: str) -> Response:
            self._require_serving()
            # Single-segment root-level static asset wins if present.
            if _STATIC_DIR.exists():
                candidate = _STATIC_DIR / cid
                if candidate.is_file():
                    return FileResponse(candidate)
            if cid not in self.campaigns:
                raise HTTPException(status_code=404, detail="not found")
            if _STATIC_DIR.exists():
                return FileResponse(_STATIC_DIR / "index.html")
            return HTMLResponse(_INLINE_HTML)

        # frontend-serve-mount + frontend-serve-spa: mount StaticFiles at `/`
        # AFTER all `/api/*` routes are registered. `html=True` provides SPA
        # fallback to `index.html` for unknown paths. The mount shadows any
        # explicit `GET /` handler — that handler is therefore only registered
        # above when `_STATIC_DIR` is absent.
        if _STATIC_DIR.exists():
            self._fastapi.mount(
                "/",
                StaticFiles(directory=str(_STATIC_DIR), html=True),
                name="static",
            )

    # ----------------------- run -----------------------

    @classmethod
    def _build_and_load(
        cls, sidestage_dir: str, llm_profile_name: str = "localhost"
    ) -> App:
        """server-build-and-load: shared construction + load path.

        Both `App.run` (non-reload entry) and `create_app` (uvicorn reload
        factory) call this. Owns the LOADING -> SERVING transition.

        - server-run-state-loading: Sets `state = LOADING` before campaign
          load; while in this state every API route returns 503.
        - server-app-llm-profile: Loads
          `<sidestage_dir>/llm_profiles/<llm_profile_name>.yaml` into
          `cls.llm_profile` BEFORE campaign load so that any Character
          with `owner="npc"` can construct its NpcActor at deserialize
          time.
        - server-run-load: Walks `<sidestage_dir>/campaigns/` for
          subdirectories containing `config.yaml` and loads the FIRST one
          found (sorted, deterministic); registers it as
          `App.campaigns[campaign.name] = campaign`. Raises `RuntimeError`
          if `<sidestage_dir>/campaigns/` is missing or empty.
        - server-run-state-serving: Sets `state = SERVING` after the campaign
          is fully loaded; API endpoints become active.
        """
        # server-run-sidestage-dir.
        instance = cls(sidestage_dir=sidestage_dir)
        # server-run-state-loading.
        instance.state = ServerState.LOADING

        # server-app-llm-profile: resolve the active LLM profile from disk.
        # Missing dir → empty dict per llm-profile-discovery-missing-dir;
        # missing-named-profile is a config error (we surface a clear
        # message instead of letting NpcActor instantiation crash later).
        profiles = load_profiles(sidestage_dir)
        if profiles and llm_profile_name not in profiles:
            available = ", ".join(sorted(profiles)) or "(none)"
            raise RuntimeError(
                f"server-app-llm-profile: profile {llm_profile_name!r} not "
                f"found in {sidestage_dir}/llm_profiles/; "
                f"available: {available}"
            )
        cls.llm_profile = profiles.get(llm_profile_name)

        # server-run-load: walk `<sidestage_dir>/campaigns/` for subdirs
        # with a `config.yaml`. Today's single-campaign world maps to
        # dict[name] -> Campaign.
        campaigns_root = Path(sidestage_dir) / "campaigns"
        if not campaigns_root.is_dir():
            raise RuntimeError(f"No campaigns/ directory under {sidestage_dir}")
        campaign_dirs = sorted(
            d
            for d in campaigns_root.iterdir()
            if d.is_dir() and (d / "config.yaml").exists()
        )
        if not campaign_dirs:
            raise RuntimeError(f"No campaign with config.yaml in {campaigns_root}")
        campaign = Campaign.load(campaign_dirs[0])
        instance.campaigns[campaign.name] = campaign
        # server-run-state-serving.
        instance.state = ServerState.SERVING
        return instance

    @classmethod
    def run(
        cls,
        sidestage_dir: str = "sidestage/",
        port: int = 8000,
        llm_profile_name: str = "localhost",
    ) -> None:
        """server-run: non-reload entry point — build, load, serve.

        - server-run-sidestage-dir: The `sidestage_dir` argument sets the
          instance state root; defaults to `"sidestage/"`. Campaign trees
          live under `<sidestage_dir>/campaigns/<name>/`.
        - server-run-port: The `port` argument sets the listen port;
          defaults to `8000`. Test harnesses pass an ephemeral port to
          avoid colliding with the dev server.
        - server-run-serve: Starts the FastAPI server (uvicorn) on
          `0.0.0.0:<port>`.

        `llm_profile_name` selects which YAML under
        `<sidestage_dir>/llm_profiles/` is loaded into `App.llm_profile`
        (per `server-app-llm-profile`).

        For the reload path see `create_app` and `server-run-reload`.

        .implements: cuj-startup-launch, cuj-startup-load, cuj-startup-ready
        """
        instance = cls._build_and_load(sidestage_dir, llm_profile_name)
        # server-run-serve.
        uvicorn.run(instance._fastapi, host="0.0.0.0", port=port)


def create_app() -> FastAPI:
    """server-create-app: zero-arg ASGI factory for `uvicorn --reload`.

    uvicorn's reload mechanism spawns a worker subprocess that imports
    this module fresh on every file change. The factory contract requires
    a zero-arg callable returning the ASGI app — so config is passed
    through the env (`SIDESTAGE_INSTANCE_CONFIG`, JSON) set by `main()`
    before invoking uvicorn.

    .implements: server-run-reload, cuj-startup-launch
    """
    config = _instance_config_from_env()
    instance = App._build_and_load(config.sidestage_dir, config.llm_profile)
    return instance._fastapi


def main() -> None:
    """server-main: CLI entry point for the `sidestage` console script.

    Parses `--sidestage-dir`, `--port`, `--reload`. Resolves into an
    `InstanceConfig` (per `instance-config-resolve`), serializes to env,
    then dispatches to uvicorn. When `reload` is true, uvicorn runs the
    `create_app` factory in a worker subprocess and re-runs the factory
    on any file change under `src/sidestage/`.

    - server-main-loads-dotenv: Before resolving config or starting
      uvicorn, loads `.env` (if present) into `os.environ` via
      `python-dotenv`. API keys and other secrets live there
      (gitignored); read by downstream HTTP clients (e.g. litellm) at
      runtime.

    .implements: cuj-startup-launch
    """
    # server-main-loads-dotenv. Idempotent: if .env is absent, no-op.
    load_dotenv()

    parser = argparse.ArgumentParser()
    parser.add_argument("--sidestage-dir", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument(
        "--reload",
        action="store_true",
        default=None,
        help="Run under uvicorn --reload (dev workflow).",
    )
    args = parser.parse_args()

    config = _instance_config_resolve(
        sidestage_dir=args.sidestage_dir,
        port=args.port,
        reload=args.reload,
    )
    _instance_config_serialize_to_env(config)

    if config.reload:
        # server-run-reload: factory + reload_dirs.
        uvicorn.run(
            "sidestage.server:create_app",
            factory=True,
            host="0.0.0.0",
            port=config.port,
            reload=True,
            reload_dirs=[str(Path(__file__).parent)],
        )
    else:
        App.run(
            config.sidestage_dir,
            port=config.port,
            llm_profile_name=config.llm_profile,
        )
