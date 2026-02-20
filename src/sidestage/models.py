"""Domain model classes for Sidestage campaign entities.

All persistent domain objects (entities, events, scenes) are defined here.
API request/response schemas live in schemas.py.
"""

from datetime import datetime
from enum import Enum
from typing import Any, ClassVar, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# --- Enums ---


class EventType(str, Enum):
    CHAT_MESSAGE = "ChatMessage"
    JOIN = "JoinEvent"
    LEAVE = "LeaveEvent"
    ADJUST_GAMETIME = "AdjustGametime"
    ERROR = "Error"


class Visibility(str, Enum):
    PUBLIC = "public"
    GM_ONLY = "gm_only"
    PRIVATE = "private"


# --- Domain Models ---


class EntityModel(BaseModel):
    entity_type: ClassVar[str] = "Entity"

    name: str
    body: str = ""
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
    owner: str = Field(
        default="npc",
        description="'npc' for NPC characters, a user_id string for player characters",
    )
    system_actor: bool = Field(
        default=False, description="True for the Campaign Co-Author character"
    )


class EventModel(EntityModel):
    model_config = ConfigDict(extra="ignore")

    entity_type: ClassVar[str] = "Event"

    event_type: EventType
    scene_id: str
    gametime: int = Field(
        ..., description="Gametime in seconds when the event occurred"
    )
    walltime: datetime = Field(
        ..., description="Real-world timestamp when the event occurred"
    )
    character_id: Optional[str] = None
    actor_id: Optional[str] = None
    body: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    visibility: Visibility = Visibility.PUBLIC


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
    character_ids: List[str] = Field(
        default_factory=list, description="IDs of characters participating in this scene"
    )


# Backward-compat aliases for modules not yet migrated (scene.py, memory/context.py).
# These will be removed in sections 04/06.
ChatMessageModel = EventModel
JoinEventModel = EventModel
LeaveEventModel = EventModel
FastForwardEventModel = EventModel
