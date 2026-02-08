"""Context assembly for agent prompts.

Fetches memories from the store, formats them into structured text sections,
and trims chat history to fit within a token budget.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sidestage.memory.models import ContextResult, ContextMemories
from sidestage.memory.store import get_memories_for_context, touch_memory

from sidestage.schemas import ChatMessage

if TYPE_CHECKING:
    from sidestage.graph.client import GraphClient

logger = logging.getLogger(__name__)

AVG_TOKENS_PER_WORD = 1.3
DEFAULT_CHAT_HISTORY_RATIO = 0.20


def _format_memories(memories: ContextMemories, character_names: dict[str, str] | None = None) -> str:
    """Format ContextMemories into structured markdown sections.

    Sections with no content are omitted entirely.
    """
    sections: list[str] = []

    # World Knowledge
    if memories.world_facts:
        lines = ["## World Knowledge"]
        for wf in memories.world_facts:
            lines.append(f"- {wf.content}")
        sections.append("\n".join(lines))

    # Common scene memory
    if memories.common_scene_memory:
        sections.append(f"## Scene Memory (General)\n{memories.common_scene_memory.content}")

    # Private scene memory
    if memories.private_scene_memory:
        sections.append(f"## My Scene Memory\n{memories.private_scene_memory.content}")

    # Character memories
    if memories.character_memories:
        lines = ["## People I Know"]
        names = character_names or {}
        for char_id, mem in memories.character_memories.items():
            display_name = names.get(char_id, char_id)
            lines.append(f"### {display_name}\n{mem.content}")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def _trim_chat_history(messages: list[ChatMessage], word_budget: int) -> str:
    """Trim chat messages to fit word budget, keeping most recent."""
    if not messages or word_budget <= 0:
        return ""

    # Work backwards from most recent, accumulating words
    selected: list[str] = []
    words_used = 0

    for msg in reversed(messages):
        formatted = f"[{msg.character_id}]: {msg.message}"
        msg_words = len(formatted.split())
        if words_used + msg_words > word_budget and selected:
            break
        selected.append(formatted)
        words_used += msg_words

    selected.reverse()
    return "\n".join(selected)


def _estimate_tokens(text: str) -> int:
    """Simple token estimation: len(text) // 4."""
    return len(text) // 4


async def assemble_context(
    client: GraphClient,
    owner_id: str,
    scene_id: str,
    present_character_ids: list[str],
    recent_messages: list[ChatMessage],
    context_limit: int,
    chat_history_ratio: float = DEFAULT_CHAT_HISTORY_RATIO,
    character_names: dict[str, str] | None = None,
) -> ContextResult:
    """Assemble memory context for an agent prompt.

    Fetches all applicable memories, formats them, trims chat history,
    and returns a ContextResult ready for injection into the LLM prompt.
    """
    # 1. Fetch memories
    memories = await get_memories_for_context(
        client, owner_id, scene_id, present_character_ids,
    )

    # 2. Touch accessed memories (non-blocking, best-effort)
    memory_ids = []
    if memories.common_scene_memory:
        memory_ids.append(memories.common_scene_memory.id)
    if memories.private_scene_memory:
        memory_ids.append(memories.private_scene_memory.id)
    for mem in memories.character_memories.values():
        memory_ids.append(mem.id)
    for mem in memories.world_facts:
        memory_ids.append(mem.id)

    for mid in memory_ids:
        try:
            await touch_memory(client, mid)
        except Exception:
            logger.warning("Failed to touch memory %s", mid)

    # 3. Format memories
    memory_text = _format_memories(memories, character_names=character_names)

    # 4. Trim chat history
    word_budget = int(context_limit * chat_history_ratio / AVG_TOKENS_PER_WORD)
    chat_text = _trim_chat_history(recent_messages, word_budget)

    # 5. Estimate tokens
    total_text = memory_text + chat_text
    token_estimate = _estimate_tokens(total_text)

    return ContextResult(
        memory_text=memory_text,
        chat_text=chat_text,
        token_estimate=token_estimate,
    )
