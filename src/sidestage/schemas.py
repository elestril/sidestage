from typing import List, Optional, Dict, Any, Union, Literal
from pydantic import BaseModel, Field, model_validator
from pydantic_core import PydanticCustomError

# --- Domain Models ---

class Entity(BaseModel):
    name: str
    body: str
    id: str = Field(..., description="Unique identifier for the entity")

class Item(Entity):
    pass

class Location(Entity):
    connected_locations: List[str] = Field(default_factory=list, description="IDs of connected locations")

class Character(Entity):
    unseen: bool = Field(default=False, description="If true, this character is not perceived by other in-game entities.")
    location_id: Optional[str] = Field(default=None, description="ID of the location where the character is currently present")
    inventory: List[str] = Field(default_factory=list, description="IDs of items in possession")

class Event(Entity):
    scene_id: str
    gametime: int = Field(..., description="Gametime in seconds when the event occurred")
    walltime: str = Field(..., description="ISO formatted walltime when the event occurred")

class ChatMessage(Event):
    character_id: str = Field(..., description="ID of the Character persona who sent the message")
    actor_id: Optional[str] = Field(default=None, description="ID of the Actor who originated the message (for audit)")
    message: str = Field(..., description="The content of the chat message")
    widget: Optional[Dict[str, Any]] = Field(default=None, description="Optional interactive widget data")

    @model_validator(mode='before')
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
                    # If actor was 'user', character_id is likely 'user' (or whatever default)
                    # If actor was 'agent', character_id was likely 'char_co_author'
                    if actor == "agent":
                        data["character_id"] = "char_co_author"
                    elif actor == "user":
                        data["character_id"] = "user" # Or 'char_user' if we standardized that
                    else:
                        data["character_id"] = actor
                else:
                    # Fallback if no actor info either (shouldn't happen for valid messages)
                    data["character_id"] = "unknown"
            
            # Handle missing actor_id if we just have character_id (less likely for legacy, but possible)
            if "actor_id" not in data and "actor" in data:
                data["actor_id"] = data["actor"]

        return data

class JoinEvent(Event):
    actor_id: str = Field(..., description="ID of the Actor who joined")

class LeaveEvent(Event):
    actor_id: str = Field(..., description="ID of the Actor who left")

class FastForwardEvent(Event):
    duration_str: str = Field(..., description="A string describing the time jump, e.g. '2 hours'")

class Scene(Entity):
    current_gametime: Optional[int] = Field(default=None, description="Current gametime in seconds. None if inactive.")
    location_id: Optional[str] = Field(default=None, description="Primary location of the scene")
    events: List[str] = Field(default_factory=list, description="IDs of events in this scene")
    messages: List[ChatMessage] = Field(default_factory=list, description="List of messages in this scene")


# --- API Request/Response Models ---

class WebSocketMessage(BaseModel):
    type: str
    # Other fields are flexible depending on type, but we can define common ones
    text: Optional[str] = None
    sender: Optional[str] = None
    scene_id: Optional[str] = None
    widget: Optional[Dict[str, Any]] = None
    entity_id: Optional[str] = None
    body: Optional[str] = None

class EntityListResponse(BaseModel):
    # Just a list of dicts with an added "type" field
    # We can use a Union of models if we want strict typing, but for list view usually lightweight is fine.
    # The current implementation returns model_dump() + type string.
    pass

class SceneCreateRequest(BaseModel):
    name: str
    description: str = ""
    current_gametime: Optional[int] = None

class EntityMarkdownResponse(BaseModel):
    markdown: str

class EntityMarkdownUpdateRequest(BaseModel):
    markdown: str

class StatusResponse(BaseModel):
    status: Literal["ok", "error"]
    message: Optional[str] = None

class ExportResponse(BaseModel):
    message: str

class ImportResponse(BaseModel):
    message: str

class ChatRequest(BaseModel):
    message: str
    scene_id: str = "campaign_planning"

class ChatResponse(BaseModel):
    user_message: ChatMessage
    agent_message: Optional[ChatMessage] = None
