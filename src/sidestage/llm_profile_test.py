"""Unit tests for `llm-profile-loader` and the `ModelEntry` / `LlmProfile`
schema. Covers discovery, validation, and the minimal field set.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from sidestage.llm_profile import LlmProfile, ModelEntry, load_profiles


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


class TestModelEntry:
    def test_minimal_local_entry(self) -> None:
        # llm-profile-schema: endpoint + model are required; api_key_env optional.
        m = ModelEntry.model_validate(
            {"endpoint": "http://127.0.0.1:8080", "model": "openai/local"}
        )
        assert m.endpoint == "http://127.0.0.1:8080"
        assert m.model == "openai/local"
        assert m.api_key_env is None

    def test_external_entry_with_api_key_env(self) -> None:
        m = ModelEntry.model_validate(
            {
                "endpoint": "https://api.anthropic.com/v1",
                "model": "anthropic/claude-sonnet-4-5",
                "api_key_env": "ANTHROPIC_API_KEY",
            }
        )
        assert m.api_key_env == "ANTHROPIC_API_KEY", (
            "llm-profile-schema-api-key-by-env: api_key_env MUST round-trip; "
            f"got api_key_env={m.api_key_env!r}"
        )

    def test_endpoint_required(self) -> None:
        with pytest.raises(ValidationError):
            ModelEntry.model_validate({"model": "openai/local"})

    def test_model_required(self) -> None:
        # llm-profile-schema-model: every entry MUST declare its litellm model string.
        with pytest.raises(ValidationError):
            ModelEntry.model_validate({"endpoint": "http://127.0.0.1:8080"})

    def test_unknown_field_is_rejected(self) -> None:
        # extra='forbid': typos surface immediately rather than being silently dropped.
        with pytest.raises(ValidationError):
            ModelEntry.model_validate(
                {
                    "endpoint": "http://127.0.0.1:8080",
                    "model": "openai/local",
                    "hf-repo": "x/y",
                }
            )


class TestLlmProfile:
    def test_models_required(self) -> None:
        with pytest.raises(ValidationError):
            LlmProfile.model_validate({})

    def test_models_map_keyed_by_role(self) -> None:
        # llm-profile-schema-models: models is a dict[role, ModelEntry].
        p = LlmProfile.model_validate(
            {
                "models": {
                    "default": {
                        "endpoint": "http://127.0.0.1:8080",
                        "model": "openai/local",
                    },
                    "embedding": {
                        "endpoint": "http://127.0.0.1:8081",
                        "model": "openai/local-embed",
                    },
                }
            }
        )
        assert set(p.models.keys()) == {"default", "embedding"}, (
            "llm-profile-schema-models: roles MUST be exposed as the keys "
            f"of `models`; got {set(p.models.keys())!r}"
        )


class TestLoadProfiles:
    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        # llm-profile-discovery-missing-dir: absent dir is a no-op, not an error.
        result = load_profiles(tmp_path)
        assert result == {}, (
            "llm-profile-discovery-missing-dir: missing llm_profiles/ MUST "
            f"return an empty dict; got {result!r}"
        )

    def test_scans_all_yaml(self, tmp_path: Path) -> None:
        # llm-profile-discovery-dir + llm-profile-discovery-stem: each
        # *.yaml becomes a profile keyed by filename stem.
        _write(
            tmp_path / "llm_profiles" / "localhost.yaml",
            "models:\n"
            "  default:\n"
            "    endpoint: http://127.0.0.1:8080\n"
            "    model: openai/local\n",
        )
        _write(
            tmp_path / "llm_profiles" / "anthropic.yaml",
            "models:\n"
            "  default:\n"
            "    endpoint: https://api.anthropic.com/v1\n"
            "    model: anthropic/claude-sonnet-4-5\n"
            "    api_key_env: ANTHROPIC_API_KEY\n",
        )
        result = load_profiles(tmp_path)
        assert set(result.keys()) == {"localhost", "anthropic"}, (
            "llm-profile-discovery-stem: profile name MUST be the YAML "
            f"filename stem; got {set(result.keys())!r}"
        )
        assert result["localhost"].models["default"].model == "openai/local"
        assert (
            result["anthropic"].models["default"].model == "anthropic/claude-sonnet-4-5"
        )

    def test_ignores_non_yaml(self, tmp_path: Path) -> None:
        # Stray non-YAML files in the dir don't trip the loader.
        _write(
            tmp_path / "llm_profiles" / "localhost.yaml",
            "models:\n"
            "  default:\n"
            "    endpoint: http://127.0.0.1:8080\n"
            "    model: openai/local\n",
        )
        _write(tmp_path / "llm_profiles" / "README.md", "notes")
        _write(tmp_path / "llm_profiles" / ".keep", "")
        result = load_profiles(tmp_path)
        assert set(result.keys()) == {"localhost"}

    def test_empty_yaml_is_invalid(self, tmp_path: Path) -> None:
        # Empty file → empty dict → no `models` field → validation error.
        _write(tmp_path / "llm_profiles" / "empty.yaml", "")
        with pytest.raises(ValidationError):
            load_profiles(tmp_path)

    def test_malformed_raises(self, tmp_path: Path) -> None:
        # llm-profile-loader-validation: bad YAML fails at load time, not first use.
        _write(tmp_path / "llm_profiles" / "broken.yaml", "models: [this is wrong]\n")
        with pytest.raises(ValidationError):
            load_profiles(tmp_path)

    def test_sidestage_dir_as_str(self, tmp_path: Path) -> None:
        # The signature accepts `str | Path`; both must work.
        _write(
            tmp_path / "llm_profiles" / "localhost.yaml",
            "models:\n"
            "  default:\n"
            "    endpoint: http://127.0.0.1:8080\n"
            "    model: openai/local\n",
        )
        result = load_profiles(str(tmp_path))
        assert "localhost" in result
