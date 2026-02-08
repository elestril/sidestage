# `sidestage.migration.parser`

Parse markdown/ directory tree into entities, memories, and chat logs.

## Functions

### `parse_directory(markdown_dir: Path) -> ParseResult`

Parse the markdown/ directory tree into entities, memories, and chat logs.

Reads all type subdirectories (characters/, locations/, items/, scenes/,
events/), parses .md files as entities, reads .d/ companion directories
for memories and chat logs.

Args:
    markdown_dir: Path to the markdown/ directory.

Returns:
    ParseResult with parsed entities, memories, chatlogs, and any
    errors/warnings encountered during parsing. Never raises exceptions
    for bad input -- all issues are reported in the result.
