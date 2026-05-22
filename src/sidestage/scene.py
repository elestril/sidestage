"""scene: The active game scene.

Per `specs/entity-model.md`. Scene is pure data + event source. The
two mutation surfaces are both EntityList-wrapped Model fields:

- `scene.characters.append(id)` — add a character to the scene.
- `scene.messages.append(msg)` — append a chat message.

Both emit `EntityChanged(deltas={attr: ListDelta(...)})` automatically.

Scene OWNS its own message persistence. When the campaign runs against
a backing store with a `db_handle` (i.e. `FalkorEntityFactory`), the
`MessageList` write-through (`_on_add`) calls `XADD` on the Redis
stream `scene:<id>:messages`; `Scene.__init__` loads the stream via
`XRANGE` and seeds `Scene.Model.messages` with `list.extend` (the
base list method), which bypasses both the ListDelta emit and the
`MessageList._on_add` re-write. Outside Scene, the only surface is
the generic `messages` property — nothing about streams leaks out.

Reactions are listener-driven (per `events.md`): characters subscribed
to a scene react via `Character.notify`.
"""

from __future__ import annotations

import typing
from typing import TYPE_CHECKING, ClassVar

from sidestage.entity import Entity, EntityId, EntityList
from sidestage.message import Message

if TYPE_CHECKING:
    from sidestage.campaign import Campaign
    from sidestage.character import Character


def _stream_key(scene_id: str) -> str:
    """The Redis stream key for a scene's message log."""
    return f"scene:{scene_id}:messages"


class MessageList(EntityList[Message]):
    """scene-message-list: `EntityList[Message]` that durably writes
    through to the scene's Redis stream on every add.

    The owning Scene's id + DB handle is reachable via
    `self._owner.id` and `self._owner._campaign.db_handle`. `_on_add`
    runs synchronously *before* the item lands in the underlying
    list (per `EntityList.append`), so an append is durably XADDed
    before any in-memory observer sees it.

    When `db_handle is None` (DictEntityFactory case), this is a
    no-op — messages live only in `Scene.Model.messages` for the
    duration of the process.

    Load-time fill via `list.extend(messages, loaded)` (in
    `Scene.__init__`) uses the base list method and bypasses this
    hook entirely, so opening a scene from the stream doesn't
    re-XADD.

    .implements: scene-message-persistence
    """

    def _on_add(self, item: Message) -> None:
        owner = self._owner
        campaign = owner._campaign
        handle = campaign.db_handle
        if handle is None:
            return
        handle.client.xadd(
            _stream_key(owner.id),
            {"sender_id": str(item.sender_id), "body": item.body},
        )


class Scene(Entity):
    """scene-class: Abstract scene — holds the list of present
    characters and the message history.

    Tests use `await scene.idle()` to wait for listener-spawned background
    tasks to settle before asserting.
    """

    class Model(Entity.Model):
        """scene-model: On-disk + on-wire Scene shape.

        `characters` is a list of `EntityId` references to the scene's
        participating characters; the FalkorEntityFactory translates
        this into Cypher relationships in the graph.

        `messages` is a chat history. When the campaign has a
        `db_handle`, Scene persists it to a per-scene Redis stream
        directly (via `MessageList._on_add` on append, `XRANGE` in
        `Scene.__init__` on load). The factory does NOT touch this
        field.
        """

        characters: list[EntityId] = []
        messages: list[Message] = []

    # entity-list-attribute: `characters` uses the base `EntityList`
    # (mutations emit `ListDelta`); `messages` uses `MessageList` which
    # additionally writes through to the Redis stream.
    _entity_lists: ClassVar = {"characters": EntityList, "messages": MessageList}

    @property
    def model(self) -> Scene.Model:
        return self._model  # type: ignore[return-value]

    def __init__(self, model: Scene.Model, campaign: Campaign) -> None:
        """Construct a Scene wrapping `model`, bound to `campaign`.

        After the standard `Entity.__init__` (which wraps the messages
        list in a `MessageList`), restores message history from the
        Redis stream if `campaign.db_handle` is present. The restore
        uses `list.extend` (base list method) to bypass emit and
        `_on_add`, so reopening a scene neither echoes nor re-XADDs.

        .implements: scene-message-persistence
        """
        super().__init__(model, campaign)
        handle = campaign.db_handle
        if handle is None:
            return
        entries = typing.cast(
            list[tuple[str, dict[str, str]]],
            handle.client.xrange(_stream_key(self.id), "-", "+"),
        )
        loaded = [
            Message(
                sender_id=EntityId(fields["sender_id"]),
                body=fields["body"],
            )
            for _, fields in entries
        ]
        # Base list method — bypasses EntityList.extend's emit + _on_add.
        list.extend(self.messages, loaded)

    async def idle(self, timeout: float = 5.0) -> None:
        """scene-idle: Wait for all background tasks spawned in response to
        recent emissions to settle. Test-only primitive — production
        never calls it. Public on Scene because Scene is where mutation
        cascades actually happen (per `events-async-tasks-idle`).

        .implements: events-async-tasks-idle, scene-idle
        """
        await self._idle(timeout)


class SimpleScene(Scene):
    """simple-scene: Two-party scene — exactly one user-controlled character
    and one non-user character.

    Roles (user vs npc) are derived from `Character.owner`, not from
    position in `model.characters`. Validation + subscription happen at
    construction; the loader is responsible for adding characters to
    the campaign *before* the SimpleScene is constructed (load order:
    characters → scenes).
    """

    def __init__(self, model: Scene.Model, campaign: Campaign) -> None:
        """Construct a SimpleScene wrapping `model`.

        - simple-scene-init-count: Raises `ValueError` if
          `len(model.characters) != 2`.
        - simple-scene-init-roles: Raises `ValueError` unless exactly
          one of the two characters has `has_human_actor() is True`
          (the user) and one has `has_human_actor() is False` (the
          NPC). Role identification is by `Character.owner`, not by
          list position.
        - simple-scene-init-subscribes-characters: Subscribes every
          character so the listener-driven response cycle runs.
          - .tested-by: test_events_dataflow

        Cross-entity resolution requires both characters to be already
        registered in `campaign` — the load loop enforces character-
        before-scene order.
        """
        super().__init__(model, campaign)
        char_ids = list(self.characters)
        if len(char_ids) != 2:
            raise ValueError(
                f"SimpleScene {self.id!r} requires exactly 2 characters; "
                f"got {len(char_ids)}"
            )
        resolved: list[Character] = [
            campaign.get(cid)  # type: ignore[misc]
            for cid in char_ids
        ]
        users = [c for c in resolved if c.has_human_actor()]
        npcs = [c for c in resolved if not c.has_human_actor()]
        if len(users) != 1 or len(npcs) != 1:
            raise ValueError(
                f"SimpleScene {self.id!r}: expected exactly one user-"
                f"controlled and one non-user character; got "
                f"users={[c.id for c in users]!r} npcs={[c.id for c in npcs]!r}"
            )
        self._user = users[0]
        self._npc = npcs[0]
        for c in resolved:
            self.subscribe(c)
