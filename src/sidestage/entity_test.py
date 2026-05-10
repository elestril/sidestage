from __future__ import annotations

import pytest
from sidestage.entity import (
    DictEntityFactory,
    Entity,
    EntityId,
    EntityType,
    UnresolvedEntityError,
)


def make_entity(id: str = "e1", name: str = "Test", body: str = "body") -> Entity:
    model = Entity.Model(id=EntityId(id), name=name, type=EntityType.ENTITY, body=body)
    return Entity.deserialize(model)


class TestEntityId:
    def test_newtype_is_str(self):
        eid = EntityId("abc")
        assert isinstance(eid, str)
        assert eid == "abc"


class TestEntityGhost:
    def test_ghost_safe_id(self):
        factory = DictEntityFactory()
        ghost = factory.ghost("g1", EntityType.ENTITY)
        assert ghost.id == "g1"

    def test_ghost_safe_loaded(self):
        factory = DictEntityFactory()
        ghost = factory.ghost("g1", EntityType.ENTITY)
        assert ghost._loaded is False

    def test_ghost_unresolved_raises(self):
        factory = DictEntityFactory()
        ghost = factory.ghost("g1", EntityType.ENTITY)
        with pytest.raises(UnresolvedEntityError):
            _ = ghost.name

    def test_ghost_unresolved_body_raises(self):
        factory = DictEntityFactory()
        ghost = factory.ghost("g1", EntityType.ENTITY)
        with pytest.raises(UnresolvedEntityError):
            _ = ghost.body


class TestEntityModel:
    def test_deserialize_returns_entity(self):
        entity = make_entity()
        assert isinstance(entity, Entity)

    def test_deserialize_sets_loaded(self):
        entity = make_entity()
        assert entity._loaded is True

    def test_deserialize_fields(self):
        entity = make_entity(id="abc", name="Foo", body="bar")
        assert entity.id == "abc"
        assert entity.name == "Foo"
        assert entity.body == "bar"
        assert entity.type == EntityType.ENTITY

    def test_serialize_returns_model(self):
        entity = make_entity(id="abc", name="Foo", body="bar")
        model = entity.serialize()
        assert isinstance(model, Entity.Model)
        assert model.id == "abc"
        assert model.name == "Foo"
        assert model.body == "bar"

    def test_serialize_ghost_raises(self):
        factory = DictEntityFactory()
        ghost = factory.ghost("g1", EntityType.ENTITY)
        with pytest.raises(UnresolvedEntityError):
            ghost.serialize()


class TestDictEntityFactory:
    def test_get_returns_none_for_missing(self):
        factory = DictEntityFactory()
        assert factory.get("missing") is None

    def test_add_and_get(self):
        factory = DictEntityFactory()
        entity = make_entity("e1")
        factory.add(entity)
        assert factory.get("e1") is entity

    def test_add_sets_loaded(self):
        factory = DictEntityFactory()
        entity = make_entity("e1")
        factory.add(entity)
        result = factory.get("e1")
        assert result._loaded is True

    def test_add_hydrates_ghost(self):
        factory = DictEntityFactory()
        ghost = factory.ghost("e1", EntityType.ENTITY)
        assert ghost._loaded is False

        entity = make_entity("e1")
        factory.add(entity)

        assert ghost._loaded is True
        assert ghost.name == "Test"

    def test_ghost_creates_unresolved(self):
        factory = DictEntityFactory()
        ghost = factory.ghost("g1", EntityType.ENTITY)
        assert ghost._loaded is False
        assert ghost.id == "g1"

    def test_ghost_returns_same_instance(self):
        factory = DictEntityFactory()
        g1 = factory.ghost("g1", EntityType.ENTITY)
        g2 = factory.ghost("g1", EntityType.ENTITY)
        assert g1 is g2

    def test_add_registers_new_entity(self):
        factory = DictEntityFactory()
        entity = make_entity("e1")
        factory.add(entity)
        assert factory.get("e1") is entity
