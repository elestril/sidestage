"""Scenario runner — drives a Scenario against an App.

Per `spec-location-pydoc`, the runner spec lives on this module's
`run_scenario` function.

.implements: testing-runner
"""

from __future__ import annotations

from sidestage.scene import SimpleScene
from sidestage.server import App
from tests.lib.scenarios import Scenario

# Bound on the idle-wait for listener-spawned background tasks.
_IDLE_TIMEOUT_S = 1.0


async def run_scenario(scenario: Scenario, app: App) -> None:
    """run-scenario-fn: Execute one Scenario against an App.

    Steps:
    - run-scenario-build-scene: Construct a fresh `SimpleScene` from
      `scenario.scene` (a `Scene.Model`), bound to the app's campaign. The
      campaign already holds the referenced characters; the SimpleScene
      resolves them via `campaign.get(id)`. Fresh scene = no message bleed
      across tests.
    - run-scenario-seed-history: Append each `Message` in
      `scenario.chat_history` to the new scene's `messages` list directly
      via `list.append` (bypassing the `EntityList.append` mutator) so
      seeding doesn't fire any listener tasks.
    - run-scenario-dispatch: Call `scene.messages.append(scenario.input)`,
      which records the message and emits `EntityChanged` — characters
      subscribed at construction react via their `notify` handlers.
    - run-scenario-await-cycle: Await `scene.idle()` to wait for all
      listener-spawned background tasks to settle.
    - run-scenario-check: Invoke `scenario.expect.check(scene.messages)`.

    .implements: testing-runner
    """
    # run-scenario-build-scene. `scenario.scene` is a `Scene.Model`; wrap it
    # in a fresh `SimpleScene` bound to the app's campaign. The campaign
    # resolves the model's `character_ids` to registered Character entities.
    campaign = next(iter(app.campaigns.values()))
    # Re-validate as a SimpleScene.Model — `scenario.scene` is typed as the
    # base `Scene.Model`, and `SimpleScene.__init__` is annotated to accept
    # that, but constructing through `SimpleScene.Model` keeps the surface
    # explicit (and is a no-op for already-matching shapes).
    scene = SimpleScene(
        SimpleScene.Model.model_validate(scenario.scene.model_dump()),
        campaign,
    )

    # run-scenario-seed-history. Mutate the underlying list via `list.append`
    # so seeding doesn't fire any listener tasks; the EntityList wrapper's
    # `append` would emit a ListDelta per call.
    for msg in scenario.chat_history:
        list.append(scene.messages, msg)

    # run-scenario-dispatch. `scene.messages.append` records the message and
    # emits `EntityChanged`; subscribed characters react in spawned tasks.
    scene.messages.append(scenario.input)

    # run-scenario-await-cycle. Wait for every listener-spawned task to
    # settle, bounded so a wedged coroutine fails fast.
    await scene.idle(timeout=_IDLE_TIMEOUT_S)

    # run-scenario-check.
    scenario.expect.check(list(scene.messages))
