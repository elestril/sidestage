from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Self

from sidestage.entity import Entity, EntityId, EntityType

if TYPE_CHECKING:
    from sidestage.actor import Actor
    from sidestage.message import Message


class Character(Entity):
    class Model(Entity.Model):
        actor_type: str
        model: Optional[str] = None

    def __init__(self, id: EntityId, *, _loaded: bool = False) -> None:
        super().__init__(id, _loaded=_loaded)

    @classmethod
    def deserialize(cls, model: Character.Model) -> Self:
        instance = cls.__new__(cls)
        object.__setattr__(instance, "id", model.id)
        object.__setattr__(instance, "_loaded", True)
        object.__setattr__(instance, "name", model.name)
        object.__setattr__(instance, "type", EntityType.CHARACTER)
        object.__setattr__(instance, "body", model.body)
        object.__setattr__(instance, "actor_type", model.actor_type)
        object.__setattr__(instance, "model", model.model)
        from sidestage.actor import StubActor
        object.__setattr__(instance, "_actor", StubActor())
        return instance

    def serialize(self) -> Character.Model:
        return self.Model(
            id=self.id,
            name=self.name,
            type=self.type,
            body=self.body,
            actor_type=self.actor_type,
            model=self.model,
        )

    def respond(self, message: Message) -> Optional[Message]:
        return self._actor.respond(message, self)

    def has_human_actor(self) -> bool:
        return self._actor.is_human()
