Now I have all the context I need. Let me generate the section content.

# Section 01: Vitest Infrastructure

## Overview

This section sets up the Vitest testing framework for the Sidestage React 19 SPA frontend. The goal is a working `npm test` command that can discover and run test files using jsdom, with global test APIs (`describe`, `it`, `expect`), Testing Library DOM matchers, and automatic cleanup between tests. This section produces only the infrastructure -- mocks and component tests are in sections 02 and 03 respectively.

**No other sections need to be completed before this one.** Sections 02 (frontend mocks) and 03 (component tests) depend on this section being complete.

## Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `/home/harald/src/sidestage/frontend/package.json` | Modify | Add test dependencies and scripts |
| `/home/harald/src/sidestage/frontend/vite.config.ts` | Modify | Add `test` block to existing defineConfig |
| `/home/harald/src/sidestage/frontend/tsconfig.test.json` | Create | Test-specific TypeScript config with vitest/globals types |
| `/home/harald/src/sidestage/frontend/tsconfig.json` | Modify | Add reference to tsconfig.test.json |
| `/home/harald/src/sidestage/frontend/src/test-setup.ts` | Create | Setup file: matchers, cleanup, mock restoration |
| `/home/harald/src/sidestage/frontend/src/canary.test.ts` | Create | Canary test validating infrastructure works |

## Tests First

Write a canary test file at `/home/harald/src/sidestage/frontend/src/canary.test.ts` that validates all aspects of the infrastructure before any component tests exist. This test file must pass once the infrastructure is fully wired up.

```
Tests for canary.test.ts:
  - Vitest can find and run a trivial test file (canary test)
  - globals mode works (describe/it/expect available without imports)
  - jsdom environment is active (document and window exist)
  - setup file runs (jest-dom matchers like .toBeInTheDocument() work)
  - afterEach cleanup runs (component unmount between tests)
  - TypeScript compiles test files without errors (vitest/globals types resolve)
```

The canary test file should contain:

```typescript
// frontend/src/canary.test.ts
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
```

The canary test imports nothing. If it passes, it proves: Vitest found the file, global APIs work, jsdom is active, jest-dom matchers are extended onto `expect`, and cleanup runs between tests. The TypeScript compilation check is implicit -- if `tsc -p tsconfig.test.json` (or equivalently `vitest typecheck`) succeeds, the types are correct.

## Implementation Details

### 1. Add devDependencies to package.json

Add these five packages to the `devDependencies` in `/home/harald/src/sidestage/frontend/package.json`:

- `vitest` -- the test runner, integrates natively with Vite
- `@testing-library/react` (version >=16.0.0 required for React 19 compatibility) -- component rendering and queries
- `@testing-library/jest-dom` -- DOM assertion matchers (`.toBeInTheDocument()`, `.toHaveTextContent()`, etc.)
- `@testing-library/user-event` -- user interaction simulation (v14+ is async-by-default, all calls must be awaited)
- `jsdom` -- DOM environment for Node.js (chosen over happy-dom for better Tiptap/marked compatibility)

Also add two new scripts to the `scripts` block:

```json
"test": "vitest",
"test:run": "vitest run"
```

The `test` script runs Vitest in interactive watch mode (for development). The `test:run` script runs a single pass (for CI).

After modifying package.json, run `npm install` in the `frontend/` directory to install the new dependencies.

### 2. Add test block to vite.config.ts

Modify `/home/harald/src/sidestage/frontend/vite.config.ts` to add a `test` block inside the `defineConfig` call. This approach (rather than a separate `vitest.config.ts`) ensures tests inherit the existing React plugin, Tailwind plugin, and `base: '/sidestage/'` setting.

The existing file looks like:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  base: '/sidestage/',
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    proxy: {
      '/v1': {
        target: 'http://localhost:8000',
        ws: true
      },
      '/agents': 'http://localhost:8000',
      '/sessions': 'http://localhost:8000',
    }
  }
})
```

Add a `test` property at the top level of the config object:

```typescript
test: {
  globals: true,
  environment: 'jsdom',
  setupFiles: './src/test-setup.ts',
  css: false,
}
```

Key settings explained:
- **`globals: true`** -- makes `describe`, `it`, `expect`, `vi`, `beforeEach`, `afterEach` etc. available globally without importing them in every test file.
- **`environment: 'jsdom'`** -- provides `document`, `window`, and the full DOM API in Node.js. Required for React Testing Library to render components.
- **`setupFiles: './src/test-setup.ts'`** -- this file runs before every test file. It configures matchers, cleanup, and global mocks.
- **`css: false`** -- disables CSS processing in tests. The Tailwind CSS 4 Vite plugin does not work in jsdom, so CSS is irrelevant for unit tests.

### 3. Create tsconfig.test.json

Create `/home/harald/src/sidestage/frontend/tsconfig.test.json`:

```json
{
  "extends": "./tsconfig.app.json",
  "compilerOptions": {
    "types": ["vitest/globals"]
  },
  "include": ["src"]
}
```

This file extends the existing `tsconfig.app.json` (which already has React JSX support, strict mode, ES2022 target, bundler module resolution, etc.) and adds `"types": ["vitest/globals"]` so TypeScript recognizes `describe`, `it`, `expect`, `vi`, etc. as global types without explicit imports. This is the companion to `globals: true` in the Vitest config.

A separate file is needed because `tsconfig.app.json` has `"verbatimModuleSyntax": true` and `"types": ["vite/client"]`. Adding `vitest/globals` to that config would make Vitest types available in production code, which is undesirable.

Also modify `/home/harald/src/sidestage/frontend/tsconfig.json` to add a reference to the test config:

```json
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" },
    { "path": "./tsconfig.test.json" }
  ]
}
```

### 4. Create test-setup.ts

Create `/home/harald/src/sidestage/frontend/src/test-setup.ts`. This file runs before every test file (configured via `setupFiles` in vite.config.ts).

The setup file must do three things for this section. (Section 02 will add WebSocket and fetch mocks to this file later.)

```typescript
// frontend/src/test-setup.ts

// 1. Extend expect with jest-dom matchers (.toBeInTheDocument(), .toHaveTextContent(), etc.)
import '@testing-library/jest-dom/vitest'

// 2. Cleanup rendered components after each test to prevent cross-test DOM pollution.
//    React Testing Library's cleanup unmounts React trees rendered with render().
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup()
})

// 3. Restore all mocks after each test to prevent cross-test mock pollution.
//    This resets vi.spyOn, vi.fn, vi.mock state between tests.
afterEach(() => {
  vi.restoreAllMocks()
})
```

Notes on the import style: `@testing-library/jest-dom/vitest` is the Vitest-specific entry point that properly extends Vitest's `expect` (not Jest's). This is the recommended approach for Vitest + jest-dom integration.

The `afterEach(cleanup)` call is critical. Without it, components rendered in one test remain mounted in the next test, causing cross-test pollution and confusing failures. The `vi.restoreAllMocks()` similarly prevents mock state from leaking between tests.

### 5. Verification Procedure

After implementing all the above, verify the infrastructure by running:

```bash
cd /home/harald/src/sidestage/frontend && npm install && npm run test:run
```

This should:
1. Install the five new devDependencies
2. Run Vitest in single-run mode
3. Discover and execute `src/canary.test.ts`
4. All four tests pass

Additionally, verify TypeScript compilation of test files:

```bash
cd /home/harald/src/sidestage/frontend && npx tsc -p tsconfig.test.json --noEmit
```

This should complete with no errors, confirming that `vitest/globals` types are properly resolved.

## Background Context

**Why jsdom over happy-dom:** The frontend uses `marked` (markdown parser) and Tiptap (rich text editor built on ProseMirror). Both rely on relatively complete DOM implementations. jsdom has better compatibility with these libraries than happy-dom. While happy-dom is faster, correctness matters more here.

**Why `css: false`:** Tailwind CSS 4 uses a Vite plugin (`@tailwindcss/vite`) rather than PostCSS. This plugin generates CSS at build time and does not function in the jsdom test environment. Disabling CSS in tests avoids errors and is standard practice -- component tests verify behavior and DOM structure, not visual styling.

**Why `globals: true`:** This is a developer experience choice. Without it, every test file would need `import { describe, it, expect, vi } from 'vitest'`. With it, these are available globally, matching the convention used by Jest (which many developers expect). The `tsconfig.test.json` provides the corresponding TypeScript type definitions.

**Existing frontend stack:** The frontend is a React 19 SPA using Vite v7, TypeScript 5.9, Tailwind CSS 4, React Router v7, Tiptap for rich text editing, and `marked` for markdown rendering. The app has an `AppContext` (React context provider) that manages all state including WebSocket connections and fetch calls. Every component that needs app state is wrapped in `<AppProvider>`.