from __future__ import annotations

import argparse
import asyncio
import json
import logging
from enum import Enum
from pathlib import Path
from typing import AsyncIterator, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from sidestage.actor import Actor, SceneUpdatedEvent, StubActor, UserActor
from sidestage.campaign import Campaign, CampaignResponse
from sidestage.entity import (
    DictEntityFactory,
    EntityId,
    UnresolvedEntityError,
)
from sidestage.message import Message, MessageId
from sidestage.scene import SceneResponse

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
# Wire models for request bodies tied to POST endpoints. SceneResponse and
# CampaignResponse live with their domain owners (sidestage.scene,
# sidestage.campaign) per spec-location-pydoc.
# ---------------------------------------------------------------------------


class MessageRequest(BaseModel):
    """server-message-request: Wire shape of `POST /api/campaigns/{cid}/scenes/{scene_id}/messages`.

    The minimal payload a client sends to inject a player message into a scene.
    The server constructs the actual `Message` from this plus the resolved
    sender Character.

    .implements: rest-api-post-message
    """

    sender_id: EntityId
    """server-message-request-sender-id: EntityId of the Character sending the
    message; must appear in `SceneResponse.player_character_ids` or the request
    is rejected with 422."""

    body: str
    """server-message-request-body: The message body text."""


class MessageAccepted(BaseModel):
    """server-message-accepted: Wire shape returned by
    `POST /api/campaigns/{cid}/scenes/{scene_id}/messages` on success (201 Created).

    Returns the server-assigned MessageId so the client can correlate its
    optimistic local message with the canonical entry in scene history.

    .implements: rest-api-post-message
    """

    id: MessageId
    """server-message-accepted-id: MessageId assigned by `Scene.dispatch`."""


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

_KEEPALIVE_INTERVAL_S = 15.0


async def _sse_event_stream(
    queue: asyncio.Queue,
    request: Optional[Request] = None,
    on_close=None,
    keepalive_interval_s: float = _KEEPALIVE_INTERVAL_S,
) -> AsyncIterator[bytes]:
    """Yield SSE bytes from a queue of SceneUpdatedEvent.

    rest-api-events-yield + sse-dataflow-event: emits each dequeued event as
    `event: scene_updated\\ndata: <json>\\n\\n`.
    rest-api-events-keepalive: emits `: keepalive` after `keepalive_interval_s`
    of inactivity.
    rest-api-events-cleanup: invokes `on_close` in the finally block.
    """
    try:
        while True:
            if request is not None and await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(
                    queue.get(),
                    timeout=keepalive_interval_s,
                )
            except asyncio.TimeoutError:
                yield b": keepalive\n\n"
                continue
            if isinstance(event, SceneUpdatedEvent):
                data = event.model_dump_json()
            else:
                data = json.dumps(event)
            yield f"event: scene_updated\ndata: {data}\n\n".encode("utf-8")
    finally:
        if on_close is not None:
            on_close()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


class App:
    """server-app: The Sidestage FastAPI application and CLI entry point.

    Owns the running campaign, the lifecycle state, and the FastAPI route
    table. Also owns two class-level singletons that deserialize-time code
    reaches via `App` directly: the actor registry (`_actors`, private) and
    the active EntityFactory (`factory`). Both are accessed from
    `Character.__init__` and `Scene.deserialize` without being threaded
    through call signatures.

    HTTP route handlers are registered by `_setup_routes`; their per-route
    invariants live in `specs/server.md` and `specs/rest-api.md`. Routes are
    deliberately thin: they call domain methods and return the result.

    .implements: cuj-startup-launch, cuj-startup-load, cuj-startup-ready
    .implemented-by: App.run, App.get_actor
    """

    config_dir: str
    """server-app-config-dir: Filesystem path the campaign is loaded from;
    set by `__init__` from the `--config` CLI flag (default `"configs/"`).

    .implements: server-run-config
    """

    campaigns: dict[str, Campaign]
    """server-app-campaigns: Loaded campaigns keyed by `campaign.name`. Today
    contains at most one entry (per `App.run` loading the first subdir found
    in `config_dir`). The dict shape is the scaffold for future multi-campaign
    support.

    .implements: cuj-startup-load
    """

    state: "ServerState"
    """server-app-state: Lifecycle state of this server instance. Starts at
    `LOADING`; flipped to `SERVING` by `App.run` after the campaign is fully
    loaded. Every API route gates on this via `_require_serving`.

    .implements: server-state-loading, server-state-serving
    """

    factory: object = None  # actual type: EntityFactory; set by App.run
    """server-app-factory: Class-level slot holding the active load's
    `EntityFactory`. Set by `App.run` BEFORE `Campaign.load` so deserialize-time
    code (e.g. `Scene.deserialize`) can resolve cross-references via
    `App.factory.get(...)` without the factory being threaded through every
    call signature. Typed as `object` because the concrete `EntityFactory`
    type would create an import cycle.

    .implements: cuj-startup-load
    """

    # server-app: class-level Actor registry. Private (leading underscore) per
    # `spec-link-targets-private`; the public surface is `App.get_actor`.
    _actors: dict[str, "Actor"] = {}

    def __init__(self, config_dir: str = "configs/") -> None:
        # server-run-config: default config dir is "configs/".
        self.config_dir = config_dir
        self.campaigns = {}
        # server-state-loading: initial state is LOADING.
        self.state = ServerState.LOADING
        self._fastapi: FastAPI = FastAPI()
        self._setup_routes()

    # ----------------------- actor registry -----------------------

    @classmethod
    def get_actor(cls, owner: str) -> "Actor":
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

        # Build the matching Actor. NpcActor is not yet implemented;
        # its slot raises KeyError per the spec.
        if owner == "user":
            # UserActor takes no constructor args. The Scene wires up
            # broadcast targets via `add_queue` / `remove_queue`; `notify` is
            # invoked by Scene with a fully-formed `SceneUpdatedEvent`.
            actor: Actor = UserActor()
        elif owner == "stub":
            actor = StubActor()
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

    @classmethod
    def _user_actor(cls, user_id: str) -> UserActor:
        """Resolve the `UserActor` for `user_id`. Raises `TypeError` if the
        registered actor is not a `UserActor` — only user-owned queues
        subscribe to scene updates.
        """
        actor = cls.get_actor(user_id)
        if not isinstance(actor, UserActor):
            raise TypeError(
                f"Actor for user_id={user_id!r} is {type(actor).__name__}, "
                "not UserActor; cannot subscribe a queue."
            )
        return actor

    @classmethod
    def _subscribe(cls, user_id: str, queue: asyncio.Queue) -> None:
        """Register `queue` with the user's actor for SSE delivery.

        Today: `user_id` is always `"user"` — routes to the singleton
        `UserActor`. Subsequent events dispatched to that actor will be
        enqueued on every registered queue, including this one.
        """
        cls._user_actor(user_id).add_queue(queue)

    @classmethod
    def _unsubscribe(cls, user_id: str, queue: asyncio.Queue) -> None:
        """Deregister `queue` previously registered via `_subscribe`."""
        cls._user_actor(user_id).remove_queue(queue)

    # ----------------------- helpers -----------------------

    def _require_serving(self) -> None:
        """Raise 503 if state == LOADING (per all rest-api-*-503 invariants)."""
        if self.state == ServerState.LOADING:
            raise HTTPException(status_code=503, detail="server loading")

    # ----------------------- routes -----------------------

    def _setup_routes(self) -> None:
        app = self._fastapi

        # rest-api-get-root: GET /. Registered only when the static dir is
        # absent — when present, the static mount below shadows `/` and
        # provides the SPA fallback (frontend-serve-mount/spa).
        if not _STATIC_DIR.exists():
            @app.get("/")
            async def get_root() -> Response:
                self._require_serving()
                # rest-api-root-fallback: inline HTML.
                return HTMLResponse(_INLINE_HTML)

        # rest-api-list-campaigns: GET /api/campaigns
        @app.get("/api/campaigns")
        async def list_campaigns() -> list[CampaignResponse]:
            self._require_serving()
            return [c.to_response() for c in self.campaigns.values()]

        # rest-api-get-campaign: GET /api/campaigns/{cid}
        @app.get("/api/campaigns/{cid}")
        async def get_campaign(cid: str) -> CampaignResponse:
            self._require_serving()
            campaign = self.campaigns.get(cid)
            if campaign is None:
                raise HTTPException(status_code=404, detail="campaign not found")
            return campaign.to_response()

        # rest-api-get-scenes: GET /api/campaigns/{cid}/scenes
        @app.get("/api/campaigns/{cid}/scenes")
        async def get_scenes(cid: str) -> list[SceneResponse]:
            self._require_serving()
            campaign = self.campaigns.get(cid)
            if campaign is None:
                raise HTTPException(status_code=404, detail="campaign not found")
            return [s.to_response() for s in campaign.scenes()]

        # rest-api-get-scene: GET /api/campaigns/{cid}/scenes/{scene_id}
        @app.get("/api/campaigns/{cid}/scenes/{scene_id}")
        async def get_scene(cid: str, scene_id: str) -> SceneResponse:
            self._require_serving()
            campaign = self.campaigns.get(cid)
            if campaign is None:
                raise HTTPException(status_code=404, detail="campaign not found")
            scene = campaign.scene(EntityId(scene_id))
            if scene is None:
                raise HTTPException(status_code=404, detail="scene not found")
            return scene.to_response()

        # rest-api-get-entity: GET /api/campaigns/{cid}/entities/{entity_id}
        @app.get("/api/campaigns/{cid}/entities/{entity_id}")
        async def get_entity(cid: str, entity_id: str) -> Response:
            self._require_serving()
            campaign = self.campaigns.get(cid)
            if campaign is None:
                raise HTTPException(status_code=404, detail="campaign not found")
            entity = campaign.factory.get(entity_id)
            # rest-api-entity-404: missing or unresolved entity.
            if entity is None:
                raise HTTPException(status_code=404, detail="entity not found")
            try:
                model = entity.serialize()
            except UnresolvedEntityError:
                raise HTTPException(status_code=404, detail="entity not resolved")
            return JSONResponse(content=model.model_dump(mode="json"))

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
            except ValueError:
                raise HTTPException(
                    status_code=422, detail="from/to must be integers"
                )

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
                scene.serialize_message(i).model_dump(mode="json")
                for i in range(from_idx, to_idx)
            ]
            return JSONResponse(content=payload)

        # rest-api-post-message: POST /api/campaigns/{cid}/scenes/{scene_id}/messages
        @app.post(
            "/api/campaigns/{cid}/scenes/{scene_id}/messages", status_code=201
        )
        async def post_message(
            cid: str, scene_id: str, body: MessageRequest
        ) -> MessageAccepted:
            self._require_serving()
            campaign = self.campaigns.get(cid)
            if campaign is None:
                raise HTTPException(status_code=404, detail="campaign not found")
            scene = campaign.scene(EntityId(scene_id))
            # rest-api-post-404.
            if scene is None:
                raise HTTPException(status_code=404, detail="scene not found")
            # rest-api-post-422: sender must be a user-controlled character.
            sender = next(
                (c for c in scene.user_characters if c.id == body.sender_id),
                None,
            )
            if sender is None:
                raise HTTPException(
                    status_code=422,
                    detail="sender_id is not a player character",
                )
            # rest-api-post-dispatch: construct Message(sender, body), dispatch,
            # take returned MessageId.
            msg = Message(sender=sender, body=body.body)
            message_id = scene.dispatch(msg)
            # rest-api-post-returns: 201 + MessageAccepted{id}.
            return MessageAccepted(id=message_id)

        # rest-api-get-events: GET /api/events
        @app.get("/api/events")
        async def get_events(request: Request) -> Response:
            self._require_serving()

            # rest-api-events-accept / sse-dataflow-accept: register a queue
            # with the user's actor via App._subscribe. Today _current_user
            # always returns "user"; the routing indirection lets multi-user
            # auth land later without touching the route.
            queue: asyncio.Queue = asyncio.Queue()
            user_id = App._current_user()
            App._subscribe(user_id, queue)

            def _on_close() -> None:
                # rest-api-events-cleanup / sse-dataflow-disconnect.
                App._unsubscribe(user_id, queue)

            async def event_stream() -> AsyncIterator[bytes]:
                async for chunk in _sse_event_stream(
                    queue=queue,
                    request=request,
                    on_close=_on_close,
                ):
                    yield chunk

            return StreamingResponse(
                event_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache"},
            )

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
    def run(cls, config_dir: str = "configs/", reload: bool = False) -> None:
        """server-run: CLI entry point — construct the App, load the single
        campaign, and start serving.

        Owns the LOADING -> SERVING lifecycle transition for one process. The
        active `EntityFactory` is installed on the class BEFORE `Campaign.load`
        runs so that any deserialize-time code can resolve cross-references
        via `App.factory.get(...)`.

        - server-run-config: The `--config` flag (or the `config_dir` argument)
          sets `config_dir`; defaults to `"configs/"`.
        - server-run-state-loading: Sets `state = LOADING` before campaign
          load; while in this state every API route returns 503.
        - server-run-load: Walks `config_dir` for subdirectories containing
          `config.yaml` and loads the FIRST one found (sorted, deterministic);
          registers it as `App.campaigns[campaign.name] = campaign`. Raises
          `RuntimeError` if no campaign subdir is found.
        - server-run-state-serving: Sets `state = SERVING` after the campaign
          is fully loaded; API endpoints become active.
        - server-run-serve: Starts the FastAPI server (uvicorn) on
          `0.0.0.0:8000`. Honors `reload` per `instance-config-reload` —
          when True, uvicorn is launched via the import-string form so it
          can watch and re-import on source changes.

        .implements: cuj-startup-launch, cuj-startup-load, cuj-startup-ready
        """
        # server-run-config.
        instance = cls(config_dir=config_dir)
        # server-run-state-loading.
        instance.state = ServerState.LOADING

        # server-app-factory: install the EntityFactory at the class level
        # BEFORE campaign load so deserialize-time code can reach it via
        # App.factory.
        cls.factory = DictEntityFactory()

        # server-run-load: walk for subdirs with a `config.yaml` and load the
        # first one; today's single-campaign world maps to dict[name] -> Campaign.
        campaign_dirs = sorted(
            d for d in Path(config_dir).iterdir()
            if d.is_dir() and (d / "config.yaml").exists()
        )
        if not campaign_dirs:
            raise RuntimeError(
                f"No campaign subdir with config.yaml in {config_dir}"
            )
        campaign = Campaign.load(campaign_dirs[0])
        instance.campaigns[campaign.name] = campaign
        # server-run-state-serving.
        instance.state = ServerState.SERVING
        # server-run-serve.
        uvicorn.run(instance._fastapi, host="0.0.0.0", port=8000)
        # NOTE: reload=True is a runner-level concern (see runner-start-daemonizes).
        # uvicorn's reload requires an import-string app reference; today the
        # subprocess in `Runner.start` accomplishes the same effect by relaunching
        # the entire `sidestage` process on file changes via a watcher. The
        # `reload` flag is accepted here for signature parity but doesn't change
        # uvicorn's behavior in this in-process call.
        _ = reload


def main() -> None:
    """server-main: CLI entry point for the `sidestage` console script.

    Parses `--config` and `--reload`, then runs `App.run(...)`. Used directly
    via `uv run sidestage` for development; production deployments go through
    `sidestage-ctl` (the runner) which spawns this entry as a subprocess and
    passes `--reload` per `instance-config-reload`.

    .implements: cuj-startup-launch
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn auto-reload on source changes.",
    )
    args = parser.parse_args()
    App.run(args.config, reload=args.reload)
