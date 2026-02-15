"""Tests for backend tracing instrumentation.

Verifies that spans are created with correct names, attributes, and hierarchy
at each instrumentation point.
"""

import json
import logging
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

from sidestage.models import CharacterModel, EventModel, EventType, SceneModel


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
    import sidestage.actors as _actors
    import sidestage.memory.context as _ctx
    import sidestage.memory.tools as _tools
    import sidestage.campaign as _campaign

    _scene.tracer = provider.get_tracer("sidestage.scene")
    _char.tracer = provider.get_tracer("sidestage.character")
    _agent.tracer = provider.get_tracer("sidestage.agent")
    _actors.tracer = provider.get_tracer("sidestage.actors")
    _ctx.tracer = provider.get_tracer("sidestage.memory.context")
    _tools.tracer = provider.get_tracer("sidestage.memory.tools")
    _campaign.tracer = provider.get_tracer("sidestage.campaign")

    yield exporter
    provider.shutdown()


def _make_event_model(**overrides) -> EventModel:
    """Create an EventModel with sensible defaults for testing."""
    defaults = dict(
        id="evt_test1",
        name="Test Event",
        body="Hello",
        event_type=EventType.CHAT_MESSAGE,
        scene_id="scene_01",
        gametime=0,
        walltime="2025-01-01T00:00:00",
        actor_id="user",
        character_id="char_user",
    )
    defaults.update(overrides)
    return EventModel(**defaults)


def _make_scene(**overrides) -> SceneModel:
    defaults = dict(
        id="scene_01",
        name="Test SceneModel",
        body="A test scene",
    )
    defaults.update(overrides)
    return SceneModel(**defaults)


def _make_character(**overrides) -> CharacterModel:
    defaults = dict(
        id="char_npc1",
        name="NPC One",
        body="A test NPC",
    )
    defaults.update(overrides)
    return CharacterModel(**defaults)


def _find_spans(exporter, name):
    return [s for s in exporter.get_finished_spans() if s.name == name]


def _make_test_scene(scene_id="scene_01", tmp_path=None):
    """Create a Scene with mocked dependencies for tracing tests."""
    from sidestage.scene import Scene
    from sidestage.storage import Storage
    import tempfile

    if tmp_path is None:
        tmp_path = tempfile.mkdtemp()

    storage = Storage(db_path=f"{tmp_path}/test.db")
    scene_data = _make_scene(id=scene_id)
    campaign = MagicMock()
    scene = Scene(storage=storage, data=scene_data, campaign=campaign)
    scene.characters = {}
    return scene


def _make_npc_actor(character_id="char_npc1", character_name="NPC One"):
    """Create an NPCActor with mocked character data."""
    from sidestage.actors import NPCActor
    actor = NPCActor(actor_id=f"agent:{character_id}")
    char = MagicMock()
    char.id = character_id
    char.name = character_name
    char.body = "A test NPC"
    char.unseen = False
    actor.character = char
    actor.scene_logic = MagicMock()
    actor.scene_logic.agent = MagicMock()
    return actor


# ===========================================================================
# Event span context capture
# ===========================================================================


class TestEventSpanContext:
    def test_from_model_captures_span_context(self, otel_exporter):
        """Event.from_model() captures the current span context when a span is active."""
        from sidestage.event import Event

        model = _make_event_model()
        test_tracer = trace.get_tracer("test")

        with test_tracer.start_as_current_span("test_span") as span:
            expected_ctx = span.get_span_context()
            event = Event.from_model(model)

        assert event.span_context is not None
        assert event.span_context.trace_id == expected_ctx.trace_id
        assert event.span_context.span_id == expected_ctx.span_id

    def test_from_model_no_active_span(self):
        """Event.from_model() sets span_context to None when no tracing is active."""
        from sidestage.event import Event

        model = _make_event_model()
        event = Event.from_model(model)

        # When no real span is active, span_context should be None or invalid
        if event.span_context is not None:
            assert not event.span_context.is_valid


# ===========================================================================
# Scene._process_event tests
# ===========================================================================


class TestProcessEvent:
    @pytest.mark.anyio
    async def test_creates_root_span(self, otel_exporter):
        scene = _make_test_scene()
        model = _make_event_model()
        from sidestage.event import Event
        event = Event(model=model, span_context=None)

        await scene._process_event(event)

        spans = _find_spans(otel_exporter, "scene.process_event")
        assert len(spans) == 1

    @pytest.mark.anyio
    async def test_root_span_attributes(self, otel_exporter):
        scene = _make_test_scene()
        model = _make_event_model(scene_id="scene_01", actor_id="user", id="evt_x")
        from sidestage.event import Event
        event = Event(model=model, span_context=None)

        await scene._process_event(event)

        span = _find_spans(otel_exporter, "scene.process_event")[0]
        assert span.attributes["sidestage.scene.id"] == "scene_01"
        assert span.attributes["sidestage.event.id"] == "evt_x"
        assert span.attributes["sidestage.event.type"] == "ChatMessage"
        assert span.attributes["sidestage.actor.id"] == "user"

    @pytest.mark.anyio
    async def test_all_event_types_create_span(self, otel_exporter):
        """All event types create a processing span (no ChatMessage-only filter)."""
        scene = _make_test_scene()
        from sidestage.event import Event

        for et in EventType:
            otel_exporter.clear()
            model = _make_event_model(event_type=et, id=f"evt_{et.value}")
            event = Event(model=model, span_context=None)
            await scene._process_event(event)

            spans = _find_spans(otel_exporter, "scene.process_event")
            assert len(spans) == 1, f"Expected span for {et.value}"

    @pytest.mark.anyio
    async def test_exception_sets_error_status(self, otel_exporter):
        scene = _make_test_scene()
        scene.storage = MagicMock()
        scene.storage.add_event = MagicMock(side_effect=RuntimeError("db error"))

        model = _make_event_model()
        from sidestage.event import Event
        event = Event(model=model, span_context=None)

        with pytest.raises(RuntimeError):
            await scene._process_event(event)

        span = _find_spans(otel_exporter, "scene.process_event")[0]
        assert span.status.status_code.name == "ERROR"

    @pytest.mark.anyio
    async def test_creates_linked_root_span(self, otel_exporter):
        """_process_event() creates a new root span linked to the event's span context."""
        from sidestage.event import Event

        scene = _make_test_scene()
        model = _make_event_model()

        test_tracer = trace.get_tracer("test")
        with test_tracer.start_as_current_span("origin_span") as origin:
            origin_ctx = origin.get_span_context()
            event = Event.from_model(model)

        # Process the event outside the original span
        await scene._process_event(event)

        spans = _find_spans(otel_exporter, "scene.process_event")
        assert len(spans) == 1

        process_span = spans[0]
        # Verify it has a link to the origin span
        assert len(process_span.links) == 1
        link = process_span.links[0]
        assert link.context.trace_id == origin_ctx.trace_id
        assert link.context.span_id == origin_ctx.span_id

    @pytest.mark.anyio
    async def test_no_span_context_no_link(self, otel_exporter):
        """When event.span_context is None, the processing span has no links."""
        from sidestage.event import Event

        scene = _make_test_scene()
        model = _make_event_model()
        event = Event(model=model, span_context=None)

        await scene._process_event(event)

        span = _find_spans(otel_exporter, "scene.process_event")[0]
        assert len(span.links) == 0


# ===========================================================================
# Scene._dispatch tests
# ===========================================================================


class TestDispatch:
    @pytest.mark.anyio
    async def test_dispatch_within_process_span(self, otel_exporter):
        """_dispatch() executes within the scene.process_event span context."""
        from sidestage.event import Event
        from sidestage.actors import NPCActor, User
        from sidestage.character import Character

        scene = _make_test_scene()
        npc = NPCActor(actor_id="agent:npc1")
        npc.process = AsyncMock()
        user = User(actor_id="user")
        user.process = AsyncMock()

        scene.characters = {
            "char_npc1": Character(CharacterModel(id="char_npc1", name="NPC1", body=""), npc),
            "char_user": Character(CharacterModel(id="char_user", name="Player", body=""), user),
        }

        model = _make_event_model()
        event = Event(model=model, span_context=None)
        await scene._process_event(event)

        # The scene.process_event span should exist and encompass dispatch
        spans = _find_spans(otel_exporter, "scene.process_event")
        assert len(spans) == 1

    @pytest.mark.anyio
    async def test_npc_count_in_dispatch(self, otel_exporter):
        """Dispatch processes the correct number of NPCs."""
        from sidestage.event import Event
        from sidestage.actors import NPCActor, User
        from sidestage.character import Character

        scene = _make_test_scene()

        npc1 = NPCActor(actor_id="agent:npc1")
        npc1.process = AsyncMock()
        npc2 = NPCActor(actor_id="agent:npc2")
        npc2.process = AsyncMock()
        user = User(actor_id="user")
        user.process = AsyncMock()

        scene.characters = {
            "c1": Character(CharacterModel(id="c1", name="NPC1", body=""), npc1),
            "c2": Character(CharacterModel(id="c2", name="NPC2", body=""), npc2),
            "c3": Character(CharacterModel(id="c3", name="Player", body=""), user),
        }

        model = _make_event_model()
        event = Event(model=model, span_context=None)
        await scene._dispatch(event)

        npc1.process.assert_called_once()
        npc2.process.assert_called_once()
        user.process.assert_called_once()


# ===========================================================================
# NPCActor.process tracing tests
# ===========================================================================


class TestNPCActorProcess:
    @pytest.mark.anyio
    async def test_creates_npc_actor_span(self, otel_exporter):
        from sidestage.actors import NPCActor, User
        from sidestage.event import Event

        actor = _make_npc_actor()
        actor.agent = MagicMock()
        actor.agent.arun = AsyncMock(return_value=MagicMock(content=None))

        # Need a User actor on the event's character for the guard to pass
        model = _make_event_model(actor_id="user", character_id="char_user")
        event = Event.from_model(model)
        mock_scene = MagicMock()
        mock_scene.characters = {
            "char_user": MagicMock(actor=User(actor_id="user")),
        }
        event.scene = mock_scene

        await actor.process(event)

        spans = _find_spans(otel_exporter, "npc_actor.process")
        assert len(spans) == 1

    @pytest.mark.anyio
    async def test_character_attributes(self, otel_exporter):
        from sidestage.actors import NPCActor, User
        from sidestage.event import Event

        actor = _make_npc_actor(character_id="char_abc", character_name="TestNPC")
        actor.agent = MagicMock()
        actor.agent.arun = AsyncMock(return_value=MagicMock(content=None))

        model = _make_event_model(actor_id="user", character_id="char_user")
        event = Event.from_model(model)
        mock_scene = MagicMock()
        mock_scene.characters = {
            "char_user": MagicMock(actor=User(actor_id="user")),
        }
        event.scene = mock_scene

        await actor.process(event)

        span = _find_spans(otel_exporter, "npc_actor.process")[0]
        assert span.attributes["sidestage.character.id"] == "char_abc"
        assert span.attributes["sidestage.character.name"] == "TestNPC"

    @pytest.mark.anyio
    async def test_exception_sets_error(self, otel_exporter):
        from sidestage.actors import NPCActor, User
        from sidestage.event import Event

        actor = _make_npc_actor()
        actor.agent = MagicMock()
        actor.agent.arun = AsyncMock(side_effect=RuntimeError("agent error"))

        model = _make_event_model(actor_id="user", character_id="char_user")
        event = Event.from_model(model)
        mock_scene = MagicMock()
        mock_scene.characters = {
            "char_user": MagicMock(actor=User(actor_id="user")),
        }
        mock_scene.process = AsyncMock()
        event.scene = mock_scene

        # NPCActor.process catches exceptions and creates error events
        await actor.process(event)

        span = _find_spans(otel_exporter, "npc_actor.process")[0]
        assert span.status.status_code.name == "ERROR"


# ===========================================================================
# assemble_context tests
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
# LiteLLMAgent.arun tests
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
# Memory tool operations tests
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
# EntityModel import tracing tests
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
            campaign.campaign_log = logging.getLogger("test.campaign")

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
            campaign.campaign_log = logging.getLogger("test.campaign")

            char = _make_character()
            from sidestage.migration.parser import ParseResult
            mock_result = ParseResult(entities=[char], memories=[], chatlogs={}, errors=[], warnings=[])

            with patch("sidestage.campaign.parse_directory", return_value=mock_result):
                with patch("pathlib.Path.exists", return_value=True):
                    campaign.reload_defaults()

        span = _find_spans(otel_exporter, "campaign.reload_defaults")[0]
        assert span.attributes["entities.loaded_count"] == 1
