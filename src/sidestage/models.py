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
