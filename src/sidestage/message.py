"""message: The unit of communication.

A `Message` is a Pydantic BaseModel carrying `sender_id` and `body`.
It is both the wire shape AND the in-memory representation — no
parallel dataclass + Model split, no `scene_id`/`idx` fields.

Identity of a specific message is the composite `(scene.id,
position-in-scene.messages)` assembled externally; nothing on the
Message itself carries identity.
"""

from __future__ import annotations

from pydantic import BaseModel

from sidestage.entity import EntityId


class Message(BaseModel):
    """message-class: A unit of communication in a Scene.

    Two fields: who sent it, what they said. Identity is positional
    (the message at index N in scene S's `messages`); no id field.

    .implements: message-shape
    """

    sender_id: EntityId
    body: str
