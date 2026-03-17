# debugging

## Overview {#overview}

The system MUST provide transparency into its behavior for operators, DMs,
and external coding agents. This includes structured logging, distributed
tracing, and a programmatic interface for inspection and control.

## MCP Interface {#mcp-interface}

<a id="coding-agent-access"></a>
External coding agents MUST be able to interact with the campaign through an
MCP endpoint. This provides administrative tools for inspecting and modifying
campaign state beyond what in-game agents can access.

See [sidestage#actor](/specs/sidestage.md#actor) for the actor model.

## Structured Logging {#logging}

<a id="request-context"></a>
Every operation MUST be traceable through structured logs tagged with request
context (request ID, user, origin).

<a id="campaign-logs"></a>
Each campaign MUST have independent log streams for operational messages and
chat event traces.

## Distributed Tracing {#tracing}

<a id="opentelemetry"></a>
The system MUST support OpenTelemetry tracing for end-to-end visibility into
agent behavior, prompt handling, tool execution, and memory operations.

<a id="tracing-toggle"></a>
Tracing MUST be toggleable at runtime without restart.

## Health Monitoring {#health}

<a id="health-visibility"></a>
Campaign health state (HEALTHY, DEGRADED, UNHEALTHY) MUST be observable
through both the API and logs. See
[sidestage#principle-production-health](/specs/sidestage.md#principle-production-health).
