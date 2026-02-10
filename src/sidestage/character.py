"""Character runtime wrapper.

Character pairs a CharacterModel (persistent data) with an Actor (behavior).
The Actor is injected at construction time by Campaign.get_character().
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sidestage.actors import Actor
    from sidestage.models import CharacterModel

logger = logging.getLogger(__name__)


class Character:
    """Runtime wrapper for a CharacterModel with an associated Actor."""

    def __init__(self, model: CharacterModel, actor: Actor):
        self.data = model
        self.actor = actor

    async def activate(self) -> None:
        """Initialize the actor's LLM agent (for NPCActor). No-op for User."""
        from sidestage.actors import NPCActor
        if isinstance(self.actor, NPCActor):
            self.actor._update_prompt()
            logger.info("Character %s (%s) activated.", self.data.name, self.data.id)

    async def deactivate(self) -> None:
        """Clean up actor state."""
        from sidestage.actors import NPCActor
        if isinstance(self.actor, NPCActor):
            self.actor.agent = None
        logger.info("Character %s deactivated.", self.data.id)
