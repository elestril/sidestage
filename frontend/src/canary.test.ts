// No imports needed -- globals: true means describe/it/expect are available.
// This file validates the Vitest infrastructure is correctly configured.

describe('Vitest infrastructure canary', () => {
  it('can run a trivial test', () => {
    expect(1 + 1).toBe(2)
  })

  it('has jsdom environment active', () => {
    expect(typeof document).toBe('object')
    expect(typeof window).toBe('object')
    expect(document.createElement('div')).toBeInstanceOf(HTMLDivElement)
  })

  it('has jest-dom matchers available', () => {
    const el = document.createElement('div')
    el.textContent = 'hello'
    document.body.appendChild(el)
    expect(el).toBeInTheDocument()
    expect(el).toHaveTextContent('hello')
    el.remove()
  })

  it('afterEach cleanup runs between tests', () => {
    // If afterEach(cleanup) works, previous test's DOM additions are gone.
    // document.body should be empty (or at least not contain 'hello' from prior test).
    expect(document.body.textContent).not.toContain('hello')
  })
})
