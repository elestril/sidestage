"""Unit tests for `src/sidestage/runner.py`.

Each labeled invariant in `specs/runner.md` has at least one test below.
All subprocess and network calls are mocked — no real shell-out, no real
HTTP, no real port binding.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from sidestage import runner as runner_mod
from sidestage.runner import (
    DependencyConfig,
    DependencyError,
    InstanceConfig,
    Runner,
    _http_get,
    _is_2xx,
    _port_from_url,
    main,
)


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


def _dep(**overrides) -> DependencyConfig:
    base = dict(
        name="vite",
        health_url="http://localhost:5173/__vite_ping",
        version_url=None,
        expected_version=None,
        start_cmd="npm run dev",
        start_cwd="frontend/",
    )
    base.update(overrides)
    return DependencyConfig(**base)


def _instance(**overrides) -> InstanceConfig:
    base = dict(
        name="dev",
        port=8000,
        config_dir="configs/",
        reload=True,
        dependencies=[],
    )
    base.update(overrides)
    return InstanceConfig(**base)


# ---------------------------------------------------------------------------
# instance-config / dependency-config (Pydantic models)
# ---------------------------------------------------------------------------


class TestInstanceConfig:
    def test_loads_from_dev_yaml(self) -> None:
        # Mirrors instances/dev.yaml
        raw = {
            "name": "dev",
            "port": 8000,
            "config_dir": "configs/",
            "reload": True,
            "dependencies": [
                {
                    "name": "vite",
                    "health_url": "http://localhost:5173/__vite_ping",
                    "start_cmd": "npm run dev",
                    "start_cwd": "frontend/",
                }
            ],
        }
        cfg = InstanceConfig.model_validate(raw)
        # instance-config-name
        assert cfg.name == "dev"
        # instance-config-port
        assert cfg.port == 8000
        # instance-config-config-dir
        assert cfg.config_dir == "configs/"
        # instance-config-reload
        assert cfg.reload is True
        # instance-config-deps
        assert len(cfg.dependencies) == 1
        assert cfg.dependencies[0].name == "vite"

    def test_dep_config_optional_version_fields(self) -> None:
        d = DependencyConfig(
            name="x",
            health_url="http://h",
            start_cmd="cmd",
            start_cwd="cwd",
        )
        assert d.version_url is None
        assert d.expected_version is None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class TestPortFromUrl:
    def test_explicit_port(self) -> None:
        assert _port_from_url("http://localhost:5173/__vite_ping") == 5173

    def test_http_default(self) -> None:
        assert _port_from_url("http://example.com/x") == 80

    def test_https_default(self) -> None:
        assert _port_from_url("https://example.com/x") == 443

    def test_unknown_scheme_raises(self) -> None:
        with pytest.raises(ValueError):
            _port_from_url("ftp://example.com/x")


class TestHttpGet:
    def test_returns_zero_on_connection_refused(self) -> None:
        with patch("urllib.request.urlopen", side_effect=ConnectionError()):
            status, body = _http_get("http://localhost:1/nope")
        assert status == 0
        assert body == b""

    def test_returns_status_and_body(self) -> None:
        fake = MagicMock()
        fake.getcode.return_value = 200
        fake.read.return_value = b"ok"
        fake.__enter__ = lambda self: fake
        fake.__exit__ = lambda *a: None
        with patch("urllib.request.urlopen", return_value=fake):
            status, body = _http_get("http://x")
        assert status == 200
        assert body == b"ok"


def test_is_2xx() -> None:
    assert _is_2xx(200)
    assert _is_2xx(204)
    assert _is_2xx(299)
    assert not _is_2xx(199)
    assert not _is_2xx(300)
    assert not _is_2xx(0)


# ---------------------------------------------------------------------------
# runner-dep-dataflow — health check / start / wait / cwd / version / restart
# ---------------------------------------------------------------------------


class TestCheckDeps:
    def test_health_check_skips_to_step4_when_up(self) -> None:
        """runner-dep-health-check: 2xx => skip start, jump to cwd/version."""
        runner = Runner(_instance(dependencies=[_dep()]))
        with (
            patch.object(runner_mod, "_http_get", return_value=(200, b"")),
            patch.object(runner, "start_dep") as start_mock,
            patch.object(runner, "_cwd_matches", return_value=True),
            patch.object(runner, "_version_matches", return_value=True),
        ):
            runner.check_deps()
        start_mock.assert_not_called()

    def test_start_dep_called_when_health_fails(self) -> None:
        """runner-dep-start: non-2xx => start_dep is invoked."""
        runner = Runner(_instance(dependencies=[_dep()]))
        with (
            patch.object(runner_mod, "_http_get", return_value=(0, b"")),
            patch.object(runner, "start_dep") as start_mock,
            patch.object(runner, "_cwd_matches", return_value=True),
            patch.object(runner, "_version_matches", return_value=True),
        ):
            runner.check_deps()
        start_mock.assert_called_once()

    def test_cwd_mismatch_raises_without_force(self) -> None:
        """runner-dep-cwd-check: cwd mismatch + no --force-backends => error."""
        runner = Runner(_instance(dependencies=[_dep()]))
        with (
            patch.object(runner_mod, "_http_get", return_value=(200, b"")),
            patch.object(runner, "_cwd_matches", return_value=False),
            patch.object(runner, "_version_matches", return_value=True),
        ):
            with pytest.raises(DependencyError, match="cwd mismatch"):
                runner.check_deps()

    def test_version_mismatch_raises_without_force(self) -> None:
        """runner-dep-version-mismatch: without --force-backends => error."""
        runner = Runner(_instance(dependencies=[_dep()]))
        with (
            patch.object(runner_mod, "_http_get", return_value=(200, b"")),
            patch.object(runner, "_cwd_matches", return_value=True),
            patch.object(runner, "_version_matches", return_value=False),
        ):
            with pytest.raises(DependencyError, match="version mismatch"):
                runner.check_deps()

    def test_version_ok_passes(self) -> None:
        """runner-dep-version-ok: matching version => no error."""
        runner = Runner(_instance(dependencies=[_dep()]))
        with (
            patch.object(runner_mod, "_http_get", return_value=(200, b"")),
            patch.object(runner, "_cwd_matches", return_value=True),
            patch.object(runner, "_version_matches", return_value=True),
        ):
            runner.check_deps()  # no raise

    def test_force_restart_on_version_mismatch(self) -> None:
        """runner-dep-force-restart: --force-backends triggers restart_dep."""
        runner = Runner(_instance(dependencies=[_dep()]), force_backends=True)
        match_calls = iter([False, True])  # 1st check fails, 2nd ok after restart

        def cwd_matches(*a, **kw):
            return next(match_calls)

        with (
            patch.object(runner_mod, "_http_get", return_value=(200, b"")),
            patch.object(runner, "_cwd_matches", side_effect=cwd_matches),
            patch.object(runner, "_version_matches", return_value=True),
            patch.object(runner, "restart_dep") as restart_mock,
        ):
            runner.check_deps()
        restart_mock.assert_called_once()

    def test_force_restart_still_fails_on_persistent_mismatch(self) -> None:
        """runner-dep-force-restart: post-restart mismatch hard-fails."""
        runner = Runner(_instance(dependencies=[_dep()]), force_backends=True)
        with (
            patch.object(runner_mod, "_http_get", return_value=(200, b"")),
            patch.object(runner, "_cwd_matches", return_value=False),
            patch.object(runner, "_version_matches", return_value=True),
            patch.object(runner, "restart_dep"),
        ):
            with pytest.raises(DependencyError):
                runner.check_deps()

    def test_iterates_in_order(self) -> None:
        """runner-check-deps: deps processed in declared order."""
        d1 = _dep(name="a", health_url="http://localhost:5173/")
        d2 = _dep(name="b", health_url="http://localhost:6000/")
        runner = Runner(_instance(dependencies=[d1, d2]))
        seen: list[str] = []

        def fake_http(url, timeout=2.0):
            seen.append(url)
            return (200, b"")

        with (
            patch.object(runner_mod, "_http_get", side_effect=fake_http),
            patch.object(runner, "_cwd_matches", return_value=True),
            patch.object(runner, "_version_matches", return_value=True),
        ):
            runner.check_deps()
        assert seen == [d1.health_url, d2.health_url]


# ---------------------------------------------------------------------------
# runner-start-dep
# ---------------------------------------------------------------------------


class TestStartDep:
    def test_spawns_subprocess_with_cwd(self) -> None:
        runner = Runner(_instance())
        dep = _dep()
        with (
            patch("subprocess.Popen") as popen,
            patch.object(runner_mod, "_http_get", return_value=(200, b"")),
        ):
            runner.start_dep(dep)
        popen.assert_called_once()
        kwargs = popen.call_args.kwargs
        assert kwargs.get("cwd") == "frontend/"
        assert kwargs.get("shell") is True
        assert popen.call_args.args[0] == "npm run dev"

    def test_polls_until_2xx(self) -> None:
        runner = Runner(_instance())
        dep = _dep()
        responses = iter([(0, b""), (0, b""), (200, b"")])
        with (
            patch("subprocess.Popen"),
            patch.object(runner_mod, "_http_get", side_effect=lambda *a, **k: next(responses)),
            patch("time.sleep"),
        ):
            runner.start_dep(dep)  # no raise => poll succeeded

    def test_timeout_raises(self) -> None:
        runner = Runner(_instance())
        dep = _dep()
        # monotonic returns 0, then a value past the deadline.
        with (
            patch("subprocess.Popen"),
            patch.object(runner_mod, "_http_get", return_value=(0, b"")),
            patch("time.sleep"),
            patch("time.monotonic", side_effect=[0.0, 0.0, 1000.0]),
        ):
            with pytest.raises(DependencyError, match="did not return 2xx"):
                runner.start_dep(dep)


# ---------------------------------------------------------------------------
# runner-restart-dep
# ---------------------------------------------------------------------------


class TestRestartDep:
    def test_calls_fuser_then_start(self) -> None:
        runner = Runner(_instance())
        dep = _dep()  # health_url => port 5173
        with (
            patch("subprocess.run") as run_mock,
            patch.object(runner, "start_dep") as start_mock,
        ):
            runner.restart_dep(dep)
        run_mock.assert_called_once()
        cmd = run_mock.call_args.args[0]
        assert cmd == ["fuser", "-k", "5173/tcp"]
        start_mock.assert_called_once_with(dep)


# ---------------------------------------------------------------------------
# _version_matches / _cwd_matches
# ---------------------------------------------------------------------------


class TestVersionMatches:
    def test_no_version_url_returns_true(self) -> None:
        runner = Runner(_instance())
        assert runner._version_matches(_dep()) is True

    def test_prefix_match(self) -> None:
        runner = Runner(_instance())
        dep = _dep(version_url="http://x/v", expected_version="6")
        with patch.object(
            runner_mod, "_http_get", return_value=(200, b'{"version": "6.3.1"}')
        ):
            assert runner._version_matches(dep) is True

    def test_prefix_mismatch(self) -> None:
        runner = Runner(_instance())
        dep = _dep(version_url="http://x/v", expected_version="6")
        with patch.object(
            runner_mod, "_http_get", return_value=(200, b'{"version": "5.0.0"}')
        ):
            assert runner._version_matches(dep) is False

    def test_non_2xx_is_mismatch(self) -> None:
        runner = Runner(_instance())
        dep = _dep(version_url="http://x/v", expected_version="6")
        with patch.object(runner_mod, "_http_get", return_value=(500, b"")):
            assert runner._version_matches(dep) is False

    def test_invalid_json_is_mismatch(self) -> None:
        runner = Runner(_instance())
        dep = _dep(version_url="http://x/v", expected_version="6")
        with patch.object(runner_mod, "_http_get", return_value=(200, b"not json")):
            assert runner._version_matches(dep) is False


class TestCwdMatches:
    def test_no_cwd_set_returns_true(self) -> None:
        runner = Runner(_instance())
        dep = _dep(start_cwd="")
        assert runner._cwd_matches(dep, port=5173) is True

    def test_no_pid_returns_true(self) -> None:
        runner = Runner(_instance())
        with patch.object(runner_mod, "_pid_on_port", return_value=None):
            assert runner._cwd_matches(_dep(), port=5173) is True

    def test_matching_cwd_returns_true(self, tmp_path: Path) -> None:
        runner = Runner(_instance())
        dep = _dep(start_cwd=str(tmp_path))
        with (
            patch.object(runner_mod, "_pid_on_port", return_value=1234),
            patch.object(runner_mod, "_cwd_of_pid", return_value=tmp_path.resolve()),
        ):
            assert runner._cwd_matches(dep, port=5173) is True

    def test_mismatched_cwd_returns_false(self, tmp_path: Path) -> None:
        runner = Runner(_instance())
        dep = _dep(start_cwd=str(tmp_path))
        other = (tmp_path / "other").resolve()
        with (
            patch.object(runner_mod, "_pid_on_port", return_value=1234),
            patch.object(runner_mod, "_cwd_of_pid", return_value=other),
        ):
            assert runner._cwd_matches(dep, port=5173) is False


# ---------------------------------------------------------------------------
# Runner.run / Runner.start / Runner.stop
# ---------------------------------------------------------------------------


class TestRun:
    def test_run_invokes_check_deps_then_app_run(self) -> None:
        runner = Runner(_instance())
        with (
            patch.object(runner, "check_deps") as check,
            patch("sidestage.runner.App.run") as app_run,
        ):
            runner.run()
        check.assert_called_once()
        app_run.assert_called_once_with("configs/")


class TestStart:
    def test_start_writes_pidfile_and_spawns(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        inst = _instance(name="dev", reload=True)
        runner = Runner(inst)
        fake_proc = MagicMock(pid=4242)
        with (
            patch.object(runner, "check_deps"),
            patch("subprocess.Popen", return_value=fake_proc) as popen,
        ):
            runner.start()
        cmd = popen.call_args.args[0]
        assert cmd[:3] == ["uv", "run", "sidestage"]
        assert "--config" in cmd and "configs/" in cmd
        assert "--reload" in cmd
        assert popen.call_args.kwargs.get("start_new_session") is True
        pid_file = tmp_path / ".sidestage-dev.pid"
        assert pid_file.exists()
        assert pid_file.read_text().strip() == "4242"

    def test_start_omits_reload_flag_when_false(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        inst = _instance(reload=False)
        runner = Runner(inst)
        fake_proc = MagicMock(pid=1)
        with (
            patch.object(runner, "check_deps"),
            patch("subprocess.Popen", return_value=fake_proc) as popen,
        ):
            runner.start()
        cmd = popen.call_args.args[0]
        assert "--reload" not in cmd


class TestStop:
    def test_stop_kills_port_and_removes_pidfile(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        pid_file = tmp_path / ".sidestage-dev.pid"
        pid_file.write_text("9999\n")
        runner = Runner(_instance(name="dev", port=8000))
        with patch("subprocess.run") as run_mock:
            runner.stop()
        run_mock.assert_called_once()
        assert run_mock.call_args.args[0] == ["fuser", "-k", "8000/tcp"]
        assert not pid_file.exists()

    def test_stop_when_no_pidfile_is_idempotent(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        runner = Runner(_instance(port=8000))
        with patch("subprocess.run"):
            runner.stop()  # no raise


# ---------------------------------------------------------------------------
# CLI entry point — runner-cli-instance / runner-cli-force / runner-cli-unknown
# ---------------------------------------------------------------------------


class TestMain:
    def _write_dev(self, dir: Path) -> None:
        (dir / "instances").mkdir()
        (dir / "instances" / "dev.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "dev",
                    "port": 8000,
                    "config_dir": "configs/",
                    "reload": True,
                    "dependencies": [],
                }
            )
        )

    def test_default_instance_is_dev(self, tmp_path: Path, monkeypatch) -> None:
        """runner-cli-instance: instance defaults to 'dev'."""
        monkeypatch.chdir(tmp_path)
        self._write_dev(tmp_path)
        with patch("sidestage.runner.Runner") as runner_cls:
            runner_cls.return_value = MagicMock()
            rc = main(["run"])
        assert rc == 0
        # Inspect the InstanceConfig passed in
        kwargs = runner_cls.call_args.kwargs
        assert kwargs["instance"].name == "dev"

    def test_unknown_instance_exits_with_error(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """runner-cli-unknown: unknown instance => non-zero exit."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "instances").mkdir()
        rc = main(["run", "ghost"])
        assert rc != 0
        err = capsys.readouterr().err
        assert "unknown instance" in err

    def test_force_backends_flag(self, tmp_path: Path, monkeypatch) -> None:
        """runner-cli-force: --force-backends sets Runner.force_backends."""
        monkeypatch.chdir(tmp_path)
        self._write_dev(tmp_path)
        with patch("sidestage.runner.Runner") as runner_cls:
            runner_cls.return_value = MagicMock()
            main(["run", "dev", "--force-backends"])
        kwargs = runner_cls.call_args.kwargs
        assert kwargs["force_backends"] is True

    def test_dispatches_run_start_stop(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        self._write_dev(tmp_path)
        for cmd in ("run", "start", "stop"):
            with patch("sidestage.runner.Runner") as runner_cls:
                runner_inst = MagicMock()
                runner_cls.return_value = runner_inst
                main([cmd])
            getattr(runner_inst, cmd).assert_called_once()

    def test_dependency_error_exits_nonzero(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        monkeypatch.chdir(tmp_path)
        self._write_dev(tmp_path)
        with patch("sidestage.runner.Runner") as runner_cls:
            inst = MagicMock()
            inst.run.side_effect = DependencyError("vite is on fire")
            runner_cls.return_value = inst
            rc = main(["run"])
        assert rc == 1
        assert "vite is on fire" in capsys.readouterr().err
