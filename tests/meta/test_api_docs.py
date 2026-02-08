"""Meta-test: ensure auto-generated API docs are up to date with source code.

If this test fails, run:
    python scripts/generate_api_docs.py
"""

import hashlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "sidestage"
HASH_FILE = PROJECT_ROOT / "docs" / "api" / ".source_hash"


def _collect_source_files(src_dir: Path) -> list[Path]:
    """Collect all .py files under src/sidestage/, sorted deterministically."""
    return sorted(
        p for p in src_dir.rglob("*.py")
        if "__pycache__" not in p.parts
    )


def _compute_source_hash(files: list[Path]) -> str:
    """Compute SHA-256 over source paths and contents."""
    hasher = hashlib.sha256()
    for filepath in files:
        rel = filepath.relative_to(SRC_DIR)
        hasher.update(str(rel).encode())
        hasher.update(filepath.read_bytes())
    return hasher.hexdigest()


def test_api_docs_up_to_date():
    """Verify that generated API docs match the current source code.

    Fails if docs/api/.source_hash is missing or does not match
    the hash of current source files.

    To fix: run ``python scripts/generate_api_docs.py``
    """
    assert HASH_FILE.exists(), (
        "API docs have not been generated yet. "
        "Run: python scripts/generate_api_docs.py"
    )

    stored_hash = HASH_FILE.read_text().strip()
    files = _collect_source_files(SRC_DIR)
    current_hash = _compute_source_hash(files)

    assert stored_hash == current_hash, (
        "API docs are stale -- source files have changed since last generation. "
        "Run: python scripts/generate_api_docs.py"
    )
