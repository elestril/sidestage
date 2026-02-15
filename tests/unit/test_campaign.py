"""Tests for Campaign class — actor infrastructure and character resolution."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sidestage.actors import NPCActor, User
from sidestage.campaign import Campaign
from sidestage.character import Character
from sidestage.config import SidestageConfig
from sidestage.models import CharacterModel


def _make_campaign(tmp_path: Path) -> Campaign:
    """Create a Campaign with mocked LLM availability check."""
    with patch("sidestage.config.get_config", return_value=SidestageConfig()):
        with patch("sidestage.campaign.Campaign._ensure_llm_availability"):
            return Campaign(name="test", base_dir=tmp_path)


def test_campaign_creates_user_at_startup(tmp_path: Path):
    """Campaign.__init__ creates a User actor accessible as campaign.user."""
    campaign = _make_campaign(tmp_path)
    assert isinstance(campaign.user, User)
    assert campaign.user.actor_id == "user"


def test_campaign_no_agent_attribute(tmp_path: Path):
    """Campaign should not have a .agent attribute (Co-Author is now an NPCActor)."""
    campaign = _make_campaign(tmp_path)
    assert not hasattr(campaign, "agent")


def test_campaign_has_character_registry(tmp_path: Path):
    """Campaign has a characters dict for the character registry."""
    campaign = _make_campaign(tmp_path)
    assert isinstance(campaign.characters, dict)
    assert len(campaign.characters) == 0


def test_get_character_returns_character(tmp_path: Path):
    """Campaign.get_character() returns a Character instance."""
    campaign = _make_campaign(tmp_path)
    model = CharacterModel(id="char_test", name="Test NPC", owner="npc")
    char = campaign.get_character(model)
    assert isinstance(char, Character)
    assert char.data is model


def test_get_character_caches(tmp_path: Path):
    """Campaign.get_character() caches and returns the same Character."""
    campaign = _make_campaign(tmp_path)
    model = CharacterModel(id="char_test", name="Test NPC", owner="npc")
    char1 = campaign.get_character(model)
    char2 = campaign.get_character(model)
    assert char1 is char2


def test_npc_owner_resolves_to_npc_actor(tmp_path: Path):
    """Character with owner='npc' gets an NPCActor."""
    campaign = _make_campaign(tmp_path)
    model = CharacterModel(id="char_npc", name="NPC", owner="npc")
    char = campaign.get_character(model)
    assert isinstance(char.actor, NPCActor)
    assert char.actor.actor_id == "agent:char_npc"


def test_player_owner_resolves_to_user_actor(tmp_path: Path):
    """Character with owner != 'npc' gets the shared User actor."""
    campaign = _make_campaign(tmp_path)
    model = CharacterModel(id="char_player", name="Player Char", owner="player")
    char = campaign.get_character(model)
    assert char.actor is campaign.user


def test_system_actor_flag_propagated(tmp_path: Path):
    """system_actor=True on CharacterModel propagates to NPCActor."""
    campaign = _make_campaign(tmp_path)
    model = CharacterModel(
        id="char_co_author", name="Co-Author",
        owner="npc", system_actor=True,
    )
    char = campaign.get_character(model)
    assert isinstance(char.actor, NPCActor)
    assert char.actor.system_actor is True


def test_regular_npc_not_system_actor(tmp_path: Path):
    """Regular NPC without system_actor flag has system_actor=False."""
    campaign = _make_campaign(tmp_path)
    model = CharacterModel(id="char_npc", name="NPC", owner="npc")
    char = campaign.get_character(model)
    assert isinstance(char.actor, NPCActor)
    assert char.actor.system_actor is False
