from __future__ import annotations

import asyncio
from abc import abstractmethod
from typing import TYPE_CHECKING, Self

from sidestage.actor import SceneUpdatedEvent
from sidestage.entity import Entity, EntityId, EntityType
from sidestage.message import Message, MessageId

if TYPE_CHECKING:
    from sidestage.character import Character


class Scene(Entity):
    """scene-class: Abstract scene — holds the message history and lists the
    present characters.

    Scene is abstract; only concrete subclasses are instantiated. Subclass
    constructors are responsible for populating `characters` and providing
    the backing storage for the abstract `messages` property.

    .implements: scene
    .implemented-by: SimpleScene
    """

    characters: list["Character"]
    """scene-characters: All characters present in the scene. Concrete subclasses
    may impose order or count constraints (see SimpleScene).

    .implements: scene-class
    .implemented-by: Scene.characters
    """

    class Model(Entity.Model):
        """scene-model: Inner Pydantic model — the on-disk / on-wire shape for
        any Scene.

        `characters` is a list of `EntityId` — the ids of characters present
        in the scene. Concrete subclasses MAY extend `Scene.Model` with
        subclass-specific fields. `SimpleScene.Model` adds none today.

        .implements: scene-class
        .implemented-by: Scene.Model
        """

        characters: list[EntityId]

    def __init__(
        self,
        *,
        id: EntityId,
        name: str,
        body: str,
        characters: list["Character"],
    ) -> None:
        # Bypass Entity.__init__ default (which leaves ghost state) and fully
        # populate as a loaded scene.
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "_loaded", True)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "type", EntityType.SCENE)
        object.__setattr__(self, "body", body)
        object.__setattr__(self, "characters", list(characters))

    @property
    @abstractmethod
    def messages(self) -> list[Message]:
        """scene-messages-property: Returns the ordered list of messages in the
        scene.

        Subclasses own the backing storage; the returned list MUST be mutable —
        `_append_message` appends to it directly. A message's index in this
        list is its id; no separate counter is maintained.

        .implements: scene-class
        .implemented-by: SimpleScene.messages
        """
        ...

    def _append_message(self, message: Message) -> int:
        """Internal contract — append `message` to history, return its index.

        Private to Scene; not part of the public spec surface (per
        `spec-link-targets-private`). Documented here as an internal contract
        because subclasses rely on it.

        - scene-append-history: Appends `message` to `self.messages`.
        - scene-append-return: Returns the new index (`len(self.messages) - 1`).
        """
        msgs = self.messages
        msgs.append(message)
        return len(msgs) - 1

    def serialize_message(self, index: int) -> Message.Model:
        """scene-serialize-message: Returns
        `Message.Model(id=MessageId(f"{self.id}:{index}"),
        sender_id=self.messages[index].sender.id,
        body=self.messages[index].body)`.

        This is the only place `MessageId` is constructed; scene-internal
        code uses `int` indices.

        .implements: message-id-format
        .implemented-by: Scene.serialize_message
        """
        msg = self.messages[index]
        return Message.Model(
            id=MessageId(f"{self.id}:{index}"),
            sender_id=msg.sender.id,
            body=msg.body,
        )

    @classmethod
    def deserialize(cls, model: "Scene.Model") -> Self:
        """Construct a Scene from its on-disk model.

        - scene-deserialize-signature: Same uniform signature as
          `Entity.deserialize(model)` so callers can dispatch polymorphically.
        - scene-deserialize-resolves: Resolves each id in `model.characters`
          via `App.factory.get(id)` to a `Character` instance. Forward
          references that aren't loaded yet come back as ghosts (per the
          ghost pattern in `entity.md`) and hydrate later in the same load
          pass.
        - scene-deserialize-constructs: Returns
          `cls(id=model.id, name=model.name, body=model.body,
          characters=resolved)`.

        .implements: fs-dataflow-deserialize
        .implemented-by: Scene.deserialize
        """
        # Lazy import to avoid circular imports at module load.
        from sidestage.server import App

        resolved: list["Character"] = [
            App.factory.get(cid) for cid in model.characters
        ]
        return cls(
            id=model.id,
            name=model.name,
            body=model.body,
            characters=resolved,
        )

    @abstractmethod
    def dispatch(self, message: Message) -> MessageId:
        """Dispatch an incoming message; return its assigned `MessageId`.

        Abstract on Scene — concrete subclasses define the routing policy.

        .implements: message-dataflow-receive
        .implemented-by: SimpleScene.dispatch
        """
        ...


class SimpleScene(Scene):
    """simple-scene: Two-party scene — one user-controlled character + one NPC.

    Assumes exactly two characters: `characters[0]` is the human-controlled
    user, `characters[1]` is the NPC. The constructor validates this and
    exposes named aliases for two-party routing.

    Backing storage:
    - `_messages: list[Message]` Backing storage for the inherited `messages`
      property; initialized empty.
    - `_user: Character` Alias for `self.characters[0]` — the human-controlled
      character.
    - `_npc: Character` Alias for `self.characters[1]` — the NPC character.

    .implements: scene-class, message-simplescene-dispatch, message-simplescene-respond
    .implemented-by: SimpleScene
    """

    def __init__(
        self,
        *,
        id: EntityId,
        name: str,
        body: str,
        characters: list["Character"],
    ) -> None:
        """Construct a SimpleScene with exactly two characters.

        - simple-scene-init-count: Raises `ValueError` if
          `len(characters) != 2`.
        - simple-scene-init-user: Raises `ValueError` if
          `characters[0].has_human_actor()` is False.
        - simple-scene-init-npc: Raises `ValueError` if
          `characters[1].has_human_actor()` is True.
        - simple-scene-init-messages: Initializes `self._messages = []`.
        - simple-scene-init-aliases: Sets `_user = characters[0]` and
          `_npc = characters[1]`.

        .implements: simple-scene
        .implemented-by: SimpleScene.__init__
        """
        if len(characters) != 2:
            raise ValueError(
                f"SimpleScene requires exactly 2 characters; got {len(characters)}"
            )
        if not characters[0].has_human_actor():
            raise ValueError(
                "SimpleScene.characters[0] must be the human-controlled character"
            )
        if characters[1].has_human_actor():
            raise ValueError(
                "SimpleScene.characters[1] must be the NPC (non-human) character"
            )
        super().__init__(id=id, name=name, body=body, characters=characters)
        object.__setattr__(self, "_messages", [])
        object.__setattr__(self, "_user", characters[0])
        object.__setattr__(self, "_npc", characters[1])

    @property
    def messages(self) -> list[Message]:
        """simple-scene-messages: Returns `self._messages`. Mutable;
        `_append_message` mutates in place.

        .implements: scene-messages-property
        .implemented-by: SimpleScene.messages
        """
        return self._messages

    def dispatch(self, message: Message) -> MessageId:
        """Dispatch an incoming message: record it, kick off the NPC reply,
        and return the new message's id.

        - simple-scene-dispatch-append: Calls
          `index = self._append_message(message)`.
        - simple-scene-dispatch-task: Spawns
          `asyncio.create_task(self._respond(message))`; does NOT await.
        - simple-scene-dispatch-return: Returns
          `MessageId(f"{self.id}:{index}")`.

        .implements: message-simplescene-dispatch, message-dataflow-receive,
            Scene.dispatch
        .implemented-by: SimpleScene.dispatch
        """
        index = self._append_message(message)
        asyncio.create_task(self._respond(message))
        return MessageId(f"{self.id}:{index}")

    def _make_scene_update(self, latest_index: int) -> SceneUpdatedEvent:
        """Internal contract — build a `SceneUpdatedEvent` for `latest_index`.

        Private to Scene; not part of the public spec surface (per
        `spec-link-targets-private`). Documented here as an internal contract
        because it is the only place Scene constructs notification events.

        - scene-make-update: Returns
          `SceneUpdatedEvent(scene_id=self.id,
          latest_message_index=latest_index)`.
        """
        return SceneUpdatedEvent(
            scene_id=self.id,
            latest_message_index=latest_index,
        )

    async def _respond(self, message: Message) -> None:
        """Internal contract — drive the NPC response and notify the user.

        Private to Scene; not part of the public spec surface (per
        `spec-link-targets-private`). Documented here as an internal contract
        because the dispatch task depends on it.

        - simple-scene-respond-call:
          `response = await self._npc.respond(message)`.
        - simple-scene-respond-append: If `response is not None`, calls
          `latest_index = self._append_message(response)`.
        - simple-scene-respond-notify: Builds an event via
          `self._make_scene_update(latest_index)` and calls
          `self._user.notify(event)` to wake the user's connected SSE
          clients.
        """
        response = await self._npc.respond(message)
        if response is not None:
            latest_index = self._append_message(response)
            event = self._make_scene_update(latest_index)
            self._user.notify(event)
