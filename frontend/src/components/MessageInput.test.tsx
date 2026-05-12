/**
 * Sanity-tier tests for MessageInput.
 *
 * .tests: frontend-input-disabled, frontend-input-submit-button,
 *         frontend-input-submit-enter, frontend-input-testid
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test, vi } from 'vitest';

import { MessageInput } from './MessageInput';

describe('MessageInput', () => {
  test('frontend-input-disabled', () => {
    render(<MessageInput connected={false} onSend={() => {}} />);
    const textarea = screen.getByTestId('message-input') as HTMLTextAreaElement;
    const button = screen.getByTestId('send-button') as HTMLButtonElement;
    expect(
      textarea.disabled,
      'frontend-input-disabled: textarea must be disabled when connected=false',
    ).toBe(true);
    expect(
      button.disabled,
      'frontend-input-disabled: send button must be disabled when connected=false',
    ).toBe(true);
  });

  test('frontend-input-submit-button', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<MessageInput connected={true} onSend={onSend} />);
    const textarea = screen.getByTestId('message-input') as HTMLTextAreaElement;
    await user.type(textarea, 'hello');
    await user.click(screen.getByTestId('send-button'));
    expect(
      onSend.mock.calls,
      'frontend-input-submit-button: clicking Send must invoke onSend with ' +
        `the trimmed body; got calls=${JSON.stringify(onSend.mock.calls)}`,
    ).toEqual([['hello']]);
    expect(
      textarea.value,
      'frontend-input-submit-button: input must clear after a successful send',
    ).toBe('');
  });

  test('frontend-input-submit-button-trims-and-rejects-empty', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<MessageInput connected={true} onSend={onSend} />);
    const textarea = screen.getByTestId('message-input') as HTMLTextAreaElement;
    // Whitespace-only input keeps the send button disabled (button reads body.trim()).
    await user.type(textarea, '   ');
    const button = screen.getByTestId('send-button') as HTMLButtonElement;
    expect(
      button.disabled,
      'frontend-input-submit-button: send button must be disabled for ' +
        'whitespace-only input',
    ).toBe(true);
    expect(onSend.mock.calls.length).toBe(0);
  });

  test('frontend-input-submit-enter', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<MessageInput connected={true} onSend={onSend} />);
    const textarea = screen.getByTestId('message-input');
    await user.type(textarea, 'hi');
    await user.keyboard('{Enter}');
    expect(
      onSend.mock.calls,
      'frontend-input-submit-enter: Enter (without Shift) must invoke onSend',
    ).toEqual([['hi']]);
  });

  test('frontend-input-submit-enter-shift-noop', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<MessageInput connected={true} onSend={onSend} />);
    const textarea = screen.getByTestId('message-input') as HTMLTextAreaElement;
    await user.type(textarea, 'line1');
    await user.keyboard('{Shift>}{Enter}{/Shift}');
    expect(
      onSend.mock.calls.length,
      'frontend-input-submit-enter: Shift+Enter must NOT submit — newline ' +
        `behaviour only; got onSend calls=${onSend.mock.calls.length}`,
    ).toBe(0);
  });

  test('frontend-input-testid', () => {
    render(<MessageInput connected={true} onSend={() => {}} />);
    expect(
      screen.queryByTestId('message-input'),
      'frontend-input-testid: textarea must carry data-testid="message-input"',
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('send-button'),
      'frontend-input-testid: send button must carry data-testid="send-button"',
    ).toBeInTheDocument();
  });
});
