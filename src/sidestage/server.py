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

from sidestage.actor import Actor, StubActor, UserActor
from sidestage.events import EntityChanged
from sidestage.campaign import Campaign, CampaignResponse
from sidestage.entity import (
    DictEntityFactory,
    EntityId,
    UnresolvedEntityError,
)
from sidestage.message import Message
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

    Carries the composite identity assigned by `Scene.append` so the
    client can correlate its optimistic local message with the canonical
    entry in scene history.

    .implements: rest-api-post-message
    """

    scene_id: EntityId
    """server-message-accepted-scene-id: scene this message was appended to (echoes the URL path)."""

    index: int
    """server-message-accepted-index: 0-based position in the scene's message history."""


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
    """Yield SSE bytes from a queue of `EntityChanged` events.

    rest-api-events-yield + sse-dataflow-event: emits each dequeued event as
    `event: entity_changed\\ndata: <json>\\n\\n`.
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
            if isinstance(event, EntityChanged):
                # events-subscription: serialize the in-process @dataclass
                # event to the wire shape — entity reference becomes id,
                # attributes pass through.
                payload = {
                    "entity_id": event.entity.id,
                    "attributes": list(event.attributes),
                }
                data = json.dumps(payload)
            else:
                data = json.dumps(event)
            yield f"event: entity_changed\ndata: {data}\n\n".encode("utf-8")
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
            # rest-api-post-dispatch: construct Message(sender, body), call
            # scene.append (per events-dataflow), return assigned (scene_id, index).
            # Reactions (npc cycle, SSE delivery) are listener-driven — the
            # POST handler does not await them.
            msg = Message(sender=sender, body=body.body)
            index = scene.append(msg)
            # rest-api-post-returns: 201 + MessageAccepted{scene_id, index}.
            return MessageAccepted(scene_id=scene.id, index=index)

        # rest-api-get-entity-events: GET /api/campaigns/{cid}/entities/{eid}/events
        @app.get("/api/campaigns/{cid}/entities/{entity_id}/events")
        async def get_entity_events(
            cid: str, entity_id: str, request: Request
        ) -> Response:
            """Per-entity SSE stream (per events.md). Resolves the campaign
            and entity, routes the queue subscription through the
            current-user's UserActor (per sse-dataflow-accept), yields each
            EntityChanged as `event: entity_changed\\ndata: …\\n\\n`, calls
            unsubscribe in finally on disconnect.
            """
            # rest-api-events-503.
            self._require_serving()
            # rest-api-events-404: campaign or entity unknown.
            campaign = self.campaigns.get(cid)
            if campaign is None:
                raise HTTPException(status_code=404, detail="campaign not found")
            entity = campaign.factory.get(entity_id)
            if entity is None:
                raise HTTPException(status_code=404, detail="entity not found")
            # rest-api-events-accept: route the queue through the user's actor.
            queue: asyncio.Queue = asyncio.Queue()
            user_id = App._current_user()
            user_actor = App.get_actor(user_id)
            user_actor.subscribe_to(entity, queue)

            # rest-api-events-cleanup: on disconnect, unsubscribe.
            def _on_close() -> None:
                user_actor.unsubscribe_from(entity, queue)

            return StreamingResponse(
                _sse_event_stream(queue, request, _on_close),
                media_type="text/event-stream",
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
    def run(cls, config_dir: str = "configs/") -> None:
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
          `0.0.0.0:8000`.

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


def main() -> None:
    """server-main: CLI entry point for the `sidestage` console script.

    Parses `--config` and runs `App.run(...)`. Typically invoked via
    `just run` (which also brings up the Vite dev server).

    .implements: cuj-startup-launch
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/")
    args = parser.parse_args()
    App.run(args.config)
