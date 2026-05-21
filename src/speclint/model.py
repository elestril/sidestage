"""speclint: Data model shared across the extractor, rules, and CLI.

The vocabulary here mirrors the meta-spec `specs/spec.md`: a corpus is a
collection of `Label`s (each anchored at a source position) plus a list of
directed `LinkEdge`s between them. Rules consume that representation and emit
`Diagnostic`s, which the CLI filters through `Suppression`s before rendering.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class SourceKind(StrEnum):
    MARKDOWN_H1 = "markdown_h1"
    MARKDOWN_H2 = "markdown_h2"
    MARKDOWN_H3 = "markdown_h3"
    MARKDOWN_BULLET = "markdown_bullet"
    PYDOC_MODULE = "pydoc_module"
    PYDOC_CLASS = "pydoc_class"
    PYDOC_METHOD = "pydoc_method"
    PYDOC_ATTRIBUTE = "pydoc_attribute"
    PYDOC_FUNCTION = "pydoc_function"


class LinkKind(StrEnum):
    IMPLEMENTS = "implements"
    IMPLEMENTED_BY = "implemented-by"
    TESTED_BY = "tested-by"
    TESTS = "tests"


@dataclass(frozen=True)
class Label:
    name: str
    file: str
    line: int
    col: int
    source_kind: SourceKind
    parent_label: str | None
    depth: int
    body_text: str


@dataclass(frozen=True)
class LinkEdge:
    src_label: str
    kind: LinkKind
    target: str
    file: str
    line: int
    col: int


@dataclass(frozen=True)
class Diagnostic:
    file: str
    line: int
    col: int
    code: str
    severity: Severity
    message: str

    def render(self) -> str:
        return f"{self.file}:{self.line}:{self.col}: {self.code} {self.message}"


class SuppressionScope(StrEnum):
    GLOBAL = "global"
    PER_FILE = "per-file"
    INLINE = "inline"


@dataclass(frozen=True)
class Suppression:
    scope: SuppressionScope
    code: str
    file: str | None = None
    line: int | None = None


class LabelIndex:
    """In-memory index of all labels parsed across markdown specs and pydoc.

    Insertion-order preserved per name so SL003 (duplicate) can name the
    first-seen occurrence as canonical.
    """

    def __init__(self) -> None:
        self._by_name: dict[str, list[Label]] = defaultdict(list)

    def add(self, label: Label) -> None:
        self._by_name[label.name].append(label)

    def get(self, name: str) -> Label | None:
        labels = self._by_name.get(name)
        return labels[0] if labels else None

    def all_for(self, name: str) -> list[Label]:
        return list(self._by_name.get(name, ()))

    def names(self) -> Iterable[str]:
        return self._by_name.keys()

    def all_labels(self) -> Iterator[Label]:
        for labels in self._by_name.values():
            yield from labels

    def duplicates(self) -> Iterator[list[Label]]:
        for labels in self._by_name.values():
            if len(labels) > 1:
                yield labels

    def __contains__(self, name: str) -> bool:
        return name in self._by_name

    def __len__(self) -> int:
        return sum(len(v) for v in self._by_name.values())
