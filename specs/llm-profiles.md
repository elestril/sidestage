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
    endpoint: str        # full URL (REQUIRED) — e.g. http://127.0.0.1:8080
    hf-repo: str         # HuggingFace repo (managed-only, llama-server --hf-repo)
    hf-file: str         # weight file within the repo (managed-only)
    model: str           # model id (external-only; sent in the API request)
    api_key_env: str     # ENV VAR NAME that holds the API key (never the value)
    ctx-size: int        # context window (managed-only)
    embedding: bool      # treat as embedding model (managed-only)
```

- llm-profile-schema-models: `models` is a `dict[role_name, ModelEntry]`.
  Roles are free-form strings — `smart`, `dumb`, `narrator`, `embedding`,
  etc. Code reads roles by name; the profile decides which physical
  endpoint backs each role.
- llm-profile-schema-endpoint: `endpoint` is the single source of truth
  for where to reach the model. There is no separate `port` or `host`
  field — both are extracted from the URL.
- llm-profile-schema-managed: Whether `bin/llm_up.py` will spawn the
  server is DERIVED from `endpoint`, not declared. If the URL host is
  loopback (`127.0.0.1`, `localhost`, `::1`), `entry.managed` is True
  and the lifecycle treats it as a server we own. Anything else is
  external and we just consume it. This keeps the schema minimal and
  prevents drift between two fields that have to agree.
- llm-profile-schema-managed-fields: Managed entries need weight refs
  (`hf-repo` + `hf-file` for HF auto-download). External entries need
  whatever the remote API expects (`model`, `api_key_env`).
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
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

class ModelEntry(BaseModel):
    endpoint: str
    hf_repo: str | None = None  # alias hf-repo
    hf_file: str | None = None  # alias hf-file
    model: str | None = None
    api_key_env: str | None = None
    ctx_size: int | None = None  # alias ctx-size
    embedding: bool = False

    @property
    def managed(self) -> bool:
        return urlparse(self.endpoint).hostname in _LOOPBACK_HOSTS

    @property
    def port(self) -> int | None:
        return urlparse(self.endpoint).port

class LlmProfile(BaseModel):
    models: dict[str, ModelEntry]

def load_profiles(sidestage_dir: Path) -> dict[str, LlmProfile]:
    """Scan <sidestage_dir>/llm_profiles/*.yaml; return dict by stem."""
```

- llm-profile-loader-aliases: YAML uses hyphens (`hf-repo`, `ctx-size`)
  while Python uses underscores (`hf_repo`, `ctx_size`). Pydantic
  field aliases bridge the two so users don't have to mix conventions.
- llm-profile-loader-derived: `managed` and `port` are computed from
  `endpoint` — never stored. Callers ask `entry.managed` to branch on
  spawn-vs-consume, and `entry.port` for the loopback port.
- llm-profile-loader-validation: Malformed YAML raises at load time —
  better to fail fast than at first LLM call. Unknown fields raise too
  (`extra="forbid"`) so typos in the YAML surface immediately.
- .implemented-by: load_profiles, ModelEntry, LlmProfile

## llm-profile-lifecycle

The `just run` recipe inlines lifecycle: it calls `bin/llm_up.py
<sidestage_dir> <profile>` to bring servers up, then runs sidestage in
the foreground. `llm_up.py`:

1. llm-up-load: Loads the named profile from `<sidestage_dir>/llm_profiles/`.
2. llm-up-skip-external: Ignores any entry where `entry.managed` is
   False (non-loopback host) — we just consume those.
3. llm-up-check-up: For each managed entry, polls
   `http://127.0.0.1:<port>/health`; if 2xx, the server is already up
   and this iteration is a no-op.
4. llm-up-spawn: Otherwise execs `bin/run-llama-server.sh` with CLI
   flags built from the entry (`--port`, `--hf-repo`, `--hf-file`,
   `--ctx-size`, `--embedding` as applicable). The wrapper applies
   machine-wide defaults (`--host 127.0.0.1`, GPU/thread tuning) so
   contributors edit one shell file rather than burying flags in
   Python. Detached via `start_new_session=True`; stdout/stderr to
   `<sidestage_dir>/logs/llm-<role>.log`.
   - llm-up-spawn-started-pid: Prints `STARTED-PID:<pid>` on its own
     stdout line so the wrapping shell (the `run` recipe) can record
     ownership and clean up on exit. No `STARTED-PID` line is printed
     for entries that were already healthy — ownership flows from
     spawn, not consumption.
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
5. llm-up-wait: Polls `/health` until 2xx or a timeout (~180 s — first
   run may need to download weights).
6. llm-up-tear-down: Out of scope here. The `run` recipe's bash trap
   kills only the PIDs reported via `STARTED-PID:`. `just stop` is the
   blunt hammer that kills all `llama-server` processes via `pkill`,
   intended for orphans from prior sessions.

- .implemented-by: bin/llm_up.py, bin/run-llama-server.sh, justfile (run)
- .tested-by: test_llm_profile_loader_*  (lifecycle itself is exercised
  in dev via `just run`; not unit-tested because it shells out)

## llm-profile-runtime

Phase 6b. `NpcActor` (and any other LLM-using actor) reads the active
profile via `InstanceConfig.llm_profile` + `load_profiles`, picks the
endpoint per role, makes the HTTP call (via litellm or similar).
Out of scope for Phase 6a — only the loader, profiles, and lifecycle
plumbing land here.
