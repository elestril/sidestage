from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Optional, Self

from sidestage.entity import Entity, EntityId, EntityType

if TYPE_CHECKING:
    from sidestage.actor import Actor, SceneUpdatedEvent
    from sidestage.message import Message


class Character(Entity):
    """character-class: A person in the game world — player character, NPC, or
    meta-character such as the GM. Persistent world-state plus an `owner`
    discriminator that selects which runtime Actor handles responses.

    .implements: character
    """

    owner: str
    """character-owner: Persistent role discriminator — `"user"`, `"npc"`, or
    `"stub"`. Serialized to disk; selects the runtime Actor via
    `App.get_actor(self.owner)`.

    .implements: character
    """

    class Model(Entity.Model):
        """character-model: Inner Pydantic model — the on-disk / on-wire shape
        of a Character. Adds the `owner` Literal field on top of `EntityModel`.

        .implements: character
        """

        owner: Literal["user", "npc", "stub"]

    def __init__(
        self,
        *,
        id: EntityId,
        name: str,
        body: str,
        owner: Literal["user", "npc", "stub"],
    ) -> None:
        """Construct a fully-loaded (non-ghost) Character.

        - character-init-stores-owner: Stores `owner` as an attribute.
        - character-init-binds-actor: Calls `App.get_actor(self.owner)` and
          stores the returned Actor instance as `self._actor`. The Actor is
          a shared singleton managed by App; multiple characters with the
          same `owner` share one Actor.

        .implements: character
        """
        # Initialise as a fully-loaded (non-ghost) Entity.
        super().__init__(id, _loaded=True)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "type", EntityType.CHARACTER)
        object.__setattr__(self, "body", body)
        # character-init-stores-owner.
        object.__setattr__(self, "owner", owner)
        # character-init-binds-actor: lookup the shared Actor singleton via App.
        # Lazy import — server.py imports character.py, so a top-level import
        # would cycle.
        from sidestage.server import App

        actor = App.get_actor(owner)
        object.__setattr__(self, "_actor", actor)

    @classmethod
    def deserialize(cls, model: Character.Model) -> Self:
        # Construct via __init__ so the actor binding happens consistently.
        return cls(
            id=model.id,
            name=model.name,
            body=model.body,
            owner=model.owner,
        )

    def serialize(self) -> Character.Model:
        return self.Model(
            id=self.id,
            name=self.name,
            type=self.type,
            body=self.body,
            owner=self.owner,
        )

    async def respond(self, message: Message) -> Optional[Message]:
        """character-respond-passthrough: Pure pass-through —
        `await self._actor.respond(message, self)`.

        .implements: message-simplescene-respond
        """
        return await self._actor.respond(message, self)

    def notify(self, event: SceneUpdatedEvent) -> None:
        """character-notify-passthrough: Pure pass-through to
        `self._actor.notify(event)`.

        .implements: message-simplescene-respond
        """
        return self._actor.notify(event)

    def has_human_actor(self) -> bool:
        """character-has-human-actor: Returns `self.owner == "user"`. The check
        is against the persistent role, not the live actor binding — owners do
        not change over a character's lifetime.

        .implements: character
        """
        return self.owner == "user"
