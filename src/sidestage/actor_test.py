from typing import AsyncIterator

import pytest

from sidestage.actor import NpcActor, UserActor
from sidestage.llm_client import LLMMessage


class StubLLMClient:
    """In-test stub for LLMClient capturing call arguments and yielding fixed tokens."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self.received_messages: list[LLMMessage] | None = None
        self.received_model: str | None = None
        self.stream_call_count = 0

    async def stream(
        self, messages: list[LLMMessage], model: str | None
    ) -> AsyncIterator[str]:
        self.stream_call_count += 1
        self.received_messages = messages
        self.received_model = model
        for token in self._tokens:
            yield token


async def test_npc_actor_yields_all_tokens_from_llm_client_stream():
    stub = StubLLMClient(tokens=["hello", " world"])
    actor = NpcActor(llm_client=stub, model="gpt-4")
    messages = [LLMMessage(role="user", content="hi")]

    collected: list[str] = []
    async for token in actor.chat_stream(messages):
        collected.append(token)

    assert collected == ["hello", " world"], (
        "NpcActor.chat_stream must yield every token produced by the injected "
        "LLMClient.stream async iterator, in order. Stub yielded ['hello', ' world'] "
        f"but NpcActor.chat_stream produced {collected!r}"
    )


async def test_npc_actor_passes_configured_model_to_llm_client():
    stub = StubLLMClient(tokens=["x"])
    actor = NpcActor(llm_client=stub, model="claude-3-5-sonnet")
    messages = [LLMMessage(role="user", content="hi")]

    async for _ in actor.chat_stream(messages):
        pass

    assert stub.received_model == "claude-3-5-sonnet", (
        "NpcActor.chat_stream must forward self.model to LLMClient.stream as the "
        "`model` argument. Expected the stub to receive 'claude-3-5-sonnet' but it "
        f"received {stub.received_model!r}"
    )


async def test_npc_actor_passes_none_model_to_llm_client_when_model_is_none():
    stub = StubLLMClient(tokens=["x"])
    actor = NpcActor(llm_client=stub, model=None)
    messages = [LLMMessage(role="user", content="hi")]

    async for _ in actor.chat_stream(messages):
        pass

    assert stub.received_model is None, (
        "When NpcActor is constructed with model=None, chat_stream must pass None "
        "through to LLMClient.stream (no defaulting or substitution). Expected the "
        f"stub to receive None but it received {stub.received_model!r}"
    )


async def test_user_actor_chat_stream_raises_not_implemented_error():
    actor = UserActor()
    messages = [LLMMessage(role="user", content="hi")]

    with pytest.raises(NotImplementedError):
        async for _ in actor.chat_stream(messages):
            pass
