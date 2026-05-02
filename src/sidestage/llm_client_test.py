from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sidestage.llm_client import LiteLLMClient, LLMMessage


def _make_chunk(content: str | None) -> SimpleNamespace:
    """Build a minimal mock litellm streaming chunk.

    litellm streaming chunks expose `chunk.choices[0].delta.content`, where
    `content` can be a string token or `None` (e.g., for role-only deltas).
    """
    delta = SimpleNamespace(content=content)
    choice = SimpleNamespace(delta=delta)
    return SimpleNamespace(choices=[choice])


class _AsyncChunkIterator:
    """Async iterator yielding pre-built mock streaming chunks.

    `litellm.acompletion(..., stream=True)` returns an awaitable that resolves
    to an async iterator over chunks. We use AsyncMock(return_value=...) to
    satisfy the awaitable, and this class to provide the async iterator.
    """

    def __init__(self, chunks: list[SimpleNamespace]) -> None:
        self._chunks = chunks
        self._index = 0

    def __aiter__(self) -> "_AsyncChunkIterator":
        return self

    async def __anext__(self) -> SimpleNamespace:
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk


async def test_stream_uses_default_model_when_model_argument_is_none():
    chunks = _AsyncChunkIterator([_make_chunk("hello")])
    messages = [LLMMessage(role="user", content="hi")]
    client = LiteLLMClient(default_model="gpt-4o")

    with patch(
        "sidestage.llm_client.litellm.acompletion",
        new=AsyncMock(return_value=chunks),
    ) as mock_acompletion:
        async for _ in client.stream(messages, None):
            pass

    assert mock_acompletion.await_count == 1, (
        "LiteLLMClient.stream must call litellm.acompletion exactly once per "
        f"stream() invocation; got {mock_acompletion.await_count} awaited calls."
    )
    _, kwargs = mock_acompletion.call_args
    assert kwargs.get("model") == "gpt-4o", (
        "When LiteLLMClient.stream is called with model=None, it must invoke "
        "litellm.acompletion with model=self.default_model. Constructed with "
        "default_model='gpt-4o', expected litellm.acompletion to receive "
        f"model='gpt-4o', but received model={kwargs.get('model')!r}."
    )


async def test_stream_uses_explicit_model_argument_when_provided():
    chunks = _AsyncChunkIterator([_make_chunk("hello")])
    messages = [LLMMessage(role="user", content="hi")]
    client = LiteLLMClient(default_model="gpt-4o")

    with patch(
        "sidestage.llm_client.litellm.acompletion",
        new=AsyncMock(return_value=chunks),
    ) as mock_acompletion:
        async for _ in client.stream(messages, "claude-3"):
            pass

    assert mock_acompletion.await_count == 1, (
        "LiteLLMClient.stream must call litellm.acompletion exactly once per "
        f"stream() invocation; got {mock_acompletion.await_count} awaited calls."
    )
    _, kwargs = mock_acompletion.call_args
    assert kwargs.get("model") == "claude-3", (
        "When LiteLLMClient.stream is called with an explicit model argument, "
        "it must forward that value (NOT the default_model) to "
        "litellm.acompletion. Called with model='claude-3' (default_model="
        "'gpt-4o'), expected litellm.acompletion to receive model='claude-3', "
        f"but received model={kwargs.get('model')!r}."
    )


async def test_stream_passes_messages_and_stream_true_to_litellm():
    chunks = _AsyncChunkIterator([_make_chunk("hello")])
    messages = [
        LLMMessage(role="system", content="you are helpful"),
        LLMMessage(role="user", content="hi"),
    ]
    client = LiteLLMClient(default_model="gpt-4o")

    with patch(
        "sidestage.llm_client.litellm.acompletion",
        new=AsyncMock(return_value=chunks),
    ) as mock_acompletion:
        async for _ in client.stream(messages, None):
            pass

    _, kwargs = mock_acompletion.call_args
    assert kwargs.get("stream") is True, (
        "LiteLLMClient.stream must pass stream=True to litellm.acompletion to "
        "request a streaming response; got "
        f"stream={kwargs.get('stream')!r}."
    )
    assert "messages" in kwargs, (
        "LiteLLMClient.stream must pass the messages argument to "
        "litellm.acompletion as a keyword argument named 'messages'; "
        f"call kwargs were {sorted(kwargs.keys())!r}."
    )


async def test_stream_yields_non_none_token_content_in_order():
    chunks = _AsyncChunkIterator(
        [
            _make_chunk("hello"),
            _make_chunk(" "),
            _make_chunk("world"),
        ]
    )
    messages = [LLMMessage(role="user", content="hi")]
    client = LiteLLMClient(default_model="gpt-4o")

    collected: list[str] = []
    with patch(
        "sidestage.llm_client.litellm.acompletion",
        new=AsyncMock(return_value=chunks),
    ):
        async for token in client.stream(messages, None):
            collected.append(token)

    assert collected == ["hello", " ", "world"], (
        "LiteLLMClient.stream must yield chunk.choices[0].delta.content for "
        "every chunk that has non-None content, preserving order. Mocked "
        "litellm.acompletion produced contents ['hello', ' ', 'world'] but "
        f"stream() yielded {collected!r}."
    )


async def test_stream_skips_chunks_with_none_content():
    chunks = _AsyncChunkIterator(
        [
            _make_chunk(None),
            _make_chunk("hello"),
            _make_chunk(None),
            _make_chunk("world"),
            _make_chunk(None),
        ]
    )
    messages = [LLMMessage(role="user", content="hi")]
    client = LiteLLMClient(default_model="gpt-4o")

    collected: list[str] = []
    with patch(
        "sidestage.llm_client.litellm.acompletion",
        new=AsyncMock(return_value=chunks),
    ):
        async for token in client.stream(messages, None):
            collected.append(token)

    assert collected == ["hello", "world"], (
        "LiteLLMClient.stream must skip any chunk whose "
        "chunk.choices[0].delta.content is None (e.g., role-only deltas) and "
        "yield only the non-None content tokens, preserving order. Mocked "
        "litellm.acompletion produced contents [None, 'hello', None, 'world', "
        f"None] but stream() yielded {collected!r}."
    )
