---
name: Use git worktrees for implementation
description: Always use worktree isolation when implementing code changes
type: feedback
---

Use git worktrees (Agent tool with `isolation: "worktree"`) for all implementation work.

**Why:** User wants implementation changes isolated from the main working tree to avoid polluting in-progress work and enable parallel tracks.

**How to apply:** When implementing a track or making code changes, launch agents with `isolation: "worktree"`. The worktree config in settings.local.json symlinks `node_modules`, `frontend/node_modules`, and `.venv` to avoid disk bloat.
