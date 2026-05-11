"""Unit tests for instance-config precedence and env round-trip."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from sidestage.instance_config import (
    InstanceConfig,
    from_env,
    resolve,
    serialize_to_env,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch) -> Iterator[None]:
    # Strip any inherited SIDESTAGE_* so the test universe is hermetic.
    for k in list(os.environ.keys()):
        if k.startswith("SIDESTAGE_"):
            monkeypatch.delenv(k, raising=False)
    yield


def _make_yaml(tmp_path: Path, body: str) -> str:
    yaml_path = tmp_path / "sidestage.yaml"
    yaml_path.write_text(body)
    return str(tmp_path) + "/"


class TestInstanceConfigDefaults:
    def test_defaults(self) -> None:
        # instance-config-*: defaults apply when no other source sets a field.
        c = InstanceConfig()
        assert c.sidestage_dir == "sidestage/", (
            "instance-config-sidestage-dir: default sidestage_dir MUST be "
            f"'sidestage/'; got {c.sidestage_dir!r}"
        )
        assert c.port == 8000, (
            f"instance-config-port: default port MUST be 8000; got {c.port}"
        )
        assert c.reload is False, (
            f"instance-config-reload: default reload MUST be False; got {c.reload!r}"
        )
        assert c.llm_profile == "localhost", (
            "instance-config-llm-profile: default llm_profile MUST be "
            f"'localhost'; got {c.llm_profile!r}"
        )


class TestInstanceConfigPrecedence:
    def test_cli_beats_env_beats_yaml_beats_default(
        self, tmp_path, monkeypatch
    ) -> None:
        # instance-config-resolve: CLI > env > YAML > defaults.
        sd = _make_yaml(tmp_path, "port: 7777\nreload: true\n")
        monkeypatch.setenv("SIDESTAGE_PORT", "8888")
        c = resolve(sidestage_dir=sd, port=9999)
        assert c.port == 9999, (
            "instance-config-resolve: CLI override MUST win over env+yaml; "
            f"got port={c.port}"
        )

    def test_env_beats_yaml(self, tmp_path, monkeypatch) -> None:
        sd = _make_yaml(tmp_path, "port: 7777\n")
        monkeypatch.setenv("SIDESTAGE_PORT", "8888")
        c = resolve(sidestage_dir=sd)
        assert c.port == 8888, (
            f"instance-config-resolve: env MUST win over YAML; got port={c.port}"
        )

    def test_yaml_beats_default(self, tmp_path) -> None:
        sd = _make_yaml(tmp_path, "port: 7777\n")
        c = resolve(sidestage_dir=sd)
        assert c.port == 7777, (
            f"instance-config-resolve: YAML MUST win over defaults; got port={c.port}"
        )

    def test_default_when_no_source_sets(self) -> None:
        c = resolve()
        assert c.port == 8000

    def test_missing_yaml_falls_back(self, tmp_path) -> None:
        # instance-config-yaml-load: absent YAML is a no-op, not an error.
        c = resolve(sidestage_dir=str(tmp_path) + "/")  # tmp_path has no yaml
        assert c.port == 8000, (
            "instance-config-yaml-load: missing sidestage.yaml MUST fall "
            f"through to defaults; got port={c.port}"
        )

    def test_yaml_extras_are_ignored(self, tmp_path) -> None:
        # instance-config-yaml-load: unknown YAML keys must not break load
        # (forward-compat for fields other modules read).
        sd = _make_yaml(tmp_path, "port: 9000\ndefault_model: claude-x\n")
        c = resolve(sidestage_dir=sd)
        assert c.port == 9000

    def test_cli_none_is_treated_as_unset(self, tmp_path, monkeypatch) -> None:
        # argparse passes None for unset flags. resolve() must treat None as
        # "not provided" so env/YAML/defaults can win.
        monkeypatch.setenv("SIDESTAGE_PORT", "8888")
        c = resolve(port=None, reload=None)
        assert c.port == 8888, (
            f"instance-config-resolve: CLI=None MUST yield to env; got port={c.port}"
        )


class TestInstanceConfigEnvRoundTrip:
    def test_serialize_then_from_env(self, monkeypatch) -> None:
        # instance-config-{serialize-to-env,from-env}: round-trip via env.
        src = InstanceConfig(sidestage_dir="x/", port=12345, reload=True)
        serialize_to_env(src)
        out = from_env()
        assert out.model_dump() == src.model_dump(), (
            "instance-config-from-env: round-trip via env MUST preserve "
            f"all fields; got {out.model_dump()!r} vs {src.model_dump()!r}"
        )

    def test_from_env_missing_is_fatal(self, monkeypatch) -> None:
        # instance-config-from-env: missing env var is a setup error.
        monkeypatch.delenv("SIDESTAGE_INSTANCE_CONFIG", raising=False)
        with pytest.raises(RuntimeError, match="SIDESTAGE_INSTANCE_CONFIG"):
            from_env()
