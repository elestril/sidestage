from __future__ import annotations

from pathlib import Path
import pytest
from sidestage.campaign import Campaign, CampaignConfig
from sidestage.scene import Scene
from sidestage.character import Character


DRAGONS_LAIR = Path("configs/dragons_lair")


class TestCampaignConfig:
    def test_config_has_name_and_active_scene(self):
        config = CampaignConfig(name="Test", active_scene_id="s1")
        assert config.name == "Test"
        assert config.active_scene_id == "s1"


class TestCampaignLoad:
    def test_load_returns_campaign(self):
        campaign = Campaign.load(DRAGONS_LAIR)
        assert isinstance(campaign, Campaign)

    def test_load_campaign_name(self):
        campaign = Campaign.load(DRAGONS_LAIR)
        assert campaign.name == "Dragon's Lair"

    def test_load_active_scene(self):
        campaign = Campaign.load(DRAGONS_LAIR)
        assert isinstance(campaign.scene, Scene)
        assert campaign.scene.id == "dungeon_entrance"

    def test_load_scene_name(self):
        campaign = Campaign.load(DRAGONS_LAIR)
        assert campaign.scene.name == "Dungeon Entrance"

    def test_load_characters_in_scene(self):
        campaign = Campaign.load(DRAGONS_LAIR)
        char_ids = {c.id for c in campaign.scene.characters}
        assert "bob" in char_ids
        assert "elara" in char_ids

    def test_load_character_names(self):
        campaign = Campaign.load(DRAGONS_LAIR)
        char_map = {c.id: c for c in campaign.scene.characters}
        assert char_map["bob"].name == "Bob"
        assert char_map["elara"].name == "Elara Moonwhisper"

    def test_load_character_actor_types(self):
        campaign = Campaign.load(DRAGONS_LAIR)
        char_map = {c.id: c for c in campaign.scene.characters}
        assert char_map["bob"].actor_type == "user"
        assert char_map["elara"].actor_type == "npc"

    def test_load_characters_have_stub_actor(self):
        from sidestage.actor import StubActor
        campaign = Campaign.load(DRAGONS_LAIR)
        char_map = {c.id: c for c in campaign.scene.characters}
        assert isinstance(char_map["elara"]._actor, StubActor)

    def test_load_warns_unresolved_ghosts(self, caplog, tmp_path):
        import logging
        (tmp_path / "characters").mkdir()
        (tmp_path / "scenes").mkdir()
        (tmp_path / "config.yaml").write_text("name: Test\nactive_scene_id: s1\n")
        (tmp_path / "characters" / "alice.md").write_text(
            "---\nname: Alice\nactor: user\n---\nA character.\n"
        )
        (tmp_path / "scenes" / "s1.md").write_text(
            "---\nname: Scene One\nactive_characters:\n  - alice\n  - ghost_char\n---\nA scene.\n"
        )
        with caplog.at_level(logging.WARNING, logger="sidestage.campaign"):
            campaign = Campaign.load(tmp_path)
        assert any("ghost_char" in r.message for r in caplog.records)

    def test_load_factory_has_entities(self):
        campaign = Campaign.load(DRAGONS_LAIR)
        assert campaign.factory.get("bob") is not None
        assert campaign.factory.get("elara") is not None
        assert campaign.factory.get("dungeon_entrance") is not None
