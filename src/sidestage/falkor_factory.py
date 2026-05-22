"""falkor_factory: FalkorDBLite-backed `EntityFactory`.

Per [[specs/persistence.md]]. Stores entity state in an embedded
FalkorDB graph: nodes (with their scalar Model fields as properties)
plus Cypher relationships derived from any field typed
`list[EntityId]`.

The factory does NOT know that messages exist. Scene owns its own
message persistence via the Redis stream (reached through
`campaign.db_handle.client`) — see `scene.py`. The annotation-driven
rule here ("scalars → property, `list[EntityId]` → edges, anything
else → skip") naturally leaves `list[Message]` to Scene.

Construction is per-campaign — the engine itself is the namespace.
The graph name is `"world"`; stream keys (managed by Scene) are
namespace-free.
"""

from __future__ import annotations

import logging
import typing
from typing import TYPE_CHECKING, Any

from redislite import FalkorDB

from sidestage.character import Character
from sidestage.entity import Entity, EntityFactory, EntityId, EntityType
from sidestage.scene import Scene, SimpleScene

if TYPE_CHECKING:
    from sidestage.campaign import Campaign


logger = logging.getLogger(__name__)


GRAPH_NAME = "world"


# Fields the factory never touches:
#   - "id" — node identity, written as the MERGE key
_SKIP_FIELDS = frozenset({"id"})


def _is_entity_id_list(annotation: Any) -> bool:
    """True when the annotation is `list[EntityId]` (the convention this
    factory translates into graph relationships).

    .implements: persistence-graph-edges-detection
    """
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    return origin is list and len(args) == 1 and args[0] is EntityId


_NOT_SCALAR = object()


def _to_scalar(value: Any) -> Any:
    """Coerce a Model field value into a Cypher-storable scalar, or
    return the `_NOT_SCALAR` sentinel if it isn't storable as a single
    property.

    Cypher accepts strings, ints, floats, bools (and arrays of those).
    Enums serialise as their string value; `EntityId` is already a str
    at runtime; Pydantic `Literal` values are just strings/ints.
    """
    if isinstance(value, EntityType):
        return value.value
    if isinstance(value, str | int | float | bool):
        return value
    return _NOT_SCALAR


def _edge_label(field_name: str) -> str:
    """Derive the Cypher relationship label from a Model field name.

    .implements: persistence-graph-edges-label
    """
    return field_name.upper()


def _node_label(entity_type: EntityType) -> str:
    """The subclass label that complements `:Entity` on the node."""
    # EntityType.SCENE → "Scene", EntityType.CHARACTER → "Character"
    return entity_type.value.capitalize()


_LABEL_TO_ENTITY_CLS: dict[str, type[Entity]] = {
    "Character": Character,
    "Scene": SimpleScene,
    "Entity": Entity,
}

_LABEL_TO_MODEL_CLS: dict[str, type[Entity.Model]] = {
    "Character": Character.Model,
    "Scene": Scene.Model,
    "Entity": Entity.Model,
}


def _classes_from_labels(labels: list[str]) -> tuple[type[Entity], type[Entity.Model]]:
    """Pick the Python concrete class and its Model from the Cypher
    labels on a node. Discrimination is by label, not by the `type`
    property (per `persistence-graph-class-discrimination`).
    """
    for label in labels:
        if label == "Entity":
            continue
        cls = _LABEL_TO_ENTITY_CLS.get(label)
        model = _LABEL_TO_MODEL_CLS.get(label)
        if cls is not None and model is not None:
            return cls, model
    return Entity, Entity.Model


class FalkorEntityFactory(EntityFactory):
    """falkor-entity-factory: FalkorDBLite-backed `EntityFactory`.

    .implements: entity-factory-impl, persistence-engine-redislite
    """

    def __init__(self, falkor: FalkorDB) -> None:
        self._falkor = falkor
        self._graph = falkor.select_graph(GRAPH_NAME)
        self._cache: dict[str, Entity] = {}
        self._campaign: Campaign | None = None

    # ---- duck-typed Campaign coupling --------------------------------

    @property
    def db_handle(self) -> FalkorDB:
        """Public seam for entities that need DB access (notably Scene
        for its message stream). Exposed via `Campaign.db_handle`.

        .implements: persistence-campaign-db-handle
        """
        return self._falkor

    def set_campaign(self, campaign: Campaign) -> None:
        """Stash the Campaign reference for wrapper construction at
        rehydration time. Called by `Campaign.__init__` via duck-typing.
        """
        self._campaign = campaign

    def load_existing(self) -> None:
        """Walk the graph in dependency order and construct all wrappers.

        Characters land in the cache first so that `SimpleScene.__init__`
        can resolve `scene.characters` ids via `campaign.get(id)` at the
        moment the scene wrapper is constructed.

        Idempotent — calling twice doesn't re-construct cached wrappers.
        Called by `Campaign.open` via duck-typing.

        .implements: persistence-startup
        """
        for label in ("Character", "Scene"):
            result = self._graph.query(
                f"MATCH (n:{label}) RETURN n.id",
            )
            for row in result.result_set:
                eid = row[0]
                if eid not in self._cache:
                    self._hydrate(eid)

    # ---- entity surface (the ABC contract) ---------------------------

    def get(self, id: str) -> Entity | None:
        cached = self._cache.get(id)
        if cached is not None:
            return cached
        return self._hydrate(id)

    def add(self, entity: Entity) -> None:
        """MERGE `entity` into the graph: scalar Model fields become node
        properties, `list[EntityId]` fields become graph relationships.
        Non-scalar fields (`list[Message]`) are skipped — the entity
        owns persistence for those.

        .implements: persistence-cypher-add, persistence-graph-edges-merge
        """
        model = entity.model
        model_cls = type(model)
        node_label = _node_label(entity.type)

        scalar_props: dict[str, Any] = {}
        edge_fields: dict[str, list[str]] = {}

        for field_name, field_info in model_cls.model_fields.items():
            if field_name in _SKIP_FIELDS:
                continue
            value = getattr(model, field_name)
            if _is_entity_id_list(field_info.annotation):
                edge_fields[field_name] = [str(v) for v in value]
                continue
            scalar = _to_scalar(value)
            if scalar is _NOT_SCALAR:
                # Non-scalar field (e.g. list[Message]) — entity owns
                # persistence for these; the factory skips them.
                continue
            scalar_props[field_name] = scalar

        # MERGE the node (idempotent — re-import is safe).
        self._graph.query(
            f"MERGE (n:Entity:{node_label} {{id: $id}}) SET n += $props",
            {"id": str(entity.id), "props": scalar_props},
        )

        # MERGE outgoing relationships. For idempotence across re-imports,
        # drop the existing edges of the given kind first; this keeps the
        # graph in sync if the source list was edited.
        for field_name, targets in edge_fields.items():
            label = _edge_label(field_name)
            self._graph.query(
                f"MATCH (s:Entity {{id: $sid}})-[r:{label}]->() DELETE r",
                {"sid": str(entity.id)},
            )
            for target in targets:
                self._graph.query(
                    f"MATCH (s:Entity {{id: $sid}}), (t:Entity {{id: $tid}}) "
                    f"MERGE (s)-[:{label}]->(t)",
                    {"sid": str(entity.id), "tid": target},
                )

        self._cache[entity.id] = entity

    def delete(self, id: str) -> None:
        self._graph.query(
            "MATCH (n:Entity {id: $id}) DETACH DELETE n",
            {"id": id},
        )
        self._cache.pop(id, None)

    def entities(self) -> typing.Iterable[Entity]:
        return self._cache.values()

    # ---- rehydration -------------------------------------------------

    def _hydrate(self, eid: str) -> Entity | None:
        """Build a wrapper for `eid` from the graph and cache it."""
        if self._campaign is None:
            raise RuntimeError(
                "FalkorEntityFactory.set_campaign was not called before "
                "rehydration; Campaign.__init__ does this via duck-typing"
            )
        result = self._graph.query(
            "MATCH (n:Entity {id: $id}) RETURN n",
            {"id": eid},
        )
        if not result.result_set:
            return None
        node = result.result_set[0][0]
        props: dict[str, Any] = dict(node.properties)

        entity_cls, model_cls = _classes_from_labels(list(node.labels))

        # Reconstruct `list[EntityId]` fields from outgoing relationships.
        for field_name, field_info in model_cls.model_fields.items():
            if _is_entity_id_list(field_info.annotation):
                label = _edge_label(field_name)
                edge_result = self._graph.query(
                    f"MATCH (:Entity {{id: $sid}})-[:{label}]->(t:Entity) "
                    f"RETURN t.id ORDER BY t.id",
                    {"sid": eid},
                )
                props[field_name] = [EntityId(row[0]) for row in edge_result.result_set]

        model = model_cls.model_validate(props)
        entity = entity_cls(model, self._campaign)
        self._cache[eid] = entity
        return entity
