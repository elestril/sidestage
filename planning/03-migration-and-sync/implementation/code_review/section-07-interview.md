# Code Review Interview: Section 07 - Importer

**Date:** 2026-02-07

## Auto-Fixes

1. **Move CONNECTS_TO try/except inside inner loop.** One failed link() shouldn't skip remaining connections.
2. **Remove dead `last_accessed` variable.** Never referenced in Cypher construction.
3. **Remove redundant `hasattr(entity, "scene_id")`.** All Event instances have scene_id.
4. **Add memory count verification.** Plan specifies verifying both entity and memory counts.

## Let Go

- Private `_TYPE_TO_SUBLABEL` import: pragmatic reuse, same module family
- `gametime=0` for ChatMessages: chatlog format doesn't contain gametime data
- Positional ChatMessage IDs: acceptable for import, no external references
- Schema init error wording: minor, not worth separate error path
- Chatlog regex edge cases: greedy `.*` handles inner quotes; missing quote = unparseable is fine
- Partial failure tests: coverage sufficient for foundational section
- `_parse_chatlog_lines` unit tests: covered indirectly via integration test
