import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithContext } from './test-helpers';
import type { Entity } from './types';

// Mock Tiptap modules that don't work in jsdom
vi.mock('@tiptap/react', () => ({
  useEditor: () => null,
  EditorContent: () => <div data-testid="mock-editor">Mock Editor</div>,
}));
vi.mock('@tiptap/starter-kit', () => ({ default: {} }));
vi.mock('tiptap-markdown', () => ({ Markdown: {} }));
vi.mock('@tiptap/extension-placeholder', () => ({
  default: { configure: () => ({}) },
}));

import { EntityBrowser, EntityModal } from './EntityBrowser';

const makeEntity = (overrides: Partial<Entity> = {}): Entity => ({
  id: 'char-1',
  name: 'Aria',
  body: 'A brave warrior',
  type: 'Character',
  ...overrides,
});

const testEntities: Entity[] = [
  makeEntity({ id: 'char-1', name: 'Aria', type: 'Character' }),
  makeEntity({ id: 'loc-1', name: 'Tavern', body: 'A cozy place', type: 'Location' }),
  makeEntity({ id: 'item-1', name: 'Sword', body: 'A sharp blade', type: 'Item' }),
];

const renderBrowser = (entities: Entity[] = testEntities, selectedId: string | null = null) => {
  const onSelect = vi.fn();
  const result = renderWithContext(
    <EntityBrowser selectedId={selectedId} onSelect={onSelect} />,
    { fetchOverrides: { '/v1/entities': { body: entities } } },
  );
  return { ...result, onSelect };
};

describe('EntityBrowser', () => {
  it('renders entity list from context', async () => {
    renderBrowser();
    await waitFor(() => {
      expect(screen.getByText('Aria')).toBeInTheDocument();
      expect(screen.getByText('Tavern')).toBeInTheDocument();
      expect(screen.getByText('Sword')).toBeInTheDocument();
    });
  });

  it('entity type filter shows available types', async () => {
    renderBrowser();
    await waitFor(() => {
      expect(screen.getByText('All')).toBeInTheDocument();
      expect(screen.getByText('Characters')).toBeInTheDocument();
      expect(screen.getByText('Locations')).toBeInTheDocument();
      expect(screen.getByText('Items')).toBeInTheDocument();
      expect(screen.getByText('Scenes')).toBeInTheDocument();
    });
  });

  it('selecting a type filter updates displayed entities', async () => {
    renderBrowser();
    const user = userEvent.setup();

    // Wait for entities to load
    await waitFor(() => {
      expect(screen.getByText('Aria')).toBeInTheDocument();
    });

    // Click "Characters" filter
    await user.click(screen.getByText('Characters'));

    // Only Character entities should be visible
    expect(screen.getByText('Aria')).toBeInTheDocument();
    expect(screen.queryByText('Tavern')).not.toBeInTheDocument();
    expect(screen.queryByText('Sword')).not.toBeInTheDocument();
  });

  it('clicking an entity selects it', async () => {
    const { onSelect } = renderBrowser();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Aria')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Aria'));
    expect(onSelect).toHaveBeenCalledWith('char-1');
  });

  it('EntityModal renders when entityId prop is set', async () => {
    renderWithContext(
      <EntityModal entityId="char-1" onClose={vi.fn()} />,
      {
        fetchOverrides: {
          '/v1/entities': { body: [makeEntity({ id: 'char-1', name: 'Aria' })] },
          '/v1/entities/char-1/markdown': { body: { markdown: '# Aria\nA warrior' } },
        },
      },
    );

    await waitFor(() => {
      expect(screen.getByText('Aria')).toBeInTheDocument();
    });
    // Should show the markdown content
    await waitFor(() => {
      expect(screen.getByText(/# Aria/)).toBeInTheDocument();
    });
  });

  it('EntityModal calls onClose when dismissed', async () => {
    const onClose = vi.fn();
    renderWithContext(
      <EntityModal entityId="char-1" onClose={onClose} />,
      {
        fetchOverrides: {
          '/v1/entities': { body: [makeEntity({ id: 'char-1', name: 'Aria' })] },
          '/v1/entities/char-1/markdown': { body: { markdown: '# Aria' } },
        },
      },
    );

    const user = userEvent.setup();
    await waitFor(() => {
      expect(screen.getByText('Close')).toBeInTheDocument();
    });
    await user.click(screen.getByText('Close'));
    expect(onClose).toHaveBeenCalled();
  });

  it('EntityModal returns null when entityId is null', () => {
    renderWithContext(
      <EntityModal entityId={null} onClose={vi.fn()} />,
    );
    // Component returns null -- no modal content should be rendered
    expect(screen.queryByText('Close')).not.toBeInTheDocument();
  });
});
