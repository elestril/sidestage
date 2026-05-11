## spec: Meta-specification for writing specifications

This project is entirely driven by specifications, that form a traceable
unbroken logic chain from high level product requirements and critical user
journeys down to testable invariants and ultimately the actual implementation.

### spec-layout: The parts of a specification

- spec-prose: A spec document SHOULD start with a prose section briefly
  describing the intent of the spec.
- spec-current: Specs describe what is implemented now. They do not describe
  future plans, aspirations, or out-of-scope features. If it is not in the code,
  it is not in the spec. Specs and code are kept in sync.
- spec-length: Spec files must not exceed ~1000 words. This allows agents to
  load specs incrementally without overwhelming their context window. If a spec
  grows beyond this, split it into focused sub-files.

### spec-location: Where specs live

Specs split across two physical homes:

- spec-location-markdown: `specs/*.md` owns top-down design — product goal,
  CUJs, dataflows that cross process boundaries, and any cross-cutting
  concern that does not belong to a single class.
- spec-location-pydoc: Per-class realisation lives in pydoc on the
  corresponding Python class, attribute, method, or module-level symbol.
  The docstring IS the spec — same labels, same invariants, same link
  bullets that would otherwise live in markdown. This eliminates the
  spec-vs-code drift that bare type declarations enable.
- spec-location-split: Class spec files in `specs/` keep the prose and any
  cross-cutting sections (dataflows, on-disk format, CUJ-implementing
  routes) but defer per-symbol invariants to pydoc.

### spec-build: Generated markdown view

- spec-build-tool: `pydoc-markdown` (dev dependency, configured in
  `pydoc-markdown.yml` at the repo root). It walks `src/sidestage` and
  emits a clean markdown view — public surface only, no implementation
  bodies — so agents and reviewers can reason about specs without loading
  the full source.
- spec-build-style: Pydoc uses the **Google** docstring convention.
  `pydoc-markdown` is configured with the Google parser. New code SHOULD
  use Google sections (`Args:`, `Returns:`, `Raises:`) where they apply;
  the labeled-invariant + `.implements:` lines are plain Markdown content
  inside the docstring and render as-is.
- spec-build-output: Generated markdown lives at `specs/generated/api.md`
  (gitignored, regenerated on demand).
- spec-build-invocation: `uv run pydoc-markdown` from the repo root.

### spec-format: How specs are formatted in markdown

- spec-labels: All binding specs have labels, which precede the actual text of
  the spec, separated by a ':'. Spec labels are english words concatenated by
  `-`.
  - spec-labels-unique: All spec labels must be globally unique in the project.
  - spec-labels-file: The top-level label of a spec document is encoded in both
    the filename (e.g. `chat.md`) and the file title (e.g. `# chat: ...`). The
    filename IS the label.
  - spec-labels-headings: Section headings within a spec file CAN also carry
    labels (e.g. `## chat-connect: ...`). They are sub-specs of the file's
    top-level spec.
  - spec-headings-weight: Reserve `##` section headings for substantial sub-specs.
    Minor implementation specs SHOULD be grouped as bullets under a single heading
    rather than each getting their own `##` section.

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
  metadata. Both directions are independently maintained; having both makes
  reviews robust to drift on either axis:
  ```
  - spec-foo: Description.
    - .implements: parent-spec, OtherClass.method
    - .implemented-by: child-spec-a, ConcreteClass.method
    - .tested-by: TestFoo.test_happy_path, cuj-hello-send
  ```
  - spec-links-implements: Upward link — "this spec point implements the named target."
  - spec-links-implemented-by: Downward link — "this spec point is implemented by the named target."
  - spec-links-tested-by: Test link — "this spec point is proven by the named
    test(s)." The value is any selector that uniquely picks out the test in
    its runner: `pytest -k <selector>` for Python, `vitest -t <selector>`
    for TypeScript, `playwright test -g <selector>` for browser tests. The
    selector may be a method/test name, a class/`describe` name, or a
    parametrize / `test('<name>')` id.
    - spec-links-tested-by-implicit: Every labeled spec invariant
      `foo-bar-baz` implicitly has a colocated unit test named after it.
      Python: `test_foo_bar_baz` in `*_test.py` (dashes → underscores,
      because Python identifiers can't contain dashes). TypeScript:
      `test('foo-bar-baz', …)` in `*.test.tsx` (the test name is a
      string, so dashes are preserved verbatim). Either spelling is
      selected by the runner's name-filter flag (`pytest -k foo-bar-baz`
      OR `vitest -t foo-bar-baz`). The implicit link is NOT written
      out. A missing unit test of the expected name is a defect.
    - spec-links-tested-by-explicit: Write `.tested-by` only when the
      implicit link does not apply: the test lives outside the colocated
      `*_test.py` (typically an integration test in `tests/integration/`),
      or the test name does not follow the `test_<spec-name>` convention
      (e.g. a parametrized scenario id like `cuj-hello-send`).
  - spec-links-tests: Reverse of `.tested-by`. Test docstrings carry
    `.tests: <spec-label>[, …]` pointing at the spec invariants the test
    proves. Same value rules as `.implements`.
  - spec-links-both: When the same edge exists, BOTH ends carry the link. If
    `A.implements: B`, then `B.implemented-by: A` should also appear; if
    `A.tested-by: TestThing`, then `TestThing.tests: A` should also appear.
    Adding code does not drop the spec link; refactoring the spec hierarchy
    does not drop the code link.

- spec-link-targets: A link target is either a labeled bullet spec
  (`scene-append-history`) OR the name of a public class, method, or
  attribute (`SimpleScene.dispatch`, `Scene.messages`).
  - spec-link-targets-public-are-specs: All public classes, methods, and
    attributes ARE first-class specs. Their signature and invariant bullets
    ARE the spec text. They can appear as `.implements` / `.implemented-by`
    targets without any additional label.
  - spec-link-targets-private: Private members (leading underscore) are
    implementation detail and are NOT spec targets. Reference the public
    surface instead.

- spec-class-format: Class, method, and attribute specs ALL use a single
  preformatted signature line followed by labeled invariant bullets. Each
  invariant is a first-class spec label and implicitly defines a unit test
  case. Link bullets appear at the end:

  `dispatch(self, message: Message) -> list[Message]`
  - scene-dispatch-appends: Appends incoming message to history.
  - scene-dispatch-responds: Calls character.respond() on each Character.
  - scene-dispatch-returns: Returns the list of non-None responses.
  - .implements: cuj-hello-send
  - .implemented-by: SimpleScene.dispatch

  `active_scene_id: EntityId` *(attribute)*
  - campaign-active-scene-id-source: Loaded from `config.yaml`'s `active_scene_id` field.
  - campaign-active-scene-id-resolves: Resolves to the active Scene via `factory.get(self.active_scene_id)`.
  - .implements: campaign-config-active-scene
  - .implemented-by: Campaign.active_scene_id

  - spec-class-format-no-bare: Bare `attr: type` declarations without a
    labeled invariant are NOT a valid spec form. They describe a type
    without explaining what the attribute means or where its value comes
    from — and they let attributes slip into the codebase without anyone
    having to defend the design.

- spec-enum-members: Python's `Enum` has no per-member docstring convention
  (PEP 224 was rejected). When spec'ing an enum class, document each member
  as a labeled bullet inside the class docstring. The class itself takes
  the `<name>` label; each member takes a `<name>-<member>` label.
  ```python
  class ServerState(Enum):
      """server-state: Enum of server lifecycle states.

      - server-state-loading: Initial state during campaign load; all API
        endpoints return 503.
      - server-state-serving: Set once the campaign is fully loaded; API
        endpoints are active.
      """
      LOADING = 1
      SERVING = 2
  ```

- spec-public-required: ALL public symbols in code (classes, methods, properties,
  attributes, module-level functions and constants) MUST appear as specs with
  a full bidirectional link chain. Private members (leading underscore) are
  implementation detail and need no spec.
  - spec-public-required-implements: Every public spec MUST carry an
    `.implements` link pointing upward to its parent spec or higher-level CUJ.
    A spec with no upward link is unjustified — it has no reason to exist.
  - spec-public-required-implemented-by: Every spec describing observable
    behavior MUST carry an `.implemented-by` link pointing to the code symbol
    (or sub-spec) that realises it.
  - spec-public-required-no-orphan-code: Code may not introduce a public
    symbol without a corresponding spec. Adding an unspec'd public symbol is
    a defect — flag it during review and either spec it or make it private.
  - spec-public-required-no-orphan-spec: Likewise, a spec describing a public
    symbol that no longer exists in code is a defect — flag and resolve.

- spec-coverage-required: Every labeled spec invariant MUST be proven by
  at least one test. The link is implicit when a colocated unit test
  `test_<spec-name>` exists (per `spec-links-tested-by-implicit`); when
  coverage lives elsewhere — integration or e2e — the spec MUST carry an
  explicit `.tested-by` pointer (per `spec-links-tested-by-explicit`). A
  spec with neither is a defect.
  - spec-coverage-required-no-orphan-spec: A spec invariant lacking both
    an implicit unit test of the matching name AND an explicit
    `.tested-by` is a defect — flag during review and either add the
    test or remove the unjustified spec.
  - spec-coverage-required-no-orphan-test: Conversely, a `test_<spec-name>`
    that no longer maps to a real spec invariant is a defect — flag and
    delete (or rename to match a current invariant).

### spec-chain: The traceability chain

The chain runs: product goal → CUJ → class/method invariants.

- spec-chain-product: The top level captures the product goal in one sentence.
  - .implemented-by: one or more CUJ specs

- spec-chain-cuj: A CUJ (Critical User Journey) is a single spec whose sub-specs
  are its steps. Each step carries an explicit full label so it can be used as a
  stable link target in code and test assertions. Steps are numbered for
  readability — but the label, not the number, is the identity:

  ```
  - cuj-foo: User does X.
    1. cuj-foo-open: The user opens the app.
    2. cuj-foo-call-api: The app calls the API.
    3. cuj-foo-result: The user sees the result.
    - .implements: product-goal
    - .implemented-by: cuj-foo-open, cuj-foo-call-api, cuj-foo-result
  ```

  Inserting a new step only renumbers — existing labels are unaffected.

- spec-chain-indirect: Chains may be indirect. Intermediate spec layers may
  be inserted between any two levels — for example, a dataflow spec between a
  CUJ step and class-level invariants. Each intermediate spec implements the
  level above it, and is implemented-by the level below. The full chain remains
  unbroken as long as every leaf is traceable to a CUJ step.

- spec-chain-dataflow: Any data flow that crosses a process boundary MUST have
  a comprehensive dataflow spec with every step explicitly labelled. Process
  boundaries include: WebSocket, HTTP, database, filesystem, and remote RPC.
  Dataflow steps are first-class specs and must be traceable in both directions.

- spec-chain-invariant: Class and method level specs are the leaves of the
  chain. Each references the nearest spec above it in the chain.
  - .implements: the specific parent spec label

### spec-process: How specifications are written

- spec-top-down: Specifications MUST be written top-down. Start from the
  highest-level requirements (product goals, CUJs) and derive lower-level specs
  through an unbroken chain of logic. Each spec must be traceable to a parent
  spec above it.
  - spec-never-bottom-up: Never derive specs by reading the implementation. Code
    may not reflect intent. Specs describe WHAT and WHY, not WHAT THE CODE DOES.
- spec-interactive: Spec writing is an interview process. The spec writer MUST
  ask the user to clarify ambiguities, missing requirements, unstated
  constraints, and design choices. The spec writer MUST NEVER improvise or fill
  gaps from assumptions. Draft one level at a time, get sign-off, then proceed.
