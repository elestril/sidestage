"""runner: Instance lifecycle manager.

Implements `specs/runner.md`. The runner reads an instance config from
`instances/<name>.yaml`, checks/starts/validates required backend
dependencies, then launches the Sidestage server.

The CLI entry point is `sidestage-ctl` (registered in `pyproject.toml`).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from json import loads as json_loads
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel

from sidestage.server import App


# ---------------------------------------------------------------------------
# Tunables. Module-level so tests can monkeypatch instead of mocking time.
# ---------------------------------------------------------------------------

_HEALTH_TIMEOUT_S: float = 30.0
_HEALTH_POLL_INTERVAL_S: float = 0.5
_HEALTH_REQUEST_TIMEOUT_S: float = 2.0


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DependencyError(RuntimeError):
    """runner-dependency-error: Raised by `Runner.check_deps` when a
    dependency cannot be brought into a healthy, version-matched state.

    .implements: runner-check-deps
    """


# ---------------------------------------------------------------------------
# Config models
# ---------------------------------------------------------------------------


class DependencyConfig(BaseModel):
    """dependency-config: Pydantic model for a single backend dependency
    declared under `dependencies:` in an instance config file.

    .implements: instance-config-deps
    """

    name: str
    """dep-config-name: Human-readable label used in log output."""

    health_url: str
    """dep-config-health-url: URL polled to determine if the service is up;
    a 2xx response means the dependency is considered healthy."""

    version_url: Optional[str] = None
    """dep-config-version-url: Optional URL whose JSON response contains a
    `version` field; consulted when `expected_version` is also set."""

    expected_version: Optional[str] = None
    """dep-config-expected-version: Optional prefix matched against the
    `version` field returned by `version_url` (e.g. `"6"` matches `"6.3.1"`)."""

    start_cmd: str
    """dep-config-start-cmd: Shell command used to start the dependency."""

    start_cwd: str
    """dep-config-start-cwd: Working directory for `start_cmd`; also the
    expected CWD of a running instance — resolved to an absolute path at
    runtime for comparison against `/proc/<pid>/cwd`."""


class InstanceConfig(BaseModel):
    """instance-config: Pydantic model for `instances/<name>.yaml`.

    .implements: cuj-startup-launch
    """

    name: str
    """instance-config-name: Display name of the instance."""

    port: int
    """instance-config-port: Port the Sidestage server listens on."""

    config_dir: str
    """instance-config-config-dir: Campaign directory passed to `App.run()`."""

    reload: bool = False
    """instance-config-reload: If `True`, the server is started with the
    `--reload` flag (only meaningful when launched as a subprocess)."""

    dependencies: list[DependencyConfig] = []
    """instance-config-deps: Ordered list of backend dependencies that the
    runner checks (and starts if needed) before launching the server."""


# ---------------------------------------------------------------------------
# Helpers (private — implementation detail, no spec)
# ---------------------------------------------------------------------------


def _port_from_url(url: str) -> int:
    """Extract the TCP port from a URL. Falls back to 80/443 for http/https
    when the URL omits an explicit port. Raises `ValueError` if no port can
    be derived.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.port is not None:
        return parsed.port
    if parsed.scheme == "http":
        return 80
    if parsed.scheme == "https":
        return 443
    raise ValueError(f"cannot derive port from URL: {url!r}")


def _http_get(url: str, timeout: float = _HEALTH_REQUEST_TIMEOUT_S) -> tuple[int, bytes]:
    """GET `url` and return `(status, body_bytes)`.

    Treats connection-refused / DNS / timeout errors as status 0 so callers
    can use a single integer comparison to gate behaviour.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.getcode(), resp.read()
    except urllib.error.HTTPError as e:
        # HTTP-level failure (4xx/5xx) — caller may still want the code.
        return e.code, b""
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        return 0, b""


def _is_2xx(status: int) -> bool:
    return 200 <= status < 300


def _pid_on_port(port: int) -> Optional[int]:
    """Return the PID of the process listening on `port`, or None if no
    process is found. Uses `fuser <port>/tcp`.
    """
    try:
        result = subprocess.run(
            ["fuser", f"{port}/tcp"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    out = (result.stdout or "") + " " + (result.stderr or "")
    # fuser prints PIDs whitespace-separated on stdout; the port label goes
    # to stderr. Take the first token that parses as an integer.
    for token in out.split():
        token = token.strip().rstrip(":")
        try:
            return int(token)
        except ValueError:
            continue
    return None


def _cwd_of_pid(pid: int) -> Optional[Path]:
    """Return the resolved CWD of `pid` via `/proc/<pid>/cwd`. Returns None
    if the link cannot be read (process gone, permission denied, non-Linux).
    """
    link = Path(f"/proc/{pid}/cwd")
    try:
        return Path(os.readlink(link)).resolve()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class Runner:
    """runner-class: Owns one instance's lifecycle — dependency check,
    server launch, daemonisation, and shutdown.

    Constructed with a parsed `InstanceConfig` and a `force_backends` flag.
    The CLI entry point `main()` performs the YAML load and constructs a
    Runner.

    .implements: cuj-startup-launch, cuj-startup-deps, cuj-startup-load, cuj-startup-ready
    """

    instance: InstanceConfig
    """runner-instance: The InstanceConfig loaded from `instances/<name>.yaml`.

    .implements: instance-config
    """

    force_backends: bool
    """runner-force-backends: When True, version/cwd mismatches trigger
    `runner-dep-force-restart` instead of erroring out.

    .implements: runner-cli-force
    """

    def __init__(self, instance: InstanceConfig, force_backends: bool = False) -> None:
        """runner-init: Construct a Runner bound to a loaded `InstanceConfig`.

        Args:
            instance: The instance config to manage.
            force_backends: Per `runner-force-backends`.

        .implements: runner-class
        """
        self.instance = instance
        self.force_backends = force_backends

    # ------------------------- dependency checks -------------------------

    def check_deps(self) -> None:
        """runner-check-deps: Execute `runner-dep-dataflow` for each
        dependency in `instance.dependencies` in order.

        Raises:
            DependencyError: If any dependency cannot be brought into a
            healthy, version-and-cwd-matched state.

        .implements: cuj-startup-deps
        """
        for dep in self.instance.dependencies:
            self._check_one_dep(dep, allow_restart=self.force_backends)

    def _check_one_dep(
        self, dep: DependencyConfig, allow_restart: bool
    ) -> None:
        """Run the full per-dependency dataflow. `allow_restart` toggles
        whether a cwd/version mismatch triggers `restart_dep` (force mode)
        or raises immediately.
        """
        port = _port_from_url(dep.health_url)

        # 1. runner-dep-health-check
        status, _ = _http_get(dep.health_url)
        if not _is_2xx(status):
            # 2. runner-dep-start + 3. runner-dep-wait
            self.start_dep(dep)

        # 4. runner-dep-cwd-check
        cwd_ok = self._cwd_matches(dep, port)
        # 5. runner-dep-version-check
        version_ok = self._version_matches(dep)

        if cwd_ok and version_ok:
            return

        # 6. runner-dep-force-restart
        if not allow_restart:
            reasons = []
            if not cwd_ok:
                reasons.append("cwd mismatch")
            if not version_ok:
                reasons.append("version mismatch")
            raise DependencyError(
                f"dependency {dep.name!r}: "
                f"{', '.join(reasons)} "
                f"(re-run with --force-backends to restart)"
            )

        # Force-restart path. Recurse once with allow_restart=False so any
        # post-restart mismatch hard-fails per spec ("regardless of
        # --force-backends").
        self.restart_dep(dep)
        self._check_one_dep(dep, allow_restart=False)

    def _cwd_matches(self, dep: DependencyConfig, port: int) -> bool:
        """True if the process on `port` runs out of `dep.start_cwd`
        (resolved to absolute). True if we cannot determine the PID/CWD —
        we don't want a /proc oddity to falsely flag a healthy dep.
        """
        if not dep.start_cwd:
            return True
        pid = _pid_on_port(port)
        if pid is None:
            return True
        actual = _cwd_of_pid(pid)
        if actual is None:
            return True
        expected = Path(dep.start_cwd).resolve()
        return actual == expected

    def _version_matches(self, dep: DependencyConfig) -> bool:
        """True when `version_url`/`expected_version` are unset OR when the
        response's `version` field starts with `expected_version`.
        """
        if not dep.version_url or not dep.expected_version:
            return True
        status, body = _http_get(dep.version_url)
        if not _is_2xx(status):
            return False
        try:
            payload = json_loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return False
        version = payload.get("version") if isinstance(payload, dict) else None
        if not isinstance(version, str):
            return False
        return version.startswith(dep.expected_version)

    # ------------------------- dep lifecycle -------------------------

    def start_dep(self, dep: DependencyConfig) -> None:
        """runner-start-dep: Run `dep.start_cmd` in `dep.start_cwd` as a
        background process and poll `dep.health_url` until 2xx or until
        `_HEALTH_TIMEOUT_S` (30 s) elapses.

        Raises:
            DependencyError: If the health URL does not return 2xx before
            the timeout expires.

        .implements: runner-dep-start, runner-dep-wait
        """
        print(f"[runner] starting dependency {dep.name!r} ...", file=sys.stderr)
        subprocess.Popen(  # noqa: S603
            dep.start_cmd,
            shell=True,
            cwd=dep.start_cwd or None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        deadline = time.monotonic() + _HEALTH_TIMEOUT_S
        while time.monotonic() < deadline:
            status, _ = _http_get(dep.health_url)
            if _is_2xx(status):
                return
            time.sleep(_HEALTH_POLL_INTERVAL_S)
        raise DependencyError(
            f"dependency {dep.name!r}: health URL {dep.health_url} "
            f"did not return 2xx within {_HEALTH_TIMEOUT_S:.0f}s"
        )

    def restart_dep(self, dep: DependencyConfig) -> None:
        """runner-restart-dep: Derive the port from `dep.health_url`, run
        `fuser -k <port>/tcp` to kill whatever is currently listening, then
        call `start_dep(dep)` to bring up a fresh instance.

        .implements: runner-dep-force-restart
        """
        port = _port_from_url(dep.health_url)
        print(
            f"[runner] force-restarting {dep.name!r} on port {port}",
            file=sys.stderr,
        )
        subprocess.run(  # noqa: S603, S607
            ["fuser", "-k", f"{port}/tcp"],
            check=False,
            capture_output=True,
        )
        self.start_dep(dep)

    # ------------------------- server lifecycle -------------------------

    def run(self) -> None:
        """runner-run-checks + runner-run-server: Check dependencies, then
        launch `App.run(self.instance.config_dir)` in this process.

        Note: `instance.reload` is honoured by `start()` (which launches the
        server in a subprocess able to take `--reload`) but is not plumbed
        into the in-process `App.run` call today — `App.run` doesn't accept
        a reload kwarg.

        .implements: cuj-startup-deps, cuj-startup-load, cuj-startup-ready
        """
        self.check_deps()
        App.run(self.instance.config_dir)

    def start(self) -> None:
        """runner-start-daemonizes: Check dependencies, then daemonize the
        server process (writing PID to `.sidestage-<name>.pid` and logs to
        `.sidestage-<name>.log`). The current process exits after spawning.

        .implements: cuj-startup-deps, cuj-startup-load, cuj-startup-ready
        """
        self.check_deps()

        pid_file = Path(f".sidestage-{self.instance.name}.pid")
        log_file = Path(f".sidestage-{self.instance.name}.log")

        cmd = [
            "uv",
            "run",
            "sidestage",
            "--config",
            self.instance.config_dir,
        ]
        if self.instance.reload:
            cmd.append("--reload")

        log_fh = open(log_file, "a")
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        pid_file.write_text(f"{proc.pid}\n")
        print(
            f"sidestage[{self.instance.name}] started (pid {proc.pid}) -> {log_file}",
            file=sys.stderr,
        )

    def stop(self) -> None:
        """runner-stop-port + runner-stop-pidfile: Kill the process on
        `instance.port` via `fuser -k`, then remove the PID file if it
        exists.

        .implements: runner-stop-port, runner-stop-pidfile
        """
        subprocess.run(  # noqa: S603, S607
            ["fuser", "-k", f"{self.instance.port}/tcp"],
            check=False,
            capture_output=True,
        )
        pid_file = Path(f".sidestage-{self.instance.name}.pid")
        if pid_file.exists():
            pid_file.unlink()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _load_instance(name: str) -> InstanceConfig:
    """runner-cli-instance helper: load `instances/<name>.yaml` and parse it
    into an `InstanceConfig`. Raises `FileNotFoundError` if the file is
    absent (the CLI translates that to `runner-cli-unknown`).
    """
    path = Path("instances") / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(str(path))
    raw = yaml.safe_load(path.read_text()) or {}
    return InstanceConfig.model_validate(raw)


def main(argv: Optional[list[str]] = None) -> int:
    """runner-entrypoint: `sidestage-ctl <run|start|stop> [instance] [--force-backends]`.

    - runner-cli-instance: `instance` defaults to `dev`; loads
      `instances/<instance>.yaml`.
    - runner-cli-force: `--force-backends` sets `Runner.force_backends = True`.
    - runner-cli-unknown: Unknown instance name exits with error.

    .implements: cuj-startup-launch
    """
    parser = argparse.ArgumentParser(
        prog="sidestage-ctl",
        description="Sidestage instance lifecycle manager.",
    )
    parser.add_argument(
        "command",
        choices=["run", "start", "stop"],
        help="Lifecycle command to execute.",
    )
    parser.add_argument(
        "instance",
        nargs="?",
        default="dev",
        help="Instance name (default: dev). Loads instances/<name>.yaml.",
    )
    parser.add_argument(
        "--force-backends",
        action="store_true",
        help="Force-restart dependencies whose cwd or version doesn't match.",
    )
    args = parser.parse_args(argv)

    try:
        instance = _load_instance(args.instance)
    except FileNotFoundError:
        print(
            f"sidestage-ctl: unknown instance {args.instance!r} "
            f"(no instances/{args.instance}.yaml)",
            file=sys.stderr,
        )
        return 2

    runner = Runner(instance=instance, force_backends=args.force_backends)

    try:
        if args.command == "run":
            runner.run()
        elif args.command == "start":
            runner.start()
        elif args.command == "stop":
            runner.stop()
    except DependencyError as e:
        print(f"sidestage-ctl: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
