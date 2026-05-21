# unbalanced: SL008 + SL009 fixture.

- unbalanced-a: References an unresolved target and a one-way link.
  - .implements: nonexistent-spec
  - .implemented-by: unbalanced-b
- unbalanced-b: Does not point back at unbalanced-a.
