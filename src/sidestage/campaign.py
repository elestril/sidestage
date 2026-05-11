from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import frontmatter
import yaml
from pydantic import BaseModel

from sidestage.character import Character
from sidestage.entity import DictEntityFactory, EntityFactory, EntityId, EntityType
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

    default_scene_id: str | None = None
    """campaign-config-default-scene: Optional `EntityId` of the scene the
    client should load by default if it has no other navigation context.
    Just a hint — there is no singular "active scene", clients navigate freely.

    .implements: campaign-config-default-scene
    """


class CampaignResponse(BaseModel):
    """campaign-response: Wire shape for GET /api/campaign.

    .implements: rest-api-get-campaign
    """

    name: str
    default_scene_id: EntityId | None


class Campaign:
    """campaign-class: The core world container — name, factory of every loaded
    Entity, and an optional `default_scene_id` hint for the client.

    .implements: cuj-startup-load
    """

    name: str
    """campaign-name: Display name of the campaign; sourced from `config.yaml`.

    .implements: campaign-config-name
    """

    factory: EntityFactory
    """campaign-factory: Holds every loaded Entity indexed by `EntityId`.

    .implements: cuj-startup-load
    """

    default_scene_id: EntityId | None
    """campaign-default-scene-id: Optional `EntityId` hint for the client to
    load if it has no other navigation context. NOT a Scene reference —
    resolves via `self.factory.get(self.default_scene_id)` at use time. May
    be `None` if `config.yaml` omits the field.

    .implements: campaign-config-default-scene
    """

    def __init__(
        self,
        *,
        name: str,
        factory: EntityFactory,
        default_scene_id: EntityId | None = None,
    ) -> None:
        self.name = name
        self.factory = factory
        self.default_scene_id = default_scene_id

    @classmethod
    def load(cls, path: Path) -> Campaign:
        """campaign-load: Load a campaign from disk via single forward pass.

        Uses the ghost pattern to resolve forward references without needing a
        topological sort. Sets `App.factory` BEFORE any deserializer that needs
        to consult the active factory.

        - campaign-load-config: Reads `<path>/config.yaml` and stores `name` and
          `default_scene_id`.
        - campaign-load-walks: Performs a single forward pass over all entity
          files in `path`.
        - campaign-load-classifies: Determines each path's concrete entity type
          from its location and structure.
        - campaign-load-parses: Parses YAML frontmatter + markdown body into
          `EntityClass.Model`.
        - campaign-load-ghosts: Uses `factory.ghost()` for forward references
          encountered before the target is loaded.
        - campaign-load-deserializes: Calls `EntityClass.deserialize(model)` to
          construct each entity.
        - campaign-load-adds: Calls `factory.add(entity)` for each fully parsed
          entity, hydrating any existing ghosts.
        - campaign-load-default-scene-id: Stores `config.default_scene_id` on
          the returned Campaign as a client navigation hint. Stores `None` if
          the field is absent from config; never raises.
        - campaign-load-warns-dangling: Logs a warning listing any ghost ids
          still unresolved at end of load; ghosts are left in place.
        - campaign-load-returns: Returns a fully initialised Campaign.

        .implements: fs-dataflow-config, fs-dataflow-walk, fs-dataflow-classify,
            fs-dataflow-parse, fs-dataflow-resolve-refs, fs-dataflow-deserialize,
            fs-dataflow-add, fs-dataflow-finalize
        """
        config_data = yaml.safe_load((path / "config.yaml").read_text())
        config = CampaignConfig(**config_data)

        factory = DictEntityFactory()

        # Set App.factory BEFORE any deserialize that needs it.
        from sidestage.server import App

        App.factory = factory

        chars_dir = path / "characters"
        if chars_dir.exists():
            for md_file in chars_dir.glob("*.md"):
                char_id = md_file.stem
                post = frontmatter.load(str(md_file))
                model = Character.Model(
                    id=EntityId(char_id),
                    name=post.metadata.get("name", char_id),
                    type=EntityType.CHARACTER,
                    body=post.content,
                    owner=post.metadata.get("owner", "stub"),
                )
                character = Character.deserialize(model)
                factory.add(character)

        scenes_dir = path / "scenes"
        if scenes_dir.exists():
            for md_file in scenes_dir.glob("*.md"):
                scene_id = md_file.stem
                post = frontmatter.load(str(md_file))
                raw_chars = post.metadata.get("characters", [])
                char_ids = [EntityId(cid) for cid in raw_chars]
                for cid in char_ids:
                    if factory.get(cid) is None:
                        factory.ghost(cid, EntityType.CHARACTER)
                model = SimpleScene.Model(
                    id=EntityId(scene_id),
                    name=post.metadata.get("name", scene_id),
                    type=EntityType.SCENE,
                    body=post.content,
                    characters=char_ids,
                )
                scene = SimpleScene.deserialize(model)
                factory.add(scene)

        dangling = [
            eid
            for eid, entity in factory._entities.items()
            if not object.__getattribute__(entity, "_loaded")
        ]
        if dangling:
            logger.warning("Unresolved ghost entities after load: %s", dangling)

        default_scene_id = (
            EntityId(config.default_scene_id)
            if config.default_scene_id is not None
            else None
        )
        return cls(
            name=config.name,
            factory=factory,
            default_scene_id=default_scene_id,
        )

    def scenes(self) -> list[Scene]:
        """campaign-scenes: All scenes registered in this campaign's factory.

        Iterates the factory's registered entities and filters to those that
        are `Scene` instances. Order is the factory's iteration order
        (currently insertion order for `DictEntityFactory`).

        .implements: rest-api-get-scenes
        """
        return [e for e in self.factory._entities.values() if isinstance(e, Scene)]

    def scene(self, scene_id: EntityId) -> Optional[Scene]:
        """campaign-scene: Look up a scene by id; `None` if unknown or if the
        id resolves to a non-Scene entity.

        .implements: rest-api-get-scene
        """
        entity = self.factory.get(scene_id)
        if entity is None or not isinstance(entity, Scene):
            return None
        return entity

    def to_response(self) -> CampaignResponse:
        """campaign-to-response: Build the wire shape for this campaign.

        The only place `CampaignResponse` is constructed.

        .implements: rest-api-get-campaign
        """
        return CampaignResponse(
            name=self.name,
            default_scene_id=self.default_scene_id,
        )
