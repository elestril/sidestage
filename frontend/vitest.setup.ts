// frontend-test-setup: registers @testing-library/jest-dom matchers
// (`toBeInTheDocument`, `toHaveTextContent`, etc.) with vitest's `expect`,
// and installs a strict console-spy that fails any test producing
// unexpected console.warn / console.error output.
//
// Tests that EXPECT a log (e.g. exercising an error path) must assert on
// the spy and clear it before afterEach runs:
//
//   expect(console.error).toHaveBeenCalledWith(...);
//   vi.mocked(console.error).mockClear();
//
// Without that, the unexpected-log assertion fires.
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, vi } from 'vitest';

beforeEach(() => {
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  const warnMock = vi.mocked(console.warn);
  const errorMock = vi.mocked(console.error);
  const warnCalls = warnMock.mock.calls;
  const errorCalls = errorMock.mock.calls;
  warnMock.mockRestore();
  errorMock.mockRestore();
  if (errorCalls.length > 0) {
    throw new Error(
      `unexpected console.error (${errorCalls.length}): ${JSON.stringify(errorCalls)}. ` +
        'If the test intentionally triggers errors, assert on the spy and ' +
        'mockClear() before afterEach.',
    );
  }
  if (warnCalls.length > 0) {
    throw new Error(
      `unexpected console.warn (${warnCalls.length}): ${JSON.stringify(warnCalls)}. ` +
        'If the test intentionally triggers warnings, assert on the spy and ' +
        'mockClear() before afterEach.',
    );
  }
});
