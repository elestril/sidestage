Now I have all the context needed. Let me produce the section content.

# Section 05: Mock Actor

## Overview

This section implements the MockLLMAgent class, test-only API routes for configuring it, the conditional injection point in `NPCActor._update_prompt()`, and `SIDESTAGE_PORT` environment variable support. Together these enable deterministic E2E testing of chat flows without requiring a real LLM.

**Dependencies:** Section 04 (E2E infrastructure) must be complete before E2E tests can use these components. However, the mock actor code itself can be implemented independently.

## Files to Create or Modify

| File | Action |
|------|--------|
| `src/sidestage/testing/__init__.py` | Create (empty package init) |
| `src/sidestage/testing/mock_actor.py` | Create (MockLLMAgent class) |
| `src/sidestage/testing/routes.py` | Create (test-only API endpoints) |
| `src/sidestage/actors.py` | Modify (`_update_prompt()` conditional) |
| `src/sidestage/orchestrator.py` | Modify (conditional test route registration) |
| `src/sidestage/server.py` | Modify (SIDESTAGE_PORT env var support) |
| `scripts/run-dev.sh` | Modify (pass SIDESTAGE_PORT to uvicorn) |
| `tests/unit/test_mock_actor.py` | Create (unit tests for MockLLMAgent) |
| `tests/unit/test_mock_actor_integration.py` | Create (integration point tests) |
| `tests/unit/test_mock_actor_routes.py` | Create (test-only route tests) |

## Tests First

All tests use existing project conventions: `@pytest.mark.anyio` for async tests, files named `test_*.py`, fixtures in `conftest.py`.

### Unit Tests: MockLLMAgent (`tests/unit/test_mock_actor.py`)

```python
"""Tests for the MockLLMAgent class."""

import pytest
from sidestage.testing.mock_actor import MockLLMAgent, MockResponse


@pytest.mark.anyio
async def test_arun_returns_next_response_from_queue():
    """MockLLMAgent.arun() should pop and return the first response from the queue."""


@pytest.mark.anyio
async def test_arun_uses_default_response_when_queue_empty():
    """When the response queue is empty, arun() should return default_response."""


@pytest.mark.anyio
async def test_arun_waits_response_delay_before_returning():
    """arun() should wait response_delay seconds before returning (simulates LLM thinking)."""


@pytest.mark.anyio
async def test_arun_returns_response_with_correct_event_type():
    """The returned AgentResponse should reflect the MockResponse's event_type field."""


@pytest.mark.anyio
async def test_arun_returns_response_with_correct_actor_id():
    """The returned AgentResponse should reflect the MockResponse's actor_id field."""


def test_mock_response_defaults():
    """MockResponse should default to event_type='ChatMessage' and delay=0.5."""
```

### Integration Point Tests (`tests/unit/test_mock_actor_integration.py`)

These tests verify the conditional in `NPCActor._update_prompt()`.

```python
"""Tests for the MockLLMAgent integration point in NPCActor."""

import os
import pytest
from unittest.mock import patch, MagicMock
from sidestage.actors import NPCActor


def test_update_prompt_creates_mock_agent_when_env_set():
    """When SIDESTAGE_MOCK_AGENT=1 is set, _update_prompt() should create a MockLLMAgent."""


def test_update_prompt_creates_litellm_agent_when_env_not_set():
    """When SIDESTAGE_MOCK_AGENT is not set, _update_prompt() should create a LiteLLMAgent."""


@pytest.mark.anyio
async def test_mock_agent_processes_chat_and_returns_canned_response():
    """End-to-end: NPCActor with mock agent should process a chat event and return the canned response."""
```

### Test-Only API Route Tests (`tests/unit/test_mock_actor_routes.py`)

```python
"""Tests for the test-only mock agent API endpoints."""

import pytest
from unittest.mock import patch


@pytest.mark.anyio
async def test_configure_sets_response_queue():
    """POST /v1/test/mock-agent/configure should set the response queue on all active mock agents."""


@pytest.mark.anyio
async def test_reset_clears_response_queue():
    """POST /v1/test/mock-agent/reset should clear the response queue on all active mock agents."""


@pytest.mark.anyio
async def test_endpoints_return_404_when_mock_agent_not_set():
    """Test endpoints should return 404 when SIDESTAGE_MOCK_AGENT is not set."""


@pytest.mark.anyio
async def test_configure_reaches_active_scene_mock_agents():
    """Configure endpoint should traverse active_scenes to find and update mock agents."""
```

## Implementation Details

### 1. MockLLMAgent Class

**File:** `/home/harald/src/sidestage/src/sidestage/testing/__init__.py`

Empty file to make `testing` a Python package.

**File:** `/home/harald/src/sidestage/src/sidestage/testing/mock_actor.py`

The `MockLLMAgent` class must implement the same `arun()` interface as `LiteLLMAgent` (defined in `/home/harald/src/sidestage/src/sidestage/agent.py`). The key interface:

```python
async def arun(self, message: str, context: str | None = None, stream: bool = False) -> AgentResponse
```

Where `AgentResponse` is a Pydantic `BaseModel` with a single `content: str` field, imported from `sidestage.agent`.

The mock should contain:

- A `MockResponse` dataclass with fields:
  - `body: str` -- the response text
  - `character_id: str | None = None`
  - `actor_id: str = "agent:co_author"`
  - `event_type: str = "ChatMessage"` -- must match the `EventType` enum values
  - `delay: float = 0.5` -- per-response delay override

- A `MockLLMAgent` class with fields:
  - `responses: list[MockResponse]` -- queue of canned responses, popped FIFO
  - `default_response: str` -- fallback text when queue is empty (default: `"Mock response"`)
  - `response_delay: float` -- base delay in seconds (default: `0.1` for tests, not `0.5` as in production)
  - `name: str` -- agent name, for compatibility with `LiteLLMAgent`

- The `arun()` method:
  1. Wait `response_delay` seconds (or the per-response `delay` if a queued response is used) using `asyncio.sleep()`
  2. If `responses` is non-empty, pop the first `MockResponse` and return `AgentResponse(content=response.body)`
  3. Otherwise return `AgentResponse(content=self.default_response)`

The `MockLLMAgent` does not need to handle tools, tracing, or any LiteLLM-specific functionality. It is a minimal stand-in.

### 2. Integration Point: `NPCActor._update_prompt()` Conditional

**File:** `/home/harald/src/sidestage/src/sidestage/actors.py`

Modify the `_update_prompt()` method (currently at line 73). Add a conditional check at the very beginning of the method, before any existing logic:

```python
def _update_prompt(self) -> None:
    """Load the appropriate prompt template and instantiate the LiteLLMAgent."""
    import os
    if os.environ.get("SIDESTAGE_MOCK_AGENT"):
        from sidestage.testing.mock_actor import MockLLMAgent
        char_name = self.character.name if self.character else "NPC"
        self.agent = MockLLMAgent(name=char_name)
        return

    # ... existing code unchanged ...
```

This is a minimal, early-return conditional. When `SIDESTAGE_MOCK_AGENT` is set to any truthy value (e.g., `"1"`), the method creates a `MockLLMAgent` and returns immediately, bypassing all LLM configuration, prompt template loading, and tool setup.

The key insight from the existing code: `_update_prompt()` is called by `Character.activate()` (in `/home/harald/src/sidestage/src/sidestage/character.py`, line 30). The scene activation flow goes: `Scene.activate()` -> iterates characters -> `character.activate()` -> `actor._update_prompt()`. So the mock agent is injected at exactly the right point in the lifecycle.

### 3. Test-Only API Endpoints

**File:** `/home/harald/src/sidestage/src/sidestage/testing/routes.py`

This module defines a function that registers test-only routes on a FastAPI app. The routes allow E2E tests to configure mock agent behavior dynamically.

The function signature:

```python
def register_test_routes(app: FastAPI, orchestrator: "SidestageOrchestrator") -> None:
    """Register test-only API routes for mock agent configuration.
    
    Only call this when SIDESTAGE_MOCK_AGENT is set.
    """
```

**Route: `POST /v1/test/mock-agent/configure`**

Request body (Pydantic model):

```python
class MockAgentConfigureRequest(BaseModel):
    responses: list[dict] = []  # Each dict has: body, event_type (optional), delay (optional)
    default_response: str | None = None
    response_delay: float | None = None
```

Behavior:
1. Traverse `orchestrator.active_scenes` -> each scene's `characters` dict -> each character's `actor`
2. For each `NPCActor` whose `.agent` is a `MockLLMAgent` instance:
   - If `responses` is provided, set `agent.responses` to a list of `MockResponse` objects built from the request dicts
   - If `default_response` is provided, set `agent.default_response`
   - If `response_delay` is provided, set `agent.response_delay`
3. Return `{"status": "ok", "agents_configured": count}` where `count` is the number of mock agents updated

**Route: `POST /v1/test/mock-agent/reset`**

Behavior:
1. Same traversal as configure
2. For each mock agent: clear `responses` list, reset `default_response` to `"Mock response"`, reset `response_delay` to `0.1`
3. Return `{"status": "ok", "agents_reset": count}`

**Important consideration:** The configure endpoint needs to reach agents in scenes that have already been activated. When the E2E test navigates to a page and sends a chat message, the scene gets activated (via `orchestrator.get_active_scene()`), which calls `_update_prompt()` and creates mock agents. The configure endpoint then updates those already-created agents. This means the typical E2E test flow is:

1. Navigate to page (triggers scene activation, which creates mock agents)
2. POST `/v1/test/mock-agent/configure` (updates the mock agents with specific responses)
3. Send chat message (mock agent returns the configured response)

If no scenes are active yet when configure is called, the endpoint should still succeed (with `agents_configured: 0`). The default responses will be used.

### 4. Conditional Route Registration in Orchestrator

**File:** `/home/harald/src/sidestage/src/sidestage/orchestrator.py`

Add a conditional at the end of `_setup_routes()` (or after `_setup_routes()` is called in `__init__`). The cleanest approach is to add it at the bottom of `_setup_routes()`:

```python
def _setup_routes(self) -> None:
    # ... existing routes ...

    # Test-only routes (mock agent configuration)
    if os.environ.get("SIDESTAGE_MOCK_AGENT"):
        from sidestage.testing.routes import register_test_routes
        register_test_routes(self.fastapi_app, self)
```

This requires adding `import os` at the top of orchestrator.py (it is already imported).

### 5. SIDESTAGE_PORT Environment Variable Support

**File:** `/home/harald/src/sidestage/src/sidestage/server.py`

The `main()` function currently hardcodes `--port` default to `8000`. Add support for `SIDESTAGE_PORT` env var so the E2E server fixture can control the port:

In the `main()` function, after argument parsing, check for the env var:

```python
port = int(os.environ.get("SIDESTAGE_PORT", str(args.port)))
```

Then use `port` instead of `args.port` in the `uvicorn.run()` call.

**File:** `/home/harald/src/sidestage/scripts/run-dev.sh`

The script currently ends with:

```bash
exec uv run sidestage --sidestage_dir . "$CAMPAIGN"
```

Modify to pass the port if `SIDESTAGE_PORT` is set:

```bash
PORT_ARGS=""
if [ -n "${SIDESTAGE_PORT:-}" ]; then
  PORT_ARGS="--port $SIDESTAGE_PORT"
fi

exec uv run sidestage --sidestage_dir . $PORT_ARGS "$CAMPAIGN"
```

This allows the E2E fixture to pass `SIDESTAGE_PORT=8001` as an environment variable when launching the server subprocess, and the server will bind to that port.

### 6. How the Pieces Connect

The flow for E2E test execution:

1. **E2E fixture** (from section 04) starts the server with `SIDESTAGE_MOCK_AGENT=1` and `SIDESTAGE_PORT=8001`
2. **Server** starts on port 8001, orchestrator registers test-only routes
3. **Scene activation** creates `NPCActor` instances; `_update_prompt()` detects `SIDESTAGE_MOCK_AGENT` and creates `MockLLMAgent` instances
4. **E2E test** calls `POST /v1/test/mock-agent/configure` to set up expected responses
5. **E2E test** sends a chat message via the UI
6. **NPCActor.process()** calls `self.agent.arun()` on the `MockLLMAgent`, which returns the configured canned response after a short delay
7. **Response** is broadcast to the frontend via WebSocket, just like a real LLM response

### 7. Existing Code Context

Key interfaces the mock must be compatible with:

**`AgentResponse`** (from `/home/harald/src/sidestage/src/sidestage/agent.py`):
```python
class AgentResponse(BaseModel):
    content: str
```

**`LiteLLMAgent.arun()` signature** (from the same file):
```python
async def arun(self, message: str, context: str | None = None, stream: bool = False) -> AgentResponse
```

**`NPCActor.process()` uses the agent** (from `/home/harald/src/sidestage/src/sidestage/actors.py`, line 199):
```python
response = await self.agent.arun(event.model.body, context=context_text)
```

It then checks `response.content` and creates an `EventModel` from it. The mock does not need to change any of this logic -- it just needs to return an `AgentResponse` with the expected `content` field.

**Scene character traversal** (from `/home/harald/src/sidestage/src/sidestage/scene.py`): Active scenes store characters in `self.characters: Dict[str, Character]`. Each `Character` has an `.actor` attribute. The test routes traverse: `orchestrator.active_scenes[scene_id].characters[char_id].actor.agent`.

### 8. Edge Cases and Notes

- The `MockLLMAgent` does not need `instructions`, `tools`, `model`, or any other `LiteLLMAgent`-specific constructor parameters. It is not a subclass of `LiteLLMAgent` -- it is a duck-typed replacement that implements the same `arun()` method.
- The `event_type` and `actor_id` fields on `MockResponse` are included for future use by the configure endpoint, but `NPCActor.process()` currently always creates the response `EventModel` with `EventType.CHAT_MESSAGE` and uses its own `self.actor_id`. To support custom event types (e.g., `Error`), the mock response's `event_type` would need to be plumbed through differently. For this section, the `MockResponse.body` is what matters -- it becomes `AgentResponse.content`.
- When `SIDESTAGE_MOCK_AGENT` is not set, the test routes (`/v1/test/mock-agent/*`) should not exist at all. Any request to those paths will naturally return 404 because the routes were never registered. No explicit 404 handler is needed.
- The `response_delay` should be kept short in tests (0.1s default) to avoid slow test runs, but non-zero to exercise the async timing behavior that the thinking indicator depends on.

## Implementation Notes

- Used `anyio.sleep()` instead of `asyncio.sleep()` for trio test backend compatibility (project tests run under both asyncio and trio via pytest-anyio).
- Added `# type: ignore[assignment]` on the duck-typed MockLLMAgent assignment in `_update_prompt()` since `self.agent` is typed as `LiteLLMAgent | None`.
- Moved `SIDESTAGE_PORT` resolution in `server.py` before the startup log message so the logged port is accurate.

## Tests

- `tests/unit/test_mock_actor.py`: 7 tests (MockLLMAgent unit tests)
- `tests/unit/test_mock_actor_integration.py`: 3 tests (NPCActor integration)
- `tests/unit/test_mock_actor_routes.py`: 5 tests (API route tests including 404 contract test)