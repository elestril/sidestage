from __future__ import annotations

from abc import abstractmethod
from typing import Optional, Self

from sidestage.entity import Entity, EntityId, EntityType
from sidestage.message import Message
from sidestage.character import Character


class Scene(Entity):
    class Model(Entity.Model):
        active_character_ids: list[str] = []

    @classmethod
    def deserialize(cls, model: Scene.Model) -> Self:
        instance = cls.__new__(cls)
        object.__setattr__(instance, "id", model.id)
        object.__setattr__(instance, "_loaded", True)
        object.__setattr__(instance, "name", model.name)
        object.__setattr__(instance, "type", EntityType.SCENE)
        object.__setattr__(instance, "body", model.body)
        object.__setattr__(instance, "active_character_ids", model.active_character_ids)
        object.__setattr__(instance, "characters", [])
        object.__setattr__(instance, "messages", [])
        return instance

    def serialize(self) -> Scene.Model:
        return self.Model(
            id=self.id,
            name=self.name,
            type=self.type,
            body=self.body,
            active_character_ids=self.active_character_ids,
        )

    @abstractmethod
    def dispatch(self, message: Message) -> None:
        pass


class SimpleScene(Scene):
    def dispatch(self, message: Message) -> None:
        self.messages.append(message)
        response: Optional[Message] = None
        for character in self.characters:
            if character is not message.sender:
                response = character.respond(message)
                break
        if response is not None:
            self.messages.append(response)
            message.sender.respond(response)
