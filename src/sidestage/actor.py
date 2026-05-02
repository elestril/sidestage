from typing import AsyncIterator, Protocol

from sidestage.llm_client import LLMClient, LLMMessage


class Actor(Protocol):
    async def chat_stream(
        self, messages: list[LLMMessage]
    ) -> AsyncIterator[str]: ...


class NpcActor:
    def __init__(self, llm_client: LLMClient, model: str | None) -> None:
        self.llm_client = llm_client
        self.model = model

    async def chat_stream(
        self, messages: list[LLMMessage]
    ) -> AsyncIterator[str]:
        async for token in self.llm_client.stream(messages, self.model):
            yield token


class UserActor:
    async def chat_stream(
        self, messages: list[LLMMessage]
    ) -> AsyncIterator[str]:
        raise NotImplementedError
        yield  # pragma: no cover
