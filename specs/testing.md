# testing: How Sidestage is tested

Three layers — unit (colocated, mocked deps), integration (multi-module
flows in-process), eval (behavioral; opt-in). Integration is built on a
small framework — `Scenario` dataclass + PyHamcrest matchers + a runner —
sized for the multi-agent-scene world that's coming, where dozens of
scenarios per scene assert varied message-sequence outcomes.

## testing-categories

- testing-categories-unit: One module, mocked cross-deps. Lives next to
  source as `*_test.py`. Fast (whole suite under one second).
- testing-categories-integration: Real Scene + Character + Actor + App,
  no mocking of the domain layer. Routes called via `TestClient`; SSE via
  `httpx.AsyncClient` + `ASGITransport`. Lives in `tests/integration/`.
- testing-categories-eval: Behavioral evals against rubrics. Today every
  actor is deterministic so evals reduce to property checks; once
  LLM-backed actors land, evals slot in as PyHamcrest matchers calling
  an LLM judge. Opt-in. Lives in `tests/eval/`.

## testing-layout

```
src/sidestage/*_test.py                 # unit tests, colocated
tests/
├── conftest.py                         # shared fixtures
├── test_campaign/                      # canonical fixture campaign
│   ├── config.yaml                     # default_scene_id: parlor
│   ├── characters/
│   │   ├── alice.md                    # owner: user
│   │   └── bob.md                      # owner: stub
│   └── scenes/
│       └── parlor.md                   # alice + bob
├── lib/                                # framework code
│   ├── __init__.py
│   ├── scenarios.py                    # Scenario dataclass + scene_from()
│   └── runner.py                       # run_scenario()
├── integration/test_*.py               # @pytest.mark.integration
└── eval/test_*.py                      # @pytest.mark.eval, opt-in
```

- testing-layout-unit-colocated: Existing unit tests stay in `src/sidestage/`.
- testing-layout-test-campaign: Single canonical fixture campaign at
  `tests/test_campaign/`. Minimal — alice (user) + bob (stub) + parlor scene.
  Scenarios specialize via `scene_from(...)` overrides.
- testing-layout-no-matchers-module: Matchers come from `pyhamcrest`
  (dev dep). No custom matcher classes — `assert_that(actual, has_properties(...))`
  is enough. New matchers (e.g. `LLMJudge`) inherit `BaseMatcher` from PyHamcrest.

## testing-markers

```toml
[tool.pytest.ini_options]
markers = [
    "integration: in-process multi-module flows",
    "eval: behavioral evals; opt-in (require EVAL=1)",
]
```

- testing-markers-default: `uv run pytest` runs unit + integration; eval
  skipped.
- testing-markers-eval-opt-in: Eval tests carry `@pytest.mark.eval` AND
  `@pytest.mark.skipif(os.environ.get("EVAL") != "1", reason="eval-only")`.

## testing-failure-message

Every assertion that proves a spec invariant MUST include the spec label
verbatim in its message, followed by a prose description of what the
invariant requires and how the actual value violated it. The
label-in-message rule applies even when the enclosing test name already
encodes the label (per `spec-links-tested-by-implicit`) — duplication
keeps the failure line self-contained, so an agent reading only the
failure output knows which spec to load without opening the test file.

```python
assert len(scene.messages) == 1, (
    "scene-append-records: scene.messages must contain the appended "
    f"message; got len={len(scene.messages)}"
)
```

- testing-failure-message-exempt: Setup/precondition assertions (object
  is not None, fixture wired correctly) are exempt — they prove no spec
  invariant. Their failure points at infrastructure, not at a spec.
- testing-failure-message-pyhamcrest: PyHamcrest matchers satisfy the
  rule when the `reason` argument starts with the spec label:
  `assert_that(messages, has_length(1), reason="scene-append-records: …")`.

## testing-fixtures

Defined in `tests/conftest.py`.

- testing-fixture-test-campaign: `test_campaign` (**session-scoped**) —
  loads `tests/test_campaign/` once. Characters and factory are read-only
  and shared across the session.
- testing-fixture-test-app: `test_app` (function-scoped) — fresh `App`
  with `App.campaigns` and `App.factory` set from `test_campaign`,
  `state = SERVING`. Resets class-level state on teardown.
- testing-fixture-test-client: `test_client` (function-scoped) — sync
  `TestClient(test_app._fastapi)` for non-streaming routes.
- testing-fixture-mock-user-actor: `mock_user_actor` (function-scoped) —
  scripted `MagicMock(spec=UserActor)` registered at `App._actors["user"]`.
  Records `subscribe_to`/`unsubscribe_from`/`cancel_all` calls; returns a
  controlled `asyncio.Queue` from `subscribe_to` so SSE-handler tests can
  drive what the response loop reads. Per `testing-mock-user-actor`.

## testing-mock-user-actor

UserActor holds edge state — queues, future auth context. Integration
tests MUST use a scripted mock instead of the real `UserActor`. Two
reasons:

- testing-mock-user-actor-edge: A real `UserActor` would carry process-wide
  SSE infrastructure across tests. Mocks isolate per-test.
- testing-mock-user-actor-script: Tests drive scripted SSE behavior by
  controlling what `subscribe_to` returns (which queue) and asserting on
  `unsubscribe_from` cleanup. Real UserActor's internals aren't reachable
  this way.

`StubActor` doesn't need mocking — it's deterministic and stateless. Tests
can use real `StubActor`. `NpcActor` (future) MUST be mocked the same way
as `UserActor` — it'll hold an LLM client.

## testing-scenario

```python
@dataclass(frozen=True)
class Scenario:
    name: str
    scene: Scene.Model              # full Model, typically built via scene_from()
    chat_history: list[Message]     # pre-seeded into the per-test Scene
    input: Message                  # dispatched via scene.append()
    expect: Callable[[list[Message]], None]   # PyHamcrest assertion
```

```python
def scene_from(campaign: Campaign, scene_id: str, **overrides) -> Scene.Model:
    """Clone-with-overrides from test_campaign via Pydantic model_copy."""
    return campaign.scene(scene_id).to_model().model_copy(update=overrides)
```

- scenario-class, scenario-name, scenario-scene, scenario-chat-history,
  scenario-input, scenario-expect — invariants per attribute.
- scene-from-fn — the helper.
- scenario-expect-pyhamcrest: `expect` is a callable that runs PyHamcrest
  assertions (typically `assert_that(messages, has_item(...))` or similar).
  Raises `AssertionError` on mismatch — pytest reports cleanly.

## testing-runner

```python
async def run_scenario(scenario: Scenario, app: App) -> None:
    """Execute one Scenario against an App.

    1. run-scenario-build-scene: fresh SimpleScene from scenario.scene,
       characters resolved via app.campaigns[...].factory.get(id).
    2. run-scenario-seed-history: scene._messages.extend(scenario.chat_history)
       — bypasses the emit path so seeded messages don't trigger listeners.
    3. run-scenario-append: scene.append(scenario.input) — fires
       EntityChanged; listeners react (Character.notify spawns the actor
       cycle).
    4. run-scenario-await-idle: await scene.idle() — Scene tracks its
       spawned background tasks; idle() returns when all settle. Bounded
       by a small timeout to fail fast on wedges.
    5. run-scenario-check: scenario.expect(scene.messages).
    """
```

Tests parametrize over scenarios:

```python
@pytest.mark.integration
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
async def test_dispatch(scenario, test_app):
    await run_scenario(scenario, test_app)
```

## testing-sse

SSE handler tests use the per-entity URL and the `mock_user_actor` fixture.
The mock's `subscribe_to(entity, queue)` returns a controlled queue; the
test puts events on that queue and asserts the response loop yields them.

```python
@pytest.mark.integration
async def test_sse_yields_event(test_app, mock_user_actor):
    queue = asyncio.Queue()
    mock_user_actor.subscribe_to.return_value = queue

    transport = ASGITransport(app=test_app._fastapi)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        async with c.stream("GET", "/api/campaigns/{cid}/entities/{eid}/events") as r:
            await queue.put(EntityChanged(entity_id=..., hint=...))
            line = await anext(aiter(r.aiter_lines()))
            assert "entity_changed" in line
```

- testing-sse-mock-user-actor: SSE tests assert that the handler called
  `mock_user_actor.subscribe_to(entity, queue)` AND
  `mock_user_actor.unsubscribe_from(...)` on disconnect. The handler's
  delegation is the test surface — not the QueueListener internals.

## testing-eval-extension

When LLM actors land, eval matchers (LLM-judge, semantic similarity) plug
in as PyHamcrest `BaseMatcher` subclasses — Scenario shape, runner, and
fixtures don't change. The integration may pull in DeepEval's `GEval` or
similar for the LLM scoring; the wrapping is local to the matcher impl.
