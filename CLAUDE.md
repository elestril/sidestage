# Sidestage Agent Directives

- Sidestage is completely driven by the specs/ directory. EVERY iteration must
  strive to keep the specs and the code STRICTLY in sync
- The specs can ONLY be ammended after an explicit design converstation with the
  user. You MUST NOT deviate from the written specs.
- You MUST ONLY use relative paths in ALL tool calls — Read, Write, Edit, Bash, and Agent prompts.
  NEVER write an absolute path (e.g. /home/...) anywhere. Use paths like `specs/entity.md`,
  `src/sidestage/entity.py`. This applies to you AND to every subagent you spawn.
  Subagent prompts MUST NOT contain any absolute paths either.
- NEVER read, edit, or otherwise touch `.env` / `.env.*` files. They hold secrets.
  Permission rules in `.claude/settings.json` enforce this as a hard ban — do not
  attempt workarounds (`cat`, `source`, `grep`, indirect Bash). If you need to know
  whether a variable is set, ask the user. Subagent prompts inherit this rule.
