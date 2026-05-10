# Sidestage Agent Directives

- Sidestage is completely driven by the specs/ directory. EVERY iteration must
  strive to keep the specs and the code STRICTLY in sync
- The specs can ONLY be ammended after an explicit design converstation with the
  user. You MUST NOT deviate from the written specs.
- You MUST ONLY use relative paths in ALL tool calls — Read, Write, Edit, Bash, and Agent prompts.
  NEVER write an absolute path (e.g. /home/...) anywhere. Use paths like `specs/entity.md`,
  `src/sidestage/entity.py`. This applies to you AND to every subagent you spawn.
  Subagent prompts MUST NOT contain any absolute paths either.
