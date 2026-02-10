"""API request/response schemas for Sidestage HTTP and WebSocket endpoints.

Domain model classes live in models.py.
"""

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel

from sidestage.models import EventModel


# --- API Request/Response Models ---


class WebSocketMessage(BaseModel):
    type: str
    text: Optional[str] = None
    sender: Optional[str] = None
    scene_id: Optional[str] = None
    widget: Optional[Dict[str, Any]] = None
    entity_id: Optional[str] = None
    body: Optional[str] = None


class EntityListResponse(BaseModel):
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
    event: EventModel
