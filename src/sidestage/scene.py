"""scene: The active game scene.

Per `specs/entity-model.md`. Scene is **pure data + event source** — `append`
records a message and emits `EntityChanged`; reactions are listener-driven
(per `events.md`). No `dispatch`, no `_respond` orchestration on Scene.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING

from sidestage.entity import Entity, EntityId
from sidestage.events import EntityChanged
from sidestage.message import Message

if TYPE_CHECKING:
    from sidestage.campaign import Campaign
    from sidestage.character import Character


class Scene(Entity):
    """scene-class: Abstract scene — holds the message history and lists the
    present characters.

    Pure data + event source. Public mutation is `append(msg) -> int` which
    records and emits `EntityChanged`. The NPC response cycle is driven by
    listener fanout (Character.notify), not by Scene.

    Tests use `await scene.idle()` to wait for listener-spawned background
    tasks to settle before asserting.
    """

    class Model(Entity.Model):
        """scene-model: On-disk Scene shape — character ids list + inherited
        Entity fields. Messages are runtime-only (not persisted)."""

        character_ids: list[EntityId]

    @property
    def model(self) -> Scene.Model:
        return self._model  # type: ignore[return-value]

    @property
    def characters(self) -> list[Character]:
        """scene-characters: Resolved Character instances for this scene.

        Computed from `self._model.character_ids` via the Campaign. Resolved
        fresh each access — caching is a micro-optimisation we don't need
        today.

        .implements: scene-deserialize-resolves
        """
        return [self._campaign.get(cid) for cid in self._model.character_ids]  # type: ignore[misc,list-item]

    @property
    @abstractmethod
    def messages(self) -> list[Message]:
        """scene-messages-property: Ordered list of messages. Subclasses own
        the backing storage."""
        ...

    def _append_message(self, message: Message) -> int:
        """Internal: append `message` to history, return its index.

        - scene-append-history: Appends to `self.messages`.
        - scene-append-return: Returns `len(self.messages) - 1`.
        """
        msgs = self.messages
        msgs.append(message)
        return len(msgs) - 1

    def append(self, message: Message) -> int:
        """scene-append: Record `message` and emit `EntityChanged`.

        Single public mutation for adding a message. The composite
        `(self.id, index)` is the message's wire identity.

        - scene-append-records: Appends via `_append_message`.
        - scene-append-emits: Fires
          `EntityChanged(entity=self, attributes=["messages"])`.
        - scene-append-returns: Returns the new index.

        .implements: events-dataflow-emit, message-dataflow-record-emit
        """
        idx = self._append_message(message)
        self._emit(EntityChanged(entity=self, attributes=["messages"]))
        return idx

    @property
    def user_characters(self) -> list[Character]:
        """scene-user-characters: Characters with `has_human_actor()` True."""
        return [c for c in self.characters if c.has_human_actor()]

    def serialize_message(self, index: int) -> Message.Model:
        """scene-serialize-message: Build the wire `Message.Model` for the
        message at `index`."""
        msg = self.messages[index]
        return Message.Model(
            scene_id=self.id,
            index=index,
            sender_id=msg.sender.id,
            body=msg.body,
        )


class SimpleScene(Scene):
    """simple-scene: Two-party scene — exactly one user-controlled character
    and one non-user character.

    Validates count + roles at construction. Resolved characters live as a
    property on Scene; subscription wiring happens in `__init__`.
    """

    def __init__(self, model: Scene.Model, campaign: Campaign) -> None:
        """Construct a SimpleScene wrapping `model`.

        - simple-scene-init-count: Raises `ValueError` if
          `len(model.character_ids) != 2`.
        - simple-scene-init-user: Raises `ValueError` if the first
          character is not human-controlled.
        - simple-scene-init-npc: Raises `ValueError` if the second
          character is human-controlled.
        - simple-scene-init-messages: Initialises the runtime messages list.
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
        self._messages: list[Message] = []
        self._user, self._npc = chars
        for c in chars:
            self.subscribe(c)

    @property
    def messages(self) -> list[Message]:
        """simple-scene-messages: Returns `self._messages`. Mutable;
        `_append_message` mutates in place."""
        return self._messages
