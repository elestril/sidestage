# llm-profiles: LLM endpoint topology, per instance

Sidestage talks to one or more LLMs (smart, dumb, narrator, embedding,
…). Each runtime role maps to an HTTP endpoint reachable via `litellm`.
The topology — which roles exist, where to reach them — is captured in
**profiles**.

Sidestage does NOT spawn LLM servers. The endpoint declared by each
profile entry MUST already be reachable when sidestage starts. Bring
your own llama-server, vllm, ollama, or hosted API.

A profile is one YAML file under `<sidestage_dir>/llm_profiles/`. The
filename stem IS the profile name. `InstanceConfig.llm_profile` selects
which profile is active for that instance.

## llm-profile-schema

```yaml
# <sidestage_dir>/llm_profiles/<name>.yaml
models:
  <role>:
    endpoint: str        # base URL of the HTTP endpoint (REQUIRED)
    model: str           # litellm model string with provider prefix (REQUIRED)
    api_key_env: str     # ENV VAR NAME holding the API key (optional)
```

- llm-profile-schema-models: `models` is a `dict[role_name, ModelEntry]`.
  Roles are free-form strings — `smart`, `dumb`, `narrator`, `embedding`,
  etc. Code reads roles by name; the profile decides which physical
  endpoint backs each role.
- llm-profile-schema-endpoint: `endpoint` is the base URL of the LLM
  HTTP endpoint. It is passed to litellm as `api_base` for every call.
- llm-profile-schema-model: `model` is the litellm model string with
  provider prefix included (`openai/local`, `openai/llama-3.2-3b`,
  `anthropic/claude-sonnet-4-5`). For OpenAI-compatible local servers
  (llama-server, vllm) the suffix after `openai/` is informational —
  the server has one model loaded.
- llm-profile-schema-api-key-by-env: API keys are NEVER stored in the
  YAML. The profile names the env var (`api_key_env: ANTHROPIC_API_KEY`);
  the value lives in `.env` (gitignored) or the shell. Sidestage loads
  `.env` via `python-dotenv` at startup so the var is in `os.environ`.
  Local servers that ignore the api_key may omit `api_key_env` — a stub
  is sent.

## llm-profile-discovery

- llm-profile-discovery-dir: `<sidestage_dir>/llm_profiles/` is the
  canonical location. The dev instance ships `sidestage/llm_profiles/`;
  the test instance ships `tests/sidestage/llm_profiles/`.
- llm-profile-discovery-stem: Filename stem == profile name. Profiles
  are added by dropping in a YAML, removed by `rm`. No registry file.
- llm-profile-discovery-missing-dir: If `<sidestage_dir>/llm_profiles/`
  doesn't exist, `load_profiles` returns `{}` — no error. The instance
  simply has no LLM topology defined.

## llm-profile-loader

`src/sidestage/llm_profile.py`:

```python
class ModelEntry(BaseModel):
    endpoint: str
    model: str
    api_key_env: str | None = None

class LlmProfile(BaseModel):
    models: dict[str, ModelEntry]

def load_profiles(sidestage_dir: Path) -> dict[str, LlmProfile]:
    """Scan <sidestage_dir>/llm_profiles/*.yaml; return dict by stem."""
```

- llm-profile-loader-validation: Malformed YAML raises at load time —
  better to fail fast than at first LLM call. Unknown fields raise too
  (`extra="forbid"`) so typos in the YAML surface immediately.
- .implemented-by: load_profiles, ModelEntry, LlmProfile

## llm-profile-runtime

`NpcActor` reads the active profile via `InstanceConfig.llm_profile` +
`load_profiles`, picks the role-specific entry, and dispatches via
`litellm.acompletion`. The role-to-entry resolution is a single point of
indirection — Actor never sees profile names or filenames.

- llm-profile-runtime-default-role: NpcActor reads
  `profile.models["default"]`. The role name `default` is the convention
  for the primary chat model; profiles MUST define a `default` entry to
  be NpcActor-usable. Multi-role wiring (separate `narrator`, `dumb`,
  `embedding` roles) is a future expansion that picks per-call.
- llm-profile-runtime-litellm-kwargs: Every call passes
  `model=entry.model`, `api_base=entry.endpoint`, and
  `api_key=os.environ[entry.api_key_env]` (or `"sk-no-key"` if
  `api_key_env` is unset). litellm's provider prefix in `model` routes
  the call; `api_base` overrides the provider's default base URL.
- .implemented-by: NpcActor
