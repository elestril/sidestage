---
name: sidestage-server-monitor
description: Run, monitor, and interact with the Sidestage server (AgentOS). Capture logs and execute API calls for debugging and verification.
---

# Sidestage Server Monitor

This skill provides tools to manage and interact with the Sidestage server for specific campaigns.

## Core Commands

### Manage Server
- `python3 .gemini/skills/sidestage-server-monitor/scripts/server_manager.py start <campaign_name> [--reload]`
- `python3 .gemini/skills/sidestage-server-monitor/scripts/server_manager.py stop <campaign_name>`
- `python3 .gemini/skills/sidestage-server-monitor/scripts/server_manager.py status <campaign_name>`

### Monitor Logs
- `python3 .gemini/skills/sidestage-server-monitor/scripts/server_manager.py monitor <campaign_name>`
  - **Exit Code 2 (ERROR)**: Analyze logs and fix the root cause.
  - **Exit Code 3 (WARNING)**: Pause and ask the user for instructions.

### Interact with API
- `python3 .gemini/skills/sidestage-server-monitor/scripts/server_manager.py call <campaign_name> <endpoint> [METHOD] [DATA_JSON]`
  - Example (List Agents): `... call test /agents`
  - Example (Run Agent): `... call test /agents/sidestage-co-author/runs POST '{"message": "who is barnaby", "stream": false}'`

## Troubleshooting
- Logs: `~/.sidestage/<campaign_name>/server.log`
- PIDs: `~/.sidestage/<campaign_name>/server.pid`
- Environment: The script automatically sets `SIDESTAGE_CAMPAIGN` for the server process.
