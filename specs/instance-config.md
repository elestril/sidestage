# instance-config: typed sidestage instance config

A Sidestage instance carries a small set of runtime knobs: where its
state lives, which port to serve, whether to run with hot-reload. These
live in a typed Pydantic `BaseSettings` model so the resolution
precedence is uniform across CLI, env, on-disk YAML, and defaults.

## instance-config: InstanceConfig

```python
class InstanceConfig(BaseSettings):
    sidestage_dir: str = "sidestage/"
    port: int = 8000
    reload: bool = False
```

- instance-config-sidestage-dir: Instance state root. Resolves from CLI
  or env only — YAML can't redefine itself (the YAML lives inside this
  directory).
- instance-config-port: Listen port; default 8000. Browser e2e passes an
  ephemeral port (per `testing-fixture-test-server`).
- instance-config-reload: Dev hot-reload toggle. When true, `main()`
  dispatches to uvicorn's reload mechanism via the `create_app` factory
  (per `server-run-reload`).
- .implemented-by: InstanceConfig

## instance-config-resolve: Resolution precedence

CLI overrides (highest) > env vars (`SIDESTAGE_*`) > `<sidestage_dir>/sidestage.yaml` > Pydantic defaults (lowest).

- instance-config-resolve-cli: argparse-parsed flags. `None` (the
  argparse default for an unset flag) is treated as "not provided" so
  lower-precedence sources still win.
- instance-config-resolve-env: pydantic-settings auto-reads
  `SIDESTAGE_<FIELD>` env vars (case-insensitive). Beats YAML and
  defaults.
- instance-config-resolve-yaml: `<sidestage_dir>/sidestage.yaml` is
  optional. If absent, no error — defaults apply. Unknown keys are
  ignored (forward-compat: the YAML may carry settings other modules
  read).
- instance-config-resolve-defaults: Field defaults on `InstanceConfig`
  itself; lowest precedence.
- .implemented-by: instance_config.resolve

## instance-config-env-roundtrip: parent → reload-worker handoff

uvicorn's `--reload` spawns a worker subprocess that imports the module
fresh on every file change. The factory is zero-arg by contract, so
config crosses the process boundary via a single env var.

- instance-config-serialize-to-env: `main()` writes the resolved
  `InstanceConfig` to `SIDESTAGE_INSTANCE_CONFIG` as JSON before
  invoking uvicorn. Atomic — the worker sees exactly what the parent
  resolved.
- instance-config-from-env: `create_app` reads
  `SIDESTAGE_INSTANCE_CONFIG`, parses with `model_validate_json`, and
  uses the result. Missing env var is a hard error (the factory was
  invoked outside the supported pathway).
- .implemented-by: instance_config.serialize_to_env, instance_config.from_env
- .tested-by: test_serialize_then_from_env, test_from_env_missing_is_fatal
