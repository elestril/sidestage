# speclint: Spec format and link linter

Sidestage is driven by `specs/`. Specs and code must stay strictly in sync,
and the format itself is defined by `specs/spec.md`. `speclint` mechanically
enforces that format and that spec-to-spec links are bidirectional and
resolve. It rides the same parsing pipeline as `just spec` — `markdown-it-py`
for `.md` files and `docspec-python` for pydoc docstrings — so anything
`pydoc-markdown` can render, the linter can lint.

The linter lives at `src/speclint/` as a sibling package to `src/sidestage/`:
dev tooling, not shipped runtime. Invoked via `just speclint` or
`uv run speclint`.

## speclint-scope: V1 covers Groups A and B

V1 enforces structural and link-consistency rules over the unified spec
corpus (`specs/*.md` plus pydoc docstrings under `src/sidestage/`).
Spec-to-code symbol resolution (Group C) and spec-to-test coverage
(Group D) are explicitly out of scope and planned as future phases.

- speclint-scope-group-a: Structural — label format, uniqueness, hierarchy,
  length, heading weight.
- speclint-scope-group-b: Link consistency — target syntax, bidirectional
  balance, label resolution.
- speclint-scope-deferred: Symbol-shaped link targets (`Class.method`) are
  parsed but not resolved; Group C will index public symbols and validate.

## speclint-rules: The nine V1 rule codes

Each rule has a stable code `SL0NN`. Severity is hardcoded per code;
`--warn-as-error` promotes warnings to errors for CI use.

- speclint-rules-sl001: `spec-labels-file` — `specs/<name>.md`'s `# <label>:`
  H1 must have `label == name`. Error.
- speclint-rules-sl002: `spec-labels-headings` — every `##`/`###` heading must
  match `<label>: <description>`. Error.
- speclint-rules-sl003: `spec-labels-unique` — all labels globally unique
  across both `.md` files and pydoc docstrings. Error.
- speclint-rules-sl004: `spec-hierarchy` — a multi-segment label like
  `foo-bar-baz` requires one of `foo` or `foo-bar` in the index. H1 labels
  (file roots) are exempt. Error.
- speclint-rules-sl005: `spec-length` — warn at ≥ 900 words, error at ≥ 1100
  words per `.md` file.
- speclint-rules-sl006: `spec-headings-weight` — warn on `##` sections with
  fewer than three non-blank content lines.
- speclint-rules-sl007: link target syntax — comma-separated kebab labels or
  `Class[.member]` symbols; rejects prose. Error.
- speclint-rules-sl008: bidirectional balance — if A `.implements` B and B is
  a known kebab label, B must carry `.implemented-by: A` (and symmetrically
  for `.tested-by` / `.tests`). Error.
- speclint-rules-sl009: unresolved spec-label target — every kebab-label
  target must exist in the index. Symbol targets skipped in V1. Error.

## speclint-suppression: Suppressing diagnostics

Two layers, ruff-style. Resolution order is inline > per-file > global.

- speclint-suppression-inline: `<!-- speclint: ignore SL003 -->` immediately
  before the offending line in `.md`, or `# speclint: ignore SL003` in a
  docstring. Suppresses the next non-blank line.
- speclint-suppression-config: `pyproject.toml` carries `[tool.speclint]`
  with `ignore = [...]` (global) and `per-file-ignores = { ... }` (path
  scoped). Both are merged with any `--ignore` flags from the CLI.

Suppressed diagnostics still surface under `--show-ignored` so legacy debt
stays visible rather than rotting silently.

## speclint-rollout: V1 ships opt-in, not in `just lint`

V1 does not wire `_speclint` into the parallel `lint` recipe because the
existing corpus carries substantial format and link drift accumulated before
the rule set existed. Forcing all of it green at once would be a sweeping
spec edit that the linter rollout itself can't justify.

- speclint-rollout-opt-in: `just speclint` runs the linter on demand against
  `specs/` and `src/sidestage/`. Exit code is nonzero on unsuppressed errors.
- speclint-rollout-backlog: First-run output is a known drift backlog —
  duplicate labels split across `.md` and docstrings, unbalanced links,
  compound root labels missing their prefix parent. Each item is real and
  resolves with a spec edit after design conversation.
- speclint-rollout-promote: Wiring `_speclint` into the parallel `lint`
  recipe is a follow-up PR once the backlog is small enough that the
  precommit gate is useful rather than blocking.
