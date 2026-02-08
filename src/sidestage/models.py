"""Domain model classes for Sidestage campaign entities.

All persistent domain objects (entities, events, scenes) are defined here.
API request/response schemas live in schemas.py.
"""

from typing import Any, ClassVar, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


# --- Domain Models ---


class EntityModel(BaseModel):
    entity_type: ClassVar[str] = "Entity"

    name: str
    body: str
    id: str = Field(..., description="Unique identifier for the entity")


class ItemModel(EntityModel):
    entity_type: ClassVar[str] = "Item"


class LocationModel(EntityModel):
    entity_type: ClassVar[str] = "Location"

    connected_locations: List[str] = Field(
        default_factory=list, description="IDs of connected locations"
    )


class CharacterModel(EntityModel):
    entity_type: ClassVar[str] = "Character"

    unseen: bool = Field(
        default=False,
        description="If true, this character is not perceived by other in-game entities.",
    )
    location_id: Optional[str] = Field(
        default=None,
        description="ID of the location where the character is currently present",
    )
    inventory: List[str] = Field(
        default_factory=list, description="IDs of items in possession"
    )


class EventModel(EntityModel):
    entity_type: ClassVar[str] = "Event"

    scene_id: str
    gametime: int = Field(
        ..., description="Gametime in seconds when the event occurred"
    )
    walltime: str = Field(
        ..., description="ISO formatted walltime when the event occurred"
    )


class ChatMessageModel(EventModel):
    entity_type: ClassVar[str] = "ChatMessage"

    character_id: str = Field(
        ..., description="ID of the Character persona who sent the message"
    )
    actor_id: Optional[str] = Field(
        default=None,
        description="ID of the Actor who originated the message (for audit)",
    )
    message: str = Field(..., description="The content of the chat message")
    widget: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional interactive widget data"
    )

    @model_validator(mode="before")
    @classmethod
    def backfill_legacy_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Handle missing character_id
            if "character_id" not in data:
                # Legacy data might have 'actor' field
                actor = data.get("actor")
                if actor:
                    # Map 'actor' to 'actor_id' if missing
                    if "actor_id" not in data:
                        data["actor_id"] = actor

                    # Map 'actor' to 'character_id'
                    if actor == "agent":
                        data["character_id"] = "char_co_author"
                    elif actor == "user":
                        data["character_id"] = "user"
                    else:
                        data["character_id"] = actor
                else:
                    data["character_id"] = "unknown"

            # Handle missing actor_id if we just have character_id
            if "actor_id" not in data and "actor" in data:
                data["actor_id"] = data["actor"]

        return data


class JoinEventModel(EventModel):
    entity_type: ClassVar[str] = "JoinEvent"

    actor_id: str = Field(..., description="ID of the Actor who joined")


class LeaveEventModel(EventModel):
    entity_type: ClassVar[str] = "LeaveEvent"

    actor_id: str = Field(..., description="ID of the Actor who left")


class FastForwardEventModel(EventModel):
    entity_type: ClassVar[str] = "FastForwardEvent"

    duration_str: str = Field(
        ..., description="A string describing the time jump, e.g. '2 hours'"
    )


class SceneModel(EntityModel):
    entity_type: ClassVar[str] = "Scene"

    current_gametime: Optional[int] = Field(
        default=None, description="Current gametime in seconds. None if inactive."
    )
    location_id: Optional[str] = Field(
        default=None, description="Primary location of the scene"
    )
    events: List[str] = Field(
        default_factory=list, description="IDs of events in this scene"
    )
    messages: List[ChatMessageModel] = Field(
        default_factory=list, description="List of messages in this scene"
    )
