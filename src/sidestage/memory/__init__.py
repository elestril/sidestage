"""Sidestage memory system -- living text documents stored as graph nodes."""

from sidestage.memory.models import Memory, MemoryType, ContextResult, ContextMemories
from sidestage.memory.store import (
    MEMORY_REL_TYPES,
    upsert_memory,
    upsert_scene_memory,
    upsert_common_scene_memory,
    upsert_character_memory,
    upsert_world_fact,
    get_scene_memory,
    get_common_scene_memory,
    get_character_memory,
    get_memories_for_context,
    get_all_memories,
    delete_memory,
    touch_memory,
    search_similar,
)
from sidestage.memory.embeddings import (
    EmbeddingError,
    embed_text,
    embed_and_update,
    validate_embed_config,
)
