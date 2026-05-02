from dataclasses import dataclass
from typing import AsyncIterator, Protocol

import litellm


@dataclass
class LLMMessage:
    role: str
    content: str


class LLMClient(Protocol):
    async def stream(
        self, messages: list[LLMMessage], model: str | None
    ) -> AsyncIterator[str]: ...


class LiteLLMClient:
    def __init__(self, default_model: str) -> None:
        self.default_model = default_model

    async def stream(
        self, messages: list[LLMMessage], model: str | None
    ) -> AsyncIterator[str]:
        chosen_model = model if model is not None else self.default_model
        response = await litellm.acompletion(
            model=chosen_model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            stream=True,
        )
        async for chunk in response:
            content = chunk.choices[0].delta.content
            if content is not None:
                yield content
