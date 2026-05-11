from __future__ import annotations

import logging
from pathlib import Path

import frontmatter
import yaml
from pydantic import BaseModel

from sidestage.character import Character
from sidestage.entity import DictEntityFactory, EntityFactory, EntityId, EntityType
from sidestage.scene import SimpleScene

logger = logging.getLogger(__name__)


class CampaignConfig(BaseModel):
    """campaign-config: top-level campaign settings stored in `config.yaml`.

    .implements: campaign-config
    """

    name: str
    """campaign-config-name: Display name of the campaign.

    .implements: campaign-config-name
    """

    active_scene_id: str
    """campaign-config-active-scene: EntityId of the scene the player was last
    in. NOT a Scene reference — resolved at use time via the factory.

    .implements: campaign-config-active-scene
    """


class Campaign:
    """campaign-class: The core world container — name, factory of every loaded
    Entity, and a persistent "where the player left off" pointer.

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

    active_scene_id: EntityId
    """campaign-active-scene-id: EntityId of the scene that is "current" — where
    the player was last interacting. NOT a Scene reference — resolves to the
    active Scene via `self.factory.get(self.active_scene_id)` at use time.

    .implements: campaign-config-active-scene
    """

    def __init__(
        self, *, name: str, factory: EntityFactory, active_scene_id: EntityId
    ) -> None:
        self.name = name
        self.factory = factory
        self.active_scene_id = active_scene_id

    @classmethod
    def load(cls, path: Path) -> Campaign:
        """campaign-load: Load a campaign from disk via single forward pass.

        Uses the ghost pattern to resolve forward references without needing a
        topological sort. Sets `App.factory` BEFORE any deserializer that needs
        to consult the active factory.

        - campaign-load-config: Reads `<path>/config.yaml` and stores `name` and
          `active_scene_id`.
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
        - campaign-load-active-scene-id: Stores `config.active_scene_id` on the
          returned Campaign. The Scene itself is resolved later via the factory.
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

        return cls(
            name=config.name,
            factory=factory,
            active_scene_id=EntityId(config.active_scene_id),
        )
