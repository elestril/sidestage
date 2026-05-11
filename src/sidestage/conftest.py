from __future__ import annotations

from pathlib import Path

import pytest

from sidestage.campaign import Campaign


@pytest.fixture(scope="session")
def minimal_campaign() -> Campaign:
    """Session-scoped fixture loading the minimal in-tree testdata campaign.

    Loads `src/sidestage/testdata/minimal_campaign` exactly once per test
    session. Use for happy-path read-only assertions on campaign shape.

    NOTE: `Campaign.load` mutates `App.factory` as a side effect. Tests that
    need a clean `App.factory` / `App._actors` state MUST mock or override —
    do not rely on this fixture for those.
    """
    path = Path(__file__).parent / "testdata" / "minimal_campaign"
    return Campaign.load(path)
