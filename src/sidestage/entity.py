from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import NewType, Optional, Self

from pydantic import BaseModel


EntityId = NewType("EntityId", str)


class EntityType(str, Enum):
    CHARACTER = "character"
    SCENE = "scene"
    ENTITY = "entity"


class UnresolvedEntityError(Exception):
    pass


_GHOST_SAFE = {"id", "_loaded"}


class Entity:
    class Model(BaseModel):
        id: EntityId
        name: str
        type: EntityType
        body: str

    def __init__(self, id: EntityId, *, _loaded: bool = False) -> None:
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "_loaded", _loaded)

    def __getattribute__(self, name: str):
        if name in _GHOST_SAFE or name.startswith("__"):
            return object.__getattribute__(self, name)
        loaded = object.__getattribute__(self, "_loaded")
        if not loaded:
            raise UnresolvedEntityError(
                f"Entity '{object.__getattribute__(self, 'id')}' is not resolved"
            )
        return object.__getattribute__(self, name)

    def serialize(self) -> Entity.Model:
        return self.Model(
            id=self.id,
            name=self.name,
            type=self.type,
            body=self.body,
        )

    @classmethod
    def deserialize(cls, model: Entity.Model) -> Self:
        instance = cls.__new__(cls)
        object.__setattr__(instance, "id", model.id)
        object.__setattr__(instance, "_loaded", True)
        object.__setattr__(instance, "name", model.name)
        object.__setattr__(instance, "type", model.type)
        object.__setattr__(instance, "body", model.body)
        return instance


class EntityFactory(ABC):
    @abstractmethod
    def get(self, id: str) -> Optional[Entity]:
        pass

    @abstractmethod
    def add(self, entity: Entity) -> None:
        pass

    @abstractmethod
    def ghost(self, id: str, type: EntityType) -> Entity:
        pass


class DictEntityFactory(EntityFactory):
    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}

    def get(self, id: str) -> Optional[Entity]:
        return self._entities.get(id)

    def add(self, entity: Entity) -> None:
        existing = self._entities.get(entity.id)
        if existing is not None and not object.__getattribute__(existing, "_loaded"):
            object.__setattr__(existing, "_loaded", True)
            for attr in ("name", "type", "body"):
                object.__setattr__(existing, attr, object.__getattribute__(entity, attr))
            for attr in self._extra_attrs(entity):
                object.__setattr__(existing, attr, object.__getattribute__(entity, attr))
        else:
            object.__setattr__(entity, "_loaded", True)
            self._entities[entity.id] = entity

    def ghost(self, id: str, type: EntityType) -> Entity:
        if id in self._entities:
            return self._entities[id]
        ghost = Entity.__new__(Entity)
        object.__setattr__(ghost, "id", EntityId(id))
        object.__setattr__(ghost, "_loaded", False)
        self._entities[id] = ghost
        return ghost

    def _extra_attrs(self, entity: Entity) -> list[str]:
        return []
