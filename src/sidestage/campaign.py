from __future__ import annotations

import logging
from pathlib import Path

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

    # ----------------------------------------------------------------
    # Architectural surface: get / add / delete
    # ----------------------------------------------------------------

    def get(self, entity_id: str) -> Entity | None:
        """Resolve an entity by id; `None` if unknown.

        .implements: entity-campaign
        """
        return self._store.get(entity_id)

    def add(self, entity: Entity) -> None:
        """Register an entity with this Campaign.

        .implements: entity-campaign
        """
        self._store.add(entity)

    def delete(self, entity_id: str) -> None:
        """Remove an entity by id; no-op if unknown.

        .implements: entity-campaign
        """
        self._store.delete(entity_id)

    # ----------------------------------------------------------------
    # Domain helpers
    # ----------------------------------------------------------------

    def scenes(self) -> list[Scene]:
        """campaign-scenes: All scenes in this campaign.

        .implements: rest-api-get-scenes
        """
        return [e for e in self._store.entities() if isinstance(e, Scene)]

    def scene(self, scene_id: EntityId) -> Scene | None:
        """campaign-scene: Look up a scene by id; `None` if unknown or if
        the id resolves to a non-Scene entity.

        .implements: rest-api-get-scene
        """
        entity = self.get(scene_id)
        if entity is None or not isinstance(entity, Scene):
            return None
        return entity

    def to_model(self) -> Campaign.Model:
        """campaign-to-model: Build the canonical serialised form.

        .implements: campaign-model
        """
        return Campaign.Model(
            name=self.name,
            default_scene_id=self.default_scene_id,
        )

    # ----------------------------------------------------------------
    # Load
    # ----------------------------------------------------------------

    @classmethod
    def load(cls, path: Path) -> Campaign:
        """campaign-load: Single-pass load from disk.

        Walks the tree in dependency order (characters before scenes), so
        cross-entity references resolve at construction time via
        `campaign.get(id)`. Each entity is constructed by calling its
        class on the parsed Model.

        - campaign-load-config: Reads `<path>/config.yaml`.
        - campaign-load-construct: Each entity is built via `Cls(model,
          campaign)` and registered with `campaign.add(entity)`.
        - campaign-load-default-scene-id: Stored as the navigation hint.
        - campaign-load-order: Characters before scenes. Scenes' cross-refs
          resolve at construction.

        .implements: fs-dataflow-config, fs-dataflow-walk, fs-dataflow-classify,
            fs-dataflow-parse, fs-dataflow-deserialize, fs-dataflow-add,
            fs-dataflow-finalize
        """
        config_data = yaml.safe_load((path / "config.yaml").read_text())
        config = CampaignConfig(**config_data)

        default_scene_id = (
            EntityId(config.default_scene_id)
            if config.default_scene_id is not None
            else None
        )
        campaign = cls(
            name=config.name,
            default_scene_id=default_scene_id,
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
                raw_chars = (
                    post.metadata.get("character_ids")
                    or post.metadata.get("characters")
                    or []
                )
                if not isinstance(raw_chars, list):
                    raise ValueError(
                        f"{md_file}: `character_ids` must be a list, "
                        f"got {type(raw_chars).__name__}"
                    )
                char_ids = [EntityId(str(cid)) for cid in raw_chars]
                model = SimpleScene.Model.model_validate(
                    {
                        "id": EntityId(scene_id),
                        "name": post.metadata.get("name", scene_id),
                        "type": EntityType.SCENE,
                        "body": post.content,
                        "character_ids": char_ids,
                    }
                )
                campaign.add(SimpleScene(model, campaign))

        return campaign
