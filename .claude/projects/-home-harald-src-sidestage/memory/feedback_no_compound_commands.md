---
name: No compound shell commands or scripts without explicit prompt
description: Never run compound shell commands or one-off coded scripts unless explicitly asked
type: feedback
---

Never run compound shell commands (pipes, `||`, `&&`, etc.) or one-off scripts without an explicit prompt from the user asking for it.

**Why:** The user expects shell commands to be simple, targeted, and intentional. Compound commands or scripts are a form of autonomous action that goes beyond what was asked.

**How to apply:** If a task seems to require a compound command, ask the user first. Only run simple, single-purpose commands unless explicitly told otherwise.
