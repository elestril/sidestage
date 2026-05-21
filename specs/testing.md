# testing: How Sidestage is tested

Four tiers — **unit** (colocated, mocked deps), **integration**
(multi-module domain flows, no API), **e2e** (real uvicorn + httpx +
websockets over TCP), **eval** (behavioural; opt-in). Integration and
e2e share scenario scaffolding — `Scenario` dataclass + PyHamcrest
matchers + a runner.

## testing-categories

- testing-categories-unit: One module, mocked cross-deps. Lives next to
  source as `*_test.py` / `*.test.tsx`. Fast (whole suite under one
  second).
- testing-categories-integration: Real Scene + Character + Actor + App,
  no API boundary, no live LLM. Uses `StubActor` only — deterministic,
  no network. Asserts on entity-level state via direct method calls.
  Lives in `tests/integration/`.
- testing-categories-e2e: Crosses a real process boundary. Three flavours:
  - testing-categories-e2e-http: Sidestage's API surface — real uvicorn
    on an ephemeral port driven by `httpx.AsyncClient` (REST) and
    `websockets.connect` (WS). Lives in `tests/e2e/`. `test_cuj_hello`
    is the canonical example.
  - testing-categories-e2e-browser: Playwright + Chromium against the
    built SPA. Owns the WS → registry → React → DOM path that
    HTTP-tier doesn't touch. Lives in `tests/playwright/`. Invoked via
    `just test-browser` (not in `just test`'s inner loop because of
    the build step + browser launch).
  - testing-categories-e2e-live-llm: The LLM provider surface — `NpcActor`
    calling a real OpenAI-compatible endpoint. Carries
    `pytest.mark.live_llm` and auto-skips when the endpoint isn't up.
- testing-categories-eval: Behavioural evals against rubrics. Opt-in
  (`EVAL=1`). Lives in `tests/eval/`.

## testing-layout

```
src/sidestage/*_test.py     # python unit tests, colocated
frontend/src/**/*.test.tsx  # vitest unit tests, colocated
tests/
├── conftest.py             # test_campaign, test_app, test_client
├── sidestage/              # canonical fixture instance root
├── lib/                    # Scenario / runner / matcher scaffolding
├── integration/            # @pytest.mark.integration
├── e2e/                    # @pytest.mark.e2e + conftest.py (test_server)
├── playwright/             # *.spec.ts
└── eval/                   # @pytest.mark.eval, opt-in
```

- testing-layout-test-campaign: Single canonical fixture campaign at
  `tests/sidestage/campaigns/test_campaign/`. Minimal — alice (user) +
  bob (stub) + parlor scene. Scenarios specialise via `scene_from(...)`
  overrides.
- testing-layout-no-matchers-module: Matchers come from `pyhamcrest`
  (dev dep). No custom matcher classes — `assert_that(...,
  has_properties(...))` is enough. New matchers (e.g. `LLMJudge`)
  inherit `BaseMatcher`.

## testing-markers

Registered in `pyproject.toml`:

- testing-markers-default: `uv run pytest` runs unit + integration +
  e2e (including `live_llm`); eval skipped.
- testing-markers-eval-opt-in: `@pytest.mark.eval` AND
  `@pytest.mark.skipif(os.environ.get("EVAL") != "1", ...)`.
- testing-markers-live-llm: `@pytest.mark.live_llm` AND
  `@pytest.mark.skipif(not _llm_endpoint_up(), ...)` where
  `_llm_endpoint_up()` pings the configured endpoint's `/health`.
  Use `@pytest.mark.timeout(90)` to override the 2 s default —
  first-call weight load on a local server can take dozens of seconds.

## testing-failure-message

Every assertion that proves a spec invariant MUST include the spec
label verbatim in its message, followed by what the invariant requires
and the observed value that violated it. Duplication keeps the failure
line self-contained.

```python
assert len(scene.messages) == 1, (
    "scene-append-records: scene.messages MUST contain the appended "
    f"message; got len={len(scene.messages)}"
)
```

- testing-failure-message-modal: State in modal terms ("MUST",
  "expected"), not indicative — `"default port is 8000; got 54321"` is
  self-contradictory in the failure log.
- testing-failure-message-exempt: Setup/precondition assertions (not
  None, fixture wired correctly) are exempt — their failure points at
  infrastructure, not a spec.
- testing-failure-message-pyhamcrest: PyHamcrest matchers satisfy the
  rule when `reason` starts with the spec label.

## testing-no-stray-logs

Warnings and unexpected log output drown signal. The suite treats both
as failures.

- testing-no-stray-logs-pytest: `pyproject.toml`'s
  `filterwarnings` starts with `"error"`. Third-party noise we cannot
  fix earns a surgical `ignore:<pattern>:<Category>` line; never a
  blanket suppression.
- testing-no-stray-logs-vitest: `vitest.setup.ts` installs a per-test
  `console.warn`/`console.error` spy and asserts no calls in
  `afterEach`. Tests that intentionally trigger errors assert on the
  spy and `mockClear()` before afterEach.

## testing-lint: Lint + type check

Python: `ruff` (lint + format), `pyright` (basic mode). Frontend:
`tsc --noEmit`, Vitest. All three are gated by `just test-all` (and
covered by the cheap `just lint`).

- testing-lint-pyright-return-types: Every function — tests, helpers,
  inner closures — carries a return-type annotation so pyright checks
  the body. `-> None` is the right answer ~95% of the time.
- testing-lint-ruff: `E/W/F/I/B/UP/SIM`. New rules need a spec-amend,
  not a CI-amend.

## testing-fixtures

Shared fixtures live in `tests/conftest.py`; e2e-only in
`tests/e2e/conftest.py`.

- testing-fixture-test-campaign: `test_campaign` (session-scoped) —
  loads `tests/sidestage/campaigns/test_campaign/` once. Read-only
  across the session.
- testing-fixture-test-app: `test_app` (function-scoped) — fresh `App`
  with campaigns + factory wired from `test_campaign`, `state =
  SERVING`. Resets `App.factory` on teardown.
- testing-fixture-test-client: `test_client` (function-scoped) — sync
  `TestClient(test_app._fastapi)` for non-streaming routes.
- testing-fixture-test-server: `test_server` (function-scoped, in
  `tests/e2e/conftest.py`) — real uvicorn on ephemeral `127.0.0.1`;
  yields base URL. Required for the WS endpoint — httpx's in-process
  `ASGITransport` cannot multiplex a long-lived socket alongside REST
  requests against the same app.

## testing-ws

The WS handler (`WsConnection`) owns its own listeners. WS handler
tests don't need a mocked actor; they exercise the handler directly.

- testing-ws-unit: Construct a `WsConnection` against a fake WebSocket
  (a small adapter with `receive_text` / `send_text` driven by asyncio
  queues, so the test scripts frames in and reads frames out). Assert
  that `subscribe` frames call `entity.subscribe(...)`, that
  `entity_changed` frames are sent when the entity emits, and that
  `unsubscribe` / socket-close paths remove every listener.
- testing-ws-e2e: Open a real WS via `websockets.connect(...)` against
  `test_server`, send `{"op":"subscribe","entity_id":<id>}`, trigger
  the emit on the server (REST POST in Phase 1; WS mutation in
  Phase 2), assert the `entity_changed` frame arrives. A brief
  `asyncio.sleep(0.05)` between subscribe and emit ensures the
  listener is registered before the emit fires.
- testing-ws-no-asgi-transport: Do NOT drive the WS endpoint via
  `httpx.ASGITransport`. Tests deadlock against a long-lived socket
  alongside concurrent REST traffic. Use `test_server`.

`StubActor` doesn't need mocking. `NpcActor` unit tests patch
`litellm.acompletion`. Integration tests do NOT use `NpcActor`; the
single live-LLM validation is in `tests/e2e/test_npc_actor_live.py`.

## testing-scenario

```python
@dataclass(frozen=True)
class Scenario:
    name: str
    scene: Scene.Model              # built via scene_from()
    chat_history: list[Message]     # pre-seeded into the per-test Scene
    input: Message                  # dispatched via scene.append()
    expect: Callable[[list[Message]], None]   # PyHamcrest assertion

def scene_from(campaign, scene_id, **overrides) -> Scene.Model:
    return campaign.scene(scene_id).to_model().model_copy(update=overrides)
```

## testing-runner

`run_scenario(scenario, app)` builds a fresh SimpleScene from the
scenario, seeds `chat_history` (bypassing emit so listeners don't fire),
calls `scene.append(scenario.input)` to fire `EntityChanged`, awaits
`scene.idle()` until cascading reactions settle (small timeout — fail
fast on wedges), then runs `scenario.expect(scene.messages)`. Tests
parametrize:

```python
@pytest.mark.integration
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
async def test_dispatch(scenario, test_app):
    await run_scenario(scenario, test_app)
```
