/**
 * Browser e2e: same scenario as test_events_dataflow (integration) and
 * test_cuj_hello (Python e2e), driven through a real Chromium against the
 * built SPA served by FastAPI on :8000. Proves the SSE → React state →
 * DOM render path that lower tiers don't touch.
 *
 * .tests: cuj-hello-send, cuj-hello-respond, frontend-sse-client-dataflow,
 *         frontend-messagelist-items, frontend-input-submit-button
 */
import { test, expect } from '@playwright/test';

test('cuj-hello-browser', async ({ page }) => {
  await page.goto('/');

  // Wait for SSE to come up so the input is enabled. The connected indicator
  // is an `aria-label="connected"` span in the header (per ChatView).
  await expect(
    page.getByLabel('connected'),
    'frontend-state-connected: header shows the live SSE state via an ' +
      'aria-label="connected" indicator',
  ).toBeVisible({ timeout: 5_000 });

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
    'frontend-messagelist-items: alice\'s "Hi" must render in the message ' +
      'list at (parlor, 0) after the POST round-trips through SSE',
  ).toContainText('Hi', { timeout: 5_000 });

  // bob (stub) replies via the listener cycle. The reply is at index=1 and
  // carries StubActor's canonical body (the character's own body field).
  const bobsReply = page.locator(
    '[data-testid="message-item"][data-scene-id="parlor"][data-index="1"]',
  );
  await expect(
    bobsReply,
    'cuj-hello-respond: bob\'s reply must arrive via SSE and render at ' +
      '(parlor, 1) after the listener-driven npc cycle settles',
  ).toBeVisible({ timeout: 5_000 });
  await expect(
    bobsReply,
    'cuj-hello-respond: bob\'s reply body is the stub character\'s body',
  ).toContainText('*nods quietly*');
});
