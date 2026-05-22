"""E2E live-LLM: NpcActor against a real OpenAI-compatible endpoint.

Per `testing-categories-e2e-live-llm`. Crosses the process boundary to
the user's LLM server (llama-server / vllm / ollama). Speaks directly
to the `NpcActor` class — no Character / Scene / REST / SSE; those are
covered by `test_cuj_hello` with `StubActor` per
`testing-categories-e2e-http`.

Auto-skips when the endpoint declared by `sidestage/llm_profiles/
localhost.yaml` isn't answering `/health`, so this test runs as part
of `just test` whenever the LLM is up and skips cleanly otherwise.
"""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock

import httpx
import pytest

from sidestage.character import Character
from sidestage.entity import Entity, EntityId, MessageContext
from sidestage.llm_profile import ModelEntry, load_profiles
from sidestage.message import Message
from sidestage.npc_actor import NpcActor

_LLM_HEALTH_URL = "http://127.0.0.1:8080/health"


def _llm_endpoint_up() -> bool:
    """Pre-flight /health on the LLM endpoint declared by localhost.yaml.

    Skipping here gives a clear "your LLM isn't running" message instead
    of a 60s timeout deep inside litellm when the test actually fires.
    """
    try:
        r = httpx.get(_LLM_HEALTH_URL, timeout=2.0)
        return 200 <= r.status_code < 300
    except (httpx.HTTPError, OSError):
        return False


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.live_llm,
    pytest.mark.skipif(
        not _llm_endpoint_up(),
        reason=(
            f"no OpenAI-compatible endpoint reachable on {_LLM_HEALTH_URL} — "
            "start llama-server / vllm / ollama / etc. to run this test"
        ),
    ),
    pytest.mark.timeout(90),
]


# ---------------------------------------------------------------------------
# Minimal stubs — NpcActor.respond only reads `character.annotate_context`
# (per npc-actor-consumes-context) and `scene.messages` (history). We feed
# both via MagicMock(spec=Entity) so the test doesn't drag in Campaign /
# factory / Character.__init__ machinery.
# ---------------------------------------------------------------------------


def _character_stub(*, id: str, persona: str) -> MagicMock:
    """A Character-shaped stub whose `annotate_context` writes a fixed
    persona line keyed by itself.
    """
    char = MagicMock(spec=Entity)
    char.id = EntityId(id)

    def _annotate(ctx: MessageContext) -> None:
        ctx.annotations[char] = persona

    char.annotate_context = MagicMock(side_effect=_annotate)
    return char


def _scene_stub(messages: list[Message] | None = None) -> MagicMock:
    scene = MagicMock(spec=Entity)
    scene.id = EntityId("tavern")
    scene.messages = messages or []
    return scene


@pytest.fixture
def entry() -> ModelEntry:
    """ModelEntry from the dev profile — points at whatever endpoint
    the user runs locally."""
    return load_profiles("sidestage")["localhost"].models["default"]


@pytest.fixture
def marigold() -> MagicMock:
    return _character_stub(
        id="marigold",
        persona=(
            "You are Marigold Hearthwell, the warm and gossipy keeper of "
            "the Cracked Tankard tavern. Reply in one short sentence."
        ),
    )


@pytest.fixture
def bob() -> MagicMock:
    return _character_stub(id="bob", persona="A weary traveler.")


@pytest.fixture
def scene() -> MagicMock:
    return _scene_stub(messages=[])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_responds_with_non_empty_message(
    entry: ModelEntry,
    marigold: MagicMock,
    bob: MagicMock,
    scene: MagicMock,
) -> None:
    """`NpcActor.respond` against the live endpoint returns a non-empty
    `Message` for a basic prompt — the smoke test for the litellm →
    real-LLM path.
    """
    actor = NpcActor(entry)
    msg = Message(sender_id=bob.id, body="Say hi in one short sentence.")
    # In production, the EntityList[Message].append on `scene.messages`
    # puts the triggering message into `scene.messages` BEFORE the listener
    # kicks the actor. Mirror that here so `_shape_turns` produces a chat
    # history with a user turn — otherwise NpcActor sends just the system
    # prompt and provider chat templates (e.g. Qwen3) raise "no user query
    # found".
    scene.messages = [msg]

    reply = await actor.respond(msg, cast(Character, marigold), cast(Entity, scene))

    assert reply is not None, (
        "npc-actor-respond: expected reply text from a live endpoint; "
        "got None (check server logs for empty completion / non-2xx)"
    )
    assert reply.strip() != "", (
        f"npc-actor-respond: reply body MUST be non-empty; got body={reply!r}"
    )


async def test_handles_reasoning_model(
    entry: ModelEntry,
    marigold: MagicMock,
    bob: MagicMock,
    scene: MagicMock,
) -> None:
    """When the configured endpoint is a reasoning model (one that emits
    a chain-of-thought preamble alongside `content`), `NpcActor` MUST
    still surface a non-empty `content`-derived reply within the budget
    — and MUST NOT leak the chain-of-thought as the NPC's in-character
    speech.

    Non-reasoning endpoints pass this trivially: no preamble, content
    arrives quickly, no CoT markers in the body. Reasoning endpoints
    are the interesting case (Qwen3-Thinking, o1-style, DeepSeek-R1).
    """
    actor = NpcActor(entry)
    # An open-ended prompt that often triggers a reasoning preamble on
    # CoT-trained models.
    msg = Message(
        sender_id=bob.id,
        body=(
            "Two travelers ask which local quest is worth their trouble — "
            "which do you steer them toward?"
        ),
    )
    scene.messages = [msg]  # production seeds the trigger; see test above.

    reply = await actor.respond(msg, cast(Character, marigold), cast(Entity, scene))

    assert reply is not None, (
        "npc-actor-respond: expected reply text even when the model emits "
        "a reasoning preamble; got None"
    )
    assert reply.strip() != "", (
        f"npc-actor-respond: reply body MUST be non-empty; got body={reply!r}"
    )
    # Reasoning leak guard: chain-of-thought emitted into `content`
    # (instead of the provider's `reasoning_content` field) reads as a
    # break in character. Heuristic markers catch the most common shapes.
    body_lower = reply.lower()
    cot_markers = (
        "<think>",
        "thinking process",
        "let me think",
        "let's think",
        "first, i'll",
        "first, let",
        "step 1",
    )
    leaked = [m for m in cot_markers if m in body_lower]
    assert not leaked, (
        "npc-actor-respond: reply MUST be the content answer, not the "
        f"chain-of-thought preamble; found markers {leaked!r} in "
        f"body={reply!r}"
    )
