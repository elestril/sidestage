"""message: The unit of communication.

Domain types for messages exchanged between Characters in a Scene.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, NewType

from pydantic import BaseModel

from sidestage.entity import EntityId

if TYPE_CHECKING:
    from sidestage.character import Character


MessageId = NewType("MessageId", str)
"""message-id-newtype: All message references use `MessageId` rather than bare `str`.

- message-id-format: A `MessageId` is formatted as `"{scene_id}:{index}"` where
  `index` is a per-scene monotonically increasing integer; ids within a scene
  are consecutive.
- message-id-assign: A `Message` arrives at `Scene.dispatch` without an id; the
  scene assigns the next available `MessageId` there (in
  `Scene.serialize_message`, the only place `MessageId` is constructed). This
  is the only place ids are assigned.

.implements: message-dataflow-receive, message-simplescene-dispatch
.implemented-by: SimpleScene.dispatch, SimpleScene.serialize_message
"""


@dataclass
class Message:
    """message-class: A unit of communication between Characters in a Scene.

    The domain `Message` carries no `id` field — its position in
    `scene.messages` IS its identity. Wire serialization is performed by
    `Scene.serialize_message(index)` since constructing the `MessageId`
    requires the scene's id.

    `sender: Character`
    `body: str`

    - message-class-fields: Has exactly two fields, `sender: Character` and
      `body: str`. No `id` attribute on instances.
    - message-class-no-serialize: Carries no `serialize` method; serialization
      lives on `Scene.serialize_message`.

    .implements: message-dataflow-receive
    .implemented-by: SimpleScene.dispatch, SimpleScene.serialize_message
    """

    sender: "Character"
    body: str

    class Model(BaseModel):
        """message-model: Canonical wire shape for a Message.

        Inner Pydantic model used both in `GET /api/scenes/{scene_id}/messages`
        responses and in SSE `message_created` event payloads.

        ```python
        class Model(BaseModel):
            id: MessageId        # "{scene_id}:{index}" — built by Scene.serialize_message
            sender_id: EntityId  # resolves against the client entity cache
            body: str
        ```

        - message-model-fields: Has exactly three fields — `id: MessageId`,
          `sender_id: EntityId`, `body: str`. All required.
        - message-model-inner: Defined as an inner class on `Message`.
        - message-model-built-by: Constructed only by `Scene.serialize_message`,
          the sole place `MessageId` is materialized.

        .implements: message-dataflow-receive, rest-api-get-messages
        .implemented-by: SimpleScene.serialize_message
        """

        id: MessageId
        sender_id: EntityId
        body: str
