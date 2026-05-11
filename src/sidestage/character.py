from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Self

from sidestage.entity import Entity, EntityId, EntityType

if TYPE_CHECKING:
    from sidestage.events import EntityChanged
    from sidestage.message import Message


class Character(Entity):
    """character-class: A person in the game world — player character, NPC, or
    meta-character such as the GM. Persistent world-state plus an `owner`
    discriminator that selects which runtime Actor handles responses.

    .implements: character
    """

    owner: Literal["user", "stub"]
    """character-owner: Persistent role discriminator — `"user"` or
    `"stub"`. Serialized to disk; selects the runtime Actor via
    `App.get_actor(self.owner)`. Future expansion (e.g. `"npc"` once
    an LLM-backed actor lands) widens this Literal.

    .implements: character
    """

    class Model(Entity.Model):
        """character-model: Inner Pydantic model — the on-disk / on-wire shape
        of a Character. Adds the `owner` Literal field on top of `EntityModel`.

        .implements: character
        """

        owner: Literal["user", "stub"]

    def __init__(
        self,
        *,
        id: EntityId,
        name: str,
        body: str,
        owner: Literal["user", "stub"],
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

    async def respond(self, message: Message) -> Message | None:
        """character-respond-passthrough: Pure pass-through —
        `await self._actor.respond(message, self)`.

        .implements: message-simplescene-respond
        """
        return await self._actor.respond(message, self)

    async def notify(self, event: EntityChanged) -> None:
        """character-notify-react: React to an `EntityChanged` event from a
        Scene we're subscribed to.

        Pure async — the bus wraps each listener in a task per
        `events-async-tasks`, so this can `await` directly without manual
        `create_task`. The wrapping task is tracked on `event.entity` for
        `idle()` to await.

        Filters: only emissions where `event.entity` is a Scene AND
        `"messages" in event.attributes`; only when the latest message's
        sender is NOT this character (avoids responding to own messages,
        including the recursive case where this character's response
        causes another emission).

        Action: `await self._actor.respond(latest, self)`. If the response
        is non-None, appends it back via `event.entity.append(response)`
        (which fires another `EntityChanged`).

        .implements: events-pattern-subscription, message-dataflow-react
        .tested-by: test_events_dataflow
        """
        # Lazy import — scene.py imports character.py via TYPE_CHECKING; doing
        # this at module level would cycle.
        from sidestage.scene import Scene

        # Filter: only Scene emissions with message-list changes.
        if not isinstance(event.entity, Scene):
            return
        if "messages" not in event.attributes:
            return
        latest = event.entity.messages[-1]
        # Don't respond to our own messages — avoids the recursion where our
        # appended response triggers another EntityChanged we'd react to.
        if latest.sender is self:
            return
        # Generate a response via the bound actor; append back if non-None.
        response = await self._actor.respond(latest, self)
        if response is not None:
            event.entity.append(response)

    def has_human_actor(self) -> bool:
        """character-has-human-actor: Returns `self.owner == "user"`. The check
        is against the persistent role, not the live actor binding — owners do
        not change over a character's lifetime.

        .implements: character
        """
        return self.owner == "user"
