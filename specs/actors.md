# actors: Actor hierarchy + LLM profiles

An **Actor** is a runtime singleton owned by `App`. It holds the edge
state that connects a Character to the world outside the Sidestage
process — LLM connections, future auth context. Character carries
world-data; Actor carries the I/O.

`Character.owner: Literal["user", "stub", "npc"]` selects the runtime
Actor via `App.get_actor(owner)`. Today: 1:1 — one singleton per
owner. When multi-user lands, `owner` generalises to per-instance
identifiers (`"bob"`, `"alice"`); each user-owned character resolves
to its own `UserActor` instance.

Actor is NOT an Entity — Actors don't receive events. The Listener
role for a Character belongs to `Character.notify` (per
[[entity-model]] `character-listener`); on a triggering
`EntityChanged`, Character spawns a task that calls
`self._actor.respond(...)`. A non-None reply text is published via
`self.speak(text)` — the same `@action` method that user-issued
EntityAction frames invoke. NPC and human paths converge on
`Character.speak`.

## actor-base: Actor

```python
class Actor(ABC):
    @abstractmethod
    def is_human(self) -> bool: ...

    @abstractmethod
    async def respond(
        self, message: Message, character: Character, scene: Entity
    ) -> str | None: ...
```

- actor-respond-contract: Generate reply text or return `None` for "no
  reply this turn". The returned string is the body that the
  Character will publish via `self.speak(text)`. `scene` is the Scene
  the message was appended to; LLM-backed actors use it to build
  prompt context. Stateless actors ignore it.

## actor-stub: StubActor

```python
class StubActor(Actor):
    def is_human(self) -> bool: ...      # False
    async def respond(self, ...) -> str: ...  # returns character.body
```

- actor-stub: Deterministic test responder. No edge state. `respond`
  returns `character.body` — content comes from the Character.
- .implemented-by: StubActor

## actor-user: UserActor

```python
class UserActor(Actor):
    def is_human(self) -> bool: ...           # True
    async def respond(self, ...) -> None: ... # always None
```

- actor-user-respond-noop: Returns `None` unconditionally — humans
  publish via the FE's `Character.speak` EntityAction, not via the
  listener cycle.
- actor-user-stateless: UserActor holds no per-user state today. The
  WS handler (`WsConnection`) owns its own listeners; UserActor is
  the marker for human-controlled characters and a seam for future
  auth + cross-WS state.
- .implemented-by: UserActor

## actor-npc: NpcActor

```python
class NpcActor(Actor):
    _entry: ModelEntry                        # immutable; from profile
    model_params: ClassVar[dict]              # request-shape overrides

    def is_human(self) -> bool: ...           # False
    async def respond(self, message, character, scene) -> str | None: ...
```

`NpcActor` talks to an LLM for response generation. Process-wide
singleton constructed from the active profile's `default` role
(`profile.models["default"]`). Multiple Characters with `owner="npc"`
share the instance — the entry is immutable, the litellm call is
stateless per request, concurrent `respond` calls across scenes need
no coordination.

- actor-npc-respond: `respond` builds `MessageContext(message, scene)`,
  calls `character.annotate_context(ctx)` (entity tree contributes
  prompt material), joins `ctx.annotations.values()` into the system
  prompt, shapes `scene.messages` into chat turns (sender=character →
  `assistant`, else `user`), calls `litellm.acompletion`, returns
  the completion text. Character.notify then publishes it via
  `self.speak(text)`.
- actor-npc-respond-error-none: Returns `None` on transport error,
  timeout, non-2xx, or empty/whitespace completion. Logs at WARNING
  or EXCEPTION. No in-band error placeholder messages — keeps scene
  history clean.
- actor-npc-respond-timeout: 60-second timeout on the litellm call.
  Budget for a local server that lazy-loads weights. Unit tests must
  mock litellm — pytest's 2s default would otherwise fail before the
  call returns.
- actor-npc-respond-max-tokens: Hard `max_tokens=512` cap. Without it,
  a runaway generation (no EOS, template glitch) keeps the server's
  decode loop pegged after the client disconnects.
- actor-npc-litellm-kwargs: Every call passes `model=entry.model`,
  `api_base=entry.endpoint`, `timeout=60`, `max_tokens=512`. API key
  comes from `os.environ[entry.api_key_env]` or a stub (`"sk-no-key"`)
  if `api_key_env` is unset.
- actor-npc-model-params: `model_params: ClassVar[dict]` is merged
  into every call after the defaults — actor-side overrides win. The
  Actor (not the profile YAML) is the source of truth for
  request-shape tuning (reasoning effort, temperature, custom
  `chat_template_kwargs`). Default disables reasoning preambles
  (`{"chat_template_kwargs": {"enable_thinking": False}}`) — NPC
  dialogue is in-character speech, not analysis, and reasoning
  tokens compete with content tokens for the `max_tokens` budget.
- actor-npc-consumes-context: Calls `character.annotate_context(ctx)`
  exactly once per `respond`. Never reads `character.body` directly
  — the Entity polymorphism is the contract. Subclassed Characters
  that override `annotate_context` (memories, schemes) need no
  NpcActor change.
- .implemented-by: NpcActor

## llm-profile: Endpoint topology

Sidestage talks to one or more LLMs (smart, dumb, narrator,
embedding, …). Each role maps to an HTTP endpoint reachable via
`litellm`. The topology — which roles exist, where to reach them —
is captured in **profiles**: YAML files under
`<sidestage_dir>/llm_profiles/`. The filename stem IS the profile
name. `InstanceConfig.llm_profile` selects which profile is active.

Sidestage does NOT spawn LLM servers. The endpoint declared by each
profile entry MUST already be reachable when sidestage starts. Bring
your own llama-server, vllm, ollama, or hosted API.

```yaml
# <sidestage_dir>/llm_profiles/<name>.yaml
models:
  default:                       # role name; free-form string
    endpoint: http://...         # litellm api_base (REQUIRED)
    model: openai/llama-3.2-3b   # litellm model string w/ provider prefix
    api_key_env: ANTHROPIC_API_KEY   # ENV VAR NAME (optional)
```

```python
class ModelEntry(BaseModel):
    endpoint: str
    model: str
    api_key_env: str | None = None

class LlmProfile(BaseModel):
    models: dict[str, ModelEntry]

def load_profiles(sidestage_dir: Path) -> dict[str, LlmProfile]: ...
```

- llm-profile-schema-models: `models` is `dict[role_name, ModelEntry]`.
  Roles are free-form. Code reads roles by name; the profile decides
  which physical endpoint backs each role.
- llm-profile-schema-api-key-by-env: API keys are NEVER stored in
  YAML. The profile names the env var; the value lives in `.env`
  (gitignored) or the shell. `App.main` calls `load_dotenv()` at
  startup so the var is in `os.environ`. Local servers that ignore
  the key may omit `api_key_env`.
- llm-profile-discovery: `<sidestage_dir>/llm_profiles/` is canonical.
  Profiles are added by dropping in a YAML, removed by `rm`. Missing
  dir returns `{}` — no error; the instance has no LLM topology.
- llm-profile-loader-validation: Malformed YAML raises at load time
  (`extra="forbid"`). Better to fail fast than at first LLM call.
- llm-profile-runtime-default-role: `NpcActor` reads
  `profile.models["default"]`. The role name `default` is the
  convention for the primary chat model; profiles MUST define a
  `default` entry to be NpcActor-usable. Multi-role wiring (separate
  `narrator`, `embedding` roles) is a future expansion.
- .implemented-by: ModelEntry, LlmProfile, load_profiles, NpcActor
