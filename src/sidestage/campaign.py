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
    name: str
    active_scene_id: str


class Campaign:
    def __init__(self, name: str, scene: Scene, factory: EntityFactory) -> None:
        self.name = name
        self.scene = scene
        self.factory = factory

    @classmethod
    def load(cls, path: Path) -> Campaign:
        config_data = yaml.safe_load((path / "config.yaml").read_text())
        config = CampaignConfig(**config_data)
        factory = DictEntityFactory()

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
                    actor_type=post.metadata.get("actor", "npc"),
                    model=post.metadata.get("model"),
                )
                character = Character.deserialize(model)
                factory.add(character)

        scenes_dir = path / "scenes"
        if scenes_dir.exists():
            for md_file in scenes_dir.glob("*.md"):
                scene_id = md_file.stem
                post = frontmatter.load(str(md_file))
                raw_chars = post.metadata.get("active_characters", [])
                char_ids = [EntityId(cid) for cid in raw_chars]
                for cid in char_ids:
                    if factory.get(cid) is None:
                        factory.ghost(cid, EntityType.CHARACTER)
                model = SimpleScene.Model(
                    id=EntityId(scene_id),
                    name=post.metadata.get("name", scene_id),
                    type=EntityType.SCENE,
                    body=post.content,
                    active_character_ids=char_ids,
                )
                scene = SimpleScene.deserialize(model)
                resolved_chars = []
                for cid in char_ids:
                    entity = factory.get(cid)
                    if entity is not None:
                        resolved_chars.append(entity)
                object.__setattr__(scene, "characters", resolved_chars)
                factory.add(scene)

        dangling = [
            eid
            for eid, entity in factory._entities.items()
            if not object.__getattribute__(entity, "_loaded")
        ]
        if dangling:
            logger.warning("Unresolved ghost entities after load: %s", dangling)

        active_scene = factory.get(config.active_scene_id)
        return cls(name=config.name, scene=active_scene, factory=factory)
