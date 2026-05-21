"""speclint: Rule registry.

Severity is hardcoded per code in the rule modules; the CLI may promote
warnings to errors via `--warn-as-error`.
"""

from __future__ import annotations

from speclint.rules.links import run_group_b
from speclint.rules.structural import run_group_a

ALL_CODES = (
    "SL001",
    "SL002",
    "SL003",
    "SL004",
    "SL005",
    "SL006",
    "SL007",
    "SL008",
    "SL009",
)

__all__ = ["ALL_CODES", "run_group_a", "run_group_b"]
