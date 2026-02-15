"""Unit tests for agent context injection and NPCActor memory integration."""

import copy
import json
from datetime import datetime, timezone
from typing import Any

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from sidestage.agent import LiteLLMAgent, AgentResponse
from sidestage.actors import NPCActor
from sidestage.character import Character
from sidestage.event import Event
from sidestage.models import CharacterModel, EventModel, EventType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_completion_response(content: str | None = "Hello", tool_calls: list[Any] | None = None) -> MagicMock:
    """Build a mock litellm.acompletion response."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_event(actor_id: str = "user", body: str = "Hello", scene_id: str = "scene_01") -> Event:
    """Build an Event with a mock scene for testing NPCActor.process()."""
    model = EventModel(
        id="m1",
        name="Msg",
        body=body,
        event_type=EventType.CHAT_MESSAGE,
        scene_id=scene_id,
        gametime=0,
        walltime=datetime.now(timezone.utc),
        actor_id=actor_id,
        character_id="user",
    )
    event = Event(model=model)
    event.scene = MagicMock()
    event.scene.process = AsyncMock()
    return event


# ---------------------------------------------------------------------------
# arun() context parameter tests
# ---------------------------------------------------------------------------


class TestArunContextParameter:
    """Tests for LiteLLMAgent.arun() context injection."""

    @pytest.mark.anyio
    @patch("sidestage.agent.litellm.acompletion", new_callable=AsyncMock)
    async def test_arun_without_context_backwards_compatible(self, mock_completion: AsyncMock) -> None:
        """arun without context parameter works as before (backwards compatible)."""
        # Capture messages at call time (before the list is mutated)
        captured: dict[str, Any] = {}
        async def _capture(**kwargs: Any) -> MagicMock:
            captured["messages"] = copy.deepcopy(kwargs["messages"])
            return _mock_completion_response("Hi there")
        mock_completion.side_effect = _capture

        agent = LiteLLMAgent(
            name="Test", model="openai/test",
            instructions=["You are helpful."],
        )
        result = await agent.arun("Hello")

        assert isinstance(result, AgentResponse)
        messages = captured["messages"]
        # Should have exactly 2 messages: system (instructions) + user
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Hello"

    @pytest.mark.anyio
    @patch("sidestage.agent.litellm.acompletion", new_callable=AsyncMock)
    async def test_arun_with_context_inserts_system_message(self, mock_completion: AsyncMock) -> None:
        """arun with context inserts a system message between system prompt and user message."""
        captured: dict[str, Any] = {}
        async def _capture(**kwargs: Any) -> MagicMock:
            captured["messages"] = copy.deepcopy(kwargs["messages"])
            return _mock_completion_response("Got it")
        mock_completion.side_effect = _capture

        agent = LiteLLMAgent(
            name="Test", model="openai/test",
            instructions=["You are helpful."],
        )
        result = await agent.arun("Hello", context="Memory context here")

        messages = captured["messages"]
        # Should have 3 messages: system (instructions) + system (context) + user
        assert len(messages) == 3
        assert messages[0]["role"] == "system"
        assert "You are helpful" in messages[0]["content"]
        assert messages[1]["role"] == "system"
        assert messages[1]["content"] == "Memory context here"
        assert messages[2]["role"] == "user"
        assert messages[2]["content"] == "Hello"

    @pytest.mark.anyio
    @patch("sidestage.agent.litellm.acompletion", new_callable=AsyncMock)
    async def test_arun_with_empty_string_context_skipped(self, mock_completion: AsyncMock) -> None:
        """arun with empty string context is equivalent to no context."""
        captured: dict[str, Any] = {}
        async def _capture(**kwargs: Any) -> MagicMock:
            captured["messages"] = copy.deepcopy(kwargs["messages"])
            return _mock_completion_response("Ok")
        mock_completion.side_effect = _capture

        agent = LiteLLMAgent(
            name="Test", model="openai/test",
            instructions=["You are helpful."],
        )
        await agent.arun("Hello", context="")

        messages = captured["messages"]
        # Empty context should be skipped, so exactly 2 messages
        assert len(messages) == 2

    @pytest.mark.anyio
    @patch("sidestage.agent.litellm.acompletion", new_callable=AsyncMock)
    async def test_arun_with_context_preserves_tool_calling(self, mock_completion: AsyncMock) -> None:
        """arun with context preserves tool calling behavior."""
        # Capture messages from first call
        captured_calls: list[Any] = []

        tool_call = MagicMock()
        tool_call.id = "call_1"
        tool_call.function.name = "my_tool"
        tool_call.function.arguments = '{"arg": "value"}'

        responses = [
            _mock_completion_response(content=None, tool_calls=[tool_call]),
            _mock_completion_response(content="Done after tool"),
        ]
        call_idx = 0

        async def _capture(**kwargs: Any) -> MagicMock:
            nonlocal call_idx
            captured_calls.append(copy.deepcopy(kwargs["messages"]))
            resp = responses[call_idx]
            call_idx += 1
            return resp

        mock_completion.side_effect = _capture

        async def my_tool(arg: str) -> str:
            """A test tool."""
            return f"result: {arg}"

        agent = LiteLLMAgent(
            name="Test", model="openai/test",
            instructions=["You are helpful."],
            tools=[my_tool],
        )
        result = await agent.arun("Do something", context="Memory context")

        assert result.content == "Done after tool"
        # First call should include context system message
        first_call_messages = captured_calls[0]
        assert len(first_call_messages) == 3
        assert first_call_messages[1]["role"] == "system"
        assert first_call_messages[1]["content"] == "Memory context"


# ---------------------------------------------------------------------------
# NPCActor memory integration tests
# ---------------------------------------------------------------------------


class TestNPCActorMemoryIntegration:
    """Tests for NPCActor memory dependencies and context assembly."""

    def test_defaults_without_memory_args(self) -> None:
        """NPCActor works without memory-related arguments."""
        actor = NPCActor(actor_id="agent:c1")
        assert actor.graph_client is None
        assert actor.embed_config is None
        assert actor.health is None
        assert actor.scene_id is None

    def test_accepts_memory_kwargs(self) -> None:
        """NPCActor stores memory-related keyword arguments."""
        mock_client = MagicMock()
        mock_config = MagicMock()
        mock_health = MagicMock()

        char = CharacterModel(id="c1", name="Alice", body="I am Alice")
        actor = NPCActor(
            actor_id="agent:c1",
            character=char,
            graph_client=mock_client,
            embed_config=mock_config,
            health=mock_health,
            scene_id="scene_01",
            present_character_ids=["c2", "c3"],
            context_limit=8192,
        )
        assert actor.graph_client is mock_client
        assert actor.embed_config is mock_config
        assert actor.health is mock_health
        assert actor.scene_id == "scene_01"
        assert actor.present_character_ids == ["c2", "c3"]
        assert actor.context_limit == 8192

    @pytest.mark.anyio
    @patch("sidestage.memory.context.assemble_context", new_callable=AsyncMock)
    async def test_process_assembles_context_when_graph_available(self, mock_assemble: AsyncMock) -> None:
        """process() calls assemble_context when graph_client is available."""
        from sidestage.memory.models import ContextResult
        mock_assemble.return_value = ContextResult(
            memory_text="## World\n- War rages", chat_text="[c2]: Hello", token_estimate=50,
        )

        char = CharacterModel(id="c1", name="Alice", body="I am Alice")
        actor = NPCActor(
            actor_id="agent:c1",
            character=char,
            graph_client=MagicMock(),
            scene_id="scene_01",
            present_character_ids=["c2"],
            context_limit=4096,
        )
        actor.agent = MagicMock()
        actor.agent.arun = AsyncMock(return_value=MagicMock(content="Hi"))

        event = _make_event()
        await actor.process(event)

        mock_assemble.assert_awaited_once()
        # arun should be called with the assembled context
        actor.agent.arun.assert_awaited_once()
        context_val = actor.agent.arun.call_args.kwargs.get("context")
        assert context_val == "## World\n- War rages\n\n[c2]: Hello"

    @pytest.mark.anyio
    async def test_process_no_context_without_graph(self) -> None:
        """process() passes context=None when graph_client is not available."""
        char = CharacterModel(id="c1", name="Alice", body="I am Alice")
        actor = NPCActor(actor_id="agent:c1", character=char)  # No graph_client
        actor.agent = MagicMock()
        actor.agent.arun = AsyncMock(return_value=MagicMock(content="Hi"))

        event = _make_event()
        await actor.process(event)

        actor.agent.arun.assert_awaited_once()
        call_args = actor.agent.arun.call_args
        # context should be None (no graph client)
        context_val = call_args.kwargs.get("context") if call_args.kwargs else None
        assert context_val is None

    @pytest.mark.anyio
    @patch("sidestage.memory.context.assemble_context", new_callable=AsyncMock)
    async def test_process_graceful_degradation_on_context_failure(self, mock_assemble: AsyncMock) -> None:
        """process() proceeds without context if assemble_context raises."""
        mock_assemble.side_effect = Exception("graph down")

        char = CharacterModel(id="c1", name="Alice", body="I am Alice")
        actor = NPCActor(
            actor_id="agent:c1",
            character=char,
            graph_client=MagicMock(),
            scene_id="scene_01",
        )
        actor.agent = MagicMock()
        actor.agent.arun = AsyncMock(return_value=MagicMock(content="Hi anyway"))

        event = _make_event()
        await actor.process(event)

        # Agent should still be called (graceful degradation)
        actor.agent.arun.assert_awaited_once()

    def test_memory_tools_added_when_graph_available(self) -> None:
        """MemoryTools methods are added to agent tools when graph_client is set."""
        char = CharacterModel(id="c1", name="Alice", body="I am Alice")
        campaign = MagicMock()
        campaign.get_llm_config.return_value = MagicMock(
            provider="llama_cpp", model="test-model",
            base_url="http://localhost:8080/v1", api_key="sk-test",
        )

        actor = NPCActor(
            actor_id="agent:c1",
            character=char,
            scene_logic=campaign,
            graph_client=MagicMock(),
            embed_config=MagicMock(),
            health=MagicMock(),
            scene_id="scene_01",
        )
        actor._update_prompt()

        assert actor.agent is not None
        tool_names = [t.__name__ for t in actor.agent.tools]
        assert "update_scene_memory" in tool_names
        assert "update_character_memory" in tool_names

    def test_no_memory_tools_without_graph(self) -> None:
        """No memory tools added when graph_client is None."""
        char = CharacterModel(id="c1", name="Alice", body="I am Alice")
        campaign = MagicMock()
        campaign.get_llm_config.return_value = MagicMock(
            provider="llama_cpp", model="test-model",
            base_url="http://localhost:8080/v1", api_key="sk-test",
        )

        actor = NPCActor(
            actor_id="agent:c1",
            character=char,
            scene_logic=campaign,
        )  # No graph_client
        actor._update_prompt()

        assert actor.agent is not None
        tool_names = [t.__name__ for t in actor.agent.tools]
        assert "update_scene_memory" not in tool_names
        assert "update_character_memory" not in tool_names

    def test_no_memory_tools_without_health(self) -> None:
        """No memory tools added when health is None (even if graph_client is set)."""
        char = CharacterModel(id="c1", name="Alice", body="I am Alice")
        campaign = MagicMock()
        campaign.get_llm_config.return_value = MagicMock(
            provider="llama_cpp", model="test-model",
            base_url="http://localhost:8080/v1", api_key="sk-test",
        )

        actor = NPCActor(
            actor_id="agent:c1",
            character=char,
            scene_logic=campaign,
            graph_client=MagicMock(),
            scene_id="scene_01",
            health=None,  # health is None
        )
        actor._update_prompt()

        assert actor.agent is not None
        tool_names = [t.__name__ for t in actor.agent.tools]
        assert "update_scene_memory" not in tool_names
        assert "update_character_memory" not in tool_names


# ---------------------------------------------------------------------------
# Character wrapper tests
# ---------------------------------------------------------------------------


class TestCharacterWrapper:
    """Tests for the new Character(model, actor) wrapper."""

    def test_character_stores_model_and_actor(self) -> None:
        """Character stores model and actor references."""
        char = CharacterModel(id="c1", name="Alice", body="I am Alice")
        actor = NPCActor(actor_id="agent:c1", character=char)
        logic = Character(model=char, actor=actor)
        assert logic.data is char
        assert logic.actor is actor

    @pytest.mark.anyio
    async def test_activate_calls_update_prompt_for_npc(self) -> None:
        """activate() calls _update_prompt() for NPCActor."""
        char = CharacterModel(id="c1", name="Alice", body="I am Alice")
        campaign = MagicMock()
        campaign.get_llm_config.return_value = MagicMock(
            provider="llama_cpp", model="test-model",
            base_url="http://localhost:8080/v1", api_key="sk-test",
        )

        actor = NPCActor(actor_id="agent:c1", character=char, scene_logic=campaign)
        logic = Character(model=char, actor=actor)
        await logic.activate()
        assert actor.agent is not None

    @pytest.mark.anyio
    async def test_deactivate_clears_agent(self) -> None:
        """deactivate() clears the NPCActor agent."""
        char = CharacterModel(id="c1", name="Alice", body="I am Alice")
        actor = NPCActor(actor_id="agent:c1", character=char)
        actor.agent = MagicMock()
        logic = Character(model=char, actor=actor)
        await logic.deactivate()
        assert actor.agent is None


# ---------------------------------------------------------------------------
# Campaign health and embed validation tests
# ---------------------------------------------------------------------------


class TestCampaignHealthWiring:
    """Tests for Campaign CampaignHealth instance and embed validation."""

    @pytest.mark.anyio
    @patch("sidestage.campaign.connect", new_callable=AsyncMock)
    @patch("sidestage.memory.embeddings.validate_embed_config", new_callable=AsyncMock)
    async def test_start_graph_validates_embeddings(self, mock_validate: AsyncMock, mock_connect: AsyncMock) -> None:
        """start_graph validates embeddings when embed config is present."""
        from sidestage.campaign import Campaign
        from sidestage.config import LLMConfig, SidestageConfig
        from sidestage.graph import GraphConfig

        mock_validate.return_value = 384
        mock_connect.return_value = MagicMock()

        # Create a minimal Campaign-like object to test start_graph
        campaign = object.__new__(Campaign)
        campaign.name = "test"
        campaign.config = SidestageConfig(
            llms={
                "default": LLMConfig(),
                "embed": LLMConfig(provider="llama_cpp", model="embed-model"),
            },
            graph=GraphConfig(),
        )
        campaign.graph_client = None
        campaign.world_tools = MagicMock()

        from sidestage.health import CampaignHealth
        campaign.health = CampaignHealth()

        await campaign.start_graph()

        mock_validate.assert_awaited_once()
        assert campaign.config.graph.vector_dimension == 384

    @pytest.mark.anyio
    @patch("sidestage.campaign.connect", new_callable=AsyncMock)
    @patch("sidestage.memory.embeddings.validate_embed_config", new_callable=AsyncMock)
    async def test_start_graph_degrades_on_embed_failure(self, mock_validate: AsyncMock, mock_connect: AsyncMock) -> None:
        """start_graph sets health to DEGRADED when embed validation fails."""
        from sidestage.campaign import Campaign
        from sidestage.config import LLMConfig, SidestageConfig
        from sidestage.graph import GraphConfig
        from sidestage.health import CampaignHealth, HealthStatus

        mock_validate.return_value = None  # validation failed
        mock_connect.return_value = MagicMock()

        campaign = object.__new__(Campaign)
        campaign.name = "test"
        campaign.config = SidestageConfig(
            llms={
                "default": LLMConfig(),
                "embed": LLMConfig(provider="llama_cpp", model="embed-model"),
            },
            graph=GraphConfig(),
        )
        campaign.graph_client = None
        campaign.world_tools = MagicMock()
        campaign.health = CampaignHealth()

        await campaign.start_graph()

        assert campaign.health.status == HealthStatus.DEGRADED

    @pytest.mark.anyio
    @patch("sidestage.campaign.connect", new_callable=AsyncMock)
    async def test_start_graph_no_embed_config_skips_validation(self, mock_connect: AsyncMock) -> None:
        """start_graph skips embed validation when no embed config."""
        from sidestage.campaign import Campaign
        from sidestage.config import LLMConfig, SidestageConfig
        from sidestage.graph import GraphConfig
        from sidestage.health import CampaignHealth

        mock_connect.return_value = MagicMock()

        campaign = object.__new__(Campaign)
        campaign.name = "test"
        campaign.config = SidestageConfig(
            llms={"default": LLMConfig()},  # No embed config
            graph=GraphConfig(),
        )
        campaign.graph_client = None
        campaign.world_tools = MagicMock()
        campaign.health = CampaignHealth()

        await campaign.start_graph()

        # Should complete without error, health stays HEALTHY
        assert campaign.graph_client is not None
