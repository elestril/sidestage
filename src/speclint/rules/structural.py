"""speclint: Group A — structural rules over the unified LabelIndex.

Codes SL001–SL006. These checks operate on labels alone (plus per-file
`ParseResult` for word count) and do not consult cross-file links.
"""

from __future__ import annotations

import re
from pathlib import Path

from speclint.extract import LABEL_RE, ParseResult
from speclint.model import (
    Diagnostic,
    Label,
    LabelIndex,
    Severity,
    SourceKind,
)

_HEADING_KINDS = {
    SourceKind.MARKDOWN_H1,
    SourceKind.MARKDOWN_H2,
    SourceKind.MARKDOWN_H3,
}
_MARKDOWN_KINDS = _HEADING_KINDS | {SourceKind.MARKDOWN_BULLET}

_LENGTH_WARN = 900
_LENGTH_ERROR = 1100
_HEADING_MIN_CONTENT_LINES = 3


def sl001_filename_label(
    md_files: dict[Path, ParseResult],
) -> list[Diagnostic]:
    """SL001 spec-labels-file: filename (sans .md) must equal the H1 label."""
    out: list[Diagnostic] = []
    for path, pr in md_files.items():
        expected = path.stem
        h1s = [lbl for lbl in pr.labels if lbl.source_kind == SourceKind.MARKDOWN_H1]
        if not h1s:
            out.append(
                Diagnostic(
                    file=str(path),
                    line=1,
                    col=1,
                    code="SL001",
                    severity=Severity.ERROR,
                    message=f"missing top-level `# {expected}: ...` heading",
                )
            )
            continue
        h1 = h1s[0]
        if h1.name != expected:
            out.append(
                Diagnostic(
                    file=h1.file,
                    line=h1.line,
                    col=h1.col,
                    code="SL001",
                    severity=Severity.ERROR,
                    message=(
                        f"top-level label {h1.name!r} does not match filename "
                        f"{expected!r}"
                    ),
                )
            )
    return out


_RAW_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def sl002_heading_format(md_files: dict[Path, ParseResult]) -> list[Diagnostic]:
    """SL002 spec-labels-headings: every ##/### heading must be `<label>: ...`.

    Read the raw file text to find heading lines that did not parse into a
    LABEL_RE-matching label — those are unlabelled headings the extractor
    skipped silently.
    """
    out: list[Diagnostic] = []
    for path, _pr in md_files.items():
        text = path.read_text(encoding="utf-8")
        in_fence = False
        for idx, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            m = _RAW_HEADING_RE.match(line)
            if not m:
                continue
            depth = len(m.group(1))
            if depth < 2 or depth > 3:
                continue
            heading_text = m.group(2).strip()
            if not LABEL_RE.match(heading_text):
                out.append(
                    Diagnostic(
                        file=str(path),
                        line=idx,
                        col=1,
                        code="SL002",
                        severity=Severity.ERROR,
                        message=(
                            f"heading {heading_text!r} missing `<label>: ...` prefix"
                        ),
                    )
                )
    return out


def sl003_label_uniqueness(index: LabelIndex) -> list[Diagnostic]:
    """SL003 spec-labels-unique: labels are globally unique across all sources."""
    out: list[Diagnostic] = []
    for dupes in index.duplicates():
        first = dupes[0]
        for d in dupes[1:]:
            out.append(
                Diagnostic(
                    file=d.file,
                    line=d.line,
                    col=d.col,
                    code="SL003",
                    severity=Severity.ERROR,
                    message=(
                        f"duplicate label {d.name!r} (first at "
                        f"{first.file}:{first.line})"
                    ),
                )
            )
    return out


def sl004_hierarchy(index: LabelIndex) -> list[Diagnostic]:
    """SL004 spec-hierarchy: a sub-label must share its parent's prefix.

    For any label `a-b-c`, at least one of `a` or `a-b` must exist in the index.
    Single-segment labels (no dash) are exempt; so are H1 labels (each `.md`
    file's top-level label is a file-root pinned to the filename via SL001 and
    needs no parent prefix).
    """
    out: list[Diagnostic] = []
    for lbl in index.all_labels():
        if lbl.source_kind == SourceKind.MARKDOWN_H1:
            continue
        segments = lbl.name.split("-")
        if len(segments) < 2:
            continue
        prefixes = ["-".join(segments[:i]) for i in range(1, len(segments))]
        if not any(p in index for p in prefixes):
            out.append(
                Diagnostic(
                    file=lbl.file,
                    line=lbl.line,
                    col=lbl.col,
                    code="SL004",
                    severity=Severity.ERROR,
                    message=(
                        f"label {lbl.name!r} has no parent prefix in index "
                        f"(expected one of: {', '.join(prefixes)})"
                    ),
                )
            )
    return out


def sl005_length(md_files: dict[Path, ParseResult]) -> list[Diagnostic]:
    """SL005 spec-length: warn at ≥ 900 words, error at ≥ 1100 words per .md."""
    out: list[Diagnostic] = []
    for path, pr in md_files.items():
        wc = pr.word_count
        if wc >= _LENGTH_ERROR:
            out.append(
                Diagnostic(
                    file=str(path),
                    line=1,
                    col=1,
                    code="SL005",
                    severity=Severity.ERROR,
                    message=(
                        f"spec is {wc} words (limit ~1000; split into focused "
                        f"sub-files)"
                    ),
                )
            )
        elif wc >= _LENGTH_WARN:
            out.append(
                Diagnostic(
                    file=str(path),
                    line=1,
                    col=1,
                    code="SL005",
                    severity=Severity.WARNING,
                    message=(f"spec is {wc} words (limit ~1000; consider splitting)"),
                )
            )
    return out


def sl006_heading_weight(
    md_files: dict[Path, ParseResult],
) -> list[Diagnostic]:
    """SL006 spec-headings-weight: warn on `##` sections with <3 lines of content.

    Compute by scanning raw text and measuring lines between successive `##`
    headings (or between an `##` and EOF / the next `# `). Code-fence content
    counts toward the line total.
    """
    out: list[Diagnostic] = []
    for path, _pr in md_files.items():
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        heading_indices = [i for i, ln in enumerate(lines) if ln.startswith("## ")]
        for j, idx in enumerate(heading_indices):
            end = heading_indices[j + 1] if j + 1 < len(heading_indices) else len(lines)
            content = lines[idx + 1 : end]
            non_blank = sum(1 for ln in content if ln.strip())
            if non_blank < _HEADING_MIN_CONTENT_LINES:
                out.append(
                    Diagnostic(
                        file=str(path),
                        line=idx + 1,
                        col=1,
                        code="SL006",
                        severity=Severity.WARNING,
                        message=(
                            f"`##` section has only {non_blank} non-blank "
                            f"content lines (min {_HEADING_MIN_CONTENT_LINES}); "
                            f"consider promoting to bullet"
                        ),
                    )
                )
    return out


def run_group_a(
    index: LabelIndex,
    md_files: dict[Path, ParseResult],
) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    out.extend(sl001_filename_label(md_files))
    out.extend(sl002_heading_format(md_files))
    out.extend(sl003_label_uniqueness(index))
    out.extend(sl004_hierarchy(index))
    out.extend(sl005_length(md_files))
    out.extend(sl006_heading_weight(md_files))
    return out


__all__ = [
    "run_group_a",
    "sl001_filename_label",
    "sl002_heading_format",
    "sl003_label_uniqueness",
    "sl004_hierarchy",
    "sl005_length",
    "sl006_heading_weight",
]


# Re-export helpers used by structural+links so consumers don't need to
# reach into model for Label.
_ = Label
