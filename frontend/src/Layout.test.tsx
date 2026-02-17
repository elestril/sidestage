import { screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { renderWithContext } from './test-helpers';
import { Layout } from './Layout';
import type { Scene } from './types';

const defaultScenes: Scene[] = [
  { id: 'campaign_planning', name: 'Campaign Planning', body: '', current_gametime: null, events: [] },
  { id: 'tavern', name: 'Tavern Scene', body: '', current_gametime: null, events: [] },
];

const renderLayout = (
  initialPath = '/scenes/campaign_planning',
  scenes: Scene[] = defaultScenes,
) => {
  return renderWithContext(
    <MemoryRouter initialEntries={[initialPath]}>
      <Layout><div data-testid="child-content">Page Content</div></Layout>
    </MemoryRouter>,
    { fetchOverrides: { '/v1/scenes': { body: scenes } } },
  );
};

describe('Layout', () => {
  it('header renders "Sidestage" title and nav links', async () => {
    renderLayout();
    expect(screen.getByText('Sidestage')).toBeInTheDocument();
    // "Scenes" appears both as nav link and sidebar heading, so use role queries
    expect(screen.getByRole('link', { name: /Scenes/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Entities/ })).toBeInTheDocument();
  });

  it('sidebar renders scene list from context', async () => {
    renderLayout();
    await waitFor(() => {
      expect(screen.getByText('Campaign Planning')).toBeInTheDocument();
      expect(screen.getByText('Tavern Scene')).toBeInTheDocument();
    });
  });

  it('scene links navigate to correct URLs', async () => {
    renderLayout();
    await waitFor(() => {
      expect(screen.getByText('Tavern Scene')).toBeInTheDocument();
    });
    const tavLink = screen.getByText('Tavern Scene').closest('a');
    expect(tavLink).toHaveAttribute('href', '/scenes/tavern');
  });

  it('active scene is visually highlighted', async () => {
    renderLayout('/scenes/campaign_planning');
    await waitFor(() => {
      expect(screen.getByText('Campaign Planning')).toBeInTheDocument();
    });
    const activeLink = screen.getByText('Campaign Planning').closest('a');
    expect(activeLink).toHaveClass('bg-[#1e1e1e]');

    const inactiveLink = screen.getByText('Tavern Scene').closest('a');
    expect(inactiveLink).not.toHaveClass('bg-[#1e1e1e]');
  });
});
