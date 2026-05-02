---
name: Use relative paths in tool calls
description: All tool calls must use paths relative to the workspace root, never absolute paths
type: feedback
---

Always use paths relative to the workspace root in ALL tool calls (Read, Edit, Write, Bash, etc.).

**Why:** CLAUDE.md explicitly requires it: "ALL tool calls MUST use paths relative to the workspace root."

**How to apply:** Instead of `/home/harald/src/sidestage/specs/spec.md`, use `specs/spec.md`. Instead of `/home/harald/src/sidestage/src/sidestage/ids.py`, use `src/sidestage/ids.py`.
