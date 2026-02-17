import { screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { renderWithContext } from './test-helpers';

// Mock Tiptap modules (ScenesPage/EntitiesPage render components that import Tiptap)
vi.mock('@tiptap/react', () => ({
  useEditor: () => null,
  EditorContent: () => <div data-testid="mock-editor">Mock Editor</div>,
}));
vi.mock('@tiptap/starter-kit', () => ({ default: {} }));
vi.mock('tiptap-markdown', () => ({ Markdown: {} }));
vi.mock('@tiptap/extension-placeholder', () => ({
  default: { configure: () => ({}) },
}));

import { AppContent } from './App';

const defaultScenes = [
  { id: 'campaign_planning', name: 'Campaign Planning', body: '', current_gametime: null, events: [] },
  { id: 'tavern', name: 'Tavern', body: 'A warm place', current_gametime: null, events: [] },
];

describe('App', () => {
  it('renders without crashing', () => {
    renderWithContext(
      <MemoryRouter basename="/sidestage" initialEntries={['/sidestage/']}>
        <AppContent />
      </MemoryRouter>,
      { fetchOverrides: { '/v1/scenes': { body: defaultScenes } } },
    );
    expect(screen.getByText('Sidestage')).toBeInTheDocument();
  });

  it('default route shows main view with ChatWidget', async () => {
    renderWithContext(
      <MemoryRouter basename="/sidestage" initialEntries={['/sidestage/']}>
        <AppContent />
      </MemoryRouter>,
      { fetchOverrides: { '/v1/scenes': { body: defaultScenes } } },
    );

    // The "/" route redirects to /scenes/campaign_planning which renders ScenesPage
    await waitFor(() => {
      expect(screen.getByPlaceholderText('Describe actions or speak as characters...')).toBeInTheDocument();
    });
  });

  it('/sidestage/scenes/:sceneId route triggers load for that scene', async () => {
    renderWithContext(
      <MemoryRouter basename="/sidestage" initialEntries={['/sidestage/scenes/tavern']}>
        <AppContent />
      </MemoryRouter>,
      {
        fetchOverrides: {
          '/v1/scenes': { body: defaultScenes },
          '/v1/scenes/tavern/messages': { body: [] },
        },
      },
    );

    // ScenesPage sets currentSceneId to 'tavern', triggering message load
    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith('/v1/scenes/tavern/messages');
    });
  });
});
