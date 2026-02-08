# `sidestage.mcp_bridge`

MCP (Model Context Protocol) bridge for Sidestage.

Exposes the Sidestage campaign API as MCP tools over Streamable HTTP transport.
The MCP endpoint is mounted on the existing FastAPI server at /v1/mcp.

## Functions

### `create_mcp_server(orchestrator: SidestageOrchestrator) -> FastMCP`

Create a FastMCP server with tools wired to the orchestrator.

All tool functions close over the orchestrator instance to access
campaign state, sync manager, and scene management.

Args:
    orchestrator: The SidestageOrchestrator instance.

Returns:
    A configured FastMCP server ready to be mounted.
