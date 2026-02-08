# `sidestage.memory.embeddings`

Embedding generation via LiteLLM for the sidestage memory system.

## Classes

### `EmbeddingError(Exception)`

Raised when embedding generation fails.

#### `__init__(args, kwargs)`

## Functions

### `embed_and_update(client: GraphClient, config: LLMConfig, memory_id: str, text: str, health: CampaignHealth) -> None` *async*

Generate embedding and update the memory node. Fire-and-forget.

Never raises -- all errors are caught and logged. Designed to be
wrapped in asyncio.create_task() by callers.

### `embed_text(config: LLMConfig, text: str) -> list[float]` *async*

Generate embedding for a single text using LiteLLM aembedding().

Returns the embedding vector (list[float]).

Raises:
    EmbeddingError: On any failure (provider error, timeout, network error).

### `validate_embed_config(config: LLMConfig) -> int | None` *async*

Validate embed configuration and detect vector dimension.

Makes a test embedding call with probe text. Returns the vector
dimension on success, or None on failure.
