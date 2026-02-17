"""Test-only API routes for mock agent configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from pydantic import BaseModel

from sidestage.testing.mock_actor import MockLLMAgent, MockResponse

if TYPE_CHECKING:
    from sidestage.orchestrator import SidestageOrchestrator


class MockAgentConfigureRequest(BaseModel):
    responses: list[dict[str, Any]] = []
    default_response: str | None = None
    response_delay: float | None = None


def _find_mock_agents(orchestrator: SidestageOrchestrator) -> list[MockLLMAgent]:
    """Traverse active scenes and return all MockLLMAgent instances."""
    agents: list[MockLLMAgent] = []
    for scene in orchestrator.active_scenes.values():
        for character in scene.characters.values():
            actor = character.actor
            if actor is not None and isinstance(getattr(actor, "agent", None), MockLLMAgent):
                agents.append(actor.agent)
    return agents


def register_test_routes(app: FastAPI, orchestrator: SidestageOrchestrator) -> None:
    """Register test-only API routes for mock agent configuration.

    Only call this when SIDESTAGE_MOCK_AGENT is set.
    """

    @app.post("/v1/test/mock-agent/configure")
    async def configure_mock_agent(request: MockAgentConfigureRequest) -> dict[str, Any]:
        agents = _find_mock_agents(orchestrator)
        for agent in agents:
            if request.responses:
                agent.responses = [
                    MockResponse(**r) for r in request.responses
                ]
            if request.default_response is not None:
                agent.default_response = request.default_response
            if request.response_delay is not None:
                agent.response_delay = request.response_delay
        return {"status": "ok", "agents_configured": len(agents)}

    @app.post("/v1/test/mock-agent/reset")
    async def reset_mock_agent() -> dict[str, Any]:
        agents = _find_mock_agents(orchestrator)
        for agent in agents:
            agent.responses = []
            agent.default_response = "Mock response"
            agent.response_delay = 0.1
        return {"status": "ok", "agents_reset": len(agents)}
