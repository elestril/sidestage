"""Tests for Character runtime wrapper and Campaign character registry."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from sidestage.character import Character
from sidestage.actors import NPCActor, User, Actor
from sidestage.models import CharacterModel


# --- Character Wrapper ---

def test_character_wraps_model_and_actor():
    """Character wraps CharacterModel as .data and Actor as .actor."""
    model = CharacterModel(id="char_1", name="Alice", body="A warrior")
    actor = NPCActor(actor_id="agent:char_1")
    char = Character(model=model, actor=actor)
    assert char.data is model
    assert char.actor is actor


def test_character_data_is_character_model():
    """Character.data is a CharacterModel instance."""
    model = CharacterModel(id="char_1", name="Alice", body="A warrior")
    actor = User(actor_id="user")
    char = Character(model=model, actor=actor)
    assert isinstance(char.data, CharacterModel)


@pytest.mark.anyio
async def test_character_activate_is_noop_for_user():
    """Character.activate() is a no-op for User actors."""
    model = CharacterModel(id="char_1", name="Alice", body="", owner="user-1")
    actor = User(actor_id="user")
    char = Character(model=model, actor=actor)
    await char.activate()  # Should not raise


@pytest.mark.anyio
async def test_character_deactivate():
    """Character.deactivate() completes without error."""
    model = CharacterModel(id="char_1", name="Alice", body="")
    actor = NPCActor(actor_id="agent:char_1")
    char = Character(model=model, actor=actor)
    await char.deactivate()  # Should not raise
