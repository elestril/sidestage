"""message: The unit of communication.

Domain types for messages exchanged between Characters in a Scene.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel

from sidestage.entity import EntityId

if TYPE_CHECKING:
    from sidestage.character import Character


@dataclass
class Message:
    """message-class: A unit of communication between Characters in a Scene.

    The domain `Message` carries no id field — its position in
    `scene.messages` IS its identity. The wire shape (`Message.Model`)
    carries `scene_id` and `index` as separate fields; assembly happens in
    `Scene.serialize_message(index)`.

    `sender: Character`
    `body: str`

    - message-class-fields: Has exactly two fields, `sender: Character` and
      `body: str`. No id attribute on instances.
    - message-class-no-serialize: Carries no `serialize` method; serialization
      lives on `Scene.serialize_message`.

    .implements: message-dataflow-receive
    .implemented-by: SimpleScene.serialize_message
    """

    sender: "Character"
    body: str

    class Model(BaseModel):
        """message-model: Canonical wire shape for a Message.

        Inner Pydantic model used in `GET /scenes/{scene_id}/messages`
        responses. The composite key `(scene_id, index)` uniquely
        identifies a message system-wide; clients use them as separate
        fields rather than parsing a composed string.

        ```python
        class Model(BaseModel):
            scene_id: EntityId
            index: int
            sender_id: EntityId
            body: str
        ```

        - message-model-fields: Has exactly four fields — `scene_id: EntityId`,
          `index: int`, `sender_id: EntityId`, `body: str`. All required.
        - message-model-inner: Defined as an inner class on `Message`.
        - message-model-built-by: Constructed only by `Scene.serialize_message`.

        .implements: message-dataflow-receive, rest-api-get-messages
        .implemented-by: SimpleScene.serialize_message
        """

        scene_id: EntityId
        index: int
        sender_id: EntityId
        body: str
