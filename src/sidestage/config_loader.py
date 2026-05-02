from dataclasses import dataclass
from pathlib import Path

import frontmatter
import yaml

from sidestage.actor import NpcActor, UserActor
from sidestage.campaign import Campaign
from sidestage.character import Character
from sidestage.ids import CampaignId, CharacterId, SceneId
from sidestage.llm_client import LLMClient
from sidestage.scene import Scene


@dataclass
class ServerConfig:
    default_model: str


class ConfigLoader:
    def __init__(self, config_root: Path) -> None:
        self.config_root = config_root

    def load_server_config(self) -> ServerConfig:
        with open(self.config_root / "sidestage.yaml") as f:
            data = yaml.safe_load(f)
        return ServerConfig(default_model=data["default_model"])

    def load_all_campaigns(
        self, llm_client: LLMClient
    ) -> dict[CampaignId, Campaign]:
        campaigns: dict[CampaignId, Campaign] = {}
        for campaign_dir in self.config_root.iterdir():
            if not campaign_dir.is_dir():
                continue
            campaign_yaml_path = campaign_dir / "campaign.yaml"
            if not campaign_yaml_path.exists():
                continue
            with open(campaign_yaml_path) as f:
                campaign_yaml = yaml.safe_load(f)

            characters: dict[CharacterId, Character] = {}
            characters_dir = campaign_dir / "characters"
            if characters_dir.exists():
                for char_file in sorted(characters_dir.glob("*.md")):
                    post = frontmatter.load(char_file)
                    char_id = CharacterId(char_file.stem)
                    actor_type = post.get("actor")
                    if actor_type == "user":
                        actor = UserActor()
                    else:
                        actor = NpcActor(llm_client, post.get("model"))
                    characters[char_id] = Character(
                        id=char_id,
                        name=post["name"],
                        character_sheet=post.content,
                        actor=actor,
                    )

            scenes: dict[SceneId, Scene] = {}
            scenes_dir = campaign_dir / "scenes"
            campaign_id = CampaignId(campaign_dir.name)
            if scenes_dir.exists():
                for scene_file in sorted(scenes_dir.glob("*.md")):
                    post = frontmatter.load(scene_file)
                    scene_id = SceneId(scene_file.stem)
                    active_character_ids = [
                        CharacterId(cid)
                        for cid in post.get("active_characters", [])
                    ]
                    scenes[scene_id] = Scene(
                        id=scene_id,
                        campaign_id=campaign_id,
                        name=post["name"],
                        description=post.content,
                        active_character_ids=active_character_ids,
                        messages=[],
                    )

            active_scene_id = SceneId(campaign_yaml["active_scene_id"])
            campaigns[campaign_id] = Campaign(
                id=campaign_id,
                name=campaign_yaml["name"],
                active_scene_id=active_scene_id,
                characters=characters,
                scenes=scenes,
            )
        return campaigns
