"""npc-actor: LLM-backed Actor.

Per `specs/actor.md` (npc-actor section). Singleton owned by App; one
ModelEntry resolved from the active profile's `default` role at
construction. `respond()` is one-shot — full completion, one Message
back, no streaming.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, cast

import litellm

from sidestage.actor import Actor
from sidestage.entity import MessageContext
from sidestage.message import Message

if TYPE_CHECKING:
    from sidestage.character import Character
    from sidestage.entity import Entity
    from sidestage.llm_profile import ModelEntry


logger = logging.getLogger("sidestage.npc_actor")

# npc-actor-respond-timeout: 60s budget — a freshly-started local server
# (llama-server, vllm) may need that long for first-call model load.
# Subsequent calls return in seconds. Unit tests MUST mock litellm —
# pytest's 2s default would otherwise fail the test before the call returns.
_TIMEOUT_S = 60.0


def _shape_turns(history: list[Message], responding: Character) -> list[dict[str, str]]:
    """npc-actor-consumes-context: map scene history into chat turns.
    Sender == responding character → `assistant`; everyone else → `user`.
    Order preserved.
    """
    turns: list[dict[str, str]] = []
    for msg in history:
        role = "assistant" if msg.sender is responding else "user"
        turns.append({"role": role, "content": msg.body})
    return turns


def _litellm_kwargs(entry: ModelEntry) -> dict[str, Any]:
    """npc-actor-litellm-kwargs: derive model / api_base / api_key from
    a ModelEntry. Always passes `api_base=entry.endpoint` and
    `model=entry.model` (the YAML carries the provider prefix). If
    `entry.api_key_env` names an env var, its value is sent as the
    api_key; otherwise a stub is sent (local servers ignore it but
    litellm requires the param).

    Returned `dict[str, Any]` rather than `dict[str, object]` so the
    `**kwargs` unpacking site type-checks against litellm's typed
    parameters without a per-key cast.
    """
    kwargs: dict[str, Any] = {
        "timeout": _TIMEOUT_S,
        "model": entry.model,
        "api_base": entry.endpoint,
    }
    if entry.api_key_env:
        kwargs["api_key"] = os.environ[entry.api_key_env]
    else:
        kwargs["api_key"] = "sk-no-key"
    return kwargs


class NpcActor(Actor):
    """npc-actor: LLM-backed Actor.

    Process-wide singleton constructed from the active profile's `default`
    role. Multiple Characters with `owner="npc"` share one instance; the
    `ModelEntry` is immutable, the litellm call is stateless per request,
    so concurrent `respond` calls across scenes need no coordination.

    .implements: character-init-binds-actor, server-get-actor
    """

    def __init__(self, entry: ModelEntry) -> None:
        """npc-actor-init: stores `entry` as `self._entry`. No I/O."""
        self._entry = entry

    def is_human(self) -> bool:
        """npc-actor-is-human: returns False."""
        return False

    async def respond(
        self, message: Message, character: Character, scene: Entity
    ) -> Message | None:
        """npc-actor-respond: build MessageContext(message, scene), let
        the character annotate it, join annotations as the system
        prompt, shape scene.messages as turns, call
        `litellm.acompletion`, wrap response in
        `Message(sender=character, body=text)`.

        Returns `None` on any failure (transport, timeout, non-2xx,
        empty/whitespace-only completion) per
        `npc-actor-respond-error-none`. No in-band placeholder text —
        keeps scene history clean.
        """
        ctx = MessageContext(message=message, scene=scene)
        # npc-actor-consumes-context: Entity polymorphism is the contract.
        # We never read character.body / scene.body directly here.
        character.annotate_context(ctx)
        system = "\n\n".join(ctx.annotations.values())
        # `scene.messages` is the turn history; reachable on the Scene
        # subclass (`Scene.messages` is the ABC property). The Entity
        # type annotation on `scene` is the loosest the call site
        # supports; in production it's always a Scene.
        history = scene.messages  # type: ignore[attr-defined]
        turns = _shape_turns(history, character)
        msgs: list[dict[str, str]] = [
            {"role": "system", "content": system},
            *turns,
        ]
        try:
            response = await litellm.acompletion(
                messages=msgs, **_litellm_kwargs(self._entry)
            )
        except Exception:
            logger.exception(
                "NpcActor.respond: LLM call failed for character=%s", character.id
            )
            return None
        # litellm normalises the response shape across providers. We never
        # pass stream=True, so this is always a `ModelResponse`, not a
        # `CustomStreamWrapper` — narrow with cast for pyright.
        completion = cast("Any", response)
        text = (completion.choices[0].message.content or "").strip()
        if not text:
            logger.warning(
                "NpcActor.respond: empty completion for character=%s", character.id
            )
            return None
        return Message(sender=character, body=text)
