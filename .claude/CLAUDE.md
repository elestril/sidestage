# Sidestage

Agentic ttRPG assistant.

## Principles

- All work must be traceable via UNAMBIGUOUS REFERENCES: CUJ → design doc →
  external docs → test invariants → code.
- NEVER guess. Resolve ambiguity in dialogue.
- Do exactly what was asked, then STOP.
- ALL tool calls MUST use paths relative to the workspace root.

## TDD Workflow

All production code goes through red-green via subagents:

1. **Red**: `testwriter` writes failing tests.
2. **Green**: `coder` writes minimal code to pass them.
3. **Refactor**: Only if explicitly requested.

The orchestrator MUST NOT write tests or production code directly.
