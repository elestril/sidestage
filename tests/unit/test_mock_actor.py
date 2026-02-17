"""Tests for the MockLLMAgent class."""

import asyncio
import time
import pytest
from sidestage.testing.mock_actor import MockLLMAgent, MockResponse


@pytest.mark.anyio
async def test_arun_returns_next_response_from_queue():
    """MockLLMAgent.arun() should pop and return the first response from the queue."""
    agent = MockLLMAgent(name="test")
    agent.responses = [
        MockResponse(body="first"),
        MockResponse(body="second"),
    ]
    result = await agent.arun("hello")
    assert result.content == "first"
    result2 = await agent.arun("hello again")
    assert result2.content == "second"


@pytest.mark.anyio
async def test_arun_uses_default_response_when_queue_empty():
    """When the response queue is empty, arun() should return default_response."""
    agent = MockLLMAgent(name="test")
    result = await agent.arun("hello")
    assert result.content == "Mock response"


@pytest.mark.anyio
async def test_arun_waits_response_delay_before_returning():
    """arun() should wait response_delay seconds before returning (simulates LLM thinking)."""
    agent = MockLLMAgent(name="test", response_delay=0.2)
    start = time.monotonic()
    await agent.arun("hello")
    elapsed = time.monotonic() - start
    assert elapsed >= 0.15  # allow small tolerance


@pytest.mark.anyio
async def test_arun_uses_per_response_delay():
    """arun() should use the per-response delay when a queued response has one."""
    agent = MockLLMAgent(name="test", response_delay=0.01)
    agent.responses = [MockResponse(body="slow", delay=0.2)]
    start = time.monotonic()
    await agent.arun("hello")
    elapsed = time.monotonic() - start
    assert elapsed >= 0.15


@pytest.mark.anyio
async def test_arun_returns_response_with_correct_content():
    """The returned AgentResponse should have the MockResponse's body as content."""
    agent = MockLLMAgent(name="test")
    agent.responses = [MockResponse(body="custom text")]
    result = await agent.arun("hello")
    assert result.content == "custom text"


def test_mock_response_defaults():
    """MockResponse should default to event_type='ChatMessage' and delay=0.5."""
    r = MockResponse()
    assert r.event_type == "ChatMessage"
    assert r.delay == 0.5
    assert r.body == "Mock response"
    assert r.actor_id == "agent:co_author"
    assert r.character_id is None


def test_mock_agent_has_name():
    """MockLLMAgent should store a name attribute for compatibility."""
    agent = MockLLMAgent(name="Gandalf")
    assert agent.name == "Gandalf"
