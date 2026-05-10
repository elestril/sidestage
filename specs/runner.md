# runner: Instance lifecycle manager

The runner (`sidestage-ctl`) manages the full lifecycle of a Sidestage
instance: it reads instance config, checks and starts required backend
dependencies, then launches the server.

## runner-instance-config: Instance configuration

Instance configs live in `instances/<name>.yaml`. The `dev` instance is the
only supported instance; it uses `./configs/` as its campaign directory and
has the Vite dev server as a required dependency.

### instance-config: InstanceConfig

Pydantic model for `instances/<name>.yaml`.

`name: str`
`port: int`
`config_dir: str`
`reload: bool`
`dependencies: list[DependencyConfig]`
- instance-config-name: Display name of the instance.
- instance-config-port: Port the Sidestage server listens on.
- instance-config-config-dir: Campaign directory passed to `App.run()`.
- instance-config-reload: If `True`, server is started with `--reload`.
- instance-config-deps: Ordered list of backend dependencies to check before launch.
- .implements: cuj-startup-launch

### dependency-config: DependencyConfig

`name: str`
`health_url: str`
`version_url: str | None`
`expected_version: str | None`
`start_cmd: str`
`start_cwd: str`
- dep-config-name: Human-readable label used in log output.
- dep-config-health-url: URL polled to determine if the service is up (2xx = up).
- dep-config-version-url: Optional URL whose JSON response contains a `version` field.
- dep-config-expected-version: Optional prefix matched against the `version` field from `version_url` (e.g. `"6"` matches `"6.3.1"`).
- dep-config-start-cmd: Shell command used to start the dependency.
- dep-config-start-cwd: Working directory for `start_cmd`; also the expected CWD of a running instance — resolved to an absolute path at runtime for comparison.

## runner-dep-dataflow: Dependency lifecycle dataflow

Executed for each `DependencyConfig` in order before the server starts.

1. runner-dep-health-check: GET `health_url`; if 2xx the service is considered up, skip to step 4.
   - .implements: cuj-startup-deps
   - .implemented-by: Runner.check_deps
2. runner-dep-start: Service is not up; run `start_cmd` in `start_cwd` (background process).
   - .implements: cuj-startup-deps
   - .implemented-by: Runner.check_deps, Runner.start_dep
3. runner-dep-wait: Poll `health_url` until 2xx or timeout (30 s); error if timeout.
   - .implements: cuj-startup-deps
   - .implemented-by: Runner.check_deps, Runner.start_dep
4. runner-dep-cwd-check: If `start_cwd` is set, resolve it to an absolute path and compare
   against the CWD of the process listening on the port (`fuser <port>/tcp` → PID →
   `readlink /proc/<pid>/cwd`). A mismatch is treated identically to a version mismatch
   (error or force-restart per step 6).
   - .implements: cuj-startup-deps
   - .implemented-by: Runner.check_deps
5. runner-dep-version-check: If `version_url` and `expected_version` are set, GET `version_url`
   and prefix-match response `version` field against `expected_version`.
   - runner-dep-version-ok: Version matches — continue.
   - runner-dep-version-mismatch: Version does not match:
     - Without `--force-backends`: exit with a descriptive error.
     - With `--force-backends`: proceed to runner-dep-force-restart.
   - .implements: cuj-startup-deps
   - .implemented-by: Runner.check_deps
6. runner-dep-force-restart: Run `fuser -k <port>/tcp` to kill whatever is on the service's
   port, then re-enter from runner-dep-start. If CWD or version still mismatches after
   restart, exit with error regardless of `--force-backends`.
   - .implements: cuj-startup-deps
   - .implemented-by: Runner.check_deps, Runner.restart_dep

## runner-impl: Runner class

### runner-class: Runner

`instance: InstanceConfig`
`force_backends: bool`

`check_deps(self) -> None`
- runner-check-deps: Executes runner-dep-dataflow for each dependency in order; raises `DependencyError` on any unresolvable failure.
- .implements: cuj-startup-deps

`start_dep(self, dep: DependencyConfig) -> None`
- runner-start-dep: Runs `dep.start_cmd` in `dep.start_cwd` as a background process and polls `dep.health_url` until up or timeout.
- .implements: runner-dep-start, runner-dep-wait

`restart_dep(self, dep: DependencyConfig) -> None`
- runner-restart-dep: Derives port from `dep.health_url`; runs `fuser -k <port>/tcp`; calls `start_dep(dep)`.
- .implements: runner-dep-force-restart

`run(self) -> None`
- runner-run-checks: Calls `check_deps()`.
- runner-run-server: Launches `App.run(self.instance.config_dir, reload=self.instance.reload)`.
- .implements: cuj-startup-deps, cuj-startup-load, cuj-startup-ready

`start(self) -> None`
- runner-start-daemonizes: Same as `run()` but daemonizes the server process and writes a PID file to `.sidestage-<name>.pid`.
- .implements: cuj-startup-deps, cuj-startup-load, cuj-startup-ready

`stop(self) -> None`
- runner-stop-port: Runs `fuser -k <instance.port>/tcp` to stop the server.
- runner-stop-pidfile: Removes `.sidestage-<name>.pid` if present.

## runner-entrypoint: CLI

`sidestage-ctl <run|start|stop> [instance] [--force-backends]`
- runner-cli-instance: `instance` defaults to `dev`; loads `instances/<instance>.yaml`.
- runner-cli-force: `--force-backends` sets `Runner.force_backends = True`.
- runner-cli-unknown: Unknown instance name exits with error.
- .implements: cuj-startup-launch
