from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sidestage.character import Character
    from sidestage.message import Message


class Actor(ABC):
    @abstractmethod
    def is_human(self) -> bool:
        pass

    @abstractmethod
    def respond(self, message: Message, character: Character) -> Optional[Message]:
        pass


class StubActor(Actor):
    def is_human(self) -> bool:
        return False

    def respond(self, message: Message, character: Character) -> Optional[Message]:
        if not message.sender.has_human_actor():
            return None
        from sidestage.message import Message as Msg
        return Msg(sender=character, body="Hello User!")
