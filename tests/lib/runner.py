"""Scenario runner — drives a Scenario against an App.

Per `spec-location-pydoc`, the runner spec lives on this module's
`run_scenario` function.

.implements: testing-runner
"""

from __future__ import annotations

import asyncio

from sidestage.character import Character
from sidestage.scene import SimpleScene
from sidestage.server import App
from tests.lib.scenarios import Scenario

# Bound on the await-cycle wait. The npc cycle is fully in-process and
# synchronous-ish (StubActor.respond does no real I/O), so 1 s is generous.
_AWAIT_CYCLE_TIMEOUT_S = 1.0
# Quiescence window: number of consecutive "no growth" yields that count as
# "the npc cycle has settled". Two yields reliably catches the
# `dispatch -> create_task -> await self._npc.respond -> append -> notify`
# chain even when a future actor adds extra `await` steps.
_QUIESCENCE_YIELDS = 3


async def run_scenario(scenario: Scenario, app: App) -> None:
    """run-scenario-fn: Execute one Scenario against an App.

    Steps:
    - run-scenario-build-scene: Construct a fresh `SimpleScene` from
      `scenario.scene`, resolving each character id via the app's campaign
      factory. Fresh scene = no message bleed across tests.
    - run-scenario-seed-history: Append each `Message` in
      `scenario.chat_history` to the new scene's `_messages`.
    - run-scenario-dispatch: Call `scene.append(scenario.input)` and
      capture the returned index.
    - run-scenario-await-cycle: Await the fire-and-forget npc cycle to
      settle. Polls `len(scene.messages)` every `asyncio.sleep(0)` cycle;
      treats N consecutive no-growth yields as "settled". Bounded by
      `_AWAIT_CYCLE_TIMEOUT_S` to fail fast if a coroutine wedges.
    - run-scenario-check: Invoke `scenario.expect.check(scene.messages)`.

    .implements: testing-runner
    """
    # run-scenario-build-scene.
    campaign = next(iter(app.campaigns.values()))
    factory = campaign.factory
    characters: list[Character] = []
    for cid in scenario.scene.characters:
        entity = factory.get(cid)
        if entity is None:
            raise RuntimeError(
                f"run_scenario: scene references unknown character {cid!r}"
            )
        # The fixture campaign guarantees these are Characters.
        characters.append(entity)  # type: ignore[arg-type]
    scene = SimpleScene(
        id=scenario.scene.id,
        name=scenario.scene.name,
        body=scenario.scene.body,
        characters=characters,
    )

    # run-scenario-seed-history. Mutate the underlying _messages list rather
    # than the dispatch path so seeding doesn't fire any npc tasks.
    for msg in scenario.chat_history:
        scene._messages.append(msg)

    # run-scenario-dispatch. SimpleScene.dispatch is sync; the npc cycle is
    # spawned via asyncio.create_task and runs after this returns.
    scene.dispatch(scenario.input)

    # run-scenario-await-cycle. Poll for quiescence: once the message list
    # stops growing for N consecutive yields, the spawned task chain is done.
    loop = asyncio.get_event_loop()
    deadline = loop.time() + _AWAIT_CYCLE_TIMEOUT_S
    last_len = len(scene.messages)
    stable = 0
    while loop.time() < deadline and stable < _QUIESCENCE_YIELDS:
        await asyncio.sleep(0)
        cur = len(scene.messages)
        if cur == last_len:
            stable += 1
        else:
            stable = 0
            last_len = cur

    # run-scenario-check.
    scenario.expect.check(scene.messages)
