// Extend expect with jest-dom matchers (.toBeInTheDocument(), .toHaveTextContent(), etc.)
import '@testing-library/jest-dom/vitest'

// Cleanup rendered components after each test to prevent cross-test DOM pollution.
import { cleanup } from '@testing-library/react'

afterEach(() => {
  cleanup()
})

// Restore all mocks after each test to prevent cross-test mock pollution.
afterEach(() => {
  vi.restoreAllMocks()
})
