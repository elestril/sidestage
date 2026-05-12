# testing: How Sidestage is tested

Four tiers — unit (colocated, mocked deps), integration (multi-module
domain flows, no API), e2e (real uvicorn + httpx over TCP), eval
(behavioral; opt-in). Integration and e2e share scenario scaffolding —
`Scenario` dataclass + PyHamcrest matchers + a runner.

## testing-categories

- testing-categories-unit: One module, mocked cross-deps. Lives next to
  source as `*_test.py`. Fast (whole suite under one second).
- testing-categories-integration: Real Scene + Character + Actor + App,
  no API boundary, no live LLM. Integration uses `StubActor` only —
  deterministic, no network. Asserts on entity-level state via direct
  method calls. Lives in `tests/integration/`.
- testing-categories-e2e: Real uvicorn server on an ephemeral port, real
  client over TCP. Two flavors by driver:
  - testing-categories-e2e-http: Python `httpx.AsyncClient` (per
    `testing-fixture-test-server`). Lives in `tests/e2e/`.
  - testing-categories-e2e-browser: Playwright + Chromium against the
    built SPA. The browser tier owns the SSE → React → DOM path that
    HTTP-tier doesn't touch. Lives in `tests/playwright/`. Invoked via
    `just test-browser` (not part of `just test`'s inner loop because
    of the build step + browser launch).
- testing-categories-e2e-live-llm: Exactly ONE e2e test validates
  `NpcActor` end-to-end against a real LLM endpoint — same shape as
  the other e2e tests (real uvicorn, REST POST, SSE read) but with the
  npc owner actually wired to a real LLM. Carries `pytest.mark.e2e`
  AND `pytest.mark.live_llm` and auto-skips when the endpoint isn't
  up (see `testing-markers-live-llm`). Lives in `tests/e2e/`
  alongside the other e2e tests.
- testing-categories-eval: Behavioral evals against rubrics. Today every
  actor is deterministic so evals reduce to property checks; once
  LLM-backed actors land, evals slot in as PyHamcrest matchers calling
  an LLM judge. Opt-in. Lives in `tests/eval/`.

## testing-layout

```
src/sidestage/*_test.py     # unit tests, colocated
frontend/src/**/*.test.tsx  # vitest unit tests, colocated
tests/
├── conftest.py             # test_campaign, test_app, test_client
├── sidestage/              # canonical fixture instance-state root
│   └── campaigns/test_campaign/
├── lib/                    # Scenario / runner / matcher scaffolding
├── integration/            # @pytest.mark.integration, no API boundary
├── e2e/                    # @pytest.mark.e2e, real uvicorn + httpx
│   └── conftest.py         # test_server
├── playwright/             # Playwright + Chromium against built SPA
│   ├── package.json        # @playwright/test, get-port-cli
│   ├── playwright.config.ts
│   └── *.spec.ts
└── eval/                   # @pytest.mark.eval, opt-in
```

- testing-layout-test-campaign: Single canonical fixture campaign at
  `tests/sidestage/campaigns/test_campaign/`. Minimal — alice (user) + bob (stub) + parlor scene.
  Scenarios specialize via `scene_from(...)` overrides.
- testing-layout-no-matchers-module: Matchers come from `pyhamcrest`
  (dev dep). No custom matcher classes — `assert_that(actual, has_properties(...))`
  is enough. New matchers (e.g. `LLMJudge`) inherit `BaseMatcher` from PyHamcrest.

## testing-markers

Markers are registered in `pyproject.toml` (`[tool.pytest.ini_options]
markers`) and used both for tier selection (`pytest -m e2e`) and
skip-by-default (eval).

- testing-markers-default: `uv run pytest` runs unit + integration + e2e
  (including live_llm — see below); eval skipped.
- testing-markers-eval-opt-in: Eval tests carry `@pytest.mark.eval` AND
  `@pytest.mark.skipif(os.environ.get("EVAL") != "1", reason="eval-only")`.
- testing-markers-live-llm: Tests that hit a real LLM endpoint carry
  `@pytest.mark.live_llm` AND `@pytest.mark.skipif(not _llm_endpoint_up(), …)`
  where `_llm_endpoint_up()` pings the configured endpoint's `/health`.
  No env-var opt-in: if the endpoint is up at collection time the test
  runs; otherwise it auto-skips. Use `@pytest.mark.timeout(90)` to
  override the default 2s — first-call weight load on a local server
  can take dozens of seconds.

## testing-failure-message

Every assertion that proves a spec invariant MUST include the spec label
verbatim in its message, followed by a description of what the invariant
requires and the observed value that violated it. The label-in-message
rule applies even when the enclosing test name already encodes the label
(per `spec-links-tested-by-implicit`) — duplication keeps the failure
line self-contained, so an agent reading only the failure output knows
which spec to load without opening the test file.

```python
assert len(scene.messages) == 1, (
    "scene-append-records: scene.messages MUST contain the appended "
    f"message; got len={len(scene.messages)}"
)
```

- testing-failure-message-modal: State the requirement in modal terms
  ("MUST", "expected") rather than indicative. A message like
  `"default port is 8000; got 54321"` is self-contradictory in the
  failure log — the assertion failed precisely because the claim isn't
  true. Write `"default port MUST be 8000; got 54321"` or
  `"expected port 8000; got 54321"` instead.
- testing-failure-message-exempt: Setup/precondition assertions (object
  is not None, fixture wired correctly) are exempt — they prove no spec
  invariant. Their failure points at infrastructure, not at a spec.
- testing-failure-message-pyhamcrest: PyHamcrest matchers satisfy the
  rule when the `reason` argument starts with the spec label:
  `assert_that(messages, has_length(1), reason="scene-append-records: …")`.

## testing-no-stray-logs

Warnings and unexpected log output drown signal in test runs. The suite
treats both as failures so they stay quiet.

- testing-no-stray-logs-pytest: `pyproject.toml`'s
  `[tool.pytest.ini_options].filterwarnings` starts with `"error"` — any
  unhandled warning becomes an exception. Third-party noise we cannot fix
  earns a surgical `ignore:<pattern>:<Category>` line after it; never a
  blanket suppression.
- testing-no-stray-logs-vitest: `vitest.setup.ts` installs a per-test
  `console.warn` / `console.error` spy and asserts no calls in
  `afterEach`. Tests that intentionally exercise error paths declare
  the expected output and `mockClear()` before afterEach runs.

## testing-lint: Lint + type check

Python uses `ruff` (lint + format) and `pyright` (type check). Frontend
uses `tsc --noEmit` (type check) and Vitest (which integrates Vite for
import-side checks). All three are gated by `just test-all`.

- testing-lint-ruff: `ruff check` runs the conservative rule set
  (E/W/F/I/B/UP/SIM) configured in `pyproject.toml`. `ruff format`
  enforces formatting; `just format` applies it. New rules need a
  spec-amend, not a CI-amend.
- testing-lint-pyright: Pyright (the engine Pylance uses in the editor)
  runs in `basic` mode. Editor and CLI see the same diagnostics — no
  "passes locally, fails in CI" surprises. Every function — including
  tests, helpers, and inner closures — carries a return-type annotation
  so pyright checks the body. `-> None` is the right answer for ~95% of
  test functions; explicit types catch real bugs the rest of the time.
- testing-lint-typecheck-fe: `tsc --noEmit` is invoked by `just
  typecheck` and runs as part of `just test-fe`.

## testing-fixtures

Shared fixtures live in `tests/conftest.py`. E2E-only fixtures live in
`tests/e2e/conftest.py`.

- testing-fixture-test-campaign: `test_campaign` (**session-scoped**) —
  loads `tests/sidestage/campaigns/test_campaign/` once. Characters and factory are read-only
  and shared across the session.
- testing-fixture-test-app: `test_app` (function-scoped) — fresh `App`
  with `App.campaigns` and `App.factory` set from `test_campaign`,
  `state = SERVING`. Resets `App.factory` on teardown.
- testing-fixture-test-client: `test_client` (function-scoped) — sync
  `TestClient(test_app._fastapi)` for non-streaming routes.
- testing-fixture-test-server: `test_server` (function-scoped, in
  `tests/e2e/conftest.py`) — real uvicorn on an ephemeral `127.0.0.1`
  port; yields the base URL. E2E tests take `test_server: str` and
  connect via `httpx.AsyncClient(base_url=...)`. Required for streaming
  responses where httpx's in-process `ASGITransport` would buffer the
  full body and deadlock against an open SSE stream.
- testing-fixture-mock-user-actor: `mock_user_actor` (function-scoped) —
  scripted `MagicMock(spec=UserActor)` registered at `App._actors["user"]`.
  Used by **unit** tests of the SSE handler (per
  `testing-mock-user-actor`); e2e tests use the real UserActor.

## testing-mock-user-actor

UserActor holds edge state (queue subscriptions). **Unit** tests of the
SSE handler MUST use a scripted mock instead of the real `UserActor`:

- testing-mock-user-actor-edge: A real `UserActor` would carry queue
  subscriptions across tests. Mocks isolate per-test.
- testing-mock-user-actor-script: Tests drive scripted SSE behavior by
  controlling which queue `subscribe_to` accepts and asserting on
  `unsubscribe_from` cleanup.

E2E tests use the real UserActor — its `subscribe_to`/`unsubscribe_from`
delegation to `entity.subscribe(QueueListener)` is exactly what e2e is
exercising. Cleanup on disconnect is verified by closing the httpx
stream and observing that no listeners leak on the entity.

`StubActor` doesn't need mocking — deterministic and stateless.
`NpcActor` holds a litellm client; unit tests patch `litellm.acompletion`
directly (per the existing `npc_actor_test.py`). Integration tests do
not use `NpcActor` at all — the single live-LLM validation is the e2e
test (`testing-categories-e2e-live-llm`).

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

SSE tests split by tier:

- testing-sse-unit: The SSE route handler is unit-tested by driving it
  directly with a request mock whose `is_disconnected()` flips after a
  bounded number of polls, and a controlled `asyncio.Queue` injected via
  patching `sidestage.server.asyncio.Queue`. The handler's call to
  `mock_user_actor.subscribe_to(entity, queue)` (and matching
  `unsubscribe_from` on close) is the test surface — not the QueueListener
  internals.
- testing-sse-e2e: End-to-end SSE goes through `test_server` (real
  uvicorn). Open `client.stream("GET", events_url)`, POST concurrently to
  trigger an emission, read SSE frames from the response. A brief
  `asyncio.sleep(0.05)` before the POST ensures the SSE handler has
  reached `subscribe_to` before the emit fires.
- testing-sse-no-asgi-transport: Do NOT use `httpx.ASGITransport` for SSE.
  It awaits the ASGI app to completion before returning the response,
  which deadlocks against an open streaming generator. Use real uvicorn
  via `test_server` instead.
