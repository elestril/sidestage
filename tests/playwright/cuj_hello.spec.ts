/**
 * Browser e2e: same scenario as test_events_dataflow (integration) and
 * test_cuj_hello (Python e2e), driven through a real Chromium against the
 * built SPA served by FastAPI on :8000. Proves the WS → registry → React
 * state → DOM render path that lower tiers don't touch.
 *
 * .tests: cuj-hello-send, cuj-hello-respond, frontend-ws-client-dataflow,
 *         frontend-messagelist-items, frontend-input-submit-button
 */
import { test, expect, type WebSocket } from '@playwright/test';

test('cuj-hello-browser', async ({ page }) => {
  // Capture the WS handshake and the first outbound subscribe frame.
  const wsOpened: WebSocket[] = [];
  const subscribeFrames: string[] = [];
  page.on('websocket', (ws) => {
    wsOpened.push(ws);
    ws.on('framesent', (event) => {
      const payload =
        typeof event.payload === 'string'
          ? event.payload
          : Buffer.from(event.payload).toString('utf-8');
      if (payload.includes('"subscribe"')) {
        subscribeFrames.push(payload);
      }
    });
  });

  await page.goto('/');

  // Wait for WS to come up so the connection indicator goes green and the
  // input is enabled.
  await expect(
    page.getByLabel('connected'),
    'frontend-useconnected: header shows the live WS state via an ' +
      'aria-label="connected" indicator',
  ).toBeVisible({ timeout: 5_000 });

  // ws-dataflow-connect: at least one WS connection must have opened.
  expect(
    wsOpened.length,
    'ws-dataflow-connect: the page MUST open a WebSocket to /api/.../ws',
  ).toBeGreaterThanOrEqual(1);
  expect(wsOpened[0].url()).toMatch(/\/api\/campaigns\/.*\/ws$/);

  // ws-dataflow-subscribe: registry MUST have sent at least one subscribe
  // frame for the scene entity.
  await expect
    .poll(() => subscribeFrames.length, { timeout: 5_000 })
    .toBeGreaterThan(0);
  const parsed = subscribeFrames.map((f) => JSON.parse(f));
  expect(parsed.some((p) => p.op === 'subscribe' && p.entity_id === 'parlor')).toBe(
    true,
  );

  // Type "Hi" and press the send button.
  const input = page.getByTestId('message-input');
  await expect(
    input,
    'frontend-input-testid: the textarea carries data-testid="message-input"',
  ).toBeEnabled();
  await input.fill('Hi');
  await page.getByTestId('send-button').click();

  // alice's message lands at scene_id=parlor, index=0 — server canonical id.
  const alicesMessage = page.locator(
    '[data-testid="message-item"][data-scene-id="parlor"][data-index="0"]',
  );
  await expect(
    alicesMessage,
    "frontend-messagelist-items: alice's \"Hi\" must render in the message " +
      'list at (parlor, 0) after the POST round-trips through WS',
  ).toContainText('Hi', { timeout: 5_000 });

  // bob (stub) replies via the listener cycle. The reply is at index=1 and
  // carries StubActor's canonical body (the character's own body field).
  const bobsReply = page.locator(
    '[data-testid="message-item"][data-scene-id="parlor"][data-index="1"]',
  );
  await expect(
    bobsReply,
    "cuj-hello-respond: bob's reply must arrive via WS and render at " +
      '(parlor, 1) after the listener-driven npc cycle settles',
  ).toBeVisible({ timeout: 5_000 });
  await expect(
    bobsReply,
    "cuj-hello-respond: bob's reply body is the stub character's body",
  ).toContainText('*nods quietly*');
});
