---
name: sidestage-server-monitor
description: Run and monitor the Sidestage server, capturing errors and logs for analysis. Use this when you need to start the backend for a specific campaign or debug server-side issues.
---

# Sidestage Server Monitor

This skill provides tools to manage the Sidestage server (AgentOS) for specific campaigns.

## Monitoring and Error Handling

When using the `monitor` command:
- **Exit Code 2 (ERROR)**: You MUST immediately analyze the logs, identify the root cause, and attempt to fix the error in the codebase or configuration.
- **Exit Code 3 (WARNING)**: You MUST pause and prompt the user with the warning details, asking for instructions on how to proceed.

### Troubleshooting
- Logs are stored in `~/.sidestage/<campaign_name>/server.log`.
- PID files are stored in `~/.sidestage/<campaign_name>/server.pid`.
- Ensure `poetry` is installed and the environment is set up before starting.