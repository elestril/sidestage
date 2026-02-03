# Observability in Sidestage

Sidestage provides transparency into agent behavior, prompt logging, and tool execution primarily through structured file logging.

## Server Logging

Every campaign maintains its own dedicated log file.

- **Location:** `~/.sidestage/<campaign_name>/server.log`
- **Contents:**
    - Agent thought process and turn history.
    - Tool execution logs and return values.
    - WebSocket connection events.
    - API request/response metadata.

## OpenTelemetry (Planned)

The core platform includes `opentelemetry-sdk` as a dependency. Future updates will include:
- Exporting traces to local collectors (like Jaeger).
- In-browser visualization of agent traces.
- Performance profiling for LLM inference.

## Why this matters
Observability allows Game Masters to:
- Inspect the exact prompts being sent to the LLM.
- Debug why an agent made a specific decision.
- Verify that tools are being called with the correct parameters.
- Audit performance (latency) of agent runs.
