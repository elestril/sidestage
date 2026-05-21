"""speclint: Group B — link consistency rules.

Codes SL007–SL009. Operates on the unified LabelIndex and the flat list of
LinkEdges built by the extractor. Symbol-shaped targets (`Class.method`) are
not resolved here — Group C will handle them.
"""

from __future__ import annotations

import re

from speclint.model import (
    Diagnostic,
    LabelIndex,
    LinkEdge,
    LinkKind,
    Severity,
)

KEBAB_LABEL_RE = re.compile(r"^[a-z][a-z0-9-]*$")
SYMBOL_TARGET_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


def _is_kebab_label(target: str) -> bool:
    return bool(KEBAB_LABEL_RE.match(target))


def _is_symbol_target(target: str) -> bool:
    return "." in target and bool(SYMBOL_TARGET_RE.match(target))


def sl007_target_syntax(links: list[LinkEdge]) -> list[Diagnostic]:
    """SL007: each link target must be either a kebab label or `Class[.member]`."""
    out: list[Diagnostic] = []
    for edge in links:
        tgt = edge.target
        if not tgt:
            out.append(
                Diagnostic(
                    file=edge.file,
                    line=edge.line,
                    col=edge.col,
                    code="SL007",
                    severity=Severity.ERROR,
                    message=f"empty target on `.{edge.kind.value}` line",
                )
            )
            continue
        if (
            _is_kebab_label(tgt)
            or _is_symbol_target(tgt)
            or SYMBOL_TARGET_RE.match(tgt)
        ):
            continue
        out.append(
            Diagnostic(
                file=edge.file,
                line=edge.line,
                col=edge.col,
                code="SL007",
                severity=Severity.ERROR,
                message=(
                    f"target {tgt!r} on `.{edge.kind.value}` is not a kebab "
                    f"label or `Class[.member]` symbol"
                ),
            )
        )
    return out


_REVERSE: dict[LinkKind, LinkKind] = {
    LinkKind.IMPLEMENTS: LinkKind.IMPLEMENTED_BY,
    LinkKind.IMPLEMENTED_BY: LinkKind.IMPLEMENTS,
    LinkKind.TESTED_BY: LinkKind.TESTS,
    LinkKind.TESTS: LinkKind.TESTED_BY,
}


def sl008_bidirectional(
    index: LabelIndex,
    links: list[LinkEdge],
) -> list[Diagnostic]:
    """SL008: forward link to a known spec-label requires a matching reverse link.

    If A→.implements→B and B is a known kebab label, expect B→.implemented-by→A
    (or `A` matches a sibling label-name in B's `.implemented-by` line).

    Only checks kebab-label targets; symbol targets are deferred to Group C.
    """
    out: list[Diagnostic] = []
    by_src: dict[tuple[str, LinkKind], set[str]] = {}
    for edge in links:
        by_src.setdefault((edge.src_label, edge.kind), set()).add(edge.target)

    for edge in links:
        if not _is_kebab_label(edge.target):
            continue
        if edge.target not in index:
            continue
        reverse_kind = _REVERSE[edge.kind]
        reverse_targets = by_src.get((edge.target, reverse_kind), set())
        if edge.src_label not in reverse_targets:
            out.append(
                Diagnostic(
                    file=edge.file,
                    line=edge.line,
                    col=edge.col,
                    code="SL008",
                    severity=Severity.ERROR,
                    message=(
                        f"link {edge.src_label!r} --{edge.kind.value}--> "
                        f"{edge.target!r} not mirrored by reverse "
                        f"`.{reverse_kind.value}: {edge.src_label}` at "
                        f"{edge.target!r}"
                    ),
                )
            )
    return out


def sl009_unresolved_target(
    index: LabelIndex,
    links: list[LinkEdge],
) -> list[Diagnostic]:
    """SL009: every kebab-label target must resolve to a known label.

    Symbol-shaped targets (`Class.method`) are skipped — Group C resolves them.
    """
    out: list[Diagnostic] = []
    for edge in links:
        if not _is_kebab_label(edge.target):
            continue
        if edge.target in index:
            continue
        out.append(
            Diagnostic(
                file=edge.file,
                line=edge.line,
                col=edge.col,
                code="SL009",
                severity=Severity.ERROR,
                message=(
                    f"unresolved spec-label target {edge.target!r} on "
                    f"`.{edge.kind.value}` from {edge.src_label!r}"
                ),
            )
        )
    return out


def run_group_b(
    index: LabelIndex,
    links: list[LinkEdge],
) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    out.extend(sl007_target_syntax(links))
    out.extend(sl008_bidirectional(index, links))
    out.extend(sl009_unresolved_target(index, links))
    return out


__all__ = [
    "run_group_b",
    "sl007_target_syntax",
    "sl008_bidirectional",
    "sl009_unresolved_target",
]
