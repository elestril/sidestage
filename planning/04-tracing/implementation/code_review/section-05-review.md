# Section 05: API Endpoints — Code Review

## Critical — Fixed
1. **Toggle endpoint uses raw dict**: Changed to Pydantic `_TracingToggleRequest(enabled: bool)` for proper validation.

## High — Fixed
2. **No bounds on limit/offset**: Added `Query(ge=1, le=1000)` for limit, `Query(ge=0)` for offset.
3. **shutdown_tracing() not guarded**: Wrapped in try/except in lifespan to protect PID cleanup.

## Medium — Accepted/Deferred
4. **Broadcast callback not wired**: The `make_trace_broadcast_callback` utility exists and is tested. Wiring into the application startup flow (where `init_tracing` is called) is deferred to application integration, not the endpoint layer.
5. **start_time_ms vs ISO start_time**: The SQLite exporter returns `start_time_ms` which is more useful for the JS frontend than an ISO string. Kept as-is.
6. **Inline config import**: Deferred import avoids circular dependency. Acceptable pattern.
7. **Missing docs**: Will update docs after all sections complete.
