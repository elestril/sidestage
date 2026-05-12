"""llm-profile: typed loader for `<sidestage_dir>/llm_profiles/*.yaml`.

Per `specs/llm-profiles.md`. Each YAML file in the directory IS a
profile; the filename stem is the profile name. The loader returns a
`dict[str, LlmProfile]` keyed by stem.

Sidestage does NOT spawn LLM servers — the endpoint declared in each
entry must already be reachable. Bring your own llama-server / vllm /
ollama / hosted API.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict


class ModelEntry(BaseModel):
    """llm-profile-schema: one role within a profile's `models` map.

    `endpoint` is the base URL of an OpenAI-compatible (or
    litellm-supported) HTTP endpoint. `model` is the litellm model
    string, provider prefix included (`openai/local`,
    `anthropic/claude-sonnet-4-5`). `api_key_env` names the env var
    holding the API key for hosted providers; loopback endpoints
    typically omit it and a stub is sent.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    endpoint: str
    """llm-profile-schema-endpoint: base URL of the LLM HTTP endpoint.
    Required. Passed to litellm as `api_base`."""

    model: str
    """llm-profile-schema-model: litellm model string with provider
    prefix (e.g. `openai/local`, `anthropic/claude-sonnet-4-5`)."""

    api_key_env: str | None = None
    """llm-profile-schema-api-key-by-env: NAME of the env var holding
    the API key. The value itself MUST NOT appear in the profile YAML.
    If unset, NpcActor sends a stub key — fine for endpoints that
    ignore it (most local servers)."""


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
