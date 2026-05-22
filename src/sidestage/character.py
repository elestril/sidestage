from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from sidestage.action import action
from sidestage.entity import Entity, EntityId, MessageContext
from sidestage.message import Message

if TYPE_CHECKING:
    from sidestage.campaign import Campaign
    from sidestage.events import EntityChanged


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

    @action
    async def say(self, scene_id: EntityId, body: str) -> None:
        """character-say: Append a `Message(sender_id=self.id, body=body)`
        to scene `scene_id`. The single mutator for "this character
        produces a message" — covers both user input (FE-issued
        `EntityAction`) and NPC response (in-process call from
        `Character.notify`).

        .implements: character-say, message-dataflow
        .tested-by: cuj-hello-browser
        """
        scene = self._campaign.get(scene_id)
        if scene is None:
            raise ValueError(f"unknown scene_id {scene_id!r}")
        scene.messages.append(Message(sender_id=self.id, body=body))

    async def notify(self, event: EntityChanged) -> None:
        """character-notify-react: On `EntityChanged` from a subscribed
        Scene, if the latest message's sender is NOT `self`, run the
        bound Actor's `respond` and publish any non-None reply via
        `self.say`.

        .implements: events-pattern-subscription, message-dataflow
        .tested-by: test_events_dataflow
        """
        # Lazy import — scene.py imports character.py via TYPE_CHECKING.
        from sidestage.scene import Scene

        if not isinstance(event.entity, Scene):
            return
        if "messages" not in event.attributes:
            return
        latest: Message = event.entity.messages[-1]
        if latest.sender_id == self.id:
            return
        response_text = await self._actor.respond(latest, self, event.entity)
        if response_text is not None:
            await self.say(event.entity.id, response_text)

    def has_human_actor(self) -> bool:
        """character-has-human-actor: Returns `self.owner == "user"`.

        .implements: character
        """
        return self.owner == "user"
