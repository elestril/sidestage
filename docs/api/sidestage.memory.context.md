# `sidestage.memory.context`

Context assembly for agent prompts.

Fetches memories from the store, formats them into structured text sections,
and trims chat history to fit within a token budget.

## Functions

### `assemble_context(client: GraphClient, owner_id: str, scene_id: str, present_character_ids: list[str], recent_messages: list[ChatMessage], context_limit: int, chat_history_ratio: float = 0.2, character_names: dict[str, str] | None = None) -> ContextResult` *async*

Assemble memory context for an agent prompt.

Fetches all applicable memories, formats them, trims chat history,
and returns a ContextResult ready for injection into the LLM prompt.
