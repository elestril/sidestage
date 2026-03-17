# styleguide

## Specification {#specification}

The [specs](/specs) directory contains comprehensive specifications of the
entire project. Every feature and user visible behavior MUST be specified here.
Changes MUST comply with all existing specifications, and all changes MUST
contain a comprehensive update to the appropriate specification.

Specifications MUST describe the intended design, not the current
implementation. When the current implementation does not match the spec, a TODO
entry MUST mark the gap. Specs without TODOs are assumed to accurately reflect
the code as-implemented.

### Structure {#structure}

Specifications are organized into two levels:

- **Feature specs** (`specs/`) — User-visible concepts and requirements.
- **Implementation specs** (`specs/implementation/`) — Technical design and
  API details that implement the features.

Every file (or chapter) in `specs/implementation/` MUST contain an
`Implements:` line linking back to the feature spec it realizes:

```
Implements: [sidestage#campaign](/specs/sidestage.md#campaign)
```

If no feature spec exists for an implementation spec, a feature-level spec
MUST be created first. This ensures all implementation work traces back to a
user-visible requirement.

### Format {#format}

Specifications are labeled markdown format: Every specification MUST have a
markdown link: an anchor link to a markdown section, or a custom anchor inline.

### TODOs {#todos}

Specifications that are not fully implemented MUST contain TODO entries. Each
TODO MUST follow this format:

```
> TODO(<a id="todo-short-id"></a>todo-short-id): Imperative description of
> what needs to change.
```

- The `todo-short-id` MUST be unique within the file and serve as an anchor
  for unambiguous cross-referencing (e.g.,
  `[entities#todo-unified-visibility](/specs/implementation/entities.md#todo-unified-visibility)`).
- The description MUST be an imperative sentence (e.g., "Add X", "Replace Y
  with Z", "Migrate A to B").
- TODOs MUST be blockquote (`>`) paragraphs so they render as strong visual
  highlights.
- When a TODO relates to another TODO, it MUST cross-reference it using the
  standard spec link format.

### Testing {#testing}

All specification MUST be comprehensively covered by tests. Tests failures MUST
output the exact link to the specification being violated.

## Development Workflow {#development-workflow}

All development follows in order:

1. A feature branch is created.
2. Specification is written and committed to the branch.
3. Comprehensive tests are written. At minimum ALL sections (identified by
   section headers), and ALL custom anchors MUST have comprehensive tests, which
   are identified by assert messages that return the exact specification link
   being tested, and possibly outline which exact part of the specification is
   being tested.
4. Tests are reviewed and committed to the branch (Red TDD stage)
5. Code is written. The code writer MUST NOT look at the tests, the code writer
   can ONLY execute the tests and must rely on the assert outputs of the
   failing tests.
6. Agents MUST NEVER merge anything into the main branch.
