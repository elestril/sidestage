from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from sidestage.actor import Actor
from sidestage.campaign import Campaign
from sidestage.character import Character
from sidestage.entity import EntityId
from sidestage.message import Message
from sidestage.scene import Scene


class ServerState(Enum):
    LOADING = "loading"
    SERVING = "serving"


class InitEvent(BaseModel):
    type: Literal["init"] = "init"
    scene_id: EntityId
    characters: list[Character.Model]
    player_character_ids: list[EntityId]


class MessageEvent(BaseModel):
    type: Literal["message"] = "message"
    sender_id: EntityId
    body: str


class UserActor(Actor):
    def __init__(self, websocket: WebSocket, scene: Scene, character: Character) -> None:
        self.websocket = websocket
        self.scene = scene
        self._character = character

    def is_human(self) -> bool:
        return True

    async def run(self) -> None:
        async for data in self.websocket.iter_json():
            event = MessageEvent.model_validate(data)
            message = Message(sender=self._character, body=event.body)
            self.scene.dispatch(message)

    def respond(self, message: Message, character: Character) -> Optional[Message]:
        import asyncio
        event = MessageEvent(sender_id=message.sender.id, body=message.body)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.websocket.send_json(event.model_dump()))
        except RuntimeError:
            pass
        return None


_HTML = """<!DOCTYPE html>
<html>
<head><title>Sidestage</title></head>
<body><h1>Sidestage Chat</h1></body>
</html>
"""


class App:
    def __init__(self, config_dir: str = "config/") -> None:
        self.config_dir = config_dir
        self.campaign: Optional[Campaign] = None
        self.state: ServerState = ServerState.LOADING
        self._fastapi = FastAPI()
        self._setup_routes()

    def _setup_routes(self) -> None:
        app = self._fastapi

        @app.get("/")
        async def root():
            return HTMLResponse(_HTML)

        @app.websocket("/ws")
        async def ws_endpoint(websocket: WebSocket):
            if self.state == ServerState.LOADING:
                await websocket.close(code=1013)
                return

            await websocket.accept()

            scene = self.campaign.scene
            human_char = None
            for c in scene.characters:
                if c.actor_type == "user":
                    human_char = c
                    break

            user_actor = UserActor(websocket=websocket, scene=scene, character=human_char)
            if human_char is not None:
                object.__setattr__(human_char, "_actor", user_actor)

            init_event = InitEvent(
                scene_id=scene.id,
                characters=[c.serialize() for c in scene.characters],
                player_character_ids=[c.id for c in scene.characters if c.actor_type == "user"],
            )
            await websocket.send_json(init_event.model_dump())

            try:
                await user_actor.run()
            except WebSocketDisconnect:
                pass
            finally:
                if human_char is not None:
                    from sidestage.actor import StubActor
                    object.__setattr__(human_char, "_actor", StubActor())

    @classmethod
    def run(cls, config_dir: str = "configs/") -> None:
        instance = cls(config_dir=config_dir)
        instance.state = ServerState.LOADING
        campaign_path = next(Path(config_dir).iterdir())
        instance.campaign = Campaign.load(campaign_path)
        instance.state = ServerState.SERVING
        uvicorn.run(instance._fastapi, host="0.0.0.0", port=8000)


def _create_app() -> FastAPI:
    import os
    config_dir = os.environ.get("SIDESTAGE_CONFIG", "configs/")
    instance = App(config_dir=config_dir)
    instance.state = ServerState.LOADING
    campaign_path = next(Path(config_dir).iterdir())
    instance.campaign = Campaign.load(campaign_path)
    instance.state = ServerState.SERVING
    return instance._fastapi


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    if args.reload:
        import os
        os.environ["SIDESTAGE_CONFIG"] = args.config
        uvicorn.run("sidestage.server:_create_app", factory=True, host="0.0.0.0", port=8000, reload=True)
    else:
        App.run(args.config)
