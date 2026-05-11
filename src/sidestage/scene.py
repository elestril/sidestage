"""scene: The active game scene.

Per `specs/scene.md`. Scene is **pure data + event source** — `append`
records a message and emits `EntityChanged`; reactions are listener-driven
(per `events.md`). No `dispatch`, no `_respond` orchestration on Scene.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Literal, Self

from pydantic import BaseModel

from sidestage.entity import Entity, EntityId, EntityType
from sidestage.events import EntityChanged
from sidestage.message import Message

if TYPE_CHECKING:
    from sidestage.character import Character


class SceneResponse(BaseModel):
    """scene-response: Wire shape for `GET /api/campaigns/{cid}/entities/{id}`
    when the entity is a Scene, and for `GET /api/campaigns/{cid}/scenes`.

    Constructed exclusively by `Scene.to_response()`. The `type` discriminator
    distinguishes this variant within `EntityResponse`.
    """

    type: Literal["scene"] = "scene"
    id: EntityId
    name: str
    body: str
    character_ids: list[EntityId]
    player_character_ids: list[EntityId]


class Scene(Entity):
    """scene-class: Abstract scene — holds the message history and lists the
    present characters.

    Pure data + event source. Public mutation is `append(msg) -> int`
    (the message index) which records and emits `EntityChanged`. The npc
    response cycle is driven by listener fanout (Character.notify), not by
    Scene.

    Tests use `await scene.idle()` to wait for listener-spawned background
    tasks to settle before asserting.
    """

    characters: list[Character]
    """scene-characters: All characters present in the scene. Concrete
    subclasses may impose order or count constraints (see SimpleScene)."""

    class Model(Entity.Model):
        """scene-model: On-disk Scene shape — characters list + inherited
        Entity fields. Messages are runtime-only (not persisted)."""

        characters: list[EntityId]

    def __init__(
        self,
        *,
        id: EntityId,
        name: str,
        body: str,
        characters: list[Character],
    ) -> None:
        # Bypass Entity.__init__ default (which leaves ghost state) and fully
        # populate as a loaded scene.
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "_loaded", True)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "type", EntityType.SCENE)
        object.__setattr__(self, "body", body)
        object.__setattr__(self, "characters", list(characters))
        object.__setattr__(self, "_listeners", [])
        object.__setattr__(self, "_pending_tasks", set())

    @property
    @abstractmethod
    def messages(self) -> list[Message]:
        """scene-messages-property: Ordered list of messages in this scene.
        Subclasses own the backing storage. Mutable — `_append_message`
        appends in place. Index in the list IS the message id."""
        ...

    def _append_message(self, message: Message) -> int:
        """Internal: append `message` to history, return its index.

        - scene-append-history: Appends `message` to `self.messages`.
        - scene-append-return: Returns the new index (`len(self.messages) - 1`).
        """
        msgs = self.messages
        msgs.append(message)
        return len(msgs) - 1

    # ---------------- public mutation + test surface ---------------------

    def append(self, message: Message) -> int:
        """scene-append: Record `message` and emit `EntityChanged`.

        Single public mutation API. Returns the assigned index. The full
        message identity is `(self.id, index)`; callers that need to
        report it on the wire use `Scene.serialize_message`.

        - scene-append-records: Appends via `_append_message`.
        - scene-append-emits: Fires
          `EntityChanged(entity=self, attributes=["messages"])` via
          `self._emit`.
        - scene-append-returns: Returns the new message's index (`int`).

        .implements: events-dataflow-emit, message-dataflow-record-emit
        """
        idx = self._append_message(message)
        self._emit(EntityChanged(entity=self, attributes=["messages"]))
        return idx

    # `idle()` is inherited from `Entity` — events are entity-scoped, not
    # scene-scoped. Tests await `scene.idle()` to wait for cascading
    # reactions to scene emissions.

    # ---------------- query / serialization ------------------------------

    @property
    def user_characters(self) -> list[Character]:
        """scene-user-characters: Subset of `characters` with
        `has_human_actor()` True. Single source of truth for "which
        characters can a client send messages as"."""
        return [c for c in self.characters if c.has_human_actor()]

    def to_response(self) -> SceneResponse:
        """scene-to-response: Build the wire shape. Only place
        `SceneResponse` is constructed."""
        return SceneResponse(
            id=self.id,
            name=self.name,
            body=self.body,
            character_ids=[c.id for c in self.characters],
            player_character_ids=[c.id for c in self.user_characters],
        )

    def serialize_message(self, index: int) -> Message.Model:
        """scene-serialize-message: Build the wire `Message.Model` for the
        message at `index`. The composite `(scene_id, index)` is the
        message's identity on the wire."""
        msg = self.messages[index]
        return Message.Model(
            scene_id=self.id,
            index=index,
            sender_id=msg.sender.id,
            body=msg.body,
        )

    def to_model(self) -> Scene.Model:
        """scene-to-model: Build a `Scene.Model` from current state.
        Drops runtime-only state (messages); inverse of `Scene.deserialize`."""
        return self.Model(
            id=self.id,
            name=self.name,
            type=self.type,
            body=self.body,
            characters=[c.id for c in self.characters],
        )

    @classmethod
    def deserialize(cls, model: Scene.Model) -> Self:
        """Construct a Scene from its on-disk model.

        - scene-deserialize-resolves: Resolves each id in `model.characters`
          via `App.factory.get(id)` to a `Character` instance. Forward
          references come back as ghosts and hydrate later in the same load.
        - scene-deserialize-constructs: Returns
          `cls(id=..., name=..., body=..., characters=resolved)`.
        """
        from sidestage.server import App

        if App.factory is None:
            raise RuntimeError(
                "Scene.deserialize: App.factory must be set before "
                "deserializing scenes (see server-run-load)."
            )
        factory = App.factory
        resolved: list[Character] = []
        for cid in model.characters:
            entity = factory.get(cid)
            if entity is None:
                raise RuntimeError(
                    f"Scene.deserialize: character {cid!r} not resolved "
                    "(forward refs should have been ghost-registered)."
                )
            # The ghost machinery returns Entity instances; cast at the
            # boundary — campaign-load guarantees these are Characters.
            resolved.append(entity)  # type: ignore[arg-type]
        return cls(
            id=model.id,
            name=model.name,
            body=model.body,
            characters=resolved,
        )


class SimpleScene(Scene):
    """simple-scene: Two-party scene — exactly one user-controlled character
    and one non-user character.

    `__init__` validates the count + roles, sets `_user` / `_npc` aliases,
    and **subscribes every character to itself** so the listener-driven
    response cycle is wired automatically (per `events.md`).
    """

    def __init__(
        self,
        *,
        id: EntityId,
        name: str,
        body: str,
        characters: list[Character],
    ) -> None:
        """Construct a SimpleScene with exactly two characters.

        - simple-scene-init-count: Raises `ValueError` if `len(characters) != 2`.
        - simple-scene-init-user: Raises `ValueError` if
          `characters[0].has_human_actor()` is False.
        - simple-scene-init-npc: Raises `ValueError` if
          `characters[1].has_human_actor()` is True.
        - simple-scene-init-messages: Initializes `self._messages = []`.
        - simple-scene-init-aliases: Sets `_user = characters[0]` and
          `_npc = characters[1]`.
        - simple-scene-init-subscribes-characters: Calls `self.subscribe(c)`
          for every character in `characters`, wiring the listener-driven
          response cycle.
          - .tested-by: test_events_dataflow
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
        for c in characters:
            self.subscribe(c)

    @property
    def messages(self) -> list[Message]:
        """simple-scene-messages: Returns `self._messages`. Mutable;
        `_append_message` mutates in place."""
        return self._messages
