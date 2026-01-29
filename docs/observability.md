# Observability in Sidestage

Sidestage leverages Agno's built-in tracing and observability features to provide transparency into agent behavior, prompt logging, and tool execution.

## Built-in Tracing

Tracing is automatically enabled for every campaign. All interactions are captured and stored in the campaign's database.

### Data Storage
- **Location:** `~/.sidestage/<campaign_name>/sidestage.db`
- **Tables:**
    - `agno_spans`: Detailed logs of every model call and tool execution.
    - `agno_traces`: Groups of related spans (usually one per agent run).
    - `agno_sessions`: Metadata about each interaction session.

## Accessing Logs

### via API Endpoints
When the server is running, you can access raw observability data through the following endpoints:

- **List Traces:** `GET /traces`
- **Get Specific Trace:** `GET /traces/<trace_id>`
- **Session History:** `GET /sessions/<session_id>/runs`

### via Agno UI
You can use the official Agno UI to visualize these traces. 

1. Visit [app.agno.com](https://app.agno.com) or host the [open-source Agent UI](https://docs.agno.com/other/agent-ui).
2. Connect it to your local Sidestage server (usually `http://localhost:8000`).
3. You will be able to see a full dashboard of your agents, sessions, and a detailed trace timeline for every prompt and tool call.

## Why this matters
Observability is a core pillar of Sidestage. It allows Game Masters to:
- Inspect the exact prompts being sent to the LLM.
- Debug why an agent made a specific decision.
- Verify that tools are being called with the correct parameters.
- Audit the cost and performance (latency/tokens) of agent runs.
