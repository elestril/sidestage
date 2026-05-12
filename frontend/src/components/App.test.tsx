/**
 * Sanity-tier test for App.
 *
 * .tests: frontend-app-renders
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

// Stub Workspace so the App test asserts the dispatch contract, not the
// downstream bootstrap path (which has its own tests).
vi.mock('./Workspace', () => ({
  Workspace: () => <div data-testid="workspace-stub" />,
}));

import { App } from './App';

describe('App', () => {
  test('frontend-app-renders', () => {
    render(<App />);
    expect(
      screen.queryByTestId('workspace-stub'),
      'frontend-app-renders: App must render <Workspace /> at its root',
    ).toBeInTheDocument();
  });
});
