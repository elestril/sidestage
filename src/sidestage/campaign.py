from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import frontmatter
import yaml
from pydantic import BaseModel

from sidestage.character import Character
from sidestage.entity import (
    DictEntityFactory,
    Entity,
    EntityFactory,
    EntityId,
    EntityType,
)
from sidestage.scene import Scene, SimpleScene

logger = logging.getLogger(__name__)


class CampaignConfig(BaseModel):
    """campaign-config: top-level campaign settings stored in `config.yaml`.

    .implements: campaign-config
    """

    name: str
    """campaign-config-name: Display name of the campaign.

    .implements: campaign-config-name
    """

    default_scene_id: EntityId | None = None
    """campaign-config-default-scene: Optional `EntityId` of the scene the
    client should load by default if it has no other navigation context.

    .implements: campaign-config-default-scene
    """


class Campaign:
    """campaign-class: The core world container.

    Holds every loaded Entity directly and exposes the architectural surface
    (`get` / `add` / `delete`) per `entity-campaign`. The storage backing is
    an internal `EntityFactory` instance — today `DictEntityFactory`
    (in-memory), but the seam exists for future persistent backends.

    .implements: cuj-startup-load, entity-campaign
    """

    class Model(BaseModel):
        """campaign-model: Canonical serialised form for a Campaign. Carries
        `name` and `default_scene_id`. Same one-model rule as Entity: no
        parallel `CampaignResponse`.

        .implements: campaign-model
        """

        name: str
        default_scene_id: EntityId | None

    name: str
    """campaign-name: Display name of the campaign; sourced from `config.yaml`.

    .implements: campaign-config-name
    """

    default_scene_id: EntityId | None
    """campaign-default-scene-id: Optional `EntityId` hint for the client to
    load if it has no other navigation context. NOT a Scene reference —
    resolves via `self.get(self.default_scene_id)` at use time. May be
    `None` if `config.yaml` omits the field.

    .implements: campaign-config-default-scene
    """

    _store: EntityFactory
    """campaign-store: Private storage layer for the Campaign's entities.
    Concrete impl is `DictEntityFactory`; the abstraction is the seam for
    future persistent backends. Callers go through the public
    `get/add/delete` surface — `_store` is not part of the public Campaign
    API.

    .implements: entity-campaign
    """

    def __init__(
        self,
        *,
        name: str,
        default_scene_id: EntityId | None = None,
        store: EntityFactory | None = None,
    ) -> None:
        self.name = name
        self.default_scene_id = default_scene_id
        self._store = store if store is not None else DictEntityFactory()
        self._closed: bool = False
        # FalkorEntityFactory needs a backreference to this Campaign to
        # construct Entity wrappers on rehydration. In-memory factories
        # don't — so we duck-type instead of putting the hook on the
        # base `EntityFactory` ABC.
        set_campaign = getattr(self._store, "set_campaign", None)
        if callable(set_campaign):
            set_campaign(self)

    # ----------------------------------------------------------------
    # Closed-state fencing
    # ----------------------------------------------------------------

    def _ensure_open(self) -> None:
        """Raise if any public surface is used after `close()`.

        .implements: persistence-engine-shutdown
        """
        if self._closed:
            raise RuntimeError(f"Campaign {self.name!r} is closed")

    @property
    def db_handle(self):
        """campaign-db-handle: Public seam for entities that need DB
        access (e.g. Scene's message stream). Returns the store's
        underlying FalkorDB handle, or `None` when the campaign runs
        in-memory (DictEntityFactory has no `db_handle` attribute).

        Raises if the campaign has been closed.

        .implements: persistence-campaign-db-handle
        """
        self._ensure_open()
        return getattr(self._store, "db_handle", None)

    # ----------------------------------------------------------------
    # Lifecycle — Campaign owns its factory, which owns any engine.
    # ----------------------------------------------------------------

    def close(self) -> None:
        """campaign-close: Release resources held by this Campaign.

        Idempotent — short-circuits on the second call. Delegates to
        `self._store.close()` if the factory has one
        (`FalkorEntityFactory` shuts the embedded redis subprocess
        down here; `DictEntityFactory` has no `close` attribute so
        the duck-typed call is skipped).

        After `close()`, every public method raises `RuntimeError` via
        `_ensure_open` — closed is a real state, not a half-state.

        .implements: persistence-engine-shutdown
        """
        if self._closed:
            return
        self._closed = True
        close = getattr(self._store, "close", None)
        if callable(close):
            close()

    def __enter__(self) -> Campaign:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ----------------------------------------------------------------
    # Architectural surface: get / add / delete
    # ----------------------------------------------------------------

    def get(self, entity_id: str) -> Entity | None:
        """Resolve an entity by id; `None` if unknown.

        .implements: entity-campaign
        """
        self._ensure_open()
        return self._store.get(entity_id)

    def add(self, entity: Entity) -> None:
        """Register an entity with this Campaign.

        .implements: entity-campaign
        """
        self._ensure_open()
        self._store.add(entity)

    def delete(self, entity_id: str) -> None:
        """Remove an entity by id; no-op if unknown.

        .implements: entity-campaign
        """
        self._ensure_open()
        self._store.delete(entity_id)

    # ----------------------------------------------------------------
    # Domain helpers
    # ----------------------------------------------------------------

    def scenes(self) -> list[Scene]:
        """campaign-scenes: All scenes in this campaign.

        .implements: rest-api-get-scenes
        """
        self._ensure_open()
        return [e for e in self._store.entities() if isinstance(e, Scene)]

    def scene(self, scene_id: EntityId) -> Scene | None:
        """campaign-scene: Look up a scene by id; `None` if unknown or if
        the id resolves to a non-Scene entity.

        .implements: rest-api-get-scene
        """
        # _ensure_open via self.get below; no duplicate check needed.
        entity = self.get(scene_id)
        if entity is None or not isinstance(entity, Scene):
            return None
        return entity

    def to_model(self) -> Campaign.Model:
        """campaign-to-model: Build the canonical serialised form.

        .implements: campaign-model
        """
        self._ensure_open()
        return Campaign.Model(
            name=self.name,
            default_scene_id=self.default_scene_id,
        )

    # ----------------------------------------------------------------
    # Load / open / export — see [[persistence]] startup contract
    # ----------------------------------------------------------------

    @classmethod
    def _read_config(cls, path: Path) -> CampaignConfig:
        """Read `<path>/config.yaml` into a `CampaignConfig`. Shared by
        both `import_from_disk` and `open`."""
        config_data = yaml.safe_load((path / "config.yaml").read_text())
        return CampaignConfig(**config_data)

    @classmethod
    def open(cls, path: Path, store: EntityFactory) -> Campaign:
        """campaign-open: Construct a Campaign assuming `store` is already
        populated (typically by `FalkorEntityFactory` against an existing
        graph). Reads `<path>/config.yaml` for campaign metadata; does NOT
        read entity `.md` files — entity state comes from the store. After
        construction, calls `store.load_existing()` so persistent factories
        can hydrate their wrapper caches from the graph.

        Used when the campaign's graph already exists
        (per [[persistence]] `persistence-startup-import-on-empty`).

        .implements: campaign-open, persistence-startup
        """
        config = cls._read_config(path)
        default_scene_id = (
            EntityId(config.default_scene_id)
            if config.default_scene_id is not None
            else None
        )
        campaign = cls(
            name=config.name,
            default_scene_id=default_scene_id,
            store=store,
        )
        # Persistent factories (FalkorEntityFactory) hydrate their wrapper
        # cache from the underlying store. In-memory factories don't need
        # this hook — duck-typed for the same reason as bind_campaign.
        load = getattr(store, "load_existing", None)
        if callable(load):
            load()
        return campaign

    @classmethod
    def import_from_disk(
        cls, path: Path, store: EntityFactory | None = None
    ) -> Campaign:
        """campaign-import-from-disk: Single-pass load from disk into an
        (empty) `store`. Default store is `DictEntityFactory()` for unit
        tests; production passes a `FalkorEntityFactory` so the load
        materialises in the graph.

        Walks the tree in dependency order (characters before scenes), so
        cross-entity references resolve at construction time via
        `campaign.get(id)`. Each entity is constructed by calling its
        class on the parsed Model.

        - campaign-import-config: Reads `<path>/config.yaml`.
        - campaign-import-construct: Each entity is built via `Cls(model,
          campaign)` and registered with `campaign.add(entity)`.
        - campaign-import-default-scene-id: Stored as the navigation hint.
        - campaign-import-order: Characters before scenes. Scenes' cross-
          refs resolve at construction.

        .implements: persistence-import-dataflow,
            persistence-import-dataflow-config,
            persistence-import-dataflow-walk,
            persistence-import-dataflow-add
        """
        config = cls._read_config(path)
        default_scene_id = (
            EntityId(config.default_scene_id)
            if config.default_scene_id is not None
            else None
        )
        campaign = cls(
            name=config.name,
            default_scene_id=default_scene_id,
            store=store,
        )

        # Characters first — scene cross-refs resolve against them.
        chars_dir = path / "characters"
        if chars_dir.exists():
            for md_file in chars_dir.glob("*.md"):
                char_id = md_file.stem
                post = frontmatter.load(str(md_file))
                model = Character.Model.model_validate(
                    {
                        "id": EntityId(char_id),
                        "name": post.metadata.get("name", char_id),
                        "type": EntityType.CHARACTER,
                        "body": post.content,
                        "owner": post.metadata.get("owner", "stub"),
                    }
                )
                campaign.add(Character(model, campaign))

        scenes_dir = path / "scenes"
        if scenes_dir.exists():
            for md_file in scenes_dir.glob("*.md"):
                scene_id = md_file.stem
                post = frontmatter.load(str(md_file))
                raw_chars = post.metadata.get("characters") or []
                if not isinstance(raw_chars, list):
                    raise ValueError(
                        f"{md_file}: `characters` must be a list, "
                        f"got {type(raw_chars).__name__}"
                    )
                char_ids = [EntityId(str(cid)) for cid in raw_chars]
                model = SimpleScene.Model.model_validate(
                    {
                        "id": EntityId(scene_id),
                        "name": post.metadata.get("name", scene_id),
                        "type": EntityType.SCENE,
                        "body": post.content,
                        "characters": char_ids,
                    }
                )
                campaign.add(SimpleScene(model, campaign))

        return campaign

    def export(self, path: Path) -> None:
        """campaign-export: Regenerate the markdown directory canonically
        from the in-memory + store state.

        Writes `config.yaml`, then for each entity in
        `self._store.entities()` writes `<kind>/<id>.md` with frontmatter
        (Model's intrinsic + edge fields) + body. Chat history is NOT
        exported — it lives in per-scene Redis streams.

        First-export diff noise against hand-written markdown is accepted
        (per [[persistence]] `persistence-export-dataflow-canonical`).

        .implements: persistence-export-dataflow,
            persistence-export-dataflow-config,
            persistence-export-dataflow-nodes
        """
        path.mkdir(parents=True, exist_ok=True)
        # campaign-export-config
        config = CampaignConfig(
            name=self.name,
            default_scene_id=self.default_scene_id,
        )
        config_dict: dict[str, Any] = {"name": config.name}
        if config.default_scene_id is not None:
            config_dict["default_scene_id"] = config.default_scene_id
        (path / "config.yaml").write_text(yaml.safe_dump(config_dict, sort_keys=False))

        # Group entities by subdirectory based on their EntityType.
        by_dir: dict[str, list[Entity]] = {"characters": [], "scenes": []}
        for entity in self._store.entities():
            if entity.type == EntityType.CHARACTER:
                by_dir["characters"].append(entity)
            elif entity.type == EntityType.SCENE:
                by_dir["scenes"].append(entity)
            # Other entity types are out of scope for this iteration.

        for subdir, entities in by_dir.items():
            if not entities:
                continue
            (path / subdir).mkdir(exist_ok=True)
            for entity in entities:
                meta: dict[str, Any] = {}
                model_fields = type(entity.model).model_fields
                for field_name in model_fields:
                    # `id`, `type`, `body` live elsewhere (filename, dir,
                    # body); skip them in frontmatter.
                    if field_name in ("id", "type", "body"):
                        continue
                    value = getattr(entity.model, field_name)
                    # EntityList serialises as a plain list of strings.
                    if isinstance(value, list):
                        meta[field_name] = list(value)
                    else:
                        meta[field_name] = value
                post = frontmatter.Post(content=entity.body, **meta)
                # frontmatter.dumps emits the YAML header + body.
                (path / subdir / f"{entity.id}.md").write_text(
                    frontmatter.dumps(post) + "\n"
                )
