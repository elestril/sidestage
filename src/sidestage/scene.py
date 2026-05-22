"""scene: The active game scene.

Per `specs/entity-model.md`. Scene is pure data + event source. The
single mutation surface is `scene.messages.append(msg)` — the
`EntityList[Message]` wrapper around `Scene.Model.messages` emits
`EntityChanged(deltas={"messages": ListDelta(...)})` automatically.

Reactions are listener-driven (per `events.md`): characters subscribed
to a scene react via `Character.notify`. No `Scene.append`, no
`dispatch`, no orchestration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from sidestage.entity import Entity, EntityId, EntityList
from sidestage.message import Message

if TYPE_CHECKING:
    from sidestage.campaign import Campaign
    from sidestage.character import Character


class Scene(Entity):
    """scene-class: Abstract scene — holds the message history and lists the
    present characters.

    Tests use `await scene.idle()` to wait for listener-spawned background
    tasks to settle before asserting.
    """

    class Model(Entity.Model):
        """scene-model: On-disk Scene shape — character ids list + the
        runtime messages list. `character_ids` is persisted to disk;
        `messages` is wiped on reload (per `backend-reload`)."""

        character_ids: list[EntityId]
        messages: list[Message] = []

    # entity-list-attribute: messages is auto-wrapped in an EntityList at
    # construction; append/insert/remove/etc. emit ListDelta automatically.
    _entity_lists: ClassVar = {"messages": EntityList}

    @property
    def model(self) -> Scene.Model:
        return self._model  # type: ignore[return-value]

    @property
    def characters(self) -> list[Character]:
        """scene-characters: Resolved Character instances for this scene.

        Computed from `self._model.character_ids` via the Campaign.

        .implements: scene-characters-resolve-on-demand
        """
        return [self._campaign.get(cid) for cid in self._model.character_ids]  # type: ignore[misc,list-item]

    @property
    def user_characters(self) -> list[Character]:
        """scene-user-characters: Characters with `has_human_actor()` True."""
        return [c for c in self.characters if c.has_human_actor()]


class SimpleScene(Scene):
    """simple-scene: Two-party scene — exactly one user-controlled character
    and one non-user character.

    Validates count + roles at construction. Resolved characters live as
    `Scene.characters` (a property); subscription wiring happens in
    `__init__`.
    """

    def __init__(self, model: Scene.Model, campaign: Campaign) -> None:
        """Construct a SimpleScene wrapping `model`.

        - simple-scene-init-count: Raises `ValueError` if
          `len(model.character_ids) != 2`.
        - simple-scene-init-user: Raises `ValueError` if the first
          character is not human-controlled.
        - simple-scene-init-npc: Raises `ValueError` if the second
          character is human-controlled.
        - simple-scene-init-subscribes-characters: Subscribes every
          character so the listener-driven response cycle runs.
          - .tested-by: test_events_dataflow

        Cross-entity resolution requires both characters to be already
        registered in `campaign` — the load loop enforces character-before-
        scene order.
        """
        super().__init__(model, campaign)
        chars = self.characters
        if len(chars) != 2:
            raise ValueError(
                f"SimpleScene requires exactly 2 characters; got {len(chars)}"
            )
        if not chars[0].has_human_actor():
            raise ValueError(
                "SimpleScene.characters[0] must be the human-controlled character"
            )
        if chars[1].has_human_actor():
            raise ValueError(
                "SimpleScene.characters[1] must be the NPC (non-human) character"
            )
        self._user, self._npc = chars
        for c in chars:
            self.subscribe(c)
