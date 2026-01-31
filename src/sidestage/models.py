from typing import List, Optional
from pydantic import BaseModel, Field

class Entity(BaseModel):
    name: str
    description: str
    id: str = Field(..., description="Unique identifier for the entity")

class Item(Entity):
    pass

class Location(Entity):
    connected_locations: List[str] = Field(default_factory=list, description="IDs of connected locations")

class NPC(Entity):
    location_id: Optional[str] = Field(default=None, description="ID of the location where the NPC is currently present")
    inventory: List[str] = Field(default_factory=list, description="IDs of items in possession")

class Event(BaseModel):
    id: str = Field(..., description="Unique identifier for the event")
    scene_id: str
    gametime: int = Field(..., description="Gametime in seconds when the event occurred")
    walltime: str = Field(..., description="ISO formatted walltime when the event occurred")
    description: str

class Scene(Entity):
    current_gametime: Optional[int] = Field(default=None, description="Current gametime in seconds. None if inactive.")
    location_id: Optional[str] = Field(default=None, description="Primary location of the scene")
    events: List[str] = Field(default_factory=list, description="IDs of events in this scene")
    messages: List[str] = Field(default_factory=list, description="IDs of messages in this scene")
