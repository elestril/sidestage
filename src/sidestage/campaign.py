from dataclasses import dataclass

from sidestage.character import Character
from sidestage.ids import CampaignId, CharacterId, SceneId
from sidestage.scene import Scene


@dataclass
class Campaign:
    id: CampaignId
    name: str
    active_scene_id: SceneId | None
    characters: dict[CharacterId, Character]
    scenes: dict[SceneId, Scene]

    def get_active_scene(self) -> Scene:
        if self.active_scene_id is None:
            raise ValueError("Campaign has no active scene")
        return self.scenes[self.active_scene_id]

    def get_character(self, id: CharacterId) -> Character:
        return self.characters[id]
