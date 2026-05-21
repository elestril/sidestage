"""speclint: Extract `Label`s and `LinkEdge`s from `.md` files and Python docstrings.

The two spec homes (per `specs/spec.md` `spec-location-*`) share one label/link
grammar, so we parse both with the same `markdown-it-py` walker. For `.py` we
use `docspec-python` to enumerate symbols and `ast` to pin docstring content
to its exact source line.
"""

from __future__ import annotations

import ast
import inspect
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import docspec
import docspec_python
from markdown_it import MarkdownIt
from markdown_it.token import Token

from speclint.model import (
    Label,
    LabelIndex,
    LinkEdge,
    LinkKind,
    SourceKind,
)

LABEL_RE = re.compile(r"^(?P<name>[a-z][a-z0-9-]*)\s*:\s*(?P<body>.+)$", re.DOTALL)
LINK_RE = re.compile(
    r"^\.(?P<kind>implements|implemented-by|tested-by|tests)\s*:\s*(?P<targets>.+)$",
)


@dataclass(frozen=True)
class ParseResult:
    labels: list[Label]
    links: list[LinkEdge]
    word_count: int


def _md() -> MarkdownIt:
    return MarkdownIt("commonmark")


def _first_inline(tokens: list[Token], item_idx: int) -> tuple[str | None, int]:
    """Find the first `inline` token belonging to the list_item at `item_idx`.

    Walks forward through nested paragraph_open / inline pairs, but stops if we
    hit another list_item_open at the same depth or our own list_item_close.
    Returns (content, line) or (None, 0) if the list item has no inline text
    (e.g. an empty bullet).
    """
    open_tok = tokens[item_idx]
    j = item_idx + 1
    while j < len(tokens):
        tok = tokens[j]
        if tok.type == "list_item_close" and tok.level == open_tok.level:
            return None, 0
        if tok.type == "inline":
            line = (tok.map[0] if tok.map else 0) + 1
            return tok.content, line
        j += 1
    return None, 0


def _walk_markdown_tokens(
    tokens: list[Token],
    file: str,
    line_offset: int,
    docstring_mode: bool = False,
    docstring_owner_kind: SourceKind = SourceKind.PYDOC_FUNCTION,
) -> tuple[list[Label], list[LinkEdge]]:
    """Walk a markdown-it-py token stream emitting Labels and LinkEdges.

    `line_offset` is added to every reported line — 0 for standalone .md files,
    or the docstring's content-start line minus 1 for embedded docstrings.

    In `docstring_mode`, the FIRST top-level paragraph that matches LABEL_RE
    is treated as the docstring's root label (since pydoc docstrings use a
    `name: summary` first line where `.md` files use a `# name:` heading).
    Subsequent top-level paragraphs are prose.

    Parent tracking: maintain a stack ordered by an `(heading_depth,
    bullet_level)` tuple so headings and bullets nest correctly. When a new
    label arrives, pop everything with effective_depth >= its own.
    """
    labels: list[Label] = []
    links: list[LinkEdge] = []
    stack: list[tuple[Label, tuple[int, int]]] = []
    current_heading_depth = 0
    first_paragraph_seen = False

    i = 0
    while i < len(tokens):
        tok = tokens[i]

        if (
            docstring_mode
            and not first_paragraph_seen
            and tok.type == "paragraph_open"
            and tok.level == 0
        ):
            inline = tokens[i + 1] if i + 1 < len(tokens) else None
            if inline is not None and inline.type == "inline":
                text = inline.content.strip()
                m = LABEL_RE.match(text)
                if m:
                    line = ((tok.map[0] if tok.map else 0) + 1) + line_offset
                    lbl = Label(
                        name=m["name"],
                        file=file,
                        line=line,
                        col=1,
                        source_kind=docstring_owner_kind,
                        parent_label=None,
                        depth=1,
                        body_text=m["body"].strip(),
                    )
                    labels.append(lbl)
                    stack.append((lbl, (1, 0)))
                    current_heading_depth = 1
            first_paragraph_seen = True
            i += 3
            continue

        if tok.type == "paragraph_open" and tok.level == 0:
            first_paragraph_seen = True

        if tok.type == "heading_open":
            inline = tokens[i + 1] if i + 1 < len(tokens) else None
            if inline is None or inline.type != "inline":
                i += 1
                continue
            text = inline.content.strip()
            line = ((tok.map[0] if tok.map else 0) + 1) + line_offset
            depth = int(tok.tag[1:]) if tok.tag.startswith("h") else 3
            current_heading_depth = depth
            sk = {
                1: SourceKind.MARKDOWN_H1,
                2: SourceKind.MARKDOWN_H2,
            }.get(depth, SourceKind.MARKDOWN_H3)
            m = LABEL_RE.match(text)
            if m:
                eff = (depth, 0)
                while stack and stack[-1][1] >= eff:
                    stack.pop()
                parent = stack[-1][0].name if stack else None
                lbl = Label(
                    name=m["name"],
                    file=file,
                    line=line,
                    col=1,
                    source_kind=sk,
                    parent_label=parent,
                    depth=depth,
                    body_text=m["body"].strip(),
                )
                labels.append(lbl)
                stack.append((lbl, eff))
            i += 3
            continue

        if tok.type == "list_item_open":
            text, raw_line = _first_inline(tokens, i)
            if text is not None:
                line = raw_line + line_offset
                # Markdown loose-list continuations can fold sibling text into a
                # bullet's inline content. Link bullets only ever span one line
                # per the spec format — restrict to the first line.
                first_line = text.split("\n", 1)[0]
                ml = LINK_RE.match(first_line)
                if ml:
                    # Resolve src like a labeled bullet would: pop the stack
                    # of entries at the same or deeper effective depth so a
                    # sibling link bullet attaches to its parent heading
                    # rather than to the previous labeled sibling. (Don't
                    # push — link bullets aren't labels themselves.)
                    heading_basis = (
                        current_heading_depth if current_heading_depth > 0 else 1
                    )
                    link_eff = (heading_basis, tok.level)
                    src_stack = list(stack)
                    while src_stack and src_stack[-1][1] >= link_eff:
                        src_stack.pop()
                    if src_stack:
                        src = src_stack[-1][0].name
                        try:
                            kind = LinkKind(ml["kind"])
                        except ValueError:
                            kind = None
                        if kind is not None:
                            for tgt in (t.strip() for t in ml["targets"].split(",")):
                                if tgt:
                                    links.append(
                                        LinkEdge(
                                            src_label=src,
                                            kind=kind,
                                            target=tgt,
                                            file=file,
                                            line=line,
                                            col=1,
                                        )
                                    )
                else:
                    mb = LABEL_RE.match(first_line)
                    if mb:
                        heading_basis = (
                            current_heading_depth if current_heading_depth > 0 else 1
                        )
                        eff = (heading_basis, tok.level)
                        while stack and stack[-1][1] >= eff:
                            stack.pop()
                        parent = stack[-1][0].name if stack else None
                        lbl = Label(
                            name=mb["name"],
                            file=file,
                            line=line,
                            col=1,
                            source_kind=SourceKind.MARKDOWN_BULLET,
                            parent_label=parent,
                            depth=heading_basis + tok.level,
                            body_text=mb["body"].strip(),
                        )
                        labels.append(lbl)
                        stack.append((lbl, eff))
            i += 1
            continue

        i += 1

    return labels, links


def _count_words(text: str) -> int:
    # Strip fenced code blocks before counting — examples shouldn't blow
    # past spec-length when the prose itself is well under.
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        out.append(line)
    return len(" ".join(out).split())


def parse_markdown(path: Path) -> ParseResult:
    text = path.read_text(encoding="utf-8")
    tokens = _md().parse(text)
    labels, links = _walk_markdown_tokens(tokens, str(path), line_offset=0)
    return ParseResult(labels=labels, links=links, word_count=_count_words(text))


def _docstring_offsets(source: str) -> dict[tuple[str, int], int]:
    """Map (qualname, def_lineno) → exact line of the docstring's first content.

    docspec reports a symbol's def line; we need the line of the cleaned
    docstring's first character. Compute via stdlib `ast` so the offset
    accounts for leading newlines inside the `\"\"\"` literal.
    """
    out: dict[tuple[str, int], int] = {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return out

    def visit(node: ast.AST, prefix: str) -> None:
        if isinstance(
            node,
            ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
        ):
            name = "" if isinstance(node, ast.Module) else node.name
            qname = f"{prefix}.{name}" if prefix and name else (prefix or name)
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                raw = body[0].value.value
                leading_nl = len(raw) - len(raw.lstrip("\n"))
                start_line = body[0].lineno + leading_nl
                def_line = node.lineno if not isinstance(node, ast.Module) else 1
                out[(qname, def_line)] = start_line
            new_prefix = qname if name else prefix
            for child in body:
                visit(child, new_prefix)

    visit(tree, "")
    return out


def _docspec_qname(api_obj: docspec.ApiObject, module_name: str) -> str:
    parts: list[str] = []
    cur: docspec.ApiObject | None = api_obj
    while cur is not None and not isinstance(cur, docspec.Module):
        parts.append(cur.name)
        cur = cur.parent
    parts.reverse()
    return ".".join(parts)


_OWNER_KIND: dict[type, SourceKind] = {
    docspec.Module: SourceKind.PYDOC_MODULE,
    docspec.Class: SourceKind.PYDOC_CLASS,
    docspec.Function: SourceKind.PYDOC_FUNCTION,
    docspec.Variable: SourceKind.PYDOC_ATTRIBUTE,
}


def parse_python(path: Path, module_name: str | None = None) -> ParseResult:
    source = path.read_text(encoding="utf-8")
    mod_name = module_name or path.stem
    modules = list(docspec_python.load_python_modules(files=[(mod_name, str(path))]))
    offsets = _docstring_offsets(source)
    labels: list[Label] = []
    links: list[LinkEdge] = []

    def visit(obj: docspec.ApiObject, in_class: bool) -> None:
        ds = obj.docstring
        if ds is not None and ds.content.strip():
            qname = _docspec_qname(obj, mod_name)
            def_line = (
                obj.location.lineno if obj.location and obj.location.lineno else 1
            )
            start_line = offsets.get((qname, def_line), def_line)
            cleaned = inspect.cleandoc(ds.content)
            tokens = _md().parse(cleaned)
            owner_kind = _OWNER_KIND.get(type(obj), SourceKind.PYDOC_FUNCTION)
            if owner_kind is SourceKind.PYDOC_FUNCTION and in_class:
                owner_kind = SourceKind.PYDOC_METHOD
            o_labels, o_links = _walk_markdown_tokens(
                tokens,
                str(path),
                line_offset=start_line - 1,
                docstring_mode=True,
                docstring_owner_kind=owner_kind,
            )
            labels.extend(o_labels)
            links.extend(o_links)
        for child in getattr(obj, "members", []) or []:
            visit(child, in_class=isinstance(obj, docspec.Class))

    for mod in modules:
        visit(mod, in_class=False)

    return ParseResult(labels=labels, links=links, word_count=0)


def build_index(
    md_paths: Iterable[Path],
    py_paths: Iterable[Path],
) -> tuple[LabelIndex, list[LinkEdge], dict[Path, ParseResult]]:
    """Parse every source, build a unified LabelIndex, return all link edges
    and per-file `ParseResult`s (rules consume the latter for per-file checks
    like SL005 word count).
    """
    index = LabelIndex()
    all_links: list[LinkEdge] = []
    per_file: dict[Path, ParseResult] = {}

    for p in md_paths:
        pr = parse_markdown(p)
        per_file[p] = pr
        for lbl in pr.labels:
            index.add(lbl)
        all_links.extend(pr.links)

    for p in py_paths:
        pr = parse_python(p)
        per_file[p] = pr
        for lbl in pr.labels:
            index.add(lbl)
        all_links.extend(pr.links)

    return index, all_links, per_file
