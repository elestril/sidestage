# Code Review Interview: Section 03 - Component Tests

**Date:** 2026-02-16

## Triage Summary

Reviewed 16 findings from the code-reviewer subagent. Most are either acceptable tradeoffs or minor style preferences. One auto-fix applied.

### Auto-fix: Improve EntityModal null assertion (#10)

The `EntityModal returns null when entityId is null` test checks `container.querySelector('.fixed')` which is coupled to the CSS class. Changed to check that no modal-specific content is rendered using `queryByText('Close')` which is more semantic.

### Let go (not actioned):

- **#3 (gametime `||` vs `??`):** This is a production code bug, not a test issue. Tests correctly verify behavior as-implemented.
- **#5 (missing save test):** The plan narrative itself acknowledges this may need to be "skipped in favor of E2E coverage" due to Tiptap mocking. The EntityBrowser test suite has 7 tests as planned.
- **#6 (marked mock tautology):** Testing that `marked.parse()` is called (content wrapped in `<p>`) vs raw text rendering is meaningful, even with a simple mock.
- **#8 (EntityBrowser on default route):** The plan's implementation approach says "look for ScenesPage elements" - EntityBrowser is only on `/entities`, not the default route.
- **#9 (Layout href vs behavior):** Checking `href` attributes on NavLink is a reasonable Layout-level test.
- **#12 (Tiptap mock duplication):** `vi.mock` must be in each file due to hoisting. Extracting to a shared file is possible but adds complexity for 4 lines.
- **#16 (scrollIntoView undocumented):** The `test-setup.ts` change is a standard jsdom polyfill. Will be noted in the section doc update.
