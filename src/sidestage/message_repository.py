from typing import Protocol

from sidestage.ids import SceneId
from sidestage.message import Message


class MessageRepository(Protocol):
    async def append(self, message: Message) -> None: ...
    async def get_by_scene(self, scene_id: SceneId) -> list[Message]: ...


class InMemoryMessageRepository:
    def __init__(self) -> None:
        self._messages: list[Message] = []

    async def append(self, message: Message) -> None:
        self._messages.append(message)

    async def get_by_scene(self, scene_id: SceneId) -> list[Message]:
        return [m for m in self._messages if m.scene_id == scene_id]
