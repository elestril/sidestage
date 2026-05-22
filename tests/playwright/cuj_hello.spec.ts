/**
 * Browser e2e: alice sends via WS `entity_action(say)`; bob (stub)
 * replies; both render. Proves the WS-only end-to-end path (no POST).
 *
 * .tests: cuj-hello-send, cuj-hello-respond,
 *         backend-ws-subscribe, backend-ws-entity-action,
 *         frontend-campaign-action-dispatch,
 *         frontend-campaign-collection-delta
 */
import { test, expect, type WebSocket } from '@playwright/test';

test('cuj-hello-browser', async ({ page }) => {
  const wsOpened: WebSocket[] = [];
  const sentFrames: string[] = [];
  const restCalls: string[] = [];
  page.on('websocket', (ws) => {
    wsOpened.push(ws);
    ws.on('framesent', (event) => {
      const payload =
        typeof event.payload === 'string'
          ? event.payload
          : Buffer.from(event.payload).toString('utf-8');
      sentFrames.push(payload);
    });
  });
  // Phase-2b invariant: the FE issues NO POSTs. Capture any /api/* POST
  // so the test fails fast if a regression reintroduces one.
  page.on('request', (req) => {
    if (req.method() !== 'GET' && req.url().includes('/api/')) {
      restCalls.push(`${req.method()} ${req.url()}`);
    }
  });

  await page.goto('/');

  await expect(
    page.getByLabel('connected'),
    'frontend-useconnected: header shows the live WS state via an ' +
      'aria-label="connected" indicator',
  ).toBeVisible({ timeout: 5_000 });

  expect(
    wsOpened.length,
    'ws-dataflow-connect: the page MUST open a WebSocket to /api/.../ws',
  ).toBeGreaterThanOrEqual(1);
  expect(wsOpened[0].url()).toMatch(/\/api\/campaigns\/.*\/ws$/);

  // backend-ws-subscribe: at least one subscribe frame for the scene entity.
  await expect
    .poll(() => sentFrames.filter((f) => f.includes('"subscribe"')).length, {
      timeout: 5_000,
    })
    .toBeGreaterThan(0);
  const subscribes = sentFrames
    .map((f) => JSON.parse(f) as Record<string, unknown>)
    .filter((p) => p.op === 'subscribe');
  expect(
    subscribes.some(
      (p) =>
        Array.isArray(p.entity_ids) &&
        (p.entity_ids as string[]).includes('parlor'),
    ),
    'backend-ws-subscribe: subscribe frame must carry entity_ids: ["parlor"]',
  ).toBe(true);

  const input = page.getByTestId('message-input');
  await expect(
    input,
    'frontend-input-testid: the textarea carries data-testid="message-input"',
  ).toBeEnabled();
  await input.fill('Hi');
  await page.getByTestId('send-button').click();

  // backend-ws-entity-action: send must emit an entity_action frame
  // (NOT a POST). Action is `say`; kwargs carry scene_id + body.
  await expect
    .poll(
      () => sentFrames.filter((f) => f.includes('"entity_action"')).length,
      { timeout: 5_000 },
    )
    .toBeGreaterThan(0);
  const actions = sentFrames
    .map((f) => JSON.parse(f) as Record<string, unknown>)
    .filter((p) => p.op === 'entity_action');
  const say = actions.find(
    (p) => p.action === 'say' && p.entity_id === 'alice',
  );
  expect(say, 'entity_action frame for alice.say not seen').toBeTruthy();
  const kwargs = say!.kwargs as Record<string, unknown>;
  expect(kwargs.scene_id).toBe('parlor');
  expect(kwargs.body).toBe('Hi');

  // alice's message renders.
  const alicesMessage = page.locator(
    '[data-testid="message-item"][data-scene-id="parlor"][data-index="0"]',
  );
  await expect(
    alicesMessage,
    "frontend-messagelist-items: alice's \"Hi\" must render in the message list",
  ).toContainText('Hi', { timeout: 5_000 });

  // bob (stub) reply via the listener cycle, at index 1.
  const bobsReply = page.locator(
    '[data-testid="message-item"][data-scene-id="parlor"][data-index="1"]',
  );
  await expect(
    bobsReply,
    "cuj-hello-respond: bob's reply must arrive via WS and render at (parlor, 1)",
  ).toBeVisible({ timeout: 5_000 });
  await expect(
    bobsReply,
    "cuj-hello-respond: bob's reply body is the stub character's body",
  ).toContainText('*nods quietly*');

  // frontend-no-rest: no non-GET REST calls to /api/*.
  expect(
    restCalls,
    'frontend-no-rest: the FE must not POST/PUT/DELETE to /api/* — writes ' +
      'flow through the WS as entity_action frames',
  ).toEqual([]);
});
