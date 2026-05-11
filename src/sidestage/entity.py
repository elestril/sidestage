from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import NewType, Optional, Self

from pydantic import BaseModel


EntityId = NewType("EntityId", str)
"""entity-id-newtype: All entity references use `EntityId` rather than bare
`str`, so the type checker distinguishes ids from arbitrary strings.

.implements: entity-id
"""


class EntityType(str, Enum):
    CHARACTER = "character"
    SCENE = "scene"
    ENTITY = "entity"


class UnresolvedEntityError(Exception):
    pass


_GHOST_SAFE = {"id", "_loaded"}


class Entity:
    """entity-class: The base object of Sidestage — every world thing (character,
    scene, location, item) is an Entity. All entities belong to a Campaign and
    are managed by an EntityFactory. Entities support lazy loading via the
    ghost pattern: an unresolved entity holds only its `id`; accessing any
    other field raises `UnresolvedEntityError` until the factory hydrates it.

    .implements: entity-impl
    """

    class Model(BaseModel):
        """entity-model: Inner Pydantic model defining the on-disk / on-wire
        schema for an Entity. Every concrete Entity subclass MUST implement
        its own `Model(Entity.Model)` adding subclass-specific fields. Without
        a `Model`, the entity cannot be loaded from disk or serialized to the
        wire.

        .implements: entity-impl
        """

        id: EntityId
        name: str
        type: EntityType
        body: str

    def __init__(self, id: EntityId, *, _loaded: bool = False) -> None:
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "_loaded", _loaded)

    def __getattribute__(self, name: str):
        """Ghost-pattern attribute access guard.

        - entity-ghost-safe: `id` and `_loaded` are accessible on unresolved
          entities.
        - entity-ghost-unresolved: Accessing any other field raises
          `UnresolvedEntityError` if `_loaded` is False.

        .implements: entity-impl
        """
        if name in _GHOST_SAFE or name.startswith("__"):
            return object.__getattribute__(self, name)
        loaded = object.__getattribute__(self, "_loaded")
        if not loaded:
            raise UnresolvedEntityError(
                f"Entity '{object.__getattribute__(self, 'id')}' is not resolved"
            )
        return object.__getattribute__(self, name)

    def serialize(self) -> Entity.Model:
        """Serialize this entity to its `Model`.

        - entity-serialize-fields: Returns `self.Model` populated from this
          entity's public fields.
        - entity-serialize-ghost-rejects: Raises `UnresolvedEntityError` if
          called on an unresolved ghost (enforced indirectly via the ghost
          attribute guard when reading `name`/`type`/`body`).

        .implements: entity-impl
        """
        return self.Model(
            id=self.id,
            name=self.name,
            type=self.type,
            body=self.body,
        )

    @classmethod
    def deserialize(cls, model: Entity.Model) -> Self:
        """Construct a hydrated entity from its `Model`.

        - entity-deserialize-returns: Returns an instance of `cls` (not
          `Entity`) populated from `model`.
        - entity-deserialize-loaded: Sets `_loaded = True` on the returned
          instance.

        .implements: entity-impl
        """
        instance = cls.__new__(cls)
        object.__setattr__(instance, "id", model.id)
        object.__setattr__(instance, "_loaded", True)
        object.__setattr__(instance, "name", model.name)
        object.__setattr__(instance, "type", model.type)
        object.__setattr__(instance, "body", model.body)
        return instance


class EntityFactory(ABC):
    """entity-factory: Abstract registry of every Entity in a Campaign,
    indexed by `EntityId`. Concrete factories back the registry with whatever
    storage suits the deployment (in-memory dict at load time, etc.).

    .implements: entity-factory-impl
    """

    @abstractmethod
    def get(self, id: str) -> Optional[Entity]:
        """Look up an entity by id.

        - entity-factory-get: Returns the entity for the given id, or None if
          unknown.

        .implements: entity-factory-impl
        """
        pass

    @abstractmethod
    def add(self, entity: Entity) -> None:
        """Register a hydrated entity in the factory.

        - entity-factory-add: Registers a hydrated entity; if a ghost with the
          same id exists, hydrates it in place.

        .implements: entity-factory-impl
        """
        pass

    @abstractmethod
    def ghost(self, id: str, type: EntityType) -> Entity:
        """Return (and register, if needed) an unresolved ghost for `id`.

        - entity-factory-ghost: Returns an unresolved ghost entity; creates
          and registers one if not yet known.

        .implements: entity-factory-impl
        """
        pass


class DictEntityFactory(EntityFactory):
    """dict-entity-factory: In-memory `EntityFactory` backed by
    `dict[str, Entity]`. Used at load time and as the default factory for
    a running Campaign.

    .implements: entity-factory-impl
    """

    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}

    def get(self, id: str) -> Optional[Entity]:
        """Look up an entity by id in the backing dict.

        - dict-factory-get: Returns entity from the dict, or None if not
          found.

        .implements: entity-factory-get
        """
        return self._entities.get(id)

    def add(self, entity: Entity) -> None:
        """Register `entity`, hydrating an existing ghost in place if present.

        - dict-factory-add: Stores entity in the dict, sets `_loaded = True`;
          hydrates existing ghost if present (copies `name`, `type`, `body`,
          and any subclass-specific extra attributes onto the ghost so that
          forward references already handed out remain valid).

        .implements: entity-factory-add
        """
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
        """Return an unresolved ghost for `id`, creating one if not yet known.

        - dict-factory-ghost: Creates an unresolved Entity with
          `_loaded = False` and stores it; subsequent calls with the same id
          return the same instance so all forward references share identity.

        .implements: entity-factory-ghost
        """
        if id in self._entities:
            return self._entities[id]
        ghost = Entity.__new__(Entity)
        object.__setattr__(ghost, "id", EntityId(id))
        object.__setattr__(ghost, "_loaded", False)
        self._entities[id] = ghost
        return ghost

    def _extra_attrs(self, entity: Entity) -> list[str]:
        return []
