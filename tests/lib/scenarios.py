"""Scenario dataclass and the `scene_from` helper used by integration tests.

Per `spec-location-pydoc`, the per-class invariants for `Scenario` live here
on the dataclass docstrings.

.implements: testing-scenario
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sidestage.campaign import Campaign
from sidestage.message import Message
from sidestage.scene import Scene

if TYPE_CHECKING:
    from tests.lib.matchers import Matcher


# Re-export alias so callers can import a single name.
SceneModel = Scene.Model


@dataclass(frozen=True)
class Scenario:
    """scenario-class: One integration scenario (test case data shape).

    A Scenario is the data shape consumed by `run_scenario`: a fresh scene
    is built from `scene`, seeded with `chat_history`, then `input` is
    dispatched and `expect` asserts on the result.

    .implements: testing-scenario
    """

    name: str
    """scenario-name: Human-readable id used as the parametrize id."""

    scene: SceneModel
    """scenario-scene: Full Scene.Model. Typically built via `scene_from()`
    so most scenarios clone-with-overrides from `test_campaign`."""

    input: Message
    """scenario-input: The Message dispatched by the runner."""

    expect: "Matcher"
    """scenario-expect: Asserts on the resulting `scene.messages` after
    dispatch + npc cycle."""

    chat_history: list[Message] = field(default_factory=list)
    """scenario-chat-history: Pre-seeded into the per-test Scene's messages
    before dispatch."""


def scene_from(campaign: Campaign, scene_id: str, **overrides) -> SceneModel:
    """scene-from-fn: Return a copy of the named scene's Model with
    `overrides` applied via Pydantic `model_copy(update=...)`.

    Lets one scenario tweak just the character list (e.g. swap the npc),
    another tweak the body, another use the base scene unchanged. The
    fixture campaign stays minimal; scenarios specialize as needed.

    .implements: testing-scenario
    """
    base = campaign.scene(scene_id).to_model()
    if not overrides:
        return base
    return base.model_copy(update=overrides)
