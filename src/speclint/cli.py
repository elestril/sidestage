"""speclint: Command-line entry.

Discovers spec files, runs Group A + B rules, applies suppressions
(inline + `pyproject.toml`), renders ruff-style output, returns nonzero on
unsuppressed errors.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from speclint.extract import build_index
from speclint.model import Diagnostic, Severity
from speclint.rules import ALL_CODES, run_group_a, run_group_b

DEFAULT_SPEC_DIRS = ("specs",)
DEFAULT_PY_DIRS = ("src/sidestage",)

INLINE_SUPPRESSION_RE = re.compile(
    r"speclint:\s*ignore\s+(?P<codes>SL\d+(?:\s*,\s*SL\d+)*)"
)


@dataclass(frozen=True)
class Config:
    ignore: frozenset[str]
    per_file_ignores: dict[str, frozenset[str]]

    @staticmethod
    def empty() -> Config:
        return Config(ignore=frozenset(), per_file_ignores={})


def _load_config(pyproject: Path) -> Config:
    if not pyproject.is_file():
        return Config.empty()
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return Config.empty()
    tool = data.get("tool", {}).get("speclint", {})
    ignore = frozenset(tool.get("ignore", []))
    per_file_raw = tool.get("per-file-ignores", {}) or {}
    per_file = {k: frozenset(v) for k, v in per_file_raw.items()}
    return Config(ignore=ignore, per_file_ignores=per_file)


_EXCLUDED_MD_DIRS = ("generated",)


def _iter_md_files(roots: Iterable[Path]) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".md":
            out.append(root)
        elif root.is_dir():
            out.extend(
                p
                for p in sorted(root.rglob("*.md"))
                if not any(part in _EXCLUDED_MD_DIRS for part in p.parts)
            )
    return out


def _iter_py_files(roots: Iterable[Path]) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            out.append(root)
        elif root.is_dir():
            out.extend(
                p
                for p in sorted(root.rglob("*.py"))
                if "_test" not in p.stem and p.stem != "conftest"
            )
    return out


def _scan_inline_suppressions(paths: Iterable[Path]) -> dict[tuple[str, int], set[str]]:
    """Map (file, applicable_line) → set of SL codes suppressed inline.

    A suppression comment suppresses diagnostics on the next non-blank line.
    Supports both HTML comments in `.md` and `#` comments inside `.py`
    docstrings (the latter matches anywhere on the line so docstring-internal
    suppressions work).
    """
    out: dict[tuple[str, int], set[str]] = {}
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        pending_codes: set[str] | None = None
        for idx, line in enumerate(lines, start=1):
            m = INLINE_SUPPRESSION_RE.search(line)
            if m:
                codes = {c.strip() for c in m.group("codes").split(",")}
                if pending_codes is None:
                    pending_codes = set()
                pending_codes |= codes
                continue
            if pending_codes is not None and line.strip():
                out.setdefault((str(path), idx), set()).update(pending_codes)
                pending_codes = None
    return out


def _filter(
    diags: list[Diagnostic],
    config: Config,
    inline: dict[tuple[str, int], set[str]],
    show_ignored: bool,
) -> tuple[list[Diagnostic], list[Diagnostic]]:
    kept: list[Diagnostic] = []
    suppressed: list[Diagnostic] = []
    for d in diags:
        codes = {d.code}
        if codes & inline.get((d.file, d.line), set()):
            suppressed.append(d)
            continue
        per_file = config.per_file_ignores.get(d.file, frozenset())
        if d.code in per_file:
            suppressed.append(d)
            continue
        if d.code in config.ignore:
            suppressed.append(d)
            continue
        kept.append(d)
    if show_ignored:
        kept = kept + suppressed
        suppressed = []
    return kept, suppressed


def _render(diags: list[Diagnostic]) -> str:
    return "\n".join(d.render() for d in diags)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="speclint",
        description="Lint Sidestage specs (specs/*.md + pydoc docstrings).",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files or directories to lint. Default: specs/ + src/sidestage/.",
    )
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        metavar="CODE",
        help="Suppress all diagnostics of this code globally.",
    )
    parser.add_argument(
        "--warn-as-error",
        action="store_true",
        help="Treat warnings as errors for exit-code purposes.",
    )
    parser.add_argument(
        "--show-ignored",
        action="store_true",
        help="Render suppressed diagnostics too (still exit 0 for them).",
    )
    parser.add_argument(
        "--list-codes",
        action="store_true",
        help="Print all rule codes and exit.",
    )
    args = parser.parse_args(argv)

    if args.list_codes:
        print("\n".join(ALL_CODES))
        return 0

    config = _load_config(Path("pyproject.toml"))
    config = Config(
        ignore=frozenset(set(config.ignore) | set(args.ignore)),
        per_file_ignores=config.per_file_ignores,
    )

    if args.paths:
        roots = [Path(p) for p in args.paths]
        md_roots = roots
        py_roots = roots
    else:
        md_roots = [Path(d) for d in DEFAULT_SPEC_DIRS]
        py_roots = [Path(d) for d in DEFAULT_PY_DIRS]

    md_paths = _iter_md_files(md_roots)
    py_paths = _iter_py_files(py_roots)

    if not md_paths and not py_paths:
        print("speclint: no .md or .py files found", file=sys.stderr)
        return 2

    index, links, per_file = build_index(md_paths, py_paths)

    md_only = {p: per_file[p] for p in md_paths if p in per_file}

    diags: list[Diagnostic] = []
    diags.extend(run_group_a(index, md_only))
    diags.extend(run_group_b(index, links))

    diags.sort(key=lambda d: (d.file, d.line, d.col, d.code))

    inline = _scan_inline_suppressions(md_paths + py_paths)
    kept, _suppressed = _filter(diags, config, inline, args.show_ignored)

    if kept:
        print(_render(kept))

    has_error = any(
        d.severity == Severity.ERROR
        or (args.warn_as_error and d.severity == Severity.WARNING)
        for d in kept
    )
    return 1 if has_error else 0


if __name__ == "__main__":
    sys.exit(main())
