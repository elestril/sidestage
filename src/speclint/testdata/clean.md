# clean: A minimal well-formed spec for tests.

The clean fixture defines a tiny but valid label hierarchy used by the
extractor and rule tests.

## clean-child: A sub-spec under clean.

- clean-child-leaf: A leaf invariant.
  - .implements: clean-child
- .implemented-by: clean-child-leaf
