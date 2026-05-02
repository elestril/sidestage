# spec: Meta-specification for writing specifications

This project is entirely driven by specifications, that form a traceable
unbroken logic chain from high level product requirements and critical user
journeys down to testable invariants and ultimately the actual implementation.

## spec-layout: The parts of a specification

- spec-prose: A spec document starts with a prose section briefly describing
  the intent of the spec.

## spec-format: How specs are formatted in markdown

- spec-labels: All specs have labels, which precede the actual text of the
  spec, separated by a ':'. Spec labels are english words concatenated by `-`.
  - spec-labels-unique: All spec labels must be globally unique in the project.
  - spec-labels-file: The top-level label of a spec document is encoded in
    both the filename (e.g. `chat.md`) and the file title
    (e.g. `# chat: ...`). The filename IS the label.
  - spec-labels-headings: Section headings within a spec file also carry
    labels (e.g. `## chat-connect: ...`). They are sub-specs of the file's
    top-level spec.

- spec-hierarchy: Hierarchies are desirable. Sub-specs are considered part of
  their parent spec — they narrow and refine it. The full label of a sub-spec
  encodes the hierarchy by sharing the parent's prefix:
  ```
  # chat: ...
  ## chat-connect: ...        ← sub-spec of chat
  - chat-connect-ws: ...      ← sub-spec of chat-connect
    - chat-connect-ws-auth:   ← sub-spec of chat-connect-ws
  ```
  Sub-specs at any level (headings, bullets, sub-bullets) are all first-class
  specs: they have unique labels, can be link targets, and can appear in
  `.implements` / `.implemented-by` lines.

- spec-links: Specs reference each other using dotted relationship lines as
  sub-bullets. These are not spec labels — the leading `.` marks them as
  metadata:
  ```
  - spec-foo: Description.
    - .implements: parent-spec
    - .implemented-by: child-spec-a, child-spec-b
  ```

## spec-chain: The traceability chain

The chain runs: product goal → CUJ → class/method invariants.

- spec-chain-product: The top level captures the product goal in one sentence.
  - .implemented-by: one or more CUJ specs

- spec-chain-cuj: A CUJ (Critical User Journey) is a single spec whose
  sub-specs are its steps. Each step carries an explicit full label so it can
  be used as a stable link target in code and test assertions. Steps are
  numbered for readability — but the label, not the number, is the identity:
  ```
  - cuj-foo: User does X.
    1. cuj-foo-open: The user opens the app.
    2. cuj-foo-call-api: The app calls the API.
    3. cuj-foo-result: The user sees the result.
    - .implements: product-goal
    - .implemented-by: cuj-foo-open, cuj-foo-call-api, cuj-foo-result
  ```
  Inserting a new step only renumbers — existing labels are unaffected.

- spec-chain-invariant: Class and method level specs are the leaves of the
  chain. Each one names the class/method and its exact behavior, and references
  the CUJ step it delivers.
  - .implements: the specific cuj step label

## spec-process: How specifications are written

- spec-top-down: Specifications MUST be written top-down. Start from the
  highest-level requirements (product goals, CUJs) and derive lower-level
  specs through an unbroken chain of logic. Each spec must be traceable to
  a parent spec above it.
  - spec-never-bottom-up: Never derive specs by reading the implementation.
    Code may not reflect intent. Specs describe WHAT and WHY, not WHAT THE
    CODE DOES.
- spec-interactive: Spec writing is an interview process. The spec writer
  MUST ask the user to clarify ambiguities, missing requirements, unstated
  constraints, and design choices. The spec writer MUST NEVER improvise or
  fill gaps from assumptions. Draft one level at a time, get sign-off, then
  proceed.
