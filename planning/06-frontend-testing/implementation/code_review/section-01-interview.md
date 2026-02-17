# Code Review: Section 01 - Vitest Infrastructure

**Date:** 2026-02-16

## Auto-fixes

### Inconsistent import style in test-setup.ts
`afterEach` was explicitly imported from `vitest` while `vi` was used as a global. Since `globals: true` is configured, removed the explicit import to use both as globals consistently.

## Let Go

- tsconfig.test.json including `vite/client` alongside `vitest/globals` — necessary correction to the plan since `types` replaces rather than merges.
- Canary test ordering dependency — matches the plan, acceptable for a canary test.
- devDependencies alphabetical ordering — cosmetic, npm sorts on next install.
