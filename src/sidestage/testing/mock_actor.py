"""Mock LLM agent for deterministic E2E testing."""

import anyio
from dataclasses import dataclass

from sidestage.agent import AgentResponse


@dataclass
class MockResponse:
    """A canned response for the mock agent."""

    body: str = "Mock response"
    character_id: str | None = None
    actor_id: str = "agent:co_author"
    event_type: str = "ChatMessage"
    delay: float = 0.5


class MockLLMAgent:
    """Minimal stand-in for LiteLLMAgent that returns canned responses.

    Duck-typed replacement implementing the same ``arun()`` interface.
    """

    def __init__(
        self,
        name: str = "MockAgent",
        default_response: str = "Mock response",
        response_delay: float = 0.1,
    ):
        self.name = name
        self.responses: list[MockResponse] = []
        self.default_response = default_response
        self.response_delay = response_delay

    async def arun(
        self, message: str, context: str | None = None, stream: bool = False
    ) -> AgentResponse:
        """Return the next queued response or the default."""
        if self.responses:
            resp = self.responses.pop(0)
            await anyio.sleep(resp.delay)
            return AgentResponse(content=resp.body)

        await anyio.sleep(self.response_delay)
        return AgentResponse(content=self.default_response)
