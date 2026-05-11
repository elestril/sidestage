#!/usr/bin/env python3
"""llm_up: ensure every managed model in a profile is up.

Usage: `bin/llm_up.py <sidestage_dir> <profile_name>`

Per `specs/llm-profiles.md` → `llm-profile-lifecycle`. For each entry
whose endpoint host is loopback (so `entry.managed` is True): poll
`/health`; if down, build per-model flags and exec
`bin/run-llama-server.sh` with them (the wrapper applies any
machine-wide defaults); wait for `/health` to flip 2xx.

Idempotent. External (non-loopback) entries are skipped — we just
consume them.
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Resolved at runtime via the venv that `uv run` arranges.
from sidestage.llm_profile import LlmProfile, ModelEntry, load_profiles


# Generous timeout because first run may download multi-GB weights from
# HuggingFace. Subsequent runs hit the local cache and start in seconds.
_READY_TIMEOUT_S = 180.0

# Path to the wrapper script that exec's `llama-server`. Lives alongside
# this file in `bin/` — so contributors edit one place for machine-wide
# llama-server flags.
_WRAPPER = Path(__file__).resolve().parent / "run-llama-server.sh"


def _is_up(port: int) -> bool:
    """llm-up-check-up: True iff GET http://127.0.0.1:<port>/health is 2xx."""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/health", timeout=1.0
        ) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        return False


def _build_args(role: str, entry: ModelEntry) -> list[str]:
    """Build the per-model args list passed to `bin/run-llama-server.sh`.

    The wrapper script supplies machine-wide defaults (`--host`,
    optional GPU/thread flags). This function emits ONLY what varies
    per model: port, weight references, ctx-size, embedding flag.
    """
    if entry.port is None:
        raise ValueError(
            f"llm-profile-schema-endpoint: managed role {role!r} has no "
            f"port in its endpoint ({entry.endpoint!r})"
        )
    args = ["--port", str(entry.port)]
    if entry.hf_repo:
        args += ["--hf-repo", entry.hf_repo]
    if entry.hf_file:
        args += ["--hf-file", entry.hf_file]
    if entry.ctx_size is not None:
        args += ["--ctx-size", str(entry.ctx_size)]
    if entry.embedding:
        args += ["--embedding"]
    return args


def _spawn(role: str, entry: ModelEntry, log_dir: Path) -> None:
    """llm-up-spawn: detach `bin/run-llama-server.sh` for one model entry.

    Stdout/stderr go to `<sidestage_dir>/logs/llm-<role>.log`. The
    process detaches via `start_new_session=True` so it survives this
    script exiting.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"llm-{role}.log"
    cmd = [str(_WRAPPER), *_build_args(role, entry)]
    print(f"  spawning {role}: {' '.join(cmd)}")
    log_fh = log_path.open("ab")
    subprocess.Popen(  # noqa: S603 — args built from validated config
        cmd,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def _wait_ready(role: str, port: int, log_path: Path) -> None:
    """llm-up-wait: poll /health until ready or timeout."""
    deadline = time.monotonic() + _READY_TIMEOUT_S
    while time.monotonic() < deadline:
        if _is_up(port):
            return
        time.sleep(0.5)
    raise RuntimeError(
        f"llm-up-wait: {role} on :{port} did not come up within "
        f"{_READY_TIMEOUT_S:.0f}s — check {log_path}"
    )


def ensure_profile_up(sidestage_dir: Path, profile_name: str) -> None:
    """Top-level entry: bring every managed model in the profile up."""
    profiles = load_profiles(sidestage_dir)
    if profile_name not in profiles:
        available = ", ".join(sorted(profiles)) or "(none)"
        raise SystemExit(
            f"profile {profile_name!r} not found in "
            f"{sidestage_dir}/llm_profiles/; available: {available}"
        )
    profile: LlmProfile = profiles[profile_name]
    log_dir = sidestage_dir / "logs"
    for role, entry in profile.models.items():
        if not entry.managed:
            print(f"  {role}: external ({entry.endpoint}) — skipping")
            continue
        port = entry.port
        assert port is not None  # _build_args raises if not — defensive
        if _is_up(port):
            print(f"  {role}: already up on :{port}")
            continue
        _spawn(role, entry, log_dir)
        _wait_ready(role, port, log_dir / f"llm-{role}.log")
        print(f"  {role}: ready on :{port}")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(
            "usage: llm_up.py <sidestage_dir> <profile_name>",
            file=sys.stderr,
        )
        return 2
    sidestage_dir = Path(args[0])
    profile_name = args[1]
    ensure_profile_up(sidestage_dir, profile_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
