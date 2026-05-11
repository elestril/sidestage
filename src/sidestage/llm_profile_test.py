"""Unit tests for `llm-profile-loader` and the `ModelEntry` / `LlmProfile`
schema. Covers discovery, validation, alias mapping, and derivation of
`managed` / `port` from `endpoint`.
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
    def test_managed_loopback_127(self) -> None:
        # llm-profile-schema-managed: 127.0.0.1 is loopback → managed.
        m = ModelEntry.model_validate({"endpoint": "http://127.0.0.1:8080"})
        assert m.managed is True, (
            "llm-profile-schema-managed: loopback host MUST signal managed; "
            f"got managed={m.managed!r}"
        )
        assert m.port == 8080

    def test_managed_loopback_localhost(self) -> None:
        # llm-profile-schema-managed: localhost is also loopback.
        m = ModelEntry.model_validate({"endpoint": "http://localhost:8081"})
        assert m.managed is True
        assert m.port == 8081

    def test_managed_loopback_ipv6(self) -> None:
        m = ModelEntry.model_validate({"endpoint": "http://[::1]:8082"})
        assert m.managed is True
        assert m.port == 8082

    def test_external_endpoint(self) -> None:
        m = ModelEntry.model_validate(
            {
                "endpoint": "https://api.anthropic.com/v1",
                "model": "claude-sonnet-4-5",
                "api_key_env": "ANTHROPIC_API_KEY",
            }
        )
        assert m.managed is False, (
            "llm-profile-schema-managed: non-loopback host MUST be external; "
            f"got managed={m.managed!r}"
        )
        assert m.api_key_env == "ANTHROPIC_API_KEY"

    def test_external_lan_endpoint(self) -> None:
        # A LAN host is NOT loopback — we don't manage it even though it's
        # "local" in casual usage. That's why we picked `managed` over `local`.
        m = ModelEntry.model_validate({"endpoint": "http://beefy.lan:8080"})
        assert m.managed is False

    def test_endpoint_required(self) -> None:
        with pytest.raises(ValidationError):
            ModelEntry.model_validate({})

    def test_hyphen_aliases_round_trip(self) -> None:
        # llm-profile-loader-aliases: YAML keys use hyphens; the loader
        # MUST accept the hyphenated form and surface underscores in Python.
        m = ModelEntry.model_validate(
            {
                "endpoint": "http://127.0.0.1:8080",
                "hf-repo": "x/y",
                "hf-file": "z.gguf",
                "ctx-size": 4096,
            }
        )
        assert m.hf_repo == "x/y", (
            "llm-profile-loader-aliases: hf-repo MUST map to hf_repo; "
            f"got hf_repo={m.hf_repo!r}"
        )
        assert m.hf_file == "z.gguf"
        assert m.ctx_size == 4096

    def test_unknown_field_is_rejected(self) -> None:
        # extra='forbid': typos surface immediately rather than being silently dropped.
        with pytest.raises(ValidationError):
            ModelEntry.model_validate(
                {"endpoint": "http://127.0.0.1:8080", "hf-rrepo": "oops"}
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
                    "smart": {"endpoint": "http://127.0.0.1:8080"},
                    "embedding": {
                        "endpoint": "http://127.0.0.1:8081",
                        "embedding": True,
                    },
                }
            }
        )
        assert set(p.models.keys()) == {"smart", "embedding"}, (
            "llm-profile-schema-models: roles MUST be exposed as the keys "
            f"of `models`; got {set(p.models.keys())!r}"
        )
        assert p.models["smart"].port == 8080
        assert p.models["embedding"].embedding is True


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
            "models:\n  smart:\n    endpoint: http://127.0.0.1:8080\n",
        )
        _write(
            tmp_path / "llm_profiles" / "anthropic.yaml",
            "models:\n"
            "  smart:\n"
            "    endpoint: https://api.anthropic.com/v1\n"
            "    model: claude-sonnet-4-5\n",
        )
        result = load_profiles(tmp_path)
        assert set(result.keys()) == {"localhost", "anthropic"}, (
            "llm-profile-discovery-stem: profile name MUST be the YAML "
            f"filename stem; got {set(result.keys())!r}"
        )
        assert result["localhost"].models["smart"].managed is True
        assert result["anthropic"].models["smart"].managed is False

    def test_ignores_non_yaml(self, tmp_path: Path) -> None:
        # Stray non-YAML files in the dir don't trip the loader.
        _write(
            tmp_path / "llm_profiles" / "localhost.yaml",
            "models:\n  smart:\n    endpoint: http://127.0.0.1:8080\n",
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
            "models:\n  smart:\n    endpoint: http://127.0.0.1:8080\n",
        )
        result = load_profiles(str(tmp_path))
        assert "localhost" in result
