# llm-profiles: LLM endpoint topology, per instance

Sidestage talks to one or more LLMs (smart, dumb, narrator, embedding,
…). Each runtime role maps to either a local llama-server or a remote
HTTP endpoint. The topology — which roles exist, where to reach them —
is captured in **profiles**.

A profile is one YAML file under `<sidestage_dir>/llm_profiles/`. The
filename stem IS the profile name. `InstanceConfig.llm_profile` selects
which profile is active for that instance.

## llm-profile-schema

```yaml
# <sidestage_dir>/llm_profiles/<name>.yaml
models:
  <role>:
    local: bool          # true → managed by `bin/llm_up.py`; false → external
    port: int            # local port (local-only)
    endpoint: str        # full URL (remote-only)
    hf-repo: str         # HuggingFace repo (local-only, llama-server --hf-repo)
    hf-file: str         # weight file within the repo (local-only)
    model: str           # model id (remote-only; what to send to the API)
    api_key_env: str     # ENV VAR NAME that holds the API key (never the value)
    ctx-size: int        # context window (local-only)
    embedding: bool      # treat as embedding model (local-only)
```

- llm-profile-schema-models: `models` is a `dict[role_name, ModelEntry]`.
  Roles are free-form strings — `smart`, `dumb`, `narrator`, `embedding`,
  etc. Code reads roles by name; the profile decides which physical
  endpoint backs each role.
- llm-profile-schema-local: `local: true` declares a server that
  `bin/llm_up.py` will spawn. Requires `port` plus a way to identify the
  weights (`hf-repo` + `hf-file` for HF auto-download).
- llm-profile-schema-remote: `local: false` declares a pre-existing
  endpoint. Requires `endpoint`; may carry `model`, `api_key_env`.
- llm-profile-schema-api-key-by-env: API keys are NEVER stored in the
  YAML. The profile names the env var (`api_key_env: ANTHROPIC_API_KEY`);
  the value lives in `.env` (gitignored) or the shell. Sidestage loads
  `.env` via `python-dotenv` at startup so the var is in `os.environ`.

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
    local: bool = False
    port: int | None = None
    endpoint: str | None = None
    hf_repo: str | None = None
    hf_file: str | None = None
    model: str | None = None
    api_key_env: str | None = None
    ctx_size: int | None = None
    embedding: bool = False

class LlmProfile(BaseModel):
    models: dict[str, ModelEntry]

def load_profiles(sidestage_dir: Path) -> dict[str, LlmProfile]:
    """Scan <sidestage_dir>/llm_profiles/*.yaml; return dict by stem."""
```

- llm-profile-loader-aliases: YAML uses hyphens (`hf-repo`, `ctx-size`)
  while Python uses underscores (`hf_repo`, `ctx_size`). Pydantic
  field aliases bridge the two so users don't have to mix conventions.
- llm-profile-loader-validation: Malformed YAML raises at load time —
  better to fail fast than at first LLM call.
- .implemented-by: load_profiles, ModelEntry, LlmProfile

## llm-profile-lifecycle

The justfile's `_llm-up` recipe drives `bin/llm_up.py`, which:

1. llm-up-load: Loads the named profile from `<sidestage_dir>/llm_profiles/`.
2. llm-up-skip-remote: Ignores any `local: false` entry.
3. llm-up-check-up: For each `local: true` entry, polls
   `http://127.0.0.1:<port>/health`; if 2xx, the server is already up
   and this iteration is a no-op.
4. llm-up-spawn: Otherwise spawns `llama-server` with CLI flags built
   from the entry (`--port`, `--host 127.0.0.1`, `--hf-repo`,
   `--hf-file`, `--ctx-size`, `--embedding` as applicable). Detached;
   stdout/stderr to `<sidestage_dir>/logs/llm-<role>.log`.
   - llm-up-spawn-cache: Weights cache is intentionally global —
     llama.cpp's default (`~/.cache/llama.cpp/` or `$LLAMA_CACHE` if
     set). Multi-GB downloads are shared across instances on the same
     machine; we never copy weights into `<sidestage_dir>`.
   - llm-up-spawn-cwd: Process CWD is inherited from the caller (the
     just recipe → repo root). Because cache + HF auto-download are
     CWD-independent, this doesn't matter today. Profiles MUST NOT
     use relative file paths for model refs — use `hf-repo` /
     `hf-file` (or an absolute path if you must) so resolution stays
     deterministic.
5. llm-up-wait: Polls `/health` until 2xx or a timeout (~120 s — first
   run may need to download weights).
6. llm-up-tear-down: Out of scope here. `just stop` kills all
   `llama-server` processes via `pkill`.

- .implemented-by: bin/llm_up.py
- .tested-by: test_llm_profile_loader_*  (lifecycle itself is exercised
  in dev via `just run`; not unit-tested because it shells out)

## llm-profile-runtime

Phase 6b. `NpcActor` (and any other LLM-using actor) reads the active
profile via `InstanceConfig.llm_profile` + `load_profiles`, picks the
endpoint per role, makes the HTTP call (via litellm or similar).
Out of scope for Phase 6a — only the loader, profiles, and lifecycle
plumbing land here.
