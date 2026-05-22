from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from sidestage.entity import Entity, MessageContext

if TYPE_CHECKING:
    from sidestage.campaign import Campaign
    from sidestage.events import EntityChanged
    from sidestage.message import Message


class Character(Entity):
    """character-class: A person in the game world — player character, NPC,
    or meta-character. World-data plus an `owner` discriminator that
    selects which runtime Actor handles responses.

    .implements: character
    """

    class Model(Entity.Model):
        """character-model: Adds `owner` to the Entity Model schema.

        .implements: character
        """

        owner: Literal["user", "stub", "npc"]

    @property
    def model(self) -> Character.Model:
        return self._model  # type: ignore[return-value]

    def __init__(self, model: Character.Model, campaign: Campaign) -> None:
        """Construct a Character wrapping `model`, bound to `campaign`.

        Binds the runtime Actor singleton based on `model.owner` and stores
        it as `self._actor` (not a Model field — runtime-only).

        .implements: character, character-init-binds-actor
        """
        super().__init__(model, campaign)
        # Lazy import — server.py imports character.py via campaign.py, so a
        # top-level import would cycle.
        from sidestage.server import App

        self._actor = App.get_actor(model.owner)

    def annotate_context(self, ctx: MessageContext) -> None:
        """character-annotate-context: Writes `self.body` keyed by `self`,
        then recurses into `ctx.scene`. Future Character subclasses can
        extend this to recurse into memories / items via
        `self._campaign.get(...)`.

        .implements: character-annotate-context
        """
        super().annotate_context(ctx)
        ctx.scene.annotate_context(ctx)

    async def respond(self, message: Message, scene: Entity) -> Message | None:
        """character-respond-passthrough: Forward to the bound Actor.

        .implements: message-simplescene-respond
        """
        return await self._actor.respond(message, self, scene)

    async def notify(self, event: EntityChanged) -> None:
        """character-notify-react: On `EntityChanged` from a subscribed
        Scene, if the latest message wasn't from `self`, run the bound
        Actor's `respond` and append any non-None reply back to the scene.

        .implements: events-pattern-subscription, message-dataflow-react
        .tested-by: test_events_dataflow
        """
        # Lazy import — scene.py imports character.py via TYPE_CHECKING.
        from sidestage.scene import Scene

        if not isinstance(event.entity, Scene):
            return
        if "messages" not in event.attributes:
            return
        latest = event.entity.messages[-1]
        if latest.sender is self:
            return
        response = await self._actor.respond(latest, self, event.entity)
        if response is not None:
            event.entity.append(response)

    def has_human_actor(self) -> bool:
        """character-has-human-actor: Returns `self.owner == "user"`.

        .implements: character
        """
        return self.owner == "user"
