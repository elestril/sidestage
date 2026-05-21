"""Unit tests for NpcActor (per `specs/actors.md` npc-actor section).

litellm is patched per-test — real network calls would blow the 2s
timeout. The integration tier covers the live LLM path (gated by
`@pytest.mark.live_llm`).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sidestage.actor import Actor
from sidestage.entity import Entity, EntityId, MessageContext
from sidestage.llm_profile import ModelEntry
from sidestage.message import Message
from sidestage.npc_actor import NpcActor, _shape_turns

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _local_entry() -> ModelEntry:
    """A local-endpoint ModelEntry — no API key env var, stub key sent."""
    return ModelEntry.model_validate(
        {"endpoint": "http://127.0.0.1:8080", "model": "openai/local"}
    )


def _completion_response(text: str) -> SimpleNamespace:
    """Mimic litellm's response shape: response.choices[0].message.content."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


def _character_mock(*, id: str = "bob", body: str = "I am Bob.") -> MagicMock:
    """A Character-shaped mock that lets `annotate_context` write a fixed
    annotation and exposes `id` for log strings."""
    char = MagicMock()
    char.id = EntityId(id)
    char.body = body

    def _annotate(ctx: MessageContext) -> None:
        ctx.annotations[char] = body

    char.annotate_context = MagicMock(side_effect=_annotate)
    return char


def _scene_mock(messages: list[Message] | None = None) -> MagicMock:
    """A Scene-shaped mock with a `messages` list."""
    scene = MagicMock(spec=Entity)
    scene.id = EntityId("scene-x")
    scene.messages = messages or []
    return scene


# ---------------------------------------------------------------------------
# Class shape
# ---------------------------------------------------------------------------


class TestNpcActorClass:
    def test_implements_actor(self) -> None:
        # npc-actor: subclass of Actor.
        assert issubclass(NpcActor, Actor)

    def test_init_stores_entry(self) -> None:
        # npc-actor-init.
        entry = _local_entry()
        actor = NpcActor(entry)
        assert actor._entry is entry, (
            "npc-actor-init: __init__ MUST store entry as self._entry; "
            f"got {actor._entry!r}"
        )

    def test_is_human_returns_false(self) -> None:
        # npc-actor-is-human.
        actor = NpcActor(_local_entry())
        assert actor.is_human() is False


# ---------------------------------------------------------------------------
# _shape_turns
# ---------------------------------------------------------------------------


class TestShapeTurns:
    """npc-actor-consumes-context: scene history → chat turns."""

    def test_responding_character_maps_to_assistant(self) -> None:
        bob = _character_mock(id="bob")
        alice = _character_mock(id="alice")
        history = [
            Message(sender=alice, body="hi"),
            Message(sender=bob, body="hello"),
            Message(sender=alice, body="how are you"),
        ]
        turns = _shape_turns(history, bob)
        assert turns == [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "how are you"},
        ]

    def test_empty_history(self) -> None:
        bob = _character_mock(id="bob")
        assert _shape_turns([], bob) == []


# ---------------------------------------------------------------------------
# respond — happy + error paths
# ---------------------------------------------------------------------------


class TestNpcActorRespondLocal:
    """npc-actor-litellm-kwargs for an entry with no api_key_env."""

    async def test_passes_endpoint_and_stub_key(self) -> None:
        actor = NpcActor(_local_entry())
        bob = _character_mock(id="bob")
        scene = _scene_mock(messages=[])
        sender = _character_mock(id="alice")
        message = Message(sender=sender, body="hi")

        with patch(
            "sidestage.npc_actor.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=_completion_response("hello back"),
        ) as mock_call:
            await actor.respond(message, bob, scene)

        assert mock_call.await_args is not None
        kwargs = mock_call.await_args.kwargs
        assert kwargs["model"] == "openai/local", (
            "npc-actor-litellm-kwargs: model MUST be entry.model verbatim; "
            f"got model={kwargs['model']!r}"
        )
        assert kwargs["api_base"] == "http://127.0.0.1:8080", (
            "npc-actor-litellm-kwargs: api_base MUST be entry.endpoint; "
            f"got api_base={kwargs['api_base']!r}"
        )
        assert kwargs["api_key"] == "sk-no-key", (
            "npc-actor-litellm-kwargs: missing api_key_env MUST yield stub key; "
            f"got api_key={kwargs['api_key']!r}"
        )
        assert kwargs["timeout"] == 60.0, (
            "npc-actor-respond-timeout: timeout MUST be 60.0 seconds; "
            f"got timeout={kwargs['timeout']!r}"
        )
        assert kwargs["max_tokens"] == 512, (
            "npc-actor-respond-max-tokens: max_tokens MUST be 512 to "
            "prevent runaway generation; "
            f"got max_tokens={kwargs['max_tokens']!r}"
        )
        assert kwargs["chat_template_kwargs"] == {"enable_thinking": False}, (
            "npc-actor-model-params: NpcActor MUST merge its model_params "
            "into the litellm call so the Actor controls request shape; "
            f"got chat_template_kwargs={kwargs.get('chat_template_kwargs')!r}"
        )

    async def test_model_params_override_defaults(self) -> None:
        # npc-actor-model-params: a subclass can extend / override the
        # request shape. Use a one-off class to avoid mutating the
        # class-level default (which is shared with the rest of the suite).
        class TunedNpcActor(NpcActor):
            model_params = {
                "chat_template_kwargs": {"enable_thinking": True},
                "temperature": 0.2,
            }

        actor = TunedNpcActor(_local_entry())
        bob = _character_mock(id="bob")
        scene = _scene_mock(messages=[])
        sender = _character_mock(id="alice")
        message = Message(sender=sender, body="hi")

        with patch(
            "sidestage.npc_actor.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=_completion_response("ok"),
        ) as mock_call:
            await actor.respond(message, bob, scene)

        assert mock_call.await_args is not None
        kwargs = mock_call.await_args.kwargs
        assert kwargs["chat_template_kwargs"] == {"enable_thinking": True}, (
            "npc-actor-model-params: subclass model_params MUST override the "
            f"default; got chat_template_kwargs={kwargs.get('chat_template_kwargs')!r}"
        )
        assert kwargs["temperature"] == 0.2, (
            "npc-actor-model-params: subclass model_params MUST add new fields; "
            f"got temperature={kwargs.get('temperature')!r}"
        )

    async def test_calls_annotate_context_with_message_context(self) -> None:
        # npc-actor-consumes-context: character.annotate_context invoked
        # with a MessageContext carrying message + scene.
        actor = NpcActor(_local_entry())
        bob = _character_mock(id="bob")
        scene = _scene_mock(messages=[])
        sender = _character_mock(id="alice")
        message = Message(sender=sender, body="hi")

        with patch(
            "sidestage.npc_actor.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=_completion_response("hello"),
        ):
            await actor.respond(message, bob, scene)

        bob.annotate_context.assert_called_once()
        ctx_arg = bob.annotate_context.call_args.args[0]
        assert isinstance(ctx_arg, MessageContext)
        assert ctx_arg.message is message
        assert ctx_arg.scene is scene

    async def test_system_prompt_joins_annotations(self) -> None:
        # npc-actor-respond step 3: system prompt = "\n\n".join(ctx.annotations.values()).
        actor = NpcActor(_local_entry())
        scene = _scene_mock(messages=[])

        # Character that adds two annotations (its own + a fake "scene" one).
        bob = MagicMock()
        bob.id = EntityId("bob")
        fake_scene_entity = MagicMock(spec=Entity)
        fake_scene_entity.id = EntityId("scene-x")

        def _annotate(ctx: MessageContext) -> None:
            ctx.annotations[bob] = "bob persona"
            ctx.annotations[fake_scene_entity] = "scene setting"

        bob.annotate_context = MagicMock(side_effect=_annotate)

        sender = _character_mock(id="alice")
        message = Message(sender=sender, body="hi")

        with patch(
            "sidestage.npc_actor.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=_completion_response("ok"),
        ) as mock_call:
            await actor.respond(message, bob, scene)

        assert mock_call.await_args is not None
        msgs = mock_call.await_args.kwargs["messages"]
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "bob persona\n\nscene setting", (
            "npc-actor-respond: system prompt MUST be `\\n\\n`-joined "
            f"annotations.values(); got content={msgs[0]['content']!r}"
        )

    async def test_turns_after_system(self) -> None:
        actor = NpcActor(_local_entry())
        bob = _character_mock(id="bob")
        alice = _character_mock(id="alice")
        scene = _scene_mock(
            messages=[
                Message(sender=alice, body="first"),
                Message(sender=bob, body="second"),
            ]
        )
        message = Message(sender=alice, body="trigger")

        with patch(
            "sidestage.npc_actor.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=_completion_response("ok"),
        ) as mock_call:
            await actor.respond(message, bob, scene)

        assert mock_call.await_args is not None
        msgs = mock_call.await_args.kwargs["messages"]
        # system + 2 history turns.
        assert len(msgs) == 3
        assert msgs[1] == {"role": "user", "content": "first"}
        assert msgs[2] == {"role": "assistant", "content": "second"}

    async def test_returns_message_with_completion_body(self) -> None:
        actor = NpcActor(_local_entry())
        bob = _character_mock(id="bob", body="bob persona")
        scene = _scene_mock(messages=[])
        sender = _character_mock(id="alice")
        message = Message(sender=sender, body="hi")

        with patch(
            "sidestage.npc_actor.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=_completion_response("Hello there!"),
        ):
            result = await actor.respond(message, bob, scene)

        assert result is not None
        assert result.sender is bob
        assert result.body == "Hello there!"


class TestNpcActorRespondErrors:
    """npc-actor-respond-error-none: every failure mode → None."""

    async def test_returns_none_on_transport_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        actor = NpcActor(_local_entry())
        bob = _character_mock(id="bob")
        scene = _scene_mock(messages=[])
        sender = _character_mock(id="alice")
        message = Message(sender=sender, body="hi")

        with (
            patch(
                "sidestage.npc_actor.litellm.acompletion",
                new_callable=AsyncMock,
                side_effect=ConnectionError("boom"),
            ),
            caplog.at_level(logging.ERROR, logger="sidestage.npc_actor"),
        ):
            result = await actor.respond(message, bob, scene)

        assert result is None, (
            "npc-actor-respond-error-none: transport error MUST yield None; "
            f"got {result!r}"
        )
        assert any("LLM call failed" in rec.getMessage() for rec in caplog.records), (
            "expected EXCEPTION log on transport error"
        )

    async def test_returns_none_on_timeout(self) -> None:
        actor = NpcActor(_local_entry())
        bob = _character_mock(id="bob")
        scene = _scene_mock(messages=[])
        sender = _character_mock(id="alice")
        message = Message(sender=sender, body="hi")

        with patch(
            "sidestage.npc_actor.litellm.acompletion",
            new_callable=AsyncMock,
            side_effect=TimeoutError("slow"),
        ):
            result = await actor.respond(message, bob, scene)
        assert result is None

    async def test_returns_none_on_empty_completion(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        actor = NpcActor(_local_entry())
        bob = _character_mock(id="bob")
        scene = _scene_mock(messages=[])
        sender = _character_mock(id="alice")
        message = Message(sender=sender, body="hi")

        with (
            patch(
                "sidestage.npc_actor.litellm.acompletion",
                new_callable=AsyncMock,
                return_value=_completion_response(""),
            ),
            caplog.at_level(logging.WARNING, logger="sidestage.npc_actor"),
        ):
            result = await actor.respond(message, bob, scene)

        assert result is None, (
            "npc-actor-respond-error-none: empty completion MUST yield None; "
            f"got {result!r}"
        )
        assert any("empty completion" in rec.getMessage() for rec in caplog.records)

    async def test_returns_none_on_whitespace_only(self) -> None:
        actor = NpcActor(_local_entry())
        bob = _character_mock(id="bob")
        scene = _scene_mock(messages=[])
        sender = _character_mock(id="alice")
        message = Message(sender=sender, body="hi")

        with patch(
            "sidestage.npc_actor.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=_completion_response("   \n  "),
        ):
            result = await actor.respond(message, bob, scene)
        assert result is None

    async def test_returns_none_on_none_content(self) -> None:
        # litellm sometimes surfaces content=None for refusal-style responses.
        actor = NpcActor(_local_entry())
        bob = _character_mock(id="bob")
        scene = _scene_mock(messages=[])
        sender = _character_mock(id="alice")
        message = Message(sender=sender, body="hi")

        none_response: Any = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=None))]
        )
        with patch(
            "sidestage.npc_actor.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=none_response,
        ):
            result = await actor.respond(message, bob, scene)
        assert result is None
