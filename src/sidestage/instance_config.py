"""instance-config: typed config for a sidestage instance.

Per `specs/instance-config.md`. Resolution precedence:
CLI overrides > env vars (`SIDESTAGE_*`) > `<sidestage_dir>/sidestage.yaml` > defaults.

The YAML path depends on `sidestage_dir`, which is itself a config field —
so YAML cannot redefine `sidestage_dir`. CLI/env can.

A resolved InstanceConfig serializes cleanly to a single env var
(`SIDESTAGE_INSTANCE_CONFIG`, JSON) for the uvicorn reload handoff:
parent process resolves once, worker subprocess parses it back.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


_ENV_RESOLVED_CONFIG = "SIDESTAGE_INSTANCE_CONFIG"


class InstanceConfig(BaseSettings):
    """instance-config: typed instance state.

    Fields here are exactly the knobs the server takes. Add fields as
    they earn their place — `spec-current` applies.

    .implements: server-run-sidestage-dir, server-run-port, server-run-reload
    """

    model_config = SettingsConfigDict(
        env_prefix="SIDESTAGE_",
        case_sensitive=False,
        extra="ignore",
    )

    sidestage_dir: str = "sidestage/"
    """instance-config-sidestage-dir: Instance state root. Default `sidestage/`.
    CLI / env only — YAML cannot redefine itself."""

    port: int = 8000
    """instance-config-port: Listen port. Default 8000."""

    reload: bool = False
    """instance-config-reload: When true, server runs under uvicorn's
    `--reload` (factory + reload_dirs). Dev workflow only."""


def _load_yaml(sidestage_dir: str) -> dict[str, Any]:
    """instance-config-yaml-load: Read `<sidestage_dir>/sidestage.yaml` if
    present; return an empty dict if absent. Unknown keys are kept (the
    file may carry forward-looking settings that other modules read);
    InstanceConfig itself ignores extras via `extra="ignore"`.
    """
    yaml_path = Path(sidestage_dir) / "sidestage.yaml"
    if not yaml_path.exists():
        return {}
    with yaml_path.open() as f:
        data = yaml.safe_load(f)
    return data or {}


def resolve(**cli_overrides: Any) -> InstanceConfig:
    """instance-config-resolve: Merge sources by precedence.

    1. CLI overrides (kwargs to this function) — highest.
    2. Env vars (`SIDESTAGE_*`).
    3. YAML at `<sidestage_dir>/sidestage.yaml`.
    4. Pydantic defaults — lowest.

    `sidestage_dir` is resolved from the top three sources only (not
    YAML, since YAML lives inside it).
    """
    # Strip None overrides — argparse passes None for unset flags.
    cli = {k: v for k, v in cli_overrides.items() if v is not None}

    # 1. Pick `sidestage_dir` from CLI > env > default to know where YAML lives.
    sd = (
        cli.get("sidestage_dir")
        or os.environ.get("SIDESTAGE_SIDESTAGE_DIR")
        or InstanceConfig.model_fields["sidestage_dir"].default
    )

    # 2. Load YAML (lowest precedence among non-default sources).
    yaml_data = _load_yaml(sd)
    # Only keep keys the model knows; preserves forward-compat without
    # poisoning unrelated fields.
    yaml_filtered = {
        k: v for k, v in yaml_data.items() if k in InstanceConfig.model_fields
    }

    # 3. BaseSettings(**kwargs) layers: kwargs > env > defaults.
    # We want CLI > env > YAML > defaults — so we pass CLI as kwargs (top),
    # and YAML as a fallback under env. pydantic-settings's per-source
    # precedence helper is overkill here; instead resolve in two passes:
    # first instantiate with no overrides (gives env > defaults), then
    # for each field NOT set by env, fall back to YAML, then apply CLI.
    env_only = InstanceConfig()  # env > defaults
    env_set_fields = env_only.model_fields_set

    merged: dict[str, Any] = {}
    for name in InstanceConfig.model_fields:
        if name in cli:
            merged[name] = cli[name]
        elif name in env_set_fields:
            merged[name] = getattr(env_only, name)
        elif name in yaml_filtered:
            merged[name] = yaml_filtered[name]
        else:
            merged[name] = getattr(env_only, name)  # the default

    return InstanceConfig.model_validate(merged)


def from_env() -> InstanceConfig:
    """instance-config-from-env: Reconstruct InstanceConfig from the
    `SIDESTAGE_INSTANCE_CONFIG` env var (JSON blob). Used by the
    uvicorn-reload factory worker.

    Raises `RuntimeError` if the env var is missing — that means the
    factory was invoked without the parent process having serialized
    the config, which is a setup error, not a fallback case.
    """
    raw = os.environ.get(_ENV_RESOLVED_CONFIG)
    if raw is None:
        raise RuntimeError(
            f"{_ENV_RESOLVED_CONFIG} not set — the uvicorn factory was "
            "invoked without the parent process having serialized the "
            "resolved InstanceConfig. Invoke `sidestage` via main()."
        )
    return InstanceConfig.model_validate_json(raw)


def serialize_to_env(config: InstanceConfig) -> None:
    """instance-config-serialize-to-env: Write the resolved config to
    `SIDESTAGE_INSTANCE_CONFIG`. Called by `main()` before invoking
    uvicorn with `factory=True, reload=True`.
    """
    os.environ[_ENV_RESOLVED_CONFIG] = config.model_dump_json()
