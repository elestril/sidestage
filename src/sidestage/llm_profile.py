"""llm-profile: typed loader for `<sidestage_dir>/llm_profiles/*.yaml`.

Per `specs/llm-profiles.md`. Each YAML file in the directory IS a
profile; the filename stem is the profile name. The loader returns a
`dict[str, LlmProfile]` keyed by stem.

Pydantic field aliases let YAML keep its natural hyphenated form
(`hf-repo`, `ctx-size`) while Python uses underscores.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field

# Loopback hosts that signal "we manage this server" (per
# `llm-profile-schema-managed-loopback`).
_LOOPBACK_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "localhost", "::1"})


class ModelEntry(BaseModel):
    """llm-profile-schema: one role within a profile's `models` map.

    The single required field is `endpoint`. A loopback host
    (`127.0.0.1`, `localhost`, `::1`) signals that we spawn and manage
    a `llama-server` ourselves — `bin/llm_up.py` checks `managed`
    (derived) and acts. Any other host means the endpoint is external
    and we just consume it.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    endpoint: str
    """llm-profile-schema-endpoint: Base URL. Required. Host
    determines whether the entry is managed (`llm-profile-schema-managed`)."""

    hf_repo: str | None = Field(default=None, alias="hf-repo")
    """HuggingFace repo for llama-server's `--hf-repo` auto-download.
    Required for managed entries that use HF auto-download."""

    hf_file: str | None = Field(default=None, alias="hf-file")
    """Weight file within the HF repo (`--hf-file`)."""

    model: str | None = None
    """Remote model id (the value sent to a hosted API). Ignored for
    managed entries."""

    api_key_env: str | None = None
    """llm-profile-schema-api-key-by-env: NAME of the env var holding
    the API key. The value itself MUST NOT appear in the profile YAML.
    """

    ctx_size: int | None = Field(default=None, alias="ctx-size")
    """Context window size for managed servers (`--ctx-size`)."""

    embedding: bool = False
    """Managed entry is an embedding model (`--embedding`)."""

    @property
    def managed(self) -> bool:
        """llm-profile-schema-managed: True iff `endpoint`'s host is a
        loopback address. Derived — never stored on the wire."""
        host = urlparse(self.endpoint).hostname
        return host in _LOOPBACK_HOSTS

    @property
    def port(self) -> int | None:
        """Bind port for managed entries (parsed out of `endpoint`)."""
        return urlparse(self.endpoint).port


class LlmProfile(BaseModel):
    """llm-profile-schema: a complete named topology — every role this
    profile defines, mapped to a `ModelEntry`.
    """

    model_config = ConfigDict(extra="forbid")

    models: dict[str, ModelEntry]


def load_profiles(sidestage_dir: str | Path) -> dict[str, LlmProfile]:
    """llm-profile-loader: scan `<sidestage_dir>/llm_profiles/*.yaml`.

    Returns a dict keyed by filename stem. Missing directory → empty
    dict (no LLM topology defined for this instance). Malformed YAML
    raises immediately (fail fast — see llm-profile-loader-validation).
    """
    profiles_dir = Path(sidestage_dir) / "llm_profiles"
    if not profiles_dir.is_dir():
        return {}
    out: dict[str, LlmProfile] = {}
    for path in sorted(profiles_dir.glob("*.yaml")):
        with path.open() as f:
            data = yaml.safe_load(f) or {}
        out[path.stem] = LlmProfile.model_validate(data)
    return out
