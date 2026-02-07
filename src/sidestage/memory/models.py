"""Core memory data types for the sidestage memory system."""

from __future__ import annotations

import time
import uuid
from enum import Enum

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    SCENE = "scene"
    CHARACTER = "character"
    WORLD_FACT = "world_fact"


class Memory(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    memory_type: MemoryType
    visibility: str
    embedding: list[float] | None = None
    owner_id: str | None = None
    target_id: str
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    gametime: int | None = None
    access_count: int = 0
    last_accessed_at: float | None = None


class ContextResult(BaseModel):
    memory_text: str
    chat_text: str
    token_estimate: int


class ContextMemories(BaseModel):
    common_scene_memory: Memory | None
    private_scene_memory: Memory | None
    character_memories: dict[str, Memory]
    world_facts: list[Memory]
