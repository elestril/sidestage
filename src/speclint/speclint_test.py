"""speclint: Unit tests for extract + Group A + Group B rules.

Synthetic fixtures live under `testdata/`. Each test focuses on a single
rule code; the asserts use `code in {d.code for d in diags}` so unrelated
rule output doesn't make the test brittle.
"""

from __future__ import annotations

from pathlib import Path

from speclint.extract import build_index, parse_markdown, parse_python
from speclint.model import LinkKind, SourceKind
from speclint.rules.links import (
    sl007_target_syntax,
    sl008_bidirectional,
    sl009_unresolved_target,
)
from speclint.rules.structural import (
    sl001_filename_label,
    sl002_heading_format,
    sl003_label_uniqueness,
    sl004_hierarchy,
    sl005_length,
)

DATA = Path(__file__).parent / "testdata"


def test_extract_markdown_clean_finds_labels_and_links():
    pr = parse_markdown(DATA / "clean.md")
    names = {lbl.name for lbl in pr.labels}
    assert {"clean", "clean-child", "clean-child-leaf"} <= names
    kinds = {lbl.name: lbl.source_kind for lbl in pr.labels}
    assert kinds["clean"] == SourceKind.MARKDOWN_H1
    assert kinds["clean-child"] == SourceKind.MARKDOWN_H2
    assert kinds["clean-child-leaf"] == SourceKind.MARKDOWN_BULLET
    implements = [lk for lk in pr.links if lk.kind == LinkKind.IMPLEMENTS]
    assert any(
        lk.src_label == "clean-child-leaf" and lk.target == "clean-child"
        for lk in implements
    )


def test_extract_python_docstring_emits_pydoc_root_label():
    pr = parse_python(DATA / "sample.py")
    by_name = {lbl.name: lbl for lbl in pr.labels}
    assert by_name["sample"].source_kind == SourceKind.PYDOC_MODULE
    assert by_name["sample-class"].source_kind == SourceKind.PYDOC_CLASS
    assert by_name["sample-class-greet"].source_kind in {
        SourceKind.PYDOC_METHOD,
        SourceKind.MARKDOWN_BULLET,
    }


def test_extract_first_line_only_for_link_targets():
    # Regression: markdown-it-py loose-list continuation can fold sibling
    # text into a link bullet's inline content. The walker truncates at the
    # first newline so multi-line drift doesn't poison the target list.
    src = (
        "# multi: A spec.\n\n"
        "- multi-leaf: A bullet.\n"
        "  - .implements: multi\n"
        "    spurious continuation should not appear in the target.\n"
    )
    fixture = DATA / "_multi_tmp.md"
    fixture.write_text(src, encoding="utf-8")
    try:
        pr = parse_markdown(fixture)
        targets = [lk.target for lk in pr.links]
        assert "multi" in targets
        assert all("\n" not in t for t in targets)
    finally:
        fixture.unlink()


def test_sl001_filename_must_match_h1():
    pr = parse_markdown(DATA / "bad_filename.md")
    diags = sl001_filename_label({DATA / "bad_filename.md": pr})
    assert any(d.code == "SL001" for d in diags)


def test_sl002_heading_must_carry_label_prefix():
    pr = parse_markdown(DATA / "bad_heading.md")
    diags = sl002_heading_format({DATA / "bad_heading.md": pr})
    assert any(d.code == "SL002" for d in diags)


def test_sl003_duplicate_labels_flagged():
    index, _, _ = build_index([DATA / "dup_label.md"], [])
    diags = sl003_label_uniqueness(index)
    assert any(d.code == "SL003" and "dup-label-a" in d.message for d in diags)


def test_sl004_missing_prefix_parent_flagged():
    index, _, _ = build_index([DATA / "bad_hierarchy.md"], [])
    diags = sl004_hierarchy(index)
    assert any(
        d.code == "SL004" and "nonexistent-prefix-leaf" in d.message for d in diags
    )


def test_sl004_h1_root_is_exempt():
    # `clean` is a single-segment H1 and inherently exempt; the multi-segment
    # H1 case is covered by parse_markdown returning a MARKDOWN_H1 with no
    # parent prefix required.
    src = "# multi-segment-root: A compound root label.\n\nProse.\n"
    fixture = DATA / "_root_tmp.md"
    fixture.write_text(src, encoding="utf-8")
    try:
        index, _, _ = build_index([fixture], [])
        diags = sl004_hierarchy(index)
        assert not any(
            d.code == "SL004" and "multi-segment-root" in d.message for d in diags
        )
    finally:
        fixture.unlink()


def test_sl005_length_flags_oversize():
    # Synthesize a long spec (> 1100 words) on the fly and check SL005 errors.
    body = " ".join(["word"] * 1200)
    src = f"# long: A very long spec.\n\n{body}\n"
    fixture = DATA / "_long_tmp.md"
    fixture.write_text(src, encoding="utf-8")
    try:
        pr = parse_markdown(fixture)
        diags = sl005_length({fixture: pr})
        assert any(d.code == "SL005" and d.severity.value == "error" for d in diags)
    finally:
        fixture.unlink()


def test_sl007_rejects_non_label_target():
    src = (
        "# bad: A spec.\n\n"
        "- bad-a: Has a prose target.\n"
        "  - .implements: not a real label\n"
    )
    fixture = DATA / "_sl007_tmp.md"
    fixture.write_text(src, encoding="utf-8")
    try:
        pr = parse_markdown(fixture)
        diags = sl007_target_syntax(pr.links)
        assert any(d.code == "SL007" for d in diags)
    finally:
        fixture.unlink()


def test_sl008_bidirectional_balance_flagged():
    index, links, _ = build_index([DATA / "unbalanced.md"], [])
    diags = sl008_bidirectional(index, links)
    # unbalanced-a .implemented-by: unbalanced-b — unbalanced-b has no
    # reverse `.implements: unbalanced-a`.
    assert any(
        d.code == "SL008"
        and "unbalanced-a" in d.message
        and "unbalanced-b" in d.message
        for d in diags
    )


def test_sl009_unresolved_label_target_flagged():
    index, links, _ = build_index([DATA / "unbalanced.md"], [])
    diags = sl009_unresolved_target(index, links)
    assert any(d.code == "SL009" and "nonexistent-spec" in d.message for d in diags)


def test_clean_fixture_passes_all_rules():
    index, links, per_file = build_index([DATA / "clean.md"], [])
    md = {DATA / "clean.md": per_file[DATA / "clean.md"]}
    all_diags = (
        sl001_filename_label(md)
        + sl002_heading_format(md)
        + sl003_label_uniqueness(index)
        + sl004_hierarchy(index)
        + sl005_length(md)
        + sl007_target_syntax(links)
        + sl008_bidirectional(index, links)
        + sl009_unresolved_target(index, links)
    )
    # SL006 (heading weight) is allowed to fire on the tiny fixture; not asserted.
    assert all(d.code == "SL006" for d in all_diags), (
        "clean fixture should pass all Group A/B rules except possibly SL006: "
        + ", ".join(d.render() for d in all_diags)
    )
