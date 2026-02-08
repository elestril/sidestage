# Code Review Interview: Section 02 - Tracing Core

**Date:** 2026-02-07

## Auto-Fixes

- **Finding 2 (No-op provider):** Add warning log when no exporters are provided.
- **Finding 3 (Exporter references):** Store in-memory exporter reference at module level for Section 05 API endpoints to query.
- **Finding 5 (Error recording):** Add try/except in trace_span to call record_error on exceptions.
- **Finding 7 (Toggle before init):** Add warning log when toggle_tracing called before init.

## Let Go

- **Finding 1 (OTel reset):** Best available approach for testing. The conftest fixture comment explains the intent.
- **Finding 4 (Async validation):** Intentional design per the plan - only async functions are supported.
- **Finding 6 (Type annotation):** Minor style concern.
- **Finding 8 (Duplicate test utilities):** Minor duplication, not worth abstracting for two files.
- **Finding 9 (Config mutation):** The autouse fixture creates fresh config per test.
- **Finding 10 (_cleanup):** The `_reset_otel_provider` autouse fixture handles OTel cleanup.
- **Finding 11 (Both exporters test):** Will be tested by Section 03 integration.
- **Finding 12 (gen_ai.completion test):** Minor coverage gap.
