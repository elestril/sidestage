"""Tests for backend tracing instrumentation.

Verifies that spans are created with correct names, attributes, and hierarchy
at each instrumentation point.
"""

import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

from sidestage.schemas import Character, ChatMessage, Scene


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _SpanCollector(SpanExporter):
    """Collects spans for test assertions."""

    def __init__(self):
        self._spans: list = []

    def export(self, spans):
        self._spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass

    def get_finished_spans(self) -> list:
        return list(self._spans)

    def clear(self):
        self._spans.clear()


@pytest.fixture
def otel_exporter():
    """Set up a span collector and TracerProvider for capturing spans.

    Resets the global OTel state, creates a fresh provider, and replaces
    module-level tracer objects in all instrumented modules with real SDK
    tracers bound to the new provider.  This bypasses the ProxyTracer
    caching issue where ``_real_tracer`` sticks to a stale provider.
    """
    # Reset OTel state to allow setting a new provider
    trace._TRACER_PROVIDER_SET_ONCE._done = False
    trace._TRACER_PROVIDER = None

    exporter = _SpanCollector()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Replace module-level tracers with real (non-proxy) SDK tracers so
    # they emit spans on the new provider regardless of prior caching.
    import sidestage.scene as _scene
    import sidestage.character as _char
    import sidestage.agent as _agent
    import sidestage.memory.context as _ctx
    import sidestage.memory.tools as _tools
    import sidestage.campaign as _campaign

    _scene.tracer = provider.get_tracer("sidestage.scene")
    _char.tracer = provider.get_tracer("sidestage.character")
    _agent.tracer = provider.get_tracer("sidestage.agent")
    _ctx.tracer = provider.get_tracer("sidestage.memory.context")
    _tools.tracer = provider.get_tracer("sidestage.memory.tools")
    _campaign.tracer = provider.get_tracer("sidestage.campaign")

    yield exporter
    provider.shutdown()


def _make_chat_message(**overrides) -> ChatMessage:
    defaults = dict(
        id="msg_test1",
        name="Test Message",
        body="Hello",
        actor_id="user",
        character_id="user",
        message="Hello",
        scene_id="scene_01",
        gametime=0,
        walltime="2025-01-01T00:00:00",
    )
    defaults.update(overrides)
    return ChatMessage(**defaults)


def _make_scene(**overrides) -> Scene:
    defaults = dict(
        id="scene_01",
        name="Test Scene",
        body="A test scene",
    )
    defaults.update(overrides)
    return Scene(**defaults)


def _make_character(**overrides) -> Character:
    defaults = dict(
        id="char_npc1",
        name="NPC One",
        body="A test NPC",
    )
    defaults.update(overrides)
    return Character(**defaults)


def _find_spans(exporter, name):
    return [s for s in exporter.get_finished_spans() if s.name == name]


# ===========================================================================
# 4.1 SceneLogic._process_event tests
# ===========================================================================


class TestProcessEvent:
    @pytest.mark.anyio
    async def test_creates_root_span(self, otel_exporter):
        from sidestage.scene import SceneLogic

        storage = MagicMock()
        agent = MagicMock()
        scene_data = _make_scene()
        logic = SceneLogic(storage, agent, scene_data)
        logic._broadcast_fn = None

        msg = _make_chat_message()
        await logic._process_event(msg)

        spans = _find_spans(otel_exporter, "scene.process_event")
        assert len(spans) == 1

    @pytest.mark.anyio
    async def test_root_span_attributes(self, otel_exporter):
        from sidestage.scene import SceneLogic

        storage = MagicMock()
        agent = MagicMock()
        scene_data = _make_scene()
        logic = SceneLogic(storage, agent, scene_data)
        logic._broadcast_fn = None

        msg = _make_chat_message(scene_id="scene_01", actor_id="user", id="msg_x")
        await logic._process_event(msg)

        span = _find_spans(otel_exporter, "scene.process_event")[0]
        assert span.attributes["sidestage.scene.id"] == "scene_01"
        assert span.attributes["sidestage.event.id"] == "msg_x"
        assert span.attributes["sidestage.event.type"] == "ChatMessage"
        assert span.attributes["sidestage.actor.id"] == "user"

    @pytest.mark.anyio
    async def test_non_chatmessage_no_span(self, otel_exporter):
        from sidestage.scene import SceneLogic
        from sidestage.schemas import Event

        storage = MagicMock()
        agent = MagicMock()
        scene_data = _make_scene()
        logic = SceneLogic(storage, agent, scene_data)

        event = Event(id="evt_1", name="Test", body="test", scene_id="s1", gametime=0, walltime="2025-01-01")
        await logic._process_event(event)

        spans = _find_spans(otel_exporter, "scene.process_event")
        assert len(spans) == 0

    @pytest.mark.anyio
    async def test_exception_sets_error_status(self, otel_exporter):
        from sidestage.scene import SceneLogic

        storage = MagicMock()
        storage.update_scene = MagicMock(side_effect=RuntimeError("db error"))
        agent = MagicMock()
        scene_data = _make_scene()
        logic = SceneLogic(storage, agent, scene_data)

        msg = _make_chat_message()
        with pytest.raises(RuntimeError):
            await logic._process_event(msg)

        span = _find_spans(otel_exporter, "scene.process_event")[0]
        assert span.status.status_code.name == "ERROR"


# ===========================================================================
# 4.2 SceneLogic._dispatch_to_npcs tests
# ===========================================================================


class TestDispatchToNpcs:
    @pytest.mark.anyio
    async def test_creates_dispatch_span(self, otel_exporter):
        from sidestage.scene import SceneLogic

        storage = MagicMock()
        agent = MagicMock()
        scene_data = _make_scene()
        logic = SceneLogic(storage, agent, scene_data)

        msg = _make_chat_message()
        await logic._dispatch_to_npcs(msg)

        spans = _find_spans(otel_exporter, "scene.dispatch_to_npcs")
        assert len(spans) == 1

    @pytest.mark.anyio
    async def test_npc_count_attribute(self, otel_exporter):
        from sidestage.scene import SceneLogic
        from sidestage.character import CharacterLogic

        storage = MagicMock()
        agent = MagicMock()
        scene_data = _make_scene()
        logic = SceneLogic(storage, agent, scene_data)

        # Add mock characters
        char1 = MagicMock()
        char1.actor = MagicMock()
        char1.actor.on_event = AsyncMock()
        char1.data = MagicMock()
        char1.data.name = "NPC1"
        logic.characters = {"c1": char1}

        msg = _make_chat_message()
        await logic._dispatch_to_npcs(msg)

        span = _find_spans(otel_exporter, "scene.dispatch_to_npcs")[0]
        assert span.attributes["sidestage.npc_count"] == 1


# ===========================================================================
# 4.3 AgentActor.on_event tests
# ===========================================================================


class TestAgentOnEvent:
    @pytest.mark.anyio
    async def test_creates_on_event_span(self, otel_exporter):
        from sidestage.character import AgentActor

        char = _make_character()
        scene_logic = MagicMock()
        scene_logic.agent = MagicMock()
        scene_logic.agent.tools = []
        scene_logic.agent.model = "test-model"
        scene_logic.agent.api_base = None
        scene_logic.agent.api_key = None
        scene_logic.agent.debug_mode = False

        actor = AgentActor(char, scene_logic)
        actor.agent = MagicMock()
        actor.agent.arun = AsyncMock(return_value=MagicMock(content=None))

        msg = _make_chat_message()
        await actor.on_event(msg)

        spans = _find_spans(otel_exporter, "agent.on_event")
        assert len(spans) == 1

    @pytest.mark.anyio
    async def test_on_event_character_attributes(self, otel_exporter):
        from sidestage.character import AgentActor

        char = _make_character(id="char_abc", name="TestNPC")
        scene_logic = MagicMock()
        scene_logic.agent = MagicMock()
        scene_logic.agent.tools = []
        scene_logic.agent.model = "test-model"
        scene_logic.agent.api_base = None
        scene_logic.agent.api_key = None
        scene_logic.agent.debug_mode = False

        actor = AgentActor(char, scene_logic)
        actor.agent = MagicMock()
        actor.agent.arun = AsyncMock(return_value=MagicMock(content=None))

        msg = _make_chat_message()
        await actor.on_event(msg)

        span = _find_spans(otel_exporter, "agent.on_event")[0]
        assert span.attributes["sidestage.character.id"] == "char_abc"
        assert span.attributes["sidestage.character.name"] == "TestNPC"

    @pytest.mark.anyio
    async def test_on_event_exception_sets_error(self, otel_exporter):
        from sidestage.character import AgentActor

        char = _make_character()
        scene_logic = MagicMock()
        scene_logic.agent = MagicMock()
        scene_logic.agent.tools = []
        scene_logic.agent.model = "test-model"
        scene_logic.agent.api_base = None
        scene_logic.agent.api_key = None
        scene_logic.agent.debug_mode = False

        actor = AgentActor(char, scene_logic)
        actor.agent = MagicMock()
        actor.agent.arun = AsyncMock(side_effect=RuntimeError("agent error"))

        msg = _make_chat_message()
        with pytest.raises(RuntimeError):
            await actor.on_event(msg)

        span = _find_spans(otel_exporter, "agent.on_event")[0]
        assert span.status.status_code.name == "ERROR"


# ===========================================================================
# 4.4 assemble_context tests
# ===========================================================================


class TestAssembleContext:
    @pytest.mark.anyio
    async def test_creates_span(self, otel_exporter):
        from sidestage.memory.context import assemble_context
        from sidestage.memory.models import ContextMemories

        mock_client = MagicMock()
        mock_memories = ContextMemories(
            world_facts=[],
            common_scene_memory=None,
            private_scene_memory=None,
            character_memories={},
        )
        with patch("sidestage.memory.context.get_memories_for_context", new_callable=AsyncMock, return_value=mock_memories):
            with patch("sidestage.memory.context.touch_memory", new_callable=AsyncMock):
                result = await assemble_context(
                    client=mock_client,
                    owner_id="char_1",
                    scene_id="scene_01",
                    present_character_ids=[],
                    recent_messages=[],
                    context_limit=4096,
                )

        spans = _find_spans(otel_exporter, "memory.assemble_context")
        assert len(spans) == 1

    @pytest.mark.anyio
    async def test_span_attributes(self, otel_exporter):
        from sidestage.memory.context import assemble_context
        from sidestage.memory.models import ContextMemories

        mock_client = MagicMock()
        mock_memories = ContextMemories(
            world_facts=[],
            common_scene_memory=None,
            private_scene_memory=None,
            character_memories={},
        )
        with patch("sidestage.memory.context.get_memories_for_context", new_callable=AsyncMock, return_value=mock_memories):
            with patch("sidestage.memory.context.touch_memory", new_callable=AsyncMock):
                await assemble_context(
                    client=mock_client,
                    owner_id="char_owner",
                    scene_id="scene_ctx",
                    present_character_ids=[],
                    recent_messages=[],
                    context_limit=4096,
                )

        span = _find_spans(otel_exporter, "memory.assemble_context")[0]
        assert span.attributes["sidestage.owner_id"] == "char_owner"
        assert span.attributes["sidestage.scene.id"] == "scene_ctx"


# ===========================================================================
# 4.5 LiteLLMAgent.arun tests
# ===========================================================================


class TestAgentArun:
    @pytest.mark.anyio
    async def test_creates_agent_run_span(self, otel_exporter):
        from sidestage.agent import LiteLLMAgent

        agent = LiteLLMAgent(name="test", model="test-model")

        mock_msg = MagicMock()
        mock_msg.content = "Hello back"
        mock_msg.tool_calls = None

        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=mock_msg, finish_reason="stop")]
        mock_resp.usage = None

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
            await agent.arun("Hello")

        spans = _find_spans(otel_exporter, "agent.run")
        assert len(spans) == 1
        assert spans[0].attributes["gen_ai.request.model"] == "test-model"

    @pytest.mark.anyio
    async def test_llm_completion_span(self, otel_exporter):
        from sidestage.agent import LiteLLMAgent

        agent = LiteLLMAgent(name="test", model="test-model")

        mock_msg = MagicMock()
        mock_msg.content = "Response"
        mock_msg.tool_calls = None

        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=mock_msg, finish_reason="stop")]
        mock_resp.usage = None

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
            await agent.arun("Hello")

        spans = _find_spans(otel_exporter, "llm.completion")
        assert len(spans) == 1
        assert spans[0].attributes["agent.turn"] == 1

    @pytest.mark.anyio
    async def test_token_usage_attributes(self, otel_exporter):
        from sidestage.agent import LiteLLMAgent

        agent = LiteLLMAgent(name="test", model="test-model")

        mock_msg = MagicMock()
        mock_msg.content = "Response"
        mock_msg.tool_calls = None

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 20

        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=mock_msg, finish_reason="stop")]
        mock_resp.usage = mock_usage

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
            await agent.arun("Hello")

        span = _find_spans(otel_exporter, "llm.completion")[0]
        assert span.attributes["gen_ai.usage.input_tokens"] == 10
        assert span.attributes["gen_ai.usage.output_tokens"] == 20

    @pytest.mark.anyio
    async def test_token_usage_skipped_when_none(self, otel_exporter):
        from sidestage.agent import LiteLLMAgent

        agent = LiteLLMAgent(name="test", model="test-model")

        mock_msg = MagicMock()
        mock_msg.content = "Response"
        mock_msg.tool_calls = None

        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=mock_msg, finish_reason="stop")]
        mock_resp.usage = None

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
            await agent.arun("Hello")

        span = _find_spans(otel_exporter, "llm.completion")[0]
        assert "gen_ai.usage.input_tokens" not in span.attributes

    @pytest.mark.anyio
    async def test_tool_execute_span(self, otel_exporter):
        from sidestage.agent import LiteLLMAgent

        def my_tool(arg1: str) -> str:
            """A test tool."""
            return "tool result"

        agent = LiteLLMAgent(name="test", model="test-model", tools=[my_tool])

        # First response: tool call
        mock_tool_call = MagicMock()
        mock_tool_call.id = "tc_1"
        mock_tool_call.function.name = "my_tool"
        mock_tool_call.function.arguments = '{"arg1": "value"}'

        mock_msg1 = MagicMock()
        mock_msg1.content = None
        mock_msg1.tool_calls = [mock_tool_call]

        # Second response: final answer
        mock_msg2 = MagicMock()
        mock_msg2.content = "Done"
        mock_msg2.tool_calls = None

        mock_resp1 = MagicMock()
        mock_resp1.choices = [MagicMock(message=mock_msg1, finish_reason="tool_calls")]
        mock_resp1.usage = None

        mock_resp2 = MagicMock()
        mock_resp2.choices = [MagicMock(message=mock_msg2, finish_reason="stop")]
        mock_resp2.usage = None

        with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=[mock_resp1, mock_resp2]):
            await agent.arun("Use the tool")

        tool_spans = _find_spans(otel_exporter, "tool.execute")
        assert len(tool_spans) == 1
        assert tool_spans[0].attributes["tool.name"] == "my_tool"

    @pytest.mark.anyio
    async def test_llm_exception_sets_error(self, otel_exporter):
        from sidestage.agent import LiteLLMAgent

        agent = LiteLLMAgent(name="test", model="test-model")

        with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=RuntimeError("LLM down")):
            await agent.arun("Hello")

        span = _find_spans(otel_exporter, "llm.completion")[0]
        assert span.status.status_code.name == "ERROR"

    @pytest.mark.anyio
    async def test_llm_error_still_sets_turn_count(self, otel_exporter):
        from sidestage.agent import LiteLLMAgent

        agent = LiteLLMAgent(name="test", model="test-model")

        with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=RuntimeError("LLM down")):
            await agent.arun("Hello")

        span = _find_spans(otel_exporter, "agent.run")[0]
        assert span.attributes["agent.turn_count"] == 1

    @pytest.mark.anyio
    async def test_turn_count_on_parent_span(self, otel_exporter):
        from sidestage.agent import LiteLLMAgent

        agent = LiteLLMAgent(name="test", model="test-model")

        mock_msg = MagicMock()
        mock_msg.content = "Response"
        mock_msg.tool_calls = None

        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=mock_msg, finish_reason="stop")]
        mock_resp.usage = None

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
            await agent.arun("Hello")

        span = _find_spans(otel_exporter, "agent.run")[0]
        assert span.attributes["agent.turn_count"] == 1


# ===========================================================================
# 4.6 Memory tool operations tests
# ===========================================================================


class TestMemoryToolTracing:
    @pytest.mark.anyio
    async def test_update_scene_memory_span(self, otel_exporter):
        from sidestage.memory.tools import MemoryTools

        mock_client = MagicMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem_1"

        with patch("sidestage.memory.tools.upsert_scene_memory", new_callable=AsyncMock, return_value=mock_memory):
            tools = MemoryTools(
                client=mock_client, embed_config=None, health=MagicMock(),
                owner_id="char_1", scene_id="scene_01",
            )
            await tools.update_scene_memory("Some content")

        spans = _find_spans(otel_exporter, "memory.update_scene_memory")
        assert len(spans) == 1

    @pytest.mark.anyio
    async def test_update_character_memory_span(self, otel_exporter):
        from sidestage.memory.tools import MemoryTools

        mock_client = MagicMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem_2"

        with patch("sidestage.memory.tools.upsert_character_memory", new_callable=AsyncMock, return_value=mock_memory):
            tools = MemoryTools(
                client=mock_client, embed_config=None, health=MagicMock(),
                owner_id="char_1", scene_id="scene_01",
            )
            await tools.update_character_memory("char_2", "Impressions")

        spans = _find_spans(otel_exporter, "memory.update_character_memory")
        assert len(spans) == 1

    @pytest.mark.anyio
    async def test_update_common_memory_span(self, otel_exporter):
        from sidestage.memory.tools import DmMemoryTools

        mock_client = MagicMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem_3"

        with patch("sidestage.memory.tools.upsert_common_scene_memory", new_callable=AsyncMock, return_value=mock_memory):
            tools = DmMemoryTools(
                client=mock_client, embed_config=None, health=MagicMock(),
                dm_actor_id="dm_1",
            )
            await tools.update_common_memory("scene_01", "Common knowledge")

        spans = _find_spans(otel_exporter, "memory.update_common_memory")
        assert len(spans) == 1

    @pytest.mark.anyio
    async def test_update_canonical_memory_span(self, otel_exporter):
        from sidestage.memory.tools import DmMemoryTools

        mock_client = MagicMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem_4"

        with patch("sidestage.memory.tools.upsert_scene_memory", new_callable=AsyncMock, return_value=mock_memory):
            tools = DmMemoryTools(
                client=mock_client, embed_config=None, health=MagicMock(),
                dm_actor_id="dm_1",
            )
            await tools.update_canonical_memory("scene_01", "DM truth")

        spans = _find_spans(otel_exporter, "memory.update_canonical_memory")
        assert len(spans) == 1

    @pytest.mark.anyio
    async def test_add_world_fact_span(self, otel_exporter):
        from sidestage.memory.tools import DmMemoryTools

        mock_client = MagicMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem_5"

        with patch("sidestage.memory.tools.upsert_world_fact", new_callable=AsyncMock, return_value=mock_memory):
            tools = DmMemoryTools(
                client=mock_client, embed_config=None, health=MagicMock(),
                dm_actor_id="dm_1",
            )
            await tools.add_world_fact("entity_1", "A world fact")

        spans = _find_spans(otel_exporter, "memory.add_world_fact")
        assert len(spans) == 1

    @pytest.mark.anyio
    async def test_memory_exception_sets_error(self, otel_exporter):
        from sidestage.memory.tools import MemoryTools

        mock_client = MagicMock()

        with patch("sidestage.memory.tools.upsert_scene_memory", new_callable=AsyncMock, side_effect=RuntimeError("db error")):
            tools = MemoryTools(
                client=mock_client, embed_config=None, health=MagicMock(),
                owner_id="char_1", scene_id="scene_01",
            )
            await tools.update_scene_memory("Content")

        span = _find_spans(otel_exporter, "memory.update_scene_memory")[0]
        assert span.status.status_code.name == "ERROR"


# ===========================================================================
# 4.9 Entity import tracing tests
# ===========================================================================


class TestReloadDefaultsTracing:
    def test_creates_span(self, otel_exporter, tmp_path):
        from sidestage.campaign import Campaign

        with patch.object(Campaign, "__init__", lambda self, *a, **k: None):
            campaign = Campaign.__new__(Campaign)
            campaign.storage = MagicMock()
            campaign.storage.add_character = MagicMock()
            campaign.storage.add_scene = MagicMock()
            campaign.storage.add_location = MagicMock()
            campaign.storage.add_item = MagicMock()
            campaign.storage.add_event = MagicMock()

            from sidestage.migration.parser import ParseResult
            mock_result = ParseResult(entities=[], memories=[], chatlogs={}, errors=[], warnings=[])

            with patch("sidestage.campaign.parse_directory", return_value=mock_result):
                with patch("pathlib.Path.exists", return_value=True):
                    campaign.reload_defaults()

        spans = _find_spans(otel_exporter, "campaign.reload_defaults")
        assert len(spans) == 1

    def test_span_has_loaded_count(self, otel_exporter, tmp_path):
        from sidestage.campaign import Campaign

        with patch.object(Campaign, "__init__", lambda self, *a, **k: None):
            campaign = Campaign.__new__(Campaign)
            campaign.storage = MagicMock()
            campaign.storage.add_character = MagicMock()
            campaign.storage.add_scene = MagicMock()
            campaign.storage.add_location = MagicMock()
            campaign.storage.add_item = MagicMock()
            campaign.storage.add_event = MagicMock()

            char = _make_character()
            from sidestage.migration.parser import ParseResult
            mock_result = ParseResult(entities=[char], memories=[], chatlogs={}, errors=[], warnings=[])

            with patch("sidestage.campaign.parse_directory", return_value=mock_result):
                with patch("pathlib.Path.exists", return_value=True):
                    campaign.reload_defaults()

        span = _find_spans(otel_exporter, "campaign.reload_defaults")[0]
        assert span.attributes["entities.loaded_count"] == 1
