// Extend expect with jest-dom matchers (.toBeInTheDocument(), .toHaveTextContent(), etc.)
import '@testing-library/jest-dom/vitest'

// Cleanup rendered components after each test to prevent cross-test DOM pollution.
import { cleanup } from '@testing-library/react'
import { MockWebSocket } from './__mocks__/MockWebSocket'

// Replace globalThis.WebSocket with MockWebSocket
globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket

// jsdom doesn't implement scrollIntoView
Element.prototype.scrollIntoView = vi.fn()

// Mock marked to avoid pulling in the full library in tests
vi.mock('marked', () => ({
  marked: {
    parse: (content: string) => `<p>${content}</p>`,
    use: vi.fn(),
  },
}))

// Set up a default no-op fetch mock that returns empty responses
beforeEach(() => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => ({
    ok: true,
    status: 200,
    json: async () => ({}),
    text: async () => '{}',
  } as Response))
})

// Cleanup components, restore mocks, and reset WebSocket state after each test
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  MockWebSocket.reset()
})
